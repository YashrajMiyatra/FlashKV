import unittest
from flashkv.store import DataStore


class TestRename(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()
        self.store.set("mykey", "hello")

    def test_rename_success(self):
        self.assertTrue(self.store.rename("mykey", "newkey"))
        self.assertFalse(self.store.exists("mykey"))
        self.assertEqual(self.store.get("newkey"), "hello")

    def test_rename_missing_key(self):
        with self.assertRaises(KeyError):
            self.store.rename("nonexistent", "other")

    def test_rename_same_key(self):
        self.assertTrue(self.store.rename("mykey", "mykey"))
        self.assertEqual(self.store.get("mykey"), "hello")

    def test_renamenx_success(self):
        res = self.store.renamenx("mykey", "freekey")
        self.assertEqual(res, 1)
        self.assertEqual(self.store.get("freekey"), "hello")

    def test_renamenx_existing_destination(self):
        self.store.set("dest", "occupied")
        res = self.store.renamenx("mykey", "dest")
        self.assertEqual(res, 0)
        self.assertEqual(self.store.get("mykey"), "hello")
        self.assertEqual(self.store.get("dest"), "occupied")


if __name__ == "__main__":
    unittest.main()
