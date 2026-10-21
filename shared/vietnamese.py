"""Vietnamese text helpers shared by the Application and Data layers.

Every search term is compared without accents ("áo sơ mi" -> "ao so mi"),
so a customer who types without diacritics gets the same products.
"""
import re
import unicodedata

TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+|[<>~–-]", re.UNICODE)


def strip_accents(text):
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def has_accents(token):
    return strip_accents(token) != token


def normalize(text):
    text = unicodedata.normalize("NFC", str(text)).lower()
    text = re.sub(r"\bt[\s-]?shirts?\b", "tshirt", text)
    return text


def tokenize(text):
    """Lower-case tokens with accents kept; digits and letters are split ("100k" -> 100, k)."""
    return TOKEN_RE.findall(normalize(text))


def search_terms(text):
    """Accent-free unigrams + bigrams, the vocabulary of the text index."""
    words = [strip_accents(t) for t in tokenize(text) if t.isalnum()]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]
