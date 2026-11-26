# Änderungen

Format: neueste Version zuerst. Die Versionsnummer steht in `frnadn/__init__.py`.

## 2.24.0 – 2026-11-26

### 📰 Neu: Portal-Seite mit News – nur Admins sind Autoren
- **Öffentliche Portal-Seite** unter `/portal` im Design des Dashboards: gleiche Kopfzeile (Titel mit [Master]/[Backup]/[Standalone],
  📰 News · 🎙️ Live · 📈 Statistik, Links-Menü, DE | EN, Anmelden) und Statuszeile, über die ganze Breite.
  - Begrüßung mit Titel, Untertitel, Begrüßungstext und Kennzahlen (jetzt online, Durchgänge heute).
  - **News als Karten:** angeheftete oben über die volle Breite, Kategorien ℹ️ Info · ⚠️ Wichtig · 🛠️ Technik · 📅 Termin · 📻 Netz & Räume
    mit Filter, Datum, Autor, Symbol, Anreißer, „Ältere News“; Artikel-Seite `/news/<id>`.
  - **Seitenkästen:** Zahlen von heute, Räume mit Stationen und wer gerade sendet (nur bei öffentlichem Dashboard, versteckte Räume nie),
    *Verbinden* (FRN-Server, Betreiber, Webseite).
  - **RSS-Feed** `/portal/rss.xml`; auf dem Handy einspaltig; lädt alle 30 s neu.
- **Eigene Rubrik im Admin-Menü: 📰 Portal** mit **📝 News** und **⚙️ Portal-Seite**.
  - **Nur Admins** (Admin, Superadmin) schreiben, bearbeiten, veröffentlichen, ziehen zurück und löschen – Benutzer und Besucher
    lesen nur (Server prüft, 403). Jede Änderung im 📜 Protokoll.
  - Editor mit **Live-Vorschau**, Symbol, Kategorie, Anreißer, 📌 Anheften, **Entwurf** oder **Veröffentlichen**.
  - Kleines Markdown (fett, kursiv, Code, Links, Überschriften, Listen, Zitat, Trennlinie). Alles wird erst maskiert, dann formatiert:
    kein HTML oder Skript eines Autors erreicht einen Besucher.
  - Einstellungen: Portal an/aus, Titel, Untertitel, Begrüßungstext, Räume zeigen, Zahlen zeigen, News je Seite.
- **Eigene Domain mit Let's-Encrypt-Zertifikat** – wie immer unter 🌐 Netz, Ports & Domains → 🔒 Domains & HTTPS:
  Hat das Dashboard seine Domain, folgt **Portal-Domain eintragen & Zertifikat holen**. Das Zertifikat wird um die Portal-Domain
  **erweitert** (ein Zertifikat, beide Namen, certbot `--expand`) und im laufenden Betrieb neu geladen; die Portal-Domain zeigt direkt
  die News, `/dashboard` darunter das Dashboard. Die HTTP→HTTPS-Weiterleitung behält die aufgerufene Domain.
  Entfernen nimmt nur die Portal-Domain weg.
- **📰 News** als Menüpunkt in der Kopfzeile des Dashboards, sobald die Portal-Seite an ist.
- **Master & Backup:** News und Portal-Einstellungen gehen beim Abgleich mit zum Backup (ältere Partner ohne News stören nicht, der
  FRN-Server startet dafür nicht neu); die Portal-Domain bleibt je Server eigen.
- Neue Tabelle `news` (SQLite, auch im Backup), neue Einstellungen `portal.*`, deutsche Texte für alles Neue.
- Tests `tests/test_portal.py`: nur Admins sind Autoren, Entwürfe unsichtbar, Anheften, RSS ohne HTML, Portal aus, Portal-Domain zeigt
  das Portal, Zertifikat mit beiden Namen, Weiterleitung je Domain. Alle 91 Tests grün.
- Doku: neue Seite [Portal-Seite](docs/de/portal.md), Admin-Portal und Übersicht ergänzt, neue Screenshots.

## 2.23.0 – 2026-11-25

### 🔤 Schriftauswahl mit Vorschau – in allen N8-Systemen (N8 Theme 2.1)
- Unter *Darstellung → 🎨 Aussehen* neue **Schriftauswahl mit Vorschau** (Rufzeichen, TG, Frequenz, Umlaute, Ziffern in jeder Schrift):
  **IBM Plex Sans** (neuer Standard, technisch und sehr gut lesbar), Inter, Barlow, Exo 2, Rajdhani oder die Systemschrift. Ein Klick wirkt
  sofort, gespeichert wird mit dem Aussehen.
- Zahlen, Anzeigen und Code stehen jetzt überall in **JetBrains Mono** (`--n8-mono`, auch `--mono`).
- Alle Schriften **selbst gehostet** (`fonts/` neben `n8-theme.js`, Fontsource 5.3.0, Schnitte 400/600/700, Latin + Latin-Extended, SIL OFL 1.1,
  Lizenz je Ordner) – keine Anfrage an Google Fonts oder andere fremde Server; die Sicherheitsregeln (`font-src 'self'`) bleiben unverändert.
- Gemeinsame Dateien `n8-theme.js`/`n8-theme.css` (N8 Theme 2.1) und die Prüfung des Themes um `font` erweitert; Doku um „Schrift“ ergänzt.

## 2.22.0 – 2026-11-25

### 📋 FRN-Fehlerprotokoll im Hintergrund – wie in N8 Crosslink
- **Sofort nach einem Problem:** Meldet der FRN-Server eine Ablehnung durch den SystemManager, beendet er sich oder startet er neu,
  schaut das Dashboard ein paar Sekunden später ins öffentliche FRN-Fehlerprotokoll (höchstens einmal pro Minute) und schreibt den
  Grund ins Ereignisprotokoll. Dazu wie bisher alle 2 Minuten bei einem Fehler, sonst alle 10 Minuten.
- **Mit Master & Backup** wird auch die Adresse des Partners beobachtet – Probleme des anderen Servers (z. B. dasselbe FRN-Konto)
  stehen auf beiden.
- **Direkt unter *Einstellungen → 🌐 SystemManager*** steht jetzt das Fehlerprotokoll (Einträge zu diesem Server, Neu laden, komplett
  öffnen) – wie auf der FRN-Seite von N8 Crosslink; der bisherige Hinweiskasten dort entfällt.
- Neue Erklärung für **„unknown owner“** (Besitzer-E-Mail des Servers ist kein bekanntes FRN-Konto).
- Behoben: lange deutsche Texte mit „… of …“ wurden von einer Übersetzungsregel verschluckt; Test `test_errorlog_checked_right_after_a_problem`.

