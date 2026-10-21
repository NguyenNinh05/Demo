"""
Experimental evaluation of SnapShop search.

A text / voice query is successful when the Top-1 product satisfies every
condition the customer gave (category, price, colour, gender, material ...),
or when the system does the right thing for a special case (an empty result
with a "not found" message for an impossible request, refusing a product the
shop does not sell, finding the right order). P@5 = share of the Top-5 products that satisfy the conditions.

Photo queries (data/query_images/queries.json):
  * augmented : an edited photo of a catalogue product -> the same product must be Top-1
  * heldout   : a photo of an H&M product that is NOT in the shop -> Top-1 must be
                the same category (a "similar product")
  * text+photo: a held-out photo + a condition ("màu đen", "dưới 500k", "cho nam")

    python main.py --evaluate          (writes results/evaluation.md)
"""
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

Q = os.path.join(ROOT, "data", "query_images")
WARM = ["len", "nỉ", "nhung tăm", "da"]
THIN = ["lụa", "voan", "linen"]

# (mode, input, expected conditions)
TEST_SET = [
    # ---- text ----
    ("Text", "áo phông dưới 100k", {"cat": ["ao_phong"], "max": 100_000}),
    ("Text", "áo phông trên 2 triệu", {"empty": True}),
    ("Text", "ao thun duoi 150k", {"cat": ["ao_phong"], "max": 150_000}),
    ("Text", "quần jeans nam tầm 600-900 nghìn", {"cat": ["quan_jeans"], "gender": "nam",
                                                "min": 600_000, "max": 900_000}),
    ("Text", "áo khoác 1tr5 đổ lại", {"cat": ["ao_khoac"], "max": 1_500_000}),
    ("Text", "ao so mi trang tay dai", {"cat": ["ao_so_mi"], "color": ["trắng"]}),
    ("Text", "hoodie đen rẻ nhất", {"cat": ["ao_hoodie"], "color": ["đen"], "top": "price_asc"}),
    ("Text", "quần short nữ", {"cat": ["quan_short"], "gender": "nu"}),
    ("Text", "đồ đi làm cho nữ", {"gender": "nu", "avoid_name": ["croptop", "sát nách", "rách"],
                                  "avoid_cat": ["ao_hoodie", "quan_legging", "quan_jogger",
                                                "quan_short", "quan_jeans"]}),
    ("Text", "quần âu nam", {"cat": ["quan_au"], "gender": "nam"}),
    ("Text", "áo hai dây màu hồng", {"cat": ["ao_hai_day"], "color": ["hồng"]}),
    ("Text", "áo hai dây màu đỏ", {"empty": True}),
    ("Text", "áo kẻ sọc", {"cat": ["ao"], "pattern": ["kẻ sọc"]}),
    ("Text", "quần bò xanh", {"cat": ["quan_jeans"],
                              "color": ["xanh dương", "xanh lá", "xanh rêu", "xanh ngọc"]}),
    ("Text", "áo hodie xám", {"cat": ["ao_hoodie"], "color": ["xám"]}),
    ("Text", "áo len nam màu xám", {"cat": ["ao_len"], "gender": "nam", "color": ["xám"]}),
    ("Text", "cardigan", {"cat": ["ao_cardigan"]}),
    ("Text", "quần legging tập gym", {"cat": ["quan_legging"]}),
    ("Text", "áo thể thao", {"cat": ["ao"], "sport": True}),
    ("Text", "áo khoác thể thao", {"cat": ["ao_khoac"], "sport": True}),
    ("Text", "quần thể thao nam", {"cat": ["quan"], "gender": "nam", "sport": True}),
    # occasions: checked against the product's own attributes, not against its labels
    ("Text", "đồ đi biển", {"avoid_mat": WARM, "avoid_cat": ["ao_khoac", "ao_hoodie", "ao_len",
                                                             "quan_jeans"]}),
    ("Text", "áo mặc trời lạnh", {"cat": ["ao"], "avoid_mat": THIN,
                                  "avoid_name": ["ngắn tay", "sát nách", "croptop"]}),
    ("Text", "đồ đi làm", {"avoid_name": ["croptop", "sát nách", "rách"],
                           "avoid_cat": ["ao_hoodie", "quan_legging", "quan_jogger", "quan_short",
                                         "quan_jeans"]}),
    ("Text", "áo đi mưa", {"cat": ["ao"], "desc_any": ["water", "rain", "wind"]}),
    ("Text", "đồ đi tiệc", {"avoid_cat": ["ao_hoodie", "ao_ni", "quan_jogger", "quan_legging"],
                            "avoid_name": ["rách"]}),
    ("Text", "đồ mặc ở nhà", {"avoid_cat": ["ao_blazer", "quan_au", "quan_jeans", "ao_khoac"]}),
    ("Text", "áo thun lạnh", {"cat": ["ao_phong"], "no_occasion": True}),
    ("Text", "quần jeans thoải mái", {"cat": ["quan_jeans"], "no_occasion": True}),
    ("Text", "đầm đi tiệc", {"intent": "unsupported"}),
    ("Text", "áo len đi biển", {"empty": True}),
    ("Text", "ao polo nam duoi 400k", {"cat": ["ao_polo"], "gender": "nam", "max": 400_000}),
    ("Text", "áo sơ mi denim", {"cat": ["ao_so_mi"], "material": ["denim"]}),
    ("Text", "quần jogger nỉ xám", {"cat": ["quan_jogger"], "color": ["xám"]}),
    ("Text", "áo blazer nữ đắt nhất", {"cat": ["ao_blazer"], "gender": "nu", "top": "price_desc"}),
    ("Text", "đồ mặc khi trời lạnh", {"avoid_mat": THIN, "avoid_cat": ["quan_short"],
                                      "avoid_name": ["ngắn tay", "sát nách", "croptop"]}),
    ("Text", "giày nike", {"intent": "unsupported"}),
    ("Text", "đơn hàng DH004", {"order": "DH004"}),
    ("Text", "các đơn hàng của tôi", {"orders": 4}),
    # ---- voice: transcripts with regional words (speech-to-text step simulated) ----
    ("Voice", "cho tui coi mấy cái quần đùi hông quá 300 ngàn", {"cat": ["quan_short"],
                                                                 "max": 300_000}),
    ("Voice", "có cái áo khoác mô dưới một triệu không", {"cat": ["ao_khoac"], "max": 1_000_000}),
    ("Voice", "kiếm giùm tui cái áo thun đen nam", {"cat": ["ao_phong"], "color": ["đen"],
                                                     "gender": "nam"}),
    ("Voice", "quần jean nữ mắc nhất", {"cat": ["quan_jeans"], "gender": "nu", "top": "price_desc"}),
    ("Voice", "áo sơ mi trắng đi làm", {"cat": ["ao_so_mi"], "color": ["trắng"]}),
    ("Voice", "hông biết có hoodie xám hông", {"cat": ["ao_hoodie"], "color": ["xám"]}),
    ("Voice", "đơn hàng gần nhất của tui đâu", {"order": "DH010"}),
]
MULTIMODAL_TEXTS = [("màu đen", {"color": ["đen"]}), ("dưới 500k", {"max": 500_000}),
                    ("cho nam", {"gender": "nam"}), ("màu trắng", {"color": ["trắng"]})]


