import unittest
from flashkv.server import FlashKVServer


class TestListMove(unittest.TestCase):
    def setUp(self):
        self.server = FlashKVServer(enable_aof=False)
        self.store = self.server.store

    def test_rpoplpush_basic(self):
        self.store.rpush("src", "one", "two", "three")
        val = self.store.rpoplpush("src", "dst")
        self.assertEqual(val, "three")
        self.assertEqual(self.store.lrange("src", 0, -1), ["one", "two"])
        self.assertEqual(self.store.lrange("dst", 0, -1), ["three"])

    def test_rpoplpush_rotation(self):
        self.store.rpush("rotate", "1", "2", "3")
        val = self.store.rpoplpush("rotate", "rotate")
        self.assertEqual(val, "3")
        self.assertEqual(self.store.lrange("rotate", 0, -1), ["3", "1", "2"])

    def test_rpoplpush_nonexistent_source(self):
        val = self.store.rpoplpush("nonexistent", "dst")
        self.assertIsNone(val)

    def test_lmove_directions(self):
        # LEFT to RIGHT
        self.store.rpush("q1", "a", "b", "c")
        val = self.store.lmove("q1", "q2", "LEFT", "RIGHT")
        self.assertEqual(val, "a")
        self.assertEqual(self.store.lrange("q1", 0, -1), ["b", "c"])
        self.assertEqual(self.store.lrange("q2", 0, -1), ["a"])

        # RIGHT to RIGHT
        val2 = self.store.lmove("q1", "q2", "RIGHT", "RIGHT")
        self.assertEqual(val2, "c")
        self.assertEqual(self.store.lrange("q1", 0, -1), ["b"])
        self.assertEqual(self.store.lrange("q2", 0, -1), ["a", "c"])

    def test_wrongtype_error(self):
        self.store.set("str_key", "hello")
        self.store.rpush("list_key", "item")

        with self.assertRaises(TypeError):
            self.store.lmove("str_key", "list_key", "LEFT", "LEFT")

        with self.assertRaises(TypeError):
            self.store.lmove("list_key", "str_key", "LEFT", "LEFT")

    def test_server_command_rpoplpush(self):
        self.store.rpush("alpha", "x", "y")
        res = self.server.execute_command(["RPOPLPUSH", "alpha", "beta"])
        self.assertIn(b"$1\r\ny\r\n", res)
        self.assertEqual(self.store.lrange("beta", 0, -1), ["y"])

    def test_server_command_lmove(self):
        self.store.rpush("src2", "first", "second")
        res = self.server.execute_command(["LMOVE", "src2", "dst2", "LEFT", "RIGHT"])
        self.assertIn(b"$5\r\nfirst\r\n", res)
        self.assertEqual(self.store.lrange("dst2", 0, -1), ["first"])


if __name__ == "__main__":
    unittest.main()
