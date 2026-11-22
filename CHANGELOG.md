# Änderungen

Format: neueste Version zuerst. Die Versionsnummer steht in `frnadn/__init__.py`.

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