def satisfies(p, cond):
    cats = cond.get("cat")
    if cats and not any(p["category_id"] == c or p["category_id"].startswith(c + "_")
                        for c in cats):
        return False
    if "min" in cond and p["price"] < cond["min"]:
        return False
    if "max" in cond and p["price"] > cond["max"]:
        return False
    if "color" in cond and p["color"] not in cond["color"]:
        return False
    if "gender" in cond and p["gender"] not in (cond["gender"], "unisex"):
        return False
    if "material" in cond and p["material"] not in cond["material"]:
        return False
    if "pattern" in cond and p["pattern"] not in cond["pattern"]:
        return False
    if cond.get("sport") and not (p["brand"] == "H&M Sport" or p["material"] == "vải thể thao"):
        return False
    if p["material"] in cond.get("avoid_mat", ()) or p["category_id"] in cond.get("avoid_cat", ()):
        return False
    if any(w in p["name"] for w in cond.get("avoid_name", ())):
        return False
    if "desc_any" in cond and not any(w in (p["description_en"] or "").lower()
                                      for w in cond["desc_any"]):
        return False
    return True


def check_products(out, cond, all_products):
    results = [r["product"] for r in out.get("results") or []]
    if not results:
        return False, "-", 0.0
    top5 = results[:5]
    p5 = sum(satisfies(p, cond) for p in top5) / len(top5)
    ok = satisfies(results[0], cond)
    if cond.get("no_occasion"):
        ok = ok and not out["query"].get("occasions")
    if cond.get("top"):
        pool = [p for p in all_products if satisfies(p, cond)]
        if pool:
            best = (min if cond["top"] == "price_asc" else max)(p["price"] for p in pool)
            ok = ok and results[0]["price"] == best
    return ok, results[0]["name"], p5


