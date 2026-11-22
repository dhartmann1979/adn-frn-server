# 🧾 Konfiguration

[← Übersicht](../../readme.md) · [Installation](installation.md) · [Dashboard](dashboard.md) · [Admin-Portal](adminbereich.md) · **Konfiguration** · [Betrieb & Fehlersuche](betrieb.md)

## Was wo liegt

So viel wie möglich in SQLite, in Dateien nur, was der Java-FRN-Server lesen muss:

| Ort | Inhalt | wer schreibt |
|---|---|---|
| `/var/lib/frnadn/frnadn.db` | Einstellungen, Räume, ACL-Einträge, Theme und Site-Icon-Cache für Links, FRN-Konten, Benutzer, Sitzungen, Protokoll, Statistik | frn_adn |
| `/var/lib/frnadn/frn/server.properties` | Server und Räume für den Java-Server | frn_adn, aus der Datenbank |
| `/var/lib/frnadn/frn/log4j.xml` | Logging: `logs/server.log` und `logs/server_clients.log` | frn_adn |
| `/var/lib/frnadn/frn/acl/FRNPasswd.xml` | eigene Passwortliste (Stand-alone) | frn_adn |
| `/var/lib/frnadn/frn/acl/*List*.xml` | FRN-kompatible Kopie der Admin-, Stumm-, Sperr- und Zugangslisten | FRN-Server und frn_adn |
| `/var/lib/frnadn/branding/` | eigenes Dashboard-Logo und Site-Icon | frn_adn |
| `/opt/frn-server/FRN_Server.jar` | der FRN-Server von freeradionetwork.de | Installer / Update |
| `/etc/systemd/system/frn-server.service`, `frnadn.service` | Dienste | Installer |

`server.properties` niemals von Hand ändern – frn_adn überschreibt sie. Ansehen: Admin-Portal → Settings → *Show server.properties*. Auf der Kommandozeile:

```bash
sudo frnadn show-settings                     # alle Werte als JSON (ohne Passwörter)
sudo frnadn write-config                      # server.properties & Co. neu schreiben
sudo frnadn set-superadmin NAME · sudo frnadn reset-password NAME
sudo frnadn add-account E-MAIL RUFZEICHEN [NAME]
```

Die ACL-Dateien werden beim Dashboard-Start in SQLite übernommen. Änderungen aus dem FRN-Client bleiben möglich und werden vor dem nächsten Öffnen der ACL-Seite eingelesen. Bei einer Änderung im Admin-Portal wird die vorherige XML-Datei in `acl/backups/` gesichert.

## Server (server.properties)

| Admin-Portal | Parameter | Vorgabe | Bedeutung |
|---|---|---|---|
| Stand-alone | `standalone` | aus | ohne SystemManager betreiben |
| Allow a LAN address | `allowLANAddr` | aus | nur stand-alone: LAN-IP als Serveradresse |
| SystemManager | `sysman_server_addr` | sysman.freeradionetwork.de | |
| FRN account e-mail / password | `sysman_auth_emailaddr` / `_password` | – | das FRN-Konto, mit dem sich der Server anmeldet |
| Server address | `server_addr` | – | öffentlicher Hostname/IP – der SystemManager prüft die Erreichbarkeit |
| Port | `server_port` | 10024 | TCP-Port für die Clients |
| Owner e-mail | `server_owner` | = Konto-E-Mail | **eine** Adresse, OWNER in allen Räumen |
| Website | `website` | – | |
| Backup server / port | `backup_server_addr` / `_port` | – | wird den Clients als Ausweichserver mitgeteilt |
| Default room | `default_net` | erster Raum nach net00 | für Clients mit unbekanntem Raum |
| Client timeout | `client_sotimeout` | 8000 ms | |
| Voice timeout | `client_txtimeout` | 1000 ms | 0 = aus |
| No voice to muted … | `voip_skip_muted_crosslink_clients`, `…_gateway_…`, `…_pconly_…` | ja / ja / nein | |
| – | `xmlFilesDir` | `/var/lib/frnadn/frn/acl` | fest |

Die Bedeutung aller Parameter beschreibt das `properties_doc.pdf` von freeradionetwork.de (liegt nach der Installation in `/opt/frn-server`).

## Räume (net00 … net63)

| Admin-Portal | Parameter | Bedeutung |
|---|---|---|
| Name | `netNN` | Raumname; die Clients sehen die Räume alphabetisch |
| Room is open | `netNN_enable` | aus = Raum wird nicht angeboten |
| Room owners | `netNN_owner` | E-Mails mit **NETOWNER**-Rechten nur in diesem Raum |
| Info message | `netNN_show_infomessage` | `acl` = nur Clients, die von der Zugangsliste betroffen sind; `always` |
| Max. transmission | `netNN_tot` | Sekunden, Vorgabe 180 |
| Speech pause / message | `netNN_speechpause`, `_speechpause_msg` | Pause nach einem Durchgang (ms); Nachricht an PC-Clients, `{callsign}` wird ersetzt |
| Parrot, start/stop | `netNN_parrot_enable`, `_parrot_startstop_enable` | Echotest; net00 hat ihn immer |
| Unmute after | `netNN_unmute` | Stummschaltung endet nach N Minuten |
| Crosslinks / Gateways allowed | `netNN_acl_cl`, `_acl_gw` | leer = alle, `none` = keine, oder E-Mails |
| Message for refused … | `netNN_acl_info` | |
| Block pattern / message | `netNN_bl_regexp`, `_bl_info` | regulärer Ausdruck auf Name, E-Mail, Stadt |
| Telegram bot | `netNN_tgbot_params` | `min. Sendedauer ms;min. Pause ms;Bot-Token;Kanal-ID` |
| Hidden on the dashboard | – | nur Dashboard (SQLite) |

## Rechte im FRN-Client

| Stufe | Wer | Darf |
|---|---|---|
| OWNER | `server_owner` | alles in allen Räumen, auch Admins ernennen |
| NETOWNER | Room owners | alles im eigenen Raum |
| ADMIN | Admin-Liste des Raums | stummschalten, sperren, Zugangsliste, ENA/TXR |
| OK | alle anderen | sprechen und schreiben |

## SystemManager oder Stand-alone

| | am SystemManager | Stand-alone |
|---|---|---|
| Sichtbar im FRN-System | ja | nein, Clients tragen Server und Port selbst ein |
| Passwörter prüft | der SystemManager (FRN-Konten der Benutzer) | die eigene Liste (*FRN accounts*) oder niemand |
| Serveradresse | öffentlich erreichbar, keine LAN-IP | beliebig, LAN mit `allowLANAddr` |
| Voraussetzung | eigenes FRN-Konto (E-Mail, Passwort) | – |

## Dashboard (nur SQLite)

| Einstellung | Vorgabe |
|---|---|
| Title / Subtitle | Auf der NachtSchicht |
| Public view | an |
| Show hidden rooms publicly | aus |
| Room chat | Admins only (aus, Admins, angemeldete Benutzer, alle) |
| Login valid for | 12 h (mit „angemeldet bleiben“ 30 Tage) |
| Keep talks / logins / chat | 400 / 180 / 30 Tage; Tagessummen bleiben immer |
