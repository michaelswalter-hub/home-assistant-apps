from __future__ import annotations

import html
import mimetypes
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import quote
from uuid import uuid4

import requests
from pypdf import PdfReader

USER_AGENT = "HomeAssistant-Library/0.1 (+private-library-app)"
TIMEOUT = 12

ISBN_RE = re.compile(
    r"(?<!\d)(?:ISBN(?:-1[03])?\s*:?\s*)?"
    r"((?:97[89][\s-]?)?\d[\d\s-]{8,16}[\dXx])(?!\d)"
)

def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or None

def normalize_isbn(value: str | None) -> str | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9Xx]", "", value).upper()
    if len(digits) in (10, 13):
        return digits
    return None

def find_isbn(text: str | None) -> str | None:
    if not text:
        return None
    for match in ISBN_RE.findall(text):
        isbn = normalize_isbn(match)
        if isbn:
            return isbn
    return None

def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]

def extract_epub_metadata(path: Path, book_dir: Path) -> dict:
    result: dict = {}
    try:
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = None
            for node in container.iter():
                if _local_name(node.tag) == "rootfile":
                    rootfile = node.attrib.get("full-path")
                    break
            if not rootfile:
                return result

            opf = ET.fromstring(archive.read(rootfile))
            metadata_node = next(
                (n for n in opf.iter() if _local_name(n.tag) == "metadata"), None
            )
            manifest_node = next(
                (n for n in opf.iter() if _local_name(n.tag) == "manifest"), None
            )

            def first_text(name: str) -> str | None:
                if metadata_node is None:
                    return None
                for node in metadata_node.iter():
                    if _local_name(node.tag) == name and node.text:
                        cleaned = _clean_text(node.text)
                        if cleaned:
                            return cleaned
                return None

            result["title"] = first_text("title")
            creators = []
            if metadata_node is not None:
                for node in metadata_node.iter():
                    if _local_name(node.tag) == "creator" and node.text:
                        cleaned = _clean_text(node.text)
                        if cleaned:
                            creators.append(cleaned)
            result["author"] = ", ".join(dict.fromkeys(creators)) if creators else None
            result["description"] = first_text("description")
            result["publisher"] = first_text("publisher")
            result["published_date"] = first_text("date")
            result["language"] = first_text("language")

            identifiers = []
            if metadata_node is not None:
                for node in metadata_node.iter():
                    if _local_name(node.tag) == "identifier" and node.text:
                        identifiers.append(node.text)
            result["isbn"] = next(
                (isbn for raw in identifiers if (isbn := find_isbn(raw))), None
            )

            cover_id = None
            if metadata_node is not None:
                for node in metadata_node.iter():
                    if _local_name(node.tag) == "meta":
                        name = node.attrib.get("name", "").lower()
                        prop = node.attrib.get("property", "").lower()
                        if name == "cover":
                            cover_id = node.attrib.get("content")
                        elif prop == "cover-image" and node.text:
                            cover_id = node.text.strip()

            cover_item = None
            if manifest_node is not None:
                items = [n for n in manifest_node if _local_name(n.tag) == "item"]
                if cover_id:
                    cover_item = next(
                        (i for i in items if i.attrib.get("id") == cover_id), None
                    )
                if cover_item is None:
                    cover_item = next(
                        (
                            i for i in items
                            if "cover-image" in i.attrib.get("properties", "").split()
                        ),
                        None,
                    )
                if cover_item is None:
                    cover_item = next(
                        (
                            i for i in items
                            if "cover" in i.attrib.get("id", "").lower()
                            and i.attrib.get("media-type", "").startswith("image/")
                        ),
                        None,
                    )

            if cover_item is not None:
                href = cover_item.attrib.get("href")
                if href:
                    opf_dir = Path(rootfile).parent
                    cover_member = (opf_dir / href).as_posix()
                    try:
                        cover_bytes = archive.read(cover_member)
                        mime = cover_item.attrib.get("media-type") or mimetypes.guess_type(href)[0]
                        suffix = {
                            "image/jpeg": ".jpg",
                            "image/png": ".png",
                            "image/webp": ".webp",
                            "image/gif": ".gif",
                        }.get(mime, Path(href).suffix or ".jpg")
                        cover_path = book_dir / f"cover{suffix}"
                        cover_path.write_bytes(cover_bytes)
                        result["cover_path"] = str(cover_path)
                    except KeyError:
                        pass
    except Exception:
        return result
    return {k: v for k, v in result.items() if v}

