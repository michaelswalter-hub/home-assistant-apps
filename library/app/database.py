import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS series (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

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
    rating INTEGER NOT NULL DEFAULT 0,
    genres TEXT,
    series_id TEXT,
    series_index REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(series_id) REFERENCES series(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
CREATE INDEX IF NOT EXISTS idx_books_isbn ON books(isbn);


CREATE TABLE IF NOT EXISTS genres (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    hidden INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS book_genres (
    book_id TEXT NOT NULL,
    genre_id TEXT NOT NULL,
    PRIMARY KEY (book_id, genre_id),
    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE,
    FOREIGN KEY(genre_id) REFERENCES genres(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_book_genres_book ON book_genres(book_id);
CREATE INDEX IF NOT EXISTS idx_book_genres_genre ON book_genres(genre_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            self._migrate(conn)

    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate(self, conn):
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(books)").fetchall()
        }
        if "series_id" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN series_id TEXT")
        if "series_index" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN series_index REAL")
        if "genres" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN genres TEXT")
        if "rating" not in columns:
            conn.execute("ALTER TABLE books ADD COLUMN rating INTEGER NOT NULL DEFAULT 0")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_books_series ON books(series_id, series_index)"
        )
        conn.commit()

    def list_books(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT b.*, s.name AS series_name
                FROM books b
                LEFT JOIN series s ON s.id = b.series_id
                ORDER BY lower(b.title), lower(COALESCE(b.author, ''))
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_book(self, book_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT b.*, s.name AS series_name
                FROM books b
                LEFT JOIN series s ON s.id = b.series_id
                WHERE b.id = ?
                """,
                (book_id,),
            ).fetchone()
        return dict(row) if row else None

    def get_by_hash(self, sha256: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT b.*, s.name AS series_name
                FROM books b
                LEFT JOIN series s ON s.id = b.series_id
                WHERE b.sha256 = ?
                """,
                (sha256,),
            ).fetchone()
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

    def list_series(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.*, COUNT(b.id) AS book_count
                FROM series s
                LEFT JOIN books b ON b.series_id = s.id
                GROUP BY s.id
                ORDER BY lower(s.name)
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_series(self, series_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT s.*, COUNT(b.id) AS book_count
                FROM series s
                LEFT JOIN books b ON b.series_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (series_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_series(self, series: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO series (id, name, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    series["id"],
                    series["name"],
                    series.get("description"),
                    series["created_at"],
                    series["updated_at"],
                ),
            )
            conn.commit()

    def update_series(self, series_id: str, values: dict[str, Any]) -> None:
        if not values:
            return
        columns = list(values.keys())
        assignments = ", ".join(f"{col} = ?" for col in columns)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE series SET {assignments} WHERE id = ?",
                [values[col] for col in columns] + [series_id],
            )
            conn.commit()

    def delete_series(self, series_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE books SET series_id = NULL, series_index = NULL WHERE series_id = ?",
                (series_id,),
            )
            conn.execute("DELETE FROM series WHERE id = ?", (series_id,))
            conn.commit()

    def get_setting(self, key: str, default: Any = None) -> Any:
        import json
        with self.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        import json
        encoded = json.dumps(value, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, encoded),
            )
            conn.commit()

    def list_genres(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT g.*, COUNT(bg.book_id) AS book_count
                FROM genres g
                LEFT JOIN book_genres bg ON bg.genre_id = g.id
                GROUP BY g.id
                ORDER BY lower(g.name)
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_genre(self, genre_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT g.*, COUNT(bg.book_id) AS book_count
                FROM genres g
                LEFT JOIN book_genres bg ON bg.genre_id = g.id
                WHERE g.id = ?
                GROUP BY g.id
                """,
                (genre_id,),
            ).fetchone()
        return dict(row) if row else None

    def create_genre(self, genre: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO genres (id, name, hidden, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    genre["id"],
                    genre["name"],
                    int(bool(genre.get("hidden"))),
                    genre["created_at"],
                    genre["updated_at"],
                ),
            )
            conn.commit()

    def update_genre(self, genre_id: str, values: dict[str, Any]) -> None:
        if not values:
            return
        columns = list(values.keys())
        assignments = ", ".join(f"{col} = ?" for col in columns)
        encoded = []
        for col in columns:
            value = values[col]
            if col == "hidden":
                value = int(bool(value))
            encoded.append(value)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE genres SET {assignments} WHERE id = ?",
                encoded + [genre_id],
            )
            conn.commit()

    def delete_genre(self, genre_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM book_genres WHERE genre_id = ?", (genre_id,))
            conn.execute("DELETE FROM genres WHERE id = ?", (genre_id,))
            conn.commit()

    def get_book_genres(self, book_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT g.*
                FROM genres g
                INNER JOIN book_genres bg ON bg.genre_id = g.id
                WHERE bg.book_id = ?
                ORDER BY lower(g.name)
                """,
                (book_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_book_genres(self, book_id: str, genre_ids: list[str]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM book_genres WHERE book_id = ?", (book_id,))
            for genre_id in genre_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO book_genres (book_id, genre_id) VALUES (?, ?)",
                    (book_id, genre_id),
                )
            conn.commit()
