"""Label every product with the occasions it suits, with Gemini.

"Đồ đi biển" or "áo đi làm" cannot be answered from the category alone (a
long-sleeved wool T-shirt is not beach wear, a sleeveless blouse is not office
wear), so each product is judged once, offline, from its photo, name, fabric
and the original H&M description. The result is stored with the product and
the search filters on it.

Three steps, each cached in data/catalog/.labels/ so an interrupted run resumes:
  1. a first model labels every product
  2. a second model labels every product independently
  3. a judge (with reasoning, sees both answers) decides every product the two
     disagree on; it is a list of models tried in order when one is overloaded
(--single skips steps 2 and 3.) Then the "KHÔNG gắn cho" part of each definition
is applied as hard rules on the product's attributes, so a label that breaks it
(a sleeveless top "for the office") is removed and recorded as removed_by_rule.
The final labels (with the reason) go to data/catalog/occasions.json and to
the "occasions" field of data/catalog/products.json.

    python tools/label_occasions.py            (then: python main.py --init-db)
    python tools/label_occasions.py --single   (first model only, faster)
    python tools/label_occasions.py --check    (only print the labels removed by the rules)
    python tools/label_occasions.py --apply    (re-apply the cached labels, no Gemini call)
"""
import argparse
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402
from application.gemini_client import GeminiClient, GeminiError  # noqa: E402
from application.lexicon import OCCASIONS  # noqa: E402

CATALOG = os.path.join(ROOT, "data", "catalog")
CACHE = os.path.join(CATALOG, ".labels")
# each labeller is a list tried in order: the first answers, the next ones stand in when
# the free quota of the first is used up (every label records the model that gave it)
LABELLER_A = "gemini-3-flash-preview,gemini-3.5-flash-lite,gemini-flash-lite-latest"
LABELLER_B = "gemini-3.5-flash-lite,gemini-flash-lite-latest"
JUDGE = "gemini-3.8-flash,gemini-3.1-pro-preview,gemini-3-flash-preview"
BATCH, JUDGE_BATCH = 20, 8           # few large requests: the free tier counts requests

# what each occasion means; the keys are the occasions of application/lexicon.py
GUIDE = {
    "đi làm": "Trang phục công sở gọn gàng, lịch sự: sơ mi, blazer, áo kiểu thanh lịch, polo trơn, "
              "áo len hoặc cardigan trơn lịch sự, quần âu, quần dài vải/kaki đứng dáng. KHÔNG gắn cho: "
              "croptop, sát nách, hai dây, đồ hở, đồ rách, áo in hình lớn, hoodie, áo nỉ, đồ thể thao, "
              "legging, quần short, jogger, quần jeans.",
    "tập thể thao": "Đồ được thiết kế để tập luyện: dòng H&M Sport, vải thể thao (co giãn, nhanh khô, "
                    "thoáng khí), legging tập, quần short tập, áo tập. KHÔNG gắn cho đồ thời trang "
                    "thường như áo phông cotton hay hoodie nỉ thường, dù mặc đi tập cũng được.",
    "đi biển / trời nóng": "Mỏng, thoáng, mát: áo phông và sơ mi ngắn tay, áo hai dây, áo sát nách, sơ mi "
                           "hoặc quần chất linen/voan mỏng, quần short. KHÔNG gắn cho: len, nỉ, nhung, da, "
                           "denim dày, áo khoác, hoodie, áo dài tay dày, quần jeans dài.",
    "trời lạnh": "Giữ ấm: áo len, áo nỉ, hoodie, cardigan, áo khoác có độ ấm, áo dài tay dày, quần dài "
                 "dày (nỉ, nhung, jeans, jogger nỉ). KHÔNG gắn cho: ngắn tay, sát nách, hai dây, "
                 "croptop hở bụng, chất mỏng (lụa, voan, linen), quần short.",
    "đi tiệc / hẹn hò": "Trang phục đẹp, thanh lịch hoặc nổi bật để dự tiệc, hẹn hò: áo kiểu lụa/voan/"
                        "satin, blazer, sơ mi đẹp, áo len mỏng thanh lịch, quần âu, quần ống rộng chất đẹp, "
                        "áo hai dây hoặc croptop thời trang dáng đẹp. KHÔNG gắn cho: đồ thể thao, áo phông "
                        "trơn cơ bản, hoodie, áo nỉ, jogger, legging, đồ rách.",
    "mặc ở nhà": "Thoải mái, mềm, rộng rãi để mặc ở nhà: áo phông cotton/thun, áo nỉ, jogger, quần "
                 "short thun/cotton, cardigan mềm. KHÔNG gắn cho: blazer, sơ mi công sở, quần âu, "
                 "jeans, đồ da, áo khoác ngoài, đồ đi tiệc.",
    "đi chơi / đi học": "Đồ thường ngày năng động để đi chơi, đi học: áo phông, sơ mi casual, hoodie, áo "
                        "nỉ, jeans, quần short, quần dài casual, áo khoác casual. KHÔNG gắn cho đồ quá "
                        "trang trọng (blazer công sở, quần âu) hay đồ chỉ để tập thể thao.",
    "trời mưa / gió": "CHỈ áo khoác chống nước, chống gió, áo gió, áo parka có lớp chống nước: phải được "
                      "ghi trong mô tả (water-repellent, waterproof, windproof, rain...) hoặc nhìn rõ là "
                      "áo gió. KHÔNG gắn cho áo khoác len, nỉ, denim, lụa, blazer hay mọi loại áo khác.",
}
assert list(GUIDE) == list(OCCASIONS), "GUIDE must cover the occasions of lexicon.py"

