# Local Elasticsearch — BDS Dataset

Chạy ES + Kibana phiên bản 8.11.1 trên máy local. Mục đích: tách dữ liệu khỏi
EKS AWS để tắt cluster (tiết kiệm chi phí) mà team vẫn training AI được.

## Yêu cầu

- Docker Desktop (WSL2 enabled trên Windows)
- Node.js + elasticdump:  `npm install -g elasticdump`

## Khởi động

```powershell
cd local_es
docker compose up -d
docker compose logs -f elasticsearch   # đợi đến khi thấy "started"
```

Verify:
```powershell
curl -u elastic:z47O5lJxA1M30lB35tV8Xa4y http://localhost:9200
```

Kibana UI: http://localhost:5601  (user: `elastic`, pass: `z47O5lJxA1M30lB35tV8Xa4y`)

## Restore data lần đầu

Đảm bảo có thư mục `../es_dump/` (do người owner dump từ AWS gửi xuống).

```powershell
cd ..    # về thư mục root project
.\scripts\restore_es.ps1
```

## Dùng dataset trong code Python / Spark

```powershell
. .\scripts\load_env.ps1 .env.local
python SparkJobs\SparkBatching\main.py
```

Khi muốn quay lại trỏ AWS:
```powershell
# Terminal 1
kubectl port-forward -n elastic svc/my-es-cluster-es-http 9200:9200
# Terminal 2
. .\scripts\load_env.ps1 .env.aws
python SparkJobs\SparkBatching\main.py
```

Query syntax (ES DSL) **y hệt** — chỉ env var đổi.

## Dừng / xóa

```powershell
docker compose down          # giữ data
docker compose down -v       # xóa luôn volume (mất data)
```
