import smtplib
import ssl
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import yaml


class MailService:
    def __init__(self):
        return

    def sendMaiWithScannedDocuments(self, attachments):
        with open("./profiles/mail_service.yaml") as yaml_file:
            yaml_object = yaml.load(yaml_file, Loader=yaml.FullLoader)
            yaml_file.close()

        subject = "You scanned document"
        body = "You scanned document be attached to this email."
        sender_email = yaml_object["sender"]
        receiver_email = yaml_object["to"]

        # Create a multipart message and set headers
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Subject"] = subject

        # Add body to email
        message.attach(MIMEText(body, "plain"))

        for attachment in attachments:
            self.attach_file(message, attachment)

        text = message.as_string()

        # Log in to server using secure context and send email
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(yaml_object["smtp"]["server"], 465, context=context) as server:
            server.login(yaml_object["smtp"]["user"], yaml_object["smtp"]["password"])
            server.sendmail(sender_email, receiver_email, text)

    def attach_file(self, message, filename):
        # Open PDF file in binary mode
        with open(filename, "rb") as attachment:
            # Add file as application/octet-stream
            # Email client can usually download this automatically as attachment
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
        # Encode file in ASCII characters to send by email
        encoders.encode_base64(part)
        # Add header as key/value pair to attachment part
        part.add_header(
            "Content-Disposition",
            "attachment; filename=%s" % filename,
        )
        # Add attachment to message and convert message to string
        message.attach(part)
