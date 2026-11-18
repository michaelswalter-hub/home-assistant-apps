# Paperless-ngx (offiziell)

Diese App startet das **unveränderte offizielle Image**
`ghcr.io/paperless-ngx/paperless-ngx` in der Version, die in `config.yaml` steht,
und ergänzt nur das, was Home Assistant braucht:

- Ingress, damit Paperless als **„Paperless“ in der Seitenleiste** erscheint
- **PostgreSQL 18** als Datenbank (wie im offiziellen Compose-Setup) und Redis –
  beide laufen nur intern im Container
- Backups: Die App wird für ein HA-Backup kurz gestoppt (`backup: cold`),
  damit die Datenbank immer konsistent gesichert wird
- die Übersetzung der App-Optionen in Paperless-Umgebungsvariablen

## Erster Start

1. Im Reiter **Konfiguration** ein `admin_password` setzen (Benutzer: `admin_user`).
2. App starten. Der erste Start dauert einige Minuten (Image-Download und Datenbank-Einrichtung).
3. In der Seitenleiste auf **Paperless** klicken und mit dem Admin-Konto anmelden.

## Speicherorte

| Was | Ort |
| --- | --- |
| PostgreSQL-Datenbank, Suchindex | interner App-Speicher (`/data/postgres`, `/data/paperless`, in HA-Backups enthalten) |
| Dokumente | `media_dir` – Standard `/share/paperless-ngx/media` |
| Eingangsordner (wird automatisch eingelesen) | `consume_dir` – Standard `/share/paperless-ngx/consume` |

Den Eingangsordner erreichst du z. B. über die Samba-App unter `share/paperless-ngx/consume`.

## Optionen

| Option | Bedeutung |
| --- | --- |
| `admin_user` / `admin_password` | Admin-Konto, wird beim Start angelegt |
| `ocr_language` | OCR-Hauptsprache (z. B. `deu`) |
| `ocr_languages` | zusätzlich zu installierende Tesseract-Sprachen |
| `filename_format` | Ablagestruktur der Dateien |
| `timezone` | Standard: Zeitzone von Home Assistant |
| `usermap_uid` / `usermap_gid` | nur bei Rechteproblemen auf Netzlaufwerken (z. B. `0`) |
| `url` | nur nötig, wenn Paperless zusätzlich über eine eigene Adresse erreichbar sein soll |
| `tika_enabled`, `tika_endpoint`, `gotenberg_endpoint` | Office-Dokumente über Tika/Gotenberg verarbeiten |
| `env_vars` | beliebige weitere Paperless-Variablen, z. B. `PAPERLESS_OCR_MODE=skip` |

## Updates

Eine GitHub Action im Repository prüft täglich die offiziellen Releases.
Sobald eine neue Version erscheint, wird die App-Version erhöht und Home Assistant
zeigt das Update an. Mit **Automatisch aktualisieren** in der App wird es selbst eingespielt.
