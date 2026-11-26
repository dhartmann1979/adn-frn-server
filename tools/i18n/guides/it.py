UI = {
    'title': 'Passo dopo passo', 'contents': 'Indice', 'lang': 'Lingua', 'more': 'Descrizione dettagliata (tedesco)',
    'step': 'Passo', 'back': 'Torna alla panoramica', 'shots': 'I numeri gialli nelle immagini corrispondono ai numeri nel testo.',
}
SHARED = {
    'lang': ('Scegliere la lingua', 'In alto a destra **🌐 IT ▾** ① apre il menu delle lingue ② con nove lingue. La scelta vale subito e per tutte le interfacce N8 di questo server. Alla prima visita viene usata la lingua del browser.'),
    'domains': ('Dominio proprio con HTTPS', 'In **🌐 Rete, porte e domini → 🔒 Domini e HTTPS** ① inserisci un dominio che punta al server tramite DNS e un indirizzo e-mail per Let’s Encrypt ②. Il certificato viene ottenuto e rinnovato automaticamente. Le porte 80 e 443 devono essere raggiungibili da Internet.'),
    'users': ('Aggiungere utenti', 'In **👥 Utenti e accesso → Utenti** ① aggiungi altri account e assegni loro un ruolo ②. Gli admin vedono gli indirizzi IP e modificano le impostazioni, gli utenti vedono solo la dashboard. In **Sessioni** termini gli accessi, il **Registro** mostra ogni modifica.'),
    'update': ('Aggiornare', 'In **🖥️ Sistema → ⬆️ Aggiornamento** ① vedi la versione installata e se GitHub ne ha una più recente ②. **⬆️ Installa ora l’aggiornamento** la scarica, poi controlla l’interfaccia web e in caso di errore ripristina automaticamente la versione precedente. Non serve alcuna password.'),
    'backup': ('Eseguire il backup', 'In **🖥️ Sistema → 💾 Backup** ① crei un backup cifrato di tutti i dati ② e lo ripristini quando serve – anche su un nuovo server. Conserva bene la password del backup: senza di essa non si può aprire.'),
    'login': ('Accedere', 'Fai clic su **🔐 Accedi** in alto a destra. Nella finestra di accesso ① inserisci nome utente e password; 👁 mostra la password, «Resta connesso» evita l’accesso la volta successiva. Dopo cinque tentativi errati il nome viene bloccato per 15 minuti. Dopo l’accesso compaiono avatar e nome ▾ con account, area admin ed esci.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'ADN FRN Server è un server FreeRadioNetwork con dashboard, area admin, portale notizie e server di posta. Questa guida ti accompagna nei primi passi.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installare', 'Su un server Debian o Ubuntu come utente con diritti sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nL’installer configura Java, il server FRN, la dashboard, i servizi e i permessi e chiede il superadmin. Dopo la dashboard è raggiungibile su `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Configurare il server FRN', 'Nell’area admin, in **📡 Esercizio → ⚙️ Impostazioni → 🛰️ Server FRN** ①, trovi indirizzo, porta e timeout del server FRN ②. In **🌐 SystemManager** scegli se il server è registrato presso il SystemManager o funziona in modo autonomo. Dopo il salvataggio riavvia il server FRN.'),
            ('rooms', 'Creare le stanze', 'In **🏠 Stanze** ① crei le stanze (net) ②: nome, emoji, proprietari, chi può trasmettere e il test eco pappagallo. L’ordine nella dashboard si imposta con ▲ ▼. Il server FRN applica le modifiche dopo un riavvio.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink collega FRN, DMR e Zello in un’unica rete radio comune. Questa guida ti accompagna nei primi passi.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Installare', 'Su un computer Debian o Ubuntu (anche Raspberry Pi) con diritti sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nL’installer configura programma, servizio, vocoder e permessi in `/opt/n8crosslink`. Dopo l’interfaccia è raggiungibile su `http://<computer>:8080`.'),
            ('setup', 'Creare il superadmin', 'Alla prima apertura compare **Crea superadmin** ①: nome utente e una password di almeno 8 caratteri, poi ripetila. Questo account può fare tutto, anche ripristinare i backup. In seguito accedi nella stessa finestra.'),
            ('lang', None, None),
            ('frn', 'Collegare FRN', 'Nell’area admin, in **📡 Esercizio → 📻 FRN** ①, inserisci server, porta, e-mail e password FRN ②. La **stanza** si sceglie dalla lista letta direttamente dal server FRN. Ancora nessuna password FRN? Si può richiedere qui al SystemManager.'),
            ('dmr', 'Collegare DMR', 'In **📡 DMR** ① trovi server DMR, ID peer, password e talkgroup ②. Con HBlink4-FreeRadioID la password è la tua password FreeRadioID personale – con la passphrase del server il bridge è solo ospite e non può trasmettere su tutti i talkgroup.'),
            ('routes', 'Impostare l’instradamento', 'In **🔀 Instradamento** ① stabilisci quale sorgente va in quale rete ②, p. es. FRN → DMR e DMR → FRN. Un tempo di blocco dopo la trasmissione evita il ping-pong tra le reti. Le modifiche hanno effetto subito.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Backup e nuovo inizio', 'In **🖥️ Sistema → 💾 Backup e nuovo inizio** ① crei un backup cifrato ② – la chiave è la password del superadmin al momento del backup. Qui si possono anche reimpostare le statistiche o tutte le impostazioni.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'N8 Hotspot è un’interfaccia web per MMDVMHost e DMRGateway su un Raspberry Pi con scheda modem. Questa guida ti accompagna nei primi passi.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installare', 'La via più semplice è l’immagine DietPi pronta: scriverla su una scheda SD, inserirla nel Raspberry Pi, accendere. In alternativa su un DietPi già in funzione:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nDopo l’interfaccia è raggiungibile su `http://n8-hotspot.local` (o l’indirizzo IP).'),
            ('login', 'Accedere', 'Fai clic su **🔐 Accedi** in alto a destra e accedi nella finestra di accesso ① con l’accesso di fabbrica **n8schicht / n8schicht**. 👁 mostra la password, «Resta connesso» evita l’accesso la volta successiva.'),
            ('password', 'Impostare una password personale', 'Finché vale l’accesso di fabbrica, si apre **🔑 Il mio account** ① e non si possono modificare impostazioni. Scegli nome utente e password personali di almeno 8 caratteri – poi l’accesso di fabbrica non funziona più.'),
            ('lang', None, None),
            ('station', 'Inserire la stazione', 'Nell’area admin, in **📡 Esercizio → ⚙️ Impostazioni → 📻 Stazione** ①, inserisci nominativo, ID DMR e posizione ②. Due cifre come suffisso dell’hotspot rendono unico l’ID dell’hotspot se hai più dispositivi.'),
            ('modem', 'Impostare il modem', 'In **📡 Modem** ① scegli la scheda modem ② – questo compila porta, velocità e simplex/duplex. **Trova il modem** trova da solo la porta. Poi inserisci le frequenze di trasmissione e ricezione; in simplex sono uguali.'),
            ('network', 'Collegarsi al server DMR', 'In **🛰️ Rete DMR** ① scegli il server dalla lista ② (compila nome, indirizzo e porta) e inserisci la password – presso la N8schicht la tua password FreeRadioID.net per l’accesso completo.'),
            ('cal', 'Calibrare la frequenza', 'In **🎛️ Calibrazione** ① trovi l’offset di frequenza del tuo modem ②: avvia, trasmetti con la radio sulla frequenza simplex indicata e sposta la frequenza finché il BER è minimo (idealmente sotto l’1 %). Poi salva l’offset.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID è un server DMR con accesso FreeRadioID, dashboard, OpenBridge e APRS. Questa guida ti accompagna nei primi passi.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installare', 'Su un server Debian o Ubuntu con diritti sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nIl setup chiede nome del server, porte, superadmin e accesso FreeRadioID e configura i servizi. Dopo la dashboard è raggiungibile su `http://<server>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'Impostare il server DMR', 'Nell’area admin, in **📡 Esercizio → 🛰️ Server DMR** ①, trovi porta (predefinita 62031), tempi e collegamenti ad altri server ②. Ripetitori e hotspot si collegano a questa porta; le modifiche hanno effetto dopo un riavvio del server DMR.'),
            ('access', 'Accesso e FreeRadioID', 'In **⚙️ Impostazioni** ① stabilisci chi vede la dashboard e l’accesso di ripetitori e hotspot ②: passphrase, talkgroup e l’**accesso FreeRadioID**. Con FreeRadioID ogni stazione accede con la propria password personale; la passphrase diventa l’accesso ospite con talkgroup propri.'),
            ('aprs', 'Attivare l’APRS', 'In **📡 APRS** ① attivi il server APRS con mappa ②: ID del server (il tuo nominativo con SSID), porte aperte per app APRS e iGate e l’uplink verso APRS-IS. Le posizioni GPS del traffico DMR compaiono poi sulla mappa.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
