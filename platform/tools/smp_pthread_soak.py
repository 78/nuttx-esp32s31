#!/usr/bin/env python3
#
# SPDX-License-Identifier: Apache-2.0
#
"""Bounded production regression for concurrent U-mode address environments.

Each round starts several unpinned ``busy`` processes that each run more than
one U-mode thread and proves that all of their independent address environments
are live at the same time.  While those Apps saturate both CPUs, a foreground
``tlbstress`` App grows and tears down mappings in another address environment.
The runner then kills every busy App and requires the kernel's ``/dev/s31stat``
created/destroyed/live counters to return exactly to the per-round baseline.

Allocator output remains a capacity diagnostic, but never decides whether an
address environment leaked.  TLB shootdown send/ack/timeout counters are also
gated so the production path, rather than the old stress profile alone, is the
source of truth.

The run stops at the first fatal target output so the failing console state is
preserved for analysis instead of being overwritten by later rounds.
"""

import argparse
import datetime
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

import serial

sys.path.insert(0, str(Path(__file__).resolve().parents[2] /
                       "nuttx/tools/espressif"))

from esp32s31_nuttx_smoke import (  # noqa: E402
    PROMPT,
    collect_until_prompt,
    find_usb_console,
    hard_reset,
    parse_s31stat,
    parse_tlbshoot_stats,
    run_command,
)

# Target output that means the run must stop.  ``ADDRENV: cpu=`` is the S31
# page-fault diagnostic; the normal ``/dev/s31stat`` line begins with
# ``ADDRENV: created=`` and must not trip this gate.

FATAL_MARKERS = (
    "PANIC",
    "EXCEPTION",
    "Assertion failed",
    "ADDRENV: cpu=",
    "Segmentation fault",
    "S31SM:M-TRAP",
    "pthread_create failed",
    "posix_spawnp failed",
)

# NSH prints the region name at the end of each row, and the page pool leaves
# some columns empty, so anchor on the trailing name and take the leading
# total/used/free triplet.

MEMORY_ROW = re.compile(
    r"(?m)^\s*(\d+)\s+(\d+)\s+(\d+)\b.*?\b(Kmem|Page)\s*$")
LOAD_LINE = re.compile(r"(?m)^\s*([0-9]+(?:\.[0-9]+)?)%\s*$")

# The App announces each thread once it is spinning in U-mode.  Match as
# little of that line as possible: a saturated native USB console drops single
# characters often enough to mangle the label itself.

BUSY_THREAD = re.compile(r"\btid=(\d+)\s+cpu=\d+")

# Anchor a ps row on its scheduling policy column.  Truncated console output
# regularly leaves fragments that look like a leading "tid pid" pair, and a
# fragment that also carries a plausible policy field is far less likely.

PS_ROW = re.compile(
    r"(?m)^\s*(\d+)\s+(\d+)\s+(\d+)\s+(?:\d+|-+)\s+\d+\s+"
    r"(?:FIFO|RR|SPORADIC)\b")


class SoakFailure(Exception):
    """A target-side failure that must stop the run."""


