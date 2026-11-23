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

    def test_set_algebra(self):
        self.store.sadd("set1", "a", "b", "c")
        self.store.sadd("set2", "b", "c", "d")
        self.store.sadd("set3", "c", "d", "e")

        # Intersection
        self.assertEqual(self.store.sinter("set1", "set2"), ["b", "c"])
        self.assertEqual(self.store.sinter("set1", "set2", "set3"), ["c"])
        self.assertEqual(self.store.sinter("set1", "nonexistent"), [])

        # Union
        self.assertEqual(self.store.sunion("set1", "set2"), ["a", "b", "c", "d"])
        self.assertEqual(self.store.sunion("set1", "nonexistent"), ["a", "b", "c"])

        # Difference
        self.assertEqual(self.store.sdiff("set1", "set2"), ["a"])
        self.assertEqual(self.store.sdiff("set2", "set1"), ["d"])
        self.assertEqual(self.store.sdiff("set1", "set2", "set3"), ["a"])


    def test_dbsize_and_flushdb(self):
        self.assertEqual(self.store.dbsize(), 0)
        self.store.set("k1", "v1")
        self.store.set("k2", "v2")
        self.assertEqual(self.store.dbsize(), 2)
        self.store.flushdb()
        self.assertEqual(self.store.dbsize(), 0)
        self.assertIsNone(self.store.get("k1"))

    def test_snapshot_persistence(self):
        import tempfile, os
        # Populate diverse data types
        self.store.set("str_key", "hello_world")
        self.store.rpush("list_key", "item1", "item2")
        self.store.hset("hash_key", {"field1": "val1"})
        self.store.sadd("set_key", "elemA", "elemB")
        self.store.set("expiring_key", "temp", ex=60.0)

        with tempfile.TemporaryDirectory() as tmpdir:
            snap_path = os.path.join(tmpdir, "dump.json")
            saved = self.store.dump_snapshot(snap_path)
            self.assertEqual(saved, 5)
            self.assertTrue(os.path.exists(snap_path))

            # New empty store
            new_store = DataStore()
            restored = new_store.load_snapshot(snap_path)
            self.assertEqual(restored, 5)

            # Validate restored state
            self.assertEqual(new_store.get("str_key"), "hello_world")
            self.assertEqual(new_store.lrange("list_key", 0, -1), ["item1", "item2"])
            self.assertEqual(new_store.hget("hash_key", "field1"), "val1")
            self.assertEqual(set(new_store.smembers("set_key")), {"elemA", "elemB"})
            self.assertGreater(new_store.ttl("expiring_key"), 0)


if __name__ == "__main__":
    unittest.main()
