"""
Prepare the product catalogue from the public H&M dataset (offline step).

    python tools/prepare_catalog.py --articles <articles.parquet> [--total 500]

1. Pages through the Hugging Face dataset "tomytjandra/h-and-m-fashion-caption"
   (packshot photos + caption) and joins every caption with the original H&M
   articles table, which gives name, product type, department, colour, pattern.
2. Keeps only tops (ao) and trousers (quan), maps them to the Vietnamese
   category tree and balances men / women.
3. Downloads and resizes the photos to data/catalog/images/.
4. Writes data/catalog/products.json (seed data for the database).
5. Creates query photos for the evaluation in data/query_images/:
   - heldout_*.jpg  photos of products that are NOT in the catalogue
   - aug_*.jpg      edited photos (crop, rotation, light, background) of catalogue products

The photos are used for coursework only; prices, stock and popularity are
sample values (H&M Vietnam price level).
"""
import argparse
import io
import json
import os
import random
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pyarrow.parquet as pq
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG_DIR = os.path.join(ROOT, "data", "catalog")
IMAGE_DIR = os.path.join(CATALOG_DIR, "images")
QUERY_DIR = os.path.join(ROOT, "data", "query_images")

DATASET = "tomytjandra/h-and-m-fashion-caption"
ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET_SIZE = 20491
IMAGE_SIZE = (600, 900)
BACKGROUND = (255, 255, 255)

# products per category (sum = 500); men share is applied inside each category
TARGETS = {
    "ao_phong": 60, "ao_polo": 15, "ao_so_mi": 45, "ao_kieu": 30, "ao_hai_day": 20,
    "ao_len": 35, "ao_ni": 25, "ao_hoodie": 25, "ao_cardigan": 15, "ao_khoac": 40,
    "ao_blazer": 20,
    "quan_jeans": 45, "quan_dai": 35, "quan_au": 25, "quan_jogger": 25, "quan_short": 30,
    "quan_legging": 10,
}
MEN_SHARE = 0.38
WOMEN_ONLY = {"ao_kieu", "ao_hai_day", "quan_legging"}

# price range in VND per category (H&M Vietnam level)
PRICE_RANGE = {
    "ao_phong": (99_000, 499_000), "ao_polo": (299_000, 599_000),
    "ao_so_mi": (399_000, 899_000), "ao_kieu": (299_000, 799_000),
    "ao_hai_day": (99_000, 299_000), "ao_len": (399_000, 1_299_000),
    "ao_ni": (399_000, 799_000), "ao_hoodie": (499_000, 999_000),
    "ao_cardigan": (499_000, 1_199_000), "ao_khoac": (799_000, 2_499_000),
    "ao_blazer": (999_000, 1_999_000),
    "quan_jeans": (599_000, 1_199_000), "quan_dai": (499_000, 999_000),
    "quan_au": (699_000, 1_299_000), "quan_jogger": (399_000, 799_000),
    "quan_short": (249_000, 599_000), "quan_legging": (199_000, 499_000),
}
PREMIUM_RE = re.compile(r"\b(wool|cashmere|leather|silk|premium|italian|suede|down-filled|"
                        r"down and feather|padded with down)\b")

CATEGORY_VI = {
    "ao_phong": "Áo phông", "ao_polo": "Áo polo", "ao_so_mi": "Áo sơ mi",
    "ao_kieu": "Áo kiểu", "ao_hai_day": "Áo hai dây", "ao_len": "Áo len",
    "ao_ni": "Áo nỉ", "ao_hoodie": "Áo hoodie", "ao_cardigan": "Áo cardigan",
    "ao_khoac": "Áo khoác", "ao_blazer": "Áo blazer",
    "quan_jeans": "Quần jeans", "quan_dai": "Quần dài", "quan_au": "Quần âu",
    "quan_jogger": "Quần jogger", "quan_short": "Quần short", "quan_legging": "Quần legging",
}

COLOR_VI = {
    "Black": "đen", "White": "trắng", "Beige": "be", "Grey": "xám", "Blue": "xanh dương",
    "Green": "xanh lá", "Khaki green": "xanh rêu", "Red": "đỏ", "Pink": "hồng",
    "Brown": "nâu", "Mole": "nâu", "Yellow": "vàng", "Orange": "cam",
    "Turquoise": "xanh ngọc", "Bluish Green": "xanh ngọc", "Yellowish Green": "xanh lá",
    "Yellowish Brown": "nâu", "Lilac Purple": "tím", "Metal": "bạc",
}

