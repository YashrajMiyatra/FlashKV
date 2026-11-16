"""
REdis Serialization Protocol (RESP2) parser and serializer.
Supports streaming/chunked parsing of RESP messages.
"""

from typing import Any, List, Optional, Tuple, Union


class RESPError(Exception):
    """Base class for RESP protocol errors."""
    pass


class IncompleteDataError(RESPError):
    """Raised when more data is needed to complete parsing a RESP message."""
    pass


def encode_simple_string(val: str) -> bytes:
    return f"+{val}\r\n".encode("utf-8")


def encode_error(err: str) -> bytes:
    return f"-ERR {err}\r\n".encode("utf-8")


def encode_int(val: int) -> bytes:
    return f":{val}\r\n".encode("utf-8")


def encode_bulk_string(val: Optional[Union[str, bytes]]) -> bytes:
    if val is None:
        return b"$-1\r\n"
    if isinstance(val, str):
        b_val = val.encode("utf-8")
    else:
        b_val = val
    return f"${len(b_val)}\r\n".encode("utf-8") + b_val + b"\r\n"


def encode_array(elements: Optional[List[Any]]) -> bytes:
    if elements is None:
        return b"*-1\r\n"
    out = [f"*{len(elements)}\r\n".encode("utf-8")]
    for item in elements:
        out.append(encode_value(item))
    return b"".join(out)


def encode_value(val: Any) -> bytes:
    """Recursively encode any Python data structure to RESP."""
    if val is None:
        return encode_bulk_string(None)
    elif isinstance(val, bool):
        return encode_int(1 if val else 0)
    elif isinstance(val, int):
        return encode_int(val)
    elif isinstance(val, float):
        return encode_bulk_string(str(val))
    elif isinstance(val, (str, bytes)):
        return encode_bulk_string(val)
    elif isinstance(val, (list, tuple, set)):
        return encode_array(list(val))
    elif isinstance(val, dict):
        # Flatten dict into [k1, v1, k2, v2, ...]
        flat = []
        for k, v in val.items():
            flat.append(str(k))
            flat.append(str(v))
        return encode_array(flat)
    elif isinstance(val, Exception):
        return encode_error(str(val))
    else:
        return encode_bulk_string(str(val))


class RESPReader:
    """
    Incremental buffer-based RESP reader.
    Handles partial network packets and pipelined commands gracefully.
    """

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, data: bytes) -> None:
        self.buffer.extend(data)

    def read_one(self) -> Tuple[bool, Any]:
        """
        Attempts to parse one complete RESP entity from the buffer.
        Returns (True, parsed_value) if successful,
        or (False, None) if incomplete.
        """
        if not self.buffer:
            return False, None

        # Check for inline command format (e.g. "PING\r\n" from telnet/nc)
        prefix = chr(self.buffer[0])
        if prefix not in ("+", "-", ":", "$", "*"):
            return self._parse_inline()

        try:
            val, consumed = self._parse_at(0)
            del self.buffer[:consumed]
            return True, val
        except IncompleteDataError:
            return False, None

    def _parse_inline(self) -> Tuple[bool, Any]:
        crlf_idx = self.buffer.find(b"\r\n")
        if crlf_idx == -1:
            return False, None
        line = self.buffer[:crlf_idx].decode("utf-8", errors="replace").strip()
        del self.buffer[:crlf_idx + 2]
        if not line:
            return False, None
        parts = line.split()
        return True, parts

    def _read_line(self, offset: int) -> Tuple[bytes, int]:
        crlf_idx = self.buffer.find(b"\r\n", offset)
        if crlf_idx == -1:
            raise IncompleteDataError()
        return bytes(self.buffer[offset:crlf_idx]), crlf_idx + 2

    def _parse_at(self, offset: int) -> Tuple[Any, int]:
        if offset >= len(self.buffer):
            raise IncompleteDataError()

        prefix = chr(self.buffer[offset])
        pos = offset + 1

        if prefix == "+":
            line, next_pos = self._read_line(pos)
            return line.decode("utf-8", errors="replace"), next_pos

        elif prefix == "-":
            line, next_pos = self._read_line(pos)
            return RESPError(line.decode("utf-8", errors="replace")), next_pos

        elif prefix == ":":
            line, next_pos = self._read_line(pos)
            return int(line.decode("utf-8")), next_pos

        elif prefix == "$":
            line, next_pos = self._read_line(pos)
            length = int(line.decode("utf-8"))
            if length == -1:
                return None, next_pos
            if len(self.buffer) < next_pos + length + 2:
                raise IncompleteDataError()
            data = bytes(self.buffer[next_pos : next_pos + length])
            if bytes(self.buffer[next_pos + length : next_pos + length + 2]) != b"\r\n":
                raise RESPError("Protocol error: expected CRLF after bulk string")
            return data.decode("utf-8", errors="replace"), next_pos + length + 2

        elif prefix == "*":
            line, next_pos = self._read_line(pos)
            count = int(line.decode("utf-8"))
            if count == -1:
                return None, next_pos
            elements = []
            curr_pos = next_pos
            for _ in range(count):
                elem, curr_pos = self._parse_at(curr_pos)
                elements.append(elem)
            return elements, curr_pos

        else:
            raise RESPError(f"Protocol error: unknown type prefix '{prefix}'")
