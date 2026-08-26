# Changelog

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
