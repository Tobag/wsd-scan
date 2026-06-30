#!/usr/bin/env python3
"""Test the actual wsd-scan discovery + metadata path against the Samsung M288x.
Uses the project's own modules to check if the Probe and WS-Transfer Get work.
"""
import sys
import os

from wsd_scan import wsd_common
from wsd_scan import wsd_globals
from wsd_scan import wsd_discovery__operations
from wsd_scan import wsd_discovery__parsers  # triggers parser registration
from wsd_scan import wsd_transfer__operations

wsd_globals.debug = True

TARGET = "http://192.168.0.149:8018/wsd"

print("=== Testing discovery path ===")
print("Target: %s\n" % TARGET)

# Step 1: Probe
print("--- Step 1: wsd_probe ---")
device = wsd_discovery__operations.wsd_probe(TARGET, 10)
if device is None:
    print("Probe returned None — device did not respond to HTTP POST Probe")
    print("Will need to bypass discovery and go straight to WS-Transfer Get")
    sys.exit(1)

print("Probe succeeded!")
print("  ep_ref_addr: %s" % device.ep_ref_addr)
print("  xaddrs: %s" % device.xaddrs)
print("  types: %s" % device.types)

# Step 2: WS-Transfer Get
print("\n--- Step 2: wsd_get ---")
try:
    target_info, hosted_services = wsd_transfer__operations.wsd_get(device)
    print("Get succeeded!")
    print(str(target_info))
    for hs in hosted_services:
        print(str(hs))
        print()
except Exception as e:
    print("Get failed: %s" % e)
    import traceback
    traceback.print_exc()
