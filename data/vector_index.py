"""Data Layer - VectorIndex.

Stores one CLIP embedding per product photo and answers nearest-neighbour
queries with cosine similarity. All vectors are kept unit-length in one
NumPy matrix, so a search is a single matrix-vector product (well under a
millisecond for hundreds of products). It could be replaced by pgvector or
FAISS without changing the Application layer.
"""
import os

import numpy as np


class VectorIndex:

    def __init__(self):
        self.ids = []
        self.matrix = np.zeros((0, 0), dtype=np.float32)
        self._row = {}

    @staticmethod
    def _unit(m):
        n = np.linalg.norm(m, axis=-1, keepdims=True)
        return m / np.where(n == 0, 1, n)

    def build(self, ids, vectors):
        self.ids = [int(i) for i in ids]
        self.matrix = self._unit(np.asarray(vectors, dtype=np.float32))
        self._row = {pid: i for i, pid in enumerate(self.ids)}
        return self

    def __len__(self):
        return len(self.ids)

    def vector(self, product_id):
        i = self._row.get(int(product_id))
        return None if i is None else self.matrix[i]

    def scores(self, query):
        """Cosine similarity of the query with every product: {product_id: score}."""
        q = self._unit(np.asarray(query, dtype=np.float32))
        return dict(zip(self.ids, (self.matrix @ q).tolist()))

    def search(self, query, k=10):
        q = self._unit(np.asarray(query, dtype=np.float32))
        sims = self.matrix @ q
        top = np.argsort(-sims)[:k]
        return [(self.ids[i], float(sims[i])) for i in top]

    def save(self, path, model_name):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        np.savez(path, ids=np.array(self.ids), vectors=self.matrix, model=np.array(model_name))

    def load(self, path, model_name, expected_ids):
        """Load a cached index; returns False if it is missing or out of date."""
        if not os.path.isfile(path):
            return False
        data = np.load(path)
        if str(data["model"]) != model_name or sorted(data["ids"].tolist()) != sorted(expected_ids):
            return False
        self.build(data["ids"].tolist(), data["vectors"])
        return True
