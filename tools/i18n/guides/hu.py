UI = {
    'title': 'Lépésről lépésre', 'contents': 'Tartalom', 'lang': 'Nyelv', 'more': 'Részletes leírás (német)',
    'step': 'Lépés', 'back': 'Vissza az áttekintéshez', 'shots': 'A képeken lévő sárga számok a szövegben szereplő számokhoz tartoznak.',
}
SHARED = {
    'lang': ('Nyelv kiválasztása', 'Jobbra fent a **🌐 HU ▾** ① megnyitja a nyelvi menüt ② kilenc nyelvvel. A választás azonnal érvényes, és a szerver összes N8-felületére vonatkozik. Az első látogatáskor a böngésző nyelve érvényes.'),
    'domains': ('Saját domain HTTPS-sel', 'A **🌐 Hálózat, portok és domainek → 🔒 Domainek és HTTPS** alatt ① adjon meg egy domaint, amely DNS-sel a szerverre mutat, valamint egy e-mail-címet a Let’s Encrypt számára ②. A tanúsítvány beszerzése és megújítása automatikus. A 80-as és 443-as portnak elérhetőnek kell lennie az internetről.'),
    'users': ('Felhasználók hozzáadása', 'A **👥 Felhasználók és hozzáférés → Felhasználók** alatt ① további fiókokat hozhat létre, és szerepkört adhat nekik ②. Az adminok látják az IP-címeket és módosítják a beállításokat, a felhasználók csak a vezérlőpultot látják. A **Munkamenetek** alatt bejelentkezéseket fejezhet be, a **Napló** minden változást mutat.'),
    'update': ('Frissítés', 'A **🖥️ Rendszer → ⬆️ Frissítés** alatt ① látja a telepített verziót, és hogy van-e újabb a GitHubon ②. A **⬆️ Frissítés telepítése most** letölti, majd ellenőrzi a webes felületet, és hiba esetén automatikusan visszaállítja az előző verziót. Ehhez nem kell jelszó.'),
    'backup': ('Biztonsági mentés', 'A **🖥️ Rendszer → 💾 Biztonsági mentés** alatt ① titkosított mentést készíthet minden adatról ②, és szükség esetén visszaállíthatja – új szerveren is. Őrizze meg jól a mentés jelszavát: nélküle a mentés nem nyitható meg.'),
    'login': ('Bejelentkezés', 'Kattintson jobbra fent a **🔐 Bejelentkezés** gombra. A bejelentkezési ablakban ① adja meg a felhasználónevet és a jelszót; a 👁 megmutatja a jelszót, a „Bejelentkezve maradok” megspórolja a következő bejelentkezést. Öt hibás próbálkozás után a név 15 percre zárolódik. Bejelentkezve megjelenik az avatar és a név ▾ a fiókkal, az admin területtel és a kijelentkezéssel.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'Az ADN FRN Server egy FreeRadioNetwork-szerver vezérlőpulttal, admin területtel, hírportállal és levelezőszerverrel. Ez az útmutató végigvezet az első lépéseken.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Telepítés', 'Debian vagy Ubuntu szerveren, sudo-jogosultságú felhasználóként:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nA telepítő beállítja a Javát, az FRN-szervert, a vezérlőpultot, a szolgáltatásokat és a jogosultságokat, majd bekéri a superadmint. Utána a vezérlőpult itt érhető el: `http://<szerver>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Az FRN-szerver beállítása', 'Az admin területen az **📡 Üzem → ⚙️ Beállítások → 🛰️ FRN-szerver** alatt ① található az FRN-szerver címe, portja és időkorlátai ②. A **🌐 SystemManager** alatt választhatja ki, hogy a szerver regisztrálva legyen a SystemManagernél, vagy önállóan fusson. Mentés után indítsa újra az FRN-szervert.'),
            ('rooms', 'Szobák létrehozása', 'A **🏠 Szobák** alatt ① hozza létre a szobákat (neteket) ②: név, emoji, tulajdonosok, ki adhat, és a papagáj visszhangteszt. A sorrendet a vezérlőpulton a ▲ ▼ gombokkal állíthatja be. Az FRN-szerver újraindítás után veszi át a módosításokat.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'Az N8 Crosslink az FRN-t, a DMR-t és a Zellót egy közös rádióhálózattá köti össze. Ez az útmutató végigvezet az első lépéseken.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Telepítés', 'Debian vagy Ubuntu gépen (Raspberry Pi-n is) sudo-jogosultsággal:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nA telepítő a `/opt/n8crosslink` alá telepíti a programot, a szolgáltatást, a vokódert és a jogosultságokat. Utána a felület itt érhető el: `http://<gép>:8080`.'),
            ('setup', 'Superadmin létrehozása', 'Az első megnyitáskor megjelenik a **Superadmin létrehozása** ①: felhasználónév és legalább 8 karakteres jelszó, majd annak megismétlése. Ez a fiók mindent megtehet, a mentések visszaállítását is. Később ugyanebben az ablakban jelentkezik be.'),
            ('lang', None, None),
            ('frn', 'FRN csatlakoztatása', 'Az admin területen az **📡 Üzem → 📻 FRN** alatt ① adja meg a szervert, a portot, az e-mail-címet és az FRN-jelszót ②. A **szobát** a közvetlenül az FRN-szerverről beolvasott listából választhatja ki. Még nincs FRN-jelszava? Itt igényelhet a SystemManagertől.'),
            ('dmr', 'DMR csatlakoztatása', 'A **📡 DMR** alatt ① található a DMR-szerver, a peer ID, a jelszó és a talkgroupok ②. HBlink4-FreeRadioID esetén a jelszó az Ön személyes FreeRadioID-jelszava – a szerver passphrase-ével a híd csak vendég, és nem adhat minden talkgroupon.'),
            ('routes', 'Útválasztás beállítása', 'Az **🔀 Útválasztás** alatt ① határozza meg, melyik forrás melyik hálózatba megy ②, pl. FRN → DMR és DMR → FRN. Az adás utáni zárolási idő megakadályozza a pingpongot a hálózatok között. A módosítások azonnal érvényesek.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Mentés és újrakezdés', 'A **🖥️ Rendszer → 💾 Mentés és újrakezdés** alatt ① titkosított mentést készíthet ② – a kulcs a superadmin jelszava a mentés időpontjában. Itt a statisztika vagy az összes beállítás is visszaállítható.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'Az N8 Hotspot webes felület az MMDVMHosthoz és a DMRGatewayhez egy modem-hattal felszerelt Raspberry Pi-n. Ez az útmutató végigvezet az első lépéseken.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Telepítés', 'A legegyszerűbb a kész DietPi-képfájl: írja SD-kártyára, tegye a Raspberry Pi-be, kapcsolja be. Vagy egy futó DietPi-n:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nUtána a felület itt érhető el: `http://n8-hotspot.local` (vagy az IP-cím).'),
            ('login', 'Bejelentkezés', 'Kattintson jobbra fent a **🔐 Bejelentkezés** gombra, és a bejelentkezési ablakban ① lépjen be a gyári **n8schicht / n8schicht** adatokkal. A 👁 megmutatja a jelszót, a „Bejelentkezve maradok” megspórolja a következő bejelentkezést.'),
            ('password', 'Saját jelszó beállítása', 'Amíg a gyári bejelentkezés érvényes, a **🔑 Fiókom** ① nyílik meg, és semmilyen beállítás nem módosítható. Válasszon saját felhasználónevet és legalább 8 karakteres jelszót – ezután a gyári bejelentkezés nem működik.'),
            ('lang', None, None),
            ('station', 'Az állomás megadása', 'Az admin területen az **📡 Üzem → ⚙️ Beállítások → 📻 Állomás** alatt ① adja meg a hívójelet, a DMR ID-t és a helyszínt ②. Két számjegy hotspot-utótagként egyedivé teszi a hotspot ID-t, ha több eszköze van.'),
            ('modem', 'A modem beállítása', 'A **📡 Modem** alatt ① válassza ki a modempanelt ② – ez kitölti a portot, a sebességet és a simplex/duplex módot. A **Modem keresése** magától megtalálja a portot. Ezután adja meg az adási és vételi frekvenciát; simplexnél a kettő azonos.'),
            ('network', 'Csatlakozás a DMR-szerverhez', 'A **🛰️ DMR-hálózat** alatt ① válassza ki a szervert a listából ② (kitölti a nevet, a címet és a portot), és adja meg a jelszót – az N8schichtnél a FreeRadioID.net-jelszavát a teljes hozzáféréshez.'),
            ('cal', 'A frekvencia kalibrálása', 'A **🎛️ Kalibrálás** alatt ① megtalálja a modem frekvenciaeltolását ②: indítsa el, adjon a rádiójával a megjelenített simplex frekvencián, és tolja el a frekvenciát, amíg a BER a legalacsonyabb (ideálisan 1 % alatt). Ezután mentse az eltolást.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'A HBlink4-FreeRadioID egy DMR-szerver FreeRadioID-bejelentkezéssel, vezérlőpulttal, OpenBridge-dzsel és APRS-sel. Ez az útmutató végigvezet az első lépéseken.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Telepítés', 'Debian vagy Ubuntu szerveren sudo-jogosultsággal:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nA setup bekéri a szervernevet, a portokat, a superadmint és a FreeRadioID-bejelentkezést, majd beállítja a szolgáltatásokat. Utána a vezérlőpult itt érhető el: `http://<szerver>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'A DMR-szerver beállítása', 'Az admin területen az **📡 Üzem → 🛰️ DMR-szerver** alatt ① található a port (alapértelmezés 62031), az időzítések és a más szerverekhez vezető linkek ②. Az átjátszók és hotspotok erre a portra csatlakoznak; a módosítások a DMR-szerver újraindítása után érvényesek.'),
            ('access', 'Hozzáférés és FreeRadioID', 'A **⚙️ Beállítások** alatt ① határozza meg, ki látja a vezérlőpultot, valamint az átjátszók és hotspotok hozzáférését ②: passphrase, talkgroupok és a **FreeRadioID-bejelentkezés**. FreeRadioID esetén minden állomás a személyes jelszavával jelentkezik be; a passphrase a saját talkgroupokkal rendelkező vendéghozzáférés lesz.'),
            ('aprs', 'Az APRS bekapcsolása', 'Az **📡 APRS** alatt ① kapcsolja be az APRS-szervert térképpel ②: szerver ID (hívójele SSID-vel), nyitott portok APRS-appokhoz és iGate-ekhez, valamint az uplink az APRS-IS felé. A DMR-forgalom GPS-pozíciói ezután megjelennek a térképen.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
