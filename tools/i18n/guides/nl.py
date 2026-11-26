UI = {
    'title': 'Stap voor stap', 'contents': 'Inhoud', 'lang': 'Taal', 'more': 'Uitgebreide beschrijving (Duits)',
    'step': 'Stap', 'back': 'Terug naar het overzicht', 'shots': 'De gele cijfers in de afbeeldingen horen bij de cijfers in de tekst.',
}
SHARED = {
    'lang': ('Taal kiezen', 'Rechtsboven opent **🌐 NL ▾** ① het taalmenu ② met negen talen. De keuze geldt direct en voor alle N8-interfaces op deze server. Bij het eerste bezoek wordt de taal van de browser gebruikt.'),
    'domains': ('Eigen domein met HTTPS', 'Onder **🌐 Netwerk, poorten en domeinen → 🔒 Domeinen en HTTPS** ① voert u een domein in dat via DNS naar de server wijst, plus een e-mailadres voor Let’s Encrypt ②. Het certificaat wordt automatisch opgehaald en vernieuwd. Poorten 80 en 443 moeten vanaf internet bereikbaar zijn.'),
    'users': ('Gebruikers toevoegen', 'Onder **👥 Gebruikers en toegang → Gebruikers** ① voegt u meer accounts toe en geeft u ze een rol ②. Admins zien IP-adressen en wijzigen instellingen, gebruikers zien alleen het dashboard. Onder **Sessies** beëindigt u aanmeldingen, het **Logboek** toont elke wijziging.'),
    'update': ('Bijwerken', 'Onder **🖥️ Systeem → ⬆️ Update** ① ziet u de geïnstalleerde versie en of GitHub een nieuwere heeft ②. **⬆️ Update nu installeren** downloadt hem, controleert daarna de webinterface en zet bij een fout automatisch de vorige versie terug. Hiervoor is geen wachtwoord nodig.'),
    'backup': ('Back-up maken', 'Onder **🖥️ Systeem → 💾 Back-up** ① maakt u een versleutelde back-up van alle gegevens ② en zet u die indien nodig terug – ook op een nieuwe server. Bewaar het wachtwoord van de back-up goed: zonder kan hij niet worden geopend.'),
    'login': ('Aanmelden', 'Klik rechtsboven op **🔐 Aanmelden**. Voer in het aanmeldvenster ① gebruikersnaam en wachtwoord in; 👁 toont het wachtwoord, „Aangemeld blijven” bespaart de volgende keer het aanmelden. Na vijf verkeerde pogingen wordt de naam 15 minuten geblokkeerd. Aangemeld verschijnen avatar en naam ▾ met account, beheergedeelte en afmelden.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'De ADN FRN Server is een FreeRadioNetwork-server met dashboard, beheergedeelte, nieuwsportaal en mailserver. Deze handleiding leidt u door de eerste stappen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installeren', 'Op een Debian- of Ubuntu-server als gebruiker met sudo-rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nHet installatieprogramma richt Java, de FRN-server, het dashboard, de diensten en de rechten in en vraagt naar de superadmin. Daarna is het dashboard bereikbaar op `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'De FRN-server instellen', 'In het beheergedeelte onder **📡 Bedrijf → ⚙️ Instellingen → 🛰️ FRN-server** ① staan adres, poort en tijdslimieten van de FRN-server ②. Onder **🌐 SystemManager** kiest u of de server bij de SystemManager is geregistreerd of zelfstandig draait. Herstart na het opslaan de FRN-server.'),
            ('rooms', 'Kamers aanmaken', 'Onder **🏠 Kamers** ① maakt u de kamers (nets) aan ②: naam, emoji, eigenaren, wie mag zenden en de papegaai-echotest. De volgorde op het dashboard stelt u in met ▲ ▼. De FRN-server neemt wijzigingen over na een herstart.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink verbindt FRN, DMR en Zello tot één gemeenschappelijk radionetwerk. Deze handleiding leidt u door de eerste stappen.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Installeren', 'Op een Debian- of Ubuntu-computer (ook Raspberry Pi) met sudo-rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nHet installatieprogramma richt programma, dienst, vocoder en rechten in onder `/opt/n8crosslink`. Daarna is de interface bereikbaar op `http://<computer>:8080`.'),
            ('setup', 'Superadmin aanmaken', 'Bij het eerste bezoek verschijnt **Superadmin aanmaken** ①: gebruikersnaam en een wachtwoord van minstens 8 tekens, daarna herhalen. Dit account mag alles, ook back-ups herstellen. Later meldt u zich in hetzelfde venster aan.'),
            ('lang', None, None),
            ('frn', 'FRN verbinden', 'In het beheergedeelte onder **📡 Bedrijf → 📻 FRN** ① voert u server, poort, e-mail en FRN-wachtwoord in ②. De **kamer** kiest u uit de lijst die direct van de FRN-server wordt gelezen. Nog geen FRN-wachtwoord? Dat kunt u hier bij de SystemManager aanvragen.'),
            ('dmr', 'DMR verbinden', 'Onder **📡 DMR** ① staan DMR-server, peer-ID, wachtwoord en talkgroups ②. Bij HBlink4-FreeRadioID is het wachtwoord uw persoonlijke FreeRadioID-wachtwoord – met de passphrase van de server is de brug alleen gast en mag hij niet op alle talkgroups zenden.'),
            ('routes', 'De routering vastleggen', 'Onder **🔀 Routering** ① legt u vast welke bron naar welk netwerk gaat ②, bv. FRN → DMR en DMR → FRN. Een vergrendeltijd na het zenden voorkomt pingpong tussen de netwerken. Wijzigingen werken direct.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Back-up en opnieuw beginnen', 'Onder **🖥️ Systeem → 💾 Back-up en opnieuw beginnen** ① maakt u een versleutelde back-up ② – de sleutel is het superadmin-wachtwoord op het moment van de back-up. Hier kunt u ook statistieken of alle instellingen terugzetten.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'De N8 Hotspot is een webinterface voor MMDVMHost en DMRGateway op een Raspberry Pi met modem-hat. Deze handleiding leidt u door de eerste stappen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installeren', 'Het eenvoudigst is de kant-en-klare DietPi-image: op een SD-kaart schrijven, in de Raspberry Pi steken, opstarten. Of op een draaiende DietPi:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nDaarna is de interface bereikbaar op `http://n8-hotspot.local` (of het IP-adres).'),
            ('login', 'Aanmelden', 'Klik rechtsboven op **🔐 Aanmelden** en meld u in het aanmeldvenster ① aan met de fabrieksaanmelding **n8schicht / n8schicht**. 👁 toont het wachtwoord, „Aangemeld blijven” bespaart de volgende keer het aanmelden.'),
            ('password', 'Eigen wachtwoord instellen', 'Zolang de fabrieksaanmelding geldt, opent **🔑 Mijn account** ① en kunnen geen instellingen worden gewijzigd. Kies een eigen gebruikersnaam en een wachtwoord van minstens 8 tekens – daarna werkt de fabrieksaanmelding niet meer.'),
            ('lang', None, None),
            ('station', 'Het station invoeren', 'In het beheergedeelte onder **📡 Bedrijf → ⚙️ Instellingen → 📻 Station** ① voert u roepnaam, DMR-ID en locatie in ②. Twee cijfers als hotspot-achtervoegsel maken de hotspot-ID uniek als u meerdere apparaten hebt.'),
            ('modem', 'Het modem instellen', 'Onder **📡 Modem** ① kiest u het modemboard ② – dat vult poort, snelheid en simplex/duplex in. **Het modem zoeken** vindt de poort zelf. Voer daarna zend- en ontvangstfrequentie in; bij simplex zijn beide gelijk.'),
            ('network', 'Verbinden met de DMR-server', 'Onder **🛰️ DMR-netwerk** ① kiest u de server uit de lijst ② (vult naam, adres en poort in) en voert u het wachtwoord in – bij de N8schicht uw FreeRadioID.net-wachtwoord voor volledige toegang.'),
            ('cal', 'De frequentie kalibreren', 'Onder **🎛️ Kalibratie** ① vindt u de frequentie-offset van uw modem ②: starten, met uw portofoon op de getoonde simplexfrequentie zenden en de frequentie verschuiven tot de BER het laagst is (bij voorkeur onder 1 %). Sla daarna de offset op.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID is een DMR-server met FreeRadioID-aanmelding, dashboard, OpenBridge en APRS. Deze handleiding leidt u door de eerste stappen.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installeren', 'Op een Debian- of Ubuntu-server met sudo-rechten:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nDe setup vraagt naar servernaam, poorten, superadmin en FreeRadioID-aanmelding en richt de diensten in. Daarna is het dashboard bereikbaar op `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'De DMR-server instellen', 'In het beheergedeelte onder **📡 Bedrijf → 🛰️ DMR-server** ① staan poort (standaard 62031), timing en links naar andere servers ②. Repeaters en hotspots verbinden met deze poort; wijzigingen werken na een herstart van de DMR-server.'),
            ('access', 'Toegang en FreeRadioID', 'Onder **⚙️ Instellingen** ① legt u vast wie het dashboard ziet en de toegang voor repeaters en hotspots ②: passphrase, talkgroups en de **FreeRadioID-aanmelding**. Met FreeRadioID meldt elk station zich aan met zijn persoonlijke wachtwoord; de passphrase wordt de gasttoegang met eigen talkgroups.'),
            ('aprs', 'APRS inschakelen', 'Onder **📡 APRS** ① schakelt u de APRS-server met kaart in ②: server-ID (uw roepnaam met SSID), open poorten voor APRS-apps en iGates en de uplink naar APRS-IS. GPS-posities uit het DMR-verkeer verschijnen dan op de kaart.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
