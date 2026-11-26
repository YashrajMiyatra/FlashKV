import unittest
from flashkv.store import DataStore


class TestGeospatialOperations(unittest.TestCase):
    def setUp(self):
        self.store = DataStore()

    def test_geoadd_and_geopos(self):
        # Palermo and Catania coordinates from official Redis docs
        added = self.store.geoadd("Sicily", 13.361389, 38.115556, "Palermo", 15.087269, 37.502669, "Catania")
        self.assertEqual(added, 2)

        positions = self.store.geopos("Sicily", "Palermo", "Catania", "NonExistent")
        self.assertEqual(len(positions), 3)
        self.assertAlmostEqual(positions[0][0], 13.361389)
        self.assertAlmostEqual(positions[0][1], 38.115556)
        self.assertAlmostEqual(positions[1][0], 15.087269)
        self.assertAlmostEqual(positions[1][1], 37.502669)
        self.assertIsNone(positions[2])

    def test_geodist_units(self):
        self.store.geoadd("Sicily", 13.361389, 38.115556, "Palermo", 15.087269, 37.502669, "Catania")

        # Distance ~ 166274.25 meters
        dist_m = self.store.geodist("Sicily", "Palermo", "Catania", unit="m")
        self.assertIsNotNone(dist_m)
        self.assertAlmostEqual(dist_m, 166274.25, delta=5.0)

        # In kilometers ~ 166.27 km
        dist_km = self.store.geodist("Sicily", "Palermo", "Catania", unit="km")
        self.assertAlmostEqual(dist_km, 166.27, delta=0.05)

        # In miles ~ 103.31 mi
        dist_mi = self.store.geodist("Sicily", "Palermo", "Catania", unit="mi")
        self.assertAlmostEqual(dist_mi, 103.31, delta=0.05)

    def test_geodist_missing_member_or_key(self):
        self.assertIsNone(self.store.geodist("NoKey", "m1", "m2"))
        self.store.geoadd("Points", 0.0, 0.0, "Origin")
        self.assertIsNone(self.store.geodist("Points", "Origin", "Missing"))

    def test_invalid_coordinates(self):
        with self.assertRaises(ValueError):
            self.store.geoadd("loc", 200.0, 0.0, "Out")
        with self.assertRaises(ValueError):
            self.store.geoadd("loc", 0.0, 95.0, "Out")
        with self.assertRaises(ValueError):
            self.store.geoadd("loc", 0.0, 0.0)  # Incomplete triple

    def test_wrong_type(self):
        self.store.set("str_key", "val")
        with self.assertRaises(TypeError):
            self.store.geoadd("str_key", 0.0, 0.0, "P")
        with self.assertRaises(TypeError):
            self.store.geopos("str_key", "P")
        with self.assertRaises(TypeError):
            self.store.geodist("str_key", "P1", "P2")


if __name__ == "__main__":
    unittest.main()
