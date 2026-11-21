# ADN FRN Server

A fresh-install dashboard and administration portal for the Java FreeRadioNetwork server.

## Features

- Live dashboard, rooms, stations, last-heard and statistics
- Admin portal with server controls, users, logs and audit trail
- FRN settings stored in SQLite and rendered to `server.properties`
- Hourly update checks at each full hour for this GitHub repository and the upstream Java FRN server
- Separate **Upgrade Dashboard** and **Upgrade Java** actions; updates are never installed automatically
- Optional import of a single legacy `server.properties` file after installation; no old database, JAR, ACL files or running installation is migrated
- HBlink4-inspired links popover, accent color selection and PNG logo upload

## Fresh installation

On Debian/Ubuntu/Raspberry Pi OS:

```bash
git clone https://github.com/dhartmann1979/adn-frn-server.git
cd adn-frn-server
chmod +x scripts/install.sh scripts/update.sh
sudo ./scripts/install.sh
```

The installer defaults to `/opt/adn-frn-server`. It is intentionally for a clean installation and stops if it detects an existing FRN database, FRN `server.properties`, or running FRN service. It does not overwrite an older installation.

## Import an older server.properties (optional)

After the fresh installation, sign in to the Admin panel and use **System → Import server.properties**. Select only the old `server.properties` file. Supported server settings and room definitions are imported into the new dashboard database. No old application files, database, JAR, ACL XML or FRN password XML are copied. Review the import result and restart the Java FRN server to apply it.

## Updates

The dashboard checks both sources at the next full hour and then hourly. Administrators can also check manually. GitHub updates are fast-forward-only and are refused if the working tree has local changes. The Java update uses the upstream FRN release archive. Updates are not installed automatically.

For a dashboard update:

```bash
cd /opt/adn-frn-server
sudo ./scripts/update.sh
```

## Branding

The **Appearance** panel in Admin → System accepts a PNG logo (up to 2 MB) and an accent color. The logo is stored in the dashboard data directory, not in the source checkout.

## Documentation

- [German installation guide](docs/de/installation.md)
- [Admin panel](docs/de/adminbereich.md)
- [Operations and troubleshooting](docs/de/betrieb.md)
- [Dashboard](docs/de/dashboard.md)
- [Configuration reference](docs/de/konfiguration.md)

## References

- [FRN server](https://freeradionetwork.de/)
- [HBlink4-FreeRadioID](https://github.com/dhartmann1979/HBlink4-FreeRadioID) – visual and interaction reference
