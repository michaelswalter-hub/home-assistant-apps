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

## Benachrichtigung bei neuen Dokumenten

Mit `ha_notify` (Standard: an) löst jedes neu eingelesene Dokument in Home Assistant
das Ereignis `paperless_document_added` aus. Daten: `id`, `title`, `correspondent`,
`document_type`, `tags`, `created`, `image` (z. B. `/media/local/paperless/12.jpg`).

Beispiel-Aktion für eine Automation mit Ereignis-Auslöser:

```yaml
action: notify.mobile_app_mein_handy
data:
  title: "Neues Dokument"
  message: "{{ trigger.event.data.title }}"
  data:
    image: "{{ trigger.event.data.image }}"
```

## Anmeldung aus Home Assistant (SSO)

Mit `ingress_sso` (Standard: an) ist man in Paperless automatisch mit dem
Benutzernamen angemeldet, mit dem man in Home Assistant angemeldet ist –
aber nur über die Seitenleiste. Anfragen über den direkten Port oder von der
Home-Assistant-Integration können diese Anmeldung nicht nutzen.

Heißt der Paperless-Benutzer anders als in Home Assistant, ordnet
`sso_user_map` ihn zu, z. B. `michael=admin`. Unbekannte Namen legt Paperless
als neue Benutzer ohne Rechte an.
