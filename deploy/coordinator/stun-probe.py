#!/usr/bin/env python3
"""stun-probe.py HOST [PORT] — ask a coordinator's STUN server the question a
Tailscale client asks, and print what it answers.

    ./stun-probe.py mesh.nufi.me
    mesh.nufi.me:3478 -> Binding Response (57 ms) · you are 1.52.176.223:55304

Why this exists instead of `nc -zu` or a stock STUN client: headscale's
embedded STUN server is tailscale's, and tailscale's server answers ONLY a
Binding Request that carries a SOFTWARE attribute of "tailnode" and a
FINGERPRINT — the exact shape its own clients send. A plain RFC 5389 request
(what `stunclient`, `pystun` and most one-liners send) is dropped in silence,
which from outside looks identical to a firewall eating the port. The first
probe of the first field test was that false alarm. This script sends the
shape the server wants, so a timeout here really does mean the packet is not
arriving or not coming back.

Stdlib only. Exit 0 on an answer, 1 on a timeout.
"""
import ipaddress
import os
import socket
import struct
import sys
import time
import zlib

MAGIC = 0x2112A442


def request():
    txn = os.urandom(12)
    software = b"tailnode"
    attr_software = struct.pack("!HH", 0x8022, len(software)) + software
    fingerprint_len = 8
    header = struct.pack("!HHI", 0x0001, len(attr_software) + fingerprint_len, MAGIC) + txn
    body = header + attr_software
    crc = (zlib.crc32(body) & 0xFFFFFFFF) ^ 0x5354554E
    return txn, body + struct.pack("!HHI", 0x8028, 4, crc)


def mapped_address(data, txn):
    """The XOR-MAPPED-ADDRESS the server saw us as, either family."""
    _, length, _ = struct.unpack("!HHI", data[:8])
    key = struct.pack("!I", MAGIC) + txn
    p = 20
    while p < 20 + length:
        attr_type, attr_len = struct.unpack("!HH", data[p:p + 4])
        value = data[p + 4:p + 4 + attr_len]
        if attr_type == 0x0020:
            family = value[1]
            port = struct.unpack("!H", value[2:4])[0] ^ (MAGIC >> 16)
            raw = bytes(a ^ b for a, b in zip(value[4:], key))
            addr = ipaddress.ip_address(raw[:4] if family == 1 else raw[:16])
            if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
                addr = addr.ipv4_mapped
            return "%s:%d" % (addr, port)
        p += 4 + (attr_len + 3) // 4 * 4
    return "?"


def main(argv):
    if len(argv) < 2:
        sys.exit("usage: stun-probe.py HOST [PORT]")
    host = argv[1]
    port = int(argv[2]) if len(argv) > 2 else 3478
    txn, packet = request()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(3)
    started = time.time()
    sock.sendto(packet, (host, port))
    try:
        data, _ = sock.recvfrom(1024)
    except socket.timeout:
        print("%s:%d -> no answer in 3 s (the packet is not arriving, or not coming back)" % (host, port))
        return 1
    msg_type = struct.unpack("!H", data[:2])[0]
    if msg_type != 0x0101 or data[8:20] != txn:
        print("%s:%d -> something answered, but not a Binding Response to this request" % (host, port))
        return 1
    print("%s:%d -> Binding Response (%.0f ms) · you are %s"
          % (host, port, 1000 * (time.time() - started), mapped_address(data, txn)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
