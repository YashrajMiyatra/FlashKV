import unittest
from flashkv.store import DataStore


class TestHyperLogLog(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_pfadd_and_pfcount_cardinality(self):
        # Adding elements alters registers
        res = self.store.pfadd("hll1", "apple", "banana", "cherry")
        self.assertEqual(res, 1)

        # Count approximate cardinality
        count = self.store.pfcount("hll1")
        self.assertEqual(count, 3)

        # Adding same elements again doesn't alter registers
        res = self.store.pfadd("hll1", "apple", "banana")
        self.assertEqual(res, 0)
        self.assertEqual(self.store.pfcount("hll1"), 3)

    def test_pfcount_multiple_keys(self):
        self.store.pfadd("hll_a", "foo", "bar", "zap")
        self.store.pfadd("hll_b", "zap", "a", "b", "c")

        # Set of unique elements: foo, bar, zap, a, b, c -> 6 distinct items
        combined_count = self.store.pfcount("hll_a", "hll_b")
        self.assertEqual(combined_count, 6)

    def test_pfmerge(self):
        self.store.pfadd("source1", "elem1", "elem2")
        self.store.pfadd("source2", "elem2", "elem3", "elem4")

        success = self.store.pfmerge("dest", "source1", "source2")
        self.assertTrue(success)

        count = self.store.pfcount("dest")
        self.assertEqual(count, 4)

    def test_pfcount_nonexistent_key(self):
        self.assertEqual(self.store.pfcount("nonexistent"), 0)

    def test_wrong_type(self):
        self.store.set("str_key", "hello")
        with self.assertRaises(TypeError):
            self.store.pfadd("str_key", "val")
        with self.assertRaises(TypeError):
            self.store.pfcount("str_key")
        with self.assertRaises(TypeError):
            self.store.pfmerge("str_key", "nonexistent")


if __name__ == "__main__":
    unittest.main()
