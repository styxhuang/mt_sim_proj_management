import argparse
import logging
import select
import socket
import socketserver
import threading


BUFFER_SIZE = 64 * 1024


class ProxyHandler(socketserver.BaseRequestHandler):
    remote_host = "127.0.0.1"
    remote_port = 0

    def handle(self) -> None:
        upstream = socket.create_connection((self.remote_host, self.remote_port))
        upstream.setblocking(False)
        self.request.setblocking(False)

        sockets = [self.request, upstream]
        try:
            while True:
                readable, _, exceptional = select.select(sockets, [], sockets, 1.0)
                if exceptional:
                    break

                for sock in readable:
                    try:
                        data = sock.recv(BUFFER_SIZE)
                    except OSError:
                        return

                    if not data:
                        return

                    target = upstream if sock is self.request else self.request
                    target.sendall(data)
        finally:
            try:
                upstream.close()
            except OSError:
                pass


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def build_server(listen_host: str, listen_port: int, remote_host: str, remote_port: int) -> ThreadedTCPServer:
    handler = type(
        "BoundProxyHandler",
        (ProxyHandler,),
        {"remote_host": remote_host, "remote_port": remote_port},
    )
    return ThreadedTCPServer((listen_host, listen_port), handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows localhost TCP proxy to WSL service")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--remote-host", required=True)
    parser.add_argument("--remote-port", type=int, required=True)
    parser.add_argument("--label", default="proxy")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.info(
        "%s listen=%s:%s remote=%s:%s",
        args.label,
        args.listen_host,
        args.listen_port,
        args.remote_host,
        args.remote_port,
    )

    server = build_server(args.listen_host, args.listen_port, args.remote_host, args.remote_port)
    with server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
