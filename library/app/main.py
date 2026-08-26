from __future__ import annotations

import hashlib
import json
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
        "genres": db.get_book_genres(book["id"]),
        "series_id": book.get("series_id"),
        "series_name": book.get("series_name"),
        "series_index": book.get("series_index"),
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
    return jsonify({"status": "ok", "version": "0.6.0"})

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
            "genres": None,
            "series_id": None,
            "series_index": None,
            "created_at": now,
            "updated_at": now,
        }
        db.insert_book(record)
        return jsonify(public_book(record)), 201
    except Exception as exc:
        shutil.rmtree(book_dir, ignore_errors=True)
        app.logger.exception("Upload fehlgeschlagen")
        return jsonify({"error": f"Das Buch konnte nicht verarbeitet werden: {exc}"}), 500


@app.patch("/api/books/<book_id>")
def edit_book(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    allowed = {
        "title",
        "subtitle",
        "author",
        "description",
        "isbn",
        "publisher",
        "published_date",
        "language",
    }

    values = {}
    for key in allowed:
        if key in data:
            value = data.get(key)
            if isinstance(value, str):
                value = value.strip()
            if key == "title" and not value:
                return jsonify({"error": "Der Titel darf nicht leer sein."}), 400
            values[key] = value or None

    genre_ids = None
    if "genre_ids" in data:
        genre_ids = data.get("genre_ids") or []
        if not isinstance(genre_ids, list):
            return jsonify({"error": "genre_ids muss eine Liste sein."}), 400
        valid_ids = {genre["id"] for genre in db.list_genres()}
        genre_ids = [str(gid) for gid in genre_ids if str(gid) in valid_ids]

    if "series_id" in data or "series_index" in data:
        series_id = data.get("series_id") or None
        series_index = data.get("series_index")

        if series_id and not db.get_series(series_id):
            return jsonify({"error": "Serie nicht gefunden."}), 404

        if series_index in ("", None):
            series_index = None
        else:
            try:
                series_index = float(series_index)
                if series_index <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                return jsonify({"error": "Die Bandnummer muss eine positive Zahl sein."}), 400

        values["series_id"] = series_id
        values["series_index"] = series_index if series_id else None

    values["updated_at"] = utcnow()
    db.update_book(book_id, values)
    if genre_ids is not None:
        db.set_book_genres(book_id, genre_ids)
    return jsonify(public_book(db.get_book(book_id)))



@app.get("/api/books/<book_id>/metadata-candidates")
def metadata_candidates(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    local = {
        "title": book.get("title"),
        "author": book.get("author"),
        "isbn": book.get("isbn"),
    }
    candidates = search_metadata_candidates(local, METADATA_LANGUAGE, limit=10)
    return jsonify(candidates)

@app.post("/api/books/<book_id>/metadata-candidates/apply")
def apply_metadata_candidate(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    candidate = data.get("candidate")
    if not isinstance(candidate, dict):
        return jsonify({"error": "Kein gültiger Metadaten-Treffer übergeben."}), 400

    allowed = {
        "subtitle", "author", "description", "isbn",
        "publisher", "published_date", "language",
    }
    values = {}
    for key in allowed:
        value = candidate.get(key)
        if value not in (None, ""):
            # Title is deliberately not overwritten. Other selected edition
            # metadata may be replaced because the user explicitly chose it.
            values[key] = str(value).strip() or None

    cover_url = candidate.get("cover_url")
    if cover_url:
        cover = download_cover(cover_url, Path(book["storage_path"]).parent)
        if cover:
            values["cover_path"] = str(cover)

    values["metadata_source"] = candidate.get("metadata_source") or "Online"
    values["updated_at"] = utcnow()
    db.update_book(book_id, values)
    return jsonify(public_book(db.get_book(book_id)))

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
    enriched = enrich_metadata(current, METADATA_LANGUAGE, force_lookup=True)

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
    payload = public_book(updated)
    changed_fields = sorted(
        key for key in values.keys()
        if key not in {"updated_at", "metadata_source"}
    )
    payload["metadata_search"] = {
        "matched": bool(enriched.get("metadata_source") and enriched.get("metadata_source") not in {"Datei", book.get("metadata_source")}),
        "source": enriched.get("metadata_source"),
        "changed_fields": changed_fields,
        "isbn_found": bool(updated.get("isbn")),
    }
    return jsonify(payload)

@app.get("/api/books/<book_id>/cover")
def get_cover(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404
    cover_path = book.get("cover_path")
    if not cover_path or not Path(cover_path).exists():
        return "", 404
    return send_file(cover_path, conditional=True)

def _book_file(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return None, (jsonify({"error": "Buch nicht gefunden."}), 404)
    path = Path(book["storage_path"])
    if not path.exists():
        return None, (jsonify({"error": "Buchdatei fehlt."}), 404)
    return (book, path), None

@app.get("/api/books/<book_id>/download")
def download_book(book_id: str):
    result, error = _book_file(book_id)
    if error:
        return error
    book, path = result
    mimetype = "application/pdf" if book["format"] == "PDF" else "application/epub+zip"
    return send_file(
        path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=book["file_name"],
        conditional=True,
    )

@app.get("/api/books/<book_id>/open")
def open_book(book_id: str):
    """Inline response for iOS/Safari/Quick Look where possible."""
    result, error = _book_file(book_id)
    if error:
        return error
    book, path = result
    mimetype = "application/pdf" if book["format"] == "PDF" else "application/epub+zip"
    response = send_file(
        path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=book["file_name"],
        conditional=True,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@app.get("/api/genres")
def list_genres():
    return jsonify(db.list_genres())

@app.post("/api/genres")
def create_genre():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Bitte einen Genre-Namen angeben."}), 400
    now = utcnow()
    genre = {
        "id": uuid4().hex,
        "name": name,
        "hidden": False,
        "created_at": now,
        "updated_at": now,
    }
    try:
        db.create_genre(genre)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"error": "Dieses Genre existiert bereits."}), 409
        raise
    return jsonify(db.get_genre(genre["id"])), 201

@app.patch("/api/genres/<genre_id>")
def edit_genre(genre_id: str):
    current = db.get_genre(genre_id)
    if not current:
        return jsonify({"error": "Genre nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    values = {"updated_at": utcnow()}

    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Der Genre-Name darf nicht leer sein."}), 400
        values["name"] = name

    if "hidden" in data:
        values["hidden"] = bool(data.get("hidden"))

    try:
        db.update_genre(genre_id, values)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"error": "Dieses Genre existiert bereits."}), 409
        raise
    return jsonify(db.get_genre(genre_id))

@app.delete("/api/genres/<genre_id>")
def remove_genre(genre_id: str):
    if not db.get_genre(genre_id):
        return jsonify({"error": "Genre nicht gefunden."}), 404
    db.delete_genre(genre_id)
    return "", 204

@app.get("/api/settings")
def get_settings():
    return jsonify({})

@app.patch("/api/settings")
def update_settings():
    return jsonify({})

@app.get("/api/series")
def list_series():
    return jsonify(db.list_series())

@app.post("/api/series")
def create_series():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    description = str(data.get("description") or "").strip() or None
    if not name:
        return jsonify({"error": "Bitte einen Seriennamen angeben."}), 400

    now = utcnow()
    series = {
        "id": uuid4().hex,
        "name": name,
        "description": description,
        "created_at": now,
        "updated_at": now,
    }
    try:
        db.create_series(series)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"error": "Eine Serie mit diesem Namen existiert bereits."}), 409
        raise
    return jsonify(db.get_series(series["id"])), 201

@app.patch("/api/series/<series_id>")
def edit_series(series_id: str):
    current = db.get_series(series_id)
    if not current:
        return jsonify({"error": "Serie nicht gefunden."}), 404
    data = request.get_json(silent=True) or {}
    values = {"updated_at": utcnow()}
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Der Serienname darf nicht leer sein."}), 400
        values["name"] = name
    if "description" in data:
        values["description"] = str(data.get("description") or "").strip() or None
    try:
        db.update_series(series_id, values)
    except Exception as exc:
        if "UNIQUE constraint failed" in str(exc):
            return jsonify({"error": "Eine Serie mit diesem Namen existiert bereits."}), 409
        raise
    return jsonify(db.get_series(series_id))

@app.delete("/api/series/<series_id>")
def remove_series(series_id: str):
    if not db.get_series(series_id):
        return jsonify({"error": "Serie nicht gefunden."}), 404
    db.delete_series(series_id)
    return "", 204

@app.patch("/api/books/<book_id>/series")
def assign_book_series(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    series_id = data.get("series_id") or None
    series_index = data.get("series_index")

    if series_id and not db.get_series(series_id):
        return jsonify({"error": "Serie nicht gefunden."}), 404

    if series_index in ("", None):
        series_index = None
    else:
        try:
            series_index = float(series_index)
            if series_index <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "Die Bandnummer muss eine positive Zahl sein."}), 400

    db.update_book(
        book_id,
        {
            "series_id": series_id,
            "series_index": series_index if series_id else None,
            "updated_at": utcnow(),
        },
    )
    return jsonify(public_book(db.get_book(book_id)))
