# Änderungen

Format: neueste Version zuerst. Die Versionsnummer steht in `frnadn/__init__.py`.

## 2.4.1 – 2026-11-22

### Geändert
- Link-Site-Icons werden zusätzlich zu **Save & refresh site icons** jede Nacht um Mitternacht neu abgerufen.
- Der automatische Updatecheck wird auf die volle Stunde ausgerichtet.

## 2.4.0 – 2026-11-22

### Geändert
- **Live-Seite ohne Scrollen:** *On air* steht jetzt direkt unter den Tageskacheln über die ganze Breite (still: eine schmale Zeile).
  Darunter **Last heard** und **Rooms nebeneinander und gleich hoch**; beide füllen den Rest des Fensters und rollen in sich.
  Die Höhe passt sich automatisch an, wenn On air wächst oder das Fenster sich ändert. Last heard zeigt am Desktop alle 20 letzten
  Durchgänge (zwischen 1100 und 1400 px ohne Spalte *Band*).
- **Comings & goings** ist in den Tab **Statistics** umgezogen (ganz unten, die letzten 40 Logins/Logouts, live).
- Tablet/Handy (unter 1100 px): einspaltig in der Reihenfolge Kacheln, On air, Räume, Last heard; die Raumfilter von Last heard
  brechen am Handy sauber um.

## 2.3.0 – 2026-11-22

Neues Aussehen wie bei **DMR Die N8schicht**: Startseite, Farben und Kopfzeile folgen jetzt dem Dashboard von
HBlink4-FreeRadioID; Stationen zeigen ihre Client-Software als Avatar.

### Neu
- **Startseite wie das DMR-Dashboard:** Tageskacheln oben (Online now, Talks today, Airtime today, Stations heard, Peak online),
  darunter zwei Spalten – links *On air* und *Comings & goings*, rechts die Räume – und die kompakte *Last heard*-Liste über die volle Breite.
  Am Desktop passt die Seite meist ohne Scrollen auf einen Bildschirm.
- **Last heard kompakt:** eine Zeile pro Durchgang mit Avatar, Rufzeichen, Flagge, Raum, Dauer und Band; die ersten 8 (Handy: 5) Einträge,
  **Show all** zeigt alle.
- **Räume:** Raum-Chips mit Stationszahl und ● ON AIR; geöffnet ist automatisch der Raum, in dem gesprochen wird, sonst der vollste.
- **Avatar = Client-Software:** DMR, Zello, SvxLink, EchoLink, AllStar, C4FM/YSF, D-STAR, M17, TeamSpeak/Mumble, Crosslink,
  Funk-Gateway, PC/App und Parrot – erkannt an Band, Beschreibung und Client-Art (`frnadn/clientsw.py`). Die Bilder sind
  eigene Abzeichen (keine geschützten Hersteller-Logos); unter **Admin → Theme → Client logos** lässt sich jedes durch ein
  eigenes Bild ersetzen (PNG, JPEG, WebP, GIF, ICO oder SVG ohne Skripte, max. 512 KB, gespeichert in SQLite).
- **Rollen-Symbole** 👑 Owner und 🛡️ Admin stehen in der Raumliste jetzt **nach dem Avatar und vor dem Rufzeichen**.
- **N8 Theme:** dieselbe Farb-Engine wie HBlink4-FreeRadioID und N8-Hotspot. 7 Profile (N8 Night, Ocean, Aurora, Ember, Violet,
  Graphite und das helle **Daylight**), jede Farbe einzeln wählbar (Akzent, Akzent 2, Hintergrund, drei Leuchtfarben, Text, Kartentönung),
  Regler für Leuchten, Kartenhelligkeit, Rundung und Glas-Unschärfe, Live-Vorschau mit Lesbarkeitsprüfung.
  Gespeicherte Schemata aus 2.2 (Midnight, Forest, Sunset, Light …) werden automatisch übernommen.
- **Heller Modus** für alle Seiten und Dialoge (`static/n8-light.css`).
- **Kopfzeile am Handy in einer Zeile:** *Live data* und *FRN server* als Statuspunkte, Zahl der Stationen, Links und Benutzer als Symbole;
  Kacheln als 3+2-Raster.
- **Fußzeile** mit © Die N8schicht, Version, Commit und Datum (`/api/info` liefert dafür `build`).
- `tools/demo_live.py` schreibt Demo-Stationen in die FRN-Logs (für Tests und Screenshots).

### Behoben
- **Software updates (Admin → System) blieb bei „Not checked yet.“** Die Seite hatte zwei Elemente mit derselben ID `updInfo`
  (Java-Hinweis unter *Settings* und die Update-Karte unter *System*); das Prüfergebnis landete im unsichtbaren Element.
  Die Karte zeigt jetzt wieder Dashboard- und Java-Stand mit Commits und Vergleichslink.
- Beim Öffnen von *System* wird der zwischengespeicherte Stand (max. 10 Minuten alt) verwendet, statt GitHub jedes Mal neu zu fragen
  (schont das Abfragelimit). **↻ Check now** fragt weiterhin sofort nach; nach einem Upgrade wird neu geprüft.
- Link-Liste: *site icon* gilt nur noch für Web-Links, *new tab* nur für Web- und `mailto:`-Links (vorher auch für `#tab`/`/pfad`); 4 Tests angepasst.
- Datei-Auswahl (Logo, Site-Icon, Client-Logos, Import) im N8-Stil statt Browser-Standard.
- Benutzer-Menü und Aufklapp-Menüs nutzen die Theme-Farbe statt eines festen Dunkelblaus (lesbar im hellen Modus).

