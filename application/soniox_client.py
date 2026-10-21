"""Application / Intelligence Layer - SonioxClient (real-time speech-to-text).

Soniox streams the transcript while the customer is still speaking: every
response carries final tokens (confirmed, sent once) and non-final tokens
(provisional, may still change). Vietnamese is supported.

* Browser (live captions): the server creates a short-lived temporary key
  (temporary_key) and the page streams 16 kHz PCM audio directly to the
  Soniox WebSocket with stream_config(); the real key never leaves the server.
* Server (recorded file, console --audio): transcribe() sends the whole file
  over the same WebSocket and returns the final text.
"""
import json
import urllib.request

API_URL = "https://api.soniox.com/v1/auth/temporary-api-key"
WS_URL = "wss://stt-rt.soniox.com/transcribe-websocket"

# vocabulary of the shop: helps the recogniser with fashion words and slang prices
TERMS = [
    "áo phông", "áo thun", "áo sơ mi", "áo polo", "áo kiểu", "áo hai dây", "áo len", "áo nỉ",
    "áo hoodie", "hoodie", "cardigan", "áo khoác", "blazer", "quần jeans", "quần jean", "quần bò",
    "quần âu", "quần tây", "quần jogger", "jogger", "quần short", "quần đùi", "legging",
    "croptop", "oversize", "form rộng", "cổ tim", "cổ lọ", "linen", "denim", "kaki",
    "trăm rưỡi", "củ", "nghìn", "ngàn", "triệu", "đơn hàng", "H&M",
]
CONTEXT = {
    "general": [{"key": "domain", "value": "Fashion e-commerce (tops and trousers)"},
                {"key": "topic", "value": "Customer searching for clothes by voice, often "
                                          "with a price limit and regional Vietnamese words"}],
    "terms": TERMS,
}


class SonioxError(Exception):
    def __init__(self, reason, cause=None):
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


class SonioxClient:

    def __init__(self, api_key, model="stt-rt-v5", timeout_s=15):
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s

    def stream_config(self, audio_format="pcm_s16le", sample_rate=16000):
        config = {"model": self.model, "audio_format": audio_format,
                  "language_hints": ["vi"], "enable_endpoint_detection": True,
                  "max_endpoint_delay_ms": 1500, "context": CONTEXT}
        if audio_format != "auto":
            config.update(sample_rate=sample_rate, num_channels=1)
        return config

    def temporary_key(self, seconds=60):
        """A key valid for one WebSocket transcription, for the browser."""
        body = json.dumps({"usage_type": "transcribe_websocket", "expires_in_seconds": seconds,
                           "single_use": True, "client_reference_id": "snapshop"}).encode()
        request = urllib.request.Request(API_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise SonioxError(self._reason(e.code), e) from e
        except Exception as e:
            raise SonioxError("Không kết nối được tới dịch vụ nhận dạng giọng nói", e) from e

    def transcribe(self, audio):
        """Final transcript of a recorded file (wav, mp3, webm... detected automatically)."""
        from websockets.sync.client import connect
        try:
            with connect(WS_URL, open_timeout=self.timeout_s, close_timeout=2,
                         additional_headers={"Authorization": f"Bearer {self.api_key}"}) as ws:
                ws.send(json.dumps(self.stream_config(audio_format="auto")))
                for i in range(0, len(audio), 32_000):
                    ws.send(audio[i:i + 32_000])
                ws.send("")                                    # end of audio
                words = []
                for message in ws:
                    m = json.loads(message)
                    if m.get("error_code"):
                        raise SonioxError(self._reason(m["error_code"]), m.get("error_message"))
                    words += [t["text"] for t in m.get("tokens", [])
                              if t.get("is_final") and not t["text"].startswith("<")]
                    if m.get("finished"):
                        break
                return "".join(words).strip()
        except SonioxError:
            raise
        except Exception as e:
            raise SonioxError("Không kết nối được tới dịch vụ nhận dạng giọng nói", e) from e

    @staticmethod
    def _reason(code):
        if code in (401, 403):
            return "Khóa truy cập dịch vụ nhận dạng giọng nói không hợp lệ"
        if code == 402:
            return "Tài khoản dịch vụ nhận dạng giọng nói hết số dư"
        if code == 429:
            return "Dịch vụ nhận dạng giọng nói đang giới hạn số yêu cầu, thử lại sau"
        return f"Dịch vụ nhận dạng giọng nói báo lỗi {code}"
