# Flashing and first boot

These instructions apply to the maintained ESP32-S31-Function-CoreBoard-1
production and validation profiles using simple boot. Build with `./build.sh`
or `S31_PROFILE=validation ./build.sh` before flashing. Keep the ESP-IDF tool
environment active so that the pinned ESP32-S31-capable esptool is on `PATH`.

## Image pair and partition layout

The kernel and loadable applications are one ABI unit. Always flash `nuttx.bin`
and `appfs.img` from the same build directory. Verify the host image hashes:

```sh
cd out/esp32s31-production
shasum -a 256 -c images.sha256
cd ../..
```

Use `out/esp32s31-validation` instead when testing validation firmware.

| Flash range | Contents | Target mount |
| --- | --- | --- |
| Kernel starts at `0x2000` | `nuttx.bin`, simple-boot image | None |
| `0x200000` to `0x500000` (exclusive) | Read-only seed region containing `appfs.img` | `/system/bin` (ROMFS) |
| `0x500000` to `0xc00000` (exclusive) | Persistent writable application files | `/apps` (LittleFS) |

The kernel offset comes from the ESP32-S31 simple-boot layout, not the usual
ESP-IDF application partition address. Do not write the standalone `nuttx.bin`
at `0x0` or `0x10000`. The AppFS image offset is
`CONFIG_ESPRESSIF_STORAGE_MTD_OFFSET`; the writable region begins after
`CONFIG_ESP32S31_FLASH_APPFS_SEED_SIZE` (`0x300000`). Thus the boot message
`AppFS writable LittleFS: offset=0x500000 size=0x700000` does not give the
address at which to flash `appfs.img`.

If the partition configuration changes, use the values in that build's
`.config` and the CMake flash target rather than these default addresses.

## Serial interfaces

The maintained profiles use the native USB Serial/JTAG interface for NSH via
`CONFIG_ESPRESSIF_USBSERIAL`. It can also be used by esptool. Linux typically
names this interface `/dev/ttyACM0`; macOS typically uses
`/dev/cu.usbmodem*`. Device numbers are not fixed. Reset or ROM download can
disconnect the interface, so wait for it to re-enumerate and reopen the console.

A USB-to-TTL adapter connected to UART0 provides a recovery flashing path.
The configured board signals are TX GPIO59 and RX GPIO58: adapter RX connects
to board TX, adapter TX to board RX, with a common ground and 3.3 V logic.
Linux commonly names the adapter `/dev/ttyUSB0`; macOS names depend on the
adapter driver. DTR/RTS must be wired to the board's download/reset circuit for
automatic boot-mode selection. With only TX/RX connected, hold BOOT, pulse
RESET, then release BOOT to enter ROM download mode. After UART flashing,
return to the native USB interface for NSH; UART0 is not the console in these
profiles.

Close serial terminal programs before running esptool. If the native interface
is unavailable, use UART0 recovery and check power and cables.

## Write both images

From the repository root, with the build tool environment active:

```sh
ESPTOOL_PORT=/dev/ttyACM0 cmake --build out/esp32s31-production --target flash
```

For validation:

```sh
ESPTOOL_PORT=/dev/ttyACM0 cmake --build out/esp32s31-validation --target flash
```

The flash target writes both images at the configured offsets. Select the
actual native USB or UART adapter path with `ESPTOOL_PORT`.

The equivalent manual command for the default production layout is:

```sh
esptool --chip esp32s31 --port /dev/ttyACM0 --baud 921600 \
  write-flash --flash-size 16MB --flash-mode dio --flash-freq 80m \
  0x2000 out/esp32s31-production/nuttx.bin \
  0x200000 out/esp32s31-production/appfs.img
```

Substitute both paths together for validation. The command writes only the
kernel and ROMFS seed, preserving `/apps`. A full-chip erase destroys writable
application data and is not required for a routine update.

## First boot and regression

Open the native USB console at 115200 baud after reset. On a blank writable
region, LittleFS is formatted once; an existing filesystem is mounted without
destructive reformatting. Both profiles should reach NSH and print:

```text
AppFS writable LittleFS: offset=0x500000 size=0x700000
E1 Wi-Fi station netdev ready
```

Production does not include `sv32test` and must not attempt to install it.
Validation includes the regression applications and installs `sv32test` plus
its SHA-256 manifest into `/apps` on first boot. The `.seeded` marker prevents
reinstallation after user deletion; changing profiles does not clear existing
files or this marker.

Before investigating MMU, scheduler, or U-mode failures, check the target's
`APPVERIFY:PASS` digest against the corresponding file in the same build's
`appfs-root/`. For validation, run `/system/bin/sv32test` explicitly and compare
its reported digest with:

```sh
shasum -a 256 out/esp32s31-validation/appfs-root/sv32test
```

For production, the initial `/system/bin/init` digest should match
`appfs-root/init`. A valid checksum for an old writable `/apps` executable does
not prove that it matches the newly flashed kernel. Use `/system/bin` paths
when checking a new image pair.

Validate production on a board with a blank LittleFS region: confirm no seed
installation failure, Wi-Fi initialization, NSH, and successful station
association, DHCP, and ping. Reboot and confirm the filesystem persists and
Wi-Fi still initializes. Supply network credentials locally and redact them
from captured output.

Then flash the validation image pair and run the bounded regression:

```sh
python3 nuttx/tools/espressif/esp32s31_nuttx_smoke.py \
  --port <native-usb-console> --boots 3 --e1 --e1-rounds 3 \
  --smp-busy-rounds 10 --tlb-stress
```

The network tests read `S31_E1_WIFI_SSID` and `S31_E1_WIFI_PASSWORD` from the
local environment. Never include their values in commands saved to the public
repository or in reports. Hardware checks require an attached board; successful
host builds alone do not establish first-boot or Wi-Fi behavior.
