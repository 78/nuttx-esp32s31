# Repository Layout

The repository root is the GitHub integration repository. It must not contain
another nested project repository with the same structure.

```text
.
├── README.md
├── LICENSE
├── NOTICE
├── THIRD_PARTY_NOTICES.md
├── build.sh
├── platform/
│   ├── boards/
│   └── tools/
├── nuttx/                       # NuttX fork / Git submodule
├── nuttx-apps/                  # NuttX Apps fork / Git submodule
├── deps/
│   ├── esp-hal-3rdparty/        # HAL fork / Git submodule
│   └── f0.lock.json
├── docs/
└── out/                         # Rebuildable local output; never committed
```

## Ownership boundaries

- The NuttX fork owns architecture, kernel, MMU, SMP, drivers, board support,
  and generally reusable fixes.
- The NuttX Apps fork owns required application fixes and the smallest useful
  set of validation applications.
- The `esp-hal-3rdparty` fork owns the synchronized ESP32-S31 components and
  the NuttX adapter. It is the only HAL source tree used by the port.
- The integration repository owns board profiles, reproducible build entry
  points, dependency verification, English documentation, and bounded host
  regression tools.

The three forks are pinned as Git submodules. `deps/f0.lock.json` additionally
records critical nested dependencies and Espressif binary digests so a fresh
recursive clone can reproduce the reviewed source state.

`.archive/`, `tmp/`, `out/`, credentials, raw evidence, and investigation
reports are outside the public repository boundary.
