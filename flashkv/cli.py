"""
Interactive FlashKV CLI Client.
Allows connecting to any FlashKV / Redis server directly from the terminal without redis-cli!
"""

import socket
import sys
from typing import List
from .protocol import encode_array, RESPReader


class FlashKVClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6379) -> None:
        self.host = host
        self.port = port
        self.sock: socket.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.reader = RESPReader()

    def connect(self) -> None:
        self.sock.connect((self.host, self.port))

    def send_command(self, cmd_parts: List[str]) -> str:
        encoded = encode_array(cmd_parts)
        self.sock.sendall(encoded)

        while True:
            data = self.sock.recv(4096)
            if not data:
                return "Connection lost."
            self.reader.feed(data)
            ok, val = self.reader.read_one()
            if ok:
                return self._format_result(val)

    def _format_result(self, val: any, indent: int = 0) -> str:
        if val is None:
            return "(nil)"
        elif isinstance(val, bool):
            return "(integer) 1" if val else "(integer) 0"
        elif isinstance(val, int):
            return f"(integer) {val}"
        elif isinstance(val, Exception):
            return f"(error) {str(val)}"
        elif isinstance(val, str):
            return f'"{val}"'
        elif isinstance(val, list):
            if not val:
                return "(empty list or set)"
            lines = []
            prefix = " " * indent
            for idx, item in enumerate(val, 1):
                if isinstance(item, list):
                    lines.append(f"{prefix}{idx}) {self._format_result(item, indent + 3)}")
                else:
                    lines.append(f"{prefix}{idx}) {self._format_result(item)}")
            return "\n".join(lines)
        return str(val)

    def close(self) -> None:
        try:
            self.sock.close()
        except Exception:
            pass


def main() -> None:
    host = "127.0.0.1"
    port = 6379
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        port = int(sys.argv[2])

    client = FlashKVClient(host, port)
    try:
        client.connect()
    except ConnectionRefusedError:
        print(f"Error: Could not connect to FlashKV at {host}:{port}. Is the server running?")
        sys.exit(1)

    print(f"\033[1;36mFlashKV CLI (v1.0.0)\033[0m")
    print(f"Connected to \033[1;32m{host}:{port}\033[0m. Type 'help' or 'quit' to exit.\n")

    while True:
        try:
            line = input(f"\033[1;32m{host}:{port}>\033[0m ").strip()
            if not line:
                continue
            if line.lower() in ("exit", "quit"):
                break
            if line.lower() == "help":
                print("Available commands: PING, SET, GET, DEL, KEYS, EXPIRE, TTL, INCR, LPUSH, LRANGE, HSET, HGETALL, VADD, VSEARCH, VLIST, INFO")
                continue

            # Split command line respecting quotes
            parts = []
            curr = ""
            in_q = False
            q_char = ""
            for c in line:
                if c in ('"', "'") and not in_q:
                    in_q = True
                    q_char = c
                elif c == q_char and in_q:
                    in_q = False
                elif c.isspace() and not in_q:
                    if curr:
                        parts.append(curr)
                        curr = ""
                else:
                    curr += c
            if curr:
                parts.append(curr)

            res = client.send_command(parts)
            print(res)
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break
        except Exception as e:
            print(f"(error) {e}")

    client.close()


if __name__ == "__main__":
    main()
