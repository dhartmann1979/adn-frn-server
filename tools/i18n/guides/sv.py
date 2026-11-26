UI = {
    'title': 'Steg för steg', 'contents': 'Innehåll', 'lang': 'Språk', 'more': 'Utförlig beskrivning (tyska)',
    'step': 'Steg', 'back': 'Tillbaka till översikten', 'shots': 'De gula siffrorna i bilderna hör till siffrorna i texten.',
}
SHARED = {
    'lang': ('Välj språk', 'Uppe till höger öppnar **🌐 SV ▾** ① språkmenyn ② med nio språk. Valet gäller direkt och för alla N8-gränssnitt på denna server. Vid första besöket används webbläsarens språk.'),
    'domains': ('Egen domän med HTTPS', 'Under **🌐 Nätverk, portar och domäner → 🔒 Domäner och HTTPS** ① anger du en domän som pekar på servern via DNS, samt en e-postadress för Let’s Encrypt ②. Certifikatet hämtas och förnyas automatiskt. Portarna 80 och 443 måste kunna nås från internet.'),
    'users': ('Lägg till användare', 'Under **👥 Användare och åtkomst → Användare** ① lägger du till fler konton och ger dem en roll ②. Administratörer ser IP-adresser och ändrar inställningar, användare ser bara instrumentpanelen. Under **Sessioner** avslutar du inloggningar, **Loggen** visar varje ändring.'),
    'update': ('Uppdatera', 'Under **🖥️ System → ⬆️ Uppdatering** ① ser du den installerade versionen och om GitHub har en nyare ②. **⬆️ Installera uppdateringen nu** laddar ner den, kontrollerar sedan webbgränssnittet och återställer automatiskt den tidigare versionen om något går fel. Inget lösenord behövs för detta.'),
    'backup': ('Säkerhetskopiera', 'Under **🖥️ System → 💾 Säkerhetskopia** ① skapar du en krypterad säkerhetskopia av all data ② och återställer den vid behov – även på en ny server. Förvara säkerhetskopians lösenord väl: utan det kan den inte öppnas.'),
    'login': ('Logga in', 'Klicka på **🔐 Logga in** uppe till höger. Ange användarnamn och lösenord i inloggningsfönstret ①; 👁 visar lösenordet, ”Förbli inloggad” sparar inloggningen nästa gång. Efter fem felaktiga försök spärras namnet i 15 minuter. Inloggad visas avatar och namn ▾ med konto, adminområde och utloggning.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'ADN FRN Server är en FreeRadioNetwork-server med instrumentpanel, adminområde, nyhetsportal och e-postserver. Denna guide tar dig genom de första stegen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installera', 'På en Debian- eller Ubuntu-server som användare med sudo-rättigheter:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nInstallationsprogrammet sätter upp Java, FRN-servern, instrumentpanelen, tjänsterna och behörigheterna och frågar efter superadmin. Därefter nås instrumentpanelen på `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Konfigurera FRN-servern', 'I adminområdet under **📡 Drift → ⚙️ Inställningar → 🛰️ FRN-server** ① finns FRN-serverns adress, port och tidsgränser ②. Under **🌐 SystemManager** väljer du om servern är registrerad hos SystemManager eller körs fristående. Starta om FRN-servern efter att du sparat.'),
            ('rooms', 'Skapa rum', 'Under **🏠 Rum** ① skapar du rummen (nät) ②: namn, emoji, ägare, vem som får sända och papegojans ekotest. Ordningen i instrumentpanelen ställer du in med ▲ ▼. FRN-servern tar över ändringarna efter en omstart.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink förbinder FRN, DMR och Zello till ett gemensamt radionät. Denna guide tar dig genom de första stegen.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Installera', 'På en Debian- eller Ubuntu-dator (även Raspberry Pi) med sudo-rättigheter:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nInstallationsprogrammet sätter upp program, tjänst, vocoder och behörigheter under `/opt/n8crosslink`. Därefter nås gränssnittet på `http://<dator>:8080`.'),
            ('setup', 'Skapa superadmin', 'Vid första besöket visas **Skapa superadmin** ①: användarnamn och ett lösenord på minst 8 tecken, sedan upprepa det. Detta konto får göra allt, även återställa säkerhetskopior. Senare loggar du in i samma fönster.'),
            ('lang', None, None),
            ('frn', 'Anslut FRN', 'I adminområdet under **📡 Drift → 📻 FRN** ① anger du server, port, e-post och FRN-lösenord ②. **Rummet** väljer du i listan som läses direkt från FRN-servern. Inget FRN-lösenord än? Det kan begäras hos SystemManager här.'),
            ('dmr', 'Anslut DMR', 'Under **📡 DMR** ① finns DMR-server, peer-ID, lösenord och talkgroups ②. Med HBlink4-FreeRadioID är lösenordet ditt personliga FreeRadioID-lösenord – med serverns lösenfras är bryggan bara gäst och får inte sända på alla talkgroups.'),
            ('routes', 'Ställ in routningen', 'Under **🔀 Routning** ① bestämmer du vilken källa som går till vilket nätverk ②, t.ex. FRN → DMR och DMR → FRN. En spärrtid efter sändning förhindrar pingpong mellan nätverken. Ändringar gäller direkt.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Säkerhetskopiera och börja om', 'Under **🖥️ System → 💾 Säkerhetskopiera och börja om** ① skapar du en krypterad säkerhetskopia ② – nyckeln är superadmin-lösenordet vid tidpunkten för säkerhetskopian. Här kan även statistik eller alla inställningar återställas.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'N8 Hotspot är ett webbgränssnitt för MMDVMHost och DMRGateway på en Raspberry Pi med modemkort. Denna guide tar dig genom de första stegen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installera', 'Enklast är den färdiga DietPi-avbilden: skriv den till ett SD-kort, sätt in det i Raspberry Pi, starta. Alternativt på en körande DietPi:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nDärefter nås gränssnittet på `http://n8-hotspot.local` (eller IP-adressen).'),
            ('login', 'Logga in', 'Klicka på **🔐 Logga in** uppe till höger och logga in i inloggningsfönstret ① med fabriksinloggningen **n8schicht / n8schicht**. 👁 visar lösenordet, ”Förbli inloggad” sparar inloggningen nästa gång.'),
            ('password', 'Sätt ett eget lösenord', 'Så länge fabriksinloggningen gäller öppnas **🔑 Mitt konto** ① och inga inställningar kan ändras. Välj ett eget användarnamn och ett lösenord på minst 8 tecken – därefter fungerar fabriksinloggningen inte längre.'),
            ('lang', None, None),
            ('station', 'Ange stationen', 'I adminområdet under **📡 Drift → ⚙️ Inställningar → 📻 Station** ① anger du anropssignal, DMR-ID och plats ②. Två siffror som hotspot-suffix gör hotspot-ID:t unikt om du har flera enheter.'),
            ('modem', 'Ställ in modemet', 'Under **📡 Modem** ① väljer du modemkortet ② – det fyller i port, hastighet och simplex/duplex. **Hitta modemet** hittar porten själv. Ange sedan sänd- och mottagningsfrekvens; vid simplex är de lika.'),
            ('network', 'Anslut till DMR-servern', 'Under **🛰️ DMR-nätverk** ① väljer du servern i listan ② (fyller i namn, adress och port) och anger lösenordet – hos N8schicht ditt FreeRadioID.net-lösenord för full åtkomst.'),
            ('cal', 'Kalibrera frekvensen', 'Under **🎛️ Kalibrering** ① hittar du modemets frekvensoffset ②: starta, sänd med din radio på den visade simplexfrekvensen och flytta frekvensen tills BER är lägst (helst under 1 %). Spara sedan offseten.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID är en DMR-server med FreeRadioID-inloggning, instrumentpanel, OpenBridge och APRS. Denna guide tar dig genom de första stegen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installera', 'På en Debian- eller Ubuntu-server med sudo-rättigheter:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nSetup frågar efter servernamn, portar, superadmin och FreeRadioID-inloggning och sätter upp tjänsterna. Därefter nås instrumentpanelen på `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'Ställ in DMR-servern', 'I adminområdet under **📡 Drift → 🛰️ DMR-server** ① finns port (standard 62031), tider och länkar till andra servrar ②. Repeatrar och hotspots ansluter till denna port; ändringar gäller efter en omstart av DMR-servern.'),
            ('access', 'Åtkomst och FreeRadioID', 'Under **⚙️ Inställningar** ① bestämmer du vem som ser instrumentpanelen och åtkomsten för repeatrar och hotspots ②: lösenfras, talkgroups och **FreeRadioID-inloggningen**. Med FreeRadioID loggar varje station in med sitt personliga lösenord; lösenfrasen blir gäståtkomsten med egna talkgroups.'),
            ('aprs', 'Slå på APRS', 'Under **📡 APRS** ① slår du på APRS-servern med karta ②: server-ID (din anropssignal med SSID), öppna portar för APRS-appar och iGates samt uplinken till APRS-IS. GPS-positioner från DMR-trafiken visas då på kartan.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
