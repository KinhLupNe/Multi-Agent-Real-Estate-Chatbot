# Airflow (Docker, local) — Lập lịch Crawler BĐS

DAG `crawler_bds_to_kafka` chạy `Crawler/run_new.py` **2 lần/ngày** (06:00 & 18:00 giờ VN) → crawl BĐS → đẩy lên Kafka (broker trên AWS).

Airflow chạy bằng Docker (Windows không chạy Airflow native được). Crawler chạy **trong container**, dùng venv riêng `/opt/crawler-venv` (scrapy + playwright + confluent_kafka) tách khỏi deps Airflow.

## Chạy

> Mở **Docker Desktop** trước.

```bash
cd airflow
docker compose up -d --build      # lần đầu build image (lâu: cài playwright + chromium)
```

- UI: http://localhost:8080 — đăng nhập `admin` / `admin`
- Bật toggle DAG `crawler_bds_to_kafka` → tự chạy 6h & 18h.
- Chạy thủ công ngay: nút **Trigger DAG** trên UI.
- Tắt: `docker compose down` (thêm `-v` để xoá luôn DB).

Crawler ghi `crawled_data/` và `logs/` vào `../Crawler` trên host (vì mount volume), xem trực tiếp ở đó.

## Đổi lịch

Sửa `schedule="0 6,18 * * *"` trong `dags/crawler_bds_dag.py` rồi đợi scheduler nạp lại (vài giây) — không cần build lại.

## Lỗi hay gặp

- **Mọi task báo `kafka_connect` / `Broker: No nodes available`**: AWS instance chứa Kafka (`3.107.83.111:32047`) đang tắt → bật lên trước.
- **Build lâu / nặng**: image cài playwright + chromium + pyspark nên ~vài GB, lần đầu build chậm là bình thường.
- **DAG không hiện trên UI**: kiểm tra log scheduler `docker compose logs airflow-scheduler` — thường do lỗi import trong file DAG.
- **Đổi `requirements.txt` của crawler**: phải build lại image `docker compose up -d --build`.
