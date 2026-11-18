#!/usr/bin/env python3
"""Paperless-Post-Consume-Skript: meldet neue Dokumente an Home Assistant.

1. Legt eine JPEG-Vorschau unter /media/paperless/<id>.jpg ab
   (in Home Assistant erreichbar als /media/local/paperless/<id>.jpg,
   nur mit Anmeldung – also nicht öffentlich).
2. Löst in Home Assistant das Ereignis ``paperless_document_added`` aus.

Fehler hier dürfen das Einlesen nie stören: alles wird abgefangen und
nur protokolliert.
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

MEDIA_DIR = Path(os.environ.get("HA_NOTIFY_MEDIA_DIR", "/media/paperless"))
KEEP_DAYS = 30
EVENT = "paperless_document_added"


def log(msg: str) -> None:
    print(f"[ha-notify] {msg}", flush=True)


def document_details(doc_id: int) -> dict:
    """Titel, Typ usw. direkt aus Paperless lesen (Umgebung ist die des Workers)."""
    sys.path.insert(0, os.environ.get("PAPERLESS_SRC_DIR", "/usr/src/paperless/src"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "paperless.settings")
    import django

    django.setup()
    from documents.models import Document

    doc = Document.global_objects.select_related("correspondent", "document_type").get(pk=doc_id)
    return {
        "title": doc.title,
        "correspondent": doc.correspondent.name if doc.correspondent else "",
        "document_type": doc.document_type.name if doc.document_type else "",
        "tags": [t.name for t in doc.tags.all()],
        "page_count": doc.page_count,
    }


def save_preview(doc_id: int, thumb: str) -> str:
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    target = MEDIA_DIR / f"{doc_id}.jpg"
    from PIL import Image

    with Image.open(thumb) as img:
        img.convert("RGB").save(target, "JPEG", quality=85)
    # alte Vorschauen aufräumen
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in MEDIA_DIR.glob("*.jpg"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass
    return f"/media/local/{MEDIA_DIR.name}/{target.name}"


def fire_event(data: dict) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    req = urllib.request.Request(
        f"http://supervisor/core/api/events/{EVENT}",
        data=json.dumps(data).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def main() -> None:
    doc_id = int(os.environ["DOCUMENT_ID"])
    data = {
        "id": doc_id,
        "title": Path(os.environ.get("DOCUMENT_ORIGINAL_FILENAME", "")).stem,
        "correspondent": os.environ.get("DOCUMENT_CORRESPONDENT", "") or "",
        "document_type": os.environ.get("DOCUMENT_TYPE", "") or "",
        "tags": [t for t in (os.environ.get("DOCUMENT_TAGS", "") or "").split(",") if t],
        "created": os.environ.get("DOCUMENT_CREATED", ""),
        "original_filename": os.environ.get("DOCUMENT_ORIGINAL_FILENAME", ""),
        "image": "",
    }
    try:
        data.update(document_details(doc_id))
    except Exception as exc:  # noqa: BLE001
        log(f"Details nicht lesbar: {exc}")
    try:
        thumb = os.environ.get("DOCUMENT_THUMBNAIL_PATH", "")
        if thumb and Path(thumb).exists():
            data["image"] = save_preview(doc_id, thumb)
    except Exception as exc:  # noqa: BLE001
        log(f"Vorschau nicht erstellt: {exc}")
    try:
        fire_event(data)
        log(f"Ereignis {EVENT} für Dokument {doc_id} gesendet")
    except Exception as exc:  # noqa: BLE001
        log(f"Ereignis nicht gesendet: {exc}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001
        log(f"Unerwarteter Fehler: {exc}")
    sys.exit(0)
