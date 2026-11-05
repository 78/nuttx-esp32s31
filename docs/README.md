# Documentation

Public documentation describes the maintained ESP32-S31 NuttX port, its build
requirements, dependency boundaries, and reproducible validation procedures.

- [`architecture/REPOSITORY_LAYOUT.md`](architecture/REPOSITORY_LAYOUT.md)
  defines the integration repository and fork boundaries.
- [`FLASHING.md`](FLASHING.md) describes image offsets, serial interfaces,
  first-boot checks, and production/validation hardware regression.

Historical experiments, raw serial logs, root-cause investigations, and A/B
artifacts are private local material under the ignored `.archive/` directory.
