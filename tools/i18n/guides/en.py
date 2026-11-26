UI = {
    'title': 'Step by step', 'contents': 'Contents', 'lang': 'Language', 'more': 'Detailed description (German)',
    'step': 'Step', 'back': 'Back to the overview', 'shots': 'The yellow numbers in the pictures belong to the numbers in the text.',
}
SHARED = {
    'lang': ('Choose the language', 'At the top right, **🌐 EN ▾** ① opens the language menu ② with nine languages. The choice applies at once and to all N8 interfaces on this server. On the first visit the language of the browser is used.'),
    'domains': ('Own domain with HTTPS', 'Under **🌐 Network, ports & domains → 🔒 Domains & HTTPS** ① enter a domain that points to the server by DNS, plus an e-mail address for Let’s Encrypt ②. The certificate is fetched and renewed automatically. Ports 80 and 443 must be reachable from the internet.'),
    'users': ('Add users', 'Under **👥 Users & access → Users** ① add further accounts and give them a role ②. Admins see IP addresses and change settings, users only see the dashboard. Under **Sessions** you end logins, the **Log** shows every change.'),
    'update': ('Update', 'Under **🖥️ System → ⬆️ Update** ① you see the installed version and whether GitHub has a newer one ②. **⬆️ Install update now** downloads it, then checks the web interface and restores the previous version automatically if something goes wrong. No password is needed for this.'),
    'backup': ('Back up', 'Under **🖥️ System → 💾 Backup** ① create an encrypted backup of all data ② and restore it when needed – also on a new server. Keep the backup password safe: without it the backup cannot be opened.'),
    'login': ('Log in', 'Click **🔐 Log in** at the top right. In the login window ① enter username and password; 👁 shows the password, “Stay logged in” saves the login next time. After five wrong attempts the name is locked for 15 minutes. Once logged in, avatar and name ▾ appear with account, admin area and log out.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'The ADN FRN Server is a FreeRadioNetwork server with dashboard, admin area, news portal and mail server. This guide takes you through the first steps.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Install', 'On a Debian or Ubuntu server as a user with sudo rights:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nThe installer sets up Java, the FRN server, the dashboard, the services and the permissions and asks for the superadmin. Afterwards the dashboard is at `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Set up the FRN server', 'In the admin area under **📡 Operation → ⚙️ Settings → 🛰️ FRN server** ① you find address, port and time limits of the FRN server ②. Under **🌐 SystemManager** choose whether the server is registered at the SystemManager or runs stand-alone. Restart the FRN server after saving.'),
            ('rooms', 'Create rooms', 'Under **🏠 Rooms** ① create the rooms (nets) ②: name, emoji, owners, who may transmit and the parrot echo test. Set the order on the dashboard with ▲ ▼. The FRN server takes over changes after a restart.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink connects FRN, DMR and Zello into one common radio network. This guide takes you through the first steps.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Install', 'On a Debian or Ubuntu computer (also Raspberry Pi) with sudo rights:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nThe installer sets up program, service, vocoder and permissions under `/opt/n8crosslink`. Afterwards the interface is at `http://<computer>:8080`.'),
            ('setup', 'Create the superadmin', 'On the first visit **Create superadmin** ① appears: username and a password of at least 8 characters, then repeat it. This account may do everything, including restoring backups. Later you log in in the same window.'),
            ('lang', None, None),
            ('frn', 'Connect FRN', 'In the admin area under **📡 Operation → 📻 FRN** ① enter server, port, e-mail and FRN password ②. Choose the **room** from the list that is read directly from the FRN server. No FRN password yet? It can be requested from the SystemManager here.'),
            ('dmr', 'Connect DMR', 'Under **📡 DMR** ① you find DMR server, peer ID, password and talkgroups ②. With HBlink4-FreeRadioID the password is your personal FreeRadioID password – with the server passphrase the bridge is only a guest and may not transmit on all talkgroups.'),
            ('routes', 'Set the routing', 'Under **🔀 Routing** ① decide which source goes into which network ②, e.g. FRN → DMR and DMR → FRN. A lock time after transmitting prevents ping-pong between the networks. Changes apply at once.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Back up and start over', 'Under **🖥️ System → 💾 Backup & start over** ① create an encrypted backup ② – the key is the superadmin password at the time of the backup. Statistics or all settings can also be reset here.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'The N8 Hotspot is a web interface for MMDVMHost and DMRGateway on a Raspberry Pi with a modem hat. This guide takes you through the first steps.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Install', 'The easiest way is the ready-made DietPi image: write it to an SD card, put it into the Raspberry Pi, power on. Alternatively on a running DietPi:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nAfterwards the interface is at `http://n8-hotspot.local` (or the IP address).'),
            ('login', 'Log in', 'Click **🔐 Log in** at the top right and log in in the login window ① with the factory login **n8schicht / n8schicht**. 👁 shows the password, “Stay logged in” saves the login next time.'),
            ('password', 'Set your own password', 'As long as the factory login is active, **🔑 My account** ① opens and no settings can be changed. Choose your own username and a password of at least 8 characters – afterwards the factory login no longer works.'),
            ('lang', None, None),
            ('station', 'Enter the station', 'In the admin area under **📡 Operation → ⚙️ Settings → 📻 Station** ① enter callsign, DMR ID and location ②. Two digits as hotspot suffix make the hotspot ID unique if you have several devices.'),
            ('modem', 'Set up the modem', 'Under **📡 Modem** ① choose the modem board ② – this fills in port, speed and simplex/duplex. **Find the modem** finds the port by itself. Then enter transmit and receive frequency; for simplex both are the same.'),
            ('network', 'Connect to the DMR server', 'Under **🛰️ DMR network** ① choose the server from the list ② (fills in name, address and port) and enter the password – at the N8schicht your FreeRadioID.net password for full access.'),
            ('cal', 'Calibrate the frequency', 'Under **🎛️ Calibration** ① you find the frequency offset of your modem ②: start, transmit with your radio on the simplex frequency shown and move the frequency until the BER is lowest (ideally below 1 %). Then save the offset.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID is a DMR server with FreeRadioID login, dashboard, OpenBridge and APRS. This guide takes you through the first steps.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Install', 'On a Debian or Ubuntu server with sudo rights:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nThe setup asks for server name, ports, superadmin and FreeRadioID login and sets up the services. Afterwards the dashboard is at `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'Set up the DMR server', 'In the admin area under **📡 Operation → 🛰️ DMR server** ① you find port (default 62031), timings and links to other servers ②. Repeaters and hotspots connect to this port; changes apply after a restart of the DMR server.'),
            ('access', 'Access and FreeRadioID', 'Under **⚙️ Settings** ① decide who sees the dashboard and set the access for repeaters and hotspots ②: passphrase, talkgroups and the **FreeRadioID login**. With FreeRadioID every station logs in with its personal password; the passphrase becomes the guest access with its own talkgroups.'),
            ('aprs', 'Switch on APRS', 'Under **📡 APRS** ① switch on the APRS server with map ②: server ID (your callsign with SSID), open ports for APRS apps and iGates and the uplink to APRS-IS. GPS positions from the DMR traffic then appear on the map.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
