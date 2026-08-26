# Bibliothek – Home Assistant App

Eine private EPUB- und PDF-Bibliothek als eigenständige Home-Assistant-App.

## Version 0.7.2

Die erste Version unterstützt:

- Upload von EPUB und PDF
- mehrere Dateien in einem Upload-Vorgang
- Speicherung der Originaldateien unter `/data/library/books`
- SQLite-Datenbank unter `/data/library/library.db`
- Auslesen von EPUB-Metadaten und eingebetteten EPUB-Covern
- Auslesen von PDF-Metadaten und ISBN aus den ersten Seiten
- PDF-Seite 1 als Cover-Fallback
- automatische Metadaten-Suche über Google Books und Open Library
- Cover-Download, wenn online ein Cover gefunden wird
- Bücherregal mit Cover, Titel und Autor
- Detailansicht mit Zusammenfassung und weiteren Metadaten
- erneute Online-Suche für fehlende Metadaten
- Download der ursprünglichen EPUB-/PDF-Datei
- iPhone/iPad: Teilen-Menü mit „In Dateien sichern“ als Download-Alternative
- Serien anlegen, umbenennen und löschen
- Bücher Serien zuordnen und Bandnummern pflegen
- Bibliothek nach Serie filtern und innerhalb einer Serie nach Bandnummer sortieren
- Duplikaterkennung per SHA-256
- Home Assistant Ingress
- Streaming für größere Uploads

## Installation im Repository

Kopiere den kompletten Ordner `library/` in die Wurzel deines bestehenden
`home-assistant-apps`-Repositories.

Die Struktur sollte dann beispielsweise so aussehen:

```text
home-assistant-apps/
├── recipe-app/
├── library/
│   ├── app/
│   ├── config.yaml
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── run.sh
│   └── README.md
└── repository.yaml
```

Anschließend:

1. Änderungen nach GitHub pushen.
2. In Home Assistant den App-/Add-on-Store neu laden.
3. `Bibliothek` installieren.
4. App starten.
5. `OPEN WEB UI` öffnen oder den Seitenleisten-Eintrag `Bibliothek` verwenden.

## Konfiguration

`max_upload_mb`
: Maximale Größe einer einzelnen hochgeladenen Datei. Standard: 1024 MB.

`metadata_language`
: Bevorzugte Sprache für Metadaten-Abfragen. Standard: `de`.

## Datenspeicherung

Alle Bibliotheksdaten liegen im persistenten App-Datenverzeichnis:

```text
/data/library/
├── library.db
└── books/
    └── <book-id>/
        ├── original.epub | original.pdf
        └── cover...
```

Die Originaldateien werden nicht verändert.

## Online-Metadaten

Die App fragt für fehlende Informationen öffentliche Schnittstellen ab:

- Google Books
- Open Library

Vorrang hat eine gefundene ISBN. Wenn keine ISBN vorhanden ist, wird mit Titel
und Autor gesucht. Bereits lokal vorhandene Metadaten werden bei der
automatischen Suche nicht überschrieben.

## Hinweise

- Bei EPUB-Dateien sind Metadaten und Cover meist zuverlässiger als bei PDFs.
- Bei PDF-Dateien wird versucht, eine ISBN aus den ersten acht Seiten zu erkennen.
- Wenn kein Cover verfügbar ist, zeigt die Oberfläche einen Platzhalter.
- Die Qualität automatischer Treffer hängt von den Daten der externen Anbieter ab.
- Für eine spätere Version ist eine manuelle Metadaten-Bearbeitung empfehlenswert.

## Lokaler Docker-Test

Vom Ordner `library/` aus:

```bash
docker build -t local/ha-library .
mkdir -p /tmp/ha-library-data
docker run --rm \
  -e LIBRARY_DATA_DIR=/data/library \
  -e LIBRARY_MAX_UPLOAD_MB=1024 \
  -e LIBRARY_METADATA_LANGUAGE=de \
  -v /tmp/ha-library-data:/data \
  -p 8099:8099 \
  local/ha-library
```

Danach ist die Testoberfläche unter Port `8099` erreichbar.


## Oberfläche ab 0.3.0

- Umschalter zwischen **Bücher** und **Serien**
- Serienansicht mit bis zu drei Cover-Vorschaubildern
- Klick auf eine Serie zeigt alle Bände in Reihenfolge
- Einstellungen über das Zahnrad
- Serienverwaltung befindet sich in den Einstellungen
- Buchmetadaten können in der Detailansicht über **Bearbeiten** geändert werden
- Serie und Bandnummer sind Bestandteil der Buchbearbeitung


## Neu in 0.4.0

- „Alle Serien“ aus der Bücherübersicht entfernt
- robustere Metadatensuche über Titel + Autor und mehrere Treffer
- fehlende ISBN wird gezielt ergänzt, wenn ein ausreichend passender Treffer gefunden wird
- Genres aus Online-Metadaten
- Genres in der Buchbearbeitung editierbar
- Genres können in den Einstellungen ausgeblendet werden


## Genres ab 0.5.0

Genres werden jetzt ausschließlich in den Einstellungen verwaltet:

- Genres selbst anlegen
- Genres umbenennen
- Genres löschen
- pro Genre festlegen, ob zugehörige Bücher in der Übersicht ausgeblendet werden
- ein Buch kann mehreren Genres zugeordnet werden
- Genre-Zuordnung erfolgt in „Buch bearbeiten“

## Verhalten der Ansichten

- Bücher mit Serienzuordnung erscheinen nur noch in der Serienansicht


## Neu in 0.7.0

- 1–5-Sterne-Bewertung für Bücher
- Bewertung direkt auf den Buchkarten ohne Öffnen der Detailansicht
- Sternebewertung auch in der Detailansicht
- Sternefilter in der Bücherübersicht
- Klick auf denselben Filterstern hebt den Filter wieder auf
- breitere Metadatensuche mit bereinigten Titeln, Untertiteln/Serienzusätzen und Autorvarianten
