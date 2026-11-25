import time
import unittest
from flashkv.store import DataStore


class TestTouch(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()
        self.store.set("k1", "v1")
        self.store.set("k2", "v2")

    def test_touch_existing(self):
        t0 = self.store._data["k1"].last_accessed
        time.sleep(0.01)
        count = self.store.touch("k1", "k2", "nonexistent")
        self.assertEqual(count, 2)
        t1 = self.store._data["k1"].last_accessed
        self.assertGreater(t1, t0)

    def test_touch_nonexistent(self):
        self.assertEqual(self.store.touch("foo", "bar"), 0)

    def test_touch_expired(self):
        self.store.set("exp", "val", ex=0.01)
        time.sleep(0.02)
        self.assertEqual(self.store.touch("exp"), 0)


if __name__ == "__main__":
    unittest.main()