class Soak:
    """One console session driving repeated multi-threaded App rounds."""

    def __init__(self, port: serial.Serial, log, args) -> None:
        self.port = port
        self.log = log
        self.args = args
        self.recent = ""
        self.round_output = ""

    def emit(self, text: str) -> None:
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {text}"
        print(line, flush=True)
        self.log.write(line + "\n")
        self.log.flush()

    def absorb(self, text: str) -> str:
        """Record console output and fail on any fatal marker."""

        if text:
            self.log.write(text)
            self.log.flush()
        self.recent = (self.recent + text)[-16384:]
        self.round_output += text
        hits = [marker for marker in FATAL_MARKERS if marker in text]
        if hits:
            raise SoakFailure(f"target reported {hits}")
        return text

    def command(self, command: str, timeout: float) -> str:
        """Run one NSH command, tolerating occasional console desync.

        A saturated native USB console can drop or interleave bytes, which
        looks like a prompt timeout even though the target is healthy.  Retry
        those, but never retry past a fatal marker.
        """

        last = None
        for attempt in range(3):
            try:
                return self.absorb(run_command(self.port, command,
                                               timeout=timeout))
            except TimeoutError as error:
                self.absorb(str(error))
                last = error
                self.emit(f"WARN console timeout on {command!r} "
                          f"(attempt {attempt + 1})")
                self.port.reset_input_buffer()
                time.sleep(0.5)

        self.interrogate()
        raise SoakFailure(f"console did not answer {command!r}: {last}")

    def interrogate(self) -> None:
        """Try to learn whether a silent target is hung or just backed up.

        A stall with no PANIC and no output looks the same from here whether
        the console driver is wedged or both CPUs are stuck.  Wait far longer
        than any command should take, then poke the shell without resetting the
        board, so the state is still there if it has to be examined by hand.
        """

        self.emit("console silent, interrogating without reset")

        for label, probe in (("passive", b""), ("newline", b"\r\n"),
                             ("interrupt", b"\x03"), ("newline", b"\r\n")):
            if probe:
                try:
                    self.port.write(probe)
                    self.port.flush()
                except serial.SerialException as error:
                    self.emit(f"probe {label}: write failed: {error}")
                    return

            got = b""
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                got += self.port.read(4096)
                time.sleep(0.1)

            self.absorb(got.decode("utf-8", errors="replace"))
            self.emit(f"probe {label}: {len(got)} bytes"
                      f"{' -> ' + repr(got[-200:]) if got else ''}")
            if got:
                return

    def hold(self, seconds: float) -> None:
        """Let the Apps run, watching the console for fatal output."""

        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(0.2)
            pending = self.port.read(self.port.in_waiting)
            if pending:
                self.absorb(pending.decode("utf-8", errors="replace"))

    def drain(self) -> None:
        self.absorb(self.port.read(self.port.in_waiting)
                    .decode("utf-8", errors="replace"))

    def sample_memory(self) -> dict[str, int]:
        output = self.command("free", timeout=8.0)
        counters: dict[str, int] = {}
        for _total, used, free, name in MEMORY_ROW.findall(output):
            counters[f"{name.lower()}_used"] = int(used)
            counters[f"{name.lower()}_free"] = int(free)

        if "kmem_used" not in counters or "page_used" not in counters:
            raise SoakFailure(f"could not parse free output: {output!r}")
        return counters

    def memory(self) -> dict[str, int]:
        """Read the allocator counters once they stop moving.

        Group teardown finishes on a work queue, so an immediate reading after
        kill can still include memory that is about to come back.  Only a
        settled value is comparable across rounds.
        """

        previous = self.sample_memory()
        for _ in range(5):
            time.sleep(0.6)
            current = self.sample_memory()
            if current == previous:
                return current

            previous = current

        return previous

    def s31stat(self, label: str) -> dict[str, int]:
        """Return and log the kernel address-environment counters."""

        parsed = parse_s31stat(self.command("cat /dev/s31stat", timeout=8.0))
        if parsed is None or "addrenv" not in parsed:
            raise SoakFailure(f"could not parse /dev/s31stat at {label}")

        counters = parsed["addrenv"]
        balanced = counters["created"] - counters["destroyed"] == \
            counters["live"]
        self.emit(
            f"s31stat[{label}] created={counters['created']} "
            f"destroyed={counters['destroyed']} live={counters['live']} "
            f"livemax={counters['live_max']} "
            f"pages={counters['pages_freed']} pgt={counters['pgt_freed']} "
            f"balance={'PASS' if balanced else 'FAIL'}")
        if not balanced:
            raise SoakFailure(
                f"unbalanced addrenv counters at {label}: {counters}")

        return counters

    def wait_addrenv_returned(self, before: dict[str, int],
                              expected_created: int,
                              label: str) -> dict[str, int]:
        """Wait for deferred group teardown and require exact conservation."""

        deadline = time.monotonic() + 12.0
        after = self.s31stat(label)
        while time.monotonic() < deadline:
            created = after["created"] - before["created"]
            destroyed = after["destroyed"] - before["destroyed"]
            live = after["live"] - before["live"]
            if (created == expected_created and
                    destroyed == expected_created and live == 0):
                return after

            time.sleep(0.6)
            after = self.s31stat(label)

        raise SoakFailure(
            f"addrenv did not return after {label}: expected "
            f"created=destroyed={expected_created} live=0, got "
            f"created={after['created'] - before['created']} "
            f"destroyed={after['destroyed'] - before['destroyed']} "
            f"live={after['live'] - before['live']}")

    def tlbshoot(self, label: str) -> dict[str, int]:
        """Return and log production TLB shootdown counters."""

        parsed = parse_tlbshoot_stats(
            self.command("cat /dev/tlbshoot", timeout=8.0))
        if parsed is None:
            raise SoakFailure(f"could not parse /dev/tlbshoot at {label}")

        self.emit(
            f"tlbshoot[{label}] send={parsed['send']} ack={parsed['ack']} "
            f"timeout={parsed['timeout']} range={parsed['range']} "
            f"global={parsed['global']}")
        return parsed

    def run_mapping_workload(self) -> None:
        """Grow mappings in a third addrenv while busy Apps stay runnable."""

        if self.args.skip_tlb_workload:
            return

        command = ("/system/bin/tlbstress --mode auto "
                   f"--rounds {self.args.tlb_rounds} "
                   f"--pages {self.args.tlb_pages}")
        if len(command) > 63:
            raise SoakFailure(
                f"tlbstress command exceeds the NSH 63-character limit: "
                f"{len(command)}")

        output = self.command(
            command, timeout=max(30.0, self.args.tlb_rounds * 2.0))
        passed = "TLBSTRESS:PASS" in output
        failed = "TLBSTRESS:FAIL" in output
        if not passed or failed:
            raise SoakFailure("foreground tlbstress did not pass")

        self.emit(
            f"mapping-workload=PASS rounds={self.args.tlb_rounds} "
            f"pages={self.args.tlb_pages}")

    def load(self) -> float:
        match = LOAD_LINE.search(self.command("cat /proc/cpuload",
                                              timeout=8.0))
        return float(match.group(1)) if match else -1.0

    def app_threads(self) -> dict[int, int]:
        """Return {tid: pid} for every scheduler row with a parent.

        Older ``ps`` output reported the idle threads and kernel workers with
        PPID 0.  Current SMP output associates some of those rows with init,
        so callers must compare against a pre-launch snapshot instead of
        treating every non-zero PPID as an App thread.  This still avoids the
        command column, which the saturated console can truncate.
        """

        listed = {}
        for tid, pid, ppid in PS_ROW.findall(self.command("ps", timeout=10.0)):
            if int(ppid) != 0:
                listed[int(tid)] = int(pid)

        return listed

    def alive(self, tids: set[int]) -> set[int]:
        """Return which of the given thread ids the scheduler still lists."""

        return set(self.app_threads()) & tids

    def collect_round(self, baseline_tids: set[int]) -> \
            tuple[set[int], set[int]]:
        """Sample ps until the App threads it reports are self-consistent.

        Any single ps output can lose characters under full load, which shows
        up as a missing row or a corrupted id.  Rather than trusting one
        sample, accumulate over several and require the result to satisfy the
        invariants of the round: the expected number of threads, grouped into
        the expected number of processes, where every process id is also the
        tid of its own main thread.  Corruption cannot satisfy all three, so a
        consistent result is a real one.
        """

        expect_threads = self.args.processes * self.args.threads
        tids: set[int] = set()
        pids: set[int] = set()
        listed: dict[int, int] = {}

        for _ in range(8):
            self.drain()
            current = self.app_threads()
            listed.update({tid: pid for tid, pid in current.items()
                           if tid not in baseline_tids})
            tids = set(listed)
            pids = {pid for pid in listed.values() if pid in tids}
            if len(tids) == expect_threads and \
                    len(pids) == self.args.processes:
                return pids, tids

            time.sleep(0.3)

        raise SoakFailure(
            f"expected {expect_threads} App threads in {self.args.processes} "
            f"processes, ps settled on {listed}")

    def start_round(self) -> tuple[set[int], set[int]]:
        """Launch the round's Apps and return their (pids, tids)."""

        baseline_tids = set(self.app_threads())
        command = f"/system/bin/busy --threads {self.args.threads} &"
        for _ in range(self.args.processes):
            self.command(command, timeout=10.0)
            time.sleep(0.2)
            self.drain()

        pids, tids = self.collect_round(baseline_tids)

        # Being listed only proves the thread exists.  The App's own line is
        # what proves it reached U-mode and started executing, so check it too
        # - but a dropped character there must not fail an otherwise healthy
        # round, and the per-round load check already covers a stalled thread.

        announced = {int(tid) for tid in BUSY_THREAD.findall(
            self.round_output)} & tids
        if announced != tids:
            self.emit(f"WARN only {sorted(announced)} of {sorted(tids)} "
                      f"announced U-mode entry")

        return pids, tids

    def reap(self, pids: set[int], tids: set[int]) -> None:
        for pid in sorted(pids):
            self.command(f"kill {pid}", timeout=8.0)

        for attempt in range(3):
            time.sleep(0.5)
            self.drain()
            leftover = self.alive(tids)
            if not leftover:
                return

            self.emit(f"WARN {sorted(leftover)} still listed "
                      f"(attempt {attempt + 1})")

        raise SoakFailure(f"threads survived kill: {sorted(self.alive(tids))}")

    def boot(self) -> None:
        hard_reset(self.port)
        boot = collect_until_prompt(self.port, 15.0)
        self.absorb(boot.decode("utf-8", errors="replace"))
        if PROMPT not in boot:
            raise SoakFailure("no NSH prompt after reset")

        self.emit("target booted")


