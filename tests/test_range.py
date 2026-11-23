import unittest
from flashkv.store import DataStore


class TestStringRangeCommands(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_strlen(self):
        self.assertEqual(self.store.strlen("nonexistent"), 0)
        self.store.set("mykey", "Hello World")
        self.assertEqual(self.store.strlen("mykey"), 11)

    def test_setrange_basic(self):
        self.store.set("key1", "Hello World")
        length = self.store.setrange("key1", 6, "Redis")
        self.assertEqual(length, 11)
        self.assertEqual(self.store.get("key1"), "Hello Redis")

    def test_setrange_padding(self):
        # Key does not exist, offset 5
        length = self.store.setrange("key2", 5, "World")
        self.assertEqual(length, 10)
        self.assertEqual(self.store.get("key2"), "\x00\x00\x00\x00\x00World")

    def test_getrange_basic(self):
        self.store.set("key1", "This is a string")
        self.assertEqual(self.store.getrange("key1", 0, 3), "This")
        self.assertEqual(self.store.getrange("key1", -3, -1), "ing")
        self.assertEqual(self.store.getrange("key1", 0, -1), "This is a string")
        self.assertEqual(self.store.getrange("key1", 10, 100), "string")

    def test_getrange_empty(self):
        self.assertEqual(self.store.getrange("nokey", 0, 5), "")


if __name__ == "__main__":
    unittest.main()
