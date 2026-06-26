#!/usr/bin/env python3
"""Minimal end-to-end push-scan test.
Skips discovery (endpoint is known), subscribes ONCE, starts HTTP listener.
"""
import sys
import os
import time
import threading
import copy
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from lxml import etree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import wsd_common
import wsd_globals
import wsd_scan__operations
import wsd_scan__parsers
import wsd_scan__structures
import wsd_scan__events
import wsd_transfer__structures
import yaml

wsd_common.enable_debug()

SCANNER_EP = "http://192.168.0.149:8018/wsd/scan"
LISTEN_ADDR = "http://192.168.0.110:6666/wsd"

# Token store: client_context -> dest_token
tokens = {}
profiles = {}
hosts = {}


def read_profiles():
    result = []
    for f in sorted(os.listdir("./profiles")):
        if f.endswith(".yaml") and f != "mail_service.yaml":
            with open("./profiles/" + f) as yf:
                result.append(yaml.load(yf, Loader=yaml.FullLoader))
    return result


class ScanHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        # Always respond 202
        self.send_response(202)
        self.end_headers()

        xml_tree = etree.fromstring(body)
        if xml_tree is None:
            return

        action_el = wsd_common.xml_find(xml_tree, ".//wsa:Action")
        if action_el is None:
            return
        action = action_el.text or ""
        print("\n[HTTP] Received action: %s" % action)

        if "ScanAvailableEvent" in action:
            self.handle_scan_available(xml_tree)
        else:
            print("[HTTP] Ignoring non-scan event: %s" % action)

    def handle_scan_available(self, xml_tree):
        client_context = wsd_common.xml_find(xml_tree, ".//sca:ClientContext").text
        scan_identifier = wsd_common.xml_find(xml_tree, ".//sca:ScanIdentifier").text
        input_source_el = wsd_common.xml_find(xml_tree, ".//sca:InputSource")
        input_source = input_source_el.text if input_source_el is not None else None

        print("[SCAN] ClientContext=%s ScanId=%s InputSource=%s" % (
            client_context, scan_identifier, input_source))
        print("[SCAN] Token from subscription: %s" % tokens.get(client_context, "NOT FOUND"))

        # Run scan in background thread
        t = threading.Thread(target=self.do_scan, args=(
            client_context, scan_identifier, input_source))
        t.daemon = True
        t.start()

    def do_scan(self, client_context, scan_identifier, input_source):
        dest_token = tokens[client_context]
        profile = profiles[client_context]

        # Build a HostedService object for the scanner
        host = wsd_transfer__structures.HostedService()
        host.ep_ref_addr = SCANNER_EP

        print("[SCAN] Getting scanner elements...")
        description, config, status, std_ticket = wsd_scan__operations.wsd_get_scanner_elements(host)
        print("[SCAN] Scanner state: %s" % status.state)

        # Override with profile params
        std_ticket.override_params(profile)

        # Use the input source from the ScanAvailableEvent
        if input_source is not None:
            std_ticket.doc_params.input_src = input_source
        elif std_ticket.doc_params.input_src == "Auto":
            std_ticket.doc_params.input_src = "ADF"

        print("[SCAN] Override: format=%s input=%s color=%s res=%s" % (
            std_ticket.doc_params.format,
            std_ticket.doc_params.input_src,
            std_ticket.doc_params.front.color,
            std_ticket.doc_params.front.res))

        save_format = profile["image_format"]
        file_name = "scan-" + datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
        image_id = 0
        picture_files = []
        more_images = True

        try:
            while more_images:
                print("[SCAN] Creating scan job (token=%s, scan_id=%s)..." % (dest_token, scan_identifier))
                job = wsd_scan__operations.wsd_create_scan_job(host, std_ticket, scan_identifier, dest_token)
                print("[SCAN] Job created: id=%d" % job.id)

                print("[SCAN] Retrieving image...")
                img = wsd_scan__operations.wsd_retrieve_image(host, job, file_name)

                if img is None:
                    print("[SCAN] No more images.")
                    more_images = False
                    break

                picture_file = "%s/%s_%d.%s" % ("./scans", file_name, image_id, save_format)
                img.save(picture_file, format=save_format, quality=profile["quality"])
                picture_files.append(picture_file)
                print("[SCAN] Saved: %s" % picture_file)
                image_id += 1

                if std_ticket.doc_params.input_src == "Platen":
                    more_images = False

            if picture_files and profile.get("use_pdf", False):
                import img2pdf
                pdf_file = "./scans/%s.pdf" % file_name
                with open(pdf_file, "wb") as f:
                    f.write(img2pdf.convert(picture_files))
                print("[SCAN] PDF saved: %s" % pdf_file)

            print("[SCAN] DONE. %d image(s) saved." % len(picture_files))

        except Exception as e:
            print("[SCAN] ERROR: %s" % e)
            import traceback
            traceback.print_exc()

    def log_message(self, format, *args):
        pass  # Suppress default logging


def main():
    print("=== Minimal push-scan test ===")
    print("Scanner: %s" % SCANNER_EP)
    print("Listen:  %s" % LISTEN_ADDR)
    print()

    # Load profiles
    profs = read_profiles()
    print("Loaded %d profiles:" % len(profs))
    for p in profs:
        print("  %s (id=%s, format=%s, res=%d)" % (
            p["name"], p["id"], p.get("format", "?"), p["resolution"]))
    print()

    # Build HostedService
    host = wsd_transfer__structures.HostedService()
    host.ep_ref_addr = SCANNER_EP

    # Get scanner elements to verify connectivity
    print("Getting scanner elements...")
    description, config, status, std_ticket = wsd_scan__operations.wsd_get_scanner_elements(host)
    print("Scanner state: %s" % status.state)
    print("Formats: %s" % config.settings.formats)
    print()

    # Subscribe to all scanner events
    print("Subscribing to all scanner events...")
    wsd_scan__events.wsd_scanner_all_events_subscribe(host, LISTEN_ADDR)
    print()

    # Subscribe to ScanAvailableEvent for each profile (ONCE)
    for profile in profs:
        ctx = profile["id"]
        print("Subscribing profile '%s' (context=%s)..." % (profile["name"], ctx))
        result = wsd_scan__events.wsd_scan_available_event_subscribe(
            host, profile["name"], ctx, LISTEN_ADDR)
        if result is False:
            print("  FAILED!")
            continue
        sub_id, dest_token = result
        print("  Token: %s" % dest_token)
        tokens[ctx] = dest_token
        profiles[ctx] = profile
        hosts[ctx] = host
    print()

    # Start HTTP listener
    print("Starting HTTP listener on port 6666...")
    server = HTTPServer(("", 6666), ScanHandler)
    print("Listening. Walk up to the printer and select a profile!")
    print("Press Ctrl+C to stop.")
    print()
    server.serve_forever()


if __name__ == "__main__":
    main()