def run(args, log) -> int:
    port = serial.Serial(args.port or find_usb_console(), 115200,
                         timeout=0.05, write_timeout=2.0, exclusive=True)
    port.dtr = False
    port.rts = False
    time.sleep(0.1)

    soak = Soak(port, log, args)
    expect_threads = args.processes * args.threads
    memory_baseline: Optional[dict[str, int]] = None
    started = time.monotonic()
    deadline = started + args.hours * 3600 if args.hours else None
    round_index = 0

    try:
        soak.boot()

        # Record the untouched allocator state so a one-time increase during
        # the first round is not confused with a per-round leak.

        pristine = soak.memory()
        soak.emit(f"pristine kmem={pristine['kmem_used']}/"
                  f"{pristine['kmem_free']} "
                  f"page={pristine['page_used']}/{pristine['page_free']}")
        suite_addrenv = soak.s31stat("suite-start")
        suite_tlb = soak.tlbshoot("suite-start")

        while True:
            if deadline is not None and time.monotonic() >= deadline:
                break

            if args.rounds and round_index >= args.rounds:
                break

            round_index += 1
            soak.round_output = ""
            before_addrenv = soak.s31stat(f"round-{round_index}-before")
            before_tlb = soak.tlbshoot(f"round-{round_index}-before")
            pids, tids = soak.start_round()
            soak.hold(args.hold_seconds)

            load = soak.load()

            # Accumulate over several samples: a lost ps row can only make a
            # live thread look absent, never the other way around.

            alive: set[int] = set()
            for _ in range(4):
                alive |= soak.alive(tids)
                if len(alive) == expect_threads:
                    break

                time.sleep(0.3)

            if len(alive) != expect_threads:
                raise SoakFailure(
                    f"expected {expect_threads} live threads, the scheduler "
                    f"lists {sorted(alive)} of {sorted(tids)}")

            if load < args.min_load:
                raise SoakFailure(f"load {load}% below {args.min_load}%")

            # Sampling live while all busy processes still run is the proof
            # that this is a concurrent multi-address-space test rather than
            # a fast sequence of single-App lifetimes.

            live_addrenv = soak.s31stat(f"round-{round_index}-live")
            live_delta = live_addrenv["live"] - before_addrenv["live"]
            if live_delta != args.processes:
                raise SoakFailure(
                    f"expected {args.processes} concurrent addrenvs, "
                    f"observed live delta {live_delta}")

            soak.run_mapping_workload()

            # tlbstress must not disturb the busy Apps that were already live.

            alive_after_tlb: set[int] = set()
            for _ in range(4):
                alive_after_tlb |= soak.alive(tids)
                if len(alive_after_tlb) == expect_threads:
                    break

                time.sleep(0.3)

            if len(alive_after_tlb) != expect_threads:
                raise SoakFailure(
                    "busy Apps did not survive the mapping workload: "
                    f"{sorted(alive_after_tlb)} of {sorted(tids)}")

            soak.reap(pids, tids)
            expected_created = args.processes + \
                (0 if args.skip_tlb_workload else 1)
            after_addrenv = soak.wait_addrenv_returned(
                before_addrenv, expected_created,
                f"round-{round_index}-after")
            after_tlb = soak.tlbshoot(f"round-{round_index}-after")

            send_delta = after_tlb["send"] - before_tlb["send"]
            ack_delta = after_tlb["ack"] - before_tlb["ack"]
            timeout_delta = after_tlb["timeout"] - before_tlb["timeout"]
            if (send_delta <= 0 or ack_delta != send_delta or
                    timeout_delta != 0 or after_tlb["timeout"] != 0):
                raise SoakFailure(
                    f"invalid TLB shootdown delta send={send_delta} "
                    f"ack={ack_delta} timeout={timeout_delta} "
                    f"total-timeout={after_tlb['timeout']}")

            counters = soak.memory()

            if memory_baseline is None:
                memory_baseline = counters
                once = {key: counters[key] - pristine.get(key, 0)
                        for key in counters if key.endswith("_used")}
                drift = f"baseline(first-round={once})"
            else:
                deltas = {key: counters[key] - memory_baseline.get(key, 0)
                          for key in counters}
                leaked = {key: value for key, value in deltas.items()
                          if key.endswith("_used") and value != 0}
                drift = "0" if not leaked else str(leaked)
                if leaked and args.fail_on_drift:
                    raise SoakFailure(f"allocator drift after reap: {leaked}")

            elapsed = datetime.timedelta(
                seconds=int(time.monotonic() - started))
            soak.emit(
                f"round={round_index} elapsed={elapsed} load={load}% "
                f"threads={len(alive)} pids={sorted(pids)} "
                f"kmem={counters['kmem_used']}/{counters['kmem_free']} "
                f"page={counters.get('page_used')}/"
                f"{counters.get('page_free')} drift={drift} "
                f"addrenv={after_addrenv['created'] - before_addrenv['created']}/"
                f"{after_addrenv['destroyed'] - before_addrenv['destroyed']}/"
                f"{after_addrenv['live'] - before_addrenv['live']} "
                f"tlb={send_delta}/{ack_delta}/{timeout_delta}")

        final_addrenv = soak.s31stat("suite-final")
        final_tlb = soak.tlbshoot("suite-final")
        expected_suite_created = round_index * (
            args.processes + (0 if args.skip_tlb_workload else 1))
        suite_created = final_addrenv["created"] - suite_addrenv["created"]
        suite_destroyed = (final_addrenv["destroyed"] -
                           suite_addrenv["destroyed"])
        suite_live = final_addrenv["live"] - suite_addrenv["live"]
        suite_send = final_tlb["send"] - suite_tlb["send"]
        suite_ack = final_tlb["ack"] - suite_tlb["ack"]
        suite_timeout = final_tlb["timeout"] - suite_tlb["timeout"]
        if (suite_created != expected_suite_created or
                suite_destroyed != expected_suite_created or
                suite_live != 0 or suite_send <= 0 or
                suite_ack != suite_send or suite_timeout != 0):
            raise SoakFailure(
                "suite conservation failed: "
                f"addrenv={suite_created}/{suite_destroyed}/{suite_live} "
                f"expected-created={expected_suite_created} "
                f"tlb={suite_send}/{suite_ack}/{suite_timeout}")

        soak.emit(
            f"suite-conservation addrenv={suite_created}/"
            f"{suite_destroyed}/{suite_live} "
            f"tlb={suite_send}/{suite_ack}/{suite_timeout}")

    except SoakFailure as error:
        soak.emit(f"FAIL round={round_index}: {error}")
        log.write("\n----- recent console output -----\n")
        log.write(soak.recent)
        log.write("\n----- end console output -----\n")
        log.flush()
        print(soak.recent[-4000:], flush=True)
        return 1
    except KeyboardInterrupt:
        soak.emit(f"interrupted after round={round_index}")
        return 130
    finally:
        port.close()

    elapsed = datetime.timedelta(seconds=int(time.monotonic() - started))
    soak.emit(f"PASS rounds={round_index} elapsed={elapsed}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="console device (default: autodetect)")
    parser.add_argument("--processes", type=int, default=2,
                        help="concurrent busy processes per round")
    parser.add_argument("--threads", type=int, default=2,
                        help="U-mode threads per busy process")
    parser.add_argument("--hold-seconds", type=float, default=30.0,
                        help="seconds to keep both CPUs saturated per round")
    parser.add_argument("--hours", type=float, default=24.0,
                        help="stop after this many hours (0 runs forever)")
    parser.add_argument("--rounds", type=int, default=0,
                        help="stop after this many rounds (0 is unlimited)")
    parser.add_argument("--min-load", type=float, default=90.0,
                        help="minimum total CPU load expected per round")
    parser.add_argument("--tlb-rounds", type=int, default=8,
                        help="foreground tlbstress rounds per soak round")
    parser.add_argument("--tlb-pages", type=int, default=4,
                        help="pages allocated per foreground tlbstress round")
    parser.add_argument("--skip-tlb-workload", action="store_true",
                        help="only test concurrent busy App create/kill")
    parser.add_argument("--fail-on-drift", action="store_true",
                        help="stop as soon as an allocator counter drifts")
    parser.add_argument("--log-dir",
                        default="out/esp32s31-production/multi-app-soak",
                        help="directory for the run log")
    args = parser.parse_args()

    if args.processes < 2:
        parser.error("--processes must be at least 2")
    if args.threads < 1:
        parser.error("--threads must be at least 1")
    if args.rounds < 0 or args.hours < 0:
        parser.error("--rounds and --hours must be non-negative")
    if args.rounds == 0 and args.hours == 0:
        parser.error("set a non-zero --rounds or --hours bound")
    if args.tlb_rounds < 1 or args.tlb_pages < 1:
        parser.error("--tlb-rounds and --tlb-pages must be positive")

    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"smp-pthread-soak-{stamp}.log"

    print(f"log: {log_path}", flush=True)
    with log_path.open("w", encoding="utf-8") as log:
        log.write(f"command: {' '.join(sys.argv)}\n")
        log.write(f"cwd: {os.getcwd()}\n\n")
        return run(args, log)


if __name__ == "__main__":
    sys.exit(main())
