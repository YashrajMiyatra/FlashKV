"""
Lightweight embedded HTTP dashboard server.
Uses Python's standard library asyncio HTTP server - ZERO external dependencies required!
"""

import asyncio
import json
import mimetypes
import os
import time
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from ..server import FlashKVServer

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class WebDashboard:
    def __init__(self, server: "FlashKVServer", host: str = "0.0.0.0", port: int = 6380) -> None:
        self.server = server
        self.host = host
        self.port = port
        self._http_server: Optional[asyncio.AbstractServer] = None
        self._last_cmd_count = 0
        self._last_cmd_time = time.time()
        self.current_ops_sec = 0.0

    async def _handle_request(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            line = await reader.readline()
            if not line:
                writer.close()
                return

            request_line = line.decode("utf-8", errors="replace").strip()
            parts = request_line.split(" ")
            if len(parts) < 2:
                writer.close()
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers: Dict[str, str] = {}
            content_length = 0
            while True:
                header_line = await reader.readline()
                if not header_line or header_line == b"\r\n":
                    break
                header_str = header_line.decode("utf-8", errors="replace").strip()
                if ":" in header_str:
                    k, v = header_str.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
                    if k.strip().lower() == "content-length":
                        content_length = int(v.strip())

            body = b""
            if content_length > 0:
                body = await reader.readexactly(content_length)

            # Route request
            status_code, content_type, response_data = self._route(method, path, body)

            # Send response
            response_header = (
                f"HTTP/1.1 {status_code}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(response_data)}\r\n"
                f"Access-Control-Allow-Origin: *\r\n"
                f"Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
                f"Access-Control-Allow-Headers: Content-Type\r\n"
                f"Connection: close\r\n\r\n"
            ).encode("utf-8")

            writer.write(response_header)
            writer.write(response_data)
            await writer.drain()

        except Exception as e:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    def _route(self, method: str, path: str, body: bytes) -> Tuple[str, str, bytes]:
        if method == "OPTIONS":
            return "204 No Content", "text/plain", b""

        # API Endpoints
        if path == "/api/stats":
            now = time.time()
            elapsed = now - self._last_cmd_time
            if elapsed >= 0.5:
                curr_cmds = self.server.commands_processed
                self.current_ops_sec = round((curr_cmds - self._last_cmd_count) / elapsed, 1)
                self._last_cmd_count = curr_cmds
                self._last_cmd_time = now

            uptime = int(time.time() - self.server.start_time)
            stats = {
                "version": "1.0.0",
                "uptime": uptime,
                "connected_clients": len(self.server.connected_clients),
                "total_connections": self.server.total_connections,
                "total_commands": self.server.commands_processed,
                "ops_per_second": self.current_ops_sec,
                "dbsize": self.server.store.dbsize(),
                "keyspace_hits": self.server.store.stats["keyspace_hits"],
                "keyspace_misses": self.server.store.stats["keyspace_misses"],
                "expired_keys": self.server.store.stats["expired_keys"],
                "vector_indexes": len(self.server.vectors.indexes),
                "total_vectors": self.server.vectors.count(),
                "aof_enabled": self.server.aof.enabled,
            }
            return "200 OK", "application/json", json.dumps(stats).encode("utf-8")

        elif path == "/api/keys":
            keys = self.server.store.keys("*")
            items = []
            for k in keys[:200]:  # limit to 200 keys for ui performance
                k_type = self.server.store.get_type(k)
                ttl = self.server.store.ttl(k)
                preview = ""
                if k_type == "string":
                    preview = self.server.store.get(k) or ""
                    if len(preview) > 60:
                        preview = preview[:57] + "..."
                elif k_type == "list":
                    length = self.server.store.llen(k)
                    preview = f"List ({length} items)"
                elif k_type == "hash":
                    fields = list(self.server.store.hgetall(k).keys())
                    preview = f"Hash ({len(fields)} fields: {', '.join(fields[:3])})"
                elif k_type == "set":
                    count = self.server.store.scard(k)
                    preview = f"Set ({count} members)"

                items.append({
                    "key": k,
                    "type": k_type,
                    "ttl": ttl,
                    "preview": preview,
                })
            return "200 OK", "application/json", json.dumps({"keys": items}).encode("utf-8")

        elif path == "/api/vectors":
            indexes = []
            for idx in self.server.vectors.indexes.values():
                samples = []
                for vid in list(idx.vectors.keys())[:5]:
                    samples.append({
                        "id": vid,
                        "vector": idx.vectors[vid][:6],  # first 6 components preview
                        "metadata": idx.metadata.get(vid, {}),
                    })
                indexes.append({
                    "name": idx.name,
                    "dimension": idx.dimension,
                    "count": len(idx.vectors),
                    "samples": samples,
                })
            return "200 OK", "application/json", json.dumps({"indexes": indexes}).encode("utf-8")

        elif path == "/api/execute" and method == "POST":
            try:
                payload = json.loads(body.decode("utf-8"))
                cmd_str = payload.get("command", "").strip()
                if not cmd_str:
                    return "400 Bad Request", "application/json", json.dumps({"error": "No command provided"}).encode("utf-8")

                # Basic tokenization handling quotes
                parts = []
                current = ""
                in_quote = False
                quote_char = ""
                for char in cmd_str:
                    if char in ('"', "'") and not in_quote:
                        in_quote = True
                        quote_char = char
                    elif char == quote_char and in_quote:
                        in_quote = False
                    elif char.isspace() and not in_quote:
                        if current:
                            parts.append(current)
                            current = ""
                    else:
                        current += char
                if current:
                    parts.append(current)

                resp_bytes = self.server.execute_command(parts)
                # Decode RESP to human readable output
                readable = self._resp_to_readable(resp_bytes)
                return "200 OK", "application/json", json.dumps({"output": readable, "command": cmd_str}).encode("utf-8")
            except Exception as err:
                return "500 Internal Server Error", "application/json", json.dumps({"error": str(err)}).encode("utf-8")

        # Static Files
        clean_path = path.split("?")[0].lstrip("/")
        if not clean_path:
            clean_path = "index.html"

        file_path = os.path.join(STATIC_DIR, clean_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            with open(file_path, "rb") as f:
                return "200 OK", mime_type or "text/plain", f.read()

        return "404 Not Found", "text/plain", b"404 Not Found"

    def _resp_to_readable(self, data: bytes) -> str:
        """Helper to convert raw RESP bytes into clean text for web UI."""
        if not data:
            return ""
        prefix = chr(data[0])
        raw = data[1:].decode("utf-8", errors="replace").rstrip("\r\n")

        if prefix == "+":
            return f"OK: {raw}"
        elif prefix == "-":
            return f"Error: {raw}"
        elif prefix == ":":
            return f"(integer) {raw}"
        elif prefix == "$":
            parts = raw.split("\r\n", 1)
            length = int(parts[0])
            if length == -1:
                return "(nil)"
            return parts[1] if len(parts) > 1 else ""
        elif prefix == "*":
            # Nested parsing representation
            return f"Array response: {raw.replace('\r\n', ' ')}"
        return raw

    async def start(self) -> None:
        self._http_server = await asyncio.start_server(
            self._handle_request, self.host, self.port
        )
        print(f"[+] FlashKV Web Dashboard running at http://localhost:{self.port}")

    async def stop(self) -> None:
        if self._http_server:
            self._http_server.close()
            await self._http_server.wait_closed()
