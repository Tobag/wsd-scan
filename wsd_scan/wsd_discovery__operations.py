#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import logging
import os
import pickle
import select
import socket
import sqlite3
import struct
import typing

import lxml.etree as etree

from . import wsd_common, \
    wsd_discovery__structures, \
    wsd_discovery__parsers, \
    wsd_transfer__operations, \
    wsd_globals

logger = logging.getLogger("wsd_scan")

discovery_verbosity = 10

wsd_mcast_v4 = '239.255.255.250'
wsd_mcast_v6 = 'FF02::C'
wsd_udp_port = 3702

db_path = os.environ.get("WSD_CACHE_PATH", "")


def send_unicast_soap_msg(target_address: str, xml_template: str,
                          fields_map: typing.Dict[str, str]) \
        -> typing.Union[str, None]:
    message = wsd_common.message_from_file(wsd_common.abs_path("templates/%s" % xml_template),
                                           **fields_map)

    op_name = " ".join(xml_template.split("__")[1].split(".")[0].split("_")).upper()

    if wsd_globals.debug:
        r = etree.fromstring(message.encode("ASCII"), parser=wsd_common.parser)
        logger.debug("##\n## %s\n##\n%s", op_name,
                     etree.tostring(r, pretty_print=True, xml_declaration=True).decode("ASCII"))

    return wsd_common.soap_post_unicast(target_address, message)


