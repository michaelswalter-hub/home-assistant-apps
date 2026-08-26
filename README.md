# Meine Home Assistant Apps

## Meine Rezepte

Home-Assistant-App für Rezepte, Kochbücher, Wochenplanung und optionale Cloud-KI.

### KI
Der OpenAI API-Schlüssel wird **nicht** im Repository gespeichert.
Er wird nach der Installation in der App unter **Einstellungen → Cloud-KI** eingetragen und lokal unter `/data/settings.json` gespeichert.

### Version
Rezept-Sammler 0.4.1

### Kosten-Schutz 0.4.3
KI-Bild- und Covergenerierung erfordern eine ausdrückliche Kostenbestätigung.

### 0.5.28
Fix für Rezeptbilder-Galerie und klarere KI-Bildkostenanzeige.

### 0.5.28
Neues Rezept-Hub für Erstellen, Web-Import, Foto-Scan und PDF-Vorbereitung. KI-Bild/Löschen unter Bearbeiten.

### 0.5.28
Web-Importbilder sofort in der Galerie, mehrere eigene Bilder beim Bearbeiten und KI-PDF-Import.

### 0.5.28
Eigene Bilder als eigener Verwaltungsbereich, Kochbuch-Cover ohne Kostenbestätigung und Tags sauber unter dem Rezeptbild.

### 0.5.28
Fix für Kochbuch-Cover/Farben und Kochbuch-Detailansicht; Bildverwaltung nur unter Bearbeiten; Tag-Abstand korrigiert.

### 0.5.28
Bring via Home Assistant To-do, KI-Nährwerte/Kalorien, Zubereitungszeiten und Bild im Kochmodus.

### 0.5.28
Bearbeiten neu sortiert: Bilder und Verwaltungsaktionen vor Speichern; Abbrechen ergänzt.

### 0.5.28
Bildverwaltung nur unter Bearbeiten, Bring in Rezeptansicht mit Zutaten-Auswahl, KI-Nährwerte repariert.

### 0.5.28
Bring!-Liste kann direkt beim Rezept ausgewählt werden; zuletzt gewählte Liste wird als Standard gespeichert.

### 0.5.28
Bring!-Übertragung über Home-Assistant-REST-Service korrigiert und Fehlerdiagnose verbessert.

### 0.5.28
PDF-Import auf Datei-Upload mit klaren Fehlern umgestellt; Bring-Auswahl auf Bring-Listen gefiltert.

### 0.5.28
Bring-Listenfilter korrigiert: Bring bevorzugt, zuverlässiger Fallback auf beschreibbare To-do-Listen.

### 0.5.28
Kompakte Rezept-Aktionsleiste mit +Rezept, Kochmodus, Bearbeiten und Bring.

### 0.5.28
Aktionsleiste auf iPhone als kleine kompakte Buttons statt großer Kacheln.

### 0.5.28
Cache-Busting für iPhone/Ingress, mobile Buttons erzwungen und Bring-Diagnose ergänzt.

### 0.5.28
+Rezept-Button in der Rezept-Aktionsleiste explizit ergänzt und auf Mobilgeräten erzwungen.

### 0.5.28
Foto-KI-Scan mit Fortschrittsanzeige, Bildnormalisierung und Übernahme des Scan-Fotos in die Rezeptgalerie.

### 0.5.28
Foto-Scan Internal-Server-Error behoben; +Rezept aus Detailansicht entfernt und als kleiner Plus-Button nur in Rezeptübersicht platziert.

### 0.5.28
Gruppierte Zutatenabschnitte und hellblauer Plus-Button nur in der Rezeptübersicht.

### 0.5.28
Rezept-Internal-Error bei Zutaten-Gruppen behoben; Plus nur oben rechts in der Rezeptübersicht.

### 0.5.28
Zutaten-Checkboxen, Bring übernimmt nur fehlende Zutaten, Foto-Nährwerte, Einstellungen aufgeräumt.

### 0.5.28
Tag-Filter in der Rezeptübersicht werden erst beim Öffnen/Benutzen der Suche eingeblendet.

### 0.5.28
Tag-Filter werden in der Rezeptübersicht tatsächlich erst beim Antippen der Suche eingeblendet.

### 0.5.28
Kumulatives Reparatur-Update: Zutaten-Checkboxen, Bring-Zusammenfassung, Kochbuch-/Tag-Einstellungen und aktuelles CSS erneut vollständig enthalten.

### 0.5.28
Zubereitungsschritte als graue Karten und dynamische Portionsanpassung der Zutatenmengen.

### 0.5.28
Kumulatives Repair: Bring-Datenbankzugriff robust gemacht; Einstellungen/Kochbuchansicht erneut vollständig synchronisiert.

### 0.5.28
Kochmodus zeigt automatisch die zu jedem Zubereitungsschritt passenden Zutaten.

### 0.5.28
Repair für Plus-Buttons/Kochbuchübersicht; Kochmodus gruppiert Zutaten nach Rubriken und unterstützt 'alle Zutaten'.

### 0.5.28
Bring!-Seite gegen alte/ungültige Listen- und Einstellungswerte abgesichert. Neue KI-Funktion „Aus vorhandenen Zutaten“ unter + Rezept.

### 0.5.28
KI-Anpassungen werden als zusätzliche Rezeptvarianten gespeichert. Original bleibt erhalten; Umschaltung direkt im Rezept.

### 0.5.28
Repair: Bring! vollständig abgefangen; KI-Anpassen als Action-Button; Variantenumschalter aus Zeitkarte entfernt; Varianten verwenden eigene Zutaten/Zeiten; einzelne Varianten löschbar.

### 0.5.28
Kochmodus gegen Fehler abgesichert und Variantenfähig; Lösch-X nur bei geöffneter Variante; Bring-Button direkt bei Zutaten.

### 0.5.28
Fix Kochmodus: Zutaten-Rubriken verwenden sicheren Dictionary-Zugriff statt dict.items-Methode.

### 0.5.28
Kochmodus: passende Zutaten werden vor dem jeweiligen Arbeitsschritt angezeigt.

### 0.5.31
PWA/iPhone-Unterstützung: Manifest, eigenes App-Icon und Standalone-Meta-Tags. Die Home-Assistant-Anmeldung bleibt unverändert zuständig.
