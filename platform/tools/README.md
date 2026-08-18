# Host Tools

The public host tools are limited to dependency management and bounded port
validation:

- `verify_f0_dependencies.py` verifies pinned repositories, nested Git links,
  and required binary digests.
- `smp_pthread_soak.py` validates concurrent U-mode processes, SMP load,
  address-environment reclamation, and TLB shootdown conservation.
- `net_busy_server.py` provides a local sustained TCP stream for network
  teardown regression.

Wi-Fi credentials and local network addresses must never be written to source,
reports, or committed logs.
