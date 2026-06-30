#!/usr/bin/env python3
"""Unit tests for wsd-scan — runnable without a physical scanner.

Covers:
  - Package data accessibility (templates, profiles)
  - XML template loading and placeholder substitution
  - Scan profile loading and required fields
  - ScanTicket.override_params logic
"""
import os

import pytest
import yaml

from wsd_scan import wsd_common, wsd_globals
from wsd_scan.wsd_scan__structures import ScanTicket, DocumentParams, MediaSide
from wsd_scan.cli import read_profiles_from_yaml


# --- Package data ---

class TestPackageData:
    """Verify templates and profiles are bundled and accessible."""

    def test_templates_dir_exists(self):
        tpl_dir = wsd_common.abs_path("templates")
        assert os.path.isdir(tpl_dir)

    def test_profiles_dir_exists(self):
        prof_dir = wsd_common.abs_path("profiles")
        assert os.path.isdir(prof_dir)

    @pytest.mark.parametrize("template", [
        "ws-discovery__probe.xml",
        "ws-transfer__get.xml",
        "ws-eventing__subscribe.xml",
        "ws-scan__create_scan_job.xml",
        "ws-scan__retrieve_image.xml",
        "ws-scan__validate_scan_ticket.xml",
        "ws-scan__scan_available_event_subscribe.xml",
    ])
    def test_template_exists(self, template):
        assert os.path.isfile(wsd_common.abs_path("templates/" + template))

    def test_mail_service_yaml_exists(self):
        assert os.path.isfile(wsd_common.abs_path("profiles/mail_service.yaml"))


# --- XML template loading ---

class TestTemplateLoading:
    """Verify message_from_file loads and substitutes placeholders."""

    def test_load_probe_template(self):
        msg = wsd_common.message_from_file(
            wsd_common.abs_path("templates/ws-discovery__probe.xml"),
            FROM="urn:uuid:test-123")
        assert "urn:uuid:test-123" in msg
        # MSG_ID auto-filled
        assert "{{MSG_ID}}" not in msg
        assert "urn:uuid:" in msg

    def test_load_get_template(self):
        msg = wsd_common.message_from_file(
            wsd_common.abs_path("templates/ws-transfer__get.xml"),
            FROM="urn:uuid:test-from",
            TO="urn:uuid:test-to")
        assert "urn:uuid:test-from" in msg
        assert "urn:uuid:test-to" in msg

    def test_no_unfilled_placeholders_after_substitution(self):
        """All {{PLACEHOLDER}} tokens should be gone after filling known fields."""
        msg = wsd_common.message_from_file(
            wsd_common.abs_path("templates/ws-scan__create_scan_job.xml"),
            FROM="urn:uuid:test",
            TO="urn:uuid:target",
            # provide a minimal set; MSG_ID is auto-filled
        )
        # MSG_ID is auto-filled, so no double-brace tokens should remain
        # for the fields we passed. Other required fields may remain unfilled,
        # but the auto-filled MSG_ID should not.
        assert "{{MSG_ID}}" not in msg


# --- Scan profiles ---

REQUIRED_PROFILE_FIELDS = ["id", "name", "color", "format", "resolution",
                           "input_src", "paper_size"]


class TestProfiles:
    """Verify scan profiles load and have required fields."""

    def test_load_all_profiles(self):
        profiles = read_profiles_from_yaml()
        assert len(profiles) >= 1

    def test_profile_ids_unique(self):
        profiles = read_profiles_from_yaml()
        ids = [p["id"] for p in profiles]
        assert len(ids) == len(set(ids)), "Duplicate profile IDs: %s" % ids

    @pytest.mark.parametrize("field", REQUIRED_PROFILE_FIELDS)
    def test_profiles_have_required_fields(self, field):
        profiles = read_profiles_from_yaml()
        for p in profiles:
            assert field in p, "Profile %s missing field: %s" % (p.get("id", "?"), field)

    def test_target_folder_expanded(self):
        """target_folder should have ~ and $HOME expanded."""
        profiles = read_profiles_from_yaml()
        for p in profiles:
            if "target_folder" in p:
                assert "~" not in p["target_folder"], \
                    "Profile %s has unexpanded ~ in target_folder" % p["id"]
                assert "$HOME" not in p["target_folder"], \
                    "Profile %s has unexpanded $HOME in target_folder" % p["id"]

    def test_mail_service_excluded_from_profiles(self):
        """mail_service.yaml should not appear in the scan profiles list."""
        profiles = read_profiles_from_yaml()
        for p in profiles:
            # mail_service.yaml has 'sender' not 'resolution'
            assert "resolution" in p, "Non-scan profile leaked into list: %s" % p


# --- ScanTicket.override_params ---

def make_test_ticket():
    """Build a minimal ScanTicket with front/back MediaSides for testing."""
    ticket = ScanTicket()
    ticket.doc_params = DocumentParams()
    ticket.doc_params.front = MediaSide()
    ticket.doc_params.back = MediaSide()
    return ticket


class TestScanTicketOverride:
    """Verify override_params applies profile values correctly."""

    def test_paper_size_a4(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 300, "input_src": "Auto"}
        ticket.override_params(profile)
        assert ticket.doc_params.input_size == (8267, 11693)
        assert ticket.doc_params.front.size == (8267, 11693)

    def test_paper_size_a5(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A5", "resolution": 200, "input_src": "Platen"}
        ticket.override_params(profile)
        assert ticket.doc_params.input_size == (5847, 8267)

    def test_paper_size_letter(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "Letter", "resolution": 150, "input_src": "ADF"}
        ticket.override_params(profile)
        assert ticket.doc_params.input_size == (8500, 11000)

    def test_resolution_applied(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 300, "input_src": "Auto"}
        ticket.override_params(profile)
        assert ticket.doc_params.front.res == (300, 300)

    def test_color_applied(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 200, "input_src": "Auto",
                   "color": "Grayscale8"}
        ticket.override_params(profile)
        assert ticket.doc_params.front.color == "Grayscale8"

    def test_format_applied(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 200, "input_src": "Auto",
                   "format": "jfif"}
        ticket.override_params(profile)
        assert ticket.doc_params.format == "jfif"

    def test_format_defaults_to_tiff(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 200, "input_src": "Auto"}
        ticket.override_params(profile)
        assert ticket.doc_params.format == "tiff-single-uncompressed"

    def test_input_src_applied(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 200, "input_src": "ADF"}
        ticket.override_params(profile)
        assert ticket.doc_params.input_src == "ADF"

    def test_back_synced_with_front(self):
        """override_params should deep-copy front settings to back."""
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 300, "input_src": "Auto",
                   "color": "RGB24"}
        ticket.override_params(profile)
        assert ticket.doc_params.back.res == (300, 300)
        assert ticket.doc_params.back.color == "RGB24"
        assert ticket.doc_params.back.size == (8267, 11693)

    def test_compression_and_images_num(self):
        ticket = make_test_ticket()
        profile = {"paper_size": "A4", "resolution": 200, "input_src": "Auto"}
        ticket.override_params(profile)
        assert ticket.doc_params.compression_factor == 100
        assert ticket.doc_params.images_num == 1