PATTERN_VI = {
    "Solid": "trơn", "Melange": "trơn", "Denim": "trơn", "Chambray": "trơn",
    "Treatment": "trơn", "Neps": "trơn", "Slub": "trơn", "Other structure": "trơn",
    "Stripe": "kẻ sọc", "Check": "kẻ caro", "All over pattern": "họa tiết",
    "Other pattern": "họa tiết", "Jacquard": "họa tiết", "Argyle": "họa tiết",
    "Front print": "in hình", "Placement print": "in hình", "Embroidery": "thêu",
    "Lace": "ren", "Dot": "chấm bi", "Colour blocking": "phối màu",
    "Contrast": "phối màu", "Mixed solid/pattern": "phối màu",
}

# (regex on the English description, Vietnamese material) - first match wins
MATERIALS = [
    (r"leather|suede", "da"), (r"denim", "denim"), (r"linen", "linen"),
    (r"wool|cashmere|mohair|alpaca", "len"), (r"knit", "len"),
    (r"corduroy", "nhung tăm"), (r"chiffon", "voan"), (r"satin|silk", "lụa"),
    (r"sweatshirt fabric|fleece|pile", "nỉ"),
    (r"functional fabric|fast-drying|breathable", "vải thể thao"),
    (r"cotton", "cotton"), (r"jersey", "thun"), (r"twill", "kaki"),
    (r"viscose|lyocell|modal", "viscose"),
]

# (regex, Vietnamese feature, categories prefix it applies to)
FEATURES = [
    (r"v-neck|v neck", "cổ tim", "ao"),
    (r"turtle|polo-neck|high neck|high collar|stand-up collar", "cổ lọ", "ao"),
    (r"round neck|crew neck|round neckline", "cổ tròn", "ao"),
    (r"hood", "có mũ", "ao"),
    (r"long sleeves|long-sleeved", "dài tay", "ao"),
    (r"short sleeves|short-sleeved", "ngắn tay", "ao"),
    (r"sleeveless|shoulder straps", "sát nách", "ao"),
    (r"oversized|boxy|loose fit|relaxed fit|loose-fitting|wide cut", "dáng rộng", ""),
    (r"slim fit|fitted|skinny|tight-fitting", "dáng ôm", ""),
    (r"cropped|short top", "croptop", "ao"),
    (r"zip", "khóa kéo", ""),
    (r"double-breasted", "hai hàng khuy", "ao"),
    (r"high waist|high-waisted|extra-high", "cạp cao", "quan"),
    (r"wide leg|wide-leg|wide, straight|flared", "ống rộng", "quan"),
    (r"straight leg|straight-leg|straight legs|straight-cut", "ống đứng", "quan"),
    (r"tapered", "ống côn", "quan"),
    (r"ankle-length|cropped", "lửng", "quan"),
    (r"elasticated|drawstring", "cạp chun", "quan"),
    (r"ripped|distressed|trashed|worn", "rách", "quan"),
]


def norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", "", (text or "").lower().replace("-", " ")).split())


def caption_key(article):
    return norm(f"{article['graphical_appearance_name']} {article['colour_group_name']} "
                f"{article['detail_desc']}")


def category_of(a):
    """Map an H&M article to one of our categories (None = not a top or trousers)."""
    t = a["product_type_name"]
    name = (a["prod_name"] or "").lower()
    desc = (a["detail_desc"] or "").lower()
    garment = (a["garment_group_name"] or "").lower()
    if t == "T-shirt" or t == "Top":
        return "ao_phong"
    if t == "Polo shirt":
        return "ao_polo"
    if t == "Shirt":
        return "ao_so_mi"
    if t == "Blouse":
        return "ao_kieu"
    if t == "Vest top":
        return "ao_hai_day"
    if t == "Sweater":
        return "ao_ni" if ("sweatshirt" in desc or "sweatshirt" in name) else "ao_len"
    if t == "Hoodie":
        return "ao_hoodie"
    if t == "Cardigan":
        return "ao_cardigan"
    if t in ("Jacket", "Coat"):
        return "ao_khoac"
    if t == "Blazer":
        return "ao_blazer"
    if t == "Shorts":
        return "quan_short"
    if t == "Leggings/Tights":
        if "tights" in name or " den" in name or "denier" in desc:
            return None                   # packaged tights: photo is a box
        return "quan_legging"
    if t == "Trousers":
        if "denim" in garment or "jeans" in desc or "denim" in desc:
            return "quan_jeans"
        if "jogger" in name or "sweatshirt fabric" in desc or "joggers" in desc:
            return "quan_jogger"
        if "tailored" in desc or "suit" in name or "suit" in desc or "dressed" in garment:
            return "quan_au"
        return "quan_dai"
    return None


def gender_of(a):
    section = (a["section_name"] or "").lower()
    group = a["index_group_name"]
    if group == "Menswear" or re.search(r"\bmen", section) and "women" not in section:
        return "nam"
    if group in ("Ladieswear", "Divided", "Sport"):
        return "nu"
    return None                            # baby / children: skipped


def brand_of(a):
    return {"Divided": "H&M Divided", "Sport": "H&M Sport"}.get(a["index_group_name"], "H&M")


def material_of(desc):
    d = desc.lower()
    for pattern, vi in MATERIALS:
        if re.search(pattern, d):
            return vi
    return "vải dệt"


def features_of(desc, category):
    d = desc.lower()
    found = []
    for pattern, vi, prefix in FEATURES:
        if category.startswith(prefix) and re.search(pattern, d) and vi not in found:
            found.append(vi)
    if "dáng rộng" in found and "dáng ôm" in found:
        found.remove("dáng ôm")
    return found


def price_of(article, category, rng):
    low, high = PRICE_RANGE[category]
    desc = (article["detail_desc"] or "").lower()
    x = rng.random() ** 1.3                       # more cheap items than expensive ones
    if PREMIUM_RE.search(desc):
        x = 0.55 + 0.45 * rng.random()
    price = low + x * (high - low)
    return max(low, int(round(price / 50_000) * 50_000 - 1_000))   # 149.000, 199.000 ...


def describe(p, features, desc_en):
    parts = [f"{p['category_name']} {p['color']} dành cho {'nam' if p['gender'] == 'nam' else 'nữ'}"]
    if p["material"] != "vải dệt":
        parts.append(f"chất liệu {p['material']}")
    if p["pattern"] != "trơn":
        parts.append(f"họa tiết {p['pattern']}")
    else:
        parts.append("màu trơn")
    if features:
        parts.append(", ".join(features))
    return (", ".join(parts) + f". Dòng sản phẩm {p['brand']}.")[:255]


# ---------------------------------------------------------------- download
def fetch_json(url, tries=8):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(4 * (i + 1))           # the rows API rate-limits bursts
    return None


PAGE_CACHE = os.path.join(CATALOG_DIR, ".pages")


def fetch_page(offset):
    """One page of 100 captions; cached so that a second run does not refetch it."""
    cache = os.path.join(PAGE_CACHE, f"{offset}.json")
    if os.path.isfile(cache):
        with open(cache, encoding="utf-8") as f:
            return [tuple(r) for r in json.load(f)]
    q = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "train",
                                "offset": offset, "length": 100})
    data = fetch_json(f"{ROWS_API}?{q}")
    if not data:
        print(f"  page {offset}: failed")
        return []
    rows = [(r["row"]["text"], r["row"]["image"]["src"]) for r in data["rows"]]
    os.makedirs(PAGE_CACHE, exist_ok=True)
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    time.sleep(0.5)
    return rows


