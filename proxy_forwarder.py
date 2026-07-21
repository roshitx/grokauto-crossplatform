"""
Local proxy forwarder — handles both HTTP and HTTPS (CONNECT) with DataImpulse auth.
Run this before starting the registration script.

Usage: python3 proxy_forwarder.py
Then set proxy in config.json to: http://127.0.0.1:8888
"""
import socket, threading, sys, base64, select

UPSTREAM_HOST = "gw.dataimpulse.com"
UPSTREAM_PORT = 10000
PROXY_USER = "1332938bf1c406319007__cr.de"
PROXY_PASS = "f3444110c56c6dfb"
LOCAL_PORT = 8888

AUTH_HEADER = f"Proxy-Authorization: Basic {base64.b64encode(f'{PROXY_USER}:{PROXY_PASS}'.encode()).decode()}\r\n"

def pipe(s1, s2):
    """Bidirectional pipe between two sockets."""
    try:
        while True:
            r, _, _ = select.select([s1, s2], [], [], 30)
            if not r:
                break
            for sock in r:
                data = sock.recv(65536)
                if not data:
                    return
                other = s2 if sock is s1 else s1
                other.sendall(data)
    except Exception:
        pass
    finally:
        try: s1.close()
        except: pass
        try: s2.close()
        except: pass

def handle_connect(client_sock, first_line):
    """Handle CONNECT method for HTTPS tunneling."""
    # Parse: CONNECT host:port HTTP/1.1
    parts = first_line.split()
    target = parts[1]
    host, port = target.split(":")
    port = int(port)

    # Connect to upstream proxy
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.connect((UPSTREAM_HOST, UPSTREAM_PORT))

    # Send CONNECT with auth to upstream
    connect_req = f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n{AUTH_HEADER}\r\n"
    upstream.sendall(connect_req.encode())

    # Read upstream response
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = upstream.recv(4096)
        if not chunk:
            break
        resp += chunk

    # Send 200 OK to client
    client_sock.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

    # Pipe data bidirectionally
    pipe(client_sock, upstream)

def handle_http(client_sock, first_line, headers):
    """Handle plain HTTP requests."""
    # Connect to upstream proxy
    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream.connect((UPSTREAM_HOST, UPSTREAM_PORT))

    # Forward request with auth
    upstream.sendall(first_line + b"\r\n" + headers + b"\r\n\r\n")

    # Pipe response
    while True:
        data = upstream.recv(65536)
        if not data:
            break
        client_sock.sendall(data)

    client_sock.close()
    upstream.close()

def handle_client(client_sock):
    try:
        data = client_sock.recv(8192)
        if not data:
            client_sock.close()
            return

        first_line = data.split(b"\r\n")[0]
        method = first_line.split(b" ")[0].decode().upper()

        if method == "CONNECT":
            handle_connect(client_sock, first_line)
        else:
            # HTTP — add auth and forward
            rest = data[len(first_line)+2:]  # after first \r\n
            auth_line = AUTH_HEADER.encode()
            handle_http(client_sock, first_line, rest.replace(b"\r\n\r\n", auth_line + b"\r\n\r\n", 1))
    except Exception as e:
        try: client_sock.close()
        except: pass

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", LOCAL_PORT))
    server.listen(50)
    print(f"[*] Proxy forwarder running on 127.0.0.1:{LOCAL_PORT}")
    print(f"[*] Upstream: {UPSTREAM_HOST}:{UPSTREAM_PORT}")
    print(f"[*] Set config.json proxy to: http://127.0.0.1:{LOCAL_PORT}")

    while True:
        client, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(client,), daemon=True)
        t.start()

if __name__ == "__main__":
    main()
