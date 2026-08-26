from __future__ import annotations

import hashlib
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory

from database import Database
from metadata import download_cover, enrich_metadata, extract_local_metadata

DATA_DIR = Path(os.environ.get("LIBRARY_DATA_DIR", "/data/library"))
BOOKS_DIR = DATA_DIR / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("LIBRARY_MAX_UPLOAD_MB", "1024"))
METADATA_LANGUAGE = os.environ.get("LIBRARY_METADATA_LANGUAGE", "de")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
db = Database(DATA_DIR / "library.db")

ALLOWED_EXTENSIONS = {".epub", ".pdf"}

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()

def clean_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9ÄÖÜäöüß._() \-]+", "_", name).strip()
    return name or "book"

def title_from_filename(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[_]+", " ", stem)
    stem = re.sub(r"\s*-\s*", " – ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or "Unbekanntes Buch"

def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def public_book(book: dict) -> dict:
    return {
        "id": book["id"],
        "title": book["title"],
        "subtitle": book.get("subtitle"),
        "author": book.get("author"),
        "description": book.get("description"),
        "isbn": book.get("isbn"),
        "publisher": book.get("publisher"),
        "published_date": book.get("published_date"),
        "language": book.get("language"),
        "format": book["format"],
        "file_name": book["file_name"],
        "file_size": book["file_size"],
        "metadata_source": book.get("metadata_source"),
        "created_at": book["created_at"],
        "updated_at": book["updated_at"],
        "has_cover": bool(book.get("cover_path") and Path(book["cover_path"]).exists()),
    }

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": f"Datei ist größer als {MAX_UPLOAD_MB} MB."}), 413

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "version": "0.1.0"})

@app.get("/api/books")
def list_books():
    return jsonify([public_book(book) for book in db.list_books()])

@app.get("/api/books/<book_id>")
def get_book(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404
    return jsonify(public_book(book))

@app.post("/api/books")
def upload_book():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Keine Datei ausgewählt."}), 400

    original_name = clean_filename(uploaded.filename)
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Unterstützt werden nur EPUB- und PDF-Dateien."}), 400

    book_id = uuid4().hex
    book_dir = BOOKS_DIR / book_id
    book_dir.mkdir(parents=True, exist_ok=False)
    stored_path = book_dir / f"original{suffix}"

    try:
        uploaded.save(stored_path)
        sha256 = hash_file(stored_path)
        duplicate = db.get_by_hash(sha256)
        if duplicate:
            shutil.rmtree(book_dir, ignore_errors=True)
            return jsonify({
                "error": "Dieses Buch ist bereits in der Bibliothek.",
                "book": public_book(duplicate),
            }), 409

        local = extract_local_metadata(stored_path, book_dir)
        if not local.get("title"):
            local["title"] = title_from_filename(original_name)

        needs_online = any(
            not local.get(field) for field in ("title", "author", "description")
        ) or not local.get("cover_path")
        enriched = enrich_metadata(local, METADATA_LANGUAGE) if needs_online else dict(local)
        if not enriched.get("metadata_source"):
            enriched["metadata_source"] = "Datei"

        cover_path = enriched.get("cover_path")
        if not cover_path and enriched.get("cover_url"):
            cover_path = download_cover(enriched["cover_url"], book_dir)

        now = utcnow()
        record = {
            "id": book_id,
            "title": enriched.get("title") or title_from_filename(original_name),
            "subtitle": enriched.get("subtitle"),
            "author": enriched.get("author"),
            "description": enriched.get("description"),
            "isbn": enriched.get("isbn"),
            "publisher": enriched.get("publisher"),
            "published_date": enriched.get("published_date"),
            "language": enriched.get("language"),
            "format": suffix.lstrip(".").upper(),
            "file_name": original_name,
            "file_size": stored_path.stat().st_size,
            "storage_path": str(stored_path),
            "cover_path": cover_path,
            "sha256": sha256,
            "metadata_source": enriched.get("metadata_source") or "Datei",
            "created_at": now,
            "updated_at": now,
        }
        db.insert_book(record)
        return jsonify(public_book(record)), 201
    except Exception as exc:
        shutil.rmtree(book_dir, ignore_errors=True)
        app.logger.exception("Upload fehlgeschlagen")
        return jsonify({"error": f"Das Buch konnte nicht verarbeitet werden: {exc}"}), 500

@app.post("/api/books/<book_id>/refresh-metadata")
def refresh_metadata(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    current = {
        "title": book.get("title"),
        "subtitle": book.get("subtitle"),
        "author": book.get("author"),
        "description": book.get("description"),
        "isbn": book.get("isbn"),
        "publisher": book.get("publisher"),
        "published_date": book.get("published_date"),
        "language": book.get("language"),
    }
    enriched = enrich_metadata(current, METADATA_LANGUAGE)

    values = {}
    filename_title = title_from_filename(book["file_name"])
    for key in ("title", "subtitle", "author", "description", "isbn", "publisher", "published_date", "language"):
        if enriched.get(key) and enriched.get(key) != book.get(key):
            # Refresh is conservative. A title derived only from the filename may be improved.
            if not book.get(key) or (key == "title" and book.get("title") == filename_title):
                values[key] = enriched[key]

    if not book.get("cover_path") and enriched.get("cover_url"):
        cover = download_cover(enriched["cover_url"], Path(book["storage_path"]).parent)
        if cover:
            values["cover_path"] = cover

    if enriched.get("metadata_source"):
        values["metadata_source"] = enriched["metadata_source"]
    values["updated_at"] = utcnow()
    db.update_book(book_id, values)

    updated = db.get_book(book_id)
    return jsonify(public_book(updated))

@app.get("/api/books/<book_id>/cover")
def get_cover(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404
    cover_path = book.get("cover_path")
    if not cover_path or not Path(cover_path).exists():
        return "", 404
    return send_file(cover_path, conditional=True)

@app.get("/api/books/<book_id>/download")
def download_book(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404
    path = Path(book["storage_path"])
    if not path.exists():
        return jsonify({"error": "Buchdatei fehlt."}), 404
    return send_file(
        path,
        as_attachment=True,
        download_name=book["file_name"],
        conditional=True,
    )
