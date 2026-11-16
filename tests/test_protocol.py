import unittest
from flashkv.protocol import (
    encode_simple_string,
    encode_error,
    encode_int,
    encode_bulk_string,
    encode_array,
    RESPReader,
    RESPError,
)


class TestRESPProtocol(unittest.TestCase):
    def test_encoding(self):
        self.assertEqual(encode_simple_string("OK"), b"+OK\r\n")
        self.assertEqual(encode_error("syntax error"), b"-ERR syntax error\r\n")
        self.assertEqual(encode_int(42), b":42\r\n")
        self.assertEqual(encode_bulk_string("hello"), b"$5\r\nhello\r\n")
        self.assertEqual(encode_bulk_string(None), b"$-1\r\n")
        self.assertEqual(encode_array(["SET", "key", "val"]), b"*3\r\n$3\r\nSET\r\n$3\r\nkey\r\n$3\r\nval\r\n")

    def test_reader_simple_string(self):
        reader = RESPReader()
        reader.feed(b"+PONG\r\n")
        ok, val = reader.read_one()
        self.assertTrue(ok)
        self.assertEqual(val, "PONG")

    def test_reader_bulk_string(self):
        reader = RESPReader()
        reader.feed(b"$5\r\nworld\r\n")
        ok, val = reader.read_one()
        self.assertTrue(ok)
        self.assertEqual(val, "world")

    def test_reader_array(self):
        reader = RESPReader()
        reader.feed(b"*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n")
        ok, val = reader.read_one()
        self.assertTrue(ok)
        self.assertEqual(val, ["ECHO", "hello"])

    def test_reader_chunked_streaming(self):
        """Simulate TCP packet fragmentation."""
        reader = RESPReader()
        data = b"*2\r\n$4\r\nECHO\r\n$5\r\nhello\r\n"
        reader.feed(data[:7])
        ok, val = reader.read_one()
        self.assertFalse(ok)
        self.assertIsNone(val)

        reader.feed(data[7:])
        ok, val = reader.read_one()
        self.assertTrue(ok)
        self.assertEqual(val, ["ECHO", "hello"])

    def test_reader_inline(self):
        reader = RESPReader()
        reader.feed(b"PING\r\n")
        ok, val = reader.read_one()
        self.assertTrue(ok)
        self.assertEqual(val, ["PING"])


if __name__ == "__main__":
    unittest.main()
