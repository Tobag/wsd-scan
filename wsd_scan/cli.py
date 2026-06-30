import argparse
import logging
import os
import signal
import threading
import time

import yaml

from . import wsd_common
from . import wsd_discovery__operations
from . import wsd_globals
from . import wsd_scan__events
from . import wsd_transfer__operations
from . import wsd_discovery__parsers
from . import wsd_eventing__operations

logger = logging.getLogger("wsd_scan")

DEFAULT_PORT = 6666


def noop(args):
    logger.info("Nothing to do")


def read_profiles_from_yaml():
    from os import walk

    excluded_files = ["mail_service.yaml"]
    profiles_dir = wsd_common.abs_path("profiles")

    files = []
    for (dirpath, dirnames, filenames) in walk(profiles_dir):
        files.extend(filenames)
        break

    profiles = []
    for file in files:
        if file not in excluded_files:
            with open(profiles_dir + "/" + file) as yaml_file:
                yaml_object = yaml.load(yaml_file, Loader=yaml.FullLoader)
                # Expand ~ and $HOME in target_folder so users can write
                # either absolute paths, ~/Pictures/scans, or $HOME/Pictures/scans
                if "target_folder" in yaml_object:
                    yaml_object["target_folder"] = os.path.expandvars(
                        os.path.expanduser(yaml_object["target_folder"]))
                profiles.append(yaml_object)
                yaml_file.close()

    return profiles


def start(args):
    if args.debug:
        wsd_common.enable_debug()
        logging.getLogger("wsd_scan").setLevel(logging.DEBUG)

    port = args.port

    if args.auto:
        scanners = wsd_discovery__operations.auto_discover_scanners(timeout=5)
        if not scanners:
            logger.error("No WSD scanners found on the network. Use -t to specify target manually.")
            return
        if len(scanners) == 1:
            target_service = scanners[0]
            logger.info("Auto-discovered scanner: %s", target_service.ep_ref_addr)
        else:
            logger.info("Found %d scanners:", len(scanners))
            for i, s in enumerate(scanners):
                logger.info("  [%d] %s", i, s.ep_ref_addr)
            target_service = scanners[0]
            logger.info("Using first scanner: %s", target_service.ep_ref_addr)
    else:
        if not args.target:
            logger.error("Either --auto or --target is required.")
            return
        logger.info("Target: %s", args.target)
        logger.info("Discovering device...")
        target_service = wsd_discovery__operations.get_device(args.target)
        if target_service is None:
            logger.error("Device not found at %s", args.target)
            return
        # Use the provided URL directly for transport — the device may
        # advertise XAddrs (e.g. secondary interfaces) that are unreachable,
        # causing timeouts. We know this URL works; don't let the probe
        # response override it.
        target_service.xaddrs = {args.target}

    logger.info("Device found. Getting metadata...")
    try:
        (target_info, hosted_services) = wsd_transfer__operations.wsd_get(target_service)
    except StopIteration:
        logger.error("Device did not respond to WS-Transfer Get. It may need a reboot.")
        return

    logger.info("Loading profiles...")
    wsd_globals.scan_profiles = read_profiles_from_yaml()
    logger.info("Loaded %d profile(s).", len(wsd_globals.scan_profiles))

    logger.info("Starting HTTP listener on port %d...", port)
    start_server_thread(port)

    for hosted_service in hosted_services:
        if "wscn:ScannerServiceType" in hosted_service.types:
            listen_addr = "http://%s:%d/wsd" % (args.self, port)

            subscription_ids = []

            def cleanup_on_exit(sig, frame):
                logger.info("Unsubscribing from device...")
                for sub_id in subscription_ids:
                    try:
                        wsd_eventing__operations.wsd_unsubscribe(hosted_service, sub_id)
                    except Exception:
                        pass
                logger.info("Done. Exiting.")
                os._exit(0)

            signal.signal(signal.SIGINT, cleanup_on_exit)
            signal.signal(signal.SIGTERM, cleanup_on_exit)

            logger.info("Pushing profiles to device...")

            # One all-events subscription (status, job events, etc.)
            all_events_sub = wsd_scan__events.wsd_scanner_all_events_subscribe(hosted_service, listen_addr)
            subscription_ids.append(all_events_sub)

            # One scan-available subscription per profile (creates panel entries)
            for profile in wsd_globals.scan_profiles:
                client_context = profile["id"]
                sub_id, dest_token = wsd_scan__events.wsd_scan_available_event_subscribe(hosted_service,
                                                                       profile["name"],
                                                                       client_context,
                                                                       listen_addr)
                subscription_ids.append(sub_id)
                if dest_token is not None:
                    wsd_scan__events.profile_map[client_context] = profile
                    wsd_scan__events.token_map[client_context] = dest_token
                    wsd_scan__events.host_map[client_context] = hosted_service

            # Subscribe once, then keep the process alive.
            # Subscriptions last 1 hour (PT1H). TODO: use WS-Eventing Renew
            # before expiry instead of re-subscribing from scratch.
            logger.info("Profiles pushed. Waiting for scan events on port %d...", port)

            # Profile hot-reload: poll profiles dir for changes
            profiles_dir = wsd_common.abs_path("profiles")
            last_mtime = os.path.getmtime(profiles_dir)

            while True:
                time.sleep(2)
                try:
                    current_mtime = os.path.getmtime(profiles_dir)
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        logger.info("Profiles changed, reloading...")
                        new_profiles = read_profiles_from_yaml()
                        wsd_globals.scan_profiles = new_profiles
                        for p in new_profiles:
                            ctx = p["id"]
                            if ctx in wsd_scan__events.profile_map:
                                wsd_scan__events.profile_map[ctx] = p
                                logger.info("Updated profile: %s", ctx)
                        logger.info("Profile reload complete (%d profiles).", len(new_profiles))
                except Exception as e:
                    logger.debug("Profile reload check failed: %s", e)


