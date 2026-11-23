import unittest
from flashkv.store import DataStore


class TestMsetnxCommand(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_msetnx_all_new_keys(self):
        res = self.store.msetnx({"key1": "val1", "key2": "val2", "key3": "val3"})
        self.assertEqual(res, 1)
        self.assertEqual(self.store.get("key1"), "val1")
        self.assertEqual(self.store.get("key2"), "val2")
        self.assertEqual(self.store.get("key3"), "val3")

    def test_msetnx_one_key_exists_aborts_all(self):
        self.store.set("existing_key", "original")

        # Try to set existing_key + brand new key
        res = self.store.msetnx({"existing_key": "new_val", "brand_new": "foo"})
        self.assertEqual(res, 0)

        # Existing key must be untouched
        self.assertEqual(self.store.get("existing_key"), "original")
        # Brand new key must NOT have been created
        self.assertIsNone(self.store.get("brand_new"))

    def test_msetnx_empty_dict(self):
        self.assertEqual(self.store.msetnx({}), 1)


if __name__ == "__main__":
    unittest.main()
