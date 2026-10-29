"""Application Layer - RuleParser: Vietnamese query -> structured intent (no API call).

Steps (each step "consumes" the words it understood):
  1. normalise: lower case, regional words -> standard ("hông" -> "không", "mắc" -> "đắt")
  2. typo correction against the shop vocabulary ("hodie" -> "hoodie")
  3. order intent ("đơn DH002", "đơn gần nhất của tui đâu")
  4. price: "dưới 100k", "trên 2 triệu", "từ 200 đến 500 nghìn", "tầm 300k",
            "1tr5 đổ lại", "trăm rưỡi", "hai trăm nghìn trở lên"
  5. phrases from the lexicon, longest first: category, colour, gender, material,
     pattern, design detail, occasion, sort order, unsupported products
  6. the remaining words become free keywords for BM25; unknown words lower
     the confidence, and a low confidence lets QueryService ask Gemini.
Runs in about a millisecond.
"""
import difflib
import re
import time

from application import lexicon as L
from shared.vietnamese import has_accents, normalize, strip_accents, tokenize

# ------------------------------------------------------------------ lexicon
KIND_ORDER = ["unsupported", "category", "occasion", "sort", "in_stock", "color",
              "color_group", "gender", "material", "pattern", "feature"]


def _build_entries():
    entries = []

    def add(kind, value, aliases):
        for alias in aliases:
            entries.append((tuple(tokenize(alias)), kind, value))

    for value, aliases in L.UNSUPPORTED.items():
        add("unsupported", value, aliases)
    for value, aliases in L.CATEGORIES.items():
        add("category", value, aliases)
    for value, aliases in L.OCCASIONS.items():
        add("occasion", value, aliases)
    for value, aliases in L.SORTS.items():
        add("sort", value, aliases)
    add("in_stock", True, L.IN_STOCK)
    for value, aliases in L.COLORS.items():
        add("color", value, aliases)
    for value in L.GENERIC_COLORS:
        add("color_group", value, [value])
    for value, aliases in L.GENDERS.items():
        add("gender", value, aliases)
    for value, aliases in L.MATERIALS.items():
        add("material", value, aliases)
    for value, aliases in L.PATTERNS.items():
        add("pattern", value, aliases)
    for value, aliases in L.FEATURES.items():
        add("feature", value, aliases)
    # longest phrase first; for equal length the order of KIND_ORDER
    entries.sort(key=lambda e: (-len(e[0]), KIND_ORDER.index(e[1])))
    return entries


ENTRIES = _build_entries()
ALIAS_WORDS = {strip_accents(t) for phrase, _, _ in ENTRIES for t in phrase if len(t) >= 4}
STOP_UN = {strip_accents(w) for w in L.STOP_WORDS}
CONTEXT_KINDS = {"category", "color", "material", "feature", "pattern", "gender"}
CONTEXT_WORDS = {"mau", "chat", "vai", "bang", "hang", "kieu", "gia", "loai"}
CONTEXT_ALLOWED = {"color", "material", "pattern", "feature", "sort"}   # others never guess
NEEDS_CONTEXT = {"da"}               # "da" (leather) only after "áo", "quần", "chất"...

# ------------------------------------------------------------------ price
U_MIL, U_K, U_LIT, U_VND = r"tr|trieu|cu|m", r"k|nghin|ng|ngh", r"lit|xi", r"d|dong|vnd"
NUMBER_WORDS = {"một": 1, "mot": 1, "hai": 2, "ba": 3, "bốn": 4, "bon": 4, "tư": 4,
                "năm": 5, "lăm": 5, "sáu": 6, "sau": 6, "bảy": 7, "bay": 7, "bẩy": 7,
                "tám": 8, "chín": 9, "chin": 9, "mười": 10, "muoi": 10}


def A(p):
    """Regex of one amount of money; p prefixes the group names."""
    return (rf"(?<![\w.])(?P<{p}n>\d+(?:[.,]\d+)*)"
            rf"(?:\s(?P<{p}u>{U_MIL}|{U_K}|{U_LIT}|{U_VND})(?=\s|$))?"
            rf"(?:\s(?P<{p}f>\d{{1,3}})(?=\s|$)(?!\s(?:{U_MIL}|{U_K}|{U_LIT})(?:\s|$)))?"
            rf"(?:\s(?P<{p}r>ruoi))?")


