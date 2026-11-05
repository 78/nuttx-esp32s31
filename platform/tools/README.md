# Host Tools

The public host tools are limited to dependency management and bounded port
validation:

- `verify_f0_dependencies.py` verifies pinned repositories, nested Git links,
  and required binary digests.
- `smp_pthread_soak.py` validates concurrent U-mode processes, SMP load,
  address-environment reclamation, and TLB shootdown conservation.
- `net_busy_server.py` provides a local sustained TCP stream for network
  teardown regression.

Run the bounded host regressions without a board:

```sh
python3 -m unittest discover -s platform/tools/tests -v
```

These cover esptool executable selection, legacy command compatibility, and
version-check failures. Clean production and validation builds and the
hardware checks in [`docs/FLASHING.md`](../../docs/FLASHING.md) are separate
requirements for changes affecting board bring-up.

Wi-Fi credentials and local network addresses must never be written to source,
reports, or committed logs.
