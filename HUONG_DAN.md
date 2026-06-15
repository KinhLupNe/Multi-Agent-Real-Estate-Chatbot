# Dataset BDS cho Training AI

Dataset bất động sản (~5000 record) lưu trong Elasticsearch chạy local. File này chỉ hướng dẫn **cài đặt** — cách query thì team tự tìm hiểu (Elasticsearch DSL, Python `elasticsearch` client).

## Cài 1 lần

Cài sẵn: [Docker Desktop](https://www.docker.com/products/docker-desktop) + [Node.js](https://nodejs.org).

Mở PowerShell trong thư mục đã giải nén, chạy 5 lệnh sau theo thứ tự:

```powershell
npm install -g elasticdump
```
```powershell
docker compose -f local_es\docker-compose.yml up -d elasticsearch
```
```powershell
.\scripts\init_kibana_user.ps1
```
```powershell
docker compose -f local_es\docker-compose.yml up -d kibana
```
```powershell
.\scripts\restore_es.ps1
```

## Verify

```powershell
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y "http://127.0.0.1:9200/_cat/indices?v"
```

Phải thấy 6 indices (pipeline v3, flat schema): `nhamatpho_index`, `nharieng_index`, `chungcu_index`, `bietthu_index`, `dat_index`, `khac_index`. Index nào chưa có data sẽ không xuất hiện.

## Thông tin kết nối

| | |
|---|---|
| ES endpoint | `http://127.0.0.1:9200` |
| Kibana UI | http://localhost:5601 |
| User | `elastic` |
| Pasrword | 5o6gdiSRdm4O2G9Sy186T20O|

Dùng các thông tin này trong code training của bạn.

## Bật / tắt

```powershell
# Tắt khi không dùng
docker compose -f local_es\docker-compose.yml stop

# Bật lại
docker compose -f local_es\docker-compose.yml start
```

## Sau này khi đổi sang server thật

Code training không cần sửa. Chỉ đổi 4 thông tin kết nối phía trên (host, port, user, password) là trỏ sang ES production.

## Vướng mắc

Hỏi owner package.
