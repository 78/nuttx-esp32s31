#!/usr/bin/env python3
"""Serve a firmware image over plain HTTP to saturate the target Wi-Fi path.

The on-target NSH ``wget`` has no TLS wiring, so an HTTPS origin cannot be
used directly.  Serving the same bytes from the host over plain HTTP on the
local network also produces a much higher sustained receive rate than a WAN
download, which is what the address environment leak probe needs.

Two endpoints are offered:

  /<name>         the file exactly once, for a realistic single download
  /stream/<name>  the same bytes repeated until the client disconnects, so one
                  background ``wget`` can keep the data path busy for the whole
                  probe without relying on NSH loop syntax
"""

import argparse
import os
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CHUNK_SIZE = 32768


def local_address() -> str:
    """Return the address a target on the same network can reach.

    Probing a public address picks the default route, which is the wrong
    interface when a VPN is up.  Callers on such a host must pass --advertise
    with the address of the network the target actually joined.
    """

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect(("8.8.8.8", 53))
        return probe.getsockname()[0]


class BusyHandler(BaseHTTPRequestHandler):
    """Serve the configured payload once or as an endless repetition."""

    protocol_version = "HTTP/1.0"
    payload_path = ""

    def log_message(self, fmt, *args):
        """Report transfers on one line instead of the default two."""

        sys.stderr.write(f"net-busy: {self.client_address[0]} {fmt % args}\n")

    def do_GET(self):
        streaming = self.path.startswith("/stream")
        size = os.path.getsize(self.payload_path)

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        if not streaming:
            self.send_header("Content-Length", str(size))
        self.end_headers()

        sent = 0
        try:
            while True:
                with open(self.payload_path, "rb") as payload:
                    while True:
                        chunk = payload.read(CHUNK_SIZE)
                        if not chunk:
                            break

                        self.wfile.write(chunk)
                        sent += len(chunk)

                if not streaming:
                    break
        except (BrokenPipeError, ConnectionResetError):
            # Expected: the probe kills its background wget when it is done.

            sys.stderr.write(f"net-busy: client closed after {sent} bytes\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("payload", help="file to serve")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--advertise",
        help="address to publish in the URLs instead of the default route")
    args = parser.parse_args()

    if not os.path.isfile(args.payload):
        print(f"net-busy: no such file: {args.payload}", file=sys.stderr)
        return 1

    BusyHandler.payload_path = args.payload
    name = os.path.basename(args.payload)
    address = args.advertise or local_address()

    server = ThreadingHTTPServer(("0.0.0.0", args.port), BusyHandler)
    server.daemon_threads = True
    print(f"NET_BUSY_URL=http://{address}:{args.port}/{name}")
    print(f"NET_BUSY_STREAM_URL=http://{address}:{args.port}/stream/{name}")
    print(f"NET_BUSY_PAYLOAD_BYTES={os.path.getsize(args.payload)}")
    sys.stdout.flush()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
