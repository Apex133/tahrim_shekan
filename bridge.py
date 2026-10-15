#!/usr/bin/env python3
"""tahrim-bridge: minimal HTTP proxy (CONNECT + absolute-GET) that forwards into the
SOCKS5 inbound at 127.0.0.1:12334. Exists because Hiddify here exposes SOCKS only,
while python-urllib/apt/npm need an http:// proxy. Stdlib only."""
import socket
import threading

SOCKS = ("127.0.0.1", 12334)
LISTEN = ("127.0.0.1", 8888)


def recvn(s, n):
    buf = b""
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise OSError("short read")
        buf += chunk
    return buf


def socks_connect(host, port):
    s = socket.create_connection(SOCKS, timeout=10)
    s.settimeout(10)
    s.sendall(b"\x05\x01\x00")
    if recvn(s, 2) != b"\x05\x00":
        raise OSError("socks greeting refused")
    try:
        atyp, addr = b"\x01", socket.inet_aton(host)
    except OSError:
        if ":" in host:
            atyp, addr = b"\x04", socket.inet_pton(socket.AF_INET6, host)
        else:
            if len(host.encode()) > 255:
                raise OSError("hostname too long")
            atyp, addr = b"\x03", bytes([len(host.encode())]) + host.encode()
    s.sendall(b"\x05\x01\x00" + atyp + addr + port.to_bytes(2, "big"))
    resp = recvn(s, 4)
    if resp[1] != 0:
        raise OSError(f"socks connect refused (code {resp[1]})")
    skip = {b"\x01": 4 + 2, b"\x04": 16 + 2}.get(resp[3:4])
    if skip is None:
        dlen = recvn(s, 1)[0]
        skip = dlen + 2
    recvn(s, skip)
    s.settimeout(None)
    return s


def pump(a, b):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(conn):
    try:
        conn.settimeout(30)
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 16384:
            chunk = conn.recv(16384)
            if not chunk:
                return
            head += chunk
        line, _, rest = head.partition(b"\r\n\r\n")
        method, target, _ver = line.split(b" ", 2)
        if method == b"CONNECT":
            host, _, port = target.decode().rpartition(":")
            upstream = socks_connect(host, int(port))
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        elif target.startswith(b"http://"):
            authority, _, path = target[7:].partition(b"/")
            host, _, p = authority.rpartition(b":")
            port = int(p) if p.isdigit() else 80
            upstream = socks_connect(host.decode(), port)
            upstream.sendall(line.split(b" ", 1)[0] + b" /" + path + b" HTTP/1.1\r\n" + rest)
        else:
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        conn.settimeout(None)
        t = threading.Thread(target=pump, args=(conn, upstream), daemon=True)
        t.start()
        pump(upstream, conn)
        t.join(timeout=5)
    except Exception as e:
        try:
            conn.sendall(f"HTTP/1.1 502 tahrim-bridge: {e}\r\n\r\n".encode())
        except OSError:
            pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(128)
    print(f"tahrim-bridge http://{LISTEN[0]}:{LISTEN[1]} -> socks5://{SOCKS[0]}:{SOCKS[1]}", flush=True)
    while True:
        conn, _ = srv.accept()
        threading.Thread(target=handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
