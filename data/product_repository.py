"""Data Layer - ProductRepository.

The only component that reads the product and category tables and the
image storage (data/catalog/images). Upper layers never write SQL.
"""
import os

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

PRODUCT_COLUMNS = """
    p.product_id, p.category_id, c.name AS category_name, c.parent_id AS category_parent,
    p.name, p.brand, p.gender, p.price, p.stock, p.color, p.color_detail, p.material,
    p.pattern, p.description, p.description_en, p.image_path,
    p.popularity::float AS popularity, p.occasions, p.source_url, p.created_at
"""


class ProductRepository:

    def __init__(self, db):
        self.db = db
        self._products = None
        self._by_id = None

    # ---------------------------------------------------------- catalogue
    def all_products(self):
        if self._products is None:
            self._products = self.db.query(
                f"SELECT {PRODUCT_COLUMNS} FROM product p "
                f"JOIN category c USING (category_id) ORDER BY p.product_id")
            self._by_id = {p["product_id"]: p for p in self._products}
        return self._products

    def get_product(self, product_id):
        self.all_products()
        return self._by_id.get(int(product_id))

    def image_path(self, product):
        return os.path.join(DATA_DIR, product["image_path"])

    def categories(self):
        """Category tree as rows with the number of products in each."""
        return self.db.query("""
            SELECT c.category_id, c.parent_id, c.name, count(p.product_id) AS products
            FROM category c LEFT JOIN product p USING (category_id)
            GROUP BY c.category_id ORDER BY c.parent_id NULLS FIRST, c.name""")

    def values(self, column):
        assert column in ("brand", "color", "material", "pattern")
        return [r["v"] for r in self.db.query(
            f"SELECT DISTINCT {column} AS v FROM product WHERE {column} IS NOT NULL ORDER BY 1")]
    def find(self, categories=None, genders=None, colors=None, materials=None,
             patterns=None, brands=None, min_price=None, max_price=None, in_stock=False,
             occasions=None, fuzzy_terms=None):
        where, params = [], {}
        if categories:
            where.append("p.category_id IN (SELECT category_id FROM cats)")
            params["cats"] = list(categories)
        if genders:
            where.append("p.gender = ANY(%(genders)s)")
            params["genders"] = list(genders) + ["unisex"]
        for column, values in (("color", colors), ("material", materials),
                               ("pattern", patterns), ("brand", brands)):
            if values:
                where.append(f"p.{column} = ANY(%({column}s)s)")
                params[f"{column}s"] = list(values)
        if min_price is not None:
            where.append("p.price >= %(min_price)s")
            params["min_price"] = int(min_price)
        if max_price is not None:
            where.append("p.price <= %(max_price)s")
            params["max_price"] = int(max_price)
        if in_stock:
            where.append("p.stock > 0")
        if occasions:
            where.append("p.occasions @> %(occasions)s::text[]")
            params["occasions"] = list(occasions)
        fuzzy = "0.0"
        if fuzzy_terms:
            fuzzy = ("(SELECT avg(word_similarity(t, p.search_doc)) "
                     "FROM unnest(%(terms)s::text[]) AS t)")
            params["terms"] = list(fuzzy_terms)
        sql = f"""
            WITH RECURSIVE cats AS (
                SELECT category_id FROM category WHERE category_id = ANY(%(cats)s)
                UNION
                SELECT c.category_id FROM category c JOIN cats ON c.parent_id = cats.category_id
            )
            SELECT p.product_id, {fuzzy}::float AS trgm
            FROM product p
            {'WHERE ' + ' AND '.join(where) if where else ''}"""
        params.setdefault("cats", [])
        return {r["product_id"]: r["trgm"] or 0.0 for r in self.db.query(sql, params)}
