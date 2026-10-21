"""Presentation Layer - WebSearchUI (FastAPI web shop "SnapShop").

The web version of SearchUI. It plays the same role in the architecture as
the console SearchUI and talks to the same three Application components:

    browser -> WebSearchUI -> SpeechService   (recorded voice -> text)
                           -> ImageService    (photo -> CLIP vector)
                           -> SearchService   (query, retrieval, ranking, orders)

Nothing in this file imports from the data package. Product photos are
served through SearchService.image_file().

Run: python main.py   then open http://127.0.0.1:8000   (API docs: /docs)
"""
import json
import os
import time
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from presentation.search_ui import ImageUpload, VoiceInput

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_IMAGES = ImageUpload.ALLOWED
EXAMPLES = [
    "áo phông dưới 100k", "áo khoác trên 2 triệu", "quần jeans nam tầm 500-800 nghìn",
    "ao so mi trang tay dai", "cho tui coi mấy cái quần đùi hông quá 300 ngàn",
    "áo len cổ lọ màu be", "đồ đi làm cho nữ", "hoodie đen rẻ nhất", "đơn hàng gần nhất của tôi",
]


# ------------------------------------------------------------ API schemas
class ProductOut(BaseModel):
    id: int
    name: str
    model: str
    brand: str
    category_id: str
    category_name: str
    gender: str
    price: int
    stock: int
    color: Optional[str]
    color_detail: Optional[str]
    material: Optional[str]
    pattern: Optional[str]
    description: Optional[str]
    description_en: Optional[str]
    image_url: str
    source_url: Optional[str]
    popularity: float


class ResultOut(ProductOut):
    rank: int
    s_text: float
    s_image: float
    s_business: float
    score: float
    parts: dict


class SearchResponse(BaseModel):
    mode: str
    input: dict
    query: dict
    trace: List[dict]
    results: Optional[List[ResultOut]] = None
    orders: Optional[List[dict]] = None
    weights: Optional[dict] = None
    candidates: Optional[int] = None
    message: Optional[str] = None
    image_category: Optional[dict] = None
    total_ms: float


class BrowseResponse(BaseModel):
    products: List[ProductOut]
    total: int