SYSTEM = ("Bạn là chuyên viên tư vấn thời trang của một shop quần áo ở Việt Nam. Với mỗi sản phẩm "
          "(ảnh + thông tin), hãy cho biết sản phẩm HỢP với những dịp nào trong danh sách. Một sản "
          "phẩm có thể hợp nhiều dịp hoặc không hợp dịp nào. Chỉ gắn một dịp khi sản phẩm thật sự "
          "phù hợp theo đúng định nghĩa; phân vân thì KHÔNG gắn. Nhìn kỹ ảnh: tay áo dài hay ngắn, "
          "có hở bụng không, độ dày của vải.\n\nĐịnh nghĩa các dịp:\n" +
          "\n".join(f"- {k}: {v}" for k, v in GUIDE.items()))

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "product_id": {"type": "integer"},
            "occasions": {"type": "array", "items": {"type": "string", "enum": list(GUIDE)}},
            "reason": {"type": "string", "description": "Một câu tiếng Việt ngắn giải thích."},
        },
        "required": ["product_id", "occasions", "reason"]}}},
    "required": ["items"],
}


def load_products():
    with open(os.path.join(CATALOG, "products.json"), encoding="utf-8") as f:
        return json.load(f)


def thumbnail(product):
    from PIL import Image
    img = Image.open(os.path.join(ROOT, "data", product["image_path"])).convert("RGB")
    img.thumbnail((320, 480))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def facts(p):
    return (f"product_id={p['product_id']} | loại: {p['category_name']} | tên: {p['name']} | "
            f"chất liệu: {p.get('material')} | đặc điểm: {', '.join(p.get('features') or []) or '-'} | "
            f"dòng: {p['brand']} | giới tính: {p['gender']} | mô tả gốc H&M: {p.get('description_en')}")


def ask(client, model, contents, system, think=False, retries=5):
    for attempt in range(retries):
        try:
            return client.generate_json(model, contents, SCHEMA, system=system, think=think)["items"]
        except GeminiError:
            if attempt == retries - 1:
                raise
            time.sleep(30 * (attempt + 1))     # per-minute quota or overload: wait and retry


def label_batch(client, model, batch):
    contents = ["Gắn nhãn dịp cho các sản phẩm sau."]
    for p in batch:
        contents += [facts(p), client.image(thumbnail(p))]
    items = ask(client, model, contents, SYSTEM)
    used = client.last_model
    return {i["product_id"]: {"occasions": i["occasions"], "reason": i["reason"], "model": used}
            for i in items if i["product_id"] in {p["product_id"] for p in batch}}


def load_cache(name):
    path = os.path.join(CACHE, name + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return {int(k): v for k, v in json.load(f).items()}
    return {}


def save_cache(name, labels):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, name + ".json"), "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(labels.items())}, f, ensure_ascii=False, indent=1)


def label_all(client, model, products):
    name = model.split(",")[0]               # cache named after the main model
    labels = load_cache(name)
    todo = [p for p in products if p["product_id"] not in labels]
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"{name}: {len(labels)} đã có, {len(todo)} cần gắn nhãn ({len(batches)} lượt gọi)")
    for done, batch in enumerate(batches, 1):
        labels.update(label_batch(client, model, batch))
        save_cache(name, labels)
        print(f"  {done}/{len(batches)}", flush=True)
    missing = [p["product_id"] for p in products if p["product_id"] not in labels]
    if missing:                                 # a model sometimes skips an item: ask again
        labels.update(label_batch(client, model, [p for p in products if p["product_id"] in missing]))
        save_cache(name, labels)
    return labels


JUDGE_SYSTEM = SYSTEM + ("\n\nVới mỗi sản phẩm dưới đây, hai chuyên viên A và B đã gắn nhãn và không "
                         "thống nhất. Hãy xem kỹ ảnh và thông tin, cân nhắc lý do của cả hai, rồi "
                         "đưa ra quyết định cuối cùng theo đúng định nghĩa.")


def judge_batch(client, batch, a, b):
    contents = ["Quyết định nhãn dịp cuối cùng cho các sản phẩm sau."]
    for p in batch:
        pid = p["product_id"]
        contents += [facts(p), client.image(thumbnail(p)),
                     f"Chuyên viên A: {a[pid]['occasions']} — {a[pid]['reason']}",
                     f"Chuyên viên B: {b[pid]['occasions']} — {b[pid]['reason']}"]
    items = ask(client, JUDGE, contents, JUDGE_SYSTEM, think=True)
    model = client.last_model
    return {i["product_id"]: {"occasions": i["occasions"], "reason": i["reason"],
                              "source": f"judge:{model}"}
            for i in items if i["product_id"] in {p["product_id"] for p in batch}}


