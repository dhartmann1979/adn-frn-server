UI = {
    'title': 'Paso a paso', 'contents': 'Contenido', 'lang': 'Idioma', 'more': 'Descripción detallada (alemán)',
    'step': 'Paso', 'back': 'Volver al resumen', 'shots': 'Los números amarillos de las imágenes corresponden a los números del texto.',
}
SHARED = {
    'lang': ('Elegir el idioma', 'Arriba a la derecha, **🌐 ES ▾** ① abre el menú de idiomas ② con nueve idiomas. La elección se aplica al instante y a todas las interfaces N8 de este servidor. En la primera visita se usa el idioma del navegador.'),
    'domains': ('Dominio propio con HTTPS', 'En **🌐 Red, puertos y dominios → 🔒 Dominios y HTTPS** ① introduzca un dominio que apunte al servidor por DNS y una dirección de correo para Let’s Encrypt ②. El certificado se obtiene y se renueva automáticamente. Los puertos 80 y 443 deben ser accesibles desde Internet.'),
    'users': ('Añadir usuarios', 'En **👥 Usuarios y acceso → Usuarios** ① añada más cuentas y asígneles un rol ②. Los admins ven las direcciones IP y cambian los ajustes, los usuarios solo ven el panel. En **Sesiones** termina accesos, el **Registro** muestra cada cambio.'),
    'update': ('Actualizar', 'En **🖥️ Sistema → ⬆️ Actualización** ① ve la versión instalada y si GitHub tiene una más reciente ②. **⬆️ Instalar la actualización ahora** la descarga, comprueba después la interfaz web y, si algo falla, restaura automáticamente la versión anterior. No hace falta contraseña.'),
    'backup': ('Hacer una copia de seguridad', 'En **🖥️ Sistema → 💾 Copia de seguridad** ① cree una copia cifrada de todos los datos ② y restáurela cuando haga falta – también en un servidor nuevo. Guarde bien la contraseña de la copia: sin ella no se puede abrir.'),
    'login': ('Iniciar sesión', 'Haga clic en **🔐 Iniciar sesión** arriba a la derecha. En la ventana de inicio de sesión ① introduzca nombre de usuario y contraseña; 👁 muestra la contraseña, «Mantener la sesión iniciada» evita iniciar sesión la próxima vez. Tras cinco intentos fallidos el nombre se bloquea 15 minutos. Con la sesión iniciada aparecen avatar y nombre ▾ con cuenta, área de administración y cerrar sesión.'),
}
SYSTEMS = {
    'adn': {
        'name': 'ADN FRN Server', 'intro': 'ADN FRN Server es un servidor FreeRadioNetwork con panel, área de administración, portal de noticias y servidor de correo. Esta guía le acompaña en los primeros pasos.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Instalar', 'En un servidor Debian o Ubuntu como usuario con derechos sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/adn-frn-server\ncd adn-frn-server\nsudo ./scripts/install.sh\n```\n\nEl instalador configura Java, el servidor FRN, el panel, los servicios y los permisos y pide el superadmin. Después el panel está en `http://<servidor>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('frn', 'Configurar el servidor FRN', 'En el área de administración, en **📡 Operación → ⚙️ Ajustes → 🛰️ Servidor FRN** ①, están la dirección, el puerto y los tiempos de espera del servidor FRN ②. En **🌐 SystemManager** elija si el servidor está registrado en el SystemManager o funciona de forma autónoma. Tras guardar, reinicie el servidor FRN.'),
            ('rooms', 'Crear salas', 'En **🏠 Salas** ① cree las salas (nets) ②: nombre, emoji, propietarios, quién puede emitir y la prueba de eco del loro. El orden en el panel se ajusta con ▲ ▼. El servidor FRN aplica los cambios tras un reinicio.'),
            ('domains', None, None), ('users', None, None), ('update', None, None), ('backup', None, None),
        ],
    },
    'crosslink': {
        'name': 'N8 Crosslink', 'intro': 'N8 Crosslink une FRN, DMR y Zello en una red de radio común. Esta guía le acompaña en los primeros pasos.',
        'more': 'docs/INSTALLATION.md',
        'steps': [
            ('install', 'Instalar', 'En un ordenador Debian o Ubuntu (también Raspberry Pi) con derechos sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8Crosslink.git\ncd N8Crosslink\nsudo ./install.sh\n```\n\nEl instalador configura programa, servicio, vocoder y permisos en `/opt/n8crosslink`. Después la interfaz está en `http://<ordenador>:8080`.'),
            ('setup', 'Crear el superadmin', 'En la primera visita aparece **Crear superadmin** ①: nombre de usuario y una contraseña de al menos 8 caracteres, y repetirla. Esta cuenta puede hacerlo todo, también restaurar copias. Más adelante inicia sesión en la misma ventana.'),
            ('lang', None, None),
            ('frn', 'Conectar FRN', 'En el área de administración, en **📡 Operación → 📻 FRN** ①, introduzca servidor, puerto, correo y contraseña FRN ②. La **sala** se elige de la lista que se lee directamente del servidor FRN. ¿Aún sin contraseña FRN? Puede solicitarla aquí al SystemManager.'),
            ('dmr', 'Conectar DMR', 'En **📡 DMR** ① están el servidor DMR, el ID de par, la contraseña y los talkgroups ②. Con HBlink4-FreeRadioID la contraseña es su contraseña personal de FreeRadioID – con la frase de paso del servidor, el puente es solo invitado y no puede emitir en todos los talkgroups.'),
            ('routes', 'Definir el enrutamiento', 'En **🔀 Enrutamiento** ① decida qué fuente va a qué red ②, p. ej. FRN → DMR y DMR → FRN. Un tiempo de bloqueo tras emitir evita el ping-pong entre las redes. Los cambios se aplican al instante.'),
            ('domains', None, None), ('update', None, None),
            ('backup', 'Copia de seguridad y empezar de nuevo', 'En **🖥️ Sistema → 💾 Copia de seguridad y empezar de nuevo** ① cree una copia cifrada ② – la clave es la contraseña del superadmin en el momento de la copia. Aquí también se pueden restablecer las estadísticas o todos los ajustes.'),
        ],
    },
    'hotspot': {
        'name': 'N8 Hotspot', 'intro': 'N8 Hotspot es una interfaz web para MMDVMHost y DMRGateway en una Raspberry Pi con placa módem. Esta guía le acompaña en los primeros pasos.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Instalar', 'Lo más sencillo es la imagen DietPi lista: grabarla en una tarjeta SD, insertarla en la Raspberry Pi y encender. O bien en una DietPi en marcha:\n\n```bash\ngit clone https://github.com/dhartmann1979/N8-HotSpot\ncd N8-HotSpot\nsudo ./scripts/setup.sh\n```\n\nDespués la interfaz está en `http://n8-hotspot.local` (o la dirección IP).'),
            ('login', 'Iniciar sesión', 'Haga clic en **🔐 Iniciar sesión** arriba a la derecha e inicie sesión en la ventana ① con el acceso de fábrica **n8schicht / n8schicht**. 👁 muestra la contraseña, «Mantener la sesión iniciada» evita iniciar sesión la próxima vez.'),
            ('password', 'Establecer una contraseña propia', 'Mientras el acceso de fábrica esté activo, se abre **🔑 Mi cuenta** ① y no se puede cambiar ningún ajuste. Elija un nombre de usuario propio y una contraseña de al menos 8 caracteres – después el acceso de fábrica deja de funcionar.'),
            ('lang', None, None),
            ('station', 'Introducir la estación', 'En el área de administración, en **📡 Operación → ⚙️ Ajustes → 📻 Estación** ①, introduzca indicativo, ID DMR y ubicación ②. Dos cifras como sufijo del hotspot hacen único el ID del hotspot si tiene varios equipos.'),
            ('modem', 'Ajustar el módem', 'En **📡 Módem** ① elija la placa módem ② – esto rellena puerto, velocidad y simplex/dúplex. **Buscar el módem** encuentra el puerto por sí solo. Después introduzca las frecuencias de emisión y recepción; en simplex son iguales.'),
            ('network', 'Conectar con el servidor DMR', 'En **🛰️ Red DMR** ① elija el servidor de la lista ② (rellena nombre, dirección y puerto) e introduzca la contraseña – en la N8schicht su contraseña de FreeRadioID.net para el acceso completo.'),
            ('cal', 'Calibrar la frecuencia', 'En **🎛️ Calibración** ① encuentra el desplazamiento de frecuencia de su módem ②: inicie, emita con su radio en la frecuencia simplex indicada y mueva la frecuencia hasta que el BER sea el más bajo (idealmente por debajo del 1 %). Después guarde el desplazamiento.'),
            ('update', None, None),
        ],
    },
    'hblink': {
        'name': 'HBlink4-FreeRadioID', 'intro': 'HBlink4-FreeRadioID es un servidor DMR con acceso FreeRadioID, panel, OpenBridge y APRS. Esta guía le acompaña en los primeros pasos.',
        'more': 'docs/de/installation.md',
        'steps': [
            ('install', 'Instalar', 'En un servidor Debian o Ubuntu con derechos sudo:\n\n```bash\ngit clone https://github.com/dhartmann1979/HBlink4-FreeRadioID /opt/HBlink4\nsudo /opt/HBlink4/scripts/setup.sh\n```\n\nEl setup pregunta nombre del servidor, puertos, superadmin y acceso FreeRadioID y configura los servicios. Después el panel está en `http://<servidor>:8080`.'),
            ('login', None, None), ('lang', None, None),
            ('dmr', 'Ajustar el servidor DMR', 'En el área de administración, en **📡 Operación → 🛰️ Servidor DMR** ①, están el puerto (por defecto 62031), los tiempos y los enlaces a otros servidores ②. Repetidores y hotspots se conectan a este puerto; los cambios se aplican tras reiniciar el servidor DMR.'),
            ('access', 'Acceso y FreeRadioID', 'En **⚙️ Ajustes** ① decida quién ve el panel y el acceso de repetidores y hotspots ②: frase de paso, talkgroups y el **acceso FreeRadioID**. Con FreeRadioID cada estación inicia sesión con su contraseña personal; la frase de paso pasa a ser el acceso de invitado con talkgroups propios.'),
            ('aprs', 'Activar APRS', 'En **📡 APRS** ① active el servidor APRS con mapa ②: ID del servidor (su indicativo con SSID), puertos abiertos para apps APRS e iGates y el uplink hacia APRS-IS. Las posiciones GPS del tráfico DMR aparecen entonces en el mapa.'),
            ('domains', None, None), ('users', None, None), ('update', None, None),
        ],
    },
}
