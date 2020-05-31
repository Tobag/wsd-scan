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


def send_multicast_soap_msg(xml_template: str,
                            fields_map: typing.Dict[str, str],
                            timeout: int) \
        -> socket.socket:
    """
    Send a wsd xml/soap multicast request, and return the opened socket.

    :param xml_template: the name of the xml template to fill and send
    :type xml_template: str
    :param fields_map: the map of placeholders and strings to substitute inside the template
    :type fields_map: {str: str}
    :param timeout: the timeout of the socket
    :type timeout: int
    :return: the socket use for message delivery
    :rtype: socket.socket
    """
    message = wsd_common.message_from_file(wsd_common.abs_path("templates/%s" % xml_template),
                                           **fields_map)

    op_name = " ".join(xml_template.split("__")[1].split(".")[0].split("_")).upper()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    if wsd_globals.debug:
        r = etree.fromstring(message.encode("ASCII"), parser=wsd_common.parser)
        print('##\n## %s\n##\n' % op_name)
        wsd_common.log_xml(r)
        print(etree.tostring(r, pretty_print=True, xml_declaration=True).decode("ASCII"))
    sock.sendto(message.encode("UTF-8"), (wsd_mcast_v4, wsd_udp_port))
    return sock


# FIXME Check if this update mechanism is still needed
def read_discovery_multicast_reply(sock: socket.socket,
                                   target_service: wsd_discovery__structures.TargetService) \
        -> typing.Union[None, typing.Tuple[bool, typing.List[wsd_discovery__structures.TargetService]]]:
    """
    Waits for a reply from an endpoint, containing info about the target itself. Used to
    catch wsd_probe and wsd_resolve responses. Updates the target_service with data collected.

    :param sock: The socket to read from
    :type sock: socket.socket
    :param target_service: an instance of TargetService to fill or update with data received
    :return: an updated target_service object, or False if the socket timeout is reached
    :rtype: wsd_discovery__structures.TargetService | False
    """
    while True:
        try:
            data, server = sock.recvfrom(4096)
        except socket.timeout:
            if wsd_globals.debug:
                print('##\n## TIMEOUT\n##\n')
            return False, []
        else:
            x = etree.fromstring(data)

            if not wsd_common.record_message_id(wsd_common.get_message_id(x)):
                continue

            action = wsd_common.get_action_id(x)

            if wsd_globals.debug:
                print('##\n## %s MATCH\n## %s\n##\n' % (action.split("/")[-1].upper(), server[0]))
                wsd_common.log_xml(x)
                print(etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

            if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches":
                tt = wsd_common.parse(x).get_target_services()
                return len(tt) > 1, tt
            if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/ResolveMatches":
                return False, wsd_common.parse(x).get_target_service()


def open_multicast_udp_socket(addr: str, port: int) -> socket.socket:
    res = socket.getaddrinfo(addr, port, type=socket.SOCK_DGRAM)

    if not res:
        raise ConnectionError

    addrinfo = res[0]

    sock = socket.socket(addrinfo[0], socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('', port))
    gbin = socket.inet_pton(addrinfo[0], addrinfo[4][0])
    if addrinfo[0] == socket.AF_INET:
        mreq = gbin + struct.pack('=I', socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
    else:
        mreq = gbin + struct.pack('@I', 0)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)

    return sock


def init_multicast_listener() -> typing.List[socket.socket]:
    sock_1 = open_multicast_udp_socket(wsd_mcast_v4, wsd_udp_port)
    return [sock_1]
    # sock_2 = open_multicast_udp_socket(wsd_mcast_v6, wsd_udp_port)
    # return [sock_1, sock_2] #TODO: enable ipv6 support once stable


def deinit_multicast_listener(sockets: typing.List[socket.socket]) -> None:
    for sock in sockets:
        sock.close()


def listen_multicast_announcements(sockets: typing.List[socket.socket]) \
        -> typing.Tuple[bool, wsd_discovery__structures.TargetService]:
    """

    """
    empty = []
    readable = []
    action = ""
    while action not in ["http://schemas.xmlsoap.org/ws/2005/04/discovery/Hello",
                         "http://schemas.xmlsoap.org/ws/2005/04/discovery/Bye"]:
        while not readable:
            readable, writable, exceptional = select.select(sockets, empty, empty)

        data, server = readable[0].recvfrom(4096)
        x = etree.fromstring(data)
        action = wsd_common.get_action_id(x)
        readable = []
        if not wsd_common.record_message_id(wsd_common.get_message_id(x)):
            continue

    if wsd_globals.debug:
        print('##\n## %s MATCH\n## %s\n##\n' % (action.split("/")[-1].upper(), server[0]))
        wsd_common.log_xml(x)
        print(etree.tostring(x, pretty_print=True, xml_declaration=True).decode("ASCII"))

    if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/Hello":
        return True, wsd_common.parse(x).get_target_service()
    if action == "http://schemas.xmlsoap.org/ws/2005/04/discovery/Bye":
        return False, wsd_common.parse(x).get_target_service()


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


def read_targets_from_db(db: sqlite3.Connection) -> typing.Set[wsd_discovery__structures.TargetService]:
    cursor = db.cursor()
    c = set()
    cursor.execute('SELECT DISTINCT EpRefAddr, SerializedTarget FROM WsdCache')
    for row in cursor:
        c.add(pickle.loads(row[1].encode()))
    return c


def add_target_to_db(db: sqlite3.Connection,
                     t: wsd_discovery__structures.TargetService) -> None:
    cursor = db.cursor()
    cursor.execute('UPDATE WsdCache '
                   'SET    EpRefAddr = :a, '
                   '       MetadataVersion = :b, '
                   '       SerializedTarget = :c '
                   'WHERE  EpRefAddr = :a '
                   'AND MetadataVersion > :b',
                   {"a": t.ep_ref_addr,
                    "b": t.meta_ver,
                    "c": pickle.dumps(t, 0).decode()})
    if not cursor.rowcount:
        cursor.execute('INSERT OR IGNORE '
                       'INTO WsdCache '
                       '(EpRefAddr, MetadataVersion, SerializedTarget) '
                       'VALUES (:a,:b,:c)',
                       {"a": t.ep_ref_addr,
                        "b": t.meta_ver,
                        "c": pickle.dumps(t, 0).decode()})
    discovery_log("REGISTERED     " + t.ep_ref_addr)
    db.commit()


def remove_target_from_db(db: sqlite3.Connection,
                          t: wsd_discovery__structures.TargetService) -> None:
    cursor = db.cursor()
    cursor.execute('DELETE FROM WsdCache WHERE EpRefAddr=?', (t.ep_ref_addr,))
    discovery_log("UNREGISTERED   " + t.ep_ref_addr)
    db.commit()


def set_discovery_verbosity(lvl: int):
    global discovery_verbosity
    discovery_verbosity = lvl


def discovery_log(text: str, lvl: int = 1):
    print(text) if discovery_verbosity >= lvl else None


def open_db() -> sqlite3.Connection:
    return sqlite3.connect(db_path)


#######################
# INITIALIZATION CODE #
#######################
if not db_path:
    db_path = os.path.expanduser("~/.wsdcache.db")
    os.environ["WSD_CACHE_PATH"] = db_path