def run_one(ui, mode, value):
    if mode == "Text":
        return ui.text_search(value)
    if mode == "Voice":
        return ui.voice_search(value)
    if mode == "Image":
        return ui.image_search(os.path.join(Q, value))
    text, image = value
    return ui.multimodal_search(text, os.path.join(Q, image))


def evaluate(ui):
    """Run every test on a (silent) SearchUI. Returns (rows, metrics)."""
    products = ui.search_service.products.all_products()
    rows, times = [], {"Text": [], "Voice": [], "Image": [], "Text+Image": []}

    def record(label, mode, top1, p5, ok, ms):
        rows.append({"query": label, "mode": mode, "top1": top1,
                     "p5": "" if p5 is None else f"{p5:.0%}", "ok": ok, "ms": round(ms)})
        times[mode].append(ms)

    for mode, value, cond in TEST_SET:
        t = time.perf_counter()
        out = run_one(ui, mode, value)
        ms = (time.perf_counter() - t) * 1000
        if "intent" in cond:
            ok = out["query"]["intent"] == cond["intent"]
            record(value, mode, out.get("message", "-")[:60], None, ok, ms)
        elif cond.get("empty"):
            ok = not out.get("results") and bool(out.get("message"))
            record(value, mode, out.get("message") or "-", None, ok, ms)
        elif "order" in cond or "orders" in cond:
            orders = out.get("orders") or []
            ok = (orders and orders[0]["order_id"] == cond["order"]) if "order" in cond \
                else len(orders) == cond["orders"]
            record(value, mode, ", ".join(o["order_id"] for o in orders) or "-", None, bool(ok), ms)
        else:
            ok, top1, p5 = check_products(out, cond, products)
            record(value, mode, top1, p5, ok, ms)

    with open(os.path.join(Q, "queries.json"), encoding="utf-8") as f:
        photos = json.load(f)
    exact_top1 = exact_top5 = 0
    cat_top1, cat_p5 = 0, []
    augmented = [q for q in photos if q["kind"] == "augmented"]
    heldout = [q for q in photos if q["kind"] == "heldout"]
    for q in augmented:
        t = time.perf_counter()
        out = run_one(ui, "Image", q["file"])
        ms = (time.perf_counter() - t) * 1000
        ids = [r["product"]["product_id"] for r in out["results"][:5]]
        hit1, hit5 = bool(ids) and ids[0] == q["product_id"], q["product_id"] in ids
        exact_top1 += hit1
        exact_top5 += hit5
        record(f"{q['file']} (ảnh chỉnh sửa)", "Image", out["results"][0]["product"]["name"],
               None, hit1, ms)
    for q in heldout:
        t = time.perf_counter()
        out = run_one(ui, "Image", q["file"])
        ms = (time.perf_counter() - t) * 1000
        top = [r["product"] for r in out["results"][:5]]
        same = [p["category_id"] == q["category_id"] for p in top]
        cat_top1 += same[0]
        cat_p5.append(sum(same) / len(same))
        record(f"{q['file']} (ảnh ngoài shop)", "Image", top[0]["name"], sum(same) / len(same),
               same[0], ms)
    for i, q in enumerate(heldout[:12]):
        text, cond = MULTIMODAL_TEXTS[i % len(MULTIMODAL_TEXTS)]
        cond = dict(cond, cat=[q["category_id"]])
        t = time.perf_counter()
        out = run_one(ui, "Text+Image", (text, q["file"]))
        ms = (time.perf_counter() - t) * 1000
        ok, top1, p5 = check_products(out, cond, products)
        record(f"{text} + {q['file']}", "Text+Image", top1, p5, ok, ms)

    def pct(a, b):
        return f"{100 * a / b:.0f}%" if b else "-"

    product_rows = [r for r in rows if r["p5"]]
    metrics = [
        {"name": "Ảnh chỉnh sửa → đúng sản phẩm (Top-1)", "value": pct(exact_top1, len(augmented))},
        {"name": "Ảnh chỉnh sửa → đúng sản phẩm (Top-5)", "value": pct(exact_top5, len(augmented))},
        {"name": "Ảnh ngoài shop → đúng loại (Top-1)", "value": pct(cat_top1, len(heldout))},
        {"name": "Ảnh ngoài shop → đúng loại (P@5)",
         "value": f"{100 * statistics.mean(cat_p5):.0f}%" if cat_p5 else "-"},
        {"name": "P@5 trung bình (truy vấn có điều kiện)",
         "value": f"{100 * statistics.mean(float(r['p5'][:-1]) / 100 for r in product_rows):.0f}%"},
    ] + [{"name": f"Thời gian TB · {m}", "value": f"{statistics.mean(v):.0f} ms"}
         for m, v in times.items() if v]
    return rows, metrics