NEG = r"(?:khong|ko|k|hong|hok|hem|khum|chua)"
PRICE_PATTERNS = [
    ("range", rf"(?:(?:tu|khoang|tam|trong khoang|chung|gia tu|tu gia|tam gia)\s)?{A('a')}"
              rf"\s(?:den|toi|-|–|~|cho den|cho toi)\s{A('b')}"),
    ("max", rf"{A('a')}\s(?:do lai|tro xuong|tro lai|doi lai|do xuong|thoi|tro ve|la toi da|max)"
            rf"(?=\s|$)"),
    ("min", rf"{A('a')}\s(?:tro len|do len|tro di|tro ra)(?=\s|$)"),
    ("max", rf"(?:duoi|nho hon|it hon|be hon|re hon|thap hon|{NEG}\s(?:qua|vuot qua|hon|toi|den)"
            rf"|toi da|max|gioi han|<=|<)\s(?:gia\s)?{A('a')}"),
    ("min", rf"(?:tren|hon|lon hon|nhieu hon|cao hon|dat hon|it nhat|toi thieu|min|>=|>"
            rf"|{NEG}\sduoi|tu)\s(?:gia\s)?{A('a')}"),
    ("approx", rf"(?:tam|khoang|chung|tam tam|gia|tam gia|khoang gia|ngan sach|budget)"
               rf"\s{A('a')}"),
    ("bare", A("a")),
]
PRICE_RES = [(kind, re.compile(p)) for kind, p in PRICE_PATTERNS]
NOT_PRICE_BEFORE = {"size", "co", "so", "ma", "don", "dh", "sz"}
ORDER_ID_RE = re.compile(r"\b(dh\s?-?\d{3,})\b")
NUMBER_ID_RE = re.compile(r"\b(\d{5,12})\b")


def fmt_vnd(v):
    return f"{int(v):,}".replace(",", ".") + "₫"


