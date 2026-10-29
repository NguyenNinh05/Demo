GAMMA = {"text": 0.15, "voice": 0.15, "image": 0.03, "similar": 0.03, "multimodal": 0.08}
SORT_KEYS = {
    "price_asc": lambda r: r["product"]["price"],
    "price_desc": lambda r: -r["product"]["price"],
    "popular": lambda r: -r["product"]["popularity"],
    "newest": lambda r: -r["product"]["created_at"].timestamp(),
}


class RankingService:

    def __init__(self, gamma=None):
        self.gamma = dict(GAMMA, **(gamma or {}))

    @staticmethod
    def business_score(product):
        in_stock = 1.0 if product["stock"] > 0 else 0.0
        return 0.6 * float(product["popularity"]) + 0.4 * in_stock

    def weights(self, query):
        gamma = self.gamma[query["type"]]
        relevance = 1.0 - gamma
        if query["type"] in ("text", "voice"):
            return relevance, 0.0, gamma
        if query["type"] in ("image", "similar"):
            return 0.0, relevance, gamma
        w = query.get("weights", {"text": 0.5, "image": 0.5})
        return relevance * w["text"], relevance * w["image"], gamma

    def rank(self, candidates, query, top_k=24):
        alpha, beta, gamma = self.weights(query)
        ranked = []
        for c in candidates:
            s_business = self.business_score(c["product"])
            score = alpha * c["s_text"] + beta * c["s_image"] + gamma * s_business
            ranked.append({**c, "s_business": s_business, "score": score,
                           "parts": {"text": alpha * c["s_text"], "image": beta * c["s_image"],
                                     "business": gamma * s_business}})
        ranked.sort(key=lambda r: (r["score"], r["product"]["popularity"]), reverse=True)
        sort = query.get("sort")
        if sort in SORT_KEYS and ranked:
            best = ranked[0]["score"]
            relevant = [r for r in ranked if r["score"] >= 0.6 * best]
            rest = [r for r in ranked if r["score"] < 0.6 * best]
            ranked = sorted(relevant, key=SORT_KEYS[sort]) + rest
        return ranked[:top_k], (alpha, beta, gamma)
