# Changelog

## 0.9.1

- obere Bedienleiste neu angeordnet
- Anzahl neben Bücher/Serien verschoben
- Bücher/Serien-Schalter kompakter gemacht
- Personenfilter stabil neben Sternefilter
- Zahnrad ganz rechts in die Bedienleiste verschoben
- responsives Umbruchverhalten verbessert

## 0.9.0

- MOBI-Unterstützung hinzugefügt
- Buch löschen mit Sicherheitsabfrage
- Reader für PDF, EPUB und MOBI
- EPUB/MOBI-Textreader mit Schriftgrößensteuerung
- PDF-Reader per eingebetteter Datei
- Datenbank- und Dateilöschung werden gemeinsam durchgeführt

## 0.8.2

- Seriencover und Büchercover verwenden jetzt exakt dasselbe Raster und dieselbe Größe
- Google-Books-Abfrage auf minimale, robuste API-Parameter umgestellt
- Google-Books-Diagnose zeigt HTTP-Status und konkrete Fehlermeldung
- optionaler Google Books API-Key in den Einstellungen
- Google Books verwendet weiterhin die öffentliche API, wenn kein Key hinterlegt ist

## 0.8.0

- optionale KI-Metadatensuche mit OpenAI Responses API und Websuche
- OpenAI API-Key in den Einstellungen hinterlegbar
- KI-Modi: nie, nur als Fallback, immer zusätzlich
- manueller Button „Mit KI im Internet suchen“ im Trefferdialog
- KI-Treffer können wie normale Metadaten-Treffer übernommen werden
- Quellen der KI-Webrecherche werden angezeigt
- Zusammenfassungen können aus Webquellen gefunden oder daraus erstellt werden

## 0.7.5

- Google-Books-Abfrage korrigiert: ungültigen `hl`-Parameter entfernt
- Google Books wird jetzt mit gültigen Books-API-Parametern abgefragt
- Google-Treffer werden weiterhin neben Open Library ausgewogen angezeigt
- Trefferdialog zeigt die Anzahl der Google-Books-Testtreffer an

## 0.7.4

- Serienkarten verwenden jetzt das Hochformat eines Buchcovers
- das erste Seriencover wird im Seitenverhältnis 2:3 dargestellt

## 0.7.3

- Metadaten-Treffer werden ausgewogen aus Google Books und Open Library angezeigt
- ein Anbieter kann die Trefferliste nicht mehr vollständig verdrängen
- Quellen in der Trefferliste deutlicher markiert
- Serienübersicht zeigt nur noch das Cover des ersten Buches/Bandes

## 0.7.2

- Open-Library-Treffer werden bei fehlender Zusammenfassung mit Google Books ergänzt
- ISBN-spezifische Google-Books-Suche für Zusammenfassungen
- Titel-/Autor-Fallback für Zusammenfassungen
- Quelle der Zusammenfassung wird in der Trefferliste angezeigt

## 0.7.1

- Sternebewertung aktualisiert sofort alle Sterne bis zur gewählten Bewertung
- Filtersterne zeigen ebenfalls alle Sterne bis zur Auswahl gelb
- erneuter Klick auf dieselbe Filterbewertung deaktiviert den Filter vollständig
- harte Ähnlichkeitsschwelle der Metadatensuche entfernt
- deutlich breitere Titel-/Autor-Suchvarianten
- zusätzliche reine Titel- und Open-Library-Fallbacks
- bis zu 15 Metadaten-Treffer werden zur manuellen Auswahl gezeigt

## 0.7.0

- Sternebewertung 0–5 hinzugefügt
- Bewertung direkt in der Bücherübersicht möglich
- Sternefilter in der Bücherübersicht
- Bewertung auch in der Detailansicht änderbar
- Datenbankmigration für Bewertungen
- Metadatensuche mit bereinigten Titelvarianten erweitert
- Suchvarianten für Untertitel, Serienzusätze und Autor-Nachnamen ergänzt

## 0.6.2

