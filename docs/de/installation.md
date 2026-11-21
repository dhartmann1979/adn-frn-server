# 📦 Installation

[← Übersicht](../../readme.md) · **Installation** · [Dashboard](dashboard.md) · [Admin-Portal](adminbereich.md) · [Konfiguration](konfiguration.md) · [Betrieb & Fehlersuche](betrieb.md)

Installiert werden zwei Dienste:

| Dienst | Was | Wo |
|---|---|---|
| `frn-server` | der **Java-FRN-Server von freeradionetwork.de** (FRN_Server.jar) | Programm `/opt/frn-server`, Konfiguration `/var/lib/frnadn/frn` |
| `frnadn` | Dashboard und Admin-Portal | Programm `/opt/adn-frn-server`, Datenbank `/var/lib/frnadn/frnadn.db` |

Alle Einstellungen liegen in der SQLite-Datenbank. Daraus schreibt frn_adn nur die Dateien, die der Java-Server braucht.

## Voraussetzungen

| | |
|---|---|
| System | Debian 11/12/13, Ubuntu 22.04 oder neuer, Raspberry Pi OS (64 oder 32 Bit) |
| Java | wird installiert (`default-jre-headless`, Java 17 oder 21) |
| Python | 3.9 oder neuer (wird installiert) |
| Speicher | ca. 300 MB RAM für Java und Dashboard |
| FRN-Konto | für den Betrieb am SystemManager: dein FRN-Benutzerkonto (E-Mail und das Passwort, das der SystemManager per Mail geschickt hat) |
| Netz | **TCP 10024** (FRN, änderbar) von außen erreichbar, **TCP 80** fürs Dashboard |

## Schritt für Schritt

```bash
git clone https://github.com/dhartmann1979/adn-frn-server
cd adn-frn-server
chmod +x scripts/install.sh scripts/update.sh   # falls beim Kopieren Rechte verloren gingen
sudo ./scripts/install.sh
```

Jede Frage hat eine Vorgabe in `[Klammern]`, Enter übernimmt sie.

<p align="center"><img src="../images/install-1.png" alt="Installation Schritt 1–4" width="85%"></p>

| Schritt | Was passiert |
|---|---|
| **1 System prüfen** | Betriebssystem, Architektur, systemd, apt |
| **2 Pakete** | Python, venv, curl, unzip und **Java** |
| **3 FRN-Server** | lädt `FRN_Server.zip` von **freeradionetwork.de**, entpackt `FRN_Server.jar` nach `/opt/frn-server`. Der Installer lädt das Java-FRN-Paket für die neue Installation herunter. Eine bereits vorhandene JAR wird nicht übernommen; bei erkannter Altinstallation bricht der Installer vorher ab |
| **4 Dashboard** | kopiert das Dashboard nach `/opt/adn-frn-server`, legt die Python-Umgebung, den Dienstbenutzer `frnadn` und den Befehl `frnadn` an |
| **5 Superadmin** | Benutzername und Passwort (mind. 10 Zeichen, zweimal) – gespeichert als scrypt-Hash |
| **6 FRN-Server einrichten** | Betriebsart, Serveradresse, Port, Besitzer, Räume, Titel |
| **7 Dienste** | richtet `frn-server.service` und `frnadn.service` ein, startet beide, öffnet die Ports in `ufw` |
| **8 Prüfen** | wartet, bis der FRN-Server lauscht, und zeigt Fehlermeldungen des SystemManagers verständlich an |

<p align="center"><img src="../images/install-2.png" alt="Installation Schritt 5–8" width="85%"></p>

### Schritt 6: Betriebsart