def summary(rows, metrics):
    """The result as a dictionary (for the web page)."""
    modes = []
    for mode in ("Text", "Voice", "Image", "Text+Image"):
        sub = [r for r in rows if r["mode"] == mode]
        modes.append({"mode": mode, "total": len(sub), "success": sum(r["ok"] for r in sub)})
    return {"total": len(rows), "success": sum(r["ok"] for r in rows), "modes": modes,
            "rows": rows, "metrics": metrics,
            "failures": [r for r in rows if not r["ok"]]}


def run_evaluation(write_file=True):
    from main import create_console_ui
    rows, metrics = evaluate(create_console_ui(verbose=False))
    s = summary(rows, metrics)
    w = [52, 11, 44, 6, 6]
    print("\n=== ĐÁNH GIÁ HỆ THỐNG ===")
    print("".join(h.ljust(n) for h, n in zip(["Truy vấn", "Kiểu", "Kết quả #1", "P@5", "Đạt"], w)))
    print("-" * sum(w))
    for r in rows:
        cells = [r["query"], r["mode"], r["top1"], r["p5"], "Có" if r["ok"] else "Không"]
        print("".join(str(c)[:n - 1].ljust(n) for c, n in zip(cells, w)))
    print("-" * sum(w))
    print(f"Tỉ lệ đạt: {s['success']}/{s['total']} = {s['success'] / s['total']:.1%}")
    for m in s["modes"]:
        print(f"   {m['mode']:<11}: {m['success']}/{m['total']}")
    for m in metrics:
        print(f"   {m['name']:<44}: {m['value']}")
    if write_file:
        os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
        with open(os.path.join(ROOT, "results", "evaluation.md"), "w", encoding="utf-8") as f:
            f.write("| # | Truy vấn | Kiểu | Kết quả #1 | P@5 | Đạt |\n|---|---|---|---|---|---|\n")
            for i, r in enumerate(rows, 1):
                f.write(f"| {i} | {r['query']} | {r['mode']} | {r['top1']} | {r['p5']} | "
                        f"{'Có' if r['ok'] else 'Không'} |\n")
            f.write(f"\n**Tỉ lệ đạt: {s['success']}/{s['total']} = "
                    f"{s['success'] / s['total']:.1%}**\n\n")
            for m in s["modes"]:
                f.write(f"- {m['mode']}: {m['success']}/{m['total']}\n")
            for m in metrics:
                f.write(f"- {m['name']}: {m['value']}\n")
    return s


if __name__ == "__main__":
    run_evaluation()
