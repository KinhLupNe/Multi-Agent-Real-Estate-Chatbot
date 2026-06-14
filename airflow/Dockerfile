# Airflow image cho local, kèm môi trường chạy crawler (scrapy + playwright).
#
# Crawler deps được cài vào MỘT VENV RIÊNG (/opt/crawler-venv) để KHÔNG đụng
# dependency của Airflow (airflow cũng dùng celery/redis/urllib3... dễ xung đột).
# DAG sẽ gọi python trong venv này.
FROM apache/airflow:2.9.3-python3.11

# Playwright tải browser vào path dùng chung, để airflow user đọc được lúc chạy.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

USER root

# Tạo venv riêng + cài requirements của crawler + chromium cho scrapy-playwright.
COPY Crawler/requirements.txt /tmp/crawler-requirements.txt
RUN python -m venv /opt/crawler-venv \
 && /opt/crawler-venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/crawler-venv/bin/pip install --no-cache-dir -r /tmp/crawler-requirements.txt \
 && /opt/crawler-venv/bin/playwright install --with-deps chromium \
 && chmod -R a+rX /opt/ms-playwright /opt/crawler-venv

USER airflow