def fetch_image(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return Image.open(io.BytesIO(r.read())).convert("RGB")
        except Exception:
            time.sleep(1.5 * (i + 1))
    return None


def unify_background(im):
    """H&M photos are on white or on light grey. A levels correction maps the
    background to white (the garment is brightened by a few percent at most);
    the web page then prints every photo on the same warm colour with
    mix-blend-mode: multiply, so all product cards look alike."""
    import numpy as np
    arr = np.asarray(im).astype(np.float32)
    border = np.concatenate([arr[:8].reshape(-1, 3), arr[-8:].reshape(-1, 3),
                             arr[:, :8].reshape(-1, 3), arr[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    if bg.min() < 200:                         # not a studio background: leave it
        return im
    gain = np.clip(255.0 / bg, 1.0, 1.12)
    return Image.fromarray(np.clip(arr * gain, 0, 255).astype(np.uint8))


def fit(im, size=IMAGE_SIZE):
    """Resize to 2:3 on the studio background (no crop of the garment)."""
    canvas = Image.new("RGB", size, BACKGROUND)
    im = unify_background(ImageOps.contain(im, size, Image.LANCZOS))
    canvas.paste(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
    return canvas


def augment(im, rng):
    """A different-looking photo of the same garment: crop, rotate, light, background."""
    w, h = im.size
    s = rng.uniform(0.80, 0.92)
    cw, ch = int(w * s), int(h * s)
    x, y = rng.randint(0, w - cw), rng.randint(0, h - ch)
    im = im.crop((x, y, x + cw, y + ch))
    bg = rng.choice([(214, 198, 178), (190, 196, 204), (236, 226, 214), (205, 214, 200)])
    im = im.rotate(rng.uniform(-12, 12), resample=Image.BICUBIC, expand=True, fillcolor=bg)
    # replace the light grey studio background by a coloured one
    px = im.load()
    for yy in range(im.height):
        for xx in range(im.width):
            r, g, b = px[xx, yy]
            if r > 225 and g > 225 and b > 225 and abs(r - g) < 8 and abs(g - b) < 8:
                px[xx, yy] = bg
    im = ImageEnhance.Brightness(im).enhance(rng.uniform(0.8, 1.15))
    im = ImageEnhance.Color(im).enhance(rng.uniform(0.85, 1.15))
    im = im.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.0)))
    im.thumbnail((480, 480))
    return im


def interleave_colours(items):
    """Weighted round-robin over colours: every colour gets a turn, but common
    basics (black, white, grey, blue) get more turns, like in a real shop."""
    groups = {}
    for item in items:
        groups.setdefault(item[0]["perceived_colour_master_name"], []).append(item)
    order = sorted(groups.values(), key=len, reverse=True)
    turns = [max(1, round(len(g) ** 0.5 / 3)) for g in order]
    out = []
    while any(order):
        for g, n in zip(order, turns):
            out.extend(g[:n])
            del g[:n]
    return out


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--articles", required=True, help="H&M articles table (parquet)")
    ap.add_argument("--total", type=int, default=500)
    ap.add_argument("--heldout", type=int, default=50)
    ap.add_argument("--augmented", type=int, default=40)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--restyle", action="store_true",
                    help="only unify the backgrounds of the downloaded photos")
    args = ap.parse_args()
    if args.restyle:
        for name in sorted(os.listdir(IMAGE_DIR)):
            path = os.path.join(IMAGE_DIR, name)
            unify_background(Image.open(path).convert("RGB")).save(path, quality=88)
        print("backgrounds unified")
        return

    rng = random.Random(2026)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(QUERY_DIR, exist_ok=True)

    print("1/5 joining captions with the H&M articles table")
    articles = {}
    for a in pq.read_table(args.articles).to_pylist():
        articles.setdefault(caption_key(a), a)

    rows = []
    with ThreadPoolExecutor(args.workers) as pool:
        for page in pool.map(fetch_page, range(0, DATASET_SIZE, 100)):
            rows.extend(page)
    print(f"    {len(rows)} captions downloaded")

    pool_by_cat = {}
    seen_articles = set()
    for text, src in rows:
        a = articles.get(norm(text))
        if not a or a["article_id"] in seen_articles:
            continue
        cat, gender = category_of(a), gender_of(a)
        if not cat or not gender or (cat in WOMEN_ONLY and gender == "nam"):
            continue
        seen_articles.add(a["article_id"])
        pool_by_cat.setdefault(cat, []).append((a, src, gender))
    for cat in TARGETS:
        n = len(pool_by_cat.get(cat, []))
        m = sum(1 for _, _, g in pool_by_cat.get(cat, []) if g == "nam")
        print(f"    {cat:<14} available {n:>5} (men {m})")

    print("2/5 selecting products")
    scale = args.total / sum(TARGETS.values())
    selected, heldout_pool = [], []
    for cat, target in TARGETS.items():
        items = pool_by_cat.get(cat, [])
        rng.shuffle(items)
        items = interleave_colours(items)
        target = round(target * scale)
        men_target = 0 if cat in WOMEN_ONLY else round(target * MEN_SHARE)
        per_code, chosen = {}, []
        for want_gender, quota in (("nam", men_target), ("nu", target - men_target)):
            for a, src, g in items:
                if quota <= 0:
                    break
                code = a["product_code"]
                if g != want_gender or per_code.get(code, 0) >= 2 or (a, src, g) in chosen:
                    continue
                per_code[code] = per_code.get(code, 0) + 1
                chosen.append((a, src, g))
                quota -= 1
        if len(chosen) < target:                       # not enough men: fill with women
            for item in items:
                if len(chosen) >= target:
                    break
                if item not in chosen and per_code.get(item[0]["product_code"], 0) < 2:
                    per_code[item[0]["product_code"]] = per_code.get(item[0]["product_code"], 0) + 1
                    chosen.append(item)
        selected.extend((cat, *c) for c in chosen)
        codes = {c[0]["product_code"] for c in chosen}
        heldout_pool.extend((cat, a, src, g) for a, src, g in items
                            if (a, src, g) not in chosen and a["product_code"] not in codes)
    print(f"    {len(selected)} products selected")

    print("3/5 downloading product photos")

    def download(item):
        idx, (cat, a, src, g) = item
        im = fetch_image(src)
        if im is None:
            return None
        path = os.path.join(IMAGE_DIR, f"{idx:04d}.jpg")
        fit(im).save(path, quality=88)
        return idx

    with ThreadPoolExecutor(args.workers) as pool:
        ok = set(filter(None, pool.map(download, enumerate(selected, 1))))

    products = []
    for idx, (cat, a, src, gender) in enumerate(selected, 1):
        if idx not in ok:
            continue
        prng = random.Random(a["article_id"])
        desc_en = (a["detail_desc"] or "").strip()
        material = material_of(desc_en)
        features = features_of(desc_en, cat)
        p = {
            "product_id": idx,
            "category_id": cat,
            "category_name": CATEGORY_VI[cat],
            "brand": brand_of(a),
            "gender": gender,
            "color": COLOR_VI.get(a["perceived_colour_master_name"], "nhiều màu"),
            "color_detail": a["colour_group_name"],
            "material": material,
            "pattern": PATTERN_VI.get(a["graphical_appearance_name"], "trơn"),
            "features": features,
        }
        name_bits = [CATEGORY_VI[cat]]
        if p["pattern"] not in ("trơn",):
            name_bits.append(p["pattern"])
        if material not in ("vải dệt", "thun") and material not in CATEGORY_VI[cat].lower() \
                and not (cat == "quan_jeans" and material == "denim"):
            name_bits.append(material)
        name_bits += [f for f in features if not (cat == "ao_hoodie" and f == "có mũ")][:2]
        if len(name_bits) == 1:
            name_bits.append(p["color"])
        p["name"] = " ".join(name_bits)
        p["original_name"] = a["prod_name"]
        p["price"] = price_of(a, cat, prng)
        p["stock"] = 0 if prng.random() < 0.08 else prng.randint(3, 80)
        p["popularity"] = round(min(0.99, max(0.05, prng.betavariate(2.2, 2.8))), 3)
        p["created_at"] = f"2026-{prng.randint(3, 10):02d}-{prng.randint(1, 28):02d} 09:00:00"
        p["description"] = describe(p, features, desc_en)
        p["description_en"] = f"{a['prod_name']}: {desc_en}"
        p["image_path"] = f"catalog/images/{idx:04d}.jpg"
        p["source_url"] = f"https://www2.hm.com/en_gb/productpage.{a['article_id']:010d}.html"
        products.append(p)
    with open(os.path.join(CATALOG_DIR, "products.json"), "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=1)
    print(f"    {len(products)} products written to data/catalog/products.json")

    print("4/5 held-out query photos (products not in the catalogue)")
    rng.shuffle(heldout_pool)
    per_cat, held = {}, []
    for cat, a, src, g in heldout_pool:
        if per_cat.get(cat, 0) >= max(2, args.heldout // len(TARGETS) + 1):
            continue
        per_cat[cat] = per_cat.get(cat, 0) + 1
        held.append((cat, a, src, g))
        if len(held) >= args.heldout:
            break
    queries = []

    def download_heldout(item):
        i, (cat, a, src, g) = item
        im = fetch_image(src)
        if im is None:
            return None
        name = f"heldout_{i:02d}_{cat}.jpg"
        im.thumbnail((600, 900))
        im.save(os.path.join(QUERY_DIR, name), quality=88)
        return {"file": name, "kind": "heldout", "category_id": cat, "gender": g,
                "color": COLOR_VI.get(a["perceived_colour_master_name"], "nhiều màu"),
                "original_name": a["prod_name"]}

    with ThreadPoolExecutor(args.workers) as pool:
        queries += [q for q in pool.map(download_heldout, enumerate(held, 1)) if q]

    print("5/5 augmented query photos (edited photos of catalogue products)")
    for i, p in enumerate(rng.sample(products, min(args.augmented, len(products))), 1):
        im = Image.open(os.path.join(ROOT, "data", p["image_path"])).convert("RGB")
        name = f"aug_{i:02d}_p{p['product_id']:04d}.jpg"
        augment(im, rng).save(os.path.join(QUERY_DIR, name), quality=85)
        queries.append({"file": name, "kind": "augmented", "product_id": p["product_id"],
                        "category_id": p["category_id"], "color": p["color"]})
    with open(os.path.join(QUERY_DIR, "queries.json"), "w", encoding="utf-8") as f:
        json.dump(queries, f, ensure_ascii=False, indent=1)
    print(f"    {len(queries)} query photos written to data/query_images/")


if __name__ == "__main__":
    main()
