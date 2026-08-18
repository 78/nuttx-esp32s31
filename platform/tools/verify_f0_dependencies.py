#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

def run_git(repo: Path, *args: str) -> bytes:
    command = [
        "git",
        "-C",
        str(repo),
        "-c",
        "submodule.recurse=false",
        *args,
    ]
    return subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def untracked_digest(repo: Path) -> str:
    raw = run_git(repo, "ls-files", "--others", "--exclude-standard", "-z")
    names = sorted(item.decode() for item in raw.split(b"\0") if item)
    digest = hashlib.sha256()
    for name in names:
        path = repo / name
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def resolve_repo(root: Path, candidates: list[str]) -> Path:
    for candidate in candidates:
        path = root / candidate
        if path.is_dir():
            return path
    raise FileNotFoundError(" or ".join(candidates))


def verify_repo(root: Path, entry: dict) -> list[str]:
    errors = []
    try:
        repo = resolve_repo(root, entry["candidates"])
    except FileNotFoundError as error:
        return [f'{entry["name"]}: missing {error}']

    actual_commit = run_git(repo, "rev-parse", "HEAD").decode().strip()
    patch = run_git(
        repo,
        "diff",
        "--ignore-submodules=all",
        "--full-index",
        "--binary",
        "HEAD",
    )
    checks = {
        "commit": actual_commit,
        "patch_sha256": sha256(patch),
        "untracked_sha256": untracked_digest(repo),
    }
    for field, actual in checks.items():
        expected = entry[field]
        if actual != expected:
            errors.append(
                f'{entry["name"]}: {field} expected {expected}, got {actual}'
            )

    bundle_name = entry.get("bundle")
    expected_bundle = entry.get("bundle_sha256")
    if bundle_name is not None:
        bundle = root / bundle_name
        actual_bundle = sha256(bundle.read_bytes()) if bundle.is_file() else None
        if actual_bundle != expected_bundle:
            errors.append(
                f'{entry["name"]}: bundle expected {expected_bundle}, '
                f"got {actual_bundle}"
            )
    elif expected_bundle is not None:
        errors.append(f'{entry["name"]}: bundle_sha256 requires a bundle path')

    index = run_git(repo, "ls-files", "-s").decode().splitlines()
    gitlinks = {}
    for line in index:
        metadata, _, name = line.partition("\t")
        mode, object_id, _stage = metadata.split()
        if mode == "160000":
            gitlinks[name] = object_id
    for name, expected in entry.get("gitlinks", {}).items():
        actual = gitlinks.get(name)
        if actual != expected:
            errors.append(
                f'{entry["name"]}: gitlink {name} expected {expected}, got {actual}'
            )

    for name, expected in entry.get("files", {}).items():
        path = repo / name
        actual = sha256(path.read_bytes()) if path.is_file() else None
        if actual != expected:
            errors.append(
                f'{entry["name"]}: file {name} expected {expected}, got {actual}'
            )

    if not errors:
        print(f'{entry["name"]}: PASS ({repo.relative_to(root)})')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the frozen F.0 dependencies")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[2]
    )
    args = parser.parse_args()
    root = args.root.resolve()
    lock_path = root / "deps/f0.lock.json"
    lock = json.loads(lock_path.read_text())

    errors = []
    for entry in lock["repositories"]:
        errors.extend(verify_repo(root, entry))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("F0_DEPENDENCY_LOCK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
