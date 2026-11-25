import unittest
from flashkv.store import DataStore


class TestHashIncr(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_hincrby_new_key_and_field(self):
        res = self.store.hincrby("user:100", "views", 5)
        self.assertEqual(res, 5)
        self.assertEqual(self.store.hget("user:100", "views"), "5")

        res2 = self.store.hincrby("user:100", "views", 10)
        self.assertEqual(res2, 15)
        self.assertEqual(self.store.hget("user:100", "views"), "15")

    def test_hincrby_negative(self):
        self.store.hset("user:100", {"points": "20"})
        res = self.store.hincrby("user:100", "points", -5)
        self.assertEqual(res, 15)
        self.assertEqual(self.store.hget("user:100", "points"), "15")

    def test_hincrby_invalid_value(self):
        self.store.hset("user:100", {"name": "alice"})
        with self.assertRaises(ValueError):
            self.store.hincrby("user:100", "name", 1)

    def test_hincrbyfloat(self):
        res = self.store.hincrbyfloat("cart:1", "total", 10.5)
        self.assertAlmostEqual(res, 10.5)
        self.assertEqual(self.store.hget("cart:1", "total"), "10.5")

        res2 = self.store.hincrbyfloat("cart:1", "total", 2.25)
        self.assertAlmostEqual(res2, 12.75)
        self.assertEqual(self.store.hget("cart:1", "total"), "12.75")

    def test_wrong_type(self):
        self.store.set("str_key", "hello")
        with self.assertRaises(TypeError):
            self.store.hincrby("str_key", "f", 1)
        with self.assertRaises(TypeError):
            self.store.hincrbyfloat("str_key", "f", 1.5)


if __name__ == "__main__":
    unittest.main()
