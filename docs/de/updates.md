# ⬆️ Updates

[← Übersicht](../../readme.md) · [Installation](installation.md) · [Dashboard](dashboard.md) · [Admin-Portal](adminbereich.md) · [Konfiguration](konfiguration.md) · [Betrieb & Fehlersuche](betrieb.md) · **Updates**

Zwei Programme werden aktualisiert, jedes mit eigenem Knopf. **Nichts wird automatisch installiert** – das Dashboard prüft nur und zeigt an.

| | Quelle | Knopf |
|---|---|---|
| 🖥️ **Dashboard** (frn_adn) | GitHub: `dhartmann1979/adn-frn-server`, Branch `main` | **⬆️ Update jetzt installieren** (Kachel) bzw. **Jetzt aktualisieren** (Hinweis) |
| ☕ **Java-FRN-Server** | `freeradionetwork.de` (FRN_Server.zip) | **Upgrade Java now** |

<p align="center"><img src="../images/admin-updates.png" alt="Software-Updates im Admin-Portal" width="70%"></p>

Zu finden unter **⚙️ Admin → 🖥️ System → ⬆️ Updates**. Hinweis, Kachel und Fortschritt kommen aus dem **N8 Kit** und sehen in adn-frn-server, HBlink4-FreeRadioID, N8-HotSpot und N8 Crosslink gleich aus.

<p align="center"><img src="../images/update-banner.png" alt="Update-Hinweis unter der Statusleiste" width="90%"></p>

Gibt es ein neues Dashboard, sehen **angemeldete Admins** direkt unter der Statusleiste den Hinweis *Update verfügbar: v2.6.0 · … → v2.7.0 · …* mit **Was ist neu?** (Commit-Liste), **Jetzt aktualisieren**, **Details** (öffnet Admin → System) und **Später** (blendet den Hinweis für diese Version einen Tag aus). Besucher ohne Anmeldung sehen ihn nie.

## Update-Funktion einmalig freischalten

Für die Standardinstallation sind keine zusätzlichen Einstellungen und kein GitHub-Token nötig: Das Repository `dhartmann1979/adn-frn-server` ist öffentlich; die Update-Prüfung und der Download funktionieren ohne Anmeldung. Das Dashboard muss als Git-Checkout mit `origin` auf `main` installiert sein. Nur für ein anderes öffentliches Repository oder einen anderen Branch sind die optionalen Variablen `FRNADN_GITHUB_REPO` und `FRNADN_GITHUB_BRANCH` nötig (siehe unten).

Der Dienst läuft als Benutzer `frnadn`. Dieser braucht Schreibrechte auf das Programmverzeichnis **einschließlich `.git`**, damit er den neuen Stand holen und einsetzen kann. Nach einer Neuinstallation gehört das Verzeichnis zunächst `root`. Führe deshalb einmalig als root aus:

```bash
cd /opt/adn-frn-server
sudo ./scripts/update.sh
```

> **Hinweis:** Dieser einmalige Schritt installiert zugleich den aktuellen Stand, stellt die Dateirechte ein und startet das Dashboard neu. Danach kann **Update jetzt installieren** im Admin-Portal verwendet werden. `update.sh` trägt dabei auch die Update-Prüfung mit Rollback (`ExecStartPre=… n8-update-guard.sh`) in die installierte Unit `frnadn.service` ein. Bei einem anderen Installationspfad ersetze `/opt/adn-frn-server` entsprechend.

## Wann wird geprüft?

- 30 Sekunden nach dem Start des Dashboards,
- danach zu **jeder vollen Stunde**,
- und jederzeit mit **↻ Jetzt prüfen**.

Die Abfrage an GitHub braucht keinen Zugang (zwei Anfragen pro Prüfung). Das Ergebnis zeigt je Programm: installierte Version, neue Version, bei GitHub zusätzlich die Zahl der neuen Commits samt Liste und einen Vergleichslink.

<p align="center"><img src="../images/admin-updates.png" alt="Software updates unter Admin → System" width="70%"></p>

Beim Öffnen von **Admin → System** zeigt die Karte das letzte Ergebnis (höchstens 10 Minuten alt), damit GitHub nicht bei jedem
Klick gefragt wird – ohne Anmeldung erlaubt GitHub 60 Abfragen pro Stunde. **↻ Jetzt prüfen** fragt immer sofort neu, nach einem Upgrade
wird automatisch neu geprüft. Die Uhrzeit der letzten Prüfung steht unten in der Karte.

## Dashboard aktualisieren

### Im Admin-Portal

<p align="center">
  <img src="../images/update-dialog.png" alt="Update bestätigen" width="42%">
  <img src="../images/update-dialog-done.png" alt="Update läuft" width="42%">
</p>

1. **↻ Jetzt prüfen** – steht dort **Update verfügbar**, zeigt die Kachel unter *Was ist neu* die neuen Commits.
2. **⬆️ Update jetzt installieren** (oder **Jetzt aktualisieren** im Hinweis). Das Fenster zeigt die Neuerungen; **⬆️ Jetzt aktualisieren** startet.
3. Drei Schritte mit Fortschritt: **Update wird geladen und eingespielt** (genau der Stand, den du gesehen hast, per Fast-Forward, dazu geänderte Python-Pakete) → **Dienst startet neu** (erst der FRN-Server für einen frischen Live-Status, dann das Dashboard) → **Weboberfläche wird geprüft**. Danach lädt die Seite von selbst neu. Einstellungen, Benutzer und Datenbank bleiben unberührt.

