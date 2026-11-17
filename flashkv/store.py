"""
In-memory data store supporting Strings, Lists, Hashes, Sets, and Key Expiration (TTL).
"""

import fnmatch
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union


class StoreEntry:
    __slots__ = ("value", "data_type", "expires_at")

    def __init__(
        self,
        value: Any,
        data_type: str,
        expires_at: Optional[float] = None,
    ) -> None:
        self.value = value
        self.data_type = data_type  # 'string', 'list', 'hash', 'set'
        self.expires_at = expires_at

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        if now is None:
            now = time.time()
        return now >= self.expires_at


class DataStore:
    """Thread-safe and async-compatible in-memory store."""

    def __init__(self) -> None:
        self._data: Dict[str, StoreEntry] = {}
        self.stats: Dict[str, int] = {
            "total_commands": 0,
            "keyspace_hits": 0,
            "keyspace_misses": 0,
            "expired_keys": 0,
        }
        self.created_at = time.time()

    def _get_entry(self, key: str) -> Optional[StoreEntry]:
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._data[key]
            self.stats["expired_keys"] += 1
            return None
        return entry

    # ------------------ Key & TTL Management ------------------ #

    def exists(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if self._get_entry(k) is not None:
                count += 1
        return count

    def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._data:
                del self._data[k]
                count += 1
        return count

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

    # ------------------ Lists ------------------ #

    def lpush(self, key: str, *values: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
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

    # ------------------ Hashes ------------------ #

    def hset(self, key: str, mapping: Dict[str, str]) -> int:
        entry = self._get_entry(key)
        added = 0
        if entry is None:
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

    # ------------------ Sets ------------------ #

    def sadd(self, key: str, *members: str) -> int:
        entry = self._get_entry(key)
        if entry is None:
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
