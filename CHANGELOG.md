# Änderungen

Format: neueste Version zuerst. Die Versionsnummer steht in `frnadn/__init__.py`.

## 2.10.0 – 2026-11-25

**📧 FRN-Passwort anfordern – direkt beim Server.** Wie *„Get Password“* im FRN-Client, nur im Dashboard: Ein neues FRN-Konto für
diesen Server beantragen, das Passwort kommt per E-Mail. Ausführlich: [docs/de/adminbereich.md](docs/de/adminbereich.md#-frn-passwort-anfordern).

### Warum
- Jeder FRN-Server braucht ein **eigenes** FRN-Konto. Mit derselben E-Mail und demselben Passwort auf zwei Servern (z. B. Live und Test)
  lehnt der SystemManager den zweiten ab – *„the same credentials are already online on another server“* – und der Server bleibt offline.

### 📧 Settings → 🌐 SystemManager → FRN-Passwort anfordern
- Hinweis mit Knopf im Abschnitt SystemManager; der Dialog ist mit Rufzeichen und Name des Besitzers, der Konto-E-Mail, `PC Only` und
  dem Titel vorbelegt.
- Die Anfrage geht an den eingestellten SystemManager (`sysman.host`, TCP 10025) – im selben Format wie SvxLinks `frn-register`:
  `IG:<ON>Rufzeichen, Name</ON><EA>…</EA><BC>…</BC><DS>…</DS><NN>…</NN><CT>Ort - Ortsteil</CT>`.
- Antworten: **OK** (Passwort kommt per E-Mail), **NU** (Rufzeichen + Name gibt es schon – mit Tipp für einen zweiten Server), sonst der Code.
- Eingaben werden geprüft (Rufzeichen, E-Mail, Band/Kanal wie im FRN-Client, *Ort - Ortsteil*); `<`, `>` und Zeilenumbrüche werden
  entfernt, damit niemand weitere Felder in die Anfrage schmuggeln kann.
- Höchstens eine Anfrage pro Minute und SystemManager; jede Anfrage steht im Protokoll (*📧 FRN-Passwort angefordert*).

### 🔌 API
- `GET /api/admin/frn-password` (Vorbelegung) und `POST /api/admin/frn-password` – für Admins und den **API-Token des HobbyRadioPortals**,
  damit das Portal den Knopf in seiner FRN-Verwaltung anbieten kann.

### 🧪 Tests
- `tests/test_sysman.py`: Format der Anfrage, Prüfungen, Schutz gegen eingeschmuggelte Felder, Antworten OK/NU/Fehler gegen einen
  nachgebauten SystemManager, Begrenzung auf eine Anfrage pro Minute, Freigabe für den Portal-Token.

## 2.9.0 – 2026-11-25

**Installer: komplett ohne Fragen neu einrichten – mit `FRNADN_SETUP_FILE`.** Damit kann der Web-Installer des HobbyRadioPortals
(ab 0.11.0, Schritt *FRN → ✨ FRN-Server neu installieren*) einen FRN-Server samt Superadmin, Räumen und SystemManager-Konto aufsetzen,
ohne dass jemand in der Konsole antwortet. Ausführlich: [docs/de/installation.md](docs/de/installation.md#ohne-fragen).

### ⌨️ `FRNADN_SETUP_FILE=/pfad/setup.json`
- Ersetzt die Fragen in Schritt 5 (Superadmin) und 6 (FRN-Server). Inhalt ist genau das JSON, das sonst aus den Antworten entsteht und
  `frnadn apply-setup` liest: `settings` (z. B. `frn.standalone`, `sysman.email`, `sysman.password`, `frn.address`, `frn.port`,
  `frn.owner_callsign`, `dashboard.title`, `dashboard.public`), `test_room` (wird `net00`, Parrot), `rooms` und `superadmin`.
- Die Datei wird mit Rechten 600 an den Dienstbenutzer übergeben und danach gelöscht; das Passwort landet nur als scrypt-Hash in SQLite.
- Kombinierbar mit `FRNADN_YES=1`, `FRNADN_PORT=8090` und `FRNADN_BEHIND_PROXY=1` (hinter dem Portal).

### 🧪 Tests
- `tests/test_setup_file.py`: `apply-setup` aus einer Datei legt Räume (Test als net00), Einstellungen und den Superadmin an und schreibt
  `server.properties`; `install.sh` kennt den neuen Zweig und ist syntaktisch in Ordnung.

## 2.8.1 – 2026-11-25

**Installer: `FRNADN_BEHIND_PROXY=1`** – schaltet direkt nach dem Einspielen eines Backups (oder einer Einrichtung) das eigene HTTPS aus,
bevor die Dienste starten. So kollidiert ein neu aufgesetztes Dashboard nicht mit nginx des HobbyRadioPortals auf Port 80/443 – der
Web-Installer des Portals (ab 0.10.0, *FRN → 📦 aus einem Backup*) nutzt das zusammen mit `FRNADN_RESTORE`. Die Domain und das
Zertifikat übernimmt danach das Portal.

```bash
sudo FRNADN_YES=1 FRNADN_PORT=8090 FRNADN_RESTORE=/root/frn-backup-….frnbak FRNADN_RESTORE_PASSWORD_FILE=/root/frn.pw \
     FRNADN_BEHIND_PROXY=1 ./scripts/install.sh
```

## 2.8.0 – 2026-11-25

**💾 Backup & Wiederherstellen – im Dashboard, auf der Konsole, beim Installieren und im HobbyRadioPortal.** Eine einzige,
passwortverschlüsselte Datei (`.frnbak`) enthält alles, was den Server ausmacht; damit zieht er auf eine neue Maschine oder ins Portal um.
Ausführlich: [docs/de/adminbereich.md](docs/de/adminbereich.md#-backup--wiederherstellen-nur-superadmin).

### 💾 Admin → System → Backup (nur Superadmin)
- Passwort zweimal eingeben (mind. 10 Zeichen) → **Backup erstellen** → der Browser lädt `frn-backup-<host>-<datum>.frnbak` herunter.
- Die letzten **5** Backups bleiben in `/var/lib/frnadn/backups/` (700/600) und lassen sich erneut herunterladen oder löschen.
- **Inhalt:** die komplette Datenbank (konsistent über die SQLite-Backup-API, auch im laufenden Betrieb) – Einstellungen, Benutzer,
  Räume, FRN-Konten, Stationen, Statistik, Chat, Protokoll, Client-Logos, API-Tokens –, `branding/` (Logo, Site-Icons, Links) und vom
  FRN-Server `server.properties`, `log4j.xml` und die Zugriffslisten `acl/`, dazu ein `manifest.json` mit Host, Version, Titel und Zählern.
- **Nicht drin:** Sitzungen, Let's-Encrypt-Zertifikate (werden neu geholt), Logdateien, ältere Backups.
- **Verschlüsselung:** Format `N8MIG1` – scrypt-Schlüssel, SHAKE-256-Schlüsselstrom, HMAC-SHA256 über alles (encrypt-then-MAC), nur
  Python-Standardbibliothek. Dasselbe Format nutzt der Umzug von HBlink4 ins HobbyRadioPortal, das Portal kann die Datei also selbst prüfen.

### ♻️ Admin → System → Wiederherstellen
- `.frnbak` wählen, Passwort, **🔍 Prüfen**: Hochladen (gestreamt, bis 4 GiB), Probe-Entschlüsselung und eine Vorschau mit Host, Datum,
  Version, Räumen, Benutzern, FRN-Konten, Stationen und Durchgängen. Falsches Passwort oder eine fremde Datei wird hier abgewiesen.
- `RESTORE` eintippen → **Jetzt wiederherstellen**: Das Dashboard startet neu und spielt das Backup **vor** dem Öffnen der Datenbank ein.
  Der bisherige Stand wandert nach `before-restore-<datum>/`; schlägt etwas fehl (z. B. Integritätsprüfung der Datenbank), kommt er
  automatisch zurück. Danach schreibt es `server.properties` neu und **startet den FRN-Server neu**.
- Alle melden sich mit den Konten aus dem Backup neu an. Die Kachel zeigt *Letzte Wiederherstellung* (Zeit, Host, Version oder Fehler).
- Protokoll: *💾 Backup created / downloaded / deleted*, *♻️ Restore started*, *♻️ Backup restored*.

### ⌨️ Konsole und Installer
- `python -m frnadn backup [ORDNER]` – Passwort aus `FRNADN_PASSWORD` oder per Abfrage (für Cronjobs).
- `python -m frnadn restore DATEI` – spielt ein Backup bei gestopptem Dienst ein und nennt den Ordner mit dem alten Stand.
- `install.sh` mit `FRNADN_RESTORE=/pfad/…frnbak` und `FRNADN_RESTORE_PASSWORD_FILE=/pfad/pw` richtet einen neuen Server direkt
  aus einem Backup ein (statt der Fragen zu Server und Admin-Konto). Das nutzt auch der Web-Installer des **HobbyRadioPortals**
  (ab 0.10.0: *FRN → 📦 aus einem Backup*).

### 🔐 Sicherheit
- Nur der Superadmin – kein Admin, kein API-Token – kann Backups anlegen, laden, löschen oder einspielen.
- Beim Einspielen nur Einträge unter `data/` und `frn/`, keine absoluten Pfade, kein `..`, keine Links, höchstens 20 000 Dateien / 4 GiB;
  Downloads mit `Cache-Control: no-store`.

### 🛠️ Rechte
- `install.sh` und `update.sh` prüfen und korrigieren jetzt auch die Rechte der Daten: `backups/` und `before-restore-*` 700,
  Backup-Dateien und Datenbank 600, alles im Besitz des Dienstbenutzers.

### 🧪 Tests
- `tests/test_backup.py`: Backup → falsches Passwort → Prüfen → Einspielen samt Sicherung des alten Stands, Sitzungen gelöscht,
  Logs bleiben; unsicheres Archiv abgewiesen; Einspielen beim Start (`restore.pending.tar`). Zusätzlich Ende-zu-Ende gegen ein laufendes
  Demo-Dashboard (Anlegen, Herunterladen, Hochladen, Prüfen, Einspielen nach Neustart).

## 2.7.1 – 2026-11-24

**Für den Installer des HobbyRadioPortals: das Portal kann jetzt auf diesem FRN-Server installiert werden und stellt das Dashboard
dabei selbst hinter sich.** Ausführlich: [docs/de/betrieb.md](docs/de/betrieb.md#im-hobbyradioportal) und die
[Umzugsanleitung des Portals](https://github.com/dhartmann1979/HobbyRadioPortal/blob/main/docs/UMZUG.md).

### ⌨️ Zwei neue Befehle
- `python -m frnadn behind-proxy` – schaltet das eigene HTTPS (Let's Encrypt auf Port 80/443) aus und gibt Domain, E-Mail und Titel als
  JSON aus. Der Portal-Installer übernimmt damit Domain und Zertifikat in sein nginx.
- `python -m frnadn api-token NAME` – legt einen API-Token für das Portal an und gibt ihn einmal aus (wie *Admin → Users → Portal-Zugang*).

### 🔀 Was der Portal-Installer damit macht
- Er fragt einmal: *FRN-Dashboard hinter das Portal stellen?* – dann lauscht das Dashboard nur noch auf **127.0.0.1:8090**
  (Drop-in `/etc/systemd/system/frnadn.service.d/hobbyradioportal.conf` mit `FRNADN_BIND`/`FRNADN_PORT`, übersteht Updates),
  nginx des Portals übernimmt **Port 80/443**, die Domain (z. B. `frn.auf-der-nachtschicht.de`) und holt das Zertifikat neu.
- Der **FRN-Server selbst (Port 10024)** und alle Einstellungen, Räume, Listen und Statistiken bleiben unverändert. Das Dashboard
  bleibt unter seiner Domain erreichbar – jetzt über das Portal.
- Zurück: Drop-in löschen, `systemctl daemon-reload && systemctl restart frnadn`, HTTPS unter *Admin → Settings → HTTPS & web* wieder an.

### 🧪 Tests
- `tests/test_api_tokens.py`: `behind-proxy` schaltet HTTPS aus und meldet Domain/E-Mail, `api-token` gibt einen `frn_…`-Token aus.

## 2.7.0 – 2026-11-24

**Portal-Zugang per API-Token:** Das **HobbyRadioPortal** (Plugin *FRN*, ab Portal 0.8.0) kann den FRN-Server jetzt aus seinem eigenen
Admin-Bereich verwalten – Einstellungen, Räume, Zugriffslisten und Start/Stopp des Java-Servers. Dafür gibt es eigene Tokens statt
eines Admin-Passworts im Portal. Ausführlich: [docs/de/adminbereich.md](docs/de/adminbereich.md#-portal-zugang-api-token) und
[docs/de/sicherheit.md](docs/de/sicherheit.md#portal-zugang-api-token).

### 🔌 Admin → Users → Portal-Zugang (API-Token)
- Neue Kachel unter den Benutzern: **Name** eingeben, **➕ Token anlegen**. Der Token (`frn_…`) wird **nur einmal** angezeigt
  (mit **📋 Kopieren**); gespeichert wird nur sein SHA-256-Hash.
- Liste mit Name, Token-Ende, angelegt (wann/von wem), zuletzt benutzt (wann/von welcher IP) und **Widerrufen** – sofort wirksam.
- Anlegen und Widerrufen stehen im Protokoll (*Sessions & log*: „API-Token angelegt/widerrufen“).

### 🛡️ Was ein Token darf – und was nicht
- Er wirkt wie ein **Admin**, aber nur auf einer festen Liste von Adressen: `/api/admin/settings`, `/api/admin/rooms` (inkl. Reihenfolge
  und einzelne Räume), `/api/admin/acl`, `/api/admin/audit`, `/api/admin/server/start|stop|restart` und die öffentlichen Lese-APIs
  (Live, Statistik, Stationen, Client-Logos).
- **Nie:** Benutzer, Sitzungen, Tokens selbst, FRN-Konten, Updates, System, Theme, Links, Import, Logs, Anmeldung. **HTTPS-Einstellungen**
  (`https.*`) lehnt der Server für Tokens mit 403 ab.
- Im Protokoll erscheint der Portal-Benutzer mit: `api:HobbyRadioPortal (lutz)` – man sieht also, wer im Portal geklickt hat.
- Tokens gehen nur als `Authorization: Bearer …`, nie per Cookie oder Adresse; die CSRF-Regel (`X-N8`) gilt auch für sie.

### 🌐 Sprache
- Deutsche Texte für die Token-Kachel und die neuen Protokoll-Einträge (`static/i18n-app.js`).

### 🧪 Tests
- `tests/test_api_tokens.py`: erlaubte und gesperrte Adressen, HTTPS-Sperre, Widerruf, Token-Verwaltung nur für Menschen.

### ⬆️ Update
- Wie immer über **Admin → System → ⬆️ Updates** oder `sudo ./update.sh`. Nichts zu tun, wenn du das Portal nicht nutzt – ohne Token
  ändert sich nichts.

## 2.6.1 – 2026-11-24

### 🌐 N8 Kit 1.0.1
- Absätze, die im Quelltext über mehrere Zeilen gehen, werden beim Umschalten **DE | EN** als Ganzes übersetzt (vorher Zeile für Zeile,
  deshalb blieben längere Hilfetexte manchmal in der Originalsprache). `n8-kit.js` ist wieder in allen vier N8schicht-Projekten gleich
  (HBlink4-FreeRadioID 1.6.0, adn-frn-server, N8-HotSpot, N8 Crosslink).

## 2.6.0 – 2026-11-24

Sprache **DE | EN**, ein Update-System wie in N8 Crosslink und strengere Sicherheits-Header – mit dem **N8 Kit**, das jetzt in
adn-frn-server, HBlink4-FreeRadioID, N8-HotSpot und N8 Crosslink gleich ist. Wechselst du zwischen den Oberflächen, sehen Sprache,
Update-Hinweis, Updates-Kachel und Fortschritt überall gleich aus. Ausführlich: [docs/de/sicherheit.md](docs/de/sicherheit.md).

### 🌐 Sprache DE | EN
- Umschalter **DE | EN** in der Kopfzeile zwischen 🔗 Links und Anmeldung, **Standard Deutsch**. Umschalten ohne Neuladen; die Wahl
  gilt per Cookie (`n8_lang`) für alle N8schicht-Oberflächen auf dem Server. `?lang=en` für Links.
- Deutsche Texte für Kopfzeile, Statusleiste, Live, Statistik, Stationen, Chat und das ganze Admin-Portal (Settings, Rooms, ACL-Listen,
  FRN-Konten, Benutzer, System, Theme, Client-Logos, Links, Import, Logs) in `static/i18n-app.js`. Rückfragen folgen der Sprache.

### ⬆️ Updates wie in N8 Crosslink
- **Neuer Hinweis** unter der Statusleiste für angemeldete Admins: *Update verfügbar: alt → neu* mit **Was ist neu?**, **Jetzt aktualisieren**,
  **Details** und **Später** (einen Tag). Geprüft wird weiter jede volle Stunde; die Seite holt das Ergebnis alle 10 Minuten.
- **Admin → System → ⬆️ Updates** im N8-Kit-Stil: installiert, GitHub, zuletzt geprüft, automatische Prüfung, letztes Update, Repository,
  Neuerungen, **↻ Jetzt prüfen**, **⬆️ Update jetzt installieren**. Der Java-FRN-Server bleibt darunter mit eigenem Knopf.
- **Fortschritt:** Fenster mit Neuerungen, dann *geladen und eingespielt → Dienst startet neu → Weboberfläche wird geprüft*; die Seite
  lädt danach neu (ersetzt das bisherige Overlay „restarting …“).
- **Rollback:** Vor dem Neustart wird der alte Stand gemerkt (`update.pending` im Datenverzeichnis). Die neue Version prüft ihre eigene
  Weboberfläche; antwortet sie nicht, setzt `scripts/n8-update-guard.sh` (neu als `ExecStartPre` in `frnadn.service`) nach drei Starts
  auf den alten Commit zurück. Ergebnis unter *Letztes Update*. `scripts/update.sh` trägt die Zeile in bestehende Units ein und setzt
  die Rechte der Skripte.

### 🔐 Sicherheit
- Neue Header: `Content-Security-Policy` (nur eigene Skripte, Styles, Schriften und Verbindungen; `object-src 'none'`, `base-uri`,
  `form-action`, `frame-ancestors`), `Strict-Transport-Security` über HTTPS (auch hinter einem Proxy), `Permissions-Policy`,
  `Cross-Origin-Opener-Policy`/`-Resource-Policy`. Kein `server: uvicorn` mehr. Die API-Doku war schon aus; zum Entwickeln jetzt `N8_API_DOCS=1`.
- Doku mit Beispielen für **Caddy** und **nginx** als Reverse-Proxy.

### 🧪 Tests
- `tests/test_security.py`: API-Doku aus, alle Header, HSTS hinter Proxy, kein `server`-Header, Rollback nach drei Starts, Bestätigung
  nach erfolgreichem Start, Unit und `update.sh` mit Guard, Kit-Dateien eingebunden.

## 2.5.0 – 2026-11-22

Neue Kopfzeile: **ein Menü** statt Status-Chips plus Reiter, darunter eine schmale **Statusleiste** – derselbe Aufbau wie in
HBlink4-FreeRadioID und N8-HotSpot.

### 🧭 Ein Menü in der Kopfzeile
- Die Kopfzeile enthält nur noch Logo/Titel, die Reiter (**🎙️ Live · 📈 Statistics · 📇 Stations · 💬 Chat**) und rechts Links + Anmeldung.
- **⚙️ Admin** ist nach dem Login ein eigener, gestrichelt umrandeter Menüpunkt; der Weg über das Benutzermenü entfällt.
- **🔐 Login** steht ganz rechts. Angemeldet zeigt der Platz **👤 Name** (Klick öffnet das eigene Konto mit Passwortwechsel) und **⏻ Abmelden**
  daneben – kein Aufklappmenü mehr.

### 🟢 Statusleiste
- Neue, 22 px niedrige Leiste direkt unter dem Menü: **Live data**, **FRN server**, **n online** und rechts **On air: Rufzeichen** bzw. **💤 Quiet**.
- Der Zustand steht als farbiger Punkt vor dem Text (grün ok, gelb wartet, rot Problem, blau Info); die Texte sind kurz und ohne ✓/✕.
- Am Smartphone bleibt sie eine Zeile; die Statuspunkte in der Kopfzeile entfallen, die Reiter stehen in voller Breite darunter.

### 🛠️ Technik
- Neue gemeinsame Datei `static/n8-header.css` (`.n8-topbar`, `.n8-strip`, `.n8-ss ok/warn/bad/info/idle/plain`, `.n8-user`,
  `.n8-logout`, `.n8-menu-admin`, helles Theme, Smartphone) – identisch mit N8-HotSpot.
- `renderUser()` baut Name + ⏻ statt des Benutzermenüs; `renderChips()` schreibt in die Statusleiste. IDs der Elemente bleiben gleich.

### 📚 Doku
- *Dashboard → Kopfzeile und Menü* neu geschrieben (Menü- und Statusleisten-Tabelle, Smartphone).
- Screenshots neu: Kopfzeile Desktop/Smartphone, Live (öffentlich, angemeldet, Smartphone), Stations, Statistik und alle Admin-Seiten.
- Adminbereich und Betrieb verweisen auf den Menüpunkt **⚙️ Admin** bzw. die Statusleiste.

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
