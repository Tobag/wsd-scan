import threading
import time
import argparse
import signal
import sys
import yaml

from . import wsd_common
from . import wsd_discovery__operations
from . import wsd_globals
from . import wsd_scan__events
from . import wsd_transfer__operations
from . import wsd_discovery__parsers
from . import wsd_eventing__operations

def noop(args):
    print("Nothing to do")


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
                profiles.append(yaml_object)
                yaml_file.close()

    return profiles


def start(args):
    if args.debug:
        wsd_common.enable_debug()
    print(args.target)

    print("Discovering device...")
    target_service = wsd_discovery__operations.get_device(args.target)
    if target_service is None:
        print("ERROR: Device not found at %s" % args.target)
        return
    print("Device found. Getting metadata...")
    (target_info, hosted_services) = wsd_transfer__operations.wsd_get(target_service)

    print("Loading profiles...")
    wsd_globals.scan_profiles = read_profiles_from_yaml()
    print("Loaded %d profile(s)." % len(wsd_globals.scan_profiles))

    print("Starting HTTP listener on port 6666...")
    start_server_thread()

    for hosted_service in hosted_services:
        if "wscn:ScannerServiceType" in hosted_service.types:
            listen_addr = "http://"+args.self+":6666/wsd"

            subscription_ids = []

            def cleanup_on_exit(sig, frame):
                print("\nUnsubscribing from device...")
                for sub_id in subscription_ids:
                    try:
                        wsd_eventing__operations.wsd_unsubscribe(hosted_service, sub_id)
                    except Exception:
                        pass
                print("Done.")
                sys.exit(0)

            signal.signal(signal.SIGINT, cleanup_on_exit)
            signal.signal(signal.SIGTERM, cleanup_on_exit)

            print("Pushing profiles to device...")
            for profile in wsd_globals.scan_profiles:
                client_context = profile["id"]
                sub_id = wsd_scan__events.wsd_scanner_all_events_subscribe(hosted_service, listen_addr)
                subscription_ids.append(sub_id)
                _, dest_token = wsd_scan__events.wsd_scan_available_event_subscribe(hosted_service,
                                                                       profile["name"],
                                                                       client_context,
                                                                       listen_addr)
                if dest_token is not None:
                    wsd_scan__events.profile_map[client_context] = profile
                    wsd_scan__events.token_map[client_context] = dest_token
                    wsd_scan__events.host_map[client_context] = hosted_service

            # Subscribe once, then keep the process alive.
            # Subscriptions last 1 hour (PT1H). TODO: use WS-Eventing Renew
            # before expiry instead of re-subscribing from scratch.
            print("Profiles pushed. Waiting for scan events...")
            while True:
                time.sleep(1)


def start_server_thread():
    t = threading.Thread(target=start_server)
    t.start()


def start_server():
    print("Starting server...")
    context = {"queues": wsd_scan__events.QueuesSet()}
    server = wsd_scan__events.HTTPServerWithContext(('', 6666), wsd_scan__events.RequestHandler, context)
    server.serve_forever()


def main():
    help_filter = "Help..."

    parser = argparse.ArgumentParser(description='WSD Scan')

    parser.set_defaults(func=noop)
    subparsers = parser.add_subparsers()

    list_parser = subparsers.add_parser("start")
    list_parser.add_argument('-t', '--target', action="store", required=True, type=str, help=help_filter)
    list_parser.add_argument('-s', '--self', action="store", required=True, type=str, help=help_filter)
    list_parser.add_argument('-d', '--debug', action="store_true", default=False, help="Enable debug output")
    list_parser.set_defaults(func=start)

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()