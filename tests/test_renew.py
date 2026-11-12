"""
Unit tests for subscription renewal and the active-scan counter.

No physical scanner required: the WS-Eventing calls are replaced with fakes.
"""

import pytest

from wsd_scan import cli, wsd_scan__events


class TestRenewAll:
    def test_all_subscriptions_renewed(self, monkeypatch):
        calls = []

        def renew(host, sub_id, expiration=None):
            calls.append((sub_id, expiration))
            return True

        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_renew", renew)
        assert cli._renew_all("host", ["sub-a", "sub-b"]) == "ok"
        assert calls == [("sub-a", cli.RENEW_EXPIRES), ("sub-b", cli.RENEW_EXPIRES)]

    def test_fault_from_device(self, monkeypatch):
        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_renew", lambda host, sub_id, expiration=None: False)
        assert cli._renew_all("host", ["sub-a"]) == "fault"

    def test_device_unreachable(self, monkeypatch):
        def renew(host, sub_id, expiration=None):
            raise OSError("no route to host")

        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_renew", renew)
        assert cli._renew_all("host", ["sub-a"]) == "unreachable"


class TestSubscriptionAlive:
    def test_known_subscription(self, monkeypatch):
        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_get_status", lambda host, sub_id: None)
        assert cli._subscription_alive("host", "sub-a") is True

    def test_unknown_subscription(self, monkeypatch):
        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_get_status", lambda host, sub_id: False)
        assert cli._subscription_alive("host", "sub-a") is False

    def test_device_unreachable(self, monkeypatch):
        def status(host, sub_id):
            raise OSError("timed out")

        monkeypatch.setattr(cli.wsd_eventing__operations, "wsd_get_status", status)
        assert cli._subscription_alive("host", "sub-a") is None


class TestActiveScans:
    def test_counter_returns_to_zero_after_an_error(self):
        with pytest.raises(KeyError):
            wsd_scan__events.device_initiated_scan_worker("no-such-profile", "scan-1", "scan")
        assert wsd_scan__events.active_scans() == 0
