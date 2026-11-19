#!/usr/bin/env python3
"""Eingang über Home Assistant: /media/paperless-eingang -> Paperless.

Ein Kurzbefehl lädt gescannte Seiten über die Home-Assistant-API
(/api/media_source/local_source/upload) in /media/paperless-eingang hoch.

* Seiten eines Scans heißen  <name>-p<Nummer>.jpg  (z. B. scan-20261119-131500-p1.jpg).
  Sobald 20 s lang keine neue Seite kam, werden sie in Seitenreihenfolge zu
  EINEM PDF zusammengefügt und in den Paperless-Eingangsordner gelegt.
* Alle anderen Dateien wandern unverändert in den Eingangsordner.
"""

import os
import re
import sys
import time
from pathlib import Path

INBOX = Path(os.environ.get("HA_MEDIA_INBOX", "/media/paperless-eingang"))
CONSUME = Path(os.environ.get("PAPERLESS_CONSUMPTION_DIR", "/share/paperless-ngx/consume"))
TMP = CONSUME.parent / ".eingang-tmp"  # gleiche Partition, aber außerhalb des Eingangsordners
BATCH_IDLE = 20  # Sekunden ohne neue Seite, bis ein Scan als vollständig gilt
FILE_IDLE = 5
PAGE_RE = re.compile(r"^(?P<batch>.+)-p(?P<page>\d+)\.(?P<ext>jpe?g|png|heic|heif|webp|tiff?)$", re.I)


def log(msg: str) -> None:
    print(f"[media-inbox] {msg}", flush=True)


def safe_name(name: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", name).strip() or "scan"


def unique_target(name: str) -> Path:
    target = CONSUME / name
    stem, suffix, i = target.stem, target.suffix, 1
    while target.exists():
        target = CONSUME / f"{stem}-{i}{suffix}"
        i += 1
    return target


def to_jpeg_bytes(path: Path) -> bytes:
    """img2pdf übernimmt JPEG/PNG verlustfrei; alles andere wird zu JPEG."""
    if path.suffix.lower() in (".jpg", ".jpeg", ".png"):
        return path.read_bytes()
    import io

    from PIL import Image

    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001
        pass
    with Image.open(path) as img:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=90)
        return buf.getvalue()


def merge_batch(batch: str, pages: list[tuple[int, Path]]) -> None:
    import img2pdf

    pages.sort(key=lambda p: p[0])
    images = [to_jpeg_bytes(p) for _, p in pages]
    pdf = img2pdf.convert(images, rotation=img2pdf.Rotation.ifvalid)
    target = unique_target(safe_name(batch) + ".pdf")
    tmp = TMP / f"{target.name}.part"
    tmp.write_bytes(pdf)
    tmp.rename(target)
    for _, p in pages:
        p.unlink(missing_ok=True)
    log(f"{len(pages)} Seite(n) als {target.name} an Paperless übergeben")


def move_file(path: Path) -> None:
    target = unique_target(safe_name(path.name))
    tmp = TMP / f"{target.name}.part"
    tmp.write_bytes(path.read_bytes())
    tmp.rename(target)
    path.unlink(missing_ok=True)
    log(f"{path.name} an Paperless übergeben")


def scan_once() -> None:
    now = time.time()
    batches: dict[str, list[tuple[int, Path]]] = {}
    newest: dict[str, float] = {}
    for f in INBOX.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue
        mtime = f.stat().st_mtime
        m = PAGE_RE.match(f.name)
        if m:
            b = m.group("batch")
            batches.setdefault(b, []).append((int(m.group("page")), f))
            newest[b] = max(newest.get(b, 0), mtime)
        elif now - mtime > FILE_IDLE:
            try:
                move_file(f)
            except Exception as exc:  # noqa: BLE001
                log(f"Fehler bei {f.name}: {exc}")
    for b, pages in batches.items():
        if now - newest[b] > BATCH_IDLE:
            try:
                merge_batch(b, pages)
            except Exception as exc:  # noqa: BLE001
                log(f"Fehler beim Zusammenfügen von {b}: {exc}")
                bad = INBOX / ".fehler"
                bad.mkdir(exist_ok=True)
                for _, p in pages:
                    p.rename(bad / p.name)


def main() -> int:
    INBOX.mkdir(parents=True, exist_ok=True)
    CONSUME.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    log(f"Beobachte {INBOX} -> {CONSUME}")
    while True:
        try:
            scan_once()
        except Exception as exc:  # noqa: BLE001
            log(f"Fehler: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    sys.exit(main())
