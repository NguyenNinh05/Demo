"""Presentation Layer - console SearchUI, VoiceInput, ImageUpload, SearchResultView.

This layer only collects input and displays results. SearchUI calls only
three Application components (see the component diagram):

    SearchUI -> SpeechService   (audio -> text)
    SearchUI -> ImageService    (photo -> vector)
    SearchUI -> SearchService   (query, retrieval and ranking)

It NEVER imports anything from the data package.
"""
import mimetypes
import os


class VoiceInput:
    """Microphone component: reads a recording, or takes a typed transcript (simulated)."""

    def capture(self, source):
        if os.path.isfile(source):
            with open(source, "rb") as f:
                return f.read(), mimetypes.guess_type(source)[0] or "audio/wav"
        return source, None


class ImageUpload:
    """Image upload component: validates the uploaded file."""

    ALLOWED = (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    MAX_BYTES = 10 * 1024 * 1024

    def upload(self, path):
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Không tìm thấy ảnh: {path}")
        if not path.lower().endswith(self.ALLOWED):
            raise ValueError("Chỉ hỗ trợ ảnh PNG, JPG, WEBP hoặc BMP.")
        if os.path.getsize(path) > self.MAX_BYTES:
            raise ValueError("Ảnh lớn hơn 10 MB.")
        return path


def vnd(v):
    return f"{int(v):,}".replace(",", ".") + "₫"


class SearchResultView:
    """Console view: input, understood intent, processing steps and ranked results."""

    LINE = "-" * 104

    def show_header(self, title, user_input):
        print("\n" + "=" * 104)
        print(f" {title}")
        print("=" * 104)
        print(f" INPUT      : {user_input}")

    def show_step(self, text):
        print(f" PROCESSING : {text}")

    def show_understood(self, query):
        chips = [u["label"] for u in query.get("understood", []) if u.get("label")]
        if chips:
            print(f" HIỂU LÀ    : {' · '.join(chips)}")
        if query.get("explanation"):
            print(f" AI HIỂU LÀ : {query['explanation']}")

    def show_response(self, response):
        for step in response["trace"]:
            print(f" PROCESSING : {step['component']:<16} [{step['layer']:<12}] "
                  f"{step['detail']}  ({step['ms']} ms)")
        for r in response.get("relaxed", []):
            print(f" NỚI ĐK     : {r['message']}")
        if response.get("message"):
            print(f" THÔNG BÁO  : {response['message']}")
        if response.get("image_category"):
            c = response["image_category"]
            print(f" ẢNH LÀ     : {c['name']} ({c['confidence']:.0%})")
        if "orders" in response:
            self.show_orders(response["orders"])
        elif response.get("results") is not None:
            self.show_products(response["results"], response.get("weights"))
        print(f" Tổng thời gian: {response['total_ms']} ms")

    def show_products(self, results, weights):
        if weights:
            a, b, g = weights
            print(f" RANKING    : S = {a:.2f}*S_text + {b:.2f}*S_image + {g:.2f}*S_business")
        print(self.LINE)
        if not results:
            print(" Không có sản phẩm phù hợp.")
            print(self.LINE)
            return
        print(f" {'#':<3}{'Sản phẩm':<40}{'Màu':<11}{'Giá':>11}{'Kho':>5}"
              f"{'S_text':>8}{'S_img':>7}{'S_bus':>7}{'SCORE':>8}")
        print(self.LINE)
        for i, r in enumerate(results[:10], 1):
            p = r["product"]
            stock = p["stock"] if p["stock"] > 0 else "hết"
            print(f" {i:<3}{p['name'][:38]:<40}{p['color'][:10]:<11}{vnd(p['price']):>11}"
                  f"{stock!s:>5}{r['s_text']:>8.3f}{r['s_image']:>7.3f}{r['s_business']:>7.3f}"
                  f"{r['score']:>8.3f}")
        print(self.LINE)

    def show_orders(self, orders):
        print(self.LINE)
        if not orders:
            print(" Không tìm thấy đơn hàng.")
        for o in orders:
            print(f" Đơn {o['order_id']}  ·  {o['order_date']:%d/%m/%Y %H:%M}  ·  {o['status']}"
                  f"  ·  Tổng {vnd(o['total_amount'])}")
            for item in o["items"]:
                print(f"    - {item['name']} ({item['color']}) x{item['quantity']}  "
                      f"{vnd(item['unit_price'])}")
        print(self.LINE)


class SearchUI:
    """Entry point of the console presentation layer."""

    def __init__(self, speech_service, image_service, search_service, verbose=True):
        self.speech_service = speech_service
        self.image_service = image_service
        self.search_service = search_service
        self.voice_input = VoiceInput()
        self.image_upload = ImageUpload()
        self.view = SearchResultView()
        self.verbose = verbose

    def _show(self, response):
        if self.verbose:
            self.view.show_understood(response["query"])
            self.view.show_response(response)
        return response

    def text_search(self, text):
        if self.verbose:
            self.view.show_header("TÌM BẰNG CHỮ", f'"{text}"')
        return self._show(self.search_service.search(text, modality="text"))

    def voice_search(self, transcript):
        """Voice with a typed transcript (simulated speech-to-text)."""
        if self.verbose:
            self.view.show_header("TÌM BẰNG GIỌNG NÓI (transcript nhập tay)", f'"{transcript}"')
        audio, _ = self.voice_input.capture(transcript)
        result = self.speech_service.transcribe(audio, engine="simulated")
        return self._show(self.search_service.search(result["text"], modality="voice"))

    def audio_search(self, path):
        """Voice from a recording: real speech-to-text (SpeechService)."""
        if self.verbose:
            self.view.show_header("TÌM BẰNG GIỌNG NÓI (file ghi âm)", os.path.basename(path))
        audio, mime = self.voice_input.capture(path)
        result = self.speech_service.transcribe(audio, mime)
        if self.verbose:
            self.view.show_step(f'SpeechService -> "{result["transcript"]}"  '
                                f'(chuẩn hóa: "{result["text"]}", giọng {result["dialect"]})')
        return self._show(self.search_service.search(result["text"], modality="voice"))

    def image_search(self, image_path):
        if self.verbose:
            self.view.show_header("TÌM BẰNG ẢNH", os.path.basename(image_path))
        path = self.image_upload.upload(image_path)
        embedding = self.image_service.encode(path)
        if self.verbose:
            self.view.show_step(f"ImageService.encode(ảnh) -> vector {len(embedding)} chiều")
        return self._show(self.search_service.search(
            modality="image", embedding=embedding, image=os.path.basename(path)))

    def multimodal_search(self, text, image_path, lambda_text=0.5, lambda_image=0.5):
        if self.verbose:
            self.view.show_header("TÌM BẰNG CHỮ + ẢNH",
                                  f'"{text}" + {os.path.basename(image_path)}')
        path = self.image_upload.upload(image_path)
        embedding = self.image_service.encode(path)
        return self._show(self.search_service.search(
            text, modality="multimodal", embedding=embedding, image=os.path.basename(path),
            lambda_text=lambda_text, lambda_image=lambda_image))
