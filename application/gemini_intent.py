"""Application / Intelligence Layer - GeminiIntentParser.

Called by QueryService ONLY when the rule parser is not confident
(e.g. "đồ mặc đi biển", "quà sinh nhật cho bạn trai thích thể thao").
Gemini returns the same fields as the rule parser, restricted to the
values that exist in the shop (enum in the JSON schema).
"""
import time
from functools import lru_cache

from application import lexicon as L

SYSTEM = """Bạn là bộ phân tích ý định tìm kiếm cho SnapShop, một shop thời trang ở Việt Nam
chỉ bán ÁO và QUẦN (thương hiệu H&M). Đọc câu của khách (có thể không dấu, viết tắt, tiếng
lóng, từ địa phương Bắc/Trung/Nam) và trả về JSON theo schema.

Quy tắc:
- intent: "product" (tìm áo/quần), "order" (hỏi đơn hàng), "unsupported" (hỏi mặt hàng shop
  không bán: váy, giày, túi, phụ kiện...), "unknown" (không liên quan đến mua sắm).
- categories: chọn trong danh sách id. Nếu khách nói chung chung ("áo", "quần") dùng "ao" hoặc
  "quan". Nếu khách nói nhu cầu/dịp (đi biển, đi làm, trời lạnh, tập gym, quà tặng...), hãy suy
  ra các loại phù hợp nhất (tối đa 5).
- genders: "nam"/"nu" nếu suy ra được (bạn trai, chồng, bố -> nam; bạn gái, vợ, mẹ -> nu).
- Giá đổi ra VND: 100k = 100000, 2 triệu/2 củ/2tr = 2000000, 1 lít = 100000, "tầm X" ->
  min = 0.8X, max = 1.2X. Không nói giá thì để 0.
- sort: "price_asc" (rẻ), "price_desc" (đắt, cao cấp), "popular" (bán chạy), "newest" (mới),
  "none".
- keywords: vài từ tiếng Việt mô tả kiểu dáng/chi tiết (vd "dáng rộng", "cổ tim", "dài tay").
- semantic_text_en: một cụm tiếng Anh ngắn mô tả món đồ khách muốn (để tìm ảnh bằng CLIP),
  ví dụ "light linen shirt for the beach".
- explanation: một câu tiếng Việt ngắn giải thích bạn hiểu khách cần gì.
Chỉ dùng các giá trị có trong schema, không bịa thêm."""


def build_schema(category_ids):
    enum = lambda values: {"type": "array", "items": {"type": "string", "enum": list(values)}}
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": ["product", "order", "unsupported", "unknown"]},
            "categories": enum(category_ids),
            "genders": enum(["nam", "nu"]),
            "colors": enum(L.COLORS.keys()),
            "materials": enum(L.MATERIALS.keys()),
            "patterns": enum(L.PATTERNS.keys()),
            "min_price": {"type": "integer"},
            "max_price": {"type": "integer"},
            "sort": {"type": "string",
                     "enum": ["none", "price_asc", "price_desc", "popular", "newest"]},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "order_id": {"type": "string"},
            "semantic_text_en": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": ["intent", "categories", "genders", "colors", "materials", "patterns",
                     "min_price", "max_price", "sort", "keywords", "semantic_text_en",
                     "explanation"],
    }


class GeminiIntentParser:

    name = "gemini"

    def __init__(self, client, model, category_names):
        self.client = client
        self.model = model
        self.category_names = category_names
        self.schema = build_schema(category_names.keys())
        self.parse = lru_cache(maxsize=512)(self._parse)      # same question -> no new call

    def _parse(self, text):
        start = time.perf_counter()
        cats = "\n".join(f"- {cid}: {name}" for cid, name in self.category_names.items())
        prompt = f"Danh mục của shop (id: tên):\n{cats}\n\nCâu của khách: {text}"
        result = self.client.generate_json(self.model, [prompt], self.schema, system=SYSTEM)
        result["llm_ms"] = round((time.perf_counter() - start) * 1000)
        return result
