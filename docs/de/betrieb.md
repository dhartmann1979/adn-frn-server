# 🩺 Betrieb & Fehlersuche

[← Übersicht](../../readme.md) · [Installation](installation.md) · [Dashboard](dashboard.md) · [Admin-Portal](adminbereich.md) · [Konfiguration](konfiguration.md) · **Betrieb & Fehlersuche** · [Updates](updates.md) · [Anleitungen](anleitungen.md)

## Dienste

```bash
systemctl status frn-server frnadn     # laufen sie?
journalctl -u frn-server -f            # Java-FRN-Server
journalctl -u frnadn -f                # Dashboard
tail -f /var/lib/frnadn/frn/logs/server.log
```

Beide Dienste laufen als Benutzer `frnadn` ohne Root-Rechte. frn_adn darf per sudoers-Regel (`/etc/sudoers.d/frnadn`) genau `frn-server` starten, stoppen, neu starten sowie *Reboot* und *Shut down* auslösen – sonst nichts.

`frn-server` startet nach einem Absturz nach **60 Sekunden** neu. Der Java-Server beendet sich bei schweren SystemManager-Fehlern selbst; die Wartezeit verhindert, dass er den SystemManager mit Anmeldeversuchen überflutet.

## Fehlermeldungen des SystemManagers

Sie stehen im Admin-Portal oben unter *Settings* und im Log:

| Fehler | Bedeutung | Lösung |
|---|---|---|
| **−4** wrong credentials | E-Mail oder Passwort des FRN-Kontos falsch | Settings → SystemManager |
| **−5** not accessible | Der SystemManager erreicht den Server nicht | `server_addr` richtig? Portweiterleitung TCP 10024? Firewall? Test von außen: `nc -vz frn.example.org 10024` |
| **−6** version too old | FRN_Server.jar zu alt | Settings → Check for update |
| **−7** access denied | Zugang verweigert | beim Betreiber von freeradionetwork.de nachfragen |
| **−8** address occupied | Adresse und Port nutzt schon ein anderer Server | anderen Port wählen |
| **−9** same credentials online | Dieses FRN-Konto ist schon mit einem anderen Server online | anderen Server abmelden |

## Weitere Probleme

| Problem | Ursache / Lösung |
|---|---|
| **FRN server** mit rotem Punkt in der Statusleiste | Dienst gestoppt oder Fehler: Admin-Portal → Settings zeigt den Grund; Logs → *server.log* |
| Port belegt | `sudo ss -ltnp \| grep 10024` – läuft noch ein anderer FRN-Server? |
| Dashboard zeigt keine Stationen, obwohl Clients verbunden sind | `server_clients.log` fehlt? `sudo frnadn write-config` schreibt `log4j.xml` neu, danach FRN-Server neu starten |
| Änderungen wirken nicht | Der Java-Server liest `server.properties` nur beim Start: oben *Restart now* |
| Client meldet „wrong password“ | am SystemManager: Konto des Benutzers prüfen; stand-alone: *FRN accounts* |
| Dashboard zeigt „No superadmin yet“ | `sudo frnadn set-superadmin NAME` |
| Passwort vergessen | `sudo frnadn reset-password NAME` |
| Java fehlt nach Systemupdate | `sudo apt install default-jre-headless` |
| **Upgrade Dashboard now** ist grau oder meldet keine Updates | Dateirechte oder fehlender Git-Stand: einmal `cd /opt/adn-frn-server && sudo ./scripts/update.sh`, siehe [Updates](updates.md#wenn-etwas-nicht-klappt) |
| Update-Prüfung: „rate limit“ oder „not reachable“ | GitHub begrenzt anonyme Abfragen bzw. der Server erreicht github.com nicht – später prüfen, Netz und DNS testen |
| Link-Menü fehlt in der Kopfzeile | *Show the link menu* aus oder keine Links eingetragen: Admin → 🔗 Links |

## Sicherung

Alles Wichtige steckt in `/var/lib/frnadn`:

```bash
sudo sqlite3 /var/lib/frnadn/frnadn.db ".backup '/root/frnadn-$(date +%F).db'"
sudo tar czf /root/frnadn-acl-$(date +%F).tgz -C /var/lib/frnadn/frn acl
```

Zurückspielen: Dienste stoppen, Datei nach `/var/lib/frnadn/frnadn.db` kopieren, `chown frnadn:frnadn`, `sudo frnadn write-config`, Dienste starten.

## Testen ohne Funk

```bash
python3 tools/sim_clients.py --port 10024 --stations 10 --minutes 5   # simulierte Stationen (nur stand-alone!)
FRNADN_DATA=/tmp/demo python3 tools/seed_demo.py --days 60           # erfundene Statistik – nie auf einem echten Server
FRN_TEST_JAR=/opt/frn-server/FRN_Server.jar python3 -m pytest tests  # Tests, auch gegen den echten Java-Server
```

Zum Ausprobieren ohne systemd: `FRNADN_DATA=/tmp/test FRNADN_FRN_DIRECT=1 FRNADN_PORT=8080 python3 -m frnadn` – frn_adn startet den Java-Server dann selbst.
