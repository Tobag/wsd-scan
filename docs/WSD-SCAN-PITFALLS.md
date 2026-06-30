# WSD Push-Scan — General Pitfalls & Lessons Learned

Protocol-level and codebase-level gotchas applicable to any WSD/WS-Scan
implementation. Device-specific quirks are in `SAMSUNG-M288X-QUIRKS.md`.

## XML Namespace: 2006/08 is the correct URI

The WS-Scan namespace is `http://schemas.microsoft.com/windows/2006/08/wdp/scan`.
The original codebase had two templates using the wrong URI
`http://schemas.microsoft.com/windows/2006/01/wdp/scan` (note: 01 not 08):

- `templates/ws-scan__create_scan_job.xml`
- `templates/ws-scan__scan_available_event_subscribe.xml`

The 2006/01 namespace appears to be an early draft. The 2006/08 namespace is
what the standard specifies and what real devices expect.

The Subscribe operation worked despite the wrong namespace because it's
primarily a WS-Eventing operation (the scan-specific elements are extensions).
But CreateScanJob is entirely scan-namespace-based — the device could not find
the DestinationToken element because it was in the wrong namespace, and
returned `wscn:ClientErrorInvalidDetinationToken`.

**Lesson:** Verify that every template uses `2006/08`. The parsers use the
namespace prefix `sca` mapped to `2006/08` in `wsd_common.py` NSMAP, so
template namespaces must match.

## XML Boolean Values: lowercase, not Python's capitalized

WSD/XML boolean values must be `true` / `false` (lowercase). Python's `str()`
on a boolean produces `True` / `False` (capitalized). The original `as_map()`
in `wsd_scan__structures.py` passed raw Python booleans for
`SIZE_AUTODETECT` and `AUTO_EXPOSURE`, producing invalid XML like
`<wscn:DocumentSizeAutoDetect>False</wscn:DocumentSizeAutoDetect>`.

Fix: `str(self.doc_params.size_autodetect).lower()` in `as_map()`. Check
every boolean field that goes through template substitution.

## DestinationToken Lifecycle

- A DestinationToken is issued by the device in the SubscribeResponse to a
  ScanAvailableEvent subscription.
- The token is tied to a specific subscription. Re-subscribing (sending a new
  Subscribe with the same ClientContext) creates a new token and invalidates
  the old one.
- The token must be sent in CreateScanJob to prove the scan request comes from
  the client that registered the destination.
- The ScanAvailableEvent does NOT carry the token — only ClientContext. You
  must maintain your own `client_context -> dest_token` map.
- **Never re-subscribe on a timer.** Subscribe once and use WS-Eventing Renew
  before the subscription expires (typically PT1H). Re-subscribing invalidates
  tokens and creates duplicate panel entries.

## ScanAvailableEvent Flow

The event carries three fields:
1. `ClientContext` — maps to the profile/destination the user selected
2. `ScanIdentifier` — unique per scan attempt, must be echoed in CreateScanJob
3. `InputSource` — the device's choice of Platen or ADF

The InputSource is the device telling you what it will scan from. Respect it.
The original code overrode "Auto" to "ADF" unconditionally, which fails when
the device has no paper in the ADF and reports Platen.

## Fault Handling Before Parsing

`wsd_create_scan_job()` in `wsd_scan__operations.py` did not check for SOAP
faults before calling `parse_scan_job()`. When the device returned a fault
(e.g. InvalidDestinationToken), the parser tried to find `sca:JobId` in a
fault response, got `None`, and crashed with
`AttributeError: 'NoneType' object has no attribute 'find'`.

Fix: call `wsd_common.check_fault(x)` before parsing. The same pattern should
be applied to all operation functions — always check for faults before
attempting to parse a success response.

## Subscription Refresh Strategy

The original code re-pushed all profiles every 60 seconds
(`time.sleep(60)` in `start()`). This is wrong for three reasons:

1. Creates duplicate destination entries on the device panel
2. Invalidates previously issued DestinationTokens
3. Can overwhelm the device's WSD service, causing it to hang or crash

Correct approach: subscribe once, then keep the process alive. Before the
1-hour subscription expires, send a WS-Eventing Renew to extend it. This is
not yet implemented — the current code just subscribes once and waits. For
long-running daemons, implement Renew with a timer (e.g. renew at 50 minutes).

## CreateScanJob Template: MediaBack for non-duplex

The CreateScanJob template always includes `<wscn:MediaBack>` even for
non-duplex scans. The Samsung M288x (no duplex) accepts this without error,
but other devices may reject it. If a device rejects CreateScanJob with a
validation error, try omitting MediaBack when the input source doesn't support
duplex.

## ScanRegion Dimensions

The DefaultScanTicket returns ScanRegionWidth=0 and ScanRegionHeight=0,
meaning "use the full scan area." When overriding with profile-specific paper
size, set explicit non-zero dimensions. The override_params function in
wsd_scan__structures.py handles this. Both front and back sides must have
matching dimensions (the parser deep-copies front to back when the device
doesn't return a MediaBack element, but override_params originally only
updated the front — this was fixed).