## 2.21.0 – 2026-11-25

### 🔁 Master & Backup für FRN-Clients erkennbar (z. B. N8 Crosslink)
- Das öffentliche `/api/info` sagt jetzt unter `cluster`, welcher Server **Master** und welcher **Backup** ist (Host und FRN-Port,
  dazu ob der Master gerade in Wartung ist) – dieselben Angaben, die jeder FRN-Client ohnehin als `backup_server_addr` bekommt.
- Damit erkennt N8 Crosslink (ab 1.21.0) das Paar, behandelt den Master immer als Priorität 1 und kehrt nach einem Ausfall von
  selbst vom Backup zum Master zurück, sobald dieser wieder sauber läuft. Test `test_public_cluster_info_for_frn_clients`.

## 2.20.0 – 2026-11-25

### 🔑 FRN-Konten von Master und Backup im Kasten Master & Backup
- Neuer Abschnitt **🔑 FRN-Konten beim SystemManager**: für Master **und** Backup die E-Mail des FRN-Kontos, ob ein Passwort gesetzt
  ist, und die Serveradresse – das eigene direkt, das des Partners über die verschlüsselte Verbindung (bei jedem Abgleich und
  Statusabruf aktualisiert). Gleiche E-Mail auf beiden wird rot markiert.
- **Eigenes FRN-Konto direkt hier einstellen:** E-Mail und Passwort dieses Servers mit **💾 Konto speichern** (dasselbe wie unter
  *Einstellungen → SystemManager*, mit derselben Prüfung: die E-Mail des Partners wird abgelehnt). So lässt es sich vor dem ersten
  Abgleich einrichten.
- Klar gekennzeichnet: **Der Abgleich fasst die FRN-Konten nie an** – `sysman.email` und `sysman.password` gehören zu den Werten,
  die jeder Server für sich behält (Test sichert das ab).
- Doku: Einrichtung um „eigenes FRN-Konto auf beiden“ ergänzt, neuer Abschnitt „FRN-Konten von Master und Backup“, Screenshots.

## 2.19.0 – 2026-11-25

### 🔒 Schutz: Master und Backup nie wieder mit demselben FRN-Konto
- **Anlass:** frn und frn-backup liefen mit demselben FRN-Konto. Der SystemManager lässt ein Konto nur auf einem Server online –
  sie warfen sich gegenseitig raus, zuletzt waren **beide** abgewiesen („wrong FRN password“) und ihre FRN-Server beendeten sich
  dauernd.
- **Kennung bei jeder Verbindung:** Abgleich, Statusabruf, Übergabe und Antworten tragen die Kennung des FRN-Kontos (Hash der
  E-Mail, Ende-zu-Ende verschlüsselt). Beide Server merken sich die des Partners.
- **Das Backup sperrt sich selbst:** Bei gleichem Konto stoppt es seinen FRN-Server und hält ihn gesperrt – Keep-Alive, „▶ Start“,
  Neustart nach einem Abgleich, „Vom Backup zurückholen“ und der Start beim Hochfahren lassen ihn aus. Der Master bleibt online.
- **Speichern wird verweigert:** Die E-Mail des Partners lässt sich unter *SystemManager* nicht eintragen (auf Master und Backup).
- **Freigabe von selbst**, sobald das Backup ein eigenes Konto hat – dann startet sein FRN-Server wieder.
- Anzeige im Kasten *Master & Backup* (⛔ gleiches Konto, 🔒 gestoppt und gesperrt seit …), Protokoll-Einträge `cluster_guard`.
- Doku docs/de/master-backup.md („Schutz: nie zwei Server mit demselben FRN-Konto“); Tests für Sperre, Ablehnung und Freigabe.

## 2.18.2 – 2026-11-25

### ⛔ Warnung: Master und Backup mit demselben FRN-Konto
- **Ursache eines Ausfalls auf frn.auf-der-nachtschicht.de:** Master und Backup meldeten sich mit **demselben FRN-Konto** beim
  SystemManager an. Er lässt nur einen online. Als der Master für das Update neu startete, kam das Backup zuerst durch, der Master
  bekam „SystemManager: wrong credentials“, sein Java-FRN-Server beendete sich immer wieder (Exit 0, Keep-Alive-Neustarts) – und die
  Stationen landeten auf dem Backup.
- Jetzt vergleicht *🔁 Master & Backup* das FRN-Konto beider Server (über die verschlüsselte Verbindung, nur als Hash der E-Mail)
  und zeigt bei Gleichheit oben einen **roten Hinweis** mit der Lösung (eigenes Konto fürs Backup über **📧 FRN-Passwort Backup**).
  Stand-alone-Server (ohne SystemManager) sind ausgenommen.
- Fehlersuche in docs/de/master-backup.md ergänzt; Test `test_same_fRN_account_warning`.

## 2.18.1 – 2026-11-25

### 🔗 Master & Backup über Kreuz im Link-Menü
- Mit gesetzter Rolle steht der Partner automatisch als **erster Eintrag** im Link-Menü der Kopfzeile: auf dem Master
  **🔁 FRN Backup**, auf dem Backup **🔁 FRN Master** – mit der *Dashboard-Adresse des Partners*, seinem Site-Icon und in neuem Tab.
- Wird nicht in `links.json` gespeichert (taucht unter *Darstellung → 🔗 Links* nicht auf), folgt Rolle und Partner-Adresse sofort
  (alle offenen Seiten laden das Menü neu), erscheint auch bei ausgeschaltetem Link-Menü, und eine gleiche Adresse in den eigenen
  Links wird nicht doppelt gezeigt. Einzelserver: keine Änderung.
- Test `test_partner_first_in_link_menu`; Doku *Master & Backup* und *Admin-Portal → Links* mit Screenshot.

## 2.18.0 – 2026-11-25

### 🏷️ Rolle im Kopfbereich: [Master] · [Backup] · [Standalone]
- Hinter dem Titel steht jetzt die Rolle des Servers aus *Einstellungen → 🔁 Master & Backup*, z. B. **Auf der NachtSchicht
  [Master]** (grün), **[Backup]** (gelb) oder **[Standalone]** (grau, Einzelserver) – auch im Browser-Tab, damit man Master und
  Backup nicht verwechselt. `/api/info` liefert dafür `role`.

