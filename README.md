# ADN FRN Server

A browser dashboard and administration portal for the Java FreeRadioNetwork server.

## Features

- Live dashboard, rooms, stations, last-heard and statistics
- Admin portal with server controls, users, logs and audit trail
- FRN settings stored in SQLite and rendered to `server.properties`
- Hourly update checks at each full hour for this GitHub repository and the upstream Java FRN server
- Separate **Upgrade Dashboard** and **Upgrade Java** actions; updates are never installed automatically
- Import of existing `server.properties` with a timestamped backup; recognized server options and room definitions are imported while existing ACL XML files are preserved
- HBlink4-inspired links popover, accent color selection and PNG logo upload

## Install

On Debian/Ubuntu/Raspberry Pi OS:

```bash
git clone https://github.com/dhartmann1979/adn-frn-server.git
cd adn-frn-server
chmod +x scripts/install.sh scripts/update.sh
sudo ./scripts/install.sh
```

The existing installer provisions Java, the FRN server and the dashboard. Review the installation script and configure the service paths before deploying to a production host.

## Update behavior

The dashboard checks both sources at the next full hour and then hourly. Administrators can also check manually. GitHub updates are fast-forward-only and are refused if the working tree has local changes. The Java update uses the upstream FRN release archive and restarts the FRN service. Dashboard code updates require restarting the dashboard service after installation.

## Importing a legacy configuration

Open **Admin → System → Import server.properties**, choose the existing file and confirm. Supported server and room properties are imported into SQLite. The current generated `server.properties` is backed up before it is regenerated. ACL XML files and FRN password XML are not overwritten by the import.

## Branding

The **Appearance** panel in Admin → System accepts a PNG logo (up to 2 MB) and an accent color. The logo is stored in the dashboard data directory, not in the source checkout.

## References

- [FRN server](https://freeradionetwork.de/)
- [HBlink4-FreeRadioID](https://github.com/dhartmann1979/HBlink4-FreeRadioID) – visual and interaction reference