## Image.NONE Sentinel

`wsd_retrieve_image()` returns `Image.NONE` (a non-standard sentinel) when no
images are available, not a real PIL constant. Do not use `is None` to check
for no-images — use `== Image.NONE`. This is a design flaw in the original
codebase. The test_e2e.py script uses `is None` because it uses a simplified
retrieve path.

## Codebase Structure: Flat Imports

All modules use flat imports (`import wsd_common`, not `from package import
wsd_common`). Scripts must run from the `src/` directory. This is tracked as
Phase 2 packaging work. Until fixed, always `cd src/` before running.

## Hardcoded `../log` Directory

The original `wsd_common.py` had `log_path = "../log"` and called `os.mkdir(log_path)`
at import time. This is relative to CWD, so running from any directory outside
the repo causes `PermissionError`. The `log_xml()` function is unused in normal
operation (debug mode prints to stdout). Fix: set `log_path = None` and skip
mkdir when it's None.

## YAML Path Expansion

Python does not expand `~` or `$HOME` in string paths. A YAML profile with
`target_folder: ~/Pictures/scans` will fail with `FileNotFoundError` because
the `~` is treated as a literal directory name. Fix: call
`os.path.expanduser(os.path.expandvars(path))` at profile load time in
`read_profiles_from_yaml()`.

## `ntpath` on Linux

The original `mail_service.py` used `ntpath.basename()` (Windows path module)
on Linux. This works by accident (ntpath and posixpath share basename logic
for simple cases) but is incorrect. Fix: use `os.path.basename()`.

## Silent Startup

The original `start()` function printed only the target URL, then entered a
chain of network operations (probe, Get, profile load, server start) with no
output. If the device is slow or unresponsive, the process appears to hang
silently for up to 100 seconds per request. Fix: print progress at each step
("Discovering device...", "Device found. Getting metadata...", "Loading
profiles...", etc.).

## `sys.exit()` vs `os._exit()` in Signal Handlers

Using `sys.exit(0)` in a SIGINT handler to clean up and quit does not work
when the process has active background threads (e.g. the HTTP server thread).
`sys.exit()` raises `SystemExit`, which propagates up the call stack of the
signal handler — but the main thread is in `time.sleep(1)` and the HTTP server
thread keeps the process alive, so the process hangs after printing "Done."

Fix: use `os._exit(0)` after cleanup. It terminates the process immediately
without giving threads a chance to block.

## Unsubscribe on Shutdown

Ctrl-C (SIGINT) without unsubscribing leaves stale subscription state on the
device. On the Samsung M288x, this causes the device to hang on subsequent
WS-Transfer Get requests — the probe still works, but metadata retrieval
times out (100s). The device may require a physical reboot to recover.

Fix: install a SIGINT/SIGTERM handler that sends WS-Eventing Unsubscribe for
each active subscription before calling `os._exit(0)`. Collect subscription
IDs in a list during the subscribe phase so the handler can iterate them.

## Duplicate All-Events Subscriptions

The original subscription loop called `wsd_scanner_all_events_subscribe()`
inside the per-profile loop, creating N duplicate all-events subscriptions
(one per profile) in addition to N scan-available subscriptions. On the
Samsung, multiple rapid subscriptions invalidate DestinationTokens.

Fix: call `wsd_scanner_all_events_subscribe()` once outside the profile loop,
then call `wsd_scan_available_event_subscribe()` once per profile. Total
subscriptions = 1 + N, not 2N.

## No Error Handling in Network Operations

The original code has no try/except around HTTP requests, scan job creation,
or image retrieval. A single network failure crashes the scan worker thread
silently (threads don't propagate exceptions to the main thread). The scan
worker now has a try/except wrapper that prints errors, but the underlying
operations still lack retry logic.

## WSDScannerMonitor Queue Bugs

The `WSDScannerMonitor` class in `wsd_scan__events.py` has bugs:
- `get_active_jobs()` pulls from `sc_cond_q` instead of `job_status_q`
- `get_job_history()` pulls from `sc_cond_q` instead of `job_ended_q`

These are not blocking for push-scan but would affect any code that monitors
job status via the monitor class.

## Debug Mode

Enable debug mode with `-d` flag on the `start` subcommand. This calls
`wsd_common.enable_debug()` which prints all SOAP requests and responses to
stdout. Essential for debugging protocol issues. Without it, the daemon is
completely silent.

When running in background, redirect stdout to a log file:
`PYTHONUNBUFFERED=1 python wsd-scan.py start ... -d > /tmp/wsd-scan.log 2>&1`
The `PYTHONUNBUFFERED=1` is critical — without it, Python buffers stdout and
you won't see output until the buffer flushes.

## Discovery: HTTP POST Probe, not UDP

The Samsung (and possibly other modern WSD devices) does not respond to
UDP multicast WS-Discovery Probe. It does respond to HTTP POST Probe sent
directly to its WSD endpoint. The discovery code in
`wsd_discovery__operations.py` uses HTTP POST, which works. Don't assume
standard UDP multicast discovery will find your device.