# ------------------------------------------------------------ the UI class
class WebSearchUI:
    """Turns HTTP requests into calls to the Application layer."""

    def __init__(self, speech_service, image_service, search_service):
        self.speech_service = speech_service
        self.image_service = image_service
        self.search_service = search_service
        self.voice_input = VoiceInput()
        self.image_upload = ImageUpload()

    @staticmethod
    def product_json(p):
        model = (p.get("description_en") or "").split(":")[0].strip().title()
        return {
            "id": p["product_id"], "name": p["name"], "model": model, "brand": p["brand"],
            "category_id": p["category_id"], "category_name": p["category_name"],
            "gender": p["gender"], "price": p["price"], "stock": p["stock"],
            "color": p["color"], "color_detail": p["color_detail"], "material": p["material"],
            "pattern": p["pattern"], "description": p["description"],
            "description_en": p["description_en"], "image_url": f"/product-image/{p['product_id']}",
            "source_url": p["source_url"], "popularity": float(p["popularity"]),
        }

    @classmethod
    def _result_json(cls, rank, r):
        return {**cls.product_json(r["product"]), "rank": rank,
                "s_text": round(r["s_text"], 3), "s_image": round(r["s_image"], 3),
                "s_business": round(r["s_business"], 3), "score": round(r["score"], 3),
                "parts": {k: round(v, 4) for k, v in r["parts"].items()}}

    @staticmethod
    def _order_json(o):
        return {
            "order_id": o["order_id"], "date": o["order_date"].strftime("%d/%m/%Y %H:%M"),
            "status": o["status"], "total": o["total_amount"], "address": o["shipping_address"],
            "mine": o["mine"],
            "items": [{"product_id": i["product_id"], "name": i["name"], "color": i["color"],
                       "quantity": i["quantity"], "unit_price": i["unit_price"],
                       "image_url": f"/product-image/{i['product_id']}"} for i in o["items"]],
            "payments": [{"method": p["payment_method"], "status": p["status"],
                          "amount": p["amount"]} for p in o["payments"]],
        }

    def _encode_photo(self, data, filename):
        ext = os.path.splitext(filename or "")[1].lower() or ".jpg"
        if ext not in ALLOWED_IMAGES:
            raise ValueError("Chỉ hỗ trợ ảnh PNG, JPG, WEBP hoặc BMP.")
        if len(data) > ImageUpload.MAX_BYTES:
            raise ValueError("Ảnh lớn hơn 10 MB.")
        try:
            return self.image_service.encode(data)
        except Exception:
            raise ValueError("Không đọc được ảnh, bạn thử ảnh khác nhé.")

    def search(self, mode, text=None, image=None, sample_path=None, product_id=None,
               audio=None, engine="browser"):
        """image = (bytes, filename); audio = (bytes, mime type)."""
        trace, shown_input = [], {"text": text}
        text = (text or "").strip()

        if mode == "voice":
            t = time.perf_counter()
            if audio:                                          # real recording -> Gemini
                result = self.speech_service.transcribe(audio[0], audio[1])
            elif text:                                         # browser recogniser / typed
                result = self.speech_service.transcribe(self.voice_input.capture(text)[0],
                                                        engine=engine)
            else:
                raise ValueError("Mình chưa nghe thấy gì, bạn thử nói lại nhé.")
            text = result["text"]
            shown_input.update(transcript=result["transcript"], normalized=result["text"],
                               dialect=result["dialect"], engine=result["engine"])
            trace.append({"component": "SpeechService", "layer": "Application",
                          "detail": f'chép lời: "{result["transcript"]}"',
                          "ms": round((time.perf_counter() - t) * 1000, 1)})

        embedding, image_name = None, None
        if mode in ("image", "multimodal"):
            t = time.perf_counter()
            if image:
                embedding, image_name = self._encode_photo(*image), image[1]
            elif sample_path:
                self.image_upload.upload(sample_path)
                embedding, image_name = self.image_service.encode(sample_path), \
                    os.path.basename(sample_path)
            else:
                raise ValueError("Bạn chọn hoặc kéo thả một ảnh vào nhé.")
            shown_input["image"] = image_name
            trace.append({"component": "ImageService", "layer": "Application",
                          "detail": f"encode({image_name}) → vector {len(embedding)} chiều",
                          "ms": round((time.perf_counter() - t) * 1000, 1)})
            if mode == "multimodal" and not text:
                mode = "image"
        if mode in ("text", "voice") and not text:
            raise ValueError("Bạn muốn tìm gì? Gõ vài chữ nhé.")

        response = self.search_service.search(
            text=text or None, modality=mode, embedding=embedding, image=image_name,
            product_id=product_id, top_k=48)
        response["trace"] = trace + response["trace"]
        out = {"mode": mode, "input": shown_input, "query": self._clean(response["query"]),
               "trace": response["trace"],
               "message": response.get("message"),
               "image_category": response.get("image_category"),
               "total_ms": round(response["total_ms"] + sum(
                   s["ms"] for s in trace), 1)}
        if "orders" in response:
            out["orders"] = [self._order_json(o) for o in response["orders"]]
        else:
            out["results"] = [self._result_json(i + 1, r)
                              for i, r in enumerate(response.get("results", []))]
            if response.get("weights"):
                a, b, g = response["weights"]
                out["weights"] = {"text": a, "image": b, "business": g}
            out["candidates"] = response.get("candidates")
        return out

    @staticmethod
    def _clean(query):
        keep = ("type", "query", "normalized", "intent", "categories", "genders", "colors",
                "materials", "patterns", "features", "occasions", "min_price", "max_price",
                "sort", "in_stock", "keywords", "unknown", "understood", "parser", "confidence",
                "parse_ms", "llm_name", "llm_ms", "llm_error", "llm_skipped", "explanation",
                "semantic_text", "similar_to", "weights", "prefer", "soft_keywords")
        return {k: query.get(k) for k in keep if query.get(k) not in (None, [], "")}


