# 🎙️ Dashboard

[← Übersicht](../../readme.md) · [Installation](installation.md) · **Dashboard** · [Admin-Portal](adminbereich.md) · [Konfiguration](konfiguration.md) · [Betrieb & Fehlersuche](betrieb.md) · [Updates](updates.md) · [Anleitungen](anleitungen.md)

Das Dashboard ist eine einzige Seite mit Tabs. Die Live-Daten liest frn_adn aus den beiden Logdateien des Java-FRN-Servers: `server_clients.log` – die vollständige Clientliste jedes Raums nach jeder Änderung, vom Autor des Servers genau dafür eingebaut – und `server.log` mit Logins, E-Mail, Client-Art, Sprechbeginn und -ende. Änderungen gehen per WebSocket sofort an alle Browser.

<p align="center"><img src="../images/live.png" alt="Live" width="90%"></p>

## Startseite wie beim DMR-Dashboard

Seit Version 2.3 ist die Live-Seite wie die Startseite von **DMR Die N8schicht** aufgebaut, ab 2.4 so, dass man am Desktop
praktisch nicht mehr scrollen muss:

1. **Kacheln** mit den Tageszahlen
2. **On air** über die ganze Breite – wer gerade spricht, pro Raum eine Karte; ist es still, eine schmale Zeile mit dem letzten Durchgang
3. **Last heard** (links) und **Rooms** (rechts) **nebeneinander und gleich hoch**. Beide füllen den Rest des Fensters und rollen
   in sich; die Höhe passt sich an, wenn On air wächst oder das Fenster sich ändert.

| Bereich | Inhalt |
|---|---|
| **Kacheln** | *Online now*, *Talks today*, *Airtime today*, *Stations heard*, *Peak online* mit Uhrzeit |
| **On air** | Avatar, Rufzeichen, Name, Ort, Band und laufende Zeit |
| **Last heard** | eine Zeile pro Durchgang: Zeit, Avatar, Rufzeichen mit Flagge, Raum, Dauer, Band; filterbar nach Raum. Am Desktop stehen alle letzten 20 Durchgänge in der Liste (sie rollt), bis 1400 px Breite ohne die Spalte *Band* |
| **Rooms** | Raum-Chips mit Stationszahl und ● ON AIR; geöffnet ist der Raum, in dem gesprochen wird, sonst der vollste |

**Comings & goings** (Logins und Logouts) steht seit 2.4 im Tab **📈 Statistics** ganz unten.

Unter 1100 px Breite (Tablet, Handy) ist alles einspaltig: Kacheln, On air, Räume, Last heard (5 bzw. 8 Einträge, **Show all**).

<p align="center"><img src="../images/rooms-avatars.png" alt="Raumliste mit Client-Avataren und Rollen" width="60%"></p>

