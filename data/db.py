"""Data Layer - PostgreSQL connection shared by the repositories."""
import psycopg
from psycopg.rows import dict_row


class Database:

    def __init__(self, url):
        self.url = url
        self._conn = None

    def connection(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(self.url, row_factory=dict_row, autocommit=True)
        return self._conn

    def query(self, sql, params=None):
        with self.connection().cursor() as cur:
            cur.execute(sql, params or {})
            return cur.fetchall()

    def query_one(self, sql, params=None):
        rows = self.query(sql, params)
        return rows[0] if rows else None
