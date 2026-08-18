# Third-Party Notices

This integration repository is licensed under Apache License 2.0. Source and
binary dependencies retain their original licenses and attribution notices.
The authoritative license text for each dependency is the file at the pinned
Git revision.

| Dependency | Upstream | License location |
| --- | --- | --- |
| Apache NuttX | <https://github.com/apache/nuttx> | `nuttx/LICENSE`, `nuttx/NOTICE` |
| Apache NuttX Apps | <https://github.com/apache/nuttx-apps> | `nuttx-apps/LICENSE`, `nuttx-apps/NOTICE` |
| Espressif HAL for third-party frameworks | <https://github.com/espressif/esp-hal-3rdparty> | `deps/esp-hal-3rdparty/LICENSE` and component headers |
| Mbed TLS | <https://github.com/Mbed-TLS/mbedtls> | `deps/esp-hal-3rdparty/components/mbedtls/mbedtls/LICENSE` |
| ESP-IDF build-time components and libraries | <https://github.com/espressif/esp-idf> | the pinned ESP-IDF checkout and its component license files |

Mbed TLS offers a choice of Apache-2.0 or GPL-2.0-or-later; this project uses
it under Apache-2.0. Individual ESP-IDF components may carry additional or
different compatible notices. Redistribution of binaries must preserve the
applicable notices from the exact pinned source release.