**1 – am SystemManager (Vorgabe).** Der Server meldet sich bei `sysman.freeradionetwork.de` an, erscheint im FRN-System (FRN-Client, [FRN Browser](https://tools.freeradionetwork.de:43448/FRN_Browser/)) und lässt die Logins der Clients vom SystemManager prüfen. Gefragt werden:

| Frage | Parameter | Bedeutung |
|---|---|---|
| E-Mail deines FRN-Kontos | `sysman_auth_emailaddr` | das Konto, mit dem sich der Server anmeldet |
| Passwort dieses FRN-Kontos | `sysman_auth_password` | das Passwort aus der Mail des SystemManagers (verdeckte Eingabe) |
| Öffentlicher Hostname oder IP | `server_addr` | so erreichen Clients **und der SystemManager** den Server, z. B. `frn.die-n8schicht.de`. Keine LAN-Adresse! |
| FRN-Port | `server_port` | Vorgabe 10024 |

**2 – Stand-alone.** Ohne SystemManager, z. B. für einen eigenen Verbund oder das Heimnetz. Die Logins prüft die eigene Passwortliste (Admin-Portal → FRN accounts); auf Wunsch ist auch eine LAN-Adresse als Serveradresse erlaubt (`allowLANAddr`).

Danach:

| Frage | Bedeutung |
|---|---|
| Server-Besitzer: E-Mail | bekommt **OWNER**-Rechte in jedem Raum (`server_owner`); Enter = das FRN-Konto |
| Rufzeichen, Name | für die Kopfzeile des Dashboards |
| Räume | mit Komma getrennt. **Der erste wird `net00`** – beim Java-FRN-Server immer der Test-/Parrot-Raum (Echotest) |
| Standardraum | `default_net`: wohin Clients mit unbekanntem Raum kommen |
| Titel, öffentlich | Kopfzeile, Ansicht ohne Login |

> **Vor dem ersten Start:** Der SystemManager prüft, ob `server_addr:server_port` von außen erreichbar ist (Fehler −5). Portweiterleitung TCP 10024 im Router auf den Server einrichten.

### Ohne Fragen

```bash
sudo FRNADN_YES=1 ./scripts/install.sh       # alle Vorgaben
sudo frnadn set-superadmin admin              # Superadmin anlegen
```

Danach im Admin-Portal unter **Settings** Serveradresse und SystemManager-Konto eintragen und den FRN-Server neu starten.

Weitere Variablen: `FRNADN_DIR` (Vorgabe `/opt/adn-frn-server`), `FRNADN_PORT` (Web-Port, 80), `FRN_DIR` (`/opt/frn-server`), `FRN_ZIP=/pfad/FRN_Server.zip` (vorhandenes Paket statt Download).


## Alte Konfiguration optional übernehmen

Die Installation bleibt eine frische Installation mit neuer SQLite-Datenbank und neuem Java-FRN-Server. Es wird keine alte Installation automatisch ersetzt oder migriert. Wenn du die bisherigen Servereinstellungen behalten möchtest, melde dich nach Abschluss im Admin-Portal an und wähle **Admin → System → Import server.properties**. Lade ausschließlich die Datei `server.properties` aus der alten Installation hoch. Der Import übernimmt nur unterstützte Einstellungen und Raumdefinitionen. Alte Datenbanken, JAR-Dateien, ACL-Listen und FRN-Passwortdateien werden nicht kopiert.

Vor dem Import empfiehlt sich ein Backup des neuen Datenverzeichnisses. Nach dem Import den Java-FRN-Server über das Admin-Portal neu starten.

## Router und Firewall

| Port | Richtung | Wofür |
|---|---|---|
| TCP 10024 (bzw. `server_port`) | eingehend, Portweiterleitung | FRN-Clients **und** Prüfung durch den SystemManager |
| TCP 10025 | ausgehend | Verbindung zum SystemManager (normalerweise offen) |
| TCP 80 | eingehend, optional | Dashboard von außen |

`ufw` wird vom Installer automatisch freigegeben, falls aktiv.

## FRN-Client verbinden

Am SystemManager erscheint der Server im FRN-Client in der Serverliste. Stand-alone: im Client Server und Port direkt eintragen.

## HTTPS (optional)

Dashboard hinter einen Reverse-Proxy setzen, z. B. Caddy, und frn_adn auf Port 8080 installieren (`sudo FRNADN_PORT=8080 ./scripts/install.sh`):

```
frn.example.org {
    reverse_proxy 127.0.0.1:8080
}
```

## Aktualisieren

| Was | Wie |
|---|---|
| Java-FRN-Server | Admin-Portal → **System → Upgrade Java now** (lädt von freeradionetwork.de und startet den Dienst neu) |
| Dashboard | `cd /opt/adn-frn-server && sudo ./scripts/update.sh` – der FRN-Server läuft dabei weiter |

`install.sh` ist ausschließlich für eine frische Installation vorgesehen. Es bricht ab, wenn bereits eine FRN-Datenbank, eine vorhandene `server.properties` oder ein laufender FRN-Dienst erkannt wird. Für Updates ist `scripts/update.sh` vorgesehen; `install.sh` nicht erneut auf einem installierten System ausführen.

## Deinstallieren

```bash
sudo systemctl disable --now frnadn frn-server
sudo rm -rf /opt/frnadn /opt/frn-server /etc/systemd/system/frnadn.service /etc/systemd/system/frn-server.service \
            /etc/sudoers.d/frnadn /usr/local/bin/frnadn
sudo rm -rf /var/lib/frnadn       # löscht auch Statistik, Benutzer und Einstellungen!
sudo userdel frnadn
```