def judge_all(client, products, a, b):
    final = load_cache("final")
    for p in products:
        pid = p["product_id"]
        if pid not in final and set(a[pid]["occasions"]) == set(b[pid]["occasions"]):
            final[pid] = dict(a[pid], source="A=B")
    todo = [p for p in products if p["product_id"] not in final]
    batches = [todo[i:i + JUDGE_BATCH] for i in range(0, len(todo), JUDGE_BATCH)]
    print(f"judge: {len(todo)} sản phẩm hai mô hình không thống nhất ({len(batches)} lượt gọi)")
    for done, batch in enumerate(batches, 1):
        final.update(judge_batch(client, batch, a, b))
        save_cache("final", final)
        print(f"  {done}/{len(batches)}", flush=True)
    missing = [p for p in products if p["product_id"] not in final]
    if missing:
        final.update(judge_batch(client, missing, a, b))
        save_cache("final", final)
    return final


# --------------------------------------------------------------- rules
SLEEVELESS = ("sát nách", "hai dây", "croptop")


def contradicts(p, occasion):
    """The "KHÔNG gắn cho" part of GUIDE as hard rules on the product's own attributes.
    A model sometimes breaks them ("áo sát nách ... thanh lịch hợp đi làm"); such a label
    is removed. Occasions without a clear attribute test are left to the model."""
    name, mat, cat = p["name"], p.get("material"), p["category_id"]
    sleeveless = any(w in name for w in SLEEVELESS) or cat == "ao_hai_day"
    rules = {
        "đi làm": sleeveless or "rách" in name
                  or cat in {"ao_hoodie", "quan_legging", "quan_jogger", "quan_short", "quan_jeans"},
        "đi biển / trời nóng": mat in {"len", "nỉ", "nhung tăm", "da"}
                               or cat in {"ao_hoodie", "ao_len", "quan_jeans"},
        "trời lạnh": sleeveless or "ngắn tay" in name or mat in {"lụa", "voan", "linen"}
                     or cat == "quan_short",
        "đi tiệc / hẹn hò": "rách" in name
                            or cat in {"ao_hoodie", "ao_ni", "quan_jogger", "quan_legging"},
        "mặc ở nhà": cat in {"ao_blazer", "quan_jeans"} or mat == "da",
    }
    return rules.get(occasion, False)


def enforce(products, labels):
    """Final labels = model labels minus the ones that contradict the rules."""
    out = {}
    for p in products:
        v = labels[p["product_id"]]
        removed = [o for o in v["occasions"] if contradicts(p, o)]
        out[p["product_id"]] = dict(v, occasions=[o for o in v["occasions"] if o not in removed],
                                    removed_by_rule=removed)
    return out


def report(products, labels):
    from collections import Counter
    count = Counter(o for v in labels.values() for o in v["occasions"])
    print("\nSố sản phẩm mỗi dịp:")
    for o in GUIDE:
        print(f"  {o:<22} {count[o]}")
    print(f"  (không dịp nào)       {sum(not v['occasions'] for v in labels.values())}")
    removed = [(p, labels[p["product_id"]]) for p in products if labels[p["product_id"]]["removed_by_rule"]]
    print(f"\nNhãn bị luật gỡ vì trái định nghĩa: {sum(len(v['removed_by_rule']) for _, v in removed)}")
    for p, v in removed:
        print(f"  #{p['product_id']:<4} {p['name']:<42} gỡ {v['removed_by_rule']}  — {v['reason']}")


def apply(products, labels):
    order = list(GUIDE)
    for p in products:
        p["occasions"] = sorted(labels[p["product_id"]]["occasions"], key=order.index)
    with open(os.path.join(CATALOG, "products.json"), "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=1)
    with open(os.path.join(CATALOG, "occasions.json"), "w", encoding="utf-8") as f:
        json.dump({str(p["product_id"]): {"name": p["name"], **labels[p["product_id"]]}
                   for p in products}, f, ensure_ascii=False, indent=1)
    print("đã ghi data/catalog/products.json và data/catalog/occasions.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only report on the current labels")
    ap.add_argument("--apply", action="store_true",
                    help="no Gemini call: apply the cached labels and the rules again")
    ap.add_argument("--single", action="store_true",
                    help="use the first model only (no second opinion, no judge): faster")
    args = ap.parse_args()
    products = load_products()
    if args.check or args.apply:
        final = enforce(products, load_cache("final"))
        report(products, final)
        if args.apply:
            apply(products, final)
        return
    client = GeminiClient(config.GEMINI_API_KEY, timeout_s=180)
    a = label_all(client, LABELLER_A, products)
    if args.single:
        final = {pid: dict(v, source=v.get("model", LABELLER_A.split(",")[0])) for pid, v in a.items()}
        save_cache("final", final)
    else:
        b = label_all(client, LABELLER_B, products)
        final = judge_all(client, products, a, b)
    final = enforce(products, final)
    report(products, final)
    apply(products, final)


if __name__ == "__main__":
    main()
