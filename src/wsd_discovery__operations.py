#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import os
import pickle
import select
import socket
import sqlite3
import struct
import typing

import lxml.etree as etree

import wsd_common, \
    wsd_discovery__structures, \
    wsd_transfer__operations, \
    wsd_globals

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
        print('##\n## %s\n##\n' % op_name)
        wsd_common.log_xml(r)
        print(etree.tostring(r, pretty_print=True, xml_declaration=True).decode("ASCII"))

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
        # print('##\n## %s MATCH\n## %s\n##\n' % (action.split("/")[-1].upper(), server[0]))
        wsd_common.log_xml(x)
        print(etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

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
        # print('##\n## %s MATCH\n## %s\n##\n' % (action.split("/")[-1].upper(), server[0]))
        wsd_common.log_xml(x)
        print(etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

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
    print(text) if discovery_verbosity >= lvl else None

