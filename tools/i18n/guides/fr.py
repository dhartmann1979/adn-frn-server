UI = {
    'title': 'Pas à pas', 'contents': 'Sommaire', 'lang': 'Langue', 'more': 'Description détaillée (allemand)',
    'step': 'Étape', 'back': 'Retour à l’aperçu', 'shots': 'Les chiffres jaunes des images correspondent aux chiffres du texte.',
}
SHARED = {
    'lang': ('Choisir la langue', 'En haut à droite, **🌐 FR ▾** ① ouvre le menu des langues ② avec neuf langues. Le choix s’applique immédiatement et à toutes les interfaces N8 de ce serveur. Lors de la première visite, la langue du navigateur est utilisée.'),
    'domains': ('Domaine propre avec HTTPS', 'Sous **🌐 Réseau, ports et domaines → 🔒 Domaines et HTTPS** ①, saisissez un domaine qui pointe vers le serveur par DNS, ainsi qu’une adresse e-mail pour Let’s Encrypt ②. Le certificat est obtenu et renouvelé automatiquement. Les ports 80 et 443 doivent être joignables depuis Internet.'),
    'users': ('Ajouter des utilisateurs', 'Sous **👥 Utilisateurs et accès → Utilisateurs** ①, ajoutez d’autres comptes et attribuez-leur un rôle ②. Les admins voient les adresses IP et modifient les réglages, les utilisateurs ne voient que le tableau de bord. Sous **Sessions**, vous terminez des connexions ; le **Journal** affiche chaque modification.'),
    'update': ('Mettre à jour', 'Sous **🖥️ Système → ⬆️ Mise à jour** ①, vous voyez la version installée et si GitHub en propose une plus récente ②. **⬆️ Installer la mise à jour maintenant** la télécharge, vérifie ensuite l’interface web et restaure automatiquement la version précédente en cas de problème. Aucun mot de passe n’est nécessaire.'),
    'backup': ('Sauvegarder', 'Sous **🖥️ Système → 💾 Sauvegarde** ①, créez une sauvegarde chiffrée de toutes les données ② et restaurez-la au besoin – y compris sur un nouveau serveur. Conservez bien le mot de passe de la sauvegarde : sans lui, elle ne peut pas être ouverte.'),
    'login': ('Se connecter', 'Cliquez sur **🔐 Se connecter** en haut à droite. Dans la fenêtre de connexion ①, saisissez le nom d’utilisateur et le mot de passe ; 👁 affiche le mot de passe, « Rester connecté » évite de se reconnecter la prochaine fois. Après cinq tentatives erronées, le nom est bloqué pendant 15 minutes. Une fois connecté, l’avatar et le nom ▾ apparaissent avec le compte, l’espace admin et la déconnexion.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'L’ADN FRN Server est un serveur FreeRadioNetwork avec tableau de bord, espace admin, portail d’actualités et serveur de messagerie. Ce guide vous accompagne dans les premières étapes.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installer', 'Sur un serveur Debian ou Ubuntu, en tant qu’utilisateur disposant des droits sudo :\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nL’installateur configure Java, le serveur FRN, le tableau de bord, les services et les droits, puis demande le superadmin. Ensuite, le tableau de bord est accessible sous `http://<serveur>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Configurer le serveur FRN', 'Dans l’espace admin, sous **📡 Exploitation → ⚙️ Réglages → 🛰️ Serveur FRN** ①, se trouvent l’adresse, le port et les délais du serveur FRN ②. Sous **🌐 SystemManager**, choisissez si le serveur est enregistré auprès du SystemManager ou fonctionne de manière autonome. Redémarrez le serveur FRN après l’enregistrement.'),
            ('rooms', 'Créer des salons', 'Sous **🏠 Salons** ①, créez les salons (nets) ② : nom, emoji, propriétaires, qui peut émettre et le test d’écho perroquet. L’ordre sur le tableau de bord se règle avec ▲ ▼. Le serveur FRN applique les modifications après un redémarrage.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink relie FRN, DMR et Zello en un réseau radio commun. Ce guide vous accompagne dans les premières étapes.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Installer', 'Sur un ordinateur Debian ou Ubuntu (y compris Raspberry Pi) avec les droits sudo :\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nL’installateur configure le programme, le service, le vocodeur et les droits sous `/opt/n8crosslink`. Ensuite, l’interface est accessible sous `http://<ordinateur>:8080`.'),
            ('setup', 'Créer le superadmin', 'Lors du premier accès, **Créer un superadmin** ① apparaît : nom d’utilisateur et mot de passe d’au moins 8 caractères, à répéter. Ce compte peut tout faire, y compris restaurer des sauvegardes. Par la suite, vous vous connectez dans la même fenêtre.'),
            ('lang', None, None),
            ('frn', 'Connecter FRN', 'Dans l’espace admin, sous **📡 Exploitation → 📻 FRN** ①, saisissez serveur, port, e-mail et mot de passe FRN ②. Choisissez le **salon** dans la liste lue directement depuis le serveur FRN. Pas encore de mot de passe FRN ? Il peut être demandé ici au SystemManager.'),
            ('dmr', 'Connecter DMR', 'Sous **📡 DMR** ① se trouvent le serveur DMR, l’ID de pair, le mot de passe et les talkgroups ②. Avec HBlink4-FreeRadioID, le mot de passe est votre mot de passe FreeRadioID personnel – avec la phrase secrète du serveur, le pont n’est qu’invité et ne peut pas émettre sur tous les talkgroups.'),
            ('routes', 'Définir le routage', 'Sous **🔀 Routage** ①, déterminez quelle source va dans quel réseau ②, p. ex. FRN → DMR et DMR → FRN. Un temps de verrouillage après l’émission empêche le ping-pong entre les réseaux. Les modifications s’appliquent immédiatement.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Sauvegarder et repartir de zéro', 'Sous **🖥️ Système → 💾 Sauvegarde et nouveau départ** ①, créez une sauvegarde chiffrée ② – la clé est le mot de passe superadmin au moment de la sauvegarde. Les statistiques ou tous les réglages peuvent aussi être réinitialisés ici.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'Le N8 Hotspot est une interface web pour MMDVMHost et DMRGateway sur un Raspberry Pi équipé d’une carte modem. Ce guide vous accompagne dans les premières étapes.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installer', 'Le plus simple est l’image DietPi prête à l’emploi : l’écrire sur une carte SD, l’insérer dans le Raspberry Pi, démarrer. Sinon, sur un DietPi en fonctionnement :\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nEnsuite, l’interface est accessible sous `http://n8-hotspot.local` (ou l’adresse IP).'),
            ('login', 'Se connecter', 'Cliquez sur **🔐 Se connecter** en haut à droite et connectez-vous dans la fenêtre de connexion ① avec l’identifiant d’usine **n8schicht / n8schicht**. 👁 affiche le mot de passe, « Rester connecté » évite de se reconnecter la prochaine fois.'),
            ('password', 'Définir son propre mot de passe', 'Tant que l’identifiant d’usine est actif, **🔑 Mon compte** ① s’ouvre et aucun réglage ne peut être modifié. Choisissez votre propre nom d’utilisateur et un mot de passe d’au moins 8 caractères – l’identifiant d’usine ne fonctionne plus ensuite.'),
            ('lang', None, None),
            ('station', 'Saisir la station', 'Dans l’espace admin, sous **📡 Exploitation → ⚙️ Réglages → 📻 Station** ①, saisissez l’indicatif, l’ID DMR et l’emplacement ②. Deux chiffres comme suffixe du hotspot rendent l’ID du hotspot unique si vous avez plusieurs appareils.'),
            ('modem', 'Régler le modem', 'Sous **📡 Modem** ①, choisissez la carte modem ② – cela remplit le port, la vitesse et simplex/duplex. **Trouver le modem** détecte le port tout seul. Ajoutez ensuite les fréquences d’émission et de réception ; en simplex, elles sont identiques.'),
            ('network', 'Se connecter au serveur DMR', 'Sous **🛰️ Réseau DMR** ①, choisissez le serveur dans la liste ② (remplit nom, adresse et port) et saisissez le mot de passe – chez la N8schicht, votre mot de passe FreeRadioID.net pour un accès complet.'),
            ('cal', 'Étalonner la fréquence', 'Sous **🎛️ Étalonnage** ①, déterminez le décalage de fréquence de votre modem ② : démarrez, émettez avec votre radio sur la fréquence simplex affichée et déplacez la fréquence jusqu’à ce que le BER soit le plus bas (idéalement sous 1 %). Enregistrez ensuite le décalage.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID est un serveur DMR avec connexion FreeRadioID, tableau de bord, OpenBridge et APRS. Ce guide vous accompagne dans les premières étapes.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Installer', 'Sur un serveur Debian ou Ubuntu avec les droits sudo :\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nLe setup demande le nom du serveur, les ports, le superadmin et la connexion FreeRadioID, puis configure les services. Ensuite, le tableau de bord est accessible sous `http://<serveur>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'Régler le serveur DMR', 'Dans l’espace admin, sous **📡 Exploitation → 🛰️ Serveur DMR** ①, se trouvent le port (par défaut 62031), les temporisations et les liens vers d’autres serveurs ②. Relais et hotspots se connectent sur ce port ; les modifications s’appliquent après un redémarrage du serveur DMR.'),
            ('access', 'Accès et FreeRadioID', 'Sous **⚙️ Réglages** ①, déterminez qui voit le tableau de bord et l’accès des relais et hotspots ② : phrase secrète, talkgroups et **connexion FreeRadioID**. Avec FreeRadioID, chaque station se connecte avec son mot de passe personnel ; la phrase secrète devient l’accès invité avec ses propres talkgroups.'),
            ('aprs', 'Activer l’APRS', 'Sous **📡 APRS** ①, activez le serveur APRS avec carte ② : ID du serveur (votre indicatif avec SSID), ports ouverts pour les applis APRS et iGates, et l’uplink vers APRS-IS. Les positions GPS du trafic DMR apparaissent alors sur la carte.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
