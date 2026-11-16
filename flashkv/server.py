"""
FlashKV Async TCP Server.
Handles client connections, command routing, RESP responses, and metrics.
"""

import asyncio
import json
import os
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from .aof import AOFManager
from .protocol import (
    RESPReader,
    encode_array,
    encode_bulk_string,
    encode_error,
    encode_int,
    encode_simple_string,
    encode_value,
)
from .store import DataStore
from .vector import VectorManager

MUTATING_COMMANDS = {
    "SET", "DEL", "EXPIRE", "PEXPIRE", "PERSIST", "INCR", "DECR", "INCRBY", "DECRBY",
    "MSET", "FLUSHDB", "LPUSH", "RPUSH", "LPOP", "RPOP", "HSET", "HDEL", "SADD", "SREM",
    "VADD", "VDEL"
}


class FlashKVServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 6379,
        aof_path: str = "flashkv.aof",
        enable_aof: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.store = DataStore()
        self.vectors = VectorManager()
        self.aof = AOFManager(filepath=aof_path, enabled=enable_aof)

        self.start_time = time.time()
        self.connected_clients: Set[asyncio.StreamWriter] = set()
        self.total_connections = 0
        self.commands_processed = 0
        self._running = False
        self._server: Optional[asyncio.AbstractServer] = None
        self._cleanup_task: Optional[asyncio.Task] = None

    def dump_state_for_aof(self) -> List[List[str]]:
        """Dumps entire current database state into a list of replayable commands."""
        commands: List[List[str]] = []
        now = time.time()

        for key, entry in self.store._data.items():
            if entry.is_expired(now):
                continue
            if entry.data_type == "string":
                cmd = ["SET", key, str(entry.value)]
                if entry.expires_at:
                    ttl_sec = max(int(entry.expires_at - now), 1)
                    cmd.extend(["EX", str(ttl_sec)])
                commands.append(cmd)
            elif entry.data_type == "list":
                for val in entry.value:
                    commands.append(["RPUSH", key, str(val)])
            elif entry.data_type == "hash":
                for f, v in entry.value.items():
                    commands.append(["HSET", key, str(f), str(v)])
            elif entry.data_type == "set":
                for m in entry.value:
                    commands.append(["SADD", key, str(m)])

        # Dump vectors
        for idx in self.vectors.indexes.values():
            for vid, vec in idx.vectors.items():
                vec_str = ",".join(str(x) for x in vec)
                cmd = ["VADD", idx.name, vid, vec_str]
                meta = idx.metadata.get(vid)
                if meta:
                    cmd.append(json.dumps(meta))
                commands.append(cmd)

        return commands

    def replay_startup(self) -> None:
        """Replay AOF log on startup."""
        if self.aof.enabled:
            replayed = self.aof.replay(self.execute_command)
            if replayed > 0:
                print(f"[*] Replayed {replayed} commands from AOF log.")

    def execute_command(self, parts: List[str]) -> bytes:
        """Executes a single parsed command array and returns the encoded RESP response."""
        if not parts:
            return encode_error("empty command")

        cmd = parts[0].upper()
        args = parts[1:]
        self.commands_processed += 1
        self.store.stats["total_commands"] += 1

        try:
            # ---------------- Basic / Server ---------------- #
            if cmd == "PING":
                if args:
                    return encode_bulk_string(" ".join(args))
                return encode_simple_string("PONG")

            elif cmd == "ECHO":
                if not args:
                    return encode_error("wrong number of arguments for 'echo' command")
                return encode_bulk_string(" ".join(args))

            elif cmd == "COMMAND":
                # redis-cli runs COMMAND on connect
                return encode_array([])

            elif cmd == "INFO":
                uptime = int(time.time() - self.start_time)
                info_lines = [
                    "# Server",
                    "flashkv_version:1.0.0",
                    f"uptime_in_seconds:{uptime}",
                    f"connected_clients:{len(self.connected_clients)}",
                    f"total_connections_received:{self.total_connections}",
                    f"total_commands_processed:{self.commands_processed}",
                    "# Keyspace",
                    f"db0:keys={self.store.dbsize()},expires={len([e for e in self.store._data.values() if e.expires_at])}",
                    f"keyspace_hits:{self.store.stats['keyspace_hits']}",
                    f"keyspace_misses:{self.store.stats['keyspace_misses']}",
                    f"expired_keys:{self.store.stats['expired_keys']}",
                    "# Vectors",
                    f"vector_indexes:{len(self.vectors.indexes)}",
                    f"total_vectors:{self.vectors.count()}",
                    "# Persistence",
                    f"aof_enabled:{1 if self.aof.enabled else 0}",
                ]
                return encode_bulk_string("\r\n".join(info_lines) + "\r\n")

            # ---------------- Key / TTL ---------------- #
            elif cmd == "GET":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'get' command")
                val = self.store.get(args[0])
                return encode_bulk_string(val)

            elif cmd == "SET":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'set' command")
                key, val = args[0], args[1]
                ex, px, nx, xx = None, None, False, False
                i = 2
                while i < len(args):
                    opt = args[i].upper()
                    if opt == "EX" and i + 1 < len(args):
                        ex = float(args[i + 1])
                        i += 2
                    elif opt == "PX" and i + 1 < len(args):
                        px = float(args[i + 1])
                        i += 2
                    elif opt == "NX":
                        nx = True
                        i += 1
                    elif opt == "XX":
                        xx = True
                        i += 1
                    else:
                        i += 1
                ok = self.store.set(key, val, ex=ex, px=px, nx=nx, xx=xx)
                if not ok:
                    return encode_bulk_string(None)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_simple_string("OK")

            elif cmd == "DEL":
                if not args:
                    return encode_error("wrong number of arguments for 'del' command")
                count = self.store.delete(*args)
                if count > 0 and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(count)

            elif cmd == "EXISTS":
                if not args:
                    return encode_error("wrong number of arguments for 'exists' command")
                return encode_int(self.store.exists(*args))

            elif cmd == "EXPIRE":
                if len(args) != 2:
                    return encode_error("wrong number of arguments for 'expire' command")
                ok = self.store.expire(args[0], float(args[1]))
                if ok and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(1 if ok else 0)

            elif cmd == "PEXPIRE":
                if len(args) != 2:
                    return encode_error("wrong number of arguments for 'pexpire' command")
                ok = self.store.expire(args[0], float(args[1]) / 1000.0)
                if ok and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(1 if ok else 0)

            elif cmd == "TTL":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'ttl' command")
                return encode_int(self.store.ttl(args[0]))

            elif cmd == "PTTL":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'pttl' command")
                return encode_int(self.store.pttl(args[0]))

            elif cmd == "PERSIST":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'persist' command")
                ok = self.store.persist(args[0])
                if ok and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(1 if ok else 0)

            elif cmd == "TYPE":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'type' command")
                return encode_simple_string(self.store.get_type(args[0]))

            elif cmd == "KEYS":
                pattern = args[0] if args else "*"
                matched = self.store.keys(pattern)
                return encode_array(matched)

            elif cmd == "DBSIZE":
                return encode_int(self.store.dbsize())

            elif cmd == "FLUSHDB":
                self.store.flushdb()
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_simple_string("OK")

            elif cmd in ("INCR", "DECR"):
                if len(args) != 1:
                    return encode_error(f"wrong number of arguments for '{cmd.lower()}' command")
                delta = 1 if cmd == "INCR" else -1
                val = self.store.incrby(args[0], delta)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(val)

            elif cmd in ("INCRBY", "DECRBY"):
                if len(args) != 2:
                    return encode_error(f"wrong number of arguments for '{cmd.lower()}' command")
                delta = int(args[1]) * (1 if cmd == "INCRBY" else -1)
                val = self.store.incrby(args[0], delta)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(val)

            elif cmd == "MGET":
                if not args:
                    return encode_error("wrong number of arguments for 'mget' command")
                return encode_array(self.store.mget(*args))

            elif cmd == "MSET":
                if len(args) < 2 or len(args) % 2 != 0:
                    return encode_error("wrong number of arguments for 'mset' command")
                mapping = {args[i]: args[i + 1] for i in range(0, len(args), 2)}
                self.store.mset(mapping)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_simple_string("OK")

            # ---------------- Lists ---------------- #
            elif cmd == "LPUSH":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'lpush' command")
                length = self.store.lpush(args[0], *args[1:])
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(length)

            elif cmd == "RPUSH":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'rpush' command")
                length = self.store.rpush(args[0], *args[1:])
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(length)

            elif cmd == "LPOP":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'lpop' command")
                item = self.store.lpop(args[0])
                if item is not None and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_bulk_string(item)

            elif cmd == "RPOP":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'rpop' command")
                item = self.store.rpop(args[0])
                if item is not None and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_bulk_string(item)

            elif cmd == "LLEN":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'llen' command")
                return encode_int(self.store.llen(args[0]))

            elif cmd == "LRANGE":
                if len(args) != 3:
                    return encode_error("wrong number of arguments for 'lrange' command")
                items = self.store.lrange(args[0], int(args[1]), int(args[2]))
                return encode_array(items)

            # ---------------- Hashes ---------------- #
            elif cmd == "HSET":
                if len(args) < 3:
                    return encode_error("wrong number of arguments for 'hset' command")
                key = args[0]
                pairs = args[1:]
                if len(pairs) % 2 != 0:
                    return encode_error("wrong number of arguments for 'hset' command")
                mapping = {pairs[i]: pairs[i + 1] for i in range(0, len(pairs), 2)}
                count = self.store.hset(key, mapping)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(count)

            elif cmd == "HGET":
                if len(args) != 2:
                    return encode_error("wrong number of arguments for 'hget' command")
                return encode_bulk_string(self.store.hget(args[0], args[1]))

            elif cmd == "HGETALL":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'hgetall' command")
                return encode_value(self.store.hgetall(args[0]))

            elif cmd == "HDEL":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'hdel' command")
                count = self.store.hdel(args[0], *args[1:])
                if count > 0 and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(count)

            # ---------------- Sets ---------------- #
            elif cmd == "SADD":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'sadd' command")
                count = self.store.sadd(args[0], *args[1:])
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(count)

            elif cmd == "SMEMBERS":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'smembers' command")
                return encode_array(self.store.smembers(args[0]))

            elif cmd == "SREM":
                if len(args) < 2:
                    return encode_error("wrong number of arguments for 'srem' command")
                count = self.store.srem(args[0], *args[1:])
                if count > 0 and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(count)

            elif cmd == "SCARD":
                if len(args) != 1:
                    return encode_error("wrong number of arguments for 'scard' command")
                return encode_int(self.store.scard(args[0]))

            elif cmd == "SISMEMBER":
                if len(args) != 2:
                    return encode_error("wrong number of arguments for 'sismember' command")
                return encode_int(self.store.sismember(args[0], args[1]))

            # ---------------- Vector Engine ---------------- #
            elif cmd == "VADD":
                # VADD <index> <id> <dim1,dim2,...> [metadata_json]
                if len(args) < 3:
                    return encode_error("Usage: VADD <index> <id> <v1,v2,v3,...> [metadata_json]")
                index_name, vid, vec_raw = args[0], args[1], args[2]
                try:
                    vector = [float(x.strip()) for x in vec_raw.split(",")]
                except ValueError:
                    return encode_error("invalid vector components; expected comma-separated floats")

                meta = None
                if len(args) >= 4:
                    try:
                        meta = json.loads(" ".join(args[3:]))
                    except json.JSONDecodeError:
                        return encode_error("invalid JSON metadata")

                idx = self.vectors.get_or_create(index_name, dimension=len(vector))
                idx.add(vid, vector, meta)
                if self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_simple_string("OK")

            elif cmd == "VSEARCH":
                # VSEARCH <index> <query_v1,query_v2,...> [top_k=10] [metric=cosine|euclidean]
                if len(args) < 2:
                    return encode_error("Usage: VSEARCH <index> <q1,q2,...> [k=10] [metric=cosine|euclidean]")
                index_name, vec_raw = args[0], args[1]
                top_k = int(args[2]) if len(args) >= 3 else 10
                metric = args[3] if len(args) >= 4 else "cosine"

                idx = self.vectors.get(index_name)
                if idx is None:
                    return encode_array([])

                try:
                    query = [float(x.strip()) for x in vec_raw.split(",")]
                except ValueError:
                    return encode_error("invalid query vector; expected comma-separated floats")

                matches = idx.search(query, top_k=top_k, metric=metric)
                # Format as array of nested arrays: [[id, score, meta_json], ...]
                resp_list = []
                for m in matches:
                    resp_list.append([m["id"], str(m["score"]), json.dumps(m["metadata"])])
                return encode_array(resp_list)

            elif cmd == "VDEL":
                if len(args) != 2:
                    return encode_error("Usage: VDEL <index> <id>")
                idx = self.vectors.get(args[0])
                if not idx:
                    return encode_int(0)
                ok = idx.delete(args[1])
                if ok and self.aof.enabled:
                    self.aof.append_command(parts)
                return encode_int(1 if ok else 0)

            elif cmd == "VINFO":
                if len(args) != 1:
                    return encode_error("Usage: VINFO <index>")
                idx = self.vectors.get(args[0])
                if not idx:
                    return encode_bulk_string(None)
                return encode_bulk_string(json.dumps(idx.info()))

            elif cmd == "VLIST":
                return encode_bulk_string(json.dumps(self.vectors.list_indexes()))

            # ---------------- AOF Management ---------------- #
            elif cmd == "BGREWRITEAOF":
                success = self.aof.rewrite(self.dump_state_for_aof)
                if success:
                    return encode_simple_string("Background append only file rewriting started")
                return encode_error("AOF persistence is disabled")

            else:
                return encode_error(f"unknown command `{cmd}`")

        except (ValueError, TypeError) as e:
            return encode_error(str(e))
        except Exception as e:
            return encode_error(f"internal server error: {str(e)}")

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self.connected_clients.add(writer)
        self.total_connections += 1
        resp_reader = RESPReader()

        try:
            while self._running:
                data = await reader.read(4096)
                if not data:
                    break

                resp_reader.feed(data)
                while True:
                    ok, command = resp_reader.read_one()
                    if not ok:
                        break

                    if isinstance(command, list):
                        cmd_parts = [str(x) for x in command]
                    elif isinstance(command, str):
                        cmd_parts = [command]
                    else:
                        continue

                    response = self.execute_command(cmd_parts)
                    writer.write(response)
                    await writer.drain()

        except (asyncio.IncompleteReadError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self.connected_clients.discard(writer)
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _active_expire_loop(self) -> None:
        """Periodic background task to prune expired keys."""
        while self._running:
            try:
                await asyncio.sleep(1.0)
                self.store.purge_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def start(self) -> None:
        self._running = True
        self.replay_startup()
        self._server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        self._cleanup_task = asyncio.create_task(self._active_expire_loop())
        addr = self._server.sockets[0].getsockname()
        print(f"[+] FlashKV Redis Engine listening on {addr[0]}:{addr[1]}")

    async def stop(self) -> None:
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
        for writer in list(self.connected_clients):
            try:
                writer.close()
            except Exception:
                pass
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        self.aof.close()
        print("[*] FlashKV Engine stopped.")
