import time
import unittest
from flashkv.store import DataStore


class TestRandomKey(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_randomkey_empty(self):
        self.assertIsNone(self.store.randomkey())

    def test_randomkey_single(self):
        self.store.set("k1", "v1")
        self.assertEqual(self.store.randomkey(), "k1")

    def test_randomkey_multiple(self):
        keys = {"user:1", "user:2", "user:3", "user:4"}
        for k in keys:
            self.store.set(k, "val")
        chosen = self.store.randomkey()
        self.assertIn(chosen, keys)

    def test_randomkey_ignores_expired(self):
        self.store.set("expired_key", "old", ex=0.01)
        self.store.set("active_key", "fresh")
        time.sleep(0.02)
        # expired_key must be evicted/ignored, leaving active_key
        self.assertEqual(self.store.randomkey(), "active_key")


if __name__ == "__main__":
    unittest.main()
