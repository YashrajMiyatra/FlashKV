import unittest
from flashkv.store import DataStore


class TestListExtendedCommands(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_lpushx_rpushx_existing(self):
        # LPUSHX and RPUSHX must do nothing if key doesn't exist
        self.assertEqual(self.store.lpushx("nonexistent", "val"), 0)
        self.assertEqual(self.store.rpushx("nonexistent", "val"), 0)
        self.assertIsNone(self.store.get("nonexistent"))

        # Create list first
        self.store.lpush("mylist", "b")
        self.assertEqual(self.store.lpushx("mylist", "a"), 2)
        self.assertEqual(self.store.rpushx("mylist", "c"), 3)
        self.assertEqual(self.store.lrange("mylist", 0, -1), ["a", "b", "c"])

    def test_lindex_bounds(self):
        self.store.rpush("items", "first", "second", "third")
        self.assertEqual(self.store.lindex("items", 0), "first")
        self.assertEqual(self.store.lindex("items", 1), "second")
        self.assertEqual(self.store.lindex("items", -1), "third")
        self.assertEqual(self.store.lindex("items", -2), "second")
        self.assertIsNone(self.store.lindex("items", 10))
        self.assertIsNone(self.store.lindex("items", -10))

    def test_lindex_nonexistent_key(self):
        self.assertIsNone(self.store.lindex("nokey", 0))


if __name__ == "__main__":
    unittest.main()