def wsd_probe(target_address: str, probe_timeout: int = 3) \
        -> wsd_discovery__structures.TargetService:
    """
    Send a multicast discovery probe message, and wait for wsd-enabled devices to respond.

    :param probe_timeout: the number of seconds to wait for probe replies
    :type probe_timeout: int
    :param type_filter: a set of legal strings, each representing a device class
    :type type_filter: {str}
    :return: a set of wsd targets
    :rtype: {wsd_discovery__structures.TargetService}
    """

    opt_types = ""

    fields = {"FROM": wsd_globals.urn,
              "OPT_TYPES": opt_types}

    r = send_unicast_soap_msg(target_address, "ws-discovery__probe.xml", fields)

    if r is None:
        return None

    x = etree.fromstring(r)

    if not wsd_common.record_message_id(wsd_common.get_message_id(x)):
        return None

    action = wsd_common.get_action_id(x)

    if wsd_globals.debug:
        logger.debug("##\n## PROBE MATCH\n##\n%s",
                     etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

    if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches":
        tt = wsd_common.parse(x).get_target_services()
        return tt[0]

    return None


def wsd_resolve(target_address: str, target_service: wsd_discovery__structures.TargetService) \
        -> typing.Tuple[bool, wsd_discovery__structures.TargetService]:
    """
    Send a multicast resolve message, and wait for the targeted service to respond.

    :param target_service: A wsd target to resolve
    :type target_service: wsd_discovery__structures.TargetService
    :return: an updated TargetService with additional information gathered from resolving
    :rtype: wsd_discovery__structures.TargetService
    """
    return True, target_service

    fields = {"FROM": wsd_globals.urn,
              "EP_ADDR": target_service.ep_ref_addr}
    r = send_unicast_soap_msg(target_address, "ws-discovery__resolve.xml", fields)

    if r is None:
        return None

    x = etree.fromstring(r)

    if not wsd_common.record_message_id(wsd_common.get_message_id(x)):
        return None

    action = wsd_common.get_action_id(x)

    if wsd_globals.debug:
        logger.debug("##\n## RESOLVE MATCH\n##\n%s",
                     etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

    if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/ResolveMatches":
        ts = wsd_common.parse(x).get_target_service()[0]

    if not ts:
        discovery_log("UNRESOLVED     " + target_service.ep_ref_addr)
        return False, target_service
    else:
        discovery_log("RESOLVED       " + ts.ep_ref_addr)
        return True, ts


def get_device(target_address: str) \
        -> wsd_discovery__structures.TargetService:
    device = wsd_probe(target_address, 10)
    ok, target = wsd_resolve(target_address, device)
    if ok:
        return target

    return None


def wsd_multicast_probe(timeout: int = 4) \
        -> typing.List[wsd_discovery__structures.TargetService]:
    """
    Send a UDP multicast WS-Discovery Probe and collect all responses.

    Sends to 239.255.255.250:3702 (the standard WS-Discovery multicast
    group) and listens for ProbeMatches responses.

    :param timeout: seconds to wait for responses
    :return: list of discovered TargetService objects
    """
    message = wsd_common.message_from_file(
        wsd_common.abs_path("templates/ws-discovery__probe.xml"),
        FROM=wsd_globals.urn)

    if wsd_globals.debug:
        r = etree.fromstring(message.encode("ASCII"), parser=wsd_common.parser)
        logger.debug("##\n## MULTICAST PROBE\n##\n%s",
                     etree.tostring(r, pretty_print=True, xml_declaration=True).decode("ASCII"))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
    sock.settimeout(timeout)

    try:
        sock.sendto(message.encode("ASCII"), (wsd_mcast_v4, wsd_udp_port))
        devices = []
        deadline = socket.getdefaulttimeout()
        import time as _time
        end = _time.time() + timeout
        while _time.time() < end:
            try:
                sock.settimeout(end - _time.time())
                data, addr = sock.recvfrom(65536)
                x = etree.fromstring(data)
                action = wsd_common.get_action_id(x)
                if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches":
                    probe_matches = wsd_common.parse(x).get_target_services()
                    for ts in probe_matches:
                        if ts not in devices:
                            logger.info("Discovered: %s (XAddrs: %s)", ts.ep_ref_addr, ts.xaddrs)
                            devices.append(ts)
            except socket.timeout:
                break
            except etree.XMLSyntaxError:
                continue
            except Exception as e:
                logger.debug("Error parsing discovery response: %s", e)
                continue
        return devices
    finally:
        sock.close()


def auto_discover_scanners(timeout: int = 4) \
        -> typing.List[wsd_discovery__structures.TargetService]:
    """
    Discover WSD scanner devices on the local network via UDP multicast.

    After multicast discovery, filters for devices that expose a ScannerServiceType
    by doing WS-Transfer Get on each and checking the hosted service types.

    :param timeout: seconds to wait for multicast probe responses
    :return: list of TargetService objects that have a scanner service
    """
    logger.info("Auto-discovering WSD devices via UDP multicast...")
    devices = wsd_multicast_probe(timeout)

    if not devices:
        logger.warning("No devices found via multicast. Use -t to specify target manually.")
        return []

    scanners = []
    for device in devices:
        if not device.xaddrs:
            logger.debug("Device %s has no XAddrs, skipping", device.ep_ref_addr)
            continue
        try:
            logger.info("Checking %s for scanner service...", device.ep_ref_addr)
            _, hosted_services = wsd_transfer__operations.wsd_get(device)
            for hs in hosted_services:
                if "wscn:ScannerServiceType" in hs.types:
                    logger.info("Found scanner: %s", hs.ep_ref_addr)
                    scanners.append(device)
                    break
        except Exception as e:
            logger.debug("Failed to get metadata from %s: %s", device.ep_ref_addr, e)

    return scanners


def create_table_if_not_exists(db: sqlite3.Connection) -> None:
    cursor = db.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS WsdCache ("
                   "EpRefAddr TEXT PRIMARY KEY, "
                   "MetadataVersion INT NOT NULL, "
                   "SerializedTarget TEXT);")
    db.commit()


def check_target_status(t: wsd_discovery__structures.TargetService) -> bool:
    try:
        wsd_transfer__operations.wsd_get(t)
        discovery_log("VERIFIED       " + t.ep_ref_addr)
        return True
    except (TimeoutError, StopIteration):
        return False


def set_discovery_verbosity(lvl: int):
    global discovery_verbosity
    discovery_verbosity = lvl


def discovery_log(text: str, lvl: int = 1):
    logger.debug(text) if discovery_verbosity >= lvl else None