class RuleParser:

    def __init__(self, vocabulary=None, category_names=None):
        self.vocabulary = set(vocabulary or ())
        self.category_names = category_names or {}
        self._correct_pool = sorted(ALIAS_WORDS | {w for w in self.vocabulary if len(w) >= 4})
    def parse(self, text):
        start = time.perf_counter()
        raw = (text or "").strip()
        toks = tokenize(raw)
        notes = []
        std = []
        for t in toks:
            s = L.DIALECT.get(t, t)
            if s != t:
                notes.append({"kind": "dialect", "text": t, "label": f"{t} → {s}"})
            std.extend(s.split())
        toks = []
        for t in std:
            if t == "lạnh" and toks[-1:] == ["thun"] and toks[-2:-1] != ["vải"]:
                toks += ["vải", "thun", "lạnh"]
            else:
                toks.append(t)
        # 2. typo correction
        toks = self._correct(toks, notes)
        un = [strip_accents(t) for t in toks]

        query = {"query": raw, "normalized": " ".join(toks), "intent": "product",
                 "categories": [], "genders": [], "colors": [], "materials": [],
                 "patterns": [], "brands": [], "features": [], "occasions": [],
                 "min_price": None, "max_price": None, "sort": None, "in_stock": False,
                 "keywords": [], "unsupported": [], "understood": notes, "parser": "rule"}

        # 3. order intent
        order = self._order(" ".join(toks), " ".join(un), toks)
        if order:
            query.update(order)
            query["confidence"] = 1.0
            query["understood"].append({"kind": "order", "label": order["label"]})
            query["parse_ms"] = round((time.perf_counter() - start) * 1000, 2)
            return query

        used = [False] * len(toks)
        kinds = [None] * len(toks)
        understood = 0
        understood += self._price(toks, un, used, kinds, query)
        i = 0
        while i < len(toks):
            if used[i]:
                i += 1
                continue
            hit = self._match_at(i, toks, un, used, kinds)
            if not hit:
                i += 1
                continue
            phrase, kind, value = hit
            span = " ".join(toks[i:i + len(phrase)])
            for k in range(i, i + len(phrase)):
                used[k], kinds[k] = True, kind
            self._apply(query, kind, value, span)
            understood += 1
            i += len(phrase)
        self._post_process(query)

        # 6. remaining words
        unknown = []
        for i, t in enumerate(toks):
            if used[i] or not t.isalnum() or t.isdigit():
                continue
            if t in L.STOP_WORDS or un[i] in STOP_UN:
                continue
            if un[i] in self.vocabulary:
                query["keywords"].append(un[i])
            else:
                unknown.append(t)
        query["unknown"] = unknown
        known = len(query["keywords"])
        total = understood + known + len(unknown)
        query["confidence"] = round((understood + 0.6 * known) / total, 2) if total else 0.0
        if query["unsupported"] and not query["categories"]:
            query["intent"] = "unsupported"
        elif total == 0 or (understood == 0 and known == 0):
            query["intent"] = "unknown"
        query["keywords"] = query["features"] + query["keywords"]
        query["parse_ms"] = round((time.perf_counter() - start) * 1000, 2)
        return query
    def _correct(self, toks, notes):
        out = []
        for t in toks:
            u = strip_accents(t)
            if (len(u) >= 4 and t.isalpha() and not has_accents(t) and u not in self.vocabulary
                    and u not in ALIAS_WORDS and u not in STOP_UN):
                close = difflib.get_close_matches(u, self._correct_pool, n=1, cutoff=0.8)
                if close and close[0] != u:
                    notes.append({"kind": "typo", "text": t, "label": f"{t} → {close[0]}"})
                    out.append(close[0])
                    continue
            out.append(t)
        return out

    def _order(self, acc, un, toks):
        m = ORDER_ID_RE.search(un)
        context = (re.search(r"\bđơn\b(?!\s*(?:sắc|giản|điệu|lẻ|thuần|giá))", acc)
                   or re.search(r"\b(?:don hang|order|van don|kien hang|giao hang|dat hang"
                                r"|ma don|theo doi don|tinh trang don)\b", un)
                   or re.search(r"\bhang\s(?:cua\s)?(?:toi|minh|em|to)\s(?:dau|toi dau|den dau"
                                r"|giao chua|bao gio|o dau)", un)
                   or (not any(has_accents(t) for t in toks)
                       and re.search(r"\bdon\b(?=\s(?:dh|\d|cua|gan|moi|vua|toi|minh|em|da"
                                     r"|dang|nao|so))", un)))
        if m:
            oid = re.sub(r"[\s-]", "", m.group(1)).upper()
            return {"intent": "order", "order_id": oid, "label": f"Tra cứu đơn {oid}"}
        if not context:
            return None
        m = NUMBER_ID_RE.search(un)
        if m:
            return {"intent": "order", "order_id": m.group(1), "label": f"Tra cứu đơn {m.group(1)}"}
        if any(strip_accents(p) in un for p in L.ORDER_ALL):
            return {"intent": "order", "all_orders": True, "label": "Danh sách đơn hàng của bạn"}
        return {"intent": "order", "latest": True, "label": "Đơn hàng gần nhất của bạn"}

    # ------------------------------------------------------------ price
    def _price(self, toks, un, used, kinds, query):
        # word numbers -> digits ("hai trăm" -> 200, "trăm" -> 100, "nửa triệu" -> 0.5 triệu)
        ptoks = []                                   # (text, [token indexes])
        i = 0
        while i < len(toks):
            t, u = toks[i], un[i]
            nxt = un[i + 1] if i + 1 < len(toks) else ""
            unaccented_query = not any(has_accents(x) for x in toks)
            if (t in NUMBER_WORDS or (u in NUMBER_WORDS and not unaccented_query)) \
                    and nxt in ("tram", "chuc"):
                n = NUMBER_WORDS.get(t, NUMBER_WORDS.get(u))
                ptoks.append((str(n * (100 if nxt == "tram" else 10)), [i, i + 1]))
                i += 2
                continue
            if (t in NUMBER_WORDS or u in ("hai", "mot", "bon", "sau", "bay", "chin", "muoi")) \
                    and re.fullmatch(U_MIL + "|" + U_K, nxt or "-"):
                ptoks.append((str(NUMBER_WORDS.get(t, NUMBER_WORDS.get(u))), [i]))
                i += 1
                continue
            if u == "tram" and re.fullmatch(f"{U_K}|ruoi", nxt or "-"):
                ptoks.append(("100", [i]))
                i += 1
                continue
            if u == "nua" and re.fullmatch(U_MIL, nxt or "-"):
                ptoks.append(("0.5", [i]))
                i += 1
                continue
            ptoks.append((u, [i]))
            i += 1
        text, starts = "", []
        for pt, _ in ptoks:
            starts.append(len(text))
            text += pt + " "
        text = text.rstrip()

        def tok_range(a, b):
            idx = [j for j, s in enumerate(starts) if a <= s < b]
            return [k for j in idx for k in ptoks[j][1]]

        masked = text
        found = 0
        for kind, rx in PRICE_RES:
            for m in rx.finditer(masked):
                prev = masked[:m.start()].split()[-1:] or [""]
                if prev[0] in NOT_PRICE_BEFORE:
                    continue
                if kind == "range":
                    unit_b = m.group("bu")
                    lo = self._amount(m, "a", inherit=unit_b)
                    hi = self._amount(m, "b", inherit=m.group("au"))
                    if lo is None or hi is None:
                        continue
                    lo, hi = min(lo, hi), max(lo, hi)
                    query["min_price"], query["max_price"] = lo, hi
                    label = f"Giá {fmt_vnd(lo)} – {fmt_vnd(hi)}"
                else:
                    if kind == "bare" and not m.group("au"):
                        continue                     # a lone number is not a price
                    v = self._amount(m, "a")
                    if v is None:
                        continue
                    if kind == "max":
                        query["max_price"], label = v, f"Dưới {fmt_vnd(v)}"
                    elif kind == "min":
                        query["min_price"], label = v, f"Trên {fmt_vnd(v)}"
                    else:
                        lo, hi = int(round(v * 0.8, -3)), int(round(v * 1.2, -3))
                        query["min_price"], query["max_price"] = lo, hi
                        label = f"Khoảng {fmt_vnd(v)}"
                idx = tok_range(m.start(), m.end())
                for k in idx:
                    used[k], kinds[k] = True, "price"
                span = " ".join(toks[k] for k in sorted(set(idx)))
                query["understood"].append({"kind": "price", "text": span, "label": label})
                masked = masked[:m.start()] + "#" * (m.end() - m.start()) + masked[m.end():]
                found += 1
        return found

    @staticmethod
    def _amount(m, p, inherit=None):
        n = m.group(f"{p}n")
        unit = m.group(f"{p}u") or inherit
        frac, ruoi = m.group(f"{p}f"), m.group(f"{p}r")
        if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", n):          # 500.000 / 1,200,000
            value = float(re.sub(r"[.,]", "", n))
        else:
            value = float(n.replace(",", "."))
        mult = None
        if unit and re.fullmatch(U_MIL, unit):
            mult = 1_000_000
            if frac:
                value += int(frac) / 10 ** len(frac)
        elif unit and re.fullmatch(U_K, unit):
            mult = 1_000
        elif unit and re.fullmatch(U_LIT, unit):
            mult = 100_000
        if ruoi:
            value += 50 if (value >= 100 and mult != 1_000_000) else 0.5
        if mult is None:                       # no unit: "dưới 500" means 500 nghìn
            mult = 1 if value >= 10_000 else 1_000
        amount = int(round(value * mult))
        return amount if 1_000 <= amount <= 1_000_000_000 else None

    # ---------------------------------------------------------- phrases
    def _match_at(self, i, toks, un, used, kinds):
        n = len(toks)
        for phrase, kind, value in ENTRIES:
            size = len(phrase)
            if i + size > n or any(used[i:i + size]):
                continue
            via_unaccent = False
            for k, syllable in enumerate(phrase):
                t = toks[i + k]
                if t == syllable:
                    continue
                if not has_accents(t) and strip_accents(syllable) == t:
                    via_unaccent = True
                    continue
                break
            else:
                if size == 1:
                    ambiguous = (via_unaccent and un[i] in L.AMBIGUOUS) or phrase[0] in NEEDS_CONTEXT
                    if ambiguous and (kind not in CONTEXT_ALLOWED
                                      or not self._context_ok(i, un, kinds)):
                        continue
                return phrase, kind, value
        return None

    @staticmethod
    def _context_ok(i, un, kinds):
        return i > 0 and (kinds[i - 1] in CONTEXT_KINDS or un[i - 1] in CONTEXT_WORDS)

    def _apply(self, q, kind, value, span):
        add = lambda key, v: q[key].append(v) if v not in q[key] else None
        label = None
        if kind == "category":
            add("categories", value)
            label = self.category_names.get(value, span.capitalize())
        elif kind == "unsupported":
            add("unsupported", value)
            label = f"Shop không bán {value}"
        elif kind == "color":
            add("colors", value)
            label = f"Màu {value}"
        elif kind == "color_group":
            for c in L.GENERIC_COLORS[value]:
                add("colors", c)
            label = "Màu xanh (mọi tông)"
        elif kind == "gender":
            add("genders", value)
            label = "Nam" if value == "nam" else "Nữ"
        elif kind == "material":
            add("materials", value)
            label = f"Chất {value}"
        elif kind == "pattern":
            add("patterns", value)
            label = value.capitalize()                  # "Kẻ sọc", "Họa tiết", "Trơn"
        elif kind == "feature":
            add("features", value)
            label = value.capitalize()
        elif kind == "occasion":
            add("occasions", value)
            label = f"Dịp: {value}"
        elif kind == "sort":
            q["sort"] = value
            label = {"price_asc": "Giá thấp → cao", "price_desc": "Giá cao → thấp",
                     "popular": "Bán chạy", "newest": "Mới nhất"}[value]
        elif kind == "in_stock":
            q["in_stock"] = True
            label = "Còn hàng"
        q["understood"].append({"kind": kind, "text": span, "label": label, "value": value})

    def _post_process(self, q):
        # occasions stay occasions: the products carry their own occasion labels
        # "áo lửng" is a crop top, "quần lửng" is cropped trousers
        if "lửng" in q["features"] and q["categories"] and all(
                c.startswith("ao") for c in q["categories"]):
            q["features"] = ["croptop" if f == "lửng" else f for f in q["features"]]
        # a parent and its child given together: keep the child ("áo áo phông")
        for parent in ("ao", "quan"):
            if parent in q["categories"] and any(
                    c.startswith(parent + "_") for c in q["categories"]):
                q["categories"].remove(parent)
