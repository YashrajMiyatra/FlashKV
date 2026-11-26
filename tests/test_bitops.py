import unittest
from flashkv.store import DataStore


class TestBitOperations(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_setbit_and_getbit(self):
        # Setting bit 7 to 1 produces byte \x01 (binary 00000001)
        old_bit = self.store.setbit("mykey", 7, 1)
        self.assertEqual(old_bit, 0)
        self.assertEqual(self.store.getbit("mykey", 7), 1)
        self.assertEqual(self.store.getbit("mykey", 0), 0)

        # Overwriting bit 7 returns previous bit 1
        old_bit = self.store.setbit("mykey", 7, 0)
        self.assertEqual(old_bit, 1)
        self.assertEqual(self.store.getbit("mykey", 7), 0)

    def test_setbit_multibyte_offset(self):
        # Setting bit 16 to 1 extends key to 3 bytes
        self.store.setbit("bits", 16, 1)
        self.assertEqual(self.store.getbit("bits", 16), 1)
        self.assertEqual(self.store.getbit("bits", 15), 0)
        self.assertEqual(self.store.getbit("bits", 17), 0)
        self.assertEqual(self.store.strlen("bits"), 3)

    def test_bitcount(self):
        # ASCII 'a' = 0x61 = 01100001 -> 3 bits set
        # ASCII 'b' = 0x62 = 01100010 -> 3 bits set
        self.store.set("str", "ab")
        self.assertEqual(self.store.bitcount("str"), 6)

        # Range slice [0, 0] -> first byte 'a' -> 3 bits
        self.assertEqual(self.store.bitcount("str", 0, 0), 3)
        # Range slice [1, 1] -> second byte 'b' -> 3 bits
        self.assertEqual(self.store.bitcount("str", 1, 1), 3)
        # Negative range slice [-1, -1] -> second byte 'b' -> 3 bits
        self.assertEqual(self.store.bitcount("str", -1, -1), 3)

    def test_bitcount_empty_or_nonexistent(self):
        self.assertEqual(self.store.bitcount("nonexistent"), 0)
        self.store.set("empty", "")
        self.assertEqual(self.store.bitcount("empty"), 0)

    def test_bit_wrong_type(self):
        self.store.lpush("listkey", "item")
        with self.assertRaises(TypeError):
            self.store.setbit("listkey", 0, 1)
        with self.assertRaises(TypeError):
            self.store.getbit("listkey", 0)
        with self.assertRaises(TypeError):
            self.store.bitcount("listkey")

    def test_bit_invalid_args(self):
        with self.assertRaises(ValueError):
            self.store.setbit("k", -1, 1)
        with self.assertRaises(ValueError):
            self.store.setbit("k", 0, 2)
        with self.assertRaises(ValueError):
            self.store.getbit("k", -5)


if __name__ == "__main__":
    unittest.main()
