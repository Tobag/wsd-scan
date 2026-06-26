#!/usr/bin/env python3
"""Quick verification that package data is accessible."""
import os
from wsd_scan import wsd_common

tpl = wsd_common.abs_path("templates/ws-scan__create_scan_job.xml")
prof = wsd_common.abs_path("profiles/scan_profile_lq.yaml")
print("Template exists:", os.path.exists(tpl), tpl)
print("Profile exists:", os.path.exists(prof), prof)
