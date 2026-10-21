"""Settings, read from environment variables or from the .env file."""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load_env_file(path=os.path.join(ROOT, ".env")):
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env_file()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/snapshop")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
# comma-separated: the first model is used, the next ones when it is overloaded / out of quota
GEMINI_INTENT_MODEL = os.getenv("GEMINI_INTENT_MODEL", "gemini-3.5-flash-lite,gemini-3.6-flash")
GEMINI_STT_MODEL = os.getenv("GEMINI_STT_MODEL",
                             "gemini-3.5-flash-lite,gemini-3.6-flash,gemini-3.8-flash")
GEMINI_TIMEOUT = float(os.getenv("GEMINI_TIMEOUT", "10"))

# Soniox real-time speech-to-text (used for voice instead of Gemini when the key is set)
SONIOX_API_KEY = os.getenv("SONIOX_API_KEY", "")
SONIOX_MODEL = os.getenv("SONIOX_MODEL", "stt-rt-v5")

# photo search (image -> image): fashion-specific model
PHOTO_MODEL = os.getenv("PHOTO_MODEL", "hf-hub:Marqo/marqo-fashionSigLIP")
# semantic text search (Vietnamese sentence -> product photos): multilingual CLIP
CLIP_IMAGE_MODEL = os.getenv("CLIP_IMAGE_MODEL", "clip-ViT-B-32")
CLIP_TEXT_MODEL = os.getenv("CLIP_TEXT_MODEL",
                            "sentence-transformers/clip-ViT-B-32-multilingual-v1")

DATA_DIR = os.path.join(ROOT, "data")
QUERY_IMAGE_DIR = os.path.join(DATA_DIR, "query_images")
PHOTO_INDEX_FILE = os.path.join(DATA_DIR, "catalog", "photo_vectors.npz")
SEMANTIC_INDEX_FILE = os.path.join(DATA_DIR, "catalog", "semantic_vectors.npz")

CURRENT_CUSTOMER = os.getenv("CURRENT_CUSTOMER", "C001")   # the logged-in customer

# DeepSeek (alternative LLM for hard queries)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
