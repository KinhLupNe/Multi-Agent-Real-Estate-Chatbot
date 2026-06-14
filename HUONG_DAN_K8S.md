# HƯỚNG DẪN VẬN HÀNH & KHỞI ĐỘNG TOÀN BỘ HỆ THỐNG K8S

Tài liệu này hướng dẫn bạn cách khởi động lại toàn bộ hệ thống từ đầu (sau khi tắt máy tính) và cung cấp các câu lệnh thông dụng để kiểm tra thông tin của từng phân vùng (Elasticsearch, Kafka, MinIO, Backend, Frontend).

---

## 🔄 PHẦN 1: QUY TRÌNH KHỞI ĐỘNG LẠI HỆ THỐNG (KHI BẬT MÁY)

Hãy thực hiện tuần tự theo các bước dưới đây để bật lại toàn bộ hệ thống:

### Bước 1: Mở ứng dụng Docker Desktop
- K8s (Kind) chạy trên nền Docker. Bạn phải mở **Docker Desktop** trước và đợi cho đến khi icon Docker chuyển sang màu xanh (Ready).

### Bước 2: Kiểm tra trạng thái các Pod trong K8s
- Mở PowerShell và chạy lệnh sau để kiểm tra xem các pod đã khởi động xong chưa:
  ```powershell
  kubectl get pods -A
  ```
- *Đảm bảo trạng thái của các pod trong các namespace `elastic`, `kafka`, `minio` đều hiển thị là `Running` hoặc `Completed`.*

### Bước 3: Khởi chạy luồng kết nối (Port-Forward)
- Mở một cửa sổ PowerShell mới và chạy tập lệnh tự động kết nối:
  ```powershell
  cd E:\nam4\ky2\DataScience\Project\Test
  .\start_ui.ps1
  ```
- **Lưu ý quan trọng:** Giữ nguyên cửa sổ này chạy ẩn trong suốt quá trình bạn làm việc để duy trì các đường hầm kết nối từ máy thật vào K8s.

### Bước 4: Khởi động FastAPI Backend
- Mở một cửa sổ PowerShell mới và chạy:
  ```powershell
  conda activate bds_crawler
  cd E:\nam4\ky2\DataScience\Project\Test\agent-backend
  uvicorn main:app --reload
  ```
- Backend sẽ chạy tại địa chỉ: `http://localhost:8000`

### Bước 5: Khởi động Streamlit Frontend
- Mở một cửa sổ PowerShell mới và chạy:
  ```powershell
  conda activate bds_crawler
  cd E:\nam4\ky2\DataScience\Project\Test\frontend
  streamlit run app.py
  ```
- Frontend sẽ chạy tại địa chỉ: `http://localhost:8501`

### Bước 6: Chạy Crawler (Khi cần thu thập dữ liệu)
- Mở một cửa sổ PowerShell mới và chạy:
  ```powershell
  conda activate bds_crawler
  cd E:\nam4\ky2\DataScience\Project\Test\Crawler
  python run_new.py
  ```

---

## 🛠️ PHẦN 2: CHEAT SHEET - LỆNH KIỂM TRA THÔNG TIN HỆ THỐNG

Dưới đây là tổng hợp các câu lệnh thông dụng nhất để bạn giám sát và kiểm tra dữ liệu:

### 1. Phân vùng Elasticsearch (ES)
*(Đảm bảo đã chạy `start_ui.ps1`)*

*   **Kiểm tra sức khỏe của Cluster:**
    ```powershell
    curl -u elastic:5o6gdiSRdm4O2G9Sy186T20O http://127.0.0.1:9200/_cluster/health?pretty
    ```
*   **Liệt kê toàn bộ các Index (bảng dữ liệu) đang có:**
    ```powershell
    curl -u elastic:5o6gdiSRdm4O2G9Sy186T20O http://127.0.0.1:9200/_cat/indices?v
    ```
*   **Xem tổng số bản ghi trong một Index cụ thể (ví dụ: nhamatpho_index):**
    ```powershell
    curl -u elastic:5o6gdiSRdm4O2G9Sy186T20O http://127.0.0.1:9200/nhamatpho_index/_count?pretty
    ```
*   **Truy vấn nhanh 5 bản ghi mới nhất trong index:**
    ```powershell
    curl -u elastic:5o6gdiSRdm4O2G9Sy186T20O -X GET "http://127.0.0.1:9200/nhamatpho_index/_search?pretty" -H "Content-Type: application/json" -d '{\"size\": 5, \"sort\": [{\"post_date\": \"desc\"}]}'
    ```

### 2. Phân vùng Kafka
*(Bạn có thể vào trực tiếp giao diện Web UI: **http://127.0.0.1:8080** để xem trực quan, hoặc dùng các lệnh sau)*

*   **Liệt kê toàn bộ các Topic đang có:**
    ```powershell
    kubectl exec -it my-cluster-kafka-0 -n kafka -- bin/kafka-topics.sh --bootstrap-server localhost:9092 --list
    ```
*   **Kiểm tra tin nhắn (messages) mới nhất trong một Topic (ví dụ: `nhamatpho`):**
    ```powershell
    kubectl exec -it my-cluster-kafka-0 -n kafka -- bin/kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic nhamatpho --from-beginning --max-messages 5
    ```
*   **Xem thông tin mô tả chi tiết của một Topic:**
    ```powershell
    kubectl exec -it my-cluster-kafka-0 -n kafka -- bin/kafka-topics.sh --bootstrap-server localhost:9092 --describe --topic nhamatpho
    ```

### 3. Phân vùng MinIO (Lưu trữ tệp tin)
*(Bạn có thể vào trực tiếp giao diện Web UI: **http://127.0.0.1:9001** để xem trực quan)*

*   **Kiểm tra danh sách tệp tin trong bucket `bds`:**
    Nếu bạn có cài đặt công cụ CLI `mc` (MinIO Client):
    ```powershell
    # Liệt kê thư mục trong bucket bds của K8s MinIO
    mc ls local/bds
    ```
*   **Xem thông tin cấu hình của MinIO Service trong K8s:**
    ```powershell
    kubectl describe svc minio-service -n minio
    ```

### 4. Kiểm tra Backend (FastAPI) & Frontend (Streamlit)

*   **Kiểm tra xem cổng `8000` (Backend) có đang lắng nghe kết nối không:**
    ```powershell
    Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
    ```
*   **Kiểm tra xem cổng `8501` (Frontend) có đang lắng nghe kết nối không:**
    ```powershell
    Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
    ```
*   **Tìm ID tiến trình đang chiếm dụng cổng (nếu bị lỗi Port already in use):**
    ```powershell
    # Tìm PID của cổng 8000
    (Get-NetTCPConnection -LocalPort 8000).OwningProcess
    
    # Tắt tiến trình đó đi (Thay <PID> bằng ID tìm được ở trên)
    Stop-Process -Id <PID> -Force
    ```