**Avatar = Client-Software.** Jede Station zeigt als Bild, woher sie kommt: **DMR**, **Zello**, **SVX** (SvxLink), **EL** (EchoLink),
**ASL**, **YSF**, **D★**, **M17**, TeamSpeak/Mumble, Crosslink, Funk-Gateway (Antenne), PC/App (Monitor) oder der Parrot.
Erkannt wird das an Band, Beschreibung und Client-Art; der Admin kann jedes Bild durch ein eigenes ersetzen
([Admin → Theme → Client logos](adminbereich.md#-theme)).

**Rollen:** 👑 *Owner* und 🛡️ *Admin* des Raums stehen direkt **hinter dem Avatar und vor dem Rufzeichen**. Ein grüner Punkt hinter
dem Rufzeichen heißt: spricht gerade.

## Kopfzeile und Menü

Wie bei HBlink4-FreeRadioID liegt alles in **einer** Kopfzeile: links Logo, Titel und Untertitel, in der Mitte die **Reiter**, rechts Status, Links-Knopf und Anmeldung.

<p align="center"><img src="../images/header-desktop.png" alt="Kopfzeile am Desktop" width="95%"></p>

| Anzeige | Bedeutung |
|---|---|
| 🎙️ Live · 📈 Statistics · 📇 Stations · 💬 Chat · ⚙️ Admin | die Reiter; *Chat* und *Admin* nur mit Berechtigung |
| ✓ Live data | Verbindung des Browsers zum Dashboard steht |
| ✓ FRN server | Der Dienst `frn-server` läuft und lauscht auf seinem Port; ✕ mit Grund (gestoppt, SystemManager-Fehler) |
| 👥 n online | Stationen in allen sichtbaren Räumen (ohne Parrot) |
| 🔗 Links ▾ | das Link-Menü (siehe unten) |
| 🔐 Login / 👤 Name | Anmelden bzw. Benutzer-Menü (Admin-Portal, eigenes Konto, Abmelden) |

Wer gerade spricht, steht im Bereich **On air** der Live-Seite. Das Farbschema (7 Profile, darunter das helle *Daylight*, jede Farbe frei wählbar) stellt der Admin unter **Admin → Theme** ein.

Unten auf jeder Seite steht die **Fußzeile** mit © Die N8schicht, der installierten Version mit Commit und deren Datum.

### 🔗 Link-Menü

Das Menü zeigt die eigenen Links des Betreibers – für alle, auch ohne Login. Es gibt zwei Darstellungen:

Jeder Weblink kann sein Website-Site-Icon anzeigen. Das Dashboard cached die abgerufenen Icons in SQLite und zeigt andernfalls das konfigurierte Fallback-Emoji.

<p align="center"><img src="../images/links-menu.png" alt="Link-Menü" width="62%"> <img src="../images/links-bar.png" alt="Knopfreihe" width="95%"></p>

*Button with drop-down menu* öffnet die Liste unter dem Knopf (Esc oder Klick daneben schließt sie); *Row of buttons* zeigt alle Links als Reihe unter der Kopfzeile. Ein Link `#stations` wechselt zu diesem Reiter. Einrichten: [Anleitungen → Link-Menü](anleitungen.md#-link-menü-einrichten).

### Am Smartphone

Die Kopfzeile bleibt **eine Zeile**: Logo und Titel, *Live data* und *FRN server* als zwei Statuspunkte (grün = ok, rot = Problem),
die Zahl der Stationen sowie Links und Benutzer als Symbole. Die Reiter stehen darunter. Die Kacheln bilden ein 3+2-Raster,
alles Weitere ist einspaltig.

<p align="center"><img src="../images/header-mobile.png" alt="Kopfzeile am Smartphone" width="45%"> <img src="../images/live-mobile.png" alt="Live am Smartphone" width="30%"></p>

## Tab 🎙️ Live

Die Abschnitte lassen sich wie beim DMR-Dashboard mit **▾** zuklappen; der Browser merkt sich das.

- **Today** – Online jetzt, Durchgänge, Sprechzeit, gehörte Stationen und Spitzenwert heute.
- **On air** – pro Raum eine grüne Karte mit Client-Avatar, Rufzeichen, Name, Ort, Band und laufender Zeit; `max. 180 s` ist die maximale Sendezeit des Raums. Auch der Parrot erscheint hier, wenn er einen Durchgang abspielt.
- **Rooms** – jeder Raum mit seinen Stationen, Avatar = Client-Software (siehe oben), danach 👑/🛡️ und das Rufzeichen; rechts Band und Dauer; 🔇 stumm. Die Stationsliste sortiert Crosslinks zuerst, dann Admins/Owner, QRV, QRL und die übrigen Stationen. **PC Only steht immer am Ende.** 🔒 = auf dem Dashboard versteckt (nur nach Login).
- **Last heard** – die letzten Durchgänge mit Dauer laut FRN-Server, filterbar nach Raum (*All* oder ein Raum); neben den Räumen, gleich hoch.

Ein Klick auf eine Station öffnet ihre Detailansicht. Moderiert wird – wie bei FRN üblich – im FRN-Client als Owner oder Admin (Rechtsklick auf die Station); das Dashboard zeigt das Ergebnis sofort an.

## Tab 📈 Statistics

Zeitraum *Today, 24 h, 7/30/90 days, 1 year* und Maß *Airtime* oder *Talks*.

<p align="center"><img src="../images/stats-30d.png" alt="Statistik" width="90%"></p>

- **Top stations** und **Activity per room**
- **Stations online** – Maximum, alle 5 Minuten gemessen
- **When is talked** – Wochentag × Uhrzeit
- Tabellen **Rooms** und **Most active stations**
- **Comings & goings** – Logins und Logouts, live (die letzten 40)

<p align="center"><img src="../images/stats-feed.png" alt="Comings & goings im Statistik-Tab" width="90%"></p>

Für lange Zeiträume rechnet frn_adn mit Tagessummen und speichert Ergebnisse im Cache.

## Tab 📇 Stations

Alle gehörten Stationen mit Suche (Rufzeichen, Name, Ort, Land) und Filtern *Online now* und *Talked (30 d)*.

<p align="center"><img src="../images/stations.png" alt="Stationen" width="90%"></p>

## Tab 💬 Chat

Öffentliche Textnachrichten aus den Räumen. Wer den Chat sieht, stellt der Admin ein (Vorgabe: nur Admins). Private Nachrichten zwischen Stationen werden nicht gespeichert.

## Login

<p align="center"><img src="../images/login.png" alt="Login" width="40%"></p>

Ohne Anmeldung sieht man die öffentliche Ansicht – Räume, On air, Last heard und Statistik, aber keine E-Mail- oder IP-Adressen und keine versteckten Räume:

<p align="center"><img src="../images/live-public.png" alt="Öffentliche Ansicht ohne Login" width="90%"></p>

Ist die öffentliche Ansicht abgeschaltet, sehen nur angemeldete Benutzer das Dashboard. E-Mail- und IP-Adressen der Stationen sehen nur Admins.
