"""
In-memory data store supporting Strings, Lists, Hashes, Sets, and Key Expiration (TTL).
"""

import fnmatch
import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class StoreEntry:
    __slots__ = ("value", "data_type", "expires_at", "last_accessed")

    def __init__(
        self,
        value: Any,
        data_type: str,
        expires_at: Optional[float] = None,
    ) -> None:
        self.value = value
        self.data_type = data_type  # 'string', 'list', 'hash', 'set'
        self.expires_at = expires_at
        self.last_accessed = time.time()

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        if now is None:
            now = time.time()
        return now >= self.expires_at


class DataStore:
    """Thread-safe and async-compatible in-memory store with optional LRU eviction."""

    def __init__(self, max_keys: Optional[int] = None) -> None:
        self._data: Dict[str, StoreEntry] = {}
        self.max_keys = max_keys
        self.stats: Dict[str, int] = {
            "total_commands": 0,
            "keyspace_hits": 0,
            "keyspace_misses": 0,
            "expired_keys": 0,
            "evicted_keys": 0,
        }
        self.created_at = time.time()

    def _maybe_evict(self, new_key: str) -> None:
        """Evicts the least recently accessed key if max_keys capacity is reached."""
        if self.max_keys is None or self.max_keys <= 0:
            return
        if new_key in self._data:
            return
        if len(self._data) >= self.max_keys:
            now = time.time()
            for k in list(self._data.keys()):
                if self._data[k].is_expired(now):
                    del self._data[k]
                    self.stats["expired_keys"] += 1

            if len(self._data) >= self.max_keys:
                lru_key = min(self._data.keys(), key=lambda k: self._data[k].last_accessed)
                del self._data[lru_key]
                self.stats["evicted_keys"] += 1

    def _get_entry(self, key: str) -> Optional[StoreEntry]:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._data[key]
            self.stats["expired_keys"] += 1
            return None
        entry.last_accessed = time.time()
        return entry

    def get_eviction_stats(self) -> Dict[str, Any]:
        """Returns capacity and LRU eviction metrics."""
        return {
            "max_keys": self.max_keys,
            "current_keys": len(self._data),
            "evicted_keys": self.stats["evicted_keys"],
        }

    # ------------------ Key & TTL Management ------------------ #

    def exists(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if self._get_entry(k) is not None:
                count += 1
        return count

    def touch(self, *keys: str) -> int:
        """Alters the last access time of a key(s). A key is ignored if it does not exist."""
        touched = 0
        for k in keys:
            if self._get_entry(k) is not None:
                touched += 1
        return touched

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
        return count

    def unlink(self, *keys: str) -> int:
        """Removes the specified keys asynchronously / non-blocking (Redis UNLINK semantics)."""
        return self.delete(*keys)

    def rename(self, key: str, newkey: str) -> bool:
        """Renames key to newkey. Returns True, or raises KeyError if key does not exist."""
        if key == newkey:
            if self._get_entry(key) is None:
                raise KeyError("no such key")
            return True
        entry = self._get_entry(key)
        if entry is None:
            raise KeyError("no such key")
        del self._data[key]
        self._data[newkey] = entry
        return True

    def renamenx(self, key: str, newkey: str) -> int:
        """Renames key to newkey only if newkey does not exist. Returns 1 if renamed, 0 if newkey exists."""
        if key == newkey:
            if self._get_entry(key) is None:
                raise KeyError("no such key")
            return 0
        entry = self._get_entry(key)
        if entry is None:
            raise KeyError("no such key")
        dest_entry = self._get_entry(newkey)
        if dest_entry is not None:
            return 0
        del self._data[key]
        self._data[newkey] = entry
        return 1

    def randomkey(self) -> Optional[str]:
        """Returns a random non-expired key from the store, or None if empty."""
        active_keys = [k for k in list(self._data.keys()) if self._get_entry(k) is not None]
        if not active_keys:
            return None
        import random
        return random.choice(active_keys)

    def expire(self, key: str, seconds: float) -> bool:
        entry = self._get_entry(key)
        if entry is None:
            return False
        entry.expires_at = time.time() + seconds
        return True

    def ttl(self, key: str) -> int:
        """Returns TTL in seconds. -2 if key does not exist, -1 if no TTL."""
        entry = self._get_entry(key)
        if entry is None:
            return -2
        if entry.expires_at is None:
            return -1
        remaining = int(entry.expires_at - time.time())
        return max(remaining, 0)

    def pttl(self, key: str) -> int:
        """Returns TTL in milliseconds. -2 if key does not exist, -1 if no TTL."""
        entry = self._get_entry(key)
        if entry is None:
            return -2
        if entry.expires_at is None:
            return -1
        remaining_ms = int((entry.expires_at - time.time()) * 1000)
        return max(remaining_ms, 0)

    def persist(self, key: str) -> bool:
        entry = self._get_entry(key)
        if entry is None or entry.expires_at is None:
            return False
        entry.expires_at = None
        return True

    def get_type(self, key: str) -> str:
        entry = self._get_entry(key)
        if entry is None:
            return "none"
        return entry.data_type

    def keys(self, pattern: str = "*") -> List[str]:
        now = time.time()
        result = []
        expired = []
        for k, entry in self._data.items():
            if entry.is_expired(now):
                expired.append(k)
            elif fnmatch.fnmatch(k, pattern):
                result.append(k)
        for k in expired:
            del self._data[k]
            self.stats["expired_keys"] += 1
        return sorted(result)

    def dbsize(self) -> int:
        return len(self.keys("*"))

    def flushdb(self) -> None:
        self._data.clear()

    def scan(self, cursor: int = 0, pattern: str = "*", count: int = 10) -> Tuple[int, List[str]]:
        """
        Cursor-based incremental iteration over the key space.
        Returns (next_cursor, matched_keys). A next_cursor of 0 indicates the scan is complete.
        """
        all_keys = self.keys(pattern)
        if cursor >= len(all_keys):
            return 0, []
        matched = all_keys[cursor : cursor + count]
        next_cursor = cursor + count
        if next_cursor >= len(all_keys):
            next_cursor = 0
        return next_cursor, matched

    def purge_expired(self, sample_size: int = 100) -> int:
        """Active expiration sweep (Redis-style sampling)."""
        now = time.time()
        purged = 0
        keys_to_check = list(self._data.keys())[:sample_size]
        for k in keys_to_check:
            entry = self._data.get(k)
            if entry and entry.is_expired(now):
                del self._data[k]
                purged += 1
        self.stats["expired_keys"] += purged
        return purged

    def dump_snapshot(self, filepath: str) -> int:
        """
        Atomically dumps all unexpired keys, values, and remaining TTLs to a JSON snapshot.
        Returns the number of keys saved.
        """
        now = time.time()
        snapshot_data = {}
        for k, entry in list(self._data.items()):
            if entry.is_expired(now):
                continue
            # Serialize value according to type
            val = entry.value
            if entry.data_type == "set":
                val = list(val)
            remaining_ttl = None
            if entry.expires_at is not None:
                remaining_ttl = max(0.0, entry.expires_at - now)

            snapshot_data[k] = {
                "type": entry.data_type,
                "value": val,
                "ttl": remaining_ttl,
            }

        dir_name = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(dir_name, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False) as tf:
            json.dump(snapshot_data, tf, indent=2)
            temp_path = tf.name

        os.replace(temp_path, filepath)
        return len(snapshot_data)

    def load_snapshot(self, filepath: str) -> int:
        """
        Loads keys, data types, and remaining TTLs from a snapshot file into memory.
        Returns the number of keys restored.
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Snapshot file not found: {filepath}")

        with open(filepath, "r") as f:
            snapshot_data = json.load(f)

        now = time.time()
        restored = 0
        for k, item in snapshot_data.items():
            dtype = item["type"]
            val = item["value"]
            if dtype == "set":
                val = set(val)

            expires_at = None
            if item.get("ttl") is not None:
                expires_at = now + float(item["ttl"])

            self._data[k] = StoreEntry(val, dtype, expires_at)
            restored += 1

        return restored

    # ------------------ Strings ------------------ #

    def set(
        self,
        key: str,
        value: str,
        ex: Optional[float] = None,
        px: Optional[float] = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        existing = self._get_entry(key)
        if nx and existing is not None:
            return False
        if xx and existing is None:
            return False

        expires_at = None
        if ex is not None:
            expires_at = time.time() + ex
        elif px is not None:
            expires_at = time.time() + (px / 1000.0)

        self._maybe_evict(key)
        self._data[key] = StoreEntry(str(value), "string", expires_at)
        return True

    def get(self, key: str) -> Optional[str]:
        entry = self._get_entry(key)
        if entry is None:
            self.stats["keyspace_misses"] += 1
            return None
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        self.stats["keyspace_hits"] += 1
        return str(entry.value)

    def incrby(self, key: str, amount: int = 1) -> int:
        entry = self._get_entry(key)
        if entry is None:
            self.set(key, str(amount))
            return amount
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        try:
            val = int(entry.value) + amount
        except ValueError:
            raise ValueError("value is not an integer or out of range")
        entry.value = str(val)
        return val

    def decrby(self, key: str, amount: int = 1) -> int:
        return self.incrby(key, -amount)

    def decr(self, key: str) -> int:
        return self.decrby(key, 1)

    def incrbyfloat(self, key: str, amount: float) -> float:
        entry = self._get_entry(key)
        if entry is None:
            self.set(key, str(amount))
            return float(amount)
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        try:
            val = float(entry.value) + float(amount)
        except ValueError:
            raise ValueError("value is not a valid float")
        entry.value = str(val)
        return val

    def mget(self, *keys: str) -> List[Optional[str]]:
        results = []
        for k in keys:
            entry = self._get_entry(k)
            if entry and entry.data_type == "string":
                results.append(str(entry.value))
                self.stats["keyspace_hits"] += 1
            else:
                results.append(None)
                self.stats["keyspace_misses"] += 1
        return results

    def mset(self, mapping: Dict[str, str]) -> None:
        for k, v in mapping.items():
            self.set(k, v)

    def msetnx(self, mapping: Dict[str, str]) -> int:
        if not mapping:
            return 1
        for k in mapping.keys():
            if self._get_entry(k) is not None:
                return 0
        for k, v in mapping.items():
            self.set(k, v)
        return 1

    def strlen(self, key: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        return len(str(entry.value))

    def setrange(self, key: str, offset: int, value: str) -> int:
        if offset < 0:
            raise ValueError("offset is out of range, must be non-negative")
        entry = self._get_entry(key)
        if entry is None:
            cur = ""
        else:
            if entry.data_type != "string":
                raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            cur = str(entry.value)

        if offset > len(cur):
            cur = cur.ljust(offset, "\x00")

        new_val = cur[:offset] + value + cur[offset + len(value):]
        self.set(key, new_val)
        return len(new_val)

    def getrange(self, key: str, start: int, end: int) -> str:
        entry = self._get_entry(key)
        if entry is None:
            return ""
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        s = str(entry.value)
        n = len(s)
        if n == 0:
            return ""

        if start < 0:
            start = max(0, n + start)
        if end < 0:
            end = n + end

        if start > end or start >= n:
            return ""

        end = min(end, n - 1)
        return s[start : end + 1]

    def setbit(self, key: str, offset: int, value: int) -> int:
        """
        Sets or clears the bit at offset in the string value stored at key.
        Returns the original bit value stored at offset (0 or 1).
        """
        if offset < 0:
            raise ValueError("bit offset is out of range, must be non-negative")
        if value not in (0, 1):
            raise ValueError("bit is not the integer 0 or 1")

        entry = self._get_entry(key)
        if entry is None:
            raw = bytearray()
        else:
            if entry.data_type != "string":
                raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            raw = bytearray(str(entry.value).encode("latin-1"))

        byte_idx = offset // 8
        bit_idx = 7 - (offset % 8)

        if byte_idx >= len(raw):
            raw.extend(b"\x00" * (byte_idx + 1 - len(raw)))
            old_bit = 0
        else:
            old_bit = (raw[byte_idx] >> bit_idx) & 1

        if value == 1:
            raw[byte_idx] |= (1 << bit_idx)
        else:
            raw[byte_idx] &= ~(1 << bit_idx)

        self.set(key, raw.decode("latin-1"))
        return old_bit

    def getbit(self, key: str, offset: int) -> int:
        """
        Returns the bit value at offset in the string value stored at key.
        """
        if offset < 0:
            raise ValueError("bit offset is out of range, must be non-negative")

        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")

        raw = str(entry.value).encode("latin-1")
        byte_idx = offset // 8
        bit_idx = 7 - (offset % 8)

        if byte_idx >= len(raw):
            return 0
        return (raw[byte_idx] >> bit_idx) & 1

    def bitcount(self, key: str, start: Optional[int] = None, end: Optional[int] = None) -> int:
        """
        Counts the number of set bits (population count) in a string.
        Optional byte range [start, end] supports negative indices.
        """
        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "string":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")

        raw = str(entry.value).encode("latin-1")
        n = len(raw)
        if n == 0:
            return 0

        if start is not None and end is not None:
            if start < 0:
                start = max(0, n + start)
            if end < 0:
                end = n + end
            if start > end or start >= n:
                return 0
            end = min(end, n - 1)
            raw = raw[start : end + 1]

        return sum(bin(b).count("1") for b in raw)

    # ------------------ Lists ------------------ #

    def lpush(self, key: str, *values: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            self._maybe_evict(key)
            lst = list(reversed(values))
            self._data[key] = StoreEntry(lst, "list")
            return len(lst)
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        for val in values:
            entry.value.insert(0, val)
        return len(entry.value)

    def rpush(self, key: str, *values: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            self._maybe_evict(key)
            lst = list(values)
            self._data[key] = StoreEntry(lst, "list")
            return len(lst)
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        entry.value.extend(values)
        return len(entry.value)

    def lpop(self, key: str) -> Optional[str]:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "list" or not entry.value:
            return None
        return entry.value.pop(0)

    def rpop(self, key: str) -> Optional[str]:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "list" or not entry.value:
            return None
        return entry.value.pop()

    def llen(self, key: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        return len(entry.value)

    def lrange(self, key: str, start: int, stop: int) -> List[str]:
        entry = self._get_entry(key)
        if entry is None:
            return []
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        lst = entry.value
        length = len(lst)
        if start < 0:
            start = max(length + start, 0)
        if stop < 0:
            stop = length + stop
        return lst[start : stop + 1]

    def lpushx(self, key: str, *values: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        for v in values:
            entry.value.insert(0, str(v))
        return len(entry.value)

    def rpushx(self, key: str, *values: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            return 0
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        for v in values:
            entry.value.append(str(v))
        return len(entry.value)

    def lindex(self, key: str, index: int) -> Optional[str]:
        entry = self._get_entry(key)
        if entry is None:
            return None
        if entry.data_type != "list":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        lst = entry.value
        length = len(lst)
        if index < 0:
            index = length + index
        if 0 <= index < length:
            return lst[index]
        return None

    # ------------------ Hashes ------------------ #

    def hset(self, key: str, mapping: Dict[str, str]) -> int:
        entry = self._get_entry(key)
        added = 0
        if entry is None:
            self._maybe_evict(key)
            self._data[key] = StoreEntry(dict(mapping), "hash")
            return len(mapping)
        if entry.data_type != "hash":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        for f, v in mapping.items():
            if f not in entry.value:
                added += 1
            entry.value[f] = v
        return added

    def hget(self, key: str, field: str) -> Optional[str]:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return None
        return entry.value.get(field)

    def hgetall(self, key: str) -> Dict[str, str]:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return {}
        return dict(entry.value)

    def hdel(self, key: str, *fields: str) -> int:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return 0
        deleted = 0
        for f in fields:
            if f in entry.value:
                del entry.value[f]
                deleted += 1
        return deleted

    def hexists(self, key: str, field: str) -> bool:
        """Determines whether a hash field exists."""
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return False
        return field in entry.value

    def hlen(self, key: str) -> int:
        """Returns the number of fields contained in the hash."""
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return 0
        return len(entry.value)

    def hkeys(self, key: str) -> List[str]:
        """Returns all field names in the hash."""
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return []
        return sorted(list(entry.value.keys()))

    def hvals(self, key: str) -> List[str]:
        """Returns all values in the hash."""
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "hash":
            return []
        return list(entry.value.values())

    def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """Increments the integer value of a hash field by the given number."""
        entry = self._get_entry(key)
        if entry is None:
            self._maybe_evict(key)
            self._data[key] = StoreEntry({field: str(amount)}, "hash")
            return amount
        if entry.data_type != "hash":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        current_str = entry.value.get(field, "0")
        try:
            val = int(current_str) + int(amount)
        except ValueError:
            raise ValueError("hash value is not an integer")
        entry.value[field] = str(val)
        return val

    def hincrbyfloat(self, key: str, field: str, amount: float) -> float:
        """Increments the float value of a hash field by the given number."""
        entry = self._get_entry(key)
        if entry is None:
            self._maybe_evict(key)
            self._data[key] = StoreEntry({field: str(amount)}, "hash")
            return float(amount)
        if entry.data_type != "hash":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        current_str = entry.value.get(field, "0")
        try:
            val = float(current_str) + float(amount)
        except ValueError:
            raise ValueError("hash value is not a valid float")
        entry.value[field] = str(val)
        return val

    # ------------------ Sets ------------------ #

    def sadd(self, key: str, *members: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
            self._maybe_evict(key)
            unique_members = set(members)
            self._data[key] = StoreEntry(unique_members, "set")
            return len(unique_members)
        if entry.data_type != "set":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        added = 0
        for m in members:
            if m not in entry.value:
                entry.value.add(m)
                added += 1
        return added

    def smembers(self, key: str) -> List[str]:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "set":
            return []
        return sorted(list(entry.value))

    def srem(self, key: str, *members: str) -> int:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "set":
            return 0
        removed = 0
        for m in members:
            if m in entry.value:
                entry.value.remove(m)
                removed += 1
        return removed

    def scard(self, key: str) -> int:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "set":
            return 0
        return len(entry.value)

    def sismember(self, key: str, member: str) -> int:
        entry = self._get_entry(key)
        if entry is None or entry.data_type != "set":
            return 0
        return 1 if member in entry.value else 0

    def sinter(self, *keys: str) -> List[str]:
        if not keys:
            return []
        sets = []
        for key in keys:
            entry = self._get_entry(key)
            if entry is None:
                return []
            if entry.data_type != "set":
                raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            sets.append(entry.value)
        res = set.intersection(*sets)
        return sorted(list(res))

    def sunion(self, *keys: str) -> List[str]:
        res: set = set()
        for key in keys:
            entry = self._get_entry(key)
            if entry is None:
                continue
            if entry.data_type != "set":
                raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            res.update(entry.value)
        return sorted(list(res))

    def sdiff(self, *keys: str) -> List[str]:
        if not keys:
            return []
        first_entry = self._get_entry(keys[0])
        if first_entry is None:
            return []
        if first_entry.data_type != "set":
            raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
        res = set(first_entry.value)
        for key in keys[1:]:
            entry = self._get_entry(key)
            if entry is None:
                continue
            if entry.data_type != "set":
                raise TypeError("WRONGTYPE Operation against a key holding the wrong kind of value")
            res.difference_update(entry.value)
        return sorted(list(res))

    def sinterstore(self, destination: str, *keys: str) -> int:
        """Computes the intersection of sets and stores the result in destination."""
        members = self.sinter(*keys)
        self.delete(destination)
        if members:
            self.sadd(destination, *members)
        return len(members)

    def sunionstore(self, destination: str, *keys: str) -> int:
        """Computes the union of sets and stores the result in destination."""
        members = self.sunion(*keys)
        self.delete(destination)
        if members:
            self.sadd(destination, *members)
        return len(members)

    def sdiffstore(self, destination: str, *keys: str) -> int:
        """Computes the difference of sets and stores the result in destination."""
        members = self.sdiff(*keys)
        self.delete(destination)
        if members:
            self.sadd(destination, *members)
        return len(members)
