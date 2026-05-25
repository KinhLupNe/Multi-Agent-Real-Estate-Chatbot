# Scripts — ES migrate

Pipeline v3: 6 index flat schema (`nhamatpho_index`, `nharieng_index`, `chungcu_index`, `bietthu_index`, `dat_index`, `khac_index`). Script tự skip index nào không có dump (vd: chưa crawl `khac_index`).

## Quy trình cho người owner (bạn — host data từ AWS về)

```powershell
# 1. Port-forward ES AWS (terminal riêng, giữ chạy). Tên svc check bằng:
#    kubectl get svc -n elastic
kubectl port-forward -n elastic svc/my-es-cluster-es-http 9200:9200

# 2. Set password rồi dump (script đọc 6 index v3 mặc định)
$env:ES_PASS = "z47O5lJxA1M30lB35tV8Xa4y"
.\scripts\dump_es.ps1
# → tạo ra es_dump/ với tối đa 18 file (6 index × 3 type)

# 3. Tắt port-forward (Ctrl+C terminal kia), tắt AWS được rồi. Bật ES local:
docker compose -f local_es\docker-compose.yml up -d elasticsearch
.\scripts\init_kibana_user.ps1
docker compose -f local_es\docker-compose.yml up -d kibana

# 4. Restore vào ES local
.\scripts\restore_es.ps1

# 5. Verify
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y http://localhost:9200/_cat/indices?v
```

## Chỉ dump 1 vài index

```powershell
.\scripts\dump_es.ps1 -Indices nhamatpho_index,dat_index
.\scripts\restore_es.ps1 -Indices nhamatpho_index,dat_index
```

## Quy trình cho teammate (chỉ nhận dữ liệu từ bạn)

```powershell
# 1. Giải nén es_dump.zip do owner share
Expand-Archive es_dump.zip -DestinationPath .

# 2. Khởi động ES local
cd local_es; docker compose up -d; cd ..

# 3. Restore
.\scripts\restore_es.ps1

# 4. Load env và train
. .\scripts\load_env.ps1 .env.local
python your_training_script.py
```

## Đóng gói gửi team

```powershell
Compress-Archive -Path es_dump\* -DestinationPath es_dump.zip
# Cùng với folder local_es\, scripts\, .env.local — upload Drive/share USB
```
