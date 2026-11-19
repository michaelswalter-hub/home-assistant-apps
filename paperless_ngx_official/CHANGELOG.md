## 3.5.1-10

Korrektur SSO: Absenderadresse im IPv6-Format (::ffff:…) erkennen.

## 3.5.1-9

Neu: Anmeldung aus Home Assistant durchreichen (ingress_sso), nur über die Seitenleiste; optional sso_user_map (z. B. michael=admin).

## 3.5.1-8

- Benachrichtigung: Vorschau zeigt jetzt die komplette erste Seite in guter Auflösung
- Veraltete Variable PAPERLESS_DBSSLMODE entfernt

## 3.5.1-7

Korrektur: Hochladen über die Seitenleiste (Home Assistant streamt Uploads ohne Content-Length).

## 3.5.1-6

Neu: Option ha_notify – bei neuen Dokumenten Ereignis `paperless_document_added` in Home Assistant mit Vorschau unter /media/local/paperless/<id>.jpg.

## 3.5.1-5

- Optionaler direkter Port (8000/tcp) für Handy-Apps wie Paperparrot
- Tika/Gotenberg standardmäßig aktiv, nutzt die Apps „Tika (offiziell)“ und „Gotenberg (offiziell)“

## 3.5.1-4

Neu: Option migrate_from_old_app – einmaliger Umzug aus der App „Paperless-ngx“ von Benoit Anastay.

## 3.5.1-3

Korrektur: Nach dem Login wurde Home Assistant doppelt angezeigt (fehlendes Ingress-Präfix). Behebt auch die Live-Statusanzeige.

## 3.5.1-2

Korrektur: Anmeldung über die Seitenleiste (CSRF „Origin null“ wegen Referrer-Policy von Home Assistant).

## 3.5.1-1

Korrektur: PostgreSQL-Pfad im Image.

## 3.5.1

Erste Version: offizielles Paperless-ngx 3.5.1 (https://github.com/paperless-ngx/paperless-ngx/releases/tag/v3.5.1)
