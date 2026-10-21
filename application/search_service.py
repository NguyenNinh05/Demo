"""Application / Intelligence Layer - SearchService.

The single entry point of the search use case for the Presentation layer:

    SearchUI -> SearchService.search(...)
        1. QueryService      common query representation (intent, filters, keywords)
        2. retrieval         candidates C(q):
             - structured filters in PostgreSQL (category tree, price, gender,
               colour, material, pattern, stock) + pg_trgm fuzzy score
             - BM25 keyword score (TextIndex)
             - semantic score: multilingual CLIP text vs product photos (semantic index)
             - photo: FashionSigLIP similarity (photo index) + category vote of the
               nearest neighbours
             - conditions are never dropped: if nothing satisfies all of them the
               result is empty and the customer is told so
        3. RankingService    orders the candidates

Retrieval is done here, ranking is delegated, so the two stay separate.
"""
import time

import numpy as np

from shared.vietnamese import search_terms, strip_accents

FILTER_KEYS = ("categories", "genders", "colors", "materials", "patterns",
               "min_price", "max_price", "in_stock", "occasions")


class SearchService:

    def __init__(self, products, orders, text_index, vector_index, query_service,
                 ranking_service, image_service=None, customer_id="C001", semantic_index=None):
        self.products = products
        self.orders = orders
        self.text_index = text_index
        self.vector_index = vector_index              # photo search (FashionSigLIP)
        self.semantic_index = semantic_index          # text -> photo (multilingual CLIP)
        self.query_service = query_service
        self.ranking_service = ranking_service
        self.image_service = image_service
        self.customer_id = customer_id
        self.category_names = {c["category_id"]: c["name"] for c in products.categories()}

    # ================================================================ search
    def search(self, text=None, modality="text", embedding=None, image=None, product_id=None,
               lambda_text=0.5, lambda_image=0.5, top_k=24):
        trace = []
        t0 = time.perf_counter()

        # 1. common query representation (QueryService)
        if modality == "text":
            query = self.query_service.text_query(text)
        elif modality == "voice":
            query = self.query_service.voice_query(text)
        elif modality == "image":
            query = self.query_service.image_query(embedding, image)
        elif modality == "multimodal":
            query = self.query_service.multimodal_query(text, embedding, image,
                                                        lambda_text, lambda_image)
        elif modality == "similar":
            embedding = self.vector_index.vector(product_id)
            if embedding is None:
                raise ValueError("Không tìm thấy sản phẩm.")
            query = self.query_service.image_query(embedding, image=f"sản phẩm #{product_id}")
            query.update(type="similar", similar_to=int(product_id))
        else:
            raise ValueError(f"Unknown modality: {modality}")
        how = {"rule": "luật", "clip": "ảnh"}.get(query.get("parser"), "luật + AI")
        detail = f"phân tích bằng {how}, intent = {query['intent']}"
        if query.get("llm_ms"):
            detail += f", AI {query['llm_ms']} ms"
        self._step(trace, "QueryService", "Application", detail, t0)

        response = {"query": self._public_query(query), "trace": trace}
        if query["intent"] == "order":
            t = time.perf_counter()
            response["orders"] = self.search_order(query)
            self._step(trace, "OrderRepository", "Data",
                       f"{len(response['orders'])} đơn hàng (PostgreSQL)", t)
            return self._done(response, t0)
        if query["intent"] == "unsupported":
            names = ", ".join(query["unsupported"])
            response["message"] = (f"SnapShop hiện chỉ bán áo và quần, chưa có {names}. "
                                   f"Bạn thử tìm áo hoặc quần nhé!")
            response["results"] = []
            return self._done(response, t0)

        # 2. retrieval
        t = time.perf_counter()
        candidates = self.retrieve(query, response)
        self._step(trace, "SearchService", "Application",
                   f"{len(candidates)} ứng viên C(q)", t)
        if not candidates:
            response["message"] = (f"Không tìm thấy {self._cat_label(query)} phù hợp "
                                   f"với yêu cầu của bạn.")
            response.update(results=[], candidates=0)
            return self._done(response, t0)

        # 3. ranking
        t = time.perf_counter()
        results, weights = self.ranking_service.rank(candidates, query, top_k)
        a, b, g = weights
        self._step(trace, "RankingService", "Application",
                   f"S = {a:.2f}·S_text + {b:.2f}·S_image + {g:.2f}·S_business", t)
        response.update(results=results, candidates=len(candidates), weights=weights)
        response["query"]["sort"] = query.get("sort")
        return self._done(response, t0)

    @staticmethod
    def _step(trace, component, layer, detail, t):
        trace.append({"component": component, "layer": layer, "detail": detail,
                      "ms": round((time.perf_counter() - t) * 1000, 1)})

    @staticmethod
    def _done(response, t0):
        response["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return response

    @staticmethod
    def _public_query(q):
        return {k: v for k, v in q.items() if k != "embedding"}

    # ============================================================= retrieval
    def retrieve(self, query, response):
        """Candidate set C(q) for any modality."""
        if query["type"] in ("text", "voice"):
            return self.retrieve_text(query, response)
        if query["type"] in ("image", "similar"):
            return self.retrieve_image(query, response)
        return self.retrieve_multimodal(query, response)

    # ------------------------------------------------------------- filters
    @staticmethod
    def _filters(q):
        return {k: q.get(k) for k in FILTER_KEYS}

    def _find(self, f, fuzzy_terms=None):
        return self.products.find(**f, fuzzy_terms=fuzzy_terms)

    def _cat_label(self, q):
        names = [self.category_names.get(c, c) for c in q.get("categories") or []]
        return " / ".join(names[:3]) if names else "sản phẩm"

    # ------------------------------------------------------------ semantic
    def _semantic_scores(self, q):
        """CLIP text -> photo similarity, rescaled to [0, 1] over the catalogue."""
        if self.image_service is None or self.semantic_index is None or not q.get("semantic_text"):
            return {}
        z = self.image_service.encode_text(q["semantic_text"])
        if z is None:
            return {}
        raw = self.semantic_index.scores(z)
        values = np.array(list(raw.values()))
        mid, top = np.percentile(values, 50), values.max()
        span = max(top - mid, 1e-6)
        return {pid: float(np.clip((s - mid) / span, 0, 1)) for pid, s in raw.items()}

    def _preference_bonus(self, q, pid):
        """+0.08 for each preferred fabric / pattern the product has (never removes it)."""
        prefer = q.get("prefer") or {}
        if not prefer:
            return 0.0
        p = self.products.get_product(pid)
        return 0.08 * ((p["material"] in prefer.get("materials", ()))
                       + (p["pattern"] in prefer.get("patterns", ())))

    def _text_scores(self, q, found, prune=True):
        """S_text for the products in `found` ({product_id: trigram score})."""
        scores = self._base_text_scores(q, found, prune)
        if q.get("prefer"):
            scores = {pid: min(1.0, s + self._preference_bonus(q, pid)) for pid, s in scores.items()}
        return scores

    def _base_text_scores(self, q, found, prune):
        keywords = q.get("keywords") or []
        soft = q.get("soft_keywords") or []
        sem = self._semantic_scores(q)
        ids = list(found)
        if not keywords:
            # the query is fully described by filters: every product that passed is relevant;
            # the AI's soft keywords only reorder them a little
            bm = self.text_index.score(search_terms(" ".join(soft)), ids) if soft else {}
            top = max(bm.values(), default=0.0)
            return {pid: (0.8 + 0.12 * sem.get(pid, 0.0) if sem else 0.92)
                    + (0.08 * bm.get(pid, 0.0) / top if top else 0.0) for pid in ids}
        bm25 = self.text_index.score(search_terms(" ".join(keywords)), ids)
        best = max(bm25.values(), default=0.0)
        scores = {}
        for pid in ids:
            b = bm25.get(pid, 0.0) / best if best else 0.0
            t, s = found[pid], sem.get(pid, 0.0)
            scores[pid] = (0.55 * b + 0.15 * t + 0.30 * s) if sem else (0.75 * b + 0.25 * t)
        if prune:
            if best > 0:
                scores = {pid: v for pid, v in scores.items()
                          if bm25.get(pid, 0) > 0 or found[pid] >= 0.6 or sem.get(pid, 0) >= 0.75}
            elif sem:
                keep = sorted(scores, key=scores.get, reverse=True)[:48]
                scores = {pid: scores[pid] for pid in keep}
        return scores

    # ------------------------------------------------------------------ text
    def retrieve_text(self, q, response):
        if q["intent"] == "unknown" and not any(self._filters(q).values()) and not q["keywords"]:
            response["message"] = ("Mình chưa hiểu rõ bạn cần gì. Đây là các sản phẩm nổi bật, "
                                   "bạn thử mô tả thêm loại áo/quần, màu hoặc mức giá nhé.")
            return [{"product": p, "s_text": 0.0, "s_image": 0.0}
                    for p in self.browse(size=24)["products"]]
        fuzzy = [strip_accents(k) for k in q["keywords"] if " " not in k][:6]
        found = self._find(self._filters(q), fuzzy)
        scores = self._text_scores(q, found)
        return [{"product": self.products.get_product(pid), "s_text": s, "s_image": 0.0}
                for pid, s in scores.items()]

    # ----------------------------------------------------------------- image
    def _image_scores(self, embedding, allowed=None, exclude=None, boost=0.02):
        """Cosine similarity for the allowed products, plus a small bonus for the
        category most voted by the 10 nearest neighbours of the photo."""
        scores = self.vector_index.scores(embedding)
        if exclude is not None:
            scores.pop(exclude, None)
        nearest = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:15]
        top = nearest[0][1]
        votes, parents = {}, {}
        for pid, s in nearest:                       # closer neighbours vote much more
            w = float(np.exp((s - top) / 0.04))
            cat = self.products.get_product(pid)["category_id"]
            votes[cat] = votes.get(cat, 0.0) + w
            parents[cat.split("_")[0]] = parents.get(cat.split("_")[0], 0.0) + w
        total = sum(votes.values())
        cat, weight = max(votes.items(), key=lambda kv: kv[1])
        parent, pweight = max(parents.items(), key=lambda kv: kv[1])
        share = weight / total
        prediction = {"category_id": cat, "name": self.category_names.get(cat, cat),
                      "confidence": round(share, 2), "parent_id": parent,
                      "parent_name": self.category_names.get(parent, parent),
                      "parent_confidence": round(pweight / total, 2)}
        ids = scores.keys() if allowed is None else [p for p in allowed if p in scores]
        out = {}
        for pid in ids:
            bonus = boost if (share >= 0.5 and
                              self.products.get_product(pid)["category_id"] == cat) else 0.0
            out[pid] = min(1.0, max(0.0, scores[pid] + bonus))
        return out, prediction

    def retrieve_image(self, q, response):
        scores, prediction = self._image_scores(q["embedding"], exclude=q.get("similar_to"),
                                                boost=0.04 if q["type"] == "similar" else 0.02)
        response["image_category"] = prediction
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best = ranked[0][1] if ranked else 0
        keep = [(pid, s) for pid, s in ranked if s >= best - 0.2][:60]
        return [{"product": self.products.get_product(pid), "s_text": 0.0, "s_image": s}
                for pid, s in keep]

    # ------------------------------------------------------------ multimodal
    def retrieve_multimodal(self, q, response):
        """Photo + text: the text filters ("màu đen", "dưới 500k") restrict the
        candidates, the photo decides which ones look alike. "Giống cái này nhưng
        màu đen" means the same KIND of garment, so when the text names no
        category, the category recognised in the photo becomes a filter too."""
        _, prediction = self._image_scores(q["embedding"])
        response["image_category"] = prediction
        if not q["categories"]:
            if prediction["confidence"] >= 0.55:          # sure about the exact kind
                cat, name = prediction["category_id"], prediction["name"]
            elif prediction["parent_confidence"] >= 0.7:  # at least sure it is a top / trousers
                cat, name = prediction["parent_id"], prediction["parent_name"]
            else:
                cat = None
            if cat:
                q["categories"] = [cat]
                q["understood"].append({"kind": "category", "label": f"{name} (từ ảnh)",
                                        "value": cat, "source": "image"})
        fuzzy = [strip_accents(k) for k in q["keywords"] if " " not in k][:6]
        found = self._find(self._filters(q), fuzzy)
        text_scores = self._text_scores(q, found, prune=False)
        image_scores, _ = self._image_scores(q["embedding"], allowed=found)
        lt, li = q["weights"]["text"], q["weights"]["image"]
        combined = sorted(found, key=lambda pid: lt * text_scores.get(pid, 0)
                          + li * image_scores.get(pid, 0), reverse=True)[:60]
        return [{"product": self.products.get_product(pid), "s_text": text_scores.get(pid, 0.0),
                 "s_image": image_scores.get(pid, 0.0)} for pid in combined]

    # ================================================================ orders
    def search_order(self, query):
        if query.get("order_id"):
            orders = [self.orders.find_order(query["order_id"])]
        elif query.get("all_orders"):
            orders = self.orders.orders_of_customer(self.customer_id)
        else:
            orders = [self.orders.latest_order(self.customer_id)]
        result = []
        for o in orders:
            if o is None:
                continue
            result.append({**o, "items": self.orders.items_of(o["order_id"]),
                           "payments": self.orders.payments_of(o["order_id"]),
                           "mine": o["customer_id"] == self.customer_id})
        return result

    # ======================================================== shop browsing
    def browse(self, category=None, gender=None, sort="popular", page=1, size=24):
        """Catalogue listing for the shop pages (no ranking needed)."""
        found = self.products.find(categories=[category] if category else None,
                                   genders=[gender] if gender else None)
        items = [self.products.get_product(pid) for pid in found]
        key = {"popular": lambda p: -p["popularity"], "price_asc": lambda p: p["price"],
               "price_desc": lambda p: -p["price"],
               "newest": lambda p: -p["created_at"].timestamp()}.get(sort, lambda p: -p["popularity"])
        items.sort(key=key)
        start = (page - 1) * size
        return {"products": items[start:start + size], "total": len(items)}

    def product(self, product_id):
        return self.products.get_product(product_id)

    def categories(self):
        return self.products.categories()

    def image_file(self, product_id):
        product = self.products.get_product(product_id)
        return self.products.image_path(product) if product else None

    def customer(self):
        return self.orders.customer(self.customer_id)
