"""Application / Intelligence Layer - thin wrapper around the Gemini API.

Used by GeminiIntentParser (hard text queries) and SpeechService (voice).
Every answer is requested as JSON that follows a schema, so the result can
be used directly as part of the common query representation.

A model can be temporarily overloaded (503 UNAVAILABLE) or out of free quota
(429 RESOURCE_EXHAUSTED). generate_json() then retries once and moves on to
the next model of the list, so one busy model does not break the search.
"""
import json
import time

RETRY_CODES = {429, 500, 503, 504}


class GeminiError(Exception):
    """Gemini could not answer; .reason is a short Vietnamese explanation."""

    def __init__(self, reason, cause=None):
        super().__init__(reason)
        self.reason = reason
        self.cause = cause


def _reason(error):
    code = getattr(error, "code", None)
    if code == 429:
        return "Dịch vụ AI đã hết lượt miễn phí, thử lại sau ít phút"
    if code in (500, 503, 504):
        return "Dịch vụ AI đang quá tải, thử lại sau ít giây"
    if code in (400, 401, 403):
        return "Khóa truy cập dịch vụ AI không hợp lệ"
    if code == 404:
        return "Cấu hình dịch vụ AI không còn được hỗ trợ"
    return "Không kết nối được tới dịch vụ AI"


class GeminiClient:

    def __init__(self, api_key, timeout_s=10):
        from google import genai
        from google.genai import errors, types
        self._types, self._errors = types, errors
        self.client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=int(timeout_s * 1000)))
        self.last_model = None

    def _call(self, model, contents, config):
        response = self.client.models.generate_content(
            model=model, contents=contents, config=self._types.GenerateContentConfig(**config))
        return json.loads(response.text)

    def _one_model(self, model, contents, base, think=False):
        # thinking off = lower latency; a model that does not allow it gets the plain config
        configs = [base] if think else \
            [dict(base, thinking_config=self._types.ThinkingConfig(thinking_budget=0)), base]
        attempt = 0
        while True:
            try:
                return self._call(model, contents, configs[0])
            except self._errors.APIError as e:
                if e.code == 400 and len(configs) > 1:
                    configs.pop(0)
                    continue
                if e.code in RETRY_CODES and attempt == 0:
                    attempt += 1
                    time.sleep(0.8)
                    continue
                raise

    def generate_json(self, models, contents, schema, system=None, think=False):
        """models: one model name or a list tried in order. think: let the model reason
        first (slower, for offline work such as labelling the catalogue)."""
        if isinstance(models, str):
            models = [m.strip() for m in models.split(",") if m.strip()]
        base = dict(system_instruction=system, temperature=0,
                    response_mime_type="application/json", response_json_schema=schema)
        last = None
        for model in models:
            try:
                result = self._one_model(model, contents, base, think)
                self.last_model = model
                return result
            except self._errors.APIError as e:
                last = e
                if e.code not in RETRY_CODES and e.code != 404:
                    break                     # bad key etc.: another model will not help
            except Exception as e:            # timeout, network, invalid JSON
                last = e
        raise GeminiError(_reason(last), last)

    def audio(self, data, mime_type):
        return self._types.Part.from_bytes(data=data, mime_type=mime_type)

    def image(self, data, mime_type="image/jpeg"):
        return self._types.Part.from_bytes(data=data, mime_type=mime_type)
