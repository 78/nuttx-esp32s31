# NuttX Port for Espressif ESP32-S31

This repository provides a reproducible Apache NuttX integration for the
**ESP32-S31-Function-CoreBoard-1**. It combines maintained NuttX, NuttX Apps,
and Espressif HAL forks with board profiles, dependency verification, build
tools, and bounded hardware regression tests.

This is a NuttX board and SoC port. It does not contain an application
platform, SDK, cloud service, or product UI.

## Current capabilities

- Dual-core RISC-V S-mode NuttX with U-mode ELF execution
- Sv32 virtual memory, cached PSRAM address spaces, and cross-core TLB
  shootdown
- LittleFS-backed AppFS with ELF and SHA-256 validation
- Wi-Fi station mode, DHCP, DNS, NTP, TCP, TLS, and HTTP
- Automated boot, isolation, SMP, network, TLB, and multi-process regression

## Console demonstration

The following abridged capture shows Wi-Fi connectivity and independent U-mode
applications running across both CPU cores. Network names, credentials,
addresses, and device identifiers are intentionally redacted. The fenced
console block preserves the original line layout and scrolls horizontally on
narrow displays.

```console
nsh> wapi scan wlan0
bssid / frequency / signal level / encode / ssid
<access-point list omitted>

nsh> wapi psk wlan0 <wifi-password> 3 2
nsh> wapi essid wlan0 <wifi-ssid> 1
nsh> renew wlan0
nsh> ifconfig
wlan0  Link encap:Ethernet HWaddr <device-mac> at RUNNING mtu 1500
       inet addr:<local-ip> DRaddr:<gateway> Mask:255.255.255.0

nsh> ping -c 4 example.com
PING <resolved-address> 56 bytes of data
56 bytes from <resolved-address>: icmp_seq=0 time=10.0 ms
56 bytes from <resolved-address>: icmp_seq=1 time=10.0 ms
56 bytes from <resolved-address>: icmp_seq=2 time=10.0 ms
56 bytes from <resolved-address>: icmp_seq=3 time=10.0 ms
4 packets transmitted, 4 received, 0% packet loss

nsh> busy --threads 2 &
[CPU0] APPVERIFY:PASS /system/bin/busy sha256=<verified-sha256>
busy [14:100]
BUSY:START pid=14 mode=auto cpu=1 priority=100 rr-ms=20 threads=2
BUSY:THREAD tid=14 cpu=1
BUSY:THREAD tid=15 cpu=0

nsh> busy &
busy [19:100]
BUSY:START pid=19 mode=auto cpu=0 priority=100 rr-ms=20 threads=1
BUSY:THREAD tid=19 cpu=0

nsh> ps
  TID   PID  PPID CPU PRI POLICY   TYPE    NPX STATE    EVENT     SIGMASK            STACK    USED FILLED    CPU COMMAND
    0     0     6   0   0 FIFO     Kthread   - Assigned           0000000000000000 0003040 0000876  28.8%   0.0% CPU0 IDLE
    1     0     6   1   0 FIFO     Kthread   - Assigned           0000000000000000 0003040 0000368  12.1%   0.0% CPU1 IDLE
    2     0     6 --- 100 RR       Kthread   - Waiting  Semaphore 0000000000000000 0001968 0000620  31.5%   0.0% lpwork 0x2f0106a8 0x2f0106f8
    4     0     6 --- 252 RR       Kthread   - Waiting  Semaphore 0000000000000000 0004016 0000556  13.8%   0.0% esp_timer 0x2f02e888
    5     0     6 --- 253 RR       Kthread   - Waiting  MQ empty  0000000000000000 0006608 0001896  28.6%   0.0% wifi
    6     6     0   1 101 RR       Task      - Running            0000000000000000 0004032 0001188  29.4%   0.8% /system/bin/init
    7     0     6 --- 100 RR       Kthread   - Waiting  Semaphore 0000000000000000 0001968 0000628  31.9%   0.5% netdev-wlan0 0x2f03d160 0
   14    14     6 --- 100 RR       Task      - Ready              0000000000000000 0001968 0000532  27.0%  34.3% busy --threads 2
   15    14     6 --- 100 RR       pthread   - Ready              0000000000000000 0002016 0000452  22.4%  32.5% busy 0x61002ad2 0x2
   19    19     6 --- 100 RR       Task      - Ready              0000000000000000 0002000 0000532  26.6%  30.7% busy

nsh> free
      total       used       free    maxused    maxfree  nused  nfree name
     335332     130228     205104     145896     132456    303     20 Kmem
   16777216    1810432   14966784              14966784               Page

nsh> uptime
00:30:41 up  0:02, load average: 1.00, 1.00, 1.00
nsh> uname -a
NuttX  0.0.0 ec86648c62 risc-v esp32s31-core-function-board
```

## Repository layout

```text
.
├── platform/                    # Board profiles and host-side tools
├── nuttx/                       # Maintained NuttX fork (Git submodule)
├── nuttx-apps/                  # Maintained NuttX Apps fork (Git submodule)
├── deps/
│   ├── esp-hal-3rdparty/        # Unified Espressif HAL fork (Git submodule)
│   └── f0.lock.json             # Machine-readable dependency manifest
├── docs/                        # Maintainer and user documentation
└── build.sh                     # Default build entry point
```

Local build output, toolchains, credentials, and historical investigation
material are excluded from the public repository.

## Clone

For a faster first checkout, clone the integration and its dependencies with
shallow history:

```sh
git clone --depth 1 --recurse-submodules --shallow-submodules \
  https://github.com/78/nuttx-esp32s31.git
cd nuttx-esp32s31
```

If the repository was cloned without submodules, run:

```sh
git submodule update --init --recursive
```

## Build

Install the RISC-V NuttX toolchain, CMake, Ninja, Python 3, and the ESP-IDF
tool environment pinned by `deps/f0.lock.json`. Export `IDF_PATH`, then run:

```sh
python3 -m venv .venv-nuttx
. .venv-nuttx/bin/activate
python -m pip install -r requirements.txt
./build.sh
```

The Python requirements cover both configuration (`kconfiglib`) and serial
hardware regression (`pyserial`).

The default production output is written to `out/esp32s31-production/`.
`nuttx.bin` and `appfs.img` form one ABI-matched image set and must always be
built, distributed, and flashed together.

To build the validation profile with the regression applications enabled:

```sh
S31_PROFILE=validation ./build.sh
```

## Dependency verification

The build verifies the pinned source revisions, nested Git links, and required
Espressif binary digests before configuration. It never refreshes the lock
file automatically.

Run the verifier directly with:

```sh
python3 platform/tools/verify_f0_dependencies.py
```

## Hardware validation

Hardware tests use the validation profile. Flash `nuttx.bin` and `appfs.img`
from the same output directory before running the smoke test in the NuttX
submodule:

```sh
python3 nuttx/tools/espressif/esp32s31_nuttx_smoke.py \
  --port <serial-port> --boots 3 --e1 --e1-rounds 3 \
  --smp-busy-rounds 10 --tlb-stress
```

Wi-Fi credentials must be supplied through local environment variables. They
must never be committed or included in logs.

## License

The integration repository is licensed under Apache License 2.0. The Git
submodules and third-party components retain their own license, notice, and
copyright files. See `THIRD_PARTY_NOTICES.md`.
