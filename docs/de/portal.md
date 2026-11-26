# 📰 Portal-Seite (News)

[← Übersicht](../../readme.md) · [Installation](installation.md) · [Dashboard](dashboard.md) · [Admin-Portal](adminbereich.md) · **Portal-Seite** · [Konfiguration](konfiguration.md) · [Betrieb & Fehlersuche](betrieb.md)

Seit **2.24.0** hat der ADN-FRN-Server eine öffentliche **Portal-Seite mit News** der Betreiber – unter `/portal` und auf Wunsch
unter einer **eigenen Domain mit Let's-Encrypt-Zertifikat** (z. B. `news.auf-der-nachtschicht.de`).

<p align="center"><img src="../images/portal.png" alt="Portal-Seite" width="95%"></p>

## Was Besucher sehen

- **Kopfzeile wie im Dashboard** (Logo, Titel mit [Master]/[Backup]/[Standalone], 📰 News · 🎙️ Live · 📈 Statistik, Links-Menü, DE | EN, Anmelden)
  und die schmale Statuszeile (FRN-Server, online, wer sendet).
- **Begrüßung** mit Titel, Untertitel, Begrüßungstext und zwei Kennzahlen (jetzt online, Durchgänge heute).
- **News als Karten** über die ganze Breite: angeheftete News oben über die volle Breite, die übrigen gleich breit nebeneinander.
  Jede Karte mit Kategorie (ℹ️ Info · ⚠️ Wichtig · 🛠️ Technik · 📅 Termin · 📻 Netz & Räume), Datum, Autor, Symbol, Titel und Anreißer.
  Oben lässt sich nach Kategorie filtern, unten lädt **Ältere News** nach.
- **Artikel-Seite** `/news/<Nummer>` mit dem ganzen Text.
- **Seitenkästen:** Zahlen von heute, Räume mit Stationen online (wer gerade sendet, blinkt magenta) und *Verbinden* (FRN-Server,
  Betreiber, Webseite). Räume und Zahlen nur, wenn das Dashboard öffentlich ist (oder man angemeldet ist); versteckte Räume nie.
- **RSS-Feed** `/portal/rss.xml` mit den letzten 30 veröffentlichten News.
- Auf dem Handy eine Spalte. Die Seite lädt alle 30 s neu.

<p align="center"><img src="../images/portal-artikel.png" alt="Artikel" width="62%"> <img src="../images/portal-mobile.png" alt="Portal auf dem Handy" width="26%"></p>

Im Dashboard steht der Menüpunkt **📰 News** vorne in der Kopfzeile, sobald die Portal-Seite an ist.

## Nur Admins sind Autoren

Neue Gruppe im Admin-Menü: **📰 Portal** mit **📝 News** und **⚙️ Portal-Seite**.

- **Nur Admins** (Rolle *Admin* oder *Superadmin*) schreiben, bearbeiten, veröffentlichen, zurückziehen und löschen News.
  Benutzer mit Rolle *User* und Besucher lesen nur – der Server lehnt alles andere ab (403).
- Jede Änderung steht im **📜 Protokoll** (*news_saved*, *news_published*, *news_unpublished*, *news_deleted*).
- **Entwürfe** sieht man nur im Admin-Portal. Veröffentlichen setzt das Datum; Zurückziehen nimmt die News von der Seite.

<p align="center"><img src="../images/admin-news.png" alt="Admin → Portal → News" width="95%"></p>

### Schreiben

**＋ Neue News** bzw. **✏️ Bearbeiten** öffnet den Editor: Symbol (Emoji), Titel, Kategorie, **🖼️ Themenbild** (seit 2.28: JPEG, PNG oder WebP, wird im Browser auf höchstens 1600 px verkleinert, mit Bildbeschreibung für Screenreader – oben auf der Karte, bei angehefteten News links daneben, im Artikel als breites Titelbild), Anreißer (kurz, steht auf der Karte), Text
und links daneben die **Vorschau**. *📌 Oben anheften* und *🚀 Veröffentlicht*; **💾 Als Entwurf speichern** oder
**🚀 Speichern & veröffentlichen**.

<p align="center"><img src="../images/admin-news-editor.png" alt="News-Editor mit Vorschau" width="90%"></p>

Formatierung im Text (auch im Begrüßungstext):

