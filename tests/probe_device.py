#!/usr/bin/env python3
"""Standalone probe script — interrogates the Samsung M288x via WSD.
Sends WS-Transfer Get and GetScannerElements to candidate endpoints
and dumps the raw XML responses so we can see the real service URLs
and scanner capabilities.
"""
import sys
import uuid
import requests

NSMAP = {
    "soap": "http://www.w3.org/2003/05/soap-envelope",
    "wsa": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "mex": "http://schemas.xmlsoap.org/ws/2004/09/mex",
    "wsdp": "http://schemas.xmlsoap.org/ws/2006/02/devprof",
    "pnpx": "http://schemas.microsoft.com/windows/pnpx/2005/10",
    "sca": "http://schemas.microsoft.com/windows/2006/08/wdp/scan",
}

HEADERS = {"user-agent": "WSDAPI", "content-type": "application/soap+xml"}
URN = "urn:uuid:" + str(uuid.uuid4())

# Candidate endpoints from CLAUDE.md and airscan.conf
CANDIDATES = [
    "http://192.168.0.149:8018/wsd",
    "http://192.168.0.149/wsd",
    "http://192.168.0.149:80/wsd",
]

WS_TRANSFER_GET = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:mex="http://schemas.xmlsoap.org/ws/2004/09/mex">
  <soap:Header>
    <wsa:To>{to}</wsa:To>
    <wsa:Action>http://schemas.xmlsoap.org/ws/2004/09/transfer/Get</wsa:Action>
    <wsa:MessageID>{msg_id}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsa:From>
      <wsa:Address>{from_addr}</wsa:Address>
    </wsa:From>
  </soap:Header>
  <soap:Body>
    <mex:GetMetadata/>
  </soap:Body>
</soap:Envelope>"""

GET_SCANNER_ELEMENTS = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
               xmlns:sca="http://schemas.microsoft.com/windows/2006/08/wdp/scan">
  <soap:Header>
    <wsa:To>{to}</wsa:To>
    <wsa:Action>http://schemas.microsoft.com/windows/2006/08/wdp/scan/GetScannerElements</wsa:Action>
    <wsa:MessageID>{msg_id}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsa:From>
      <wsa:Address>{from_addr}</wsa:Address>
    </wsa:From>
  </soap:Header>
  <soap:Body>
    <sca:GetScannerElementsRequest>
      <sca:RequestedElements>
        <sca:Name>sca:ScannerStatus</sca:Name>
        <sca:Name>sca:ScannerDescription</sca:Name>
        <sca:Name>sca:ScannerConfiguration</sca:Name>
        <sca:Name>sca:DefaultScanTicket</sca:Name>
      </sca:RequestedElements>
    </sca:GetScannerElementsRequest>
  </soap:Body>
</soap:Envelope>"""


def try_endpoint(url, template):
    msg = template.format(
        to=url, msg_id="urn:uuid:" + str(uuid.uuid4()),
        from_addr=URN,
    )
    try:
        r = requests.post(url, headers=HEADERS, data=msg, timeout=10)
        return r.status_code, r.content
    except Exception as e:
        return None, str(e)


def main():
    from lxml import etree

    print("=== Probing Samsung M288x at 192.168.0.149 ===\n")
    print("Client URN: %s\n" % URN)

    # Phase 1: WS-Transfer Get to find hosted services
    for url in CANDIDATES:
        print("--- WS-Transfer Get to %s ---" % url)
        code, body = try_endpoint(url, WS_TRANSFER_GET)
        if code is None:
            print("  FAILED: %s\n" % body)
            continue
        print("  HTTP %d, %d bytes" % (code, len(body)))
        if code == 200:
            print("  SUCCESS — parsing metadata...\n")
            root = etree.fromstring(body)
            print(etree.tostring(root, pretty_print=True, encoding="unicode"))
            print()

            # Extract hosted service endpoints
            hosted = root.findall(".//wsdp:Hosted", NSMAP)
            for h in hosted:
                types_el = h.find(".//wsdp:Types", NSMAP)
                addr_el = h.find(".//wsa:EndpointReference/wsa:Address", NSMAP)
                sid_el = h.find(".//wsdp:ServiceId", NSMAP)
                types_text = types_el.text if types_el is not None else "?"
                addr_text = addr_el.text if addr_el is not None else "?"
                sid_text = sid_el.text if sid_el is not None else "?"
                print("  HostedService: %s" % addr_text)
                print("    Types: %s" % types_text)
                print("    ServiceId: %s\n" % sid_text)

                if "wscn:ScannerServiceType" in types_text or "scan" in types_text.lower():
                    print("  >>> This is the Scanner Service <<<")
                    print("\n--- GetScannerElements to %s ---" % addr_text)
                    code2, body2 = try_endpoint(addr_text, GET_SCANNER_ELEMENTS)
                    if code2 is None:
                        print("  FAILED: %s\n" % body2)
                    else:
                        print("  HTTP %d, %d bytes" % (code2, len(body2)))
                        if code2 == 200:
                            root2 = etree.fromstring(body2)
                            print(etree.tostring(root2, pretty_print=True, encoding="unicode"))
            return

    print("\nNo endpoint responded with 200 to WS-Transfer Get.")


if __name__ == "__main__":
    main()