### 🗑 Abstürze bereinigen – in allen N8-Systemen
- **Admin → System → 💥 Abstürze**: jeder aufgeklappte Befund hat **🗑 Diesen Befund löschen**, unten gibt es **🗑 Alle löschen**
  (bzw. **🗑 Angezeigte löschen**, wenn nach einem Dienst gefiltert ist) – jeweils mit Rückfrage. Gelöscht werden der Eintrag in
  `crashes.jsonl` und das Protokoll `crash/<id>.log`; bei „Alle“ auch Reste und der Gelesen-Stand. Die laufende
  Faulthandler-Datei bleibt. Neue Befunde danach zählen wieder als neu.
- Neue Adresse `POST /api/admin/crashes/delete` (`{"all": true}` oder `{"ids": [...]}`), Konsole `n8-admin.sh crashes-clear`.
- Gemeinsame Bausteine `n8_admin.py`, N8 Kit 1.4.2 (`n8-kit.js`) und `n8-admin.sh` – gleich in allen N8-Systemen; Test `tests/test_crash_delete.py`.

## 2.17.3 – 2026-11-25

### 🐛 Update-Fenster: „Nicht aktualisiert“ statt fälschlich „zurückgenommen“
- Brach ein Update ab, bevor es irgendetwas geändert hatte (z. B. „von Hand geänderte Dateien“), meldete das Update-Fenster trotzdem
  „Das Update wurde zurückgenommen“ und hakte „Dienst startet neu“ ab – irreführend. Jetzt liest es das Ergebnis des Updates
  (`/api/admin/update-log`) und zeigt **„Nicht aktualisiert – es läuft unverändert die bisherige Version“** mit dem Grund. Nur ein
  echter Rückbau heißt weiter „zurückgenommen“ (mit Grund). N8 Kit 1.4.1, gleich in allen N8-Systemen.

## 2.17.2 – 2026-11-25

### 🛠️ Update: fehlende Programmdateien werden wiederhergestellt statt das Update abzubrechen
- „Update jetzt“ (`scripts/n8-admin.sh update`) brach ab mit „Im Programmverzeichnis wurden Dateien von Hand geändert – nichts
  aktualisiert“, wenn im Programmordner nur Dateien **fehlten** (z. B. Doku, LICENSE, `.github` – etwa nach einer Installation, die
  nicht alles kopiert hat). Jetzt stellt das Update **fehlende** Dateien aus git wieder her (`git checkout -- <Datei>`, im Protokoll:
  „N fehlende Programmdatei(en) aus git wiederhergestellt“) und läuft weiter. Wirklich **geänderte** Dateien sind weiterhin ein
  Grund zum Abbruch – nichts von Hand Geändertes geht verloren.
- Gemeinsames N8 Admin-Kit (`scripts/n8-admin.sh`), gleich in allen N8-Systemen.

### 📦 Installer kopiert jetzt das ganze Repository
- **Ursache des Abbruchs:** `install.sh` kopierte nur `frnadn`, `static`, `scripts`, `systemd` und `requirements.txt` nach
  `/opt/adn-frn-server`, aber das **komplette** `.git`. Für git fehlten damit Doku, LICENSE, `.github` usw. – „Update jetzt“ hielt das
  für von Hand gelöschte Dateien und aktualisierte nichts (so auf frn-backup.auf-der-nachtschicht.de).
- Jetzt kommt das ganze Repository (ohne `venv`, `data`, `__pycache__`) nach `/opt/adn-frn-server`, danach `git checkout -- .`.
  Bestehende Installationen heilt das Update selbst (siehe oben); einmalig von Hand siehe docs/de/updates.md.

## 2.17.1 – 2026-11-25

### 🌐 Web-Port bei der Installation: HTTP 8080
- Das Dashboard lauscht bei einer **neuen Installation** auf **HTTP-Port 8080** (bisher 80). So bleiben 80/443 frei für das
  eigene HTTPS mit Let's Encrypt (Port 80 nur für die Prüfung und die Weiterleitung) oder einen Reverse-Proxy.
- Der Installer **fragt** den Web-Port (Vorgabe 8080), prüft die Portnummer und warnt, wenn der Port schon belegt ist
  (mit Programmname). `FRNADN_PORT=…` setzt ihn ohne Frage.
- **Vorhandene Installationen behalten ihren Port**: Der Installer liest ihn aus `frnadn.service`, Updates ändern ihn nie.
  Behoben dabei: Das Ersetzen des Ports in der Dienst-Vorlage war nicht verankert (`FRNADN_PORT=80` hätte in `…=8080` gepasst).
- Vorgaben im Programm, in der Dienst-Vorlage und im Keep-Alive/Health-Check auf 8080; ufw gibt Dashboard-Port, FRN-Port und 80/443 frei.

