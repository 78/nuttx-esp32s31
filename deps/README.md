# Dependencies

`f0.lock.json` is the machine-readable dependency manifest for the reviewed
ESP32-S31 build. It pins the three source repositories, critical nested Git
links, and the SHA-256 digests of required ESP32-S31 Wi-Fi, PHY, and coexistence
binaries.

Verify it with:

```sh
python3 platform/tools/verify_f0_dependencies.py
```

The public layout pins reviewed commits in the `nuttx`, `nuttx-apps`, and
`esp-hal-3rdparty` Git submodules. External patch bundles are not part of the
published source interface.

The Espressif HAL keeps its upstream mbedTLS submodule at the reviewed commit.
The HAL's own NuttX compatibility patches are applied by its build integration;
an additional patch snapshot of the already-modified mbedTLS worktree is not a
separate dependency.

Do not refresh the lock merely to silence a verification failure. Dependency
changes require review, a clean build, and the corresponding hardware
regression before the lock is updated.
