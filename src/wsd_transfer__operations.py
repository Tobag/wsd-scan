#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import wsd_common, \
    wsd_discovery__operations, \
    wsd_discovery__structures, \
    wsd_transfer__structures, \
    wsd_globals


def wsd_get(target_service: wsd_discovery__structures.TargetService):
    """
    Query wsd target for information about model/device and hosted services.

    :param target_service: A wsd target
    :type target_service: wsd_discovery__structures.TargetService
    :return: A tuple containing a TargetInfo and a list of HostedService instances.
    """
    fields = {"FROM": wsd_globals.urn,
              "TO": target_service.ep_ref_addr}
    x = wsd_common.submit_request(target_service.xaddrs,
                                  "ws-transfer__get.xml",
                                  fields)

    if x is False:
        return False

    meta = wsd_common.xml_find(x, ".//mex:Metadata")
    meta_model = wsd_common.xml_find(meta,
                                     ".//mex:MetadataSection[@Dialect=\
                                     'http://schemas.xmlsoap.org/ws/2006/02/devprof/ThisModel']")
    meta_dev = wsd_common.xml_find(meta,
                                   ".//mex:MetadataSection[@Dialect=\
                                   'http://schemas.xmlsoap.org/ws/2006/02/devprof/ThisDevice']")
    meta_rel = wsd_common.xml_find(meta,
                                   ".//mex:MetadataSection[@Dialect=\
                                   'http://schemas.xmlsoap.org/ws/2006/02/devprof/Relationship']")

    tinfo = wsd_transfer__structures.TargetInfo()
    # WSD-Profiles section 5.1 (+ PNP-X)
    tinfo.manufacturer = wsd_common.xml_find(meta_model, ".//wsdp:Manufacturer").text
    q = wsd_common.xml_find(meta_model, ".//wsdp:ManufacturerUrl")
    if q is not None:
        tinfo.manufacturer_url = q.text
    tinfo.model_name = wsd_common.xml_find(meta_model, ".//wsdp:ModelName").text
    q = wsd_common.xml_find(meta_model, ".//wsdp:ModelNumber")
    if q is not None:
        tinfo.model_number = q.text
    q = wsd_common.xml_find(meta_model, ".//wsdp:ModelUrl")
    if q is not None:
        tinfo.model_url = q.text
    q = wsd_common.xml_find(meta_model, ".//wsdp:PresentationUrl")
    if q is not None:
        tinfo.presentation_url = q.text
    tinfo.device_cat = wsd_common.xml_find(meta_model, ".//pnpx:DeviceCategory").text.split()

    tinfo.friendly_name = wsd_common.xml_find(meta_dev, ".//wsdp:FriendlyName").text
    tinfo.fw_ver = wsd_common.xml_find(meta_dev, ".//wsdp:FirmwareVersion").text
    tinfo.serial_num = wsd_common.xml_find(meta_dev, ".//wsdp:SerialNumber").text

    hservices = []
    # WSD-Profiles section 5.2 (+ PNP-X)
    wsd_common.xml_findall(meta_rel, ".//wsdp:Relationship[@Type='http://schemas.xmlsoap.org/ws/2006/02/devprof/host']")

    for r in meta_rel:
        # UNCLEAR how the host item should differ from the target endpoint, and how to manage multiple host items
        # TBD - need some real-case examples
        # host = xml_find(r, ".//wsdp:Host")
        # if host is not None:    #"if omitted, implies the same endpoint reference of the targeted service"
        #    xml_find(host, ".//wsdp:Types").text
        #    xml_find(host, ".//wsdp:ServiceId").text
        #    er = xml_find(host, ".//wsa:EndpointReference")
        #    xml_find(er, ".//wsa:Address").text  #Optional endpoint fields not implemented yet
        hosted = wsd_common.xml_findall(r, ".//wsdp:Hosted")
        for h in hosted:
            hs = wsd_transfer__structures.HostedService()
            hs.types = wsd_common.xml_find(h, ".//wsdp:Types").text.split()
            hs.service_id = wsd_common.xml_find(h, ".//wsdp:ServiceId").text
            q = wsd_common.xml_find(h, ".//pnpx:HardwareId")
            if q is not None:
                hs.hardware_id = q.text
            q = wsd_common.xml_find(h, ".//pnpx:CompatibleId")
            if q is not None:
                hs.compatible_id = q.text
            q = wsd_common.xml_find(h, ".//wsdp:ServiceAddress")
            if q is not None:
                hs.service_address = q.text
            er = wsd_common.xml_find(h, ".//wsa:EndpointReference")
            hs.ep_ref_addr = wsd_common.xml_find(er, ".//wsa:Address").text
            hservices.append(hs)

    # WSD-Profiles section 5.3 and 5.4 omitted
    return tinfo, hservices


def __demo():
    wsd_common.init()
    wsd_common.enable_debug()
    tsl = wsd_discovery__operations.get_devices()
    for a in tsl:
        print(a)
        try:
            (ti, hss) = wsd_get(a)
            print(ti)
            for b in hss:
                print(b)
        except TimeoutError:
            print("The target did not reply")


if __name__ == "__main__":
    __demo()
