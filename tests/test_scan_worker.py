"""
Scan worker against a fake device: one scan job for the whole ADF, a single image for the platen.

No physical scanner required.
"""

import os
import re

import pytest
from PIL import Image

from wsd_scan import wsd_scan__events, wsd_scan__operations
from wsd_scan.wsd_scan__structures import ScanTicket, DocumentParams, MediaSide


def make_ticket():
    ticket = ScanTicket()
    ticket.doc_params = DocumentParams()
    ticket.doc_params.front = MediaSide()
    ticket.doc_params.back = MediaSide()
    return ticket


class FakeDevice:
    """Hands out `pages` images per scan job, then Image.NONE (ClientErrorNoImagesAvailable)."""

    def __init__(self, pages):
        self.pages = pages
        self.jobs = []
        self.retrieved = 0

    def get_scanner_elements(self, host):
        return None, None, None, make_ticket()

    def create_scan_job(self, host, ticket, scan_identifier, dest_token):
        self.jobs.append(ticket.doc_params.images_num)
        return object()

    def retrieve_image(self, host, job, file_name):
        self.retrieved += 1
        if self.retrieved > self.pages:
            return Image.NONE
        return Image.new("RGB", (40, 60), "white")


@pytest.fixture
def device(monkeypatch):
    def make(pages):
        fake = FakeDevice(pages)
        monkeypatch.setattr(wsd_scan__operations, "wsd_get_scanner_elements", fake.get_scanner_elements)
        monkeypatch.setattr(wsd_scan__operations, "wsd_create_scan_job", fake.create_scan_job)
        monkeypatch.setattr(wsd_scan__operations, "wsd_retrieve_image", fake.retrieve_image)
        return fake
    return make


def make_profile(target, **extra):
    profile = {"id": "test", "name": "Test", "color": "RGB24", "format": "jfif", "image_format": "jpeg",
               "quality": 70, "target_folder": str(target), "send_email": False, "use_pdf": True,
               "paper_size": "A4", "resolution": 200, "input_src": "Auto"}
    profile.update(extra)
    return profile


def scan(monkeypatch, profile, input_source):
    monkeypatch.setitem(wsd_scan__events.host_map, "test", "host")
    monkeypatch.setitem(wsd_scan__events.token_map, "test", "token")
    monkeypatch.setitem(wsd_scan__events.profile_map, "test", profile)
    wsd_scan__events.device_initiated_scan_worker("test", "scan-1", "scan", input_source)


def pdf_pages(path):
    with open(path, "rb") as f:
        return len(re.findall(rb"/Type\s*/Page\b", f.read()))


class TestMultiPage:
    def test_adf_fetches_all_pages_from_one_job(self, monkeypatch, device, tmp_path):
        fake = device(pages=3)
        scan(monkeypatch, make_profile(tmp_path), "ADF")
        assert fake.jobs == [0]                       # one job, ImagesToTransfer 0 = until the feeder is empty
        assert pdf_pages(str(tmp_path / "scan.pdf")) == 3

    def test_platen_takes_a_single_image(self, monkeypatch, device, tmp_path):
        fake = device(pages=3)
        scan(monkeypatch, make_profile(tmp_path), "Platen")
        assert fake.jobs == [1]
        assert fake.retrieved == 1
        assert pdf_pages(str(tmp_path / "scan.pdf")) == 1

    def test_images_kept_without_pdf(self, monkeypatch, device, tmp_path):
        device(pages=2)
        scan(monkeypatch, make_profile(tmp_path, use_pdf=False), "ADF")
        assert sorted(os.listdir(str(tmp_path))) == ["scan_0.jpeg", "scan_1.jpeg"]
