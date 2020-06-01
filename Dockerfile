FROM python:3.8.2-slim-buster

EXPOSE 6666

RUN pip install argparse python-dateutil uuid lxml requests urllib3 PyYAML img2pdf secure-smtplib
#RUN pip install ssl

COPY src /wsd-scan
COPY start_script.sh /

RUN chmod +x /start_script.sh

CMD /start_script.sh