"""
Unit tests for LRU Cache Eviction and Memory Limit Enforcement in FlashKV.
"""

import time
import unittest
from flashkv.store import DataStore


class TestLRUEviction(unittest.TestCase):
    def test_max_keys_enforcement(self):
        store = DataStore(max_keys=3)
        store.set("k1", "v1")
        store.set("k2", "v2")
        store.set("k3", "v3")
        self.assertEqual(store.dbsize(), 3)

        # Adding a 4th key should evict k1 (the oldest accessed)
        time.sleep(0.01)
        store.set("k4", "v4")
        self.assertEqual(store.dbsize(), 3)
        self.assertIsNone(store.get("k1"))
        self.assertEqual(store.get("k2"), "v2")
        self.assertEqual(store.get("k3"), "v3")
        self.assertEqual(store.get("k4"), "v4")
        self.assertEqual(store.stats["evicted_keys"], 1)

    def test_lru_access_ordering(self):
        store = DataStore(max_keys=3)
        store.set("a", "1")
        time.sleep(0.01)
        store.set("b", "2")
        time.sleep(0.01)
        store.set("c", "3")

        # Access 'a' to make it the most recently used
        time.sleep(0.01)
        store.get("a")

        # Now 'b' is the least recently accessed. Adding 'd' should evict 'b'.
        time.sleep(0.01)
        store.set("d", "4")

        self.assertEqual(store.dbsize(), 3)
        self.assertIsNone(store.get("b"))
        self.assertEqual(store.get("a"), "1")
        self.assertEqual(store.get("c"), "3")
        self.assertEqual(store.get("d"), "4")

    def test_eviction_stats(self):
        store = DataStore(max_keys=2)
        store.set("x", "10")
        store.set("y", "20")
        store.set("z", "30")

        stats = store.get_eviction_stats()
        self.assertEqual(stats["max_keys"], 2)
        self.assertEqual(stats["current_keys"], 2)
        self.assertEqual(stats["evicted_keys"], 1)


if __name__ == "__main__":
    unittest.main()
