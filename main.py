"""
SnapShop - Multimodal Search System for E-Commerce (Vietnamese)
Composition root: wires the three layers together.

Usage
    python main.py --init-db                       # create the PostgreSQL database + sample data
    python main.py --build-index                   # (re)compute the CLIP vectors of the photos
    python main.py                                 # web shop on http://127.0.0.1:8000
    python main.py --text "áo phông dưới 100k"
    python main.py --voice "cho tui coi quần đùi hông quá trăm rưỡi"   # typed transcript
    python main.py --audio recording.wav           # real speech-to-text (Gemini)
    python main.py --image data/query_images/heldout_01_ao_phong.jpg
    python main.py --text "giống cái này nhưng màu đen" --image photo.jpg
    python main.py --evaluate                      # run the test set
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import config  # noqa: E402
# Data layer
from data.db import Database  # noqa: E402
from data.order_repository import OrderRepository  # noqa: E402
from data.product_repository import ProductRepository  # noqa: E402
from data.text_index import TextIndex  # noqa: E402
from data.vector_index import VectorIndex  # noqa: E402
# Application / Intelligence layer
from application.gemini_client import GeminiClient  # noqa: E402
from application.deepseek_intent import DeepSeekIntentParser  # noqa: E402
from application.gemini_intent import GeminiIntentParser  # noqa: E402
from application.image_service import ImageService  # noqa: E402
from application.query_service import QueryService  # noqa: E402
from application.ranking_service import RankingService  # noqa: E402
from application.rule_parser import RuleParser  # noqa: E402
from application.search_service import SearchService  # noqa: E402
from application.soniox_client import SonioxClient  # noqa: E402
from application.speech_service import SpeechService  # noqa: E402


def build_vector_index(repository, encode, model_name, path, rebuild=False):
    """Offline indexing: z_p = f_theta(I_p) for every product photo (cached on disk)."""
    products = repository.all_products()
    ids = [p["product_id"] for p in products]
    index = VectorIndex()
    if not rebuild and index.load(path, model_name, ids):
        return index
    print(f"Encoding {len(products)} product photos with {model_name} ...", flush=True)
    vectors = encode([repository.image_path(p) for p in products])
    index.build(ids, vectors).save(path, model_name)
    return index


def create_services(rebuild_index=False):
    """Build the Data and Application layers.
    Returns the three services the Presentation layer is allowed to use."""
    # Data layer
    db = Database(config.DATABASE_URL)
    products = ProductRepository(db)
    orders = OrderRepository(db)
    text_index = TextIndex(products.all_products())
    # Application / Intelligence layer
    image_service = ImageService(config.PHOTO_MODEL, config.CLIP_IMAGE_MODEL,
                                 config.CLIP_TEXT_MODEL)
    photo_index = build_vector_index(products, image_service.encode_many, config.PHOTO_MODEL,
                                     config.PHOTO_INDEX_FILE, rebuild_index)
    semantic_index = build_vector_index(products, image_service.encode_semantic_many,
                                        config.CLIP_IMAGE_MODEL, config.SEMANTIC_INDEX_FILE,
                                        rebuild_index)
    category_names = {c["category_id"]: c["name"] for c in products.categories()}
    gemini = GeminiClient(config.GEMINI_API_KEY, config.GEMINI_TIMEOUT) \
        if config.GEMINI_API_KEY else None
    # LLM for hard queries: DeepSeek if its key is set (faster and steadier), else Gemini
    if config.DEEPSEEK_API_KEY:
        llm = DeepSeekIntentParser(config.DEEPSEEK_API_KEY, config.DEEPSEEK_MODEL, category_names)
    elif gemini:
        llm = GeminiIntentParser(gemini, config.GEMINI_INTENT_MODEL, category_names)
    else:
        llm = None
    query_service = QueryService(
        RuleParser(vocabulary=text_index.vocabulary, category_names=category_names),
        llm, category_names)
    search_service = SearchService(products, orders, text_index, photo_index, query_service,
                                   RankingService(), image_service, config.CURRENT_CUSTOMER,
                                   semantic_index=semantic_index)
    soniox = SonioxClient(config.SONIOX_API_KEY, config.SONIOX_MODEL) \
        if config.SONIOX_API_KEY else None
    speech_service = SpeechService(gemini, config.GEMINI_STT_MODEL, soniox)
    return speech_service, image_service, search_service


def create_console_ui(verbose=True):
    from presentation.search_ui import SearchUI
    return SearchUI(*create_services(), verbose=verbose)


def run_web(port):
    import uvicorn

    from presentation.web_ui import create_web_app

    from presentation.search_ui import SearchUI
    speech_service, image_service, search_service = create_services()

    def run_test_set():
        # the evaluation drives a silent console SearchUI on the same services
        from evaluation import evaluate, summary
        return summary(*evaluate(SearchUI(speech_service, image_service, search_service,
                                          verbose=False)))

    # load the models now, not on the first search
    from PIL import Image
    image_service.encode_text("áo")
    image_service.encode(Image.new("RGB", (64, 64), "white"))
    app = create_web_app(speech_service, image_service, search_service,
                         sample_dir=config.QUERY_IMAGE_DIR, evaluation=run_test_set)
    print(f"SnapShop: http://127.0.0.1:{port}   (API docs: http://127.0.0.1:{port}/docs)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="SnapShop multimodal search")
    parser.add_argument("--init-db", action="store_true", help="create database + sample data")
    parser.add_argument("--build-index", action="store_true", help="recompute CLIP vectors")
    parser.add_argument("--text", help="text query")
    parser.add_argument("--voice", help="spoken query, already transcribed (simulated STT)")
    parser.add_argument("--audio", help="audio file for real speech-to-text (Gemini)")
    parser.add_argument("--image", help="path of a query photo")
    parser.add_argument("--evaluate", action="store_true", help="run the evaluation test set")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.init_db:
        from tools.init_db import init_database
        init_database()
        return
    if args.build_index:
        create_services(rebuild_index=True)
        print("Vector indexes rebuilt:", config.PHOTO_INDEX_FILE, config.SEMANTIC_INDEX_FILE)
        return
    if args.evaluate:
        from evaluation import run_evaluation
        run_evaluation()
        return
    if not any([args.text, args.voice, args.audio, args.image]):
        run_web(args.port)
        return

    ui = create_console_ui()
    if args.text and args.image:
        ui.multimodal_search(args.text, args.image)
    elif args.image:
        ui.image_search(args.image)
    elif args.audio:
        ui.audio_search(args.audio)
    elif args.voice:
        ui.voice_search(args.voice)
    else:
        ui.text_search(args.text)


if __name__ == "__main__":
    main()
