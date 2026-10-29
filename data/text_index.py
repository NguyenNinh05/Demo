
import math
from collections import Counter

from shared.vietnamese import search_terms

# how many times each field is repeated in the indexed document (field boost)
FIELD_WEIGHTS = {"name": 3, "category_name": 3, "color": 2, "material": 2, "pattern": 2,
                 "brand": 1, "description": 1, "description_en": 1}


class TextIndex:

    def __init__(self, products, k1=1.2, b=0.75):
        self.k1, self.b = k1, b
        self.docs = {}
        for p in products:
            terms = []
            for field, weight in FIELD_WEIGHTS.items():
                terms += search_terms(p.get(field) or "") * weight
            self.docs[p["product_id"]] = Counter(terms)
        self.lengths = {pid: sum(tf.values()) for pid, tf in self.docs.items()}
        self.avg_len = sum(self.lengths.values()) / max(1, len(self.lengths))
        df = Counter(t for tf in self.docs.values() for t in tf)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.vocabulary = {t for t in df if "_" not in t}

    def score(self, terms, product_ids=None):
        """BM25 score of every (or the given) product for the query terms."""
        terms = [t for t in terms if t in self.idf]
        scores = {}
        for pid in (product_ids if product_ids is not None else self.docs):
            tf, length = self.docs[pid], self.lengths[pid]
            s = 0.0
            for t in terms:
                f = tf.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            if s > 0:
                scores[pid] = s
        return scores