- kritischen JavaScript-Startfehler aus 0.6.1 behoben
- fehlenden Metadaten-Treffer-Dialog in die Oberfläche eingefügt
- `null is not an object` bei der Metadatensuche behoben
- Zahnrad/Einstellungen funktionieren wieder
- vorhandene Bücher werden beim Öffnen wieder direkt geladen
- fehlenden Backend-Import für `search_metadata_candidates` ergänzt
- API-Ladefehler werden jetzt sauber abgefangen

## 0.6.1

- Versionsnummer erhöht, damit Home Assistant das Update erkennt
- enthält den vollständigen Funktionsstand der zuletzt aktualisierten 0.6.0
- manuelle Metadaten-Trefferauswahl
- Amazon.de-Suche pro Treffer
- Zusammenfassungen in der Metadatensuche
- Genre-Suche inklusive temporärer Anzeige ausgeblendeter Genres
- Serienbücher werden nur in der Serienansicht angezeigt

## 0.6.0

- Amazon.de-Suche pro Treffer über ISBN bzw. Titel und Autor hinzugefügt
- Treffer zeigen Cover, Titel, Autor, ISBN, Ausgabe, Verlag, Quelle und Zusammenfassung
- Metadatensuche zeigt mögliche Treffer zur manuellen Auswahl
- Metadatensuche ergänzt jetzt auch Zusammenfassungen aus passenden alternativen Ausgaben/Treffern
- Bücher mit Serienzuordnung werden in der Bücheransicht nicht mehr angezeigt
- Zahnrad in den Kopfbereich über „Bücher hinzufügen“ verschoben
- Suche berücksichtigt Genre-Namen
- Suche nach einem ausgeblendeten Genre zeigt dessen Bücher temporär wieder an
- Genres werden auf Buchkarten angezeigt
- ausgeblendete Genres werden in der Detailansicht gekennzeichnet
- Metadatensuche mit zusätzlichen Google-Books- und Open-Library-Abfragen erweitert
- Trefferbewertung für Titel/Autor verbessert
- Metadatensuche zeigt jetzt an, ob und welche Felder ergänzt wurden

## 0.5.0

- zentrale Genre-Verwaltung in den Einstellungen
- Genres können angelegt, umbenannt und gelöscht werden
- Genres können als ausgeblendet markiert werden
- Bücher mit mindestens einem ausgeblendeten Genre verschwinden aus der Übersicht
- Bücher können mehreren Genres zugeordnet werden
- Genre-Zuordnung in die Buchbearbeitung integriert
- automatische Online-Genres werden nicht mehr als eigene Kategorien übernommen

## 0.4.0

- Serienfilter aus der Bücherübersicht entfernt
- Metadatensuche mit Titel + Autor verbessert
- mehrere Online-Treffer werden bewertet
- ISBN-Suche verbessert
- Genres hinzugefügt und bearbeitbar gemacht
- Genres können in den Einstellungen ausgeblendet werden
- Datenbankmigration für Genres

## 0.3.0

- Umschaltung zwischen Bücher- und Serienansicht
- Serienansicht mit Cover-Vorschau und Bandliste
- Serienverwaltung in die Einstellungen hinter ein Zahnrad verschoben
- Buchmetadaten vollständig bearbeitbar
- Serie und Bandnummer in die Buchbearbeitung integriert
- Detailansicht vereinfacht

## 0.2.1

- Upgrade-Fehler von 0.1.x behoben (`no such column: series_id`)
- Serien-Index wird jetzt erst nach der Datenbankmigration angelegt
- Vorhandene Bücher bleiben erhalten

## 0.2.0

- Serienverwaltung hinzugefügt
- Bücher können einer Serie und einer Bandnummer zugeordnet werden
- Serienfilter im Bücherregal
- Serienname und Bandnummer auf Buchkarten
- iOS/iPadOS-Download über Web Share API („In Dateien sichern“)
- direkter Download bleibt als Fallback erhalten
- zusätzlicher Inline-Endpunkt für PDF Quick Look/Safari
- bestehende 0.1.0-Datenbank wird automatisch migriert

## 0.1.0

- Erste lauffähige Version
- EPUB-/PDF-Upload
- lokale Metadaten-Extraktion
- Google-Books- und Open-Library-Anreicherung
- Cover-Verarbeitung
- SQLite-Bibliothek
- Detailansicht
- Originaldatei-Download
- Home-Assistant-Ingress
