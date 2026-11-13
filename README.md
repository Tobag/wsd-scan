# wsd-scan

WSD push-scan receiver for Linux. Implements device-initiated scanning via the
WS-Scan / DPWS (Devices Profile for Web Services) standard. Walk up to a
WSD-capable MFP, select a scan profile from the printer panel, and the scanned
document is delivered to your Linux machine.

Based on [roncapat/WSD-python](https://github.com/roncapat/WSD-python).

## How it works

1. `wsd-scan` subscribes to ScanAvailableEvent on the scanner's WSD service endpoint
2. It pushes scan profiles (name, format, resolution, color, input source) to the device
3. You walk up to the printer panel and select a profile
4. The scanner sends ScanAvailableEvent (SOAP POST) to the HTTP listener (port 6666)
5. `wsd-scan` retrieves the DefaultScanTicket, overrides it with profile values, creates a scan job
6. It retrieves image(s) via RetrieveImage, saves them, optionally compiles to PDF, optionally emails

## Quick start

```bash
# Install — auto-discovers scanner on the network, auto-detects local IP
./install.sh

# Install (user-level service, no sudo)
./install.sh --user

# Install with explicit target (skip discovery)
./install.sh -t http://PRINTER_IP:PORT/wsd -s YOUR_IP

# Or just the pip package, no systemd
pip install -e .
```

`install.sh` creates a project venv (`.venv/`), pip-installs the package,
auto-discovers WSD scanners via UDP multicast (filtering for `/wsd` endpoints),
auto-detects your local IP from the default route, fills the
`wsd-scan.service` template with those values, enables and starts the service,
and writes `.install-record` (used by `uninstall.sh`).

If multiple scanners are found, you'll be prompted to pick one. If none are
found, you can enter the URL manually. Use `--no-discover` to skip
auto-discovery entirely.

To find your printer's WSD endpoint:
```bash
wsd-scan list-devices
```

To verify a specific device responds and has a scanner service:
```bash
wsd-scan test-connection -t http://PRINTER_IP:PORT/wsd
```

## Usage

```
wsd-scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110
wsd-scan start --auto -s 192.168.0.110
wsd-scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110 -d
```

Commands:
- `start` — Start the scan receiver (daemon mode). Subscribes to events and waits for scans.
- `list-devices` — Discover WSD scanners on the local network via UDP multicast.
- `list-profiles` — List loaded scan profiles.
- `test-connection` — Probe a device, fetch metadata, verify it has a scanner service.

Options for `start`:
- `-t, --target` — WSD endpoint URL of the scanner. Required unless `--auto` is used.
- `-s, --self` — Local IP the scanner can reach (for callback). Required.
- `-p, --port` — HTTP listener port (default: 6666).
- `--auto` — Auto-discover WSD scanners via UDP multicast (no `-t` needed).
- `-d, --debug` — Enable debug output (SOAP exchanges).

## Scan profiles

Profiles are YAML files in `wsd_scan/profiles/`. Each profile becomes an entry
on the printer's scan panel. Hot-reloaded — edit a profile and it takes effect
without restarting the service.

```yaml
id: color_hq_auto          # unique identifier (used as client_context)
name: Color HQ             # display name shown on the printer
color: RGB24               # RGB24, Grayscale8, BlackAndWhite1
format: jfif               # WSD format string (device-dependent)
image_format: jpeg         # PIL save format
quality: 70                # 0-100, PIL save quality
target_folder: ~/Pictures/scans  # output directory (~ and $HOME expanded)
work_folder: /tmp/wsd-scan      # optional: page images go here, only the PDF lands in target_folder
send_email: False          # send scanned document via SMTP
use_pdf: True              # compile images into a PDF
paper_size: A4             # A4, A5, Letter
resolution: 300            # dpi
input_src: Auto            # Auto, ADF, Platen
```

With `work_folder` set, the page images are written there and removed once the PDF is
complete; the PDF is written under a temporary name and renamed, so tools that watch
`target_folder` (sync clients, document importers) never pick up a half-written file.
Without `use_pdf`, the images are moved to `target_folder` when the scan is done.

List loaded profiles:
```bash
wsd-scan list-profiles
```

## Long-running service

Devices grant the scan-available subscriptions (the panel entries) for one hour.
`wsd-scan start` renews them with WS-Eventing Renew, so the entries stay on the
panel. If the subscriptions are lost, for example because the printer was
restarted, the process waits for running scans, unsubscribes and exits with a
non-zero code; the service manager restarts it and it subscribes again. The
bundled systemd unit (`Restart=on-failure`) and Docker's `--restart
unless-stopped` both do that.

| Variable | Default | Meaning |
| --- | --- | --- |
| `WSD_SCAN_RENEW_S` | `300` | seconds between Renew requests |
| `WSD_SCAN_RENEW_EXPIRES` | `PT1H` | expiry requested with each Renew |
| `WSD_SCAN_RESUBSCRIBE_S` | `3300` | devices without Renew support: exit after this many seconds to re-subscribe before expiry |
| `WSD_SCAN_WAIT_FOR_SCANS_S` | `300` | how long to wait for a running scan before exiting |

Exit codes: `2` subscribe failed, `3` subscriptions lost, `4` planned
re-subscribe (device without Renew support).

## Email delivery

To receive scanned documents as email attachments, configure SMTP credentials
in `wsd_scan/profiles/mail_service.yaml`:

```yaml
to: recipient@example.com
sender: sender@example.com
smtp:
  user: smtpuser
  password: smtppass
  server: smtp.example.com
```

Then set `send_email: True` in the scan profile.

## Uninstall

```bash
./uninstall.sh
```

Reads `.install-record` and removes the systemd unit + pip package. Leaves the
repo, venv, scan outputs, and profiles intact. To fully purge the venv:
`rm -rf .venv`

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

Tests run without a physical scanner — they cover profile loading, XML template
substitution, and ScanTicket override logic.

## Docker

```bash
docker build -t wsd-scan .
docker run -p 6666:6666 wsd-scan
```

## Supported devices

Works with any WSD/DPWS-compliant scanner (Brother, Canon, Dell, HP, Kyocera,
Lexmark, Epson, OKI, Ricoh, Samsung, Xerox). Tested with:

- HP Laser MFP 137fnw (original upstream)
- Samsung M288x Series MFP
- HP Color Laser MFP 179fnw (multi-page ADF, Renew)

## Dependencies

lxml, requests, python-dateutil, PyYAML, Pillow (PIL), img2pdf, secure-smtplib

Python 3.6+.