| Schreiben | ergibt |
|---|---|
| `**fett**` · `*kursiv*` · `` `Code` `` | **fett** · *kursiv* · `Code` |
| `[Text](https://…)` oder einfach `https://…` | Link (öffnet in neuem Tab) |
| `# Überschrift` · `## …` · `### …` | Zwischenüberschriften |
| `- Punkt` · `1. Punkt` | Listen |
| `> Zitat` · `---` | Hinweis-Kasten · Trennlinie |
| Leerzeile | neuer Absatz |

Alles andere wird **als Text** angezeigt: HTML oder Skripte eines Autors erreichen nie einen Besucher (der Text wird erst vollständig
maskiert, dann formatiert). Grenzen: Titel 140, Anreißer 400, Text 20 000 Zeichen.

## ⚙️ Portal-Seite

<p align="center"><img src="../images/admin-portal.png" alt="Admin → Portal → Portal-Seite" width="95%"></p>

| Einstellung | Standard | Wirkung |
|---|---|---|
| Portal-Seite an | an | aus = `/portal` leitet auf das Dashboard, die Portal-Domain zeigt das Dashboard |
| Titel des Portals | leer | leer = Titel des Dashboards |
| Untertitel | leer | steht über dem Titel und in der Kopfzeile |
| Begrüßungstext | leer | steht über den News, Formatierung wie oben |
| Räume und Stationen online zeigen | an | Seitenkasten *Räume* (nur bei öffentlichem Dashboard) |
| Zahlen von heute zeigen | an | Seitenkasten *Heute* und Kennzahlen oben |
| News je Seite | 8 | 3–30 |

Mit **Master & Backup** gehen News und diese Einstellungen beim stündlichen Abgleich mit zum Backup – nur die Portal-Domain bleibt je
Server eigen.

## 🌐 Domains: Live oder Portal

Seit **2.26.0** wählst du unter **🌐 Netz, Ports & Domains → 🔒 Domains & HTTPS** für **jede Domain und Subdomain**, was sie zeigt:

<p align="center"><img src="../images/admin-domains-zuordnung.png" alt="Domains & HTTPS – Spalte Zeigt" width="95%"></p>

- Spalte **„Zeigt“**: **🎙️ Live-Dashboard** oder **📰 Portal (News)** – umstellen wirkt **sofort, ohne Neustart**.
- **➕ Domain hinzufügen** fragt das Ziel gleich mit ab. Beliebig viele Domains, z. B. `frn.example.org` → Live,
  `news.example.org` und `www.example.org` → Portal.
- Alle Domains kommen auf **ein Let's-Encrypt-Zertifikat**; die erste ist der **🔒 Hauptname**. Beim Hinzufügen startet das Dashboard
  neu und erweitert das Zertifikat (DNS der neuen Domain muss auf diesen Server zeigen, Port 80 erreichbar). Der HTTP-Port leitet je
  Domain auf die richtige HTTPS-Adresse um.
- **Entfernen** einer Domain: das Portal bleibt unter `/portal` erreichbar, das Dashboard unter `/dashboard`. Wird der Hauptname
  entfernt, rückt die nächste Domain nach.
- Auf einer Portal-Domain führt **🎙️ Live** zur ersten Live-Domain; im Dashboard führt **📰 News** zur ersten Portal-Domain.
- Ist die Portal-Seite unter *📰 Portal → ⚙️ Portal-Seite* ausgeschaltet, zeigen auch Portal-Domains das Dashboard.

## Schnittstellen

| Pfad | Wer | Inhalt |
|---|---|---|
| `GET /portal`, `GET /news/<id>` | alle | Portal-Seite bzw. Artikel |
| `GET /api/portal?offset=&category=` | alle | Titel, Begrüßung, veröffentlichte News, ggf. Räume und Zahlen von heute |
| `GET /api/portal/news/<id>` | alle | eine veröffentlichte News |
| `GET /portal/rss.xml` | alle | RSS 2.0 |
| `GET /api/admin/portal` | Admins | Einstellungen und alle News (auch Entwürfe) |
| `POST /api/admin/news` · `POST /api/admin/news/<id>/publish` · `DELETE /api/admin/news/<id>` | Admins | schreiben, (de)veröffentlichen, löschen |
| `POST /api/admin/portal/settings` | Admins | Einstellungen `portal.*` (ohne Domain) |
