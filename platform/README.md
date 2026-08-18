# Integration Support

This directory contains only integration assets for the ESP32-S31 NuttX port:

- `boards/` stores reproducible production and validation configuration
  profiles.
- `tools/` stores host-side dependency and bounded regression utilities.

SoC mechanisms, drivers, MMU code, and scheduler integration belong in the
NuttX fork. Espressif component adaptation belongs in the HAL fork. This
directory must not become an application framework or product SDK.
