import unittest
from flashkv.vector import VectorIndex, VectorManager


class TestVectorIndex(unittest.TestCase):
    def setUp(self):
        self.mgr = VectorManager()
        self.index = self.mgr.get_or_create("embeddings", dimension=3)

    def test_add_and_search_cosine(self):
        # Target vectors
        self.index.add("v_target", [1.0, 0.0, 0.0], {"doc": "target"})
        self.index.add("v_similar", [0.99, 0.05, 0.0], {"doc": "similar"})
        self.index.add("v_orthogonal", [0.0, 1.0, 0.0], {"doc": "orthogonal"})

        # Search with vector identical to v_target
        results = self.index.search([1.0, 0.0, 0.0], top_k=2, metric="cosine")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["id"], "v_target")
        self.assertAlmostEqual(results[0]["score"], 1.0, places=4)
        self.assertEqual(results[1]["id"], "v_similar")

    def test_search_euclidean(self):
        self.index.add("p1", [0.0, 0.0, 0.0])
        self.index.add("p2", [1.0, 1.0, 1.0])
        self.index.add("p3", [10.0, 10.0, 10.0])

        results = self.index.search([0.1, 0.1, 0.1], top_k=2, metric="euclidean")
        self.assertEqual(results[0]["id"], "p1")
        self.assertEqual(results[1]["id"], "p2")

    def test_dimension_validation(self):
        with self.assertRaises(ValueError):
            self.index.add("bad_vec", [1.0, 2.0])  # dimension is 3, supplied 2

    def test_delete_vector(self):
        self.index.add("del_me", [1.0, 2.0, 3.0])
        self.assertTrue(self.index.delete("del_me"))
        self.assertFalse(self.index.delete("del_me"))


if __name__ == "__main__":
    unittest.main()