def start_server_thread(port=DEFAULT_PORT):
    t = threading.Thread(target=start_server, args=(port,))
    t.start()


def start_server(port=DEFAULT_PORT):
    context = {"queues": wsd_scan__events.QueuesSet()}
    server = wsd_scan__events.HTTPServerWithContext(('', port), wsd_scan__events.RequestHandler, context)
    server.serve_forever()


def list_devices(args):
    logger.info("Scanning for WSD devices on the network (timeout %ds)...", args.timeout)
    scanners = wsd_discovery__operations.auto_discover_scanners(timeout=args.timeout)
    if not scanners:
        print("No WSD scanners found.")
        return
    print("Found %d scanner(s):" % len(scanners))
    for i, s in enumerate(scanners):
        print("  [%d] %s" % (i, s.ep_ref_addr))
        if s.xaddrs:
            print("      XAddrs: %s" % ', '.join(s.xaddrs))


def list_profiles(args):
    profiles = read_profiles_from_yaml()
    if not profiles:
        print("No profiles found.")
        return
    print("Loaded %d profile(s):" % len(profiles))
    for p in profiles:
        print()
        print("  ID:          %s" % p.get("id", "?"))
        print("  Name:        %s" % p.get("name", "?"))
        print("  Format:      %s" % p.get("format", "?"))
        print("  Resolution:  %s dpi" % p.get("resolution", "?"))
        print("  Color:       %s" % p.get("color", "?"))
        print("  Input src:   %s" % p.get("input_src", "?"))
        print("  Paper size:  %s" % p.get("paper_size", "?"))
        print("  Target dir:  %s" % p.get("target_folder", "?"))
        print("  PDF:         %s" % p.get("use_pdf", "?"))
        print("  Email:       %s" % p.get("send_email", "?"))


def test_connection(args):
    if not args.target:
        logger.error("--target is required for test-connection.")
        return
    logger.info("Probing %s ...", args.target)
    target_service = wsd_discovery__operations.get_device(args.target)
    if target_service is None:
        print("FAILED: Device not found at %s" % args.target)
        return
    print("Device found: %s" % target_service.ep_ref_addr)
    if target_service.xaddrs:
        print("XAddrs: %s" % ', '.join(target_service.xaddrs))
    try:
        result = wsd_transfer__operations.wsd_get(target_service)
    except StopIteration:
        print("FAILED: Device did not respond to WS-Transfer Get. It may need a reboot.")
        return
    if result is False:
        print("FAILED: Device did not respond to WS-Transfer Get.")
        return
    (target_info, hosted_services) = result
    print()
    print(target_info)
    print("Hosted services:")
    for hs in hosted_services:
        if "wscn:ScannerServiceType" in hs.types:
            print("  [SCANNER] %s" % hs.ep_ref_addr)
        else:
            print("  [other]   %s (%s)" % (hs.ep_ref_addr, ', '.join(hs.types)))
    has_scanner = any("wscn:ScannerServiceType" in hs.types for hs in hosted_services)
    print()
    if has_scanner:
        print("OK: Device has a scanner service. Ready for 'wsd-scan start'.")
    else:
        print("WARNING: Device has no scanner service.")


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    parser = argparse.ArgumentParser(description='WSD Scan — push-scan receiver')
    parser.set_defaults(func=noop)
    subparsers = parser.add_subparsers()

    start_parser = subparsers.add_parser("start", help="Start the scan receiver")
    start_parser.add_argument('-t', '--target', action="store", default=None, type=str,
                              help="WSD endpoint URL of the scanner (e.g. http://192.168.0.149:8018/wsd). "
                                   "Required unless --auto is used.")
    start_parser.add_argument('-s', '--self', action="store", required=True, type=str,
                              help="Local IP the scanner can reach (e.g. 192.168.0.110)")
    start_parser.add_argument('-p', '--port', action="store", type=int, default=DEFAULT_PORT,
                              help="HTTP listener port (default: %d)" % DEFAULT_PORT)
    start_parser.add_argument('--auto', action="store_true", default=False,
                              help="Auto-discover WSD scanners via UDP multicast (no -t needed)")
    start_parser.add_argument('-d', '--debug', action="store_true", default=False,
                              help="Enable debug output (SOAP exchanges)")
    start_parser.set_defaults(func=start)

    # list-devices: discover WSD scanners on the network
    ld_parser = subparsers.add_parser("list-devices", help="Discover WSD scanners on the local network")
    ld_parser.add_argument('--timeout', action="store", type=int, default=5,
                           help="Discovery timeout in seconds (default: 5)")
    ld_parser.set_defaults(func=list_devices)

    # list-profiles: show loaded scan profiles
    subparsers.add_parser("list-profiles", help="List available scan profiles").set_defaults(func=list_profiles)

    # test-connection: probe a device and verify it has a scanner service
    tc_parser = subparsers.add_parser("test-connection", help="Test connection to a WSD scanner")
    tc_parser.add_argument('-t', '--target', action="store", required=True, type=str,
                           help="WSD endpoint URL of the scanner (e.g. http://192.168.0.149:8018/wsd)")
    tc_parser.set_defaults(func=test_connection)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
