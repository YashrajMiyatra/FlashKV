import unittest
from flashkv.store import DataStore


class TestIncrDecrCommands(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_decrby_existing_and_new(self):
        # New key starts at 0, decremented by 5 -> -5
        self.assertEqual(self.store.decrby("counter", 5), -5)
        self.assertEqual(self.store.get("counter"), "-5")

        # Decrement again
        self.assertEqual(self.store.decr("counter"), -6)
        self.assertEqual(self.store.get("counter"), "-6")

    def test_incrbyfloat_basic(self):
        self.store.set("float_key", "10.5")
        res = self.store.incrbyfloat("float_key", 0.25)
        self.assertAlmostEqual(res, 10.75)
        self.assertEqual(self.store.get("float_key"), "10.75")

        # Negative float increment
        res2 = self.store.incrbyfloat("float_key", -5.0)
        self.assertAlmostEqual(res2, 5.75)

    def test_incrbyfloat_nonexistent(self):
        res = self.store.incrbyfloat("new_float", 3.1415)
        self.assertAlmostEqual(res, 3.1415)
        self.assertEqual(self.store.get("new_float"), "3.1415")

    def test_invalid_float_raises(self):
        self.store.set("invalid_str", "not_a_number")
        with self.assertRaises(ValueError):
            self.store.incrbyfloat("invalid_str", 1.0)


if __name__ == "__main__":
    unittest.main()
