# Samsung M288x Series MFP — Device-Specific Quirks & Gotchas

Target device for this project. Samsung M288x Series MFP on the safira homelab network.
IP: 192.168.0.149. WSD scan endpoint: `http://192.168.0.149:8018/wsd/scan`

Everything here is specific to this device or its firmware. General WSD protocol
pitfalls are in `WSD-SCAN-PITFALLS.md`.

## Network & Endpoint

- The WSD endpoint path is `/wsd/scan`, not `/wsd`. The device advertises
  `http://192.168.0.149:8018/wsd` in WS-Discovery XAddrs, but the actual scan
  service lives at `/wsd/scan`. You discover this by doing WS-Transfer Get on
  the device endpoint and reading the HostedService types + endpoint references
  from the metadata response.
- The device also advertises a second XAddr `http://192.168.3.1:8018/wsd`
  (a different network interface). Ignore it — use the one on your subnet.
- Port 8018 responds HTTP 400 to a bare GET. It only accepts SOAP POSTs with
  proper WS-Addressing headers. This is normal, not an error.

## Device Capabilities (from GetScannerElements)

| Capability            | Value                                      |
|-----------------------|--------------------------------------------|
| Formats               | jfif, tiff-single-uncompressed             |
| Resolutions           | 75, 100, 150, 200, 300 dpi                 |
| Color modes           | BlackAndWhite1, Grayscale8, RGB24          |
| Input sources         | Platen, ADF (no duplex)                    |
| Max scan size         | 8503 x 11732 (units: 1/600 inch)           |
| DocumentSizeAutoDetect| Not supported (false)                       |
| AutoExposure          | Not supported (false)                       |
| Brightness/Contrast   | Supported                                   |
| Scaling               | 25–400%                                    |
| Rotations             | 0, 180                                     |

## Format Limitations

- **jfif works at all resolutions** (75–300 dpi). This is the safe choice.
- **tiff-single-uncompressed only works up to 150 dpi.** Above 150 dpi the
  device fails the transfer (WSD transfer size limit). If you need 200 or 300
  dpi, use jfif.
- The DefaultScanTicket the device returns uses `jfif` at 200 dpi, RGB24,
  Platen, CompressionQualityFactor=1. This is a good baseline.

## DestinationToken Behavior (the critical gotcha)

- Each ScanAvailableEvent Subscribe creates a **new** DestinationToken and a
  **new** destination entry on the device's panel. The old token becomes
  invalid immediately.
- The 60-second re-subscribe loop (original code) creates dozens of duplicate
  destinations on the device. The panel may show stale entries that reference
  tokens we've already overwritten. When the user selects one of those, the
  CreateScanJob fails with `wscn:ClientErrorInvalidDetinationToken`.
- **Subscribe once, keep the process alive.** Use WS-Eventing Renew before the
  1-hour expiry if you need long-running operation. Do NOT re-subscribe from
  scratch.
- The ScanAvailableEvent does NOT contain a DestinationToken. It only carries
  ClientContext, ScanIdentifier, and InputSource. You must look up the token
  from your own map keyed by ClientContext.

## Device Crash / Reboot Behavior

- If you flood the device with rapid re-subscriptions (the 60-second loop
  running for several minutes), the device's WSD service becomes unresponsive.
  WS-Transfer Get hangs indefinitely (100s timeout in wsd_common.py).
- In one observed case, pressing a profile on the panel after the device was
  overwhelmed caused it to display garbled text (including the word "param")
  and then **reboot itself**. After reboot, all subscriptions are cleared.
- Ctrl-C without unsubscribing also leaves stale subscription state. The device
  still responds to WS-Discovery Probe but hangs on WS-Transfer Get. A physical
  reboot is required to recover.
- After a reboot, wait ~30 seconds for the WSD service to come back online
  before re-subscribing. `ping` works immediately but the WSD HTTP endpoint
  takes longer.
- Keep a single subscription cycle. Don't hammer the device.

## InputSource from ScanAvailableEvent

- The ScanAvailableEvent always includes an `<wscn:InputSource>` element.
  In our tests it reported `Platen` even when we configured the profile for
  `Auto`/`ADF`. The device seems to decide the input source based on what's
  physically available (paper in ADF vs not).
- **Respect the InputSource from the event.** Do not blindly override to ADF
  as the original code did. If the device says Platen, send Platen in
  CreateScanJob. If you send ADF when there's no paper, the job fails or
  returns no images.

## Panel Behavior

- "Scan to WSD" is the correct panel menu for this project. Not "Scan to PC"
  (that requires Samsung Easy Printer Manager, Windows/macOS only).
- The device shows all subscribed profiles as entries under "Scan to WSD".
  Profile names come from `ClientDisplayName` in the Subscribe request.
- When a CreateScanJob fails (e.g. InvalidDestinationToken), the panel shows
  "not available" — there is no detailed error on the panel. Check the daemon
  log for the SOAP fault.
- When the scan succeeds, the device scans and returns to the main menu
  silently. No confirmation message on the panel.

## CompressionQualityFactor

- The device supports 0–100. The DefaultScanTicket uses 1 (nearly lossless).
- Our profiles use 100 for smaller JPEG files. This works fine with jfif.

## Paper Size Units

- WSD uses 1/600 inch units. A4 = 8267 x 11693. Letter = 8500 x 11000.
- The device max is 8503 x 11732, which is slightly larger than A4.
- ScanRegion width/height of 0 (from DefaultScanTicket) means "full scan area".
  When overriding, set explicit dimensions matching the paper size.
