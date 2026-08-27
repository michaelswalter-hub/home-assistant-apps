from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, request, send_file, send_from_directory
from bs4 import BeautifulSoup
import mobi

from database import Database
from ai_metadata import search_book_with_ai
from metadata import download_cover, enrich_metadata, extract_local_metadata, search_metadata_candidates, metadata_provider_status, set_google_books_api_key

DATA_DIR = Path(os.environ.get("LIBRARY_DATA_DIR", "/data/library"))
BOOKS_DIR = DATA_DIR / "books"
BOOKS_DIR.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = int(os.environ.get("LIBRARY_MAX_UPLOAD_MB", "1024"))
METADATA_LANGUAGE = os.environ.get("LIBRARY_METADATA_LANGUAGE", "de")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
db = Database(DATA_DIR / "library.db")

ALLOWED_EXTENSIONS = {".epub", ".pdf", ".mobi"}

def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_metadata_providers() -> None:
    set_google_books_api_key(db.get_setting("google_books_api_key", "") or "")


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


def _book_covers(book: dict) -> list[dict]:
    book_dir = Path(book["storage_path"]).parent
    active_path = Path(book["cover_path"]).resolve() if book.get("cover_path") else None
    covers = []

    if not book_dir.exists():
        return covers

    allowed_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    for path in sorted(book_dir.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0):
        if not path.is_file():
            continue
        if not path.name.lower().startswith("cover"):
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue

        try:
            resolved = path.resolve()
            is_active = active_path is not None and resolved == active_path
        except Exception:
            is_active = False

        covers.append({
            "id": path.name,
            "active": is_active,
            "size": path.stat().st_size,
        })

    return covers

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
        "rating": int(book.get("rating") or 0),
        "person": book.get("person"),
        "genres": db.get_book_genres(book["id"]),
        "series_id": book.get("series_id"),
        "series_name": book.get("series_name"),
        "series_index": book.get("series_index"),
        "created_at": book["created_at"],
        "updated_at": book["updated_at"],
        "has_cover": bool(book.get("cover_path") and Path(book["cover_path"]).exists()),
        "cover_count": len(_book_covers(book)),
    }

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": f"Datei ist größer als {MAX_UPLOAD_MB} MB."}), 413

@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")

@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "version": "0.9.12"})

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
    configure_metadata_providers()
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Keine Datei ausgewählt."}), 400

    original_name = clean_filename(uploaded.filename)
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({"error": "Unterstützt werden nur EPUB-, PDF- und MOBI-Dateien."}), 400

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

        try:
            local = extract_local_metadata(stored_path, book_dir)
        except Exception:
            app.logger.exception(
                "Lokale Metadaten konnten nicht gelesen werden; Buch wird trotzdem gespeichert"
            )
            local = {}

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
            "rating": 0,
            "person": None,
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



@app.patch("/api/books/<book_id>/rating")
def rate_book(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    try:
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Bewertung muss zwischen 0 und 5 liegen."}), 400

    if rating < 0 or rating > 5:
        return jsonify({"error": "Bewertung muss zwischen 0 und 5 liegen."}), 400

    db.update_book(book_id, {"rating": rating, "updated_at": utcnow()})
    return jsonify(public_book(db.get_book(book_id)))


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
        "person",
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

    if "person" in values:
        person = values.get("person")
        if person not in (None, "Hase", "HoBi"):
            return jsonify({"error": "Person muss Hase oder HoBi sein."}), 400

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





@app.post("/api/books/<book_id>/metadata-ai")
def ai_metadata_search(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    api_key = db.get_setting("openai_api_key", "") or ""
    ai_enabled = bool(db.get_setting("ai_enabled", False))
    model = db.get_setting("ai_model", "gpt-5.4-mini") or "gpt-5.4-mini"

    if not ai_enabled:
        return jsonify({"error": "Die KI-Metadatensuche ist in den Einstellungen deaktiviert."}), 400
    if not api_key:
        return jsonify({"error": "Kein OpenAI API-Key hinterlegt."}), 400

    try:
        candidate = search_book_with_ai(
            api_key=api_key,
            title=book.get("title"),
            author=book.get("author"),
            isbn=book.get("isbn"),
            model=model,
        )
        return jsonify(candidate)
    except Exception as exc:
        app.logger.exception("KI-Metadatensuche fehlgeschlagen")
        return jsonify({"error": str(exc)}), 502

@app.get("/api/books/<book_id>/metadata-provider-status")
def metadata_status(book_id: str):
    configure_metadata_providers()
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    local = {
        "title": book.get("title"),
        "author": book.get("author"),
        "isbn": book.get("isbn"),
    }
    return jsonify(metadata_provider_status(local, METADATA_LANGUAGE))


@app.get("/api/books/<book_id>/cover-candidates")
def cover_candidates(book_id: str):
    configure_metadata_providers()
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    local = {
        "title": book.get("title"),
        "author": book.get("author"),
        "isbn": book.get("isbn"),
    }
    candidates = search_metadata_candidates(local, METADATA_LANGUAGE, limit=24)

    # A cover-only search deliberately ignores candidates without an image.
    covers = []
    seen_urls = set()
    for candidate in candidates:
        cover_url = candidate.get("cover_url")
        if not cover_url or cover_url in seen_urls:
            continue
        seen_urls.add(cover_url)
        covers.append({
            "title": candidate.get("title"),
            "author": candidate.get("author"),
            "isbn": candidate.get("isbn"),
            "published_date": candidate.get("published_date"),
            "publisher": candidate.get("publisher"),
            "metadata_source": candidate.get("metadata_source"),
            "cover_url": cover_url,
        })

    return jsonify(covers)


@app.post("/api/books/<book_id>/cover-candidates/apply")
def apply_cover_candidate(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    data = request.get_json(silent=True) or {}
    cover_url = str(data.get("cover_url") or "").strip()
    if not cover_url.startswith(("http://", "https://")):
        return jsonify({"error": "Kein gültiges Cover ausgewählt."}), 400

    cover = download_cover(cover_url, Path(book["storage_path"]).parent)
    if not cover:
        return jsonify({"error": "Cover konnte nicht heruntergeladen werden."}), 502

    # Only the cover changes. All bibliographic metadata remains untouched.
    db.update_book(book_id, {
        "cover_path": str(cover),
        "updated_at": utcnow(),
    })

    updated = db.get_book(book_id)
    return jsonify({
        "book": public_book(updated),
        "covers": _book_covers(updated),
    })


@app.get("/api/books/<book_id>/metadata-candidates")
def metadata_candidates(book_id: str):
    configure_metadata_providers()
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    local = {
        "title": book.get("title"),
        "author": book.get("author"),
        "isbn": book.get("isbn"),
    }
    candidates = search_metadata_candidates(local, METADATA_LANGUAGE, limit=16)

    ai_enabled = bool(db.get_setting("ai_enabled", False))
    ai_mode = db.get_setting("ai_mode", "fallback") or "fallback"
    api_key = db.get_setting("openai_api_key", "") or ""
    ai_model = db.get_setting("ai_model", "gpt-5.4-mini") or "gpt-5.4-mini"

    should_use_ai = (
        ai_enabled
        and bool(api_key)
        and (
            ai_mode == "always"
            or (ai_mode == "fallback" and not candidates)
        )
    )

    if should_use_ai:
        try:
            ai_candidate = search_book_with_ai(
                api_key=api_key,
                title=book.get("title"),
                author=book.get("author"),
                isbn=book.get("isbn"),
                model=ai_model,
            )
            if ai_candidate:
                candidates.append(ai_candidate)
        except Exception:
            app.logger.exception("Automatische KI-Metadatensuche fehlgeschlagen")

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
    configure_metadata_providers()
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


@app.get("/api/books/<book_id>/covers")
def list_book_covers(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    result = []
    for cover in _book_covers(book):
        item = dict(cover)
        item["url"] = f"api/books/{book_id}/covers/{cover['id']}"
        result.append(item)
    return jsonify(result)

@app.get("/api/books/<book_id>/covers/<cover_id>")
def get_book_cover_file(book_id: str, cover_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    book_dir = Path(book["storage_path"]).parent.resolve()
    target = (book_dir / Path(cover_id).name).resolve()

    if target.parent != book_dir or not target.exists() or not target.is_file():
        return jsonify({"error": "Cover nicht gefunden."}), 404
    if not target.name.lower().startswith("cover"):
        return jsonify({"error": "Ungültige Cover-Datei."}), 400

    return send_file(target, conditional=True)

@app.patch("/api/books/<book_id>/covers/<cover_id>/active")
def set_active_cover(book_id: str, cover_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    book_dir = Path(book["storage_path"]).parent.resolve()
    target = (book_dir / Path(cover_id).name).resolve()

    if target.parent != book_dir or not target.exists() or not target.is_file():
        return jsonify({"error": "Cover nicht gefunden."}), 404
    if not target.name.lower().startswith("cover"):
        return jsonify({"error": "Ungültige Cover-Datei."}), 400

    db.update_book(book_id, {
        "cover_path": str(target),
        "updated_at": utcnow(),
    })
    return jsonify(public_book(db.get_book(book_id)))

@app.delete("/api/books/<book_id>/covers/<cover_id>")
def delete_book_cover(book_id: str, cover_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    book_dir = Path(book["storage_path"]).parent.resolve()
    target = (book_dir / Path(cover_id).name).resolve()

    if target.parent != book_dir or not target.exists() or not target.is_file():
        return jsonify({"error": "Cover nicht gefunden."}), 404
    if not target.name.lower().startswith("cover"):
        return jsonify({"error": "Ungültige Cover-Datei."}), 400

    active = Path(book["cover_path"]).resolve() if book.get("cover_path") else None
    deleting_active = active is not None and target == active

    try:
        target.unlink()
    except Exception as exc:
        return jsonify({"error": f"Cover konnte nicht gelöscht werden: {exc}"}), 500

    values = {"updated_at": utcnow()}
    if deleting_active:
        remaining = _book_covers({**book, "cover_path": None})
        if remaining:
            next_cover = (book_dir / remaining[0]["id"]).resolve()
            values["cover_path"] = str(next_cover)
        else:
            values["cover_path"] = None

    db.update_book(book_id, values)
    return jsonify(public_book(db.get_book(book_id)))

@app.get("/api/books/<book_id>/cover")
def get_cover(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404
    cover_path = book.get("cover_path")
    if not cover_path or not Path(cover_path).exists():
        return "", 404
    return send_file(cover_path, conditional=True)


def _safe_html_to_text(raw: bytes | str) -> str:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    blocks = []
    for node in soup.find_all(["h1", "h2", "h3", "h4", "p", "blockquote", "li"]):
        text = " ".join(node.stripped_strings)
        if text:
            if node.name in {"h1", "h2", "h3", "h4"}:
                blocks.append(f"\n{text}\n")
            elif node.name == "li":
                blocks.append(f"• {text}")
            else:
                blocks.append(text)
    if blocks:
        return "\n\n".join(blocks)

    return soup.get_text("\n\n", strip=True)

def _epub_reader_text(path: Path) -> str:
    chunks = []
    with zipfile.ZipFile(path) as archive:
        try:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next(
                (
                    node.attrib.get("full-path")
                    for node in container.iter()
                    if node.tag.rsplit("}", 1)[-1] == "rootfile"
                ),
                None,
            )
        except Exception:
            rootfile = None

        ordered_files = []
        if rootfile:
            try:
                opf = ET.fromstring(archive.read(rootfile))
                manifest = {}
                spine = []
                for node in opf.iter():
                    local = node.tag.rsplit("}", 1)[-1]
                    if local == "item":
                        item_id = node.attrib.get("id")
                        href = node.attrib.get("href")
                        media = node.attrib.get("media-type", "")
                        if item_id and href and ("html" in media or "xhtml" in media):
                            manifest[item_id] = href
                    elif local == "itemref":
                        idref = node.attrib.get("idref")
                        if idref:
                            spine.append(idref)
                base = Path(rootfile).parent
                ordered_files = [
                    (base / manifest[idref]).as_posix()
                    for idref in spine
                    if idref in manifest
                ]
            except Exception:
                ordered_files = []

        if not ordered_files:
            ordered_files = [
                name for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            ]

        total_chars = 0
        for member in ordered_files:
            try:
                text = _safe_html_to_text(archive.read(member))
            except Exception:
                continue
            if not text:
                continue
            chunks.append(text)
            total_chars += len(text)
            # Safety ceiling for very large books / malformed archives.
            if total_chars >= 5_000_000:
                break

    return "\n\n".join(chunks)


def _resolve_mobi_extracted_path(extracted: str | Path) -> Path | None:
    extracted_path = Path(extracted)
    if extracted_path.is_file():
        return extracted_path
    if extracted_path.is_dir():
        # KindleUnpack variants can return a directory. Prefer a readable book file.
        candidates = []
        for suffix in (".epub", ".html", ".htm", ".xhtml", ".pdf"):
            candidates.extend(extracted_path.rglob(f"*{suffix}"))
        return candidates[0] if candidates else None
    return None

def _pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    chunks = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            chunks.append(text.strip())
    return "\n\n".join(chunks)

def _mobi_reader_text(path: Path) -> str:
    tempdir = None
    try:
        tempdir, extracted = mobi.extract(str(path))
        extracted_path = _resolve_mobi_extracted_path(extracted)
        if extracted_path is None:
            return ""

        suffix = extracted_path.suffix.lower()
        if suffix == ".epub":
            return _epub_reader_text(extracted_path)
        if suffix == ".pdf":
            return _pdf_text(extracted_path)
        if suffix in {".html", ".htm", ".xhtml"}:
            return _safe_html_to_text(extracted_path.read_bytes())

        return _safe_html_to_text(extracted_path.read_bytes())
    except Exception as exc:
        raise RuntimeError(
            "MOBI konnte nicht entpackt werden. Das Buch ist möglicherweise DRM-geschützt "
            "oder verwendet eine nicht unterstützte MOBI-Variante."
        ) from exc
    finally:
        if tempdir:
            shutil.rmtree(tempdir, ignore_errors=True)

def _book_file(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return None, (jsonify({"error": "Buch nicht gefunden."}), 404)
    path = Path(book["storage_path"])
    if not path.exists():
        return None, (jsonify({"error": "Buchdatei fehlt."}), 404)
    return (book, path), None


@app.get("/api/books/<book_id>/reader-content")
def reader_content(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    path = Path(book["storage_path"])
    if not path.exists():
        return jsonify({"error": "Buchdatei fehlt."}), 404

    fmt = str(book.get("format") or "").upper()
    if fmt == "PDF":
        return jsonify({
            "format": "PDF",
            "title": book.get("title"),
            "url": f"api/books/{book_id}/open",
        })

    try:
        if fmt == "EPUB":
            text = _epub_reader_text(path)
        elif fmt == "MOBI":
            text = _mobi_reader_text(path)
        else:
            return jsonify({"error": "Dieses Format kann nicht im Reader geöffnet werden."}), 400
    except Exception as exc:
        app.logger.exception("Reader konnte Buch nicht aufbereiten")
        return jsonify({"error": f"Reader konnte das Buch nicht öffnen: {exc}"}), 500

    if not text.strip():
        return jsonify({"error": "Aus diesem Buch konnte kein lesbarer Text extrahiert werden."}), 422

    return jsonify({
        "format": fmt,
        "title": book.get("title"),
        "author": book.get("author"),
        "content": text,
    })

@app.delete("/api/books/<book_id>")
def delete_book(book_id: str):
    book = db.get_book(book_id)
    if not book:
        return jsonify({"error": "Buch nicht gefunden."}), 404

    book_dir = Path(book["storage_path"]).parent
    db.delete_book(book_id)
    try:
        shutil.rmtree(book_dir, ignore_errors=True)
    except Exception:
        app.logger.exception("Buchverzeichnis konnte nicht vollständig gelöscht werden")

    return "", 204

@app.get("/api/books/<book_id>/download")
def download_book(book_id: str):
    result, error = _book_file(book_id)
    if error:
        return error
    book, path = result
    mimetype = {
        "PDF": "application/pdf",
        "EPUB": "application/epub+zip",
        "MOBI": "application/x-mobipocket-ebook",
    }.get(book["format"], "application/octet-stream")
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
    mimetype = {
        "PDF": "application/pdf",
        "EPUB": "application/epub+zip",
        "MOBI": "application/x-mobipocket-ebook",
    }.get(book["format"], "application/octet-stream")
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
    api_key = db.get_setting("openai_api_key", "") or ""
    return jsonify({
        "ai_enabled": bool(db.get_setting("ai_enabled", False)),
        "ai_mode": db.get_setting("ai_mode", "fallback"),
        "ai_model": db.get_setting("ai_model", "gpt-5.4-mini"),
        "openai_api_key_configured": bool(api_key),
        "google_books_api_key_configured": bool(db.get_setting("google_books_api_key", "") or ""),
    })

@app.patch("/api/settings")
def update_settings():
    data = request.get_json(silent=True) or {}

    if "ai_enabled" in data:
        db.set_setting("ai_enabled", bool(data.get("ai_enabled")))

    if "ai_mode" in data:
        mode = str(data.get("ai_mode") or "fallback")
        if mode not in {"never", "fallback", "always"}:
            return jsonify({"error": "Ungültiger KI-Modus."}), 400
        db.set_setting("ai_mode", mode)

    if "ai_model" in data:
        model = str(data.get("ai_model") or "").strip()
        if not model:
            return jsonify({"error": "Das KI-Modell darf nicht leer sein."}), 400
        db.set_setting("ai_model", model)

    if data.get("clear_openai_api_key"):
        db.set_setting("openai_api_key", "")
    elif "openai_api_key" in data:
        key = str(data.get("openai_api_key") or "").strip()
        if key:
            db.set_setting("openai_api_key", key)

    if data.get("clear_google_books_api_key"):
        db.set_setting("google_books_api_key", "")
    elif "google_books_api_key" in data:
        google_key = str(data.get("google_books_api_key") or "").strip()
        if google_key:
            db.set_setting("google_books_api_key", google_key)

    api_key = db.get_setting("openai_api_key", "") or ""
    return jsonify({
        "ai_enabled": bool(db.get_setting("ai_enabled", False)),
        "ai_mode": db.get_setting("ai_mode", "fallback"),
        "ai_model": db.get_setting("ai_model", "gpt-5.4-mini"),
        "openai_api_key_configured": bool(api_key),
        "google_books_api_key_configured": bool(db.get_setting("google_books_api_key", "") or ""),
    })

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
