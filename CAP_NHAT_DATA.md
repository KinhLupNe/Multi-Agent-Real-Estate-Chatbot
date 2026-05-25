# Cập nhật Dataset từ AWS về Local

Dùng file này khi crawler đã chạy xong, ES trên AWS có data mới, muốn pull về ES local để team training tiếp.

## Tổng quan 3 terminal

| Terminal | Ở đâu | Làm gì | Đóng khi nào |
|---|---|---|---|
| **EC2 #1** | SSH vào EC2 | `kubectl port-forward` | Sau khi dump xong (bước 3) |
| **Windows #1** | PowerShell local | SSH tunnel `-L 9200:9200` | Sau khi dump xong (bước 4) |
| **Windows #2** | PowerShell local | Chạy dump + restore | Khi xong |

## Bước 1 — Terminal EC2 #1: Mở port-forward

SSH vào EC2 (cách bạn vẫn dùng), rồi chạy:

```bash
kubectl port-forward -n elastic svc/my-es-cluster-es-http 9200:9200
```

Để terminal này yên. Sẽ thấy 2 dòng:
```
Forwarding from 127.0.0.1:9200 -> 9200
Forwarding from [::1]:9200 -> 9200
```

## Bước 2 — Terminal Windows #1: Mở SSH tunnel

Mở **PowerShell mới** trên Windows, vào thư mục chứa file `.pem` (vd `ikk.pem`):

```powershell
ssh -i "ikk.pem" -L 9200:localhost:9200 ubuntu@ec2-3-107-83-111.ap-southeast-2.compute.amazonaws.com
```

Vào được shell EC2 là tunnel hoạt động. **Không gõ `exit`** — giữ session sống suốt quá trình dump.

Hoặc nếu chỉ cần tunnel không cần shell (chạy nền, gọn hơn):
```powershell
ssh -i "ikk.pem" -N -L 9200:localhost:9200 ubuntu@ec2-3-107-83-111.ap-southeast-2.compute.amazonaws.com
```
`-N` = không exec command, chỉ tunnel. Đóng bằng `Ctrl+C` khi xong.

## Bước 3 — Terminal Windows #2: Dump data

Mở **PowerShell mới thứ 2** trên Windows, vào thư mục project:

```powershell
cd E:\nam4\ky2\DataScience\Project\Test
```

Test tunnel có thông không:

```powershell
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y http://127.0.0.1:9200/_cat/indices?v
```

Phải thấy 6 indices (pipeline v3, flat schema): `nhamatpho_index`, `nharieng_index`, `chungcu_index`, `bietthu_index`, `dat_index`, `khac_index`. Index nào chưa có data có thể không xuất hiện. Ghi nhớ `docs.count` từng index để lát so với local.

Dump:

```powershell
$env:ES_PASS = "z47O5lJxA1M30lB35tV8Xa4y"
.\scripts\dump_es.ps1
```

Mỗi index in ra dạng:
```
==> Dumping [nhamatpho_index]
... | got 1000 objects from source file
... | dump complete
    Done.
```

Kết thúc thấy `All indices dumped into es_dump/` là OK. Nếu 1 index nào AWS chưa có (vd: `khac_index` chưa crawl) → script sẽ throw, chỉ định lại list bằng:
```powershell
.\scripts\dump_es.ps1 -Indices nhamatpho_index,nharieng_index,chungcu_index,bietthu_index,dat_index
```

## Bước 4 — Đóng tunnel + giải phóng port 9200

> ⚠️ **BẮT BUỘC LÀM TRƯỚC khi restore (Bước 7).** Nếu quên đóng:
> - SSH tunnel vẫn chiếm `127.0.0.1:9200` (tunnel bind cụ thể IP, ưu tiên hơn Docker bind `0.0.0.0`).
> - `restore_es.ps1` sẽ ghi data NGƯỢC lên AWS chứ không phải local Docker.
> - Local Docker ES vẫn ở data cũ → Kibana 5601 hiển thị số khác curl shell → tốn 1 tiếng debug.

**Cách 1**: quay về Terminal Windows #1, gõ:

```powershell
exit
```

Terminal EC2 #1 cũng có thể Ctrl+C lúc này — không cần nữa.

**Verify tunnel đã đóng**:
```powershell
netstat -ano | findstr :9200
```
- Trước khi đóng: thấy nhiều dòng `LISTENING` với PID của `ssh.exe`.
- Sau khi đóng: chỉ còn PID của `com.docker.backend` (Docker Desktop) bind `0.0.0.0:9200`.

Còn nghi ngờ thì check cluster name:
```powershell
curl.exe -s -u elastic:z47O5lJxA1M30lB35tV8Xa4y http://127.0.0.1:9200/ | findstr cluster_name
```
- `"cluster_name" : "docker-cluster"` → đang trỏ Docker local ✅
- `"cluster_name" : "my-es-cluster"` → vẫn đang trỏ AWS qua tunnel ❌, đóng tunnel + retry.

## Bước 5 — Đảm bảo ES local đang chạy

```powershell
docker compose -f local_es\docker-compose.yml up -d
docker compose -f local_es\docker-compose.yml ps
```

Cả `es-local` và `kibana-local` đều phải `Up (healthy)` (Kibana mất thêm ~1 phút sau khi ES healthy).

## Bước 6 — Xóa data cũ trên local (mirror chính xác AWS)

Mặc định `elasticdump` chỉ thêm + update theo `_id`, doc bị xóa trên AWS vẫn còn ở local. Để local **mirror chính xác** AWS, xóa index cũ trước khi restore:

```powershell
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y -X DELETE `
  "http://127.0.0.1:9200/nhamatpho_index,nharieng_index,chungcu_index,bietthu_index,dat_index,khac_index"
```

Verify đã xóa (`indices` list rỗng hoặc chỉ còn system index `.kibana_*`):

```powershell
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y http://127.0.0.1:9200/_cat/indices?v
```

> Nếu chỉ muốn **append** (không cần mirror chính xác) → skip bước này.

## Bước 7 — Restore vào ES local

```powershell
.\scripts\restore_es.ps1
```

Khi thấy `All indices restored.` là xong. Script đọc settings + mapping + data từ `es_dump/` đẩy vào local.

## Bước 8 — Verify

```powershell
curl.exe -u elastic:z47O5lJxA1M30lB35tV8Xa4y "http://127.0.0.1:9200/_cat/indices?v"
```

So `docs.count` từng index với số đã ghi nhớ ở Bước 3. Khớp = sync xong.

## Bước 9 — Restart backend dùng local

`agent-backend/.env` đã trỏ `ES_HOST=127.0.0.1`. Restart để pickup:

```powershell
cd agent-backend
uvicorn main:app --reload
```

Test bằng 1 widget dashboard hoặc câu chat → data đến từ local.

---

## Dọn dump cũ schema khác (1 lần)

Trong `es_dump/` còn file của 4 index nested schema cũ (`nhapho_index_*`) — không dùng được với code v3 flat schema. Xóa cho gọn:

```powershell
Remove-Item es_dump\nhapho_index_*.json
```
