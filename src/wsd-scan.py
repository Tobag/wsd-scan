import argparse
import yaml

import wsd_discovery__operations
import wsd_globals
import wsd_scan__events
import wsd_transfer__operations
import wsd_discovery__parsers

def noop(args):
    print("Nothing to do")


def read_profiles_from_yaml():
    from os import walk

    excluded_files = ["mail_service.yaml"]

    files = []
    for (dirpath, dirnames, files) in walk("./profiles"):
        files.extend(files)
        break

    profiles = []
    for file in files:
        if file not in excluded_files:
            with open("./profiles/"+file) as yaml_file:
                yaml_object = yaml.load(yaml_file, Loader=yaml.FullLoader)
                profiles.append(yaml_object)
                yaml_file.close()

    return profiles


def start(args):
    print(args.target)

    target_service = wsd_discovery__operations.get_device(args.target)
    (target_info, hosted_services) = wsd_transfer__operations.wsd_get(target_service)

    wsd_globals.scan_profiles = read_profiles_from_yaml()

    for hosted_service in hosted_services:
        if "wscn:ScannerServiceType" in hosted_service.types:
            listen_addr = "http://"+args.self+":6666/wsd"

            for profile in wsd_globals.scan_profiles:
                client_context = profile["id"]
                wsd_scan__events.wsd_scanner_all_events_subscribe(hosted_service, listen_addr)
                _, dest_token = wsd_scan__events.wsd_scan_available_event_subscribe(hosted_service,
                                                                       profile["name"],
                                                                       client_context,
                                                                       listen_addr)
                if dest_token is not None:
                    wsd_scan__events.profile_map[client_context] = profile
                    wsd_scan__events.token_map[client_context] = dest_token
                    wsd_scan__events.host_map[client_context] = hosted_service

            break

    server = wsd_scan__events.HTTPServerWithContext(('', 6666), wsd_scan__events.RequestHandler, "context")
    server.serve_forever()

def main():
    help_filter = "Help..."

    parser = argparse.ArgumentParser(description='WSD Scan')

    parser.set_defaults(func=noop)
    subparsers = parser.add_subparsers()

    list_parser = subparsers.add_parser("start")
    list_parser.add_argument('-t', '--target', action="store", required=True, type=str, help=help_filter)
    list_parser.add_argument('-s', '--self', action="store", required=True, type=str, help=help_filter)
    list_parser.set_defaults(func=start)

    args = parser.parse_args()

    args.func(args)


if __name__ == "__main__":
    main()