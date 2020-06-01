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

## Supported Devices
The program should more or less work with every WSD enabled scanner. It was only tested though with a HP Laser MFP 137fnw.

## How it works
After connecting to the target device the program pushes the scan profiles to the scanner. This is done with a subscription to the ScanAvailableEvent.
If you initiate a scan from your device now, using one of these profiles, the scanner sends the ScanAvailableEvent back to the program.
The program then retrieves the so called DefaultScanTicket from the scanner. It replaces the relevant values with those defined in the selected profile and sends it to the scanner.
The scanner starts the scan job and sends the result back to our program, where it can be compressed and stored.