import time
import unittest
from flashkv.store import DataStore


class TestDataStore(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_strings(self):
        self.store.set("foo", "bar")
        self.assertEqual(self.store.get("foo"), "bar")
        self.assertEqual(self.store.exists("foo"), 1)
        self.assertEqual(self.store.delete("foo"), 1)
        self.assertIsNone(self.store.get("foo"))

    def test_incr_decr(self):
        self.assertEqual(self.store.incrby("counter", 5), 5)
        self.assertEqual(self.store.incrby("counter", -2), 3)
        self.assertEqual(self.store.get("counter"), "3")

    def test_ttl_expiry(self):
        self.store.set("temp", "val", ex=0.1)
        self.assertEqual(self.store.get("temp"), "val")
        time.sleep(0.15)
        self.assertIsNone(self.store.get("temp"))

    def test_lists(self):
        self.store.rpush("mylist", "a", "b", "c")
        self.assertEqual(self.store.llen("mylist"), 3)
        self.assertEqual(self.store.lrange("mylist", 0, -1), ["a", "b", "c"])
        self.assertEqual(self.store.lpop("mylist"), "a")
        self.assertEqual(self.store.rpop("mylist"), "c")
        self.assertEqual(self.store.llen("mylist"), 1)

    def test_hashes(self):
        self.store.hset("user:1", {"name": "Bob", "role": "admin"})
        self.assertEqual(self.store.hget("user:1", "name"), "Bob")
        self.assertEqual(self.store.hgetall("user:1"), {"name": "Bob", "role": "admin"})
        self.assertEqual(self.store.hdel("user:1", "role"), 1)
        self.assertIsNone(self.store.hget("user:1", "role"))

    def test_sets(self):
        self.assertEqual(self.store.sadd("tags", "python", "redis", "python"), 2)
        self.assertEqual(self.store.scard("tags"), 2)
        self.assertEqual(self.store.sismember("tags", "redis"), 1)
        self.assertEqual(self.store.sismember("tags", "ruby"), 0)
        self.assertEqual(self.store.smembers("tags"), ["python", "redis"])


if __name__ == "__main__":
    unittest.main()
