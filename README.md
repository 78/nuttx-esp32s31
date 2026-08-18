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
