import unittest
from flashkv.store import DataStore


class TestSetStore(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()
        self.store.sadd("set1", "a", "b", "c")
        self.store.sadd("set2", "b", "c", "d")

    def test_sinterstore(self):
        count = self.store.sinterstore("dest_inter", "set1", "set2")
        self.assertEqual(count, 2)
        members = self.store.smembers("dest_inter")
        self.assertEqual(sorted(members), ["b", "c"])

    def test_sunionstore(self):
        count = self.store.sunionstore("dest_union", "set1", "set2")
        self.assertEqual(count, 4)
        members = self.store.smembers("dest_union")
        self.assertEqual(sorted(members), ["a", "b", "c", "d"])

    def test_sdiffstore(self):
        count = self.store.sdiffstore("dest_diff", "set1", "set2")
        self.assertEqual(count, 1)
        members = self.store.smembers("dest_diff")
        self.assertEqual(members, ["a"])

    def test_overwrite_existing_destination(self):
        self.store.set("existing", "string_val")
        count = self.store.sinterstore("existing", "set1", "set2")
        self.assertEqual(count, 2)
        members = self.store.smembers("existing")
        self.assertEqual(sorted(members), ["b", "c"])


if __name__ == "__main__":
    unittest.main()
