import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    subtitle TEXT,
    author TEXT,
    description TEXT,
    isbn TEXT,
    publisher TEXT,
    published_date TEXT,
    language TEXT,
    format TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    storage_path TEXT NOT NULL,
    cover_path TEXT,
    sha256 TEXT NOT NULL UNIQUE,
    metadata_source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON books(isbn);
"""

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_books(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM books ORDER BY lower(title), lower(COALESCE(author, ''))"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_book(self, book_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None

    def get_by_hash(self, sha256: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM books WHERE sha256 = ?", (sha256,)).fetchone()
        return dict(row) if row else None

    def insert_book(self, book: dict[str, Any]) -> None:
        columns = list(book.keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO books ({', '.join(columns)}) VALUES ({placeholders})"
        with self.connect() as conn:
            conn.execute(sql, [book[col] for col in columns])
            conn.commit()

    def update_book(self, book_id: str, values: dict[str, Any]) -> None:
        if not values:
            return
        columns = list(values.keys())
        assignments = ", ".join(f"{col} = ?" for col in columns)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE books SET {assignments} WHERE id = ?",
                [values[col] for col in columns] + [book_id],
            )
            conn.commit()