# ------------------------------------------------------------ the FastAPI app
def create_web_app(speech_service, image_service, search_service, sample_dir, evaluation=None):
    app = FastAPI(title="SnapShop API",
                  description="Multimodal search (text, voice, image) for a Vietnamese fashion "
                              "shop. Presentation layer of the three-layer architecture.",
                  version="1.0")
    app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")
    templates = Jinja2Templates(directory=os.path.join(HERE, "templates"))
    ui = WebSearchUI(speech_service, image_service, search_service)

    queries_file = os.path.join(sample_dir, "queries.json")
    samples = []
    if os.path.isfile(queries_file):
        with open(queries_file, encoding="utf-8") as f:
            samples = [q for q in json.load(f) if q["kind"] == "heldout"]
    sample_names = {s["file"] for s in samples}

    def site_config():
        cats = [dict(c) for c in search_service.categories()]
        return {"categories": cats, "examples": EXAMPLES,
                "gemini_stt": speech_service.gemini is not None,
                "stt_streaming": speech_service.streaming,
                "gemini_intent": search_service.query_service.llm is not None,
                "intent_llm": getattr(search_service.query_service.llm, "name", None),
                "customer": search_service.customer()}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html",
                                          {"config": json.dumps(site_config(), ensure_ascii=False,
                                                                default=str)})

    @app.get("/api/config", tags=["shop"])
    def api_config():
        return site_config()

    @app.get("/api/products", response_model=BrowseResponse, tags=["shop"])
    def api_products(category: Optional[str] = None, gender: Optional[str] = None,
                     sort: str = "popular", page: int = Query(1, ge=1),
                     size: int = Query(24, ge=1, le=100)):
        data = search_service.browse(category, gender, sort, page, size)
        return {"products": [ui.product_json(p) for p in data["products"]],
                "total": data["total"]}

    @app.get("/api/products/{product_id}", response_model=ProductOut, tags=["shop"])
    def api_product(product_id: int):
        p = search_service.product(product_id)
        if not p:
            raise HTTPException(404, "Không tìm thấy sản phẩm")
        return ui.product_json(p)

    @app.post("/api/search", response_model=SearchResponse, tags=["search"],
              summary="Search by text, voice, image, text + image or similar product")
    def api_search(mode: str = Form("text", description="text | voice | image | multimodal | similar"),
                   text: Optional[str] = Form(None),
                   engine: str = Form("browser", description="voice transcript source"),
                   sample: Optional[str] = Form(None),
                   product_id: Optional[int] = Form(None),
                   image: Optional[UploadFile] = File(None),
                   audio: Optional[UploadFile] = File(None)):
        if mode not in ("text", "voice", "image", "multimodal", "similar"):
            raise HTTPException(400, "Unknown search mode.")
        image_data = (image.file.read(), image.filename) if image and image.filename else None
        audio_data = (audio.file.read(), audio.content_type or "audio/wav") \
            if audio and audio.filename else None
        sample_path = os.path.join(sample_dir, sample) if sample in sample_names else None
        try:
            return ui.search(mode, text, image_data, sample_path, product_id, audio_data, engine)
        except (ValueError, FileNotFoundError) as e:
            raise HTTPException(400, str(e))

    @app.post("/api/stt/session", tags=["search"],
              summary="Temporary key + config to stream the microphone to the speech service (live captions)")
    def api_stt_session():
        try:
            return speech_service.streaming_session()
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/transcribe", tags=["search"],
              summary="Speech-to-text only (live captions while the customer is speaking)")
    def api_transcribe(audio: UploadFile = File(...)):
        try:
            result = speech_service.transcribe(audio.file.read(), audio.content_type or "audio/wav")
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"transcript": result["transcript"], "text": result["text"],
                "dialect": result["dialect"], "engine": result["engine"]}

    @app.get("/api/samples", tags=["search"])
    def api_samples():
        return [{"name": s["file"], "url": f"/sample/{s['file']}", "category_id": s["category_id"]}
                for s in samples]

    @app.get("/api/evaluation", tags=["evaluation"])
    def api_evaluation():
        if evaluation is None:
            raise HTTPException(404, "Evaluation is not available.")
        return evaluation()

    @app.get("/product-image/{product_id}", include_in_schema=False)
    def product_image(product_id: int):
        path = search_service.image_file(product_id)
        if not path or not os.path.isfile(path):
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/sample/{name}", include_in_schema=False)
    def sample_image(name: str):
        if name not in sample_names:
            raise HTTPException(404)
        return FileResponse(os.path.join(sample_dir, name))

    return app
