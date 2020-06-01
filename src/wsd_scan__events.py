#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

import copy
import http.server
import queue
import threading
import typing
from datetime import datetime, timedelta

import img2pdf as img2pdf
import lxml.etree as etree
from PIL import Image

import mail_service
import wsd_common
import wsd_eventing__operations
import wsd_globals
import wsd_scan__operations
import wsd_scan__parsers
import wsd_transfer__structures
import xml_helpers

token_map = {}
host_map = {}
profile_map = {}


def wsd_scanner_all_events_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                     notify_addr: str,
                                     expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to ScannerElementsChange events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerElementsChangeEvent"
    event_uri += " http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusSummaryEvent"
    event_uri += " http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusConditionEvent"
    event_uri += " http://schemas.microsoft.com/windows/2006/08/wdp/scan/JobStatusEvent"
    event_uri += " http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusConditionClearedEvent"
    event_uri += " http://schemas.microsoft.com/windows/2006/08/wdp/scan/JobEndStateEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)

    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_scanner_elements_change_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                          notify_addr: str,
                                          expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to ScannerElementsChange events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerElementsChangeEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)

    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_scanner_status_summary_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                         notify_addr: str,
                                         expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to ScannerStatusSummary events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
     """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusSummaryEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)
    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_scanner_status_condition_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                           notify_addr: str,
                                           expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to ScannerStatusCondition events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusConditionEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)
    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_scanner_status_condition_cleared_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                                   notify_addr: str,
                                                   expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to ScannerStatusConditionCleared events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/ScannerStatusConditionClearedEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)
    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_job_status_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                             notify_addr: str,
                             expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to JobStatus events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/JobStatusEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)
    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


def wsd_job_end_state_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                notify_addr: str,
                                expiration: typing.Union[datetime, timedelta] = None) \
        -> typing.Union[bool, str]:
    """
        Subscribe to JobEndState events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param expiration: Expiration time, as a datetime or timedelta object
        :param notify_addr: The address to send notifications to.
        :return: False if a fault message is received, a subscription ID otherwise
    """
    event_uri = "http://schemas.microsoft.com/windows/2006/08/wdp/scan/JobEndStateEvent"
    x = wsd_eventing__operations.wsd_subscribe(hosted_scan_service,
                                               event_uri,
                                               notify_addr,
                                               expiration)
    if x is False:
        return False
    return wsd_common.xml_find(x, ".//wse:Identifier").text


# TODO: handle this subscription with wsd_eventing__operations.wsd_subscribe()
def wsd_scan_available_event_subscribe(hosted_scan_service: wsd_transfer__structures.HostedService,
                                       display_str: str,
                                       context_str: str,
                                       notify_addr: str,
                                       expiration: typing.Union[datetime, timedelta] = None):
    """
        Subscribe to ScanAvailable events.

        :param hosted_scan_service: the wsd service to receive event notifications from
        :param display_str: the string to display on the device control panel
        :param context_str: a string internally used to identify the selection of this wsd host as target of the scan
        :param notify_addr: The address to send notifications to.
        :param expiration: Expiration time, as a datetime or timedelta object
        :return: a subscription ID  and the token needed in CreateScanJob to start a device-initiated scan, \
                or False if a fault message is received instead
    """

    if expiration is None:
        pass
    elif expiration.__class__ == "datetime.datetime":
        expiration = xml_helpers.fmt_as_xml_datetime(expiration)
    elif expiration.__class__ == "datetime.timedelta":
        expiration = xml_helpers.fmt_as_xml_duration(expiration)
    else:
        raise TypeError

    expiration_tag = ""
    if expiration is not None:
        expiration_tag = "<wse:Expires>%s</wse:Expires>" % expiration

    fields_map = {"FROM": wsd_globals.urn,
                  "TO": hosted_scan_service.ep_ref_addr,
                  "NOTIFY_ADDR": notify_addr,
                  "OPT_EXPIRATION": expiration_tag,
                  "DISPLAY_STR": display_str,
                  "CONTEXT": context_str}
    try:
        x = wsd_common.submit_request({hosted_scan_service.ep_ref_addr},
                                      "ws-scan__scan_available_event_subscribe.xml",
                                      fields_map)
        dest_token = wsd_common.xml_find(x, ".//sca:DestinationToken").text
        subscription_id = wsd_common.xml_find(x, ".//wse:Identifier").text
        return subscription_id, dest_token
    except TimeoutError:
        return False


class QueuesSet:
    def __init__(self):
        self.sc_descr_q = queue.Queue()
        self.sc_conf_q = queue.Queue()
        self.sc_ticket_q = queue.Queue()
        self.sc_stat_sum_q = queue.Queue()
        self.sc_cond_q = queue.Queue()
        self.sc_cond_clr_q = queue.Queue()
        self.job_status_q = queue.Queue()
        self.job_ended_q = queue.Queue()


class HTTPServerWithContext(http.server.HTTPServer):
    def __init__(self, server_address, request_handler_class, context, *args, **kw):
        super().__init__(server_address, request_handler_class, *args, **kw)
        self.context = context


class RequestHandler(http.server.BaseHTTPRequestHandler):

    def do_POST(self):
        context = self.server.context
        # request_path = self.path
        request_headers = self.headers
        length = int(request_headers["content-length"])

        message = self.rfile.read(length)

        self.protocol_version = "HTTP/1.1"
        self.send_response(202)
        self.send_header("Content-Type", "application/soap+xml")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

        x = etree.fromstring(message)
        action = wsd_common.xml_find(x, ".//wsa:Action").text
        (prefix, _, action) = action.rpartition('/')
        if prefix != 'http://schemas.microsoft.com/windows/2006/08/wdp/scan':
            return
        if action == 'ScanAvailableEvent':
            self.handle_scan_available_event(x)

        elif action == 'ScannerElementsChangeEvent':
            self.handle_scanner_elements_change_event(context['queues'], x)

        elif action == 'ScannerStatusSummaryEvent':
            self.handle_scanner_status_summary_event(context['queues'], x)

        elif action == 'ScannerStatusConditionEvent':
            self.handle_scanner_status_condition_event(context['queues'], x)

        elif action == 'ScannerStatusConditionClearedEvent':
            self.handle_scanner_status_condition_cleared_event(context['queues'], x)

        elif action == 'JobStatusEvent':
            self.handle_job_status_event(context['queues'], x)

        elif action == 'JobEndStateEvent':
            self.handle_job_end_state_event(context['queues'], x)

    @staticmethod
    def handle_scan_available_event(xml_tree):
        if wsd_globals.debug is True:
            print('##\n## SCAN AVAILABLE EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))
        client_context = wsd_common.xml_find(xml_tree, ".//sca:ClientContext").text
        scan_identifier = wsd_common.xml_find(xml_tree, ".//sca:ScanIdentifier").text
        t = threading.Thread(target=device_initiated_scan_worker,
                             args=(client_context,
                                   scan_identifier,
                                   "scan-" + datetime.now().strftime("%Y-%m-%d_%H_%M_%S")))
        t.start()

    @staticmethod
    def handle_scanner_elements_change_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## SCANNER ELEMENTS CHANGE EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))

        sca_config = wsd_common.xml_find(xml_tree, ".//sca:ScannerConfiguration")
        sca_descr = wsd_common.xml_find(xml_tree, ".//sca:ScannerDescription")
        std_ticket = wsd_common.xml_find(xml_tree, ".//sca:DefaultScanTicket")

        description = wsd_scan__parsers.parse_scan_description(sca_descr)
        configuration = wsd_scan__parsers.parse_scan_configuration(sca_config)
        std_ticket = wsd_scan__parsers.parse_scan_ticket(std_ticket)

        queues.sc_descr_q.put(description)
        queues.sc_conf_q.put(configuration)
        queues.sc_ticket_q.put(std_ticket)

    @staticmethod
    def handle_scanner_status_summary_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## SCANNER STATUS SUMMARY EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))

        state = wsd_common.xml_find(xml_tree, ".//sca:ScannerState").text
        reasons = []
        q = wsd_common.xml_find(xml_tree, ".//sca:ScannerStateReasons")
        if q is not None:
            dsr = wsd_common.xml_findall(q, ".//sca:ScannerStateReason")
            for sr in dsr:
                reasons.append(sr.text)
        queues.sc_stat_sum_q.put((state, reasons))

    @staticmethod
    def handle_scanner_status_condition_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## SCANNER STATUS CONDITION EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))

        cond = wsd_common.xml_find(xml_tree, ".//sca:DeviceCondition")
        cond = wsd_scan__parsers.parse_scanner_condition(cond)
        queues.sc_cond_q.put(cond)

    @staticmethod
    def handle_scanner_status_condition_cleared_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## SCANNER STATUS CONDITION CLEARED EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))

        cond = wsd_common.xml_find(xml_tree, ".//sca:DeviceConditionCleared")
        cond_id = int(wsd_common.xml_find(cond, ".//sca:ConditionId").text)
        clear_time = wsd_common.xml_find(cond, ".//sca:ConditionClearTime").text
        queues.sc_cond_clr_q.put((cond_id, clear_time))

    @staticmethod
    def handle_job_status_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## JOB STATUS EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))
            s = wsd_common.xml_find(xml_tree, ".//sca:JobStatus")
            queues.sc_job_status_q.put(wsd_scan__parsers.parse_job_status(s))

    @staticmethod
    def handle_job_end_state_event(queues, xml_tree):
        if wsd_globals.debug is True:
            print('##\n## JOB END STATE EVENT\n##\n')
            print(etree.tostring(xml_tree, pretty_print=True, xml_declaration=True))
            s = wsd_common.xml_find(xml_tree, ".//sca:JobEndState")
            queues.sc_job_ended_q.put(wsd_scan__parsers.parse_job_summary(s))


# TODO: implement multi-device simultaneous monitoring
class WSDScannerMonitor:
    """
    A class that abstracts event handling and data querying for a device. Programmer should instantiate this class
    and use its methods to retrieve tickets/configurations/status and more, instead of submitting a wsd request
    directly to the device. This class listens to events and so polling devices is no longer needed.
    """

    def __init__(self,
                 service: wsd_transfer__structures.HostedService,
                 listen_addr,
                 port):
        self.service = service
        (self.description,
         self.configuration,
         self.status,
         self.std_ticket) = wsd_scan__operations.wsd_get_scanner_elements(service)
        self.active_jobs = {}
        for aj in wsd_scan__operations.wsd_get_active_jobs(service):
            self.active_jobs[aj.status.id] = wsd_scan__operations.wsd_get_job_elements(service, aj.status.id)
        self.job_history = {}
        for ej in wsd_scan__operations.wsd_get_job_history(service):
            self.job_history[ej.status.id] = ej

        self.subscription_id = wsd_scanner_all_events_subscribe(service, listen_addr)

        self.queues = QueuesSet()

        context = {"allow_device_initiated_scans": False,
                   "queues": self.queues}

        self.server = HTTPServerWithContext(('', port), RequestHandler, context)
        self.listener = threading.Thread(target=self.server.serve_forever, args=())
        self.listener.start()

    def close(self):
        self.server.shutdown()
        self.listener.join()
        wsd_eventing__operations.wsd_unsubscribe(self.service, self.subscription_id)

    def get_scanner_description(self):
        """
        Updates and returns the current description of the device.

        :return: a valid ScannerDescription instance
        """
        while self.queues.sc_descr_q.empty() is not True:
            self.description = self.queues.sc_descr_q.get()
            self.queues.sc_descr_q.task_done()
        return self.description

    def get_scanner_configuration(self):
        """
        Updates and returns the current configuration of the device.

        :return: a valid ScannerConfiguration instance
        """
        while self.queues.sc_conf_q.empty() is not True:
            self.configuration = self.queues.sc_conf_q.get()
            self.queues.sc_conf_q.task_done()
        return self.configuration

    def get_default_ticket(self):
        """
        Updates and returns the default scan ticket of the device.

        :return: a valid ScanTicket instance
        """
        while self.queues.sc_ticket_q.empty() is not True:
            self.std_ticket = self.queues.sc_ticket_q.get()
            self.queues.sc_ticket_q.task_done()
        return self.std_ticket

    def get_scanner_status(self):
        """
        Updates and returns the current status and conditions of the device.

        :return: a valid ScannerStatus instance
        """
        while self.queues.sc_cond_q.empty() is not True:
            cond = self.queues.sc_cond_q.get()
            self.status.active_conditions[cond.id] = cond
            self.queues.sc_cond_q.task_done()
        while self.queues.sc_cond_clr_q.empty() is not True:
            (c_id, c_time) = self.queues.sc_cond_clr_q.get()
            self.status.conditions_history[c_time] = copy.deepcopy(self.status.active_conditions[c_id])
            del self.status.active_conditions[c_id]
            self.queues.sc_cond_clr_q.task_done()
        while self.queues.sc_stat_sum_q.empty() is not True:
            (self.status.state, self.status.reasons) = self.queues.sc_stat_sum_q.get()
            self.queues.sc_stat_sum_q.task_done()
        return self.status

    def get_active_jobs(self):
        while self.queues.job_status_q.empty() is not True:
            status = self.queues.sc_cond_q.get()
            if status.id not in self.active_jobs.keys():
                self.active_jobs[status.id] = wsd_scan__operations.wsd_get_job_elements(self.service, status.id)
            else:
                self.active_jobs[status.id][0] = status
            self.queues.job_status_q.task_done()
        while self.queues.job_ended_q.empty() is not True:
            summary = self.queues.sc_cond_q.get()
            del self.active_jobs[summary.status.id]
            self.job_history[summary.status.id] = summary
            self.queues.job_ended_q.task_done()
        return self.active_jobs

    def get_job_history(self):
        while self.queues.job_ended_q.empty() is not True:
            summary = self.queues.sc_cond_q.get()
            del self.active_jobs[summary.status.id]
            self.job_history[summary.status.id] = summary
            self.queues.job_ended_q.task_done()
        return self.job_history

    def scanner_description_has_changed(self):
        """
        Check if the scanner status has been updated since last get_scanner_description() call

        :return: True if the scanner description has changed, False otherwise
        """
        return not self.queues.sc_cond_q.empty()

    def scanner_configuration_has_changed(self):
        """
        Check if the scanner status has been updated since last get_scanner_configuration() call

        :return: True if the scanner configuration has changed, False otherwise
        """
        return not self.queues.sc_conf_q.empty()

    def default_scan_ticket_has_changed(self):
        """
        Check if the scanner status has been updated since last get_default_ticket() call

        :return: True if the default scan ticket has changed, False otherwise
        """
        return not self.queues.sc_ticket_q.empty()

    def scanner_status_has_changed(self):
        """
        Check if the scanner status has been updated since last get_scanner_status() call

        :return: True if the scanner status has changed, False otherwise
        """
        return not (self.queues.sc_cond_q.empty()
                    and self.queues.sc_cond_clr_q.empty()
                    and self.queues.sc_stat_sum_q.empty())

    def job_status_has_changed(self):
        """
        Check if the status of some jobs has been updated since last get_job_status() call

        :return: True if the status of some jobs has changed, False otherwise
        """
        return not (self.queues.job_status_q.empty()
                    and self.queues.job_ended_q.empty())


def device_initiated_scan_worker(client_context: str,
                                 scan_identifier: str,
                                 file_name: str):
    """
    Reply to a ScanAvailable event by issuing the creation of a new scan job.
    Waits for job completion and writes the output to files.

    :param client_context: a string identifying a wsd host selection
    :type client_context: str
    :param scan_identifier: a string identifying the specific scan task to handle
    :type scan_identifier: str
    :param file_name: the prefix name of the files to write.
    :type file_name: str
    """
    host = host_map[client_context]
    dest_token = token_map[client_context]
    profile = profile_map[client_context]
    description, config, status, std_ticket = wsd_scan__operations.wsd_get_scanner_elements(host)

    std_ticket.override_params(profile)

    platen_fallback = False
    # for auto input we try ADF first and use Platen as a fallback
    if std_ticket.doc_params.input_src == "Auto":
        std_ticket.doc_params.input_src = "ADF"
        platen_fallback = True

    save_format = profile["image_format"]

    image_id = 0
    picture_files = []

    more_images_available = True

    while more_images_available:
        job = wsd_scan__operations.wsd_create_scan_job(host, std_ticket, scan_identifier, dest_token)
        img = wsd_scan__operations.wsd_retrieve_image(host, job, file_name)

        if img == Image.NONE:
            if platen_fallback:
                std_ticket.doc_params.input_src = "Platen"
                continue
            else:
                more_images_available = False
                break

        picture_file = "%s/%s_%d.%s" % (profile["target_folder"], file_name, image_id, save_format)
        img.save(picture_file, format=save_format, quality=profile["quality"])
        picture_files.append(picture_file)
        image_id += 1

        # Try again with platen only once
        if platen_fallback:
            platen_fallback = False
        # Only check for more images if the ADF is used
        elif std_ticket.doc_params.input_src == "Platen":
            more_images_available = False

    if profile["use_pdf"]:
        pdf_file_name = "%s/%s.pdf" % (profile["target_folder"], file_name)
        with open(pdf_file_name, "wb") as f:
            f.write(img2pdf.convert(picture_files))
        attachments = [pdf_file_name]
    else:
        attachments = picture_files

    if profile["send_email"]:
        mail_service.MailService().sendMaiWithScannedDocuments(attachments)
