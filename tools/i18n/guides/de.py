UI = {
    'title': 'Schritt für Schritt', 'contents': 'Inhalt', 'lang': 'Sprache', 'more': 'Ausführliche Beschreibung (Deutsch)',
    'step': 'Schritt', 'back': 'Zurück zur Übersicht', 'shots': 'Die gelben Ziffern im Bild gehören zu den Ziffern im Text.',
}
SHARED = {
    'lang': ('Sprache wählen', 'Oben rechts öffnet **🌐 DE ▾** ① das Sprachmenü ② mit neun Sprachen. Die Wahl gilt sofort und für alle N8-Oberflächen auf diesem Server. Beim ersten Besuch gilt die Sprache des Browsers.'),
    'domains': ('Eigene Domain mit HTTPS', 'Unter **🌐 Netz, Ports & Domains → 🔒 Domains & HTTPS** ① trägst du eine Domain ein, die per DNS auf den Server zeigt, dazu eine E-Mail-Adresse für Let’s Encrypt ②. Das Zertifikat wird geholt und automatisch erneuert. Ports 80 und 443 müssen aus dem Internet erreichbar sein.'),
    'users': ('Benutzer anlegen', 'Unter **👥 Benutzer & Zugang → Benutzer** ① legst du weitere Konten an und vergibst die Rolle ②. Admins sehen IP-Adressen und ändern Einstellungen, Benutzer sehen nur das Dashboard. Unter **Sitzungen** beendest du Anmeldungen, das **Protokoll** zeigt jede Änderung.'),
    'update': ('Aktualisieren', 'Unter **🖥️ System → ⬆️ Update** ① siehst du die installierte Version und ob GitHub eine neuere hat ②. **⬆️ Update jetzt installieren** lädt sie, prüft danach die Weboberfläche und stellt bei einem Fehler automatisch die vorherige Version wieder her. Ein Passwort ist dafür nicht nötig.'),
    'backup': ('Sichern', 'Unter **🖥️ System → 💾 Backup** ① erstellst du eine verschlüsselte Sicherung aller Daten ② und spielst sie bei Bedarf wieder ein – auch auf einem neuen Server. Bewahre das Passwort der Sicherung gut auf: ohne es lässt sie sich nicht öffnen.'),
    'login': ('Anmelden', 'Oben rechts auf **🔐 Anmelden** klicken. Im Anmeldefenster ① Benutzername und Passwort eingeben; 👁 zeigt das Passwort, „Angemeldet bleiben“ spart die Anmeldung beim nächsten Mal. Nach fünf falschen Versuchen ist der Name für 15 Minuten gesperrt. Angemeldet erscheinen Avatar und Name ▾ mit Konto, Adminbereich und Abmelden.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN-FRN-Server', 'intro': 'Der ADN-FRN-Server ist ein FreeRadioNetwork-Server mit Dashboard, Adminbereich, News-Portal und Mailserver. Diese Anleitung führt durch die ersten Schritte.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installieren', 'Auf einem Debian- oder Ubuntu-Server als Benutzer mit sudo-Rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nDer Installer richtet Java, den FRN-Server, das Dashboard, die Dienste und die Rechte ein und fragt nach dem Superadmin. Danach ist das Dashboard unter `http://<server>:8080` erreichbar.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'FRN-Server einrichten', 'Im Adminbereich unter **📡 Betrieb → ⚙️ Einstellungen → 🛰️ FRN-Server** ① stehen Adresse, Port und Zeitgrenzen des FRN-Servers ②. Unter **🌐 SystemManager** wählst du, ob der Server beim SystemManager angemeldet ist oder eigenständig läuft. Nach dem Speichern den FRN-Server neu starten.'),
            ('rooms', 'Räume anlegen', 'Unter **🏠 Räume** ① legst du die Räume (Nets) an ②: Name, Emoji, Besitzer, wer senden darf und den Papagei-Echotest. Die Reihenfolge im Dashboard bestimmst du mit ▲ ▼. Der FRN-Server übernimmt Änderungen nach einem Neustart.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink verbindet FRN, DMR und Zello zu einem gemeinsamen Funknetz. Diese Anleitung führt durch die ersten Schritte.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Installieren', 'Auf einem Debian- oder Ubuntu-Rechner (auch Raspberry Pi) mit sudo-Rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nDer Installer richtet Programm, Dienst, Vocoder und Rechte unter `/opt/n8crosslink` ein. Danach ist die Oberfläche unter `http://<rechner>:8080` erreichbar.'),
            ('setup', 'Superadmin anlegen', 'Beim ersten Aufruf erscheint **Superadmin anlegen** ①: Benutzername und ein Passwort mit mindestens 8 Zeichen, dann wiederholen. Dieses Konto darf alles, auch Sicherungen wiederherstellen. Später meldest du dich im selben Fenster an.'),
            ('lang', None, None),
            ('frn', 'FRN verbinden', 'Im Adminbereich unter **📡 Betrieb → 📻 FRN** ① trägst du Server, Port, E-Mail und FRN-Passwort ein ②. Den **Raum** wählst du aus der Liste, die direkt vom FRN-Server gelesen wird. Noch kein FRN-Passwort? Es lässt sich hier beim SystemManager anfordern.'),
            ('dmr', 'DMR verbinden', 'Unter **📡 DMR** ① stehen DMR-Server, Peer-ID, Passwort und Talkgroups ②. Bei HBlink4-FreeRadioID ist das Passwort dein persönliches FreeRadioID-Passwort – mit der Server-Passphrase ist die Brücke nur Gast und darf nicht in alle Talkgroups senden.'),
            ('routes', 'Routing festlegen', 'Unter **🔀 Routing** ① legst du fest, welche Quelle in welches Netz geht ②, z. B. FRN → DMR und DMR → FRN. Eine Sperrzeit nach dem Senden verhindert Ping-Pong zwischen den Netzen. Änderungen gelten sofort.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Sichern und neu anfangen', 'Unter **🖥️ System → 💾 Backup & Neuanfang** ① erstellst du eine verschlüsselte Sicherung ② – der Schlüssel ist das Superadmin-Passwort zum Zeitpunkt der Sicherung. Hier lassen sich auch Statistik oder alle Einstellungen zurücksetzen.'),
        ],
    },
    'hotspot': {
        'name': 'N8-Hotspot', 'intro': 'Der N8-Hotspot ist eine Weboberfläche für MMDVMHost und DMRGateway auf einem Raspberry Pi mit Modem-Hat. Diese Anleitung führt durch die ersten Schritte.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installieren', 'Am einfachsten mit dem fertigen DietPi-Image: auf eine SD-Karte schreiben, in den Raspberry Pi stecken, starten. Alternativ auf einem laufenden DietPi:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nDanach ist die Oberfläche unter `http://n8-hotspot.local` (oder der IP-Adresse) erreichbar.'),
            ('login', 'Anmelden', 'Oben rechts auf **🔐 Anmelden** klicken und im Anmeldefenster ① mit dem Werks-Login **n8schicht / n8schicht** anmelden. 👁 zeigt das Passwort, „Angemeldet bleiben“ spart die Anmeldung beim nächsten Mal.'),
            ('password', 'Eigenes Passwort setzen', 'Solange der Werks-Login gilt, öffnet sich **🔑 Mein Konto** ① und es lassen sich keine Einstellungen ändern. Wähle einen eigenen Benutzernamen und ein Passwort mit mindestens 8 Zeichen – danach funktioniert der Werks-Login nicht mehr.'),
            ('lang', None, None),
            ('station', 'Station eintragen', 'Im Adminbereich unter **📡 Betrieb → ⚙️ Einstellungen → 📻 Station** ① trägst du Rufzeichen, DMR-ID und Standort ein ②. Zwei Ziffern als Hotspot-Suffix machen die Hotspot-ID eindeutig, wenn du mehrere Geräte hast.'),
            ('modem', 'Modem einstellen', 'Unter **📡 Modem** ① wählst du das Modem-Board ② – das füllt Port, Geschwindigkeit und Simplex/Duplex aus. **Modem suchen** findet den Port selbst. Dazu kommen Sende- und Empfangsfrequenz; bei Simplex sind beide gleich.'),
            ('network', 'Mit dem DMR-Server verbinden', 'Unter **🛰️ DMR-Netz** ① wählst du den Server aus der Liste ② (füllt Name, Adresse und Port) und trägst das Passwort ein – bei der N8schicht dein FreeRadioID.net-Passwort für vollen Zugang.'),
            ('cal', 'Frequenz kalibrieren', 'Unter **🎛️ Kalibrierung** ① findest du den Frequenz-Offset deines Modems ②: Starten, mit dem Funkgerät auf der angezeigten Simplex-Frequenz senden und die Frequenz verschieben, bis die BER am niedrigsten ist (ideal unter 1 %). Dann den Offset speichern.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID ist ein DMR-Server mit FreeRadioID-Anmeldung, Dashboard, OpenBridge und APRS. Diese Anleitung führt durch die ersten Schritte.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installieren', 'Auf einem Debian- oder Ubuntu-Server mit sudo-Rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nDas Setup fragt Servername, Ports, Superadmin und FreeRadioID-Anmeldung ab und richtet die Dienste ein. Danach ist das Dashboard unter `http://<server>:8080` erreichbar.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'DMR-Server einstellen', 'Im Adminbereich unter **📡 Betrieb → 🛰️ DMR-Server** ① stehen Port (Standard 62031), Zeiten und Verbindungen zu anderen Servern ②. Repeater und Hotspots verbinden sich auf diesen Port; Änderungen gelten nach einem Neustart des DMR-Servers.'),
            ('access', 'Zugang und FreeRadioID', 'Unter **⚙️ Einstellungen** ① legst du fest, wer das Dashboard sieht, und den Zugang für Repeater und Hotspots ②: Passphrase, Talkgroups und die **FreeRadioID-Anmeldung**. Mit FreeRadioID meldet sich jede Station mit ihrem persönlichen Passwort an; die Passphrase wird zum Gastzugang mit eigenen Talkgroups.'),
            ('aprs', 'APRS einschalten', 'Unter **📡 APRS** ① schaltest du den APRS-Server mit Karte ein ②: Server-ID (dein Rufzeichen mit SSID), offene Ports für APRS-Apps und iGates sowie der Uplink zu APRS-IS. GPS-Positionen aus dem DMR-Verkehr erscheinen dann auf der Karte.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
