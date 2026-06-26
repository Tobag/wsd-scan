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

    logger.info("Device found. Getting metadata...")
    (target_info, hosted_services) = wsd_transfer__operations.wsd_get(target_service)

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
            while True:
                time.sleep(1)


def start_server_thread(port=DEFAULT_PORT):
    t = threading.Thread(target=start_server, args=(port,))
    t.start()


def start_server(port=DEFAULT_PORT):
    context = {"queues": wsd_scan__events.QueuesSet()}
    server = wsd_scan__events.HTTPServerWithContext(('', port), wsd_scan__events.RequestHandler, context)
    server.serve_forever()


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

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
