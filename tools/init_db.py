"""Create the PostgreSQL database, the schema (data/schema.sql) and the sample data.

    python main.py --init-db          (or: python tools/init_db.py)
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta

import psycopg
from psycopg import sql

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402

CATEGORIES = [
    ("ao", None, "Áo", "Tất cả các loại áo"),
    ("quan", None, "Quần", "Tất cả các loại quần"),
    ("ao_phong", "ao", "Áo phông", "Áo phông, áo thun cổ tròn / cổ tim"),
    ("ao_polo", "ao", "Áo polo", "Áo thun có cổ bẻ"),
    ("ao_so_mi", "ao", "Áo sơ mi", "Sơ mi dài tay và ngắn tay"),
    ("ao_kieu", "ao", "Áo kiểu", "Áo blouse, áo kiểu nữ"),
    ("ao_hai_day", "ao", "Áo hai dây", "Áo hai dây, áo ba lỗ"),
    ("ao_len", "ao", "Áo len", "Áo len, áo dệt kim"),
    ("ao_ni", "ao", "Áo nỉ", "Áo nỉ, sweatshirt"),
    ("ao_hoodie", "ao", "Áo hoodie", "Áo nỉ có mũ"),
    ("ao_cardigan", "ao", "Áo cardigan", "Áo len cài khuy"),
    ("ao_khoac", "ao", "Áo khoác", "Áo khoác, áo jacket, măng tô"),
    ("ao_blazer", "ao", "Áo blazer", "Áo blazer, áo vest"),
    ("quan_jeans", "quan", "Quần jeans", "Quần jeans, quần bò"),
    ("quan_dai", "quan", "Quần dài", "Quần kaki, chino, ống rộng"),
    ("quan_au", "quan", "Quần âu", "Quần âu, quần tây công sở"),
    ("quan_jogger", "quan", "Quần jogger", "Quần jogger, quần nỉ"),
    ("quan_short", "quan", "Quần short", "Quần short, quần đùi"),
    ("quan_legging", "quan", "Quần legging", "Quần legging tập luyện"),
]

CUSTOMERS = [
    ("C001", "Nguyễn Minh Anh", "minhanh@example.com", "0901 234 567",
     "12 Nguyễn Trãi, Thanh Xuân, Hà Nội"),
    ("C002", "Trần Thu Hà", "thuha@example.com", "0912 345 678",
     "45 Lê Lợi, Hải Châu, Đà Nẵng"),
    ("C003", "Lê Hoàng Nam", "hoangnam@example.com", None,
     "88 Nguyễn Thị Minh Khai, Quận 3, TP. Hồ Chí Minh"),
]

# (order_id, customer, date, status, payment method, payment status)
ORDERS = [
    ("DH001", "C001", "2026-08-02 10:15", "Đã giao", "Chuyển khoản", "Đã thanh toán"),
    ("DH002", "C002", "2026-08-11 20:40", "Đã giao", "COD", "Đã thanh toán"),
    ("DH003", "C003", "2026-08-25 08:05", "Đã giao", "Ví MoMo", "Đã thanh toán"),
    ("DH004", "C001", "2026-09-15 21:30", "Đã giao", "Thẻ Visa", "Đã thanh toán"),
    ("DH005", "C002", "2026-09-20 12:00", "Đã hủy", "Ví MoMo", "Đã hoàn tiền"),
    ("DH006", "C003", "2026-09-28 19:10", "Đã giao", "COD", "Đã thanh toán"),
    ("DH007", "C001", "2026-10-05 09:45", "Đã hủy", "COD", "Đã hủy"),
    ("DH008", "C002", "2026-10-12 16:20", "Đang giao", "Chuyển khoản", "Đã thanh toán"),
    ("DH009", "C003", "2026-10-16 11:00", "Đang chuẩn bị hàng", "Thẻ Visa", "Đã thanh toán"),
    ("DH010", "C001", "2026-10-19 22:05", "Đang giao", "COD", "Chờ thanh toán"),
    ("DH011", "C002", "2026-10-20 14:35", "Chờ xác nhận", "COD", "Chờ thanh toán"),
    ("DH012", "C003", "2026-10-21 07:50", "Chờ xác nhận", "Ví MoMo", "Đã thanh toán"),
]


def create_database(url):
    info = psycopg.conninfo.conninfo_to_dict(url)
    name = info.get("dbname", "snapshop")
    admin = psycopg.conninfo.make_conninfo(url, dbname="postgres")
    with psycopg.connect(admin, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            print(f"created database {name}")


def init_database(url=config.DATABASE_URL,
                  catalog=os.path.join(ROOT, "data", "catalog", "products.json")):
    create_database(url)
    with open(catalog, encoding="utf-8") as f:
        products = json.load(f)
    rng = random.Random(7)
    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        with open(os.path.join(ROOT, "data", "schema.sql"), encoding="utf-8") as f:
            cur.execute(f.read())
        cur.executemany("INSERT INTO category VALUES (%s, %s, %s, %s)", CATEGORIES)
        cur.executemany("""
            INSERT INTO product (product_id, category_id, name, brand, gender, price, stock,
                color, color_detail, material, pattern, description, description_en,
                image_path, popularity, occasions, source_url, created_at)
            VALUES (%(product_id)s, %(category_id)s, %(name)s, %(brand)s, %(gender)s,
                %(price)s, %(stock)s, %(color)s, %(color_detail)s, %(material)s, %(pattern)s,
                %(description)s, %(description_en)s, %(image_path)s, %(popularity)s,
                %(occasions)s, %(source_url)s, %(created_at)s)""",
            [dict(p, occasions=p.get("occasions", [])) for p in products])
        cur.executemany("INSERT INTO customer (customer_id, full_name, email, phone, address, "
                        "created_at) VALUES (%s, %s, %s, %s, %s, '2026-01-10')", CUSTOMERS)
        address = {c[0]: c[4] for c in CUSTOMERS}
        for i, (oid, cid, date, status, method, pay_status) in enumerate(ORDERS):
            items = rng.sample(products, rng.randint(1, 3))
            lines = [(p["product_id"], rng.choice([1, 1, 1, 2]), p["price"]) for p in items]
            total = sum(q * price for _, q, price in lines) + 30_000      # + shipping
            cur.execute("INSERT INTO orders VALUES (%s, %s, %s, %s, %s, %s)",
                        (oid, cid, date, total, status, address[cid]))
            cur.executemany("INSERT INTO order_item (order_id, product_id, quantity, unit_price) "
                            "VALUES (%s, %s, %s, %s)", [(oid, *line) for line in lines])
            paid = None if pay_status in ("Chờ thanh toán", "Đã hủy") else \
                datetime.fromisoformat(date) + timedelta(minutes=5)
            cur.execute("INSERT INTO payment VALUES (%s, %s, %s, %s, %s, %s)",
                        (f"PM{i + 1:03d}", oid, method, paid, total, pay_status))
        conn.commit()
    print(f"database ready: {len(CATEGORIES)} categories, {len(products)} products, "
          f"{len(CUSTOMERS)} customers, {len(ORDERS)} orders")


if __name__ == "__main__":
    init_database()
