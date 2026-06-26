#!/usr/bin/env python3
"""Test the subscribe + GetScannerElements + CreateScanJob path against the Samsung M288x.
This verifies the full push-scan setup short of actually pressing the scan button.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wsd_common
import wsd_globals
import wsd_discovery__operations
import wsd_discovery__parsers
import wsd_transfer__operations
import wsd_transfer__structures
import wsd_scan__events
import wsd_scan__operations
import wsd_scan__parsers
import wsd_scan__structures
import yaml

wsd_globals.debug = True

TARGET = "http://192.168.0.149:8018/wsd"
SELF_IP = "192.168.0.110"
LISTEN_ADDR = "http://%s:6666/wsd" % SELF_IP


def read_profiles():
    profiles = []
    for f in os.listdir("./profiles"):
        if f.endswith(".yaml") and f != "mail_service.yaml":
            with open("./profiles/" + f) as yf:
                profiles.append(yaml.load(yf, Loader=yaml.FullLoader))
    return profiles


def main():
    print("=== Testing push-scan setup ===\n")

    # Step 1: Discovery + metadata
    print("--- Step 1: Discovery ---")
    device = wsd_discovery__operations.get_device(TARGET)
    if device is None:
        print("Discovery failed!")
        sys.exit(1)
    target_info, hosted_services = wsd_transfer__operations.wsd_get(device)
    print("Discovery OK: %s\n" % target_info.model_name)

    # Find scanner service
    scan_service = None
    for hs in hosted_services:
        if "wscn:ScannerServiceType" in hs.types:
            scan_service = hs
            break
    if scan_service is None:
        print("No scanner service found!")
        sys.exit(1)
    print("Scanner service: %s\n" % scan_service.ep_ref_addr)

    # Step 2: GetScannerElements
    print("--- Step 2: GetScannerElements ---")
    description, config, status, std_ticket = wsd_scan__operations.wsd_get_scanner_elements(scan_service)
    print("Scanner state: %s" % status.state)
    print("Formats: %s" % config.settings.formats)
    print("Platen res: %s" % config.platen.width_res if config.platen else "no platen")
    print("ADF duplex: %s" % config.adf_duplex)
    print()

    # Step 3: Load profiles and test override
    print("--- Step 3: Profile override ---")
    profiles = read_profiles()
    for profile in profiles:
        print("Profile: %s (id=%s)" % (profile["name"], profile["id"]))
        print("  format=%s, image_format=%s, res=%d, color=%s, input=%s" % (
            profile.get("format", "MISSING"), profile["image_format"],
            profile["resolution"], profile["color"], profile["input_src"]))

        # Test override on a fresh copy of the default ticket
        import copy
        ticket = copy.deepcopy(std_ticket)
        ticket.override_params(profile)
        print("  After override: format=%s, input_src=%s, front_color=%s, front_res=%s" % (
            ticket.doc_params.format,
            ticket.doc_params.input_src,
            ticket.doc_params.front.color,
            ticket.doc_params.front.res))
        if ticket.doc_params.back:
            print("  Back synced: color=%s, res=%s" % (
                ticket.doc_params.back.color, ticket.doc_params.back.res))
        print()

    # Step 4: Subscribe to ScanAvailableEvent for each profile
    print("--- Step 4: Subscribe to ScanAvailableEvent ---")
    for profile in profiles:
        client_context = profile["id"]
        print("Subscribing profile '%s' (context=%s)..." % (profile["name"], client_context))
        # First subscribe to all scanner events
        all_events_sub = wsd_scan__events.wsd_scanner_all_events_subscribe(scan_service, LISTEN_ADDR)
        print("  All-events subscription: %s" % all_events_sub)

        # Subscribe to ScanAvailableEvent
        result = wsd_scan__events.wsd_scan_available_event_subscribe(
            scan_service, profile["name"], client_context, LISTEN_ADDR)
        if result is False:
            print("  ScanAvailableEvent subscribe FAILED!")
            continue
        subscription_id, dest_token = result
        print("  Subscription ID: %s" % subscription_id)
        print("  Destination token: %s" % dest_token)

        # Store for the event handler
        wsd_scan__events.profile_map[client_context] = profile
        wsd_scan__events.token_map[client_context] = dest_token
        wsd_scan__events.host_map[client_context] = scan_service
        print()

    print("=== Setup complete ===")
    print("Profiles are pushed to the device. Walk up to the printer panel,")
    print("select Scan to WSD, and choose a profile to trigger a scan.")


if __name__ == "__main__":
    main()