def extract_pdf_metadata(path: Path, book_dir: Path) -> dict:
    result: dict = {}
    try:
        reader = PdfReader(str(path))
        meta = reader.metadata or {}
        title = _clean_text(getattr(meta, "title", None))
        author = _clean_text(getattr(meta, "author", None))
        subject = _clean_text(getattr(meta, "subject", None))
        if title:
            result["title"] = title
        if author:
            result["author"] = author
        if subject and len(subject) > 40:
            result["description"] = subject

        pages_text = []
        for page in reader.pages[:8]:
            try:
                text = page.extract_text() or ""
                if text:
                    pages_text.append(text)
            except Exception:
                continue
        joined = "\n".join(pages_text)
        isbn = find_isbn(joined)
        if isbn:
            result["isbn"] = isbn
    except Exception:
        pass

    # Fallback cover: render the first PDF page with Poppler.
    try:
        prefix = book_dir / "cover_pdf"
        subprocess.run(
            [
                "pdftoppm", "-f", "1", "-singlefile", "-jpeg",
                "-scale-to", "1000", str(path), str(prefix)
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=45,
        )
        cover_path = Path(f"{prefix}.jpg")
        if cover_path.exists():
            result["cover_path"] = str(cover_path)
    except Exception:
        pass

    return result

def extract_local_metadata(path: Path, book_dir: Path) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return extract_epub_metadata(path, book_dir)
    if suffix == ".pdf":
        return extract_pdf_metadata(path, book_dir)
    return {}

def _get_json(url: str, params: dict | None = None) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _tokens(value: str | None) -> set[str]:
    return {part for part in _normalize_title(value).split() if len(part) > 1}


def _similarity(a: str | None, b: str | None) -> float:
    a_norm = _normalize_title(a)
    b_norm = _normalize_title(b)
    if not a_norm or not b_norm:
        return 0.0
    return SequenceMatcher(None, a_norm, b_norm).ratio()

def _match_score(candidate: dict, title: str | None, author: str | None) -> float:
    title_ratio = _similarity(title, candidate.get("title"))
    score = title_ratio * 75

    if author:
        author_ratio = _similarity(author, candidate.get("author"))
        wanted = _tokens(author)
        found = _tokens(candidate.get("author"))
        token_overlap = len(wanted & found) / max(1, len(wanted)) if wanted else 0
        score += max(author_ratio, token_overlap) * 30

    if candidate.get("isbn"):
        score += 6
    if candidate.get("description"):
        score += 2
    return score

def _google_books_candidates(query: str, language: str = "de") -> list[dict]:
    try:
        data = _get_json(
            "https://www.googleapis.com/books/v1/volumes",
            {"q": query, "maxResults": 10, "printType": "books", "hl": language},
        )
        results = []
        for item in data.get("items") or []:
            info = item.get("volumeInfo", {})
            identifiers = info.get("industryIdentifiers") or []
            isbn = None
            for identifier in identifiers:
                candidate = normalize_isbn(identifier.get("identifier"))
                if candidate and len(candidate) == 13:
                    isbn = candidate
                    break
                if candidate and not isbn:
                    isbn = candidate

            image_links = info.get("imageLinks") or {}
            cover = (
                image_links.get("extraLarge")
                or image_links.get("large")
                or image_links.get("medium")
                or image_links.get("thumbnail")
                or image_links.get("smallThumbnail")
            )
            if cover:
                cover = cover.replace("http://", "https://")

            genres = []
            for value in info.get("categories") or []:
                for part in re.split(r"[/>,;]", value):
                    cleaned = _clean_text(part)
                    if cleaned and cleaned.casefold() not in {g.casefold() for g in genres}:
                        genres.append(cleaned)

            results.append({
                "title": _clean_text(info.get("title")),
                "subtitle": _clean_text(info.get("subtitle")),
                "author": ", ".join(info.get("authors") or []) or None,
                "description": _clean_text(info.get("description")),
                "isbn": isbn,
                "publisher": _clean_text(info.get("publisher")),
                "published_date": _clean_text(info.get("publishedDate")),
                "language": _clean_text(info.get("language")),
                "genres": genres,
                "cover_url": cover,
                "metadata_source": "Google Books",
            })
        return results
    except Exception:
        return []

def _open_library_candidates(isbn: str | None, title: str | None, author: str | None) -> list[dict]:
    results = []
    try:
        if isbn:
            data = _get_json(
                "https://openlibrary.org/api/books",
                {"bibkeys": f"ISBN:{isbn}", "jscmd": "data", "format": "json"},
            )
            record = data.get(f"ISBN:{isbn}") or {}
            if record:
                genres = []
                for s in record.get("subjects", [])[:12]:
                    name = _clean_text(s.get("name")) if isinstance(s, dict) else None
                    if name and name.casefold() not in {g.casefold() for g in genres}:
                        genres.append(name)
                results.append({
                    "title": _clean_text(record.get("title")),
                    "author": ", ".join(a.get("name", "") for a in record.get("authors", []) if a.get("name")) or None,
                    "isbn": isbn,
                    "publisher": ", ".join(p.get("name", "") for p in record.get("publishers", []) if p.get("name")) or None,
                    "published_date": _clean_text(record.get("publish_date")),
                    "genres": genres,
                    "cover_url": (record.get("cover") or {}).get("large") or (record.get("cover") or {}).get("medium"),
                    "metadata_source": "Open Library",
                })

        params = {"limit": 10}
        if title:
            params["title"] = title
        if author:
            params["author"] = author
        if len(params) == 1:
            return results

        data = _get_json("https://openlibrary.org/search.json", params)
        for doc in data.get("docs") or []:
            isbn_values = doc.get("isbn") or []
            found_isbn = None
            for value in isbn_values:
                candidate = normalize_isbn(value)
                if candidate and len(candidate) == 13:
                    found_isbn = candidate
                    break
                if candidate and not found_isbn:
                    found_isbn = candidate

            cover_id = doc.get("cover_i")
            genres = []
            for value in (doc.get("subject") or [])[:12]:
                cleaned = _clean_text(value)
                if cleaned and cleaned.casefold() not in {g.casefold() for g in genres}:
                    genres.append(cleaned)

            results.append({
                "title": _clean_text(doc.get("title")),
                "author": ", ".join(doc.get("author_name") or []) or None,
                "isbn": found_isbn,
                "publisher": ", ".join((doc.get("publisher") or [])[:3]) or None,
                "published_date": str(doc.get("first_publish_year")) if doc.get("first_publish_year") else None,
                "language": (doc.get("language") or [None])[0],
                "genres": genres,
                "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                "metadata_source": "Open Library",
            })
        return results
    except Exception:
        return results


def _open_library_general_candidates(title: str | None, author: str | None) -> list[dict]:
    if not title and not author:
        return []
    try:
        query = " ".join(part for part in (title, author) if part)
        data = _get_json(
            "https://openlibrary.org/search.json",
            {"q": query, "limit": 15, "fields": "title,author_name,isbn,publisher,first_publish_year,language,cover_i,subject"},
        )
        results = []
        for doc in data.get("docs") or []:
            found_isbn = None
            for value in doc.get("isbn") or []:
                candidate = normalize_isbn(value)
                if candidate and len(candidate) == 13:
                    found_isbn = candidate
                    break
                if candidate and not found_isbn:
                    found_isbn = candidate

            genres = []
            for value in (doc.get("subject") or [])[:12]:
                cleaned = _clean_text(value)
                if cleaned and cleaned.casefold() not in {g.casefold() for g in genres}:
                    genres.append(cleaned)

            cover_id = doc.get("cover_i")
            results.append({
                "title": _clean_text(doc.get("title")),
                "author": ", ".join(doc.get("author_name") or []) or None,
                "isbn": found_isbn,
                "publisher": ", ".join((doc.get("publisher") or [])[:3]) or None,
                "published_date": str(doc.get("first_publish_year")) if doc.get("first_publish_year") else None,
                "language": (doc.get("language") or [None])[0],
                "genres": genres,
                "cover_url": f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg" if cover_id else None,
                "metadata_source": "Open Library",
            })
        return results
    except Exception:
        return []

def _best_candidate(candidates: list[dict], title: str | None, author: str | None) -> dict:
    if not candidates:
        return {}
    ranked = sorted(candidates, key=lambda c: _match_score(c, title, author), reverse=True)
    best = ranked[0]

    # Require a recognizable title match, but do not reject a good book merely
    # because author spelling/order differs between providers.
    title_similarity = _similarity(title, best.get("title")) if title else 1.0
    if title and title_similarity < 0.45:
        return {}
    return best


def search_metadata_candidates(local: dict, language: str = "de", limit: int = 10) -> list[dict]:
    title = local.get("title")
    author = local.get("author")
    isbn = local.get("isbn")
    candidates = []

    if isbn:
        candidates.extend(_google_books_candidates(f"isbn:{isbn}", language))
        candidates.extend(_open_library_candidates(isbn, title, author))

    queries = []
    if title and author:
        queries.extend([
            f'intitle:"{title}" inauthor:"{author}"',
            f"intitle:{title} inauthor:{author}",
            f"{title} {author}",
            title,
        ])
    elif title:
        queries.extend([f'intitle:"{title}"', f"intitle:{title}", title])
    elif author:
        queries.extend([f'inauthor:"{author}"', f"inauthor:{author}"])

    seen_queries = set()
    for query in queries:
        key = query.casefold().strip()
        if key not in seen_queries:
            seen_queries.add(key)
            candidates.extend(_google_books_candidates(query, language))

    candidates.extend(_open_library_candidates(None, title, author))
    candidates.extend(_open_library_general_candidates(title, author))

    ranked = sorted(candidates, key=lambda c: _match_score(c, title, author), reverse=True)
    unique = []
    seen = set()
    for candidate in ranked:
        if title and _similarity(title, candidate.get("title")) < 0.42:
            continue
        key = (
            normalize_isbn(candidate.get("isbn")) or "",
            _normalize_title(candidate.get("title")),
            _normalize_title(candidate.get("author")),
            candidate.get("published_date") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        candidate = dict(candidate)
        candidate["score"] = round(_match_score(candidate, title, author), 1)
        unique.append(candidate)
        if len(unique) >= limit:
            break
    return unique

def enrich_metadata(local: dict, language: str = "de", force_lookup: bool = False) -> dict:
    title = local.get("title")
    author = local.get("author")
    isbn = local.get("isbn")
    candidates = []

    if isbn:
        candidates.extend(_google_books_candidates(f"isbn:{isbn}", language))
        candidates.extend(_open_library_candidates(isbn, title, author))
    else:
        queries = []
        if title and author:
            queries.extend([
                f'intitle:"{title}" inauthor:"{author}"',
                f"intitle:{title} inauthor:{author}",
                f"{title} {author}",
                title,
            ])
        elif title:
            queries.extend([f'intitle:"{title}"', f"intitle:{title}", title])
        elif author:
            queries.extend([f'inauthor:"{author}"', f"inauthor:{author}"])

        seen = set()
        for query in queries:
            normalized_query = query.casefold().strip()
            if normalized_query not in seen:
                seen.add(normalized_query)
                candidates.extend(_google_books_candidates(query, language))

        candidates.extend(_open_library_candidates(None, title, author))
        candidates.extend(_open_library_general_candidates(title, author))

    best = _best_candidate(candidates, title, author)
    merged = dict(local)

    if best:
        # Do not rely on one provider record for every field. A Google Books
        # result may have the ISBN but no description, while another matching
        # edition has a useful summary. Rank all sufficiently similar records
        # and use them to fill missing fields.
        ranked = sorted(
            candidates,
            key=lambda candidate: _match_score(candidate, title, author),
            reverse=True,
        )
        compatible = []
        for candidate in ranked:
            title_similarity = _similarity(title, candidate.get("title")) if title else 1.0
            if title_similarity >= 0.55:
                compatible.append(candidate)

        # The best match always comes first.
        if best not in compatible:
            compatible.insert(0, best)

        for candidate in compatible:
            for key, value in candidate.items():
                if key in {"metadata_source", "cover_url", "genres"}:
                    continue
                if value and not merged.get(key):
                    merged[key] = value

            if candidate.get("cover_url") and not merged.get("cover_url"):
                merged["cover_url"] = candidate["cover_url"]

        # Prefer a meaningful summary from any compatible edition.
        if not merged.get("description"):
            descriptions = [
                candidate.get("description")
                for candidate in compatible
                if candidate.get("description")
            ]
            if descriptions:
                merged["description"] = max(descriptions, key=len)

        merged["metadata_source"] = best.get("metadata_source") or "Online"
    elif local:
        merged["metadata_source"] = local.get("metadata_source") or "Datei"

    return merged

def download_cover(url: str, book_dir: Path) -> str | None:
    if not url or not url.startswith(("https://", "http://")):
        return None
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            stream=True,
        )
        response.raise_for_status()
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].lower()
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "image/gif": ".gif",
        }.get(content_type, ".jpg")
        target = book_dir / f"cover_online_{uuid4().hex[:8]}{suffix}"
        size = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise ValueError("Cover ist unerwartet groß")
                handle.write(chunk)
        return str(target)
    except Exception:
        return None
