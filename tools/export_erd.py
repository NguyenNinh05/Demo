"""Generate the ERD of the PostgreSQL database as a Mermaid diagram (docs/erd.md).

    python tools/export_erd.py

The diagram is read from the live database (information_schema), so it is
always in sync with data/schema.sql. VS Code, GitHub and most Markdown viewers
render Mermaid; DBeaver / pgAdmin / Visual Paradigm can also reverse-engineer
the same database.
"""
import os
import sys

import psycopg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import config  # noqa: E402

COLUMNS = """
SELECT c.table_name, c.column_name, c.data_type, c.is_nullable,
       c.character_maximum_length, c.numeric_precision, c.numeric_scale
FROM information_schema.columns c
JOIN information_schema.tables t USING (table_schema, table_name)
WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE'
ORDER BY c.table_name, c.ordinal_position"""

KEYS = """
SELECT tc.table_name, kcu.column_name, tc.constraint_type,
       ccu.table_name AS ref_table
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
LEFT JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name AND tc.constraint_type = 'FOREIGN KEY'
WHERE tc.table_schema = 'public' AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')"""


def type_of(row):
    t = row[2].replace("character varying", "varchar").replace("timestamp without time zone",
                                                                "timestamp")
    if row[4]:
        t += f"({row[4]})"
    elif t == "numeric" and row[5]:
        t += f"({row[5]},{row[6]})"
    return t.replace(" ", "_")


def main():
    with psycopg.connect(config.DATABASE_URL) as conn:
        cols = conn.execute(COLUMNS).fetchall()
        keys = conn.execute(KEYS).fetchall()
    pk = {(t, c) for t, c, k, _ in keys if k == "PRIMARY KEY"}
    fk = {(t, c): ref for t, c, k, ref in keys if k == "FOREIGN KEY"}
    lines = ["```mermaid", "erDiagram"]
    for table in dict.fromkeys(r[0] for r in cols):
        lines.append(f"    {table} {{")
        for r in (r for r in cols if r[0] == table):
            mark = "PK" if (table, r[1]) in pk else "FK" if (table, r[1]) in fk else ""
            null = '"nullable"' if r[3] == "YES" and not mark else ""
            lines.append(f"        {type_of(r)} {r[1]} {mark} {null}".rstrip())
        lines.append("    }")
    for (table, col), ref in sorted(fk.items()):
        nullable = any(r[0] == table and r[1] == col and r[3] == "YES" for r in cols)
        parent = "|o" if nullable else "||"          # self reference category.parent_id is optional
        lines.append(f'    {ref} {parent}--o{{ {table} : "{col}"')
    lines.append("```")
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    path = os.path.join(ROOT, "docs", "erd.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("# SnapShop - ERD (sinh tự động từ PostgreSQL)\n\n" + "\n".join(lines) + "\n")
    print(f"written {path}")


if __name__ == "__main__":
    main()
