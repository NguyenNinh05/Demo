import time

PROMPT = """Bạn là hệ thống nhận dạng giọng nói tiếng Việt cho một shop quần áo.
Nghe đoạn ghi âm và trả về JSON:
- transcript: chép lại chính xác lời người nói, có dấu, giữ nguyên từ địa phương.
- normalized: viết lại câu đó bằng tiếng Việt phổ thông (vd "hông" -> "không", "mắc" -> "đắt",
  "tui" -> "tôi", "mô" -> "nào", "răng" -> "sao", "chi" -> "gì", "rứa" -> "vậy"); giữ nguyên
  tên sản phẩm, màu sắc; viết số tiền bằng chữ số kèm đơn vị (vd "trăm rưỡi" -> "150 nghìn",
  "một triệu rưỡi" -> "1,5 triệu", "hai trăm ngàn" -> "200 nghìn").
- dialect: "Bắc", "Trung", "Nam" hoặc "không rõ".
Nếu không nghe rõ hoặc chỉ có tiếng ồn, để transcript và normalized rỗng. Không bịa nội dung."""

SCHEMA = {
    "type": "object",
    "properties": {
        "transcript": {"type": "string"},
        "normalized": {"type": "string"},
        "dialect": {"type": "string", "enum": ["Bắc", "Trung", "Nam", "không rõ"]},
    },
    "required": ["transcript", "normalized", "dialect"],
}


class SpeechService:

    def __init__(self, gemini=None, model=None, soniox=None):
        self.gemini = gemini
        self.model = model
        self.soniox = soniox

    @property
    def available(self):
        return self.gemini is not None or self.soniox is not None

    @property
    def streaming(self):
        return self.soniox is not None

    def streaming_session(self):
        """Temporary key + configuration for streaming from the browser (Soniox)."""
        if self.soniox is None:
            raise ValueError("Chưa bật nhận dạng giọng nói realtime.")
        from application.soniox_client import WS_URL
        try:
            key = self.soniox.temporary_key()
        except Exception as e:
            raise ValueError(f"Không mở được phiên nhận dạng: {getattr(e, 'reason', e)}.") from e
        return {"provider": "soniox", "url": WS_URL, "api_key": key["api_key"],
                "expires_at": key.get("expires_at"), "config": self.soniox.stream_config()}

    def _soniox_file(self, audio, start):
        text = self.soniox.transcribe(audio)
        if not text:
            raise ValueError("Mình chưa nghe rõ, bạn nói lại giúp nhé.")
        return {"text": text, "transcript": text, "dialect": None, "engine": "soniox",
                "ms": round((time.perf_counter() - start) * 1000)}

    def transcribe(self, audio, mime_type="audio/wav", engine="simulated"):
        """audio: recorded bytes (Gemini) or an already transcribed str."""
        start = time.perf_counter()
        if isinstance(audio, str):
            text = " ".join(audio.strip().split())
            return {"text": text, "transcript": text, "dialect": None, "engine": engine,
                    "ms": 0}
        if not self.available:
            raise ValueError("Chưa bật nhận dạng giọng nói cho file ghi âm.")
        if self.soniox is not None:
            try:
                return self._soniox_file(audio, start)
            except ValueError:
                raise
            except Exception as e:
                if self.gemini is None:
                    raise ValueError(f"Chưa nhận dạng được giọng nói: {getattr(e, 'reason', e)}.") \
                        from e                    
        try:
            result = self.gemini.generate_json(
                self.model, [PROMPT, self.gemini.audio(audio, mime_type)], SCHEMA)
        except Exception as e:                     
            reason = getattr(e, "reason", "không kết nối được tới dịch vụ nhận dạng")
            raise ValueError(f"Chưa nhận dạng được giọng nói: {reason}. "
                             f"Bạn thử lại hoặc gõ câu tìm kiếm nhé.") from e
        text = (result.get("normalized") or result.get("transcript") or "").strip()
        if not text:
            raise ValueError("Mình chưa nghe rõ, bạn nói lại giúp nhé.")
        return {"text": text, "transcript": result.get("transcript", ""),
                "dialect": result.get("dialect"), "engine": self.gemini.last_model or "gemini",
                "ms": round((time.perf_counter() - start) * 1000)}