**Automatisch zurück:** Vor dem Neustart merkt sich das Dashboard den alten Stand (`/var/lib/frnadn/update.pending`). Die neue Version ruft nach dem Start ihre eigene Weboberfläche auf. Antwortet sie nicht, beendet sie sich; nach **drei erfolglosen Starts** setzt `scripts/n8-update-guard.sh` (läuft als `ExecStartPre` vor jedem Start von `frnadn`) das Programmverzeichnis auf den alten Commit zurück. Das Ergebnis steht in der Kachel unter **Letztes Update** (*erfolgreich* oder *zurückgenommen*) und in `/var/lib/frnadn/update.result`.

Der Knopf ist grau, wenn das Upgrade so nicht möglich ist; die Kachel nennt den Grund (siehe unten).

### Auf der Konsole

```bash
cd /opt/adn-frn-server
sudo ./scripts/update.sh
```

`update.sh` holt den neuen Stand, installiert die Python-Pakete, stellt die Dateirechte ein und startet zuerst den FRN-Server und danach das Dashboard neu. Verbundene Stationen verbinden sich automatisch wieder.

## Java-FRN-Server aktualisieren

**Upgrade Java now** lädt `FRN_Server.zip` von freeradionetwork.de, ersetzt `FRN_Server.jar` (und `releasenotes.txt`) und startet den Java-Server neu. Alle Stationen verbinden sich danach selbst wieder. Dieselbe Prüfung gibt es auch unter **Settings → ⬆️ Check for update**.

## Wenn etwas nicht klappt

| Anzeige | Ursache | Lösung |
|---|---|---|
| **Update jetzt installieren** ist grau, Hinweis „Run once as root …“ | Dem Dienstbenutzer fehlen Schreibrechte im Programmverzeichnis | `cd /opt/adn-frn-server && sudo ./scripts/update.sh` |
| **unknown state** · „No git checkout …“ | Das Dashboard wurde ohne `.git`-Ordner kopiert | neu von GitHub klonen oder den Stand von Hand einspielen und `update.sh` ausführen |
| **update available**, aber „own commits“ | Im Programmverzeichnis gibt es eigene Commits | von Hand aktualisieren: `git pull --rebase` oder neu klonen |
| Fehler „Files were changed by hand (…)“ | Dateien im Programmverzeichnis wurden verändert | Änderungen sichern, `git stash`, dann erneut |
| **check failed** · „rate limit“ | GitHub begrenzt anonyme Abfragen | später noch einmal prüfen |
| **check failed** · „not reachable“ | Der Server erreicht github.com nicht | Netz, DNS und Proxy prüfen |
| „The code is updated, but the Python packages are not …“ | `pip install` ist gescheitert (z. B. kein Netz) | `sudo ./scripts/update.sh` |
| Fortschritt endet mit „Der Dienst antwortet noch nicht“ | Dashboard startet nicht | `sudo journalctl -u frnadn -n 80 --no-pager`; nach drei Starts setzt der Guard automatisch zurück |
| **Letztes Update: zurückgenommen** | Die neue Version kam nicht hoch, der alte Stand läuft wieder | Log ansehen (`journalctl -u frnadn`), Fehler melden; der Hinweis bietet das Update weiter an |

> Läuft das Dashboard **nicht** unter systemd (z. B. zum Testen mit `python3 -m frnadn`), beendet es sich nach einem Upgrade nicht selbst. Die Meldung sagt dann, dass du es von Hand neu starten sollst.

## Eigenes Repository oder anderer Branch

Wer eine eigene öffentliche Kopie pflegt, stellt Repository und Branch in der Unit `frnadn.service` per Umgebungsvariable ein:

```ini
Environment=FRNADN_GITHUB_REPO=meinname/adn-frn-server
Environment=FRNADN_GITHUB_BRANCH=main
```

Danach `sudo systemctl daemon-reload && sudo systemctl restart frnadn`. Das Upgrade holt immer vom konfigurierten `origin` des Verzeichnisses, nie von einer Adresse aus dem Browser.

## Versionen und Releases

Die Versionsnummer steht in `frnadn/__init__.py` (`__version__`), alle Änderungen stehen in [CHANGELOG.md](../../CHANGELOG.md),
die neueste Version oben (`## 2.3.0 – 2026-11-22`). Die Zählung folgt [Semantic Versioning](https://semver.org/lang/de/):
MAJOR für Änderungen, nach denen man etwas von Hand anpassen muss, MINOR für neue Funktionen, PATCH für Fehlerbehebungen.

Für eine neue Version: Abschnitt oben in `CHANGELOG.md` ausführlich schreiben, `__version__` erhöhen, committen und pushen.
Der Workflow `.github/workflows/release.yml` legt daraufhin auf GitHub den Tag `vX.Y.Z` und das Release mit genau dem Text aus
dem Changelog an. Wird der Text später verbessert, passt der Workflow das Release automatisch an.
