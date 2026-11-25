import unittest
from flashkv.store import DataStore


class TestUnlink(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()
        self.store.set("k1", "val1")
        self.store.set("k2", "val2")
        self.store.set("k3", "val3")

    def test_unlink_single(self):
        count = self.store.unlink("k1")
        self.assertEqual(count, 1)
        self.assertFalse(self.store.exists("k1"))
        self.assertTrue(self.store.exists("k2"))

    def test_unlink_multiple(self):
        count = self.store.unlink("k2", "k3", "nonexistent")
        self.assertEqual(count, 2)
        self.assertFalse(self.store.exists("k2"))
        self.assertFalse(self.store.exists("k3"))

    def test_unlink_empty(self):
        self.assertEqual(self.store.unlink("nonexistent"), 0)


if __name__ == "__main__":
    unittest.main()
