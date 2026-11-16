"""
Append-Only File (AOF) persistence engine.
Logs state-mutating commands to disk and replays them on startup.
Supports AOF compaction/rewrite.
"""

import os
import time
from typing import Any, Callable, List, Optional
from .protocol import encode_array, RESPReader


class AOFManager:
    """Manages the append-only log file for durability."""

    def __init__(self, filepath: str = "flashkv.aof", enabled: bool = True) -> None:
        self.filepath = filepath
        self.enabled = enabled
        self._file: Optional[Any] = None
        self._last_fsync: float = time.time()

        if self.enabled:
            # Open file in append-binary mode
            self._file = open(self.filepath, "a+b")

    def append_command(self, cmd_args: List[Any]) -> None:
        """Appends a mutating command to the AOF log."""
        if not self.enabled or self._file is None:
            return
        encoded = encode_array([str(a) for a in cmd_args])
        self._file.write(encoded)
        # Flush every second or immediately
        now = time.time()
        if now - self._last_fsync >= 1.0:
            self._file.flush()
            os.fsync(self._file.fileno())
            self._last_fsync = now

    def flush(self) -> None:
        if self._file is not None and not self._file.closed:
            self._file.flush()
            os.fsync(self._file.fileno())

    def close(self) -> None:
        if self._file is not None and not self._file.closed:
            self.flush()
            self._file.close()

    def replay(self, executor: Callable[[List[str]], Any]) -> int:
        """
        Reads existing AOF file and replays commands through executor callback.
        Returns number of replayed commands.
        """
        if not os.path.exists(self.filepath):
            return 0

        count = 0
        reader = RESPReader()
        with open(self.filepath, "rb") as f:
            chunk = f.read(65536)
            while chunk:
                reader.feed(chunk)
                while True:
                    ok, cmd = reader.read_one()
                    if not ok:
                        break
                    if isinstance(cmd, list) and cmd:
                        try:
                            executor(cmd)
                            count += 1
                        except Exception as e:
                            # Skip corrupt/failed replay lines gracefully
                            pass
                chunk = f.read(65536)

        return count

    def rewrite(self, store_dump_func: Callable[[], List[List[str]]]) -> bool:
        """
        Compacts the AOF file by dumping current database state into a fresh temp file,
        then atomically replacing the current file.
        """
        if not self.enabled:
            return False

        tmp_path = f"{self.filepath}.tmp"
        commands = store_dump_func()

        with open(tmp_path, "wb") as f_tmp:
            for cmd in commands:
                f_tmp.write(encode_array(cmd))
            f_tmp.flush()
            os.fsync(f_tmp.fileno())

        if self._file is not None and not self._file.closed:
            self._file.close()

        os.replace(tmp_path, self.filepath)
        self._file = open(self.filepath, "a+b")
        return True
