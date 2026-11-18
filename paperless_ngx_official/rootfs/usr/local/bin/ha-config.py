#!/usr/bin/env python3
"""Home-Assistant-Optionen -> Paperless-ngx-Umgebung (s6 container_environment)."""

import json
import os
import secrets
import sys
import urllib.request
from pathlib import Path

PREFIX = "[ha-config]"
OPTIONS_FILE = Path(os.environ.get("HA_OPTIONS_FILE", "/data/options.json"))
ENV_DIR = Path(os.environ.get("HA_ENV_DIR", "/run/s6/container_environment"))
DATA_DIR = Path(os.environ.get("HA_DATA_DIR", "/data"))
SUPERVISOR = os.environ.get("HA_SUPERVISOR_URL", "http://supervisor")


def log(msg: str) -> None:
    print(f"{PREFIX} {msg}", flush=True)


def setenv(name: str, value) -> None:
    if value is None or value == "":
        return
    if isinstance(value, bool):
        value = "true" if value else "false"
    (ENV_DIR / name).write_text(str(value))


def ingress_entry() -> str:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    req = urllib.request.Request(
        f"{SUPERVISOR}/addons/self/info",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)["data"]
    return data["ingress_entry"].rstrip("/")


def persistent_secret(name: str, length: int) -> str:
    path = DATA_DIR / name
    if not path.exists():
        path.write_text(secrets.token_urlsafe(length))
        path.chmod(0o600)
    return path.read_text().strip()


def main() -> int:
    opts = json.loads(OPTIONS_FILE.read_text()) if OPTIONS_FILE.exists() else {}
    ENV_DIR.mkdir(parents=True, exist_ok=True)

    try:
        entry = ingress_entry()
    except Exception as exc:  # noqa: BLE001
        log(f"FEHLER: Ingress-Pfad konnte nicht ermittelt werden: {exc}")
        return 1
    log(f"Ingress-Pfad: {entry}")

    data_dir = DATA_DIR / "paperless"
    media = opts.get("media_dir") or "/share/paperless-ngx/media"
    consume = opts.get("consume_dir") or "/share/paperless-ngx/consume"
    for d in (data_dir, Path(media), Path(consume)):
        d.mkdir(parents=True, exist_ok=True)

    env = {
        # Seitenleiste / Ingress
        "PAPERLESS_FORCE_SCRIPT_NAME": entry,
        "PAPERLESS_PORT": "8000",
        "PAPERLESS_USE_X_FORWARD_HOST": True,
        "PAPERLESS_PROXY_SSL_HEADER": '["HTTP_X_FORWARDED_PROTO", "https"]',
        # eigene Cookie-Namen, damit es keine Konflikte mit anderen Apps gibt
        "PAPERLESS_COOKIE_PREFIX": "pngx_ha_",
        # Infrastruktur
        "PAPERLESS_REDIS": "redis://127.0.0.1:6379",
        "PAPERLESS_DATA_DIR": str(data_dir),
        "PAPERLESS_MEDIA_ROOT": media,
        "PAPERLESS_CONSUMPTION_DIR": consume,
        "PAPERLESS_SECRET_KEY": persistent_secret("secret_key", 64),
        # PostgreSQL (läuft intern im Container)
        "PAPERLESS_DBENGINE": "postgresql",
        "PAPERLESS_DBHOST": "127.0.0.1",
        "PAPERLESS_DBPORT": "5432",
        "PAPERLESS_DBNAME": "paperless",
        "PAPERLESS_DBUSER": "paperless",
        "PAPERLESS_DBPASS": persistent_secret("postgres_password", 32),
        # Einstellungen
        "PAPERLESS_TIME_ZONE": opts.get("timezone") or os.environ.get("TZ") or "UTC",
        "PAPERLESS_OCR_LANGUAGE": opts.get("ocr_language") or "deu",
        "PAPERLESS_OCR_LANGUAGES": opts.get("ocr_languages") or "",
        "PAPERLESS_FILENAME_FORMAT": opts.get("filename_format") or "",
        "PAPERLESS_ADMIN_USER": opts.get("admin_user") or "",
        "PAPERLESS_ADMIN_PASSWORD": opts.get("admin_password") or "",
        "USERMAP_UID": opts.get("usermap_uid"),
        "USERMAP_GID": opts.get("usermap_gid"),
    }

    if opts.get("ha_notify", True):
        # Neue Dokumente an Home Assistant melden (Ereignis + Vorschau in /media)
        env["PAPERLESS_POST_CONSUME_SCRIPT"] = "/usr/local/bin/ha-post-consume.py"
        notify_dir = Path("/media/paperless")
        try:
            import pwd

            notify_dir.mkdir(parents=True, exist_ok=True)
            pw = pwd.getpwnam("paperless")
            os.chown(notify_dir, pw.pw_uid, pw.pw_gid)
        except Exception as exc:  # noqa: BLE001
            log(f"Hinweis: /media/paperless nicht vorbereitet: {exc}")

    env["HA_MIGRATE_OLD_APP"] = bool(opts.get("migrate_from_old_app"))

    url = opts.get("url")
    if url:
        env["PAPERLESS_URL"] = url.rstrip("/")

    if opts.get("tika_enabled"):
        env["PAPERLESS_TIKA_ENABLED"] = True
        # Standard: die offiziellen Tika-/Gotenberg-Apps aus demselben Repository
        repo = os.environ.get("HOSTNAME", "").split("-")[0] or "1a52d194"
        env["PAPERLESS_TIKA_ENDPOINT"] = (
            opts.get("tika_endpoint") or f"http://{repo}-tika-official:9998"
        )
        env["PAPERLESS_TIKA_GOTENBERG_ENDPOINT"] = (
            opts.get("gotenberg_endpoint") or f"http://{repo}-gotenberg-official:3000"
        )

    if not env["PAPERLESS_ADMIN_PASSWORD"]:
        env.pop("PAPERLESS_ADMIN_USER")
        log("Kein Admin-Passwort gesetzt – es wird kein Admin-Konto angelegt/aktualisiert.")

    for item in opts.get("env_vars") or []:
        name, _, value = item.partition("=")
        env[name.strip()] = value

    for name, value in env.items():
        setenv(name, value)

    log("Konfiguration geschrieben.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
