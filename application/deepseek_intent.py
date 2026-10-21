"""Application / Intelligence Layer - DeepSeekIntentParser.

Same role and same interface as GeminiIntentParser (parse(text) -> dict with
the fields of the common query representation), so QueryService can use
either one. Differences handled here:

* thinking mode is ON by default in deepseek-flash and slow -> disabled
* JSON Output only guarantees valid JSON (no schema), so every field is checked
  against the values the shop knows and anything else is dropped
* the API "may occasionally return empty content" -> one retry
* the long, unchanging instructions are in the system message so that DeepSeek's
  context cache makes them almost free after the first request
"""
import json
import time
import urllib.error
import urllib.request
from functools import lru_cache

from application import lexicon as L
from application.gemini_intent import SYSTEM

URL = "https://api.deepseek.com/chat/completions"
INTENTS = ("product", "order", "unsupported", "unknown")
SORTS = ("none", "price_asc", "price_desc", "popular", "newest")

EXAMPLE = {
    "intent": "product", "categories": ["ao_phong", "quan_short"], "genders": ["nam"],
    "colors": [], "materials": ["linen"], "patterns": [], "min_price": 0, "max_price": 500000,
    "sort": "none", "keywords": ["dáng rộng"], "order_id": "",
    "semantic_text_en": "light linen clothes for the beach",
    "explanation": "Khách nam cần đồ đi biển mát, dưới 500 nghìn.",
}


class DeepSeekError(Exception):
    def __init__(self, reason, cause=None):
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class DeepSeekIntentParser:

    name = "deepseek"

    def __init__(self, api_key, model, category_names, timeout_s=10):
        self.api_key = api_key
        self.model = model
        self.category_names = category_names
        self.timeout_s = timeout_s
        cats = "\n".join(f"- {cid}: {name}" for cid, name in category_names.items())
        self.system = (
            f"{SYSTEM}\n\nDanh mục của shop (id: tên):\n{cats}\n\n"
            f"Giá trị hợp lệ:\n- colors: {', '.join(L.COLORS)}\n"
            f"- materials: {', '.join(L.MATERIALS)}\n- patterns: {', '.join(L.PATTERNS)}\n"
            f"- genders: nam, nu\n- intent: {', '.join(INTENTS)}\n- sort: {', '.join(SORTS)}\n\n"
            f"Chỉ trả về MỘT đối tượng json đúng các khóa như ví dụ sau (không thêm chữ nào khác):\n"
            f"{json.dumps(EXAMPLE, ensure_ascii=False)}")
        self.parse = lru_cache(maxsize=512)(self._parse)      # same question -> no new call

    # ------------------------------------------------------------------ call
    def _request(self, text):
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": self.system},
                         {"role": "user", "content": f"Câu của khách: {text}"}],
            "response_format": {"type": "json_object"},
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": 500,
            "stream": False,
            "user_id": "snapshop",
        }).encode()
        request = urllib.request.Request(URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as r:
            data = json.load(r)
        return (data["choices"][0]["message"].get("content") or "").strip()

    def _parse(self, text):
        start = time.perf_counter()
        last = None
        for attempt in range(2):
            try:
                content = self._request(text)
                if content:
                    result = self._clean(json.loads(content))
                    result["llm_ms"] = round((time.perf_counter() - start) * 1000)
                    return result
                last = DeepSeekError("Dịch vụ AI trả về nội dung rỗng")
            except urllib.error.HTTPError as e:
                last = DeepSeekError(self._reason(e.code), e)
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except (json.JSONDecodeError, KeyError) as e:
                last = DeepSeekError("Dịch vụ AI trả về dữ liệu không đọc được", e)
            except Exception as e:                    # timeout, network
                last = DeepSeekError("Không kết nối được tới dịch vụ AI", e)
            if attempt == 0:
                time.sleep(0.5)
        raise last

    @staticmethod
    def _reason(code):
        return {401: "Khóa truy cập dịch vụ AI không hợp lệ",
                402: "Tài khoản dịch vụ AI hết số dư",
                429: "Dịch vụ AI đang giới hạn số yêu cầu"}.get(code, f"Dịch vụ AI báo lỗi {code}")

    # -------------------------------------------------------------- validate
    def _clean(self, r):
        def pick(key, allowed):
            values = r.get(key) or []
            if isinstance(values, str):
                values = [values]
            return [v for v in dict.fromkeys(values) if v in allowed]

        def price(key):
            try:
                v = int(float(r.get(key) or 0))
            except (TypeError, ValueError):
                return 0
            return v if 1_000 <= v <= 1_000_000_000 else 0

        keywords = r.get("keywords") or []
        return {
            "intent": r.get("intent") if r.get("intent") in INTENTS else "unknown",
            "categories": pick("categories", self.category_names)[:5],
            "genders": pick("genders", ("nam", "nu")),
            "colors": pick("colors", L.COLORS),
            "materials": pick("materials", L.MATERIALS),
            "patterns": pick("patterns", L.PATTERNS),
            "min_price": price("min_price"),
            "max_price": price("max_price"),
            "sort": r.get("sort") if r.get("sort") in SORTS else "none",
            "keywords": [str(k) for k in keywords if isinstance(k, (str, int))][:8],
            "order_id": str(r.get("order_id") or ""),
            "semantic_text_en": str(r.get("semantic_text_en") or ""),
            "explanation": str(r.get("explanation") or ""),
        }