### Doku
- Alle Screenshots neu (Desktop und Smartphone, Daylight, Theme, Client-Logos, HTTPS, Import, Server-Listen);
  die schematischen SVG-Vorschauen sind durch echte Screenshots ersetzt.
- Dashboard: neuer Abschnitt *Startseite wie beim DMR-Dashboard* mit Avataren und Rollen; Admin-Portal: Theme, Client-Logos
  mit Erkennungsregeln, Import.

## 2.2.3 – 2026-11-22

### Behoben
- Der Icon-Endpunkt füllt den SQLite-Cache bei Bedarf, falls das Menü das Bild vor dem Hintergrundabruf anfordert.

## 2.2.2 – 2026-11-22

### Behoben
- Link-Site-Icons werden zusätzlich anhand der `rel=icon`-Angaben der Zielseite gefunden (auch bei nicht standardmäßigen Icon-Pfaden) und in SQLite gecacht. Alte negative Cache-Einträge werden einmalig erneut geprüft.

## 2.2.1 – 2026-11-22

### Behoben
- Dashboard-Updates starten nun auch den FRN-Server neu, damit der Live-Site-Status nach der Aktualisierung wieder stimmt. `scripts/update.sh` startet ebenfalls beide Dienste neu.

## 2.2.0 – 2026-11-22

### Neu
- **Theme-Tab im Admin-Portal**: Farbschemata Midnight, Ocean, Forest, Sunset, Violet und Light sowie einzelne Farben für Akzent, Hintergrund, Karten und Text; Dashboard-Logo und Site-Icon (PNG/ICO) sind separat verwaltbar. Link-Site-Icons werden sicher abgerufen und in SQLite gecacht.

## 2.1.0 – 2026-11-22

### Behoben
- **Update aus dem Admin-Portal**: „Upgrade Dashboard“ meldete praktisch nie ein Update. Das Dashboard läuft als Dienstbenutzer `frnadn`, das Programmverzeichnis gehört aber root. Git verweigerte dort die Arbeit („dubious ownership“), der lokale Stand blieb leer und das Ergebnis war immer „aktuell“. Jetzt wird `safe.directory` bei jedem Git-Aufruf gesetzt, ein unbekannter Stand wird als Fehler mit Hinweis angezeigt.
- Fehlende Schreibrechte im Programmverzeichnis werden vor dem Upgrade erkannt und erklärt (statt eines rohen Git-Fehlers). `scripts/update.sh` stellt die Rechte jetzt ein.
- Das Upgrade installiert geänderte Python-Pakete (`requirements.txt`) und startet das Dashboard nur dann selbst neu, wenn systemd es wieder startet; sonst steht ein Hinweis da.
- Das Upgrade ist an den Stand gebunden, den der Administrator gesehen hat (kein Update auf einen neueren, ungeprüften Commit).
- Der Update-Check läuft nun 30 Sekunden nach dem Start und danach zu jeder vollen Stunde (vorher erst nach der ersten vollen Stunde). GitHub-Abfragelimit, Netzfehler und unbekannter Branch werden verständlich gemeldet.
- Java-Update: Fehler werden als Meldung angezeigt statt als HTTP 500 ohne Text.
- Nach einem Dashboard-Upgrade wartet die Seite, bis das Dashboard wieder antwortet, und lädt sich dann neu.

### Neu
- ACL-Verwaltung im Admin-Portal: vorhandene FRN-Admin-, Mute-, Block- und Access-Listen werden in SQLite importiert und können dort formularbasiert gepflegt werden. Vor dem Zurückschreiben der FRN-XML-Datei entsteht ein Backup; die Admin-Dokumentation enthält eine schematische Screenshot-Vorschau.
- Live-Dashboard: mehr Abstand zwischen Kopfzeile und Inhalt; Stationen je Raum in der Reihenfolge Crosslinks, Admins/Owner, QRV, QRL, übrige Stationen und PC Only zuletzt.
- **Link-Liste wie bei HBlink4-FreeRadioID**: Symbol, Name, Adresse, „neuer Tab“ je Eintrag, Reihenfolge per ↑/↓, Schnellstart-Knöpfe, Schalter „Link-Menü anzeigen“, eigener Knopftext und Darstellung als Aufklapp-Menü oder als Knopfreihe. Erlaubt sind `https://`, `http://`, `mailto:`, `#tab` und `/pfad`.
- **Menü und Kopfzeile wie bei HBlink4**: Reiter mittig in der Kopfzeile, Links-Knopf, Status-Chips und Anmeldung in einer Zeile; schmal auf dem Smartphone.
- Anzeige im Update-Bereich: installierte und neue Version, Commits seit dem eigenen Stand, Link zum Vergleich.
- Dokumentation im Stil von HBlink4-FreeRadioID: Übersicht mit Screenshots, Update-Anleitung (`docs/de/updates.md`) und Anleitungen (`docs/de/anleitungen.md`).
- Tests für das Update-Modul und die Link-Liste.

## 2.0.0

Neuer Aufbau: Dashboard und Admin-Portal für den Java-FRN-Server, Einstellungen in SQLite, stündlicher Update-Check, getrennte Aktionen „Upgrade Dashboard“ und „Upgrade Java“.