### 📦 Systempakete werden bei jedem Update geprüft und nachinstalliert
- `n8-admin.sh update` (auch „⬆️ Update jetzt“) prüft vor allem anderen, ob alles da ist, was der Installer einrichtet:
  **certbot** (HTTPS mit Let's Encrypt), **Java** (`default-jre-headless`, falls kein `java`), `python3`, `python3-venv`,
  `python3-pip`, `sudo`, `curl`, `unzip`, `ca-certificates`. Fehlendes wird per apt nachinstalliert (wartet höchstens 2 Minuten
  auf eine laufende Paketinstallation, bricht das Update bei einem Fehler nicht ab, nennt dann den Befehl im Update-Protokoll).
  Ist alles da, steht im Protokoll eine Zeile mit den Versionen von certbot, Java und Python.
- **Admin → System → 🔐 Berechtigungen & sudo** zeigt fehlende Pakete unter *📦 Programm* („certbot fehlt – HTTPS mit
  Let's Encrypt geht nicht“), **Korrigieren** installiert sie nach.
- Der Installer bricht jetzt mit einer klaren Meldung ab, wenn apt die Pakete nicht installieren kann, und zeigt die
  certbot-Version an.
- Doku: Installation (Web-Port 8080), Updates (Paketprüfung).

## 2.17.0 – 2026-11-25

### 🔁 Neu: Master & Backup – zweiter FRN-Server mit derselben Konfiguration
- **Einstellungen → 🔁 Master & Backup**: Rolle *Einzelserver / Master / Backup*, *Dashboard des Partners*, *Sync-Schlüssel*,
  *Jede volle Stunde abgleichen*. Darüber ein Statuskasten: Partner erreichbar (Name, Rolle, Version, Stationen), letzter
  Abgleich mit Ergebnis, nächster Abgleich, wann das Backup zuletzt abgeholt hat, wohin die Clients ausweichen.
- **Abgleich**: Das Backup holt zu **jeder vollen Stunde** die Konfiguration des Masters, der Unterschied ist also höchstens eine
  Stunde. **🔄 Jetzt abgleichen** auf beiden Servern (auf dem Master bittet es das Backup). Übernommen werden Räume
  (mit fester `netNN`), Zugangs-, Admin-, Stumm- und Sperrlisten samt ACL-Dateien des Java-Servers, FRN-Konten und die
  gemeinsamen Einstellungen. Jeder Server behält Adresse, Port, Ausweichserver, **sein FRN-Konto beim SystemManager**,
  HTTPS, Benutzer, Statistik und Darstellung. Geschrieben wird nur bei Unterschieden; Anmeldezeiten zählen nicht.
- **Java-Server nur neu starten, wenn nötig**: nur wenn sich Räume, Listen oder Konten geändert haben **und keine Station
  verbunden ist**; sonst Hinweis „Jetzt neu starten“. Kommen vom Master keine Räume, übernimmt das Backup nichts. Alte
  ACL-Dateien landen in `acl/backups/*.sync.bak`.
- **Ausfall erledigt FRN selbst**: Mit gesetzter Rolle ist `backup_server_addr` automatisch der Partner (wenn unter
  *FRN-Server → Ausweichserver* nichts steht). Die Clients wechseln also von selbst.
- **🛠️ Wartung von Hand** (auf dem Master): **An das Backup übergeben** gleicht ab, prüft, dass der FRN-Server auf dem Backup
  läuft, und stoppt erst dann den eigenen FRN-Server (Keep-Alive hält still). Die Stationen wechseln zum Backup. **Vom
  Backup zurückholen** startet den Master und lässt danach das Backup seinen FRN-Server neu starten, sodass die Stationen
  zurückkommen. Jeder Schritt wird angezeigt.
- **🔐 Ende-zu-Ende verschlüsselt mit dem Sync-Schlüssel**, zusätzlich zu HTTPS: Jede Anfrage und Antwort ist
  verschlüsselt und signiert (scrypt + SHAKE-256 + HMAC-SHA-256, dieselben Bausteine wie `*.frnbak`). Der Schlüssel wird nie
  übertragen. Anfragen gelten nur für ihre Adresse, höchstens 5 Minuten und nur einmal (kein Wiedereinspielen), und
  Antworten müssen zur Anfrage gehören. Falsche Versuche werden gebremst. **🎲 Neuer Schlüssel** erzeugt einen (32 Byte).
- **📧 FRN-Passwort Master / Backup**: zwei Knöpfe, die das Formular „FRN-Passwort anfordern“ für den jeweiligen Server
  vorausfüllen (Name + „Master“/„Backup“). Jeder Server braucht sein eigenes FRN-Konto.
- Neue Adressen: `POST /api/cluster/{hello,export,pull,handback}` (nur verschlüsselt, zwischen den Servern),
  `GET /api/admin/cluster`, `POST /api/admin/cluster/{sync,key,maintenance}`. Protokoll-Einträge `cluster_sync`,
  `cluster_maintenance`, `cluster_key`, `cluster_handback`.
- Doku [docs/de/master-backup.md](docs/de/master-backup.md) mit Einrichtung, Wartung und Fehlersuche; Tests
  `tests/test_cluster.py` (Abgleich, Schutz, Verschlüsselung, Wiedereinspielen, Endpunkte).

## 2.16.0 – 2026-11-25

### 🌐 Neue Rubrik „Netz, Ports & Domains“ – wie in N8 Crosslink
- HTTPS, Domain und Ports stehen jetzt **nur noch** unter **🌐 Netz, Ports & Domains** (gleich in allen N8-Systemen); der Abschnitt
  *Einstellungen → HTTPS & web* ist weg.
  - **🔌 Ports**: Web-Port (aus dem systemd-Dienst), HTTP- und HTTPS-Port, FRN-Port der Clients, Port des Ausweichservers, SystemManager –
    mit *eingehend/ausgehend* und Protokoll, ein Knopf zum Speichern, Hinweis auf Neustarts, **♻️ Dashboard neu starten**.
  - **🔒 Domains & HTTPS**: Domain + E-Mail eintragen → HTTPS an, Dashboard startet neu und holt das Zertifikat; Tabelle mit DNS,
    Zertifikat (gültig/Test/abgelaufen, bis wann), **🔄 Erneuern**, **Entfernen**, Schalter *HTTPS mit Let's Encrypt*.
- Neue Adressen (gleich in allen N8-Systemen): `GET/POST /api/admin/ports`, `GET/POST /api/admin/domains`,
  `POST /api/admin/domains/<domain>/renew`, `DELETE /api/admin/domains/<domain>`, `POST /api/admin/domains/options`.
- Eine leere Domain ist jetzt erlaubt (Domain entfernen).

### 👥 Benutzer & Zugang wie in HBlink4-FreeRadioID
- **👥 Benutzer**, **🔑 Sitzungen** und **📜 Protokoll** sind jetzt drei eigene Einträge mit der gemeinsamen Ansicht des N8 Kit 1.4
  (Vorlage HBlink4): Benutzerzeile mit Kürzel, Rolle, letzter Anmeldung, „＋ Benutzer anlegen“ in einer Zeile, Bearbeiten mit
  Anzeigename, Passwort, Rolle, gesperrt, Löschen; Sitzungen mit Rolle, IP, Browser, Ablauf und **Abmelden**.

### 🛡️ Absturz-Wächter: Neustart-Knopf ist kein „Absturz“ mehr
- „Dashboard neu starten“ beendet den Prozess absichtlich – der Absturz-Wächter wird jetzt vorher informiert und hält das nicht mehr
  als Absturz fest (`n8_crash.mark_planned`, gleich in allen N8-Systemen).

## 2.15.1 – 2026-11-25

### 🐛 Behoben: „Fehler -15“ beim Neustart des eigenen Dienstes (Admin → System → Dienste)
- **Ursache:** Startet man die Weboberfläche über *Dienste* neu (oder stoppt sie), beendet systemd **alle** Prozesse des Dienstes – auch das
  gerade laufende `sudo systemctl …`. Das meldete sich mit Rückgabewert −15 (SIGTERM) zurück, die Oberfläche zeigte „Fehler -15“, obwohl
  der Neustart geklappt hatte; im Ereignisprotokoll stand „restart … – Fehler -15“.
- **Jetzt:** Der eigene Dienst wird erkannt (`/proc/self/cgroup`), die Antwort geht zuerst raus, eine Sekunde später wird der Neustart
  ausgelöst. Die Ansicht zeigt „Die Weboberfläche startet neu – einen Moment …“ und lädt sich von selbst neu, sobald sie wieder antwortet.
  Gemeinsamer Baustein (`n8_admin.py`, `n8-kit.js`), gleich in allen N8-Systemen.

### 🖥️ Ganze Browser-Breite: überall genau wie N8 Crosslink
- **Gleicher Seitenrand** in allen N8-Systemen: 12 px links und rechts, Kopfzeile und Inhalt stehen auf den Pixel genau wie in N8 Crosslink
  (vorher je nach System 12–16 px; `n8-kit.css`).

## 2.15.0 – 2026-11-25

### 💥 Neu: Absturz-Erkennung – jeder Absturz wird mit Ursache und Protokoll festgehalten, gemeldet und der Dienst neu gestartet
Gleiche Grundlage in allen N8-Systemen (N8 Kit 1.3, `scripts/n8-admin.sh`, `n8_crash.py`) – ausgelöst durch häufige Abstürze von N8 Crosslink,
bei denen nicht erkennbar war, welcher Teil schuld ist. Überwacht werden hier: Dashboard (`frnadn.service`) und der Java-FRN-Server (`frn-server.service`).
- **Absturz-Wächter (systemd, als root):** jeder Dienst bekommt ein Drop-in `n8-crashwatch-<id>.conf` mit `ExecStopPost=+… crash-hook`.
  Nach **jedem** Ende prüft er, ob es geplant war (Stoppen/Neustart von Hand, Update, Keep-Alive, Herunterfahren); alles andere wird
  festgehalten – **Absturz durch ein Signal**, **Fehlercode**, **systemd-Watchdog**, **Speicher voll (OOM)**, **Zeitüberschreitung**,
  **unerwartetes Ende** – mit den letzten 200 Journal-Zeilen, Coredump-Kurzinfo und Python-Stack. systemd startet den Dienst sofort neu
  (Dienste ohne `Restart=` bekommen `Restart=on-failure`); bleibt er ausgefallen (`failed`), startet ihn der Keep-Alive neu (`reset-failed`,
  höchstens 4× je Stunde). Neustarts durch den Keep-Alive werden mit Grund festgehalten.
- **Welcher Teil war es?** Die Python-Dienste melden selbst: **faulthandler** (Stack aller Threads beim harten Ende, auch beim Watchdog),
  **Hänger-Wächter** (Event-Loop steht > 8 s → Stack und Teil, z. B. „Datenbank ← Live-Daten“), abgestürzte Tasks und Threads.
  Teile: FRN-Protokoll · Live-Daten · System Manager · FRN-Fehlerprotokoll · Statistik · Datenbank · Backup · Update-Prüfung · HTTPS · Anmeldung · Einstellungen & System · Webinterface.
- **⚙️ Admin → 🖥️ System → 💥 Abstürze:** alle Befunde mit Zeit, Art, Teil, Ursache und vollständigem Protokoll zum Aufklappen, Zähler je Teil
  (7 Tage, als Filter) und die überwachten Dienste.
- **Hinweisfenster nach der Anmeldung:** neue Befunde erscheinen direkt nach dem Admin-Login als Fenster („Gelesen“, „Später“, „Alle Abstürze
  ansehen“) und als roter Zähler im Admin-Menü, bis sie als gelesen markiert sind.
- Konsole: `sudo /opt/adn-frn-server/scripts/n8-admin.sh crashes`; einrichten von Hand: `sudo /opt/adn-frn-server/scripts/n8-admin.sh setup-crashwatch` (macht sonst „Update jetzt“, die
  Berechtigungsprüfung oder spätestens der Keep-Alive). Dateien im Datenordner: `crashes.jsonl`, `crash/<id>.log`.
- Neue Adressen (gleich in allen N8-Systemen): `GET /api/admin/crashes`, `GET /api/admin/crashes/<id>`, `POST /api/admin/crashes/ack`.

## 2.14.4 – 2026-11-25

### 🖥️ Ganze Browser-Breite und dieselbe Menüleiste in allen N8-Systemen
- **Volle Breite:** Seiten, Fußzeile nutzen jetzt die **ganze Breite des Browserfensters** (vorher höchstens 1400–1600 Pixel);
  der Rand passt sich der Fensterbreite an (10–24 Pixel).
- **Einheitliche Menüleiste nach dem Vorbild des ADN-FRN-Servers:** gleiche Höhe (64 px), gleiche Glas-Kachel, Logo 46 px, Titel 19 px mit
  Farbverlauf, Untertitel 12 px, das Hauptmenü als Pille in der Mitte (gleiche Knöpfe, gleiche Hervorhebung der aktiven Seite), rechts Links,
  DE | EN und Anmelden/Benutzer in gleicher Größe, darunter die schmale Statusleiste. Das gilt in HobbyRadioPortal, ADN-FRN-Server,
  HBlink4-FreeRadioID, N8 Hotspot und N8 Crosslink gleich (N8 Kit 1.2 „N8 Frame“, gemeinsam in `n8-kit.css`). Auf dem Handy bleibt die
  jeweilige kompakte Kopfzeile.

## 2.14.3 – 2026-11-25

### 🧭 Baum-Menü: anfangs zugeklappt, überall gleich
- Alle Gruppen des Admin-Menüs sind jetzt **standardmäßig zugeklappt** – offen ist nur die Gruppe der gerade gewählten Seite.
  Eine Gruppe, die du aufklappst, bleibt offen, bis du den Browser-Tab schließt (vorher wurde der Zustand dauerhaft gespeichert).
- Das gilt in allen fünf N8-Systemen gleich: HobbyRadioPortal, ADN-FRN-Server, HBlink4-FreeRadioID, N8 Hotspot und N8 Crosslink
  nutzen denselben Baum aus dem N8 Kit, mit denselben Gruppen in derselben Reihenfolge.
- Status-Punkte im Menü (z. B. ● online) stehen schlank rechts statt als Plakette.

## 2.14.2 – 2026-11-25

### 🧭 Frühere Unter-Menüs im Baum-Menü
- **⚙️ Einstellungen** hat jetzt Zweige im Baum: FRN-Server · SystemManager · Operator · Dashboard · Daten · HTTPS & Web.
  Ein Klick auf einen Zweig zeigt nur diesen Abschnitt in voller Breite, „Einstellungen“ selbst zeigt wie bisher alle (mit der Java-Kachel oben).
- **💾 Backup** hat wie in den anderen N8-Systemen einen eigenen Eintrag unter **System** (nur für den Superadmin); „Server & Daten“ zeigt
  nur noch FRN-Server, Rechner und Datenbank.
- N8 Kit: Einträge im Baum können Zweige haben (`children`); sie klappen mit ihrem Eintrag auf und zu.

## 2.14.1 – 2026-11-25

### 🐛 Fix: Keep-Alive startete einen gesunden Dienst neu („Antwort ist kein JSON“)
- **Ursache:** Macht die Anwendung HTTPS selbst (Let's Encrypt im Dashboard), leitet Port 80 nur noch auf `https://<domain>/` weiter.
  Der Keep-Alive fragte `http://127.0.0.1/api/n8/health`, bekam die Weiterleitung statt der Antwort, meldete „Antwort ist kein JSON“ –
  und startete deswegen den Java-FRN-Server (alle Stationen flogen raus) alle paar Minuten neu (bis zur Grenze von 4× je Stunde). Die Prüfung der Weboberfläche hielt die
  Weiterleitung dagegen fälschlich für „gesund“.
- **Weiterleitungen werden jetzt verfolgt – aber immer zurück auf 127.0.0.1** (gleiches Schema, gleicher Port, gleicher Pfad). So wird
  stets die Anwendung auf diesem Rechner gefragt, nie die öffentliche Adresse (kein Hairpin-NAT, kein Zertifikatsproblem, und
  `/api/n8/health` bleibt „nur lokal“). Eine Weiterleitung ins Leere zählt nicht mehr als „Weboberfläche antwortet“.
- **„Zustand unbekannt“ führt nie mehr zu einem Neustart.** Startet ein Dienst neu, dann nur, wenn die Anwendung ihn ausdrücklich als
  gestört meldet (oder wenn er nicht läuft / sein Port nichts annimmt). Keine oder eine fremde Antwort von `/api/n8/health` wird mit
  ❔ angezeigt und einmal ins Protokoll geschrieben – ob die Weboberfläche selbst lebt, prüft weiterhin ihre eigene Prüfung.
- Gilt für alle fünf N8-Systeme (gemeinsames `scripts/n8-admin.sh`).

> Auf bestehenden Servern genügt „Update jetzt“; danach den Keep-Alive unter *System → 💓 Keep-Alive* wieder fortsetzen, falls er pausiert ist.

## 2.14.0 – 2026-11-25

### 🧭 Neu: Admin-Menü als Baum – in allen fünf N8-Systemen gleich
- Die Reiterleiste im Adminbereich ist einem **Baum-Menü links** gewichen, wie im HobbyRadioPortal. Alle N8-Systeme
  (HobbyRadioPortal, ADN-FRN-Server, HBlink4-FreeRadioID, N8 Hotspot, N8 Crosslink) nutzen jetzt **dieselben Gruppen in derselben
  Reihenfolge**: 📡 Betrieb · 👥 Benutzer & Zugang · 🎨 Darstellung · 🌐 Netz & Domains · 🖥️ System.
- Gruppen lassen sich auf- und zuklappen (der Zustand wird im Browser gemerkt); auf dem Handy wird das Menü zu einer
  aufklappbaren Leiste „☰ <aktueller Bereich>“.
- ADN: Einstellungen, Räume, Server-Listen, FRN-Konten, Import und Protokolle unter **Betrieb**; „🖥️ Server & Daten“
  (FRN-Server, Rechner, Datenbank, Backup) unter **System**.

### 🖥️ Neu: Derselbe Bereich „System“ überall
- **⬆️ Update · 🧩 Dienste · 🔐 Berechtigungen & sudo · 💓 Keep-Alive** sind gemeinsame Ansichten des N8 Kit 1.1.0 und sehen in
  allen N8-Systemen gleich aus – mit denselben Texten, Knöpfen und Adressen (`/api/admin/services`, `/api/admin/perms`,
  `/api/admin/perms/fix`, `/api/admin/keepalive`, `/api/admin/update-log`).
- **Update:** Stand, GitHub, „Jetzt prüfen“, „Update jetzt installieren“ und daneben das **Update-Protokoll** mit dem Ergebnis des
  letzten Updates (erfolgreich / zurückgenommen).
  Unter dem Update steht wie bisher der **☕ Java-FRN-Server** von freeradionetwork.de mit eigenem Aktualisieren-Knopf.
- **Dienste:** Zustand, Autostart-Schalter und Starten · Stoppen · Neu starten – nur, was die sudo-Regeln freigeben.
- **Berechtigungen & sudo:** zeigt zuerst nur, was nicht stimmt; die bestandenen Prüfungen klappen auf. **🛠️ Korrigieren**
  repariert und prüft erneut.
- **Keep-Alive:** Zustand je Dienst, Internet, Heartbeat, Einstellungen und Protokoll.

### 🔓 Update ohne Passwort
- „Update jetzt installieren“ braucht kein Passwort (war beim ADN schon so) – eine Admin-Sitzung genügt.

### 📐 Symmetrische Blöcke
- Kacheln einer Reihe sind im Adminbereich jetzt **gleich hoch**, die Knöpfe stehen unten bündig; eine einzelne letzte Kachel
  nimmt die volle Breite ein.

### 🧰 Kleinigkeiten
- N8 Kit: Schriften im Menü und auf den Knöpfen werden jetzt richtig gesetzt (die `font`-Kurzform mit `inherit` war ungültig und
  wurde vom Browser verworfen).

### 💓 Neu: Keep-Alive – hohe Verfügbarkeit ohne Zutun
- **Dienste-Wächter:** Ein systemd-Timer (`frnadn-keepalive.timer`) prüft **jede Minute als root**, ob jeder Dienst wirklich arbeitet –
  nicht nur „läuft“, sondern das Dashboard antwortet, der Java-FRN-Server läuft **und** nimmt Stationen auf seinem FRN-Port an. Bleibt ein Dienst 3 Minuten krank (oder steht er auf `failed`), wird er neu gestartet,
  **höchstens 4× je Stunde** – danach meldet der Keep-Alive „aufgegeben“ statt endlos neu zu starten.
- **Netz-Wiederverbindung:** Fällt das Internet aus (1.1.1.1, 9.9.9.9 und github.com auf Port 443 nicht erreichbar), startet der
  Keep-Alive **nicht** sinnlos neu. Ist das Netz nach mindestens 60 s wieder da, startet er die Netzdienste einmal neu, damit
  alle Verbindungen sofort wieder stehen (abschaltbar).
- **Externer Ping (Heartbeat):** Optional eine Adresse für Uptime Kuma („Push“) oder Healthchecks.io – jede Minute ein Ping,
  wenn alles gesund ist, sonst die Fehler-Adresse. So merkst du auch, wenn der ganze Server weg ist.
- **Von Hand gestoppt bleibt gestoppt:** Wer einen Dienst im Webinterface stoppt, wird vom Keep-Alive nicht übergangen; erst
  „Starten“ gibt ihn wieder frei. Für Wartungen gibt es **⏸ 1 h pausieren**.
- Neue lokale Adresse `/api/n8/health` (nur von 127.0.0.1, nie über einen Proxy) liefert dem Keep-Alive den echten Zustand.
- Eingerichtet von `install`, `update` und `fix-perms`; `check-perms` prüft den Timer mit.

> Auf bestehenden Servern genügt „Update jetzt“ im Webinterface; der Keep-Alive richtet sich dabei selbst ein.

## 2.13.2 – 2026-11-25

### 🐛 Fix: „sudo verweigert“ und „Installiert vX · ?“ nach dem Umstellen auf das N8 Admin-Kit
- **git `safe.directory`:** Seit der Programmordner root gehört, lehnte git ihn für den Dienst-Benutzer ab („dubious ownership“) –
  das Webinterface sah keinen Commit (`?`) und bot kein „Update jetzt“ an. `fix-perms` trägt den Ordner jetzt systemweit ein
  (`git config --system`), `check-perms` prüft es.
- **Webinterface noch mit NoNewPrivileges gestartet:** Die Unit war korrigiert, der laufende Prozess aber noch alt – sudo wurde
  abgelehnt. `check-perms` prüft jetzt den **laufenden** Prozess (`/proc/<pid>/status`), `fix-perms` startet das Webinterface dann
  nach 5 Sekunden selbst neu (auch wenn „Korrigieren“ im Browser gedrückt wurde).
- Die Meldung „sudo verweigert“ zeigt jetzt auch den Grund (letzte Zeile von sudo).

> Einmal auf der Konsole: `sudo git -c safe.directory=/opt/adn-frn-server -C /opt/adn-frn-server pull --ff-only && sudo /opt/adn-frn-server/scripts/n8-admin.sh fix-perms`

## 2.13.1 – 2026-11-25

### 🐛 Fix: `n8-admin.sh fix-perms` brach nach „korrigiere …“ ohne Meldung ab
- Im gemeinsamen N8 Admin-Kit endete die Hilfsfunktion für die Ausschlüsse im Programmordner (`prune_args`) mit dem Status des
  letzten Vergleichs. Unter `set -e` beendete das das ganze Skript – **ohne Fehlermeldung**, direkt nach „korrigiere …“.
  Betroffen waren `fix-perms`, „Korrigieren“ im Webinterface und **jedes Update** (Abbruch nach der Zeile „Version: …“, also vor
  Rechten, sudo, Neustart und Prüfung). Die Funktion gibt jetzt immer 0 zurück; im Test korrigiert `fix-perms` alle Fehler und prüft erneut.
- `n8-admin.conf`: Werte aus der Unit (`grep … | cut`) brechen nicht mehr ab, wenn die Zeile fehlt (z. B. kein eigener Port eingetragen).

> **Auf bestehenden Servern einmalig** (das laufende alte Skript kann sich nicht selbst reparieren):
> `sudo git -c safe.directory=/opt/adn-frn-server -C /opt/adn-frn-server pull --ff-only && sudo /opt/adn-frn-server/scripts/n8-admin.sh fix-perms`

## 2.13.0 – 2026-11-25

**🧩 Gleiches Update-System wie N8 Crosslink – mit Berechtigungsprüfer, sudo-Einrichtung und schlanker Dienste-Übersicht. HobbyRadioPortal-Anbindung entfernt.**

### ⬆️ Update über den Root-Helfer `scripts/n8-admin.sh`
- Neuer gemeinsamer Helfer der N8schicht-Projekte (dieselbe Datei in allen Repositorys, Projektdaten in `scripts/n8-admin.conf`).
- **Update jetzt installieren** legt nur `update.request` im Datenordner an; die Path-Unit `frnadn-update.path` startet
  `frnadn-update.service` als root → `n8-admin.sh update --auto`: nur vorspulen (nie über von Hand geänderte Dateien oder eigene Commits),
  Python-Pakete, FRN-Konfiguration, Berechtigungen und sudo prüfen/korrigieren, FRN-Server und Dashboard neu starten, Weboberfläche prüfen –
  antwortet sie 90 s nicht, **zurück auf den alten Stand**. Ergebnis unter *Letztes Update*, Protokoll per **📜 Update log**.
- `scripts/update.sh` macht von der Konsole genau dasselbe. Der alte *N8 update guard* (`n8-update-guard.sh`, `ExecStartPre` in der Unit,
  `n8_update_guard.py`) entfällt; das Update entfernt die Zeile aus der installierten Unit.
- **Das Programmverzeichnis gehört jetzt root** und ist für den Dienst schreibgeschützt (vorher gehörte es `frnadn`, damit das Dashboard sich
  selbst per git aktualisieren konnte). Nur Datenordner und der Ordner des Java-Servers gehören `frnadn`.

### 🔐 Berechtigungen & sudo (Admin → System)
- Prüfliste mit Abzeichen und **🛠️ Korrigieren** (prüfen → korrigieren → erneut prüfen): Dienstbenutzer und Gruppen (`systemd-journal`, `adm`),
  Programm root-eigen und nicht beschreibbar, Skripte 755, venv, Datenordner 750, Datenbank und Backups 600, systemd-Units root 644,
  Update-Auslöser aktiv, sudo installiert/eingebunden/gültig/aktuell/wirksam, `n8-admin.json` aktuell. Konsole:
  `sudo scripts/n8-admin.sh check-perms` bzw. `fix-perms`. Root-Aufgaben verlassen dabei die Dienst-Sandbox per `systemd-run`.
- sudo-Freigaben jetzt in `/etc/sudoers.d/frnadn-n8admin` (die alte `/etc/sudoers.d/frnadn` wird beim Update entfernt), alles exakte Befehle.

### 🧩 Dienste (Admin → System)
- Schlanke Liste von `frnadn.service`, `frn-server.service` und dem Update-Auslöser: Status, **Autostart**-Schalter, **▶ / 🔄 / ⏹**.
  Stoppen und Autostart aus fragen nach. API: `GET /api/admin/services`, `POST /api/admin/services/{unit}/{action}`, `GET /api/admin/perms`,
  `POST /api/admin/perms/fix`, `GET /api/admin/update-log`. Alles im Audit-Log.

### 🧹 HobbyRadioPortal entfernt
- Keine lokale Portal-Schnittstelle mehr (`X-HobbyRadioPortal`, `FRNADN_PORTAL_LOCAL`, Pseudo-Benutzer „portal“); alle Admin-Adressen brauchen
  eine Anmeldung. Installer ohne `FRNADN_SETUP_FILE`; Portal-Hinweise in Benutzer-, Backup- und SystemManager-Bereich und in der Doku entfernt.
  `FRNADN_RESTORE` (Backup ohne Fragen) und `FRNADN_BEHIND_PROXY` bleiben.

### ⚠️ Einmalig nach dem Update
- Wer von 2.12 oder älter kommt: einmal `sudo /opt/adn-frn-server/scripts/n8-admin.sh fix-perms` – richtet Besitzer, sudo und „Update jetzt“ ein.

### Doku & Tests
- updates.md (neuer Ablauf), betrieb.md (Dienste & Berechtigungen), installation.md, sicherheit.md, adminbereich.md, README; Screenshots
  `admin-services.png`, `admin-system.png`. Tests für die neue API, die Verdrahtung und ohne die Portal-Tests.

## 2.12.0 – 2026-11-25

**📋 Öffentliches FRN-Fehlerprotokoll eingebaut.** Der FRN-SystemManager von freeradionetwork.de schreibt jede abgelehnte Anmeldung in ein
öffentliches Fehlerprotokoll (<http://log.freeradionetwork.de:60080/error_log.php>, auf der Website unter *Hilfe → Fehlerprotokoll*). adn-frn-server nutzt es jetzt zur Fehlersuche.
Ausführlich: [docs/de/betrieb.md](docs/de/betrieb.md#-bei-problemen-immer-zuerst-das-öffentliche-frn-fehlerprotokoll).

### Neu
- **Admin → 📜 Logs → 📋 Öffentliches FRN-Fehlerprotokoll:** Einträge zu dieser Server-Adresse (`frn.address`), dem Rufzeichen des Betreibers
  und zu Stationen, die hier in der letzten Stunde abgewiesen wurden. Gleiche Meldungen zusammengefasst („6× seit 09:58“), mit Erklärung und
  Abhilfe (Deutsch/Englisch), Abzeichen „nichts zu diesem Server“ / „7 Einträge zu diesem Server“ / „nicht erreichbar“, andere Stationen im
  Protokoll als Hinweis. **🔄 Neu laden**, **📋 Komplettes Fehlerprotokoll öffnen**.
- **Automatische Prüfung:** alle 10 Minuten, bei einem SystemManager-Fehler alle 2 Minuten; neue Einträge kommen als Ereignis `frnlog` ins
  Live-Log (jede Meldung einmal). Nicht im eigenständigen Betrieb und nicht in der Demo.
- **Hinweise mit Link** unter *Settings → SystemManager* und im Fehlerkasten des Java-Servers.
- Bekannte Meldungen mit Abhilfe: *wrong FRN password*, *multiple connections at the same time with the same connection data …*,
  *not listening on specified port*; weitere per Stichwort (gesperrt, unbekannt, Version, E-Mail); Unbekanntes mit dem englischen Hinweis
  des SystemManagers.
- API `GET /api/admin/frn-errorlog[?force=1]` – auch für das HobbyRadioPortal auf demselben Rechner. Modul `frnadn/frn_errorlog.py`
  (JSON `?action=getLog`, 60 s Zwischenspeicher).
- Demo: Beispielprotokoll ohne Internet. Tests: `tests/test_frn_errorlog.py`.
- Doku: Betrieb (neuer Abschnitt „Bei Problemen immer zuerst …“ mit Tabelle), Adminbereich (Logs, SystemManager), README; Screenshots
  `admin-frn-errorlog.png` und `admin-sysman.png` neu.

## 2.11.0 – 2026-11-25

**🔌 HobbyRadioPortal ohne Token.** Läuft das Portal auf demselben Rechner, verwaltet es diesen Server direkt – kein Token anlegen,
kopieren und eintragen mehr. Ausführlich: [docs/de/adminbereich.md](docs/de/adminbereich.md#-hobbyradioportal-auf-diesem-server).

### Was sich ändert
- **API-Tokens sind weg:** Kachel *Portal-Zugang (API-Token)* unter Users, die Adressen `/api/admin/api-tokens` und
  `python -m frnadn api-token` gibt es nicht mehr; die Tabelle `api_tokens` wird beim Start gelöscht. Unter Users steht stattdessen ein
  kurzer Hinweis, was das Portal darf.
- **Als Portal gilt nur ein direkter Aufruf auf diesem Rechner:** Absender und `Host` Loopback (`127.0.0.1`, `::1`, `localhost`),
  Kopfzeile `X-HobbyRadioPortal: 1` und **keine** Proxy-Kopfzeile (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`, `X-Forwarded-Host/-Proto`,
  `Via`, `CF-Connecting-IP`, `True-Client-IP`, `X-Client-IP`). Anfragen über nginx/Caddy – die auch von 127.0.0.1 kommen – und von anderen
  Rechnern sind damit nie „das Portal“. nginx des Portals setzt `X-Forwarded-For`, uvicorn meldet dann sogar die echte Adresse.
- **Was das Portal darf, bleibt gleich:** Einstellungen (ohne `https.*`), Räume, Zugriffslisten, Start/Stopp/Neustart des Java-Servers,
  FRN-Passwort anfordern, Protokoll – nie Benutzer, Sitzungen, FRN-Konten, Updates, System, Theme, Links, Import, Logs oder HTTPS. Der
  CSRF-Kopf `X-N8` bleibt Pflicht.
- Im Protokoll steht das Portal als `portal (<Portal-Benutzer>)` (vorher `api:<Token-Name> (…)`).
- **Abschalten:** `FRNADN_PORTAL_LOCAL=0` in der Umgebung des Dienstes (dann zeigt das Portal nur Live-Daten).

### ⚠️ Eigener Reverse-Proxy
- Steht vor dem Dashboard ein eigener Proxy, muss er `X-Forwarded-For` setzen (`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`) –
  die Vorlagen der N8schicht-Projekte und des Portals tun das. Jedes Programm auf diesem Rechner könnte sich als Portal ausgeben; wer
  das nicht will, schaltet es ab (siehe oben).

### Doku und Tests
- [Admin-Portal](docs/de/adminbereich.md), [Betrieb](docs/de/betrieb.md), [Sicherheit](docs/de/sicherheit.md) umgestellt; Screenshot
  *Users* neu, *admin-api-tokens.png* entfernt.
- `tests/test_portal_local.py`: erlaubte und gesperrte Adressen, Proxy-Kopfzeilen und öffentlicher Host werden abgelehnt, ohne Kennung oder
  von einem anderen Rechner kein Zugriff, CSRF bleibt, Abschalten.

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
