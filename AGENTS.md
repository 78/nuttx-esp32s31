# Repository Working Guide

## Scope

This repository contains the maintained Apache NuttX port and reproducible
integration for the ESP32-S31-Function-CoreBoard-1.

Keep the public tree focused on buildable product code, maintained fixes,
reproducible build tools, and bounded regression tests. Historical experiments,
root-cause investigations, raw serial logs, A/B artifacts, and legacy worktrees
belong under the ignored `.archive/` directory.

## Repository boundaries

- `platform/`: board profiles and host-side integration tools.
- `nuttx/`: NuttX fork/worktree. Preserve existing changes.
- `nuttx-apps/`: NuttX Apps fork/worktree. Preserve existing changes.
- `deps/esp-hal-3rdparty/`: the single HAL fork/worktree.
- `deps/f0.lock.json`: current machine-readable dependency truth.
- `out/`: rebuildable output; never commit it.
- `tmp/`: local toolchains and reference checkouts; never commit it.
- `.archive/`: private local history; never commit it or make production depend on it.

The repository root is the integration repository. Do not create another nested
project repository under it.

## Change discipline

- Inspect the dirty state of `nuttx`, `nuttx-apps`, and the HAL independently.
- Never use `git reset --hard` or bulk checkout to discard existing work.
- Keep hardware mechanisms in the NuttX port and integration policy in
  `platform/`.
- Keep all public documentation, configuration descriptions, and commit
  messages in English.
- Do not add application-platform, SDK, cloud-service, or product-UI scope.
- Do not restore archived diagnostic profiles or patch-on-patch files into the
  production path.
- Do not refresh dependency locks merely to silence a verification failure.
- Never read and echo `.env` values. Wi-Fi credentials must remain local and
  redacted from logs and reports.

## Build and validation

The default build entry is:

```sh
./build.sh
```

Kernel and AppFS images are one ABI unit. Flash `nuttx.bin` and `appfs.img` from
the same output directory and verify the App digest before diagnosing MMU,
scheduler, or U-mode failures.

At minimum, run dependency verification, `diff --check`, and a clean build for
source changes. Changes affecting boot, MMU, SMP, Wi-Fi, AppFS, ABI, or the HAL
require the corresponding hardware regression before they are considered done.
