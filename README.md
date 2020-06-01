# wsd-scan
Python program that allows device initiated scans for WSD capable scanners

Based on https://github.com/roncapat/WSD-python

## How to use it
The program is started with
``python wsd-scan.py start -t WSD_ADDRESS_OF_SCANNER -s OWN_IP``

After connecting to the scanner wsd-scan registers the scan profiles with the device. The profiles are defined in the yaml files from the profiles folder.

## Dependencies
Please make sure you have the following dependencies installed:
``argparse python-dateutil uuid lxml requests urllib3 PyYAML img2pdf secure-smtplib``

## Receiving scanned documents as an email attachment
If you provide the login credentials to your SMTP server in profiles/mail_service.yaml you can receive your scanned documents as an email attachment.
Make sure the scan profile has ``send_email: True``