FROM python:3.11-slim

EXPOSE 6666

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY wsd_scan/ wsd_scan/
RUN pip install --no-cache-dir --no-deps -e .

COPY start_script.sh /
RUN chmod +x /start_script.sh

CMD /start_script.sh
