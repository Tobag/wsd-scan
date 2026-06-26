# CLAUDE.md — wsd-scan

Persistent project context for AI agents working in this repo.

## Project

WSD push-scan receiver for Linux. Implements device-initiated scanning via the WS-Scan / DPWS (Devices Profile for Web Services) standard. Lets a user walk up to a WSD-capable MFP, select a scan profile from the printer panel, and have the scanned document delivered to a Linux machine.

Target device for development: Samsung M288x Series MFP (IP 192.168.0.149, safira homelab).

## Origin and Evaluation

This repo is a fork of roncapat/WSD-python (github.com/roncapat/WSD-python), copied at the library level with flat imports rather than depending on it as a package. Both upstreams are inactive (WSD-python last commit Feb 2020, wsd-scan last commit Jun 2020).

Decision: build on wsd-scan as the base because it is already ahead — it has the complete working push-scan flow that WSD-python only has as a stub. The packaging problems (flat imports, no setup.py) are fixable; re-implementing working features from scratch is not worth it.

WSD-python's README lists "Linux daemon for device-initiated scans" as a roadmap target. If that project ever becomes active again, improvements can be offered back upstream. Do not plan around a dead upstream.

## Protocol Background

WSD (Web Services for Devices) is an OASIS-standardized protocol (DPWS v1.1) using SOAP/XML over HTTP. WS-Scan is the scan-specific profile published by Microsoft. It is a cross-vendor standard adopted by all major MFP manufacturers since ~2007 (Brother, Canon, Dell, HP, Kyocera, Lexmark, Epson, OKI, Ricoh, Samsung, Xerox).

Push-scan flow:
1. Client subscribes to ScanAvailableEvent on the scanner's WSD service endpoint
2. Client pushes scan profiles (name, format, resolution, color, input source) to the device
3. User walks up to the printer panel and selects a profile
4. Scanner sends ScanAvailableEvent (SOAP POST) to the client's HTTP listener (port 6666)
5. Client retrieves the DefaultScanTicket, overrides it with profile values, creates a scan job
6. Client retrieves image(s) via RetrieveImage (MIME multipart response)
7. Client saves images, optionally compiles to PDF, optionally sends via SMTP

Key WSD concepts: WS-Discovery (UDP multicast device discovery), WS-Transfer (Get metadata), WS-Eventing (subscribe/unsubscribe), WS-Scan (scanner-specific operations).

## File Map

```
wsd_scan/                        — Python package (pip-installable)
  __init__.py                    — Package marker
  __main__.py                    — Enables `python -m wsd_scan`
  cli.py                         — CLI entry point (argparse: start -t TARGET -s SELF_IP)
  wsd_scan__events.py            — HTTP listener, event handlers, device_initiated_scan_worker, subscription logic
  wsd_scan__operations.py        — WS-Scan operations: GetScannerElements, CreateScanJob, RetrieveImage, ValidateScanTicket
  wsd_scan__parsers.py           — XML response parsers for scanner elements, tickets, job status
  wsd_scan__structures.py        — Data classes: ScanTicket, DocumentParams, ScanJob, MediaSide, etc.
                                   ScanTicket.override_params() applies YAML profile to default ticket
  wsd_common.py                  — SOAP/HTTP transport, XML helpers, namespace map, template loading
  wsd_globals.py                 — Global state: URN, debug flag, message dedup ring buffer, scan_profiles
  wsd_discovery__operations.py   — WS-Discovery (Probe/Resolve over UDP multicast)
  wsd_discovery__parsers.py      — Discovery response parsers
  wsd_discovery__structures.py   — Discovery data structures
  wsd_transfer__operations.py    — WS-Transfer (Get metadata from device)
  wsd_transfer__structures.py    — HostedService, ThisDevice, ThisModel metadata classes
  wsd_eventing__operations.py    — WS-Eventing (Subscribe/Unsubscribe/Renew)
  xml_helpers.py                 — DateTime/duration XML formatting
  mail_service.py                — SMTP email delivery for scanned documents
  profiles/
    scan_profile_*.yaml          — Scan profiles (LQ, HQ, grayscale, JPEG): color, format, quality, resolution, input_src, paper_size
    mail_service.yaml            — SMTP credentials (sender, recipient, server, user, password)
  templates/                     — 17 XML SOAP request templates (ws-scan__*, ws-eventing__*, ws-discovery__*, ws-transfer__*)
tests/                           — Development test scripts (probe_device, test_discovery, test_subscribe, test_e2e, test_pkg)
scans/.gitignore                 — Scan output directory (created at runtime)
pyproject.toml                   — Package metadata, entry point: wsd-scan = wsd_scan.cli:main
requirements.txt                 — Pinned dependencies
Dockerfile                       — Docker image (python:3.11-slim, exposes 6666)
start_script.sh                  — Interactive Docker entrypoint
wsd-scan.service                 — Systemd unit TEMPLATE (placeholders filled by install.sh)
install.sh                       — Reproducible installer (system or --user mode, writes .install-record)
uninstall.sh                     — Reads .install-record, undoes the install
.install-record                  — Generated by install.sh, gitignored, consumed by uninstall.sh
```

## Tech Stack

- Python 3.6+ (Dockerfile pins 3.11)
- Dependencies: python-dateutil, lxml, requests, PyYAML, Pillow (PIL), img2pdf, secure-smtplib
- Packaged as a pip-installable package via pyproject.toml (setuptools)
- Entry point: `wsd-scan` console script (wsd_scan.cli:main)
- Also runnable as `python -m wsd_scan`

## Commands

```bash
# Install (system-wide, default) — venv + editable pip + systemd service
./install.sh
# Install (user-level service, no sudo)
./install.sh --user
# Install with explicit scanner/self IP (skip the prompt)
./install.sh -t http://192.168.0.149:8018/wsd -s 192.168.0.110

# Uninstall — reads .install-record, removes unit + pip package; leaves repo/venv/scans/profiles
./uninstall.sh

# Re-run install.sh after code or profile changes — it reinstalls + restarts the service.

# Manual install (editable, from repo root, no systemd)
pip install -e .

# Run (installed as console script)
wsd-scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110

# Run (as module)
python -m wsd_scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110

# Run with debug
wsd-scan start -t http://192.168.0.149:8018/wsd -s 192.168.0.110 -d

# Docker
docker build -t wsd-scan .
docker run -p 6666:6666 wsd-scan
```

The `-t` flag is the WSD endpoint URL of the scanner. The `-s` flag is the local IP the scanner can reach (for callback). Port 6666 is the default for the HTTP event listener (configurable via `--port`).

`install.sh` fills the `wsd-scan.service` template (placeholders like `__TARGET__`, `__SELF_IP__`, `__USER__`) with runtime values and writes `.install-record` so `uninstall.sh` can undo exactly what was installed. Lines prefixed `#@SYSTEM` in the template are system-mode only (stripped in system mode, deleted in `--user` mode). Default is system-wide install (`/etc/systemd/system/`); `--user` installs to `~/.config/systemd/user/`.

## Known Issues and Technical Debt

- Port 6666 was hardcoded; now configurable via --port (default still 6666).
- Subscription refresh: subscribes once and waits. No WS-Eventing Renew before 1-hour expiry (TODO in cli.py).
- wsd_retrieve_image uses Image.NONE sentinel for no-images-available (not a real PIL constant).
- XML templates loaded via dumb string substitution ({{PLACEHOLDER}}) not XML tree manipulation (noted as TODO in wsd_common.py).
- Scan output dir defaults to ./scans but is configurable per-profile via target_folder in YAML (supports ~ and $HOME).

## Samsung M288x Specifics

- IP: 192.168.0.149 (safira homelab network)
- WSD endpoint: http://192.168.0.149:8018/wsd (needs verification)
- Already works with sane-airscan for pull-scan (WSD backend, device airscan:w0)
- AirScan config: /etc/sane.d/airscan.conf
- Known scan format limitation: JPEG works at all resolutions (75-300dpi). TIFF/PNG only up to 150dpi (WSD transfer limit).
- Panel scan options: Scan to PC, Scan to WSD, Scan to Email, Scan to USB. No Scan to SMB/FTP.
- Scan to PC requires Samsung Easy Printer Manager (Windows/macOS only). Scan to WSD is what this project implements.

## Development Goals

Phase 1 — Get it working with Samsung M288x:
- Verify WSD endpoint URL for the M288x
- Create scan profiles matching M288x capabilities (JPEG format, ADF + Platen)
- Test end-to-end push-scan flow
- Debug and fix any Samsung-specific protocol quirks

Phase 2 — Packaging cleanup (DONE):
- Add requirements.txt
- Restructure into proper Python package (pyproject.toml + setuptools)
- Fix flat imports to package-relative imports (from . import)
- Make pip-installable (wsd-scan console script + python -m wsd_scan)

Phase 3 — Daemon and production readiness (DONE):
- Systemd service file
- Configurable port (not hardcoded 6666)
- Proper logging (replace print with logging module)
- Auto-discovery via WS-Discovery (instead of requiring -t target IP)
- Fix WSDScannerMonitor queue bugs
- Error handling and retry for network failures
- Profile hot-reload without restart
- Unsubscribe on shutdown

Phase 4 — Polish:
- CLI improvements (list devices, list profiles, test connection)
- README rewrite with setup instructions
- Tests
- Optional: web UI for profile management

## Conventions

- Keep the WSD protocol layer (wsd_common, wsd_discovery, wsd_transfer, wsd_eventing, wsd_scan__operations/parsers/structures) clean and standard-compliant. Device-specific quirks go in the application layer (wsd-scan.py, wsd_scan__events.py).
- XML templates use {{PLACEHOLDER}} substitution. Keep them minimal and standard-compliant.
- YAML profiles are the user-facing configuration surface. Keep them simple and well-commented.
- Python 3.6+ compatibility (match original). No f-strings in shared library code unless we bump the minimum version.
