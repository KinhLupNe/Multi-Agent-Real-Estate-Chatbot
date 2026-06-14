"""DAG lập lịch crawler BĐS → đẩy lên Kafka (AWS), chạy 2 lần/ngày.

Thiết kế: DAG chỉ GỌI LẠI orchestrator `run_new.py` (đã có sẵn multiprocessing
pool, detect lỗi Kafka/HTTP/site, ghi log, đếm message delivered). Không xé nhỏ
fan-out đó thành từng Airflow task để khỏi mất logic xử lý lỗi/log hiện có.

Chạy trong Docker (xem airflow/docker-compose.yml):
- Code crawler mount tại /opt/crawler (= ../Crawler trên host).
- Crawler deps nằm trong venv riêng /opt/crawler-venv (tách khỏi deps Airflow).

LƯU Ý: Kafka broker (3.107.83.111:32047) nằm trên AWS — phải đang bật thì crawl
mới đẩy được. Broker tắt thì mọi task sẽ báo lỗi 'kafka_connect'.
"""

from __future__ import annotations

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

LOCAL_TZ = pendulum.timezone("Asia/Ho_Chi_Minh")

default_args = {
    "owner": "data-team",
    "retries": 1,
    "retry_delay": pendulum.duration(minutes=10),
}

with DAG(
    dag_id="crawler_bds_to_kafka",
    description="Crawl BĐS (bds.com.vn + bds68.com.vn) → đẩy lên Kafka, 2 lần/ngày",
    default_args=default_args,
    # 06:00 và 18:00 giờ VN mỗi ngày
    schedule="0 6,18 * * *",
    start_date=pendulum.datetime(2026, 6, 14, tz=LOCAL_TZ),
    catchup=False,
    max_active_runs=1,  # không cho 2 lần crawl chồng nhau
    # crawl full 63 tỉnh × nhiều loại BĐS có thể chạy lâu — cho timeout rộng
    dagrun_timeout=pendulum.duration(hours=8),
    tags=["bds", "crawler", "kafka"],
) as dag:

    BashOperator(
        task_id="run_crawler_push_kafka",
        # PATH trỏ vào venv crawler để cả `python` lẫn `scrapy` (subprocess) đều
        # dùng đúng môi trường có scrapy/playwright/confluent_kafka.
        bash_command=(
            "export PATH=/opt/crawler-venv/bin:$PATH && "
            "cd /opt/crawler && "
            "python run_new.py --no-reverse"
        ),
        # run_new.py tự exit 0 kể cả khi vài task lỗi (nó tổng hợp status),
        # nên task Airflow chỉ fail khi script crash thật sự.
    )
