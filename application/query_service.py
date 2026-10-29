"""Application / Intelligence Layer - QueryService.

Converts every input modality into ONE common query representation (a dict),
so SearchService and RankingService do not care whether the customer typed,
spoke or uploaded a photo:

  {type, intent, categories, genders, colors, materials, patterns, features,
   occasions, min_price, max_price, sort, in_stock, keywords, semantic_text,
   embedding?, understood (for the UI), parser, confidence}

Text understanding = RuleParser first (about 1 ms). An LLM (DeepSeek or Gemini,
same interface) is asked only when the rules are not confident enough, and its
answer is merged into the rule result (prices found by the rules are kept,
they are exact).
"""
import time

from shared.vietnamese import strip_accents, tokenize

LIST_FIELDS = ("categories", "genders", "colors", "materials", "patterns")
# what the AI only infers about fabric / pattern ("concert rock" -> denim, print) is a
# preference for ranking, not a filter; when the customer says it, the rules make it a filter
SOFT_FIELDS = ("materials", "patterns")
SORT_LABELS = {"price_asc": "Giá thấp → cao", "price_desc": "Giá cao → thấp",
               "popular": "Bán chạy", "newest": "Mới nhất"}


def _fmt(v):
    return f"{int(v):,}".replace(",", ".") + "₫"


class QueryService:

    def __init__(self, rule_parser, llm_parser=None, category_names=None, llm_threshold=0.6):
        self.rules = rule_parser
        self.llm = llm_parser
        self.category_names = category_names or {}
        self.llm_threshold = llm_threshold
    def _understand(self, text, modality):
        query = self.rules.parse(text)
        need_llm = query["intent"] == "unknown" or query["confidence"] < self.llm_threshold
        if need_llm and self.llm is not None and query["intent"] != "order":
            try:
                query = self._merge(query, self.llm.parse(query["normalized"]))
            except Exception as e:                      # overloaded, quota, timeout...
                reason = getattr(e, "reason", "Dịch vụ AI không phản hồi")
                query["llm_error"] = f"{reason} — đang dùng kết quả của rule parser."
        elif need_llm:
            query["llm_skipped"] = "Câu khó nhưng chưa bật phân tích bằng AI."
        query["type"] = modality
        query["semantic_text"] = query.get("semantic_text") or self._semantic_text(query)
        return query

    def _merge(self, q, g):
        name = getattr(self.llm, "name", "llm")
        q = dict(q, understood=list(q["understood"]), parser=f"rule+{name}", llm_name=name,
                 llm_ms=g.get("llm_ms"), explanation=g.get("explanation"))
        if g["intent"] == "order" and q["intent"] != "product":
            q.update(intent="order", order_id=g.get("order_id") or None, latest=not g.get("order_id"),
                     label="Tra cứu đơn hàng")
            return q
        if g["intent"] in ("unsupported", "unknown") and not q["categories"]:
            q["intent"] = g["intent"]
        elif g["intent"] == "product":
            q["intent"] = "product"
        for field in LIST_FIELDS:
            if q[field] or not g.get(field):
                continue
            if field in SOFT_FIELDS:
                q.setdefault("prefer", {})[field] = list(g[field])
                for v in g[field]:
                    q["understood"].append({"kind": "prefer", "source": "llm",
                                            "label": f"Ưu tiên {self._label(field, v).lower()}"})
                continue
            q[field] = list(g[field])
            for v in g[field]:
                q["understood"].append({"kind": field[:-1] if field != "categories" else "category",
                                        "label": self._label(field, v), "source": "llm"})
        if q["min_price"] is None and g.get("min_price"):
            q["min_price"] = g["min_price"]
        if q["max_price"] is None and g.get("max_price"):
            q["max_price"] = g["max_price"]
        if (g.get("min_price") or g.get("max_price")) and not any(
                u["kind"] == "price" for u in q["understood"]):
            lo, hi = q["min_price"], q["max_price"]
            label = (f"Giá {_fmt(lo)} – {_fmt(hi)}" if lo and hi else
                     f"Trên {_fmt(lo)}" if lo else f"Dưới {_fmt(hi)}")
            q["understood"].append({"kind": "price", "label": label, "source": "llm"})
        if not q["sort"] and g.get("sort") not in (None, "none"):
            q["sort"] = g["sort"]
            q["understood"].append({"kind": "sort", "label": SORT_LABELS[g["sort"]],
                                    "source": "llm"})
        soft = q.setdefault("soft_keywords", [])
        for kw in g.get("keywords", []):
            for w in tokenize(kw):
                u = strip_accents(w)
                if u.isalpha() and u not in q["keywords"] and u not in soft:
                    soft.append(u)
        if g.get("semantic_text_en"):
            q["semantic_text"] = g["semantic_text_en"]
        q["confidence"] = max(q["confidence"], 0.8)
        return q

    def _label(self, field, value):
        if field == "categories":
            return self.category_names.get(value, value)
        if field == "genders":
            return "Nam" if value == "nam" else "Nữ"
        if field == "patterns":
            return value.capitalize()
        prefix = {"colors": "Màu", "materials": "Chất"}[field]
        return f"{prefix} {value}"

    def _semantic_text(self, q):
        """Short Vietnamese description used by the CLIP text encoder."""
        prefer = q.get("prefer", {})
        parts = [self.category_names.get(c, "") for c in q["categories"][:3]]
        parts += q["colors"][:2] + q["materials"] + q["patterns"] + q["features"]
        parts += prefer.get("materials", []) + prefer.get("patterns", [])
        parts += [w for w in q["keywords"] if w not in q["features"]]
        parts += q.get("soft_keywords", [])[:4]
        parts += q["occasions"]
        if q["genders"]:
            parts.append("nam" if q["genders"] == ["nam"] else "nữ")
        text = " ".join(p for p in parts if p).strip()
        if text:
            return text
        # nothing descriptive was understood: use the raw sentence only if it has
        # words the rules did not know ("đồ đi biển"), not for "dưới 500k"
        return q["query"] if q.get("unknown") else ""

    # ------------------------------------------------ one method per modality
    def text_query(self, text):
        return self._understand(text, "text")

    def voice_query(self, text):
        return self._understand(text, "voice")

    def image_query(self, embedding, image=None):
        return {"type": "image", "intent": "product", "embedding": embedding, "image": image,
                "categories": [], "genders": [], "colors": [], "materials": [], "patterns": [],
                "brands": [], "features": [], "occasions": [], "keywords": [],
                "min_price": None, "max_price": None, "sort": None, "in_stock": False,
                "understood": [], "parser": "clip", "confidence": 1.0, "semantic_text": ""}

    def multimodal_query(self, text, embedding, image=None, lambda_text=0.5, lambda_image=0.5):
        """Text + photo: the text gives filters/keywords, the photo gives the look.
        lambda_t + lambda_i = 1."""
        query = self._understand(text, "multimodal")
        if query["intent"] in ("unknown", "unsupported"):
            query["intent"] = "product"             # "giống cái này" alone is still a search
        total = lambda_text + lambda_image
        query.update({"embedding": embedding, "image": image,
                      "weights": {"text": lambda_text / total, "image": lambda_image / total}})
        return query
