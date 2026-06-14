# Kịch bản tự động mở toàn bộ luồng kết nối UI cho K8s
# Chạy script này và để cửa sổ dòng lệnh mở.

Write-Host "Dang don dep cac tien trinh port-forward cu..." -ForegroundColor Yellow
# Dừng các tiến trình kubectl port-forward đang chạy ngầm để tránh xung đột cổng
Get-CimInstance Win32_Process -Filter "name = 'kubectl.exe'" | Where-Object { $_.CommandLine -like "*port-forward*" } | ForEach-Object { 
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue 
}
Start-Sleep -Seconds 2

Write-Host "Dang khoi dong cac duong ham ket noi toi Kubernetes..." -ForegroundColor Green

# 1. Elasticsearch API
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-es-cluster-es-http 9200:9200 -n elastic`""
Write-Host "[OK] Elasticsearch API: 127.0.0.1:9200" -ForegroundColor Cyan

# 2. Kibana UI
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-kibana-kb-http 5601:5601 -n elastic`""
Write-Host "[OK] Kibana UI: 127.0.0.1:5601" -ForegroundColor Cyan

# 3. MinIO UI & API
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/minio-service 9000:9000 9001:9001 -n minio`""
Write-Host "[OK] MinIO Web UI: 127.0.0.1:9001" -ForegroundColor Cyan

# 4. Kafka Bootstrap Server & Brokers (External NodePort Listener)
Write-Host "Dang truy van cong NodePort cua Kafka..." -ForegroundColor Yellow
$bootstrapNodePort = (kubectl get svc my-cluster-kafka-external-bootstrap -n kafka -o jsonpath='{.spec.ports[0].nodePort}').Trim()
$broker0NodePort = (kubectl get svc my-cluster-broker-0 -n kafka -o jsonpath='{.spec.ports[0].nodePort}').Trim()
$broker1NodePort = (kubectl get svc my-cluster-broker-1 -n kafka -o jsonpath='{.spec.ports[0].nodePort}').Trim()
$broker2NodePort = (kubectl get svc my-cluster-broker-2 -n kafka -o jsonpath='{.spec.ports[0].nodePort}').Trim()

if ([string]::IsNullOrEmpty($bootstrapNodePort)) {
    Write-Host "[WARNING] Khong lay duoc cong NodePort cua Kafka. Dung mac dinh 31608, 32491, 32626, 30672" -ForegroundColor Yellow
    $bootstrapNodePort = "31608"
    $broker0NodePort = "32491"
    $broker1NodePort = "32626"
    $broker2NodePort = "30672"
}

Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-cluster-kafka-external-bootstrap ${bootstrapNodePort}:9094 -n kafka`""
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-cluster-broker-0 ${broker0NodePort}:9094 -n kafka`""
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-cluster-broker-1 ${broker1NodePort}:9094 -n kafka`""
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/my-cluster-broker-2 ${broker2NodePort}:9094 -n kafka`""

Write-Host "[OK] Kafka Bootstrap External: 127.0.0.1:$bootstrapNodePort" -ForegroundColor Cyan
Write-Host "[OK] Kafka Broker 0: 127.0.0.1:$broker0NodePort" -ForegroundColor Cyan
Write-Host "[OK] Kafka Broker 1: 127.0.0.1:$broker1NodePort" -ForegroundColor Cyan
Write-Host "[OK] Kafka Broker 2: 127.0.0.1:$broker2NodePort" -ForegroundColor Cyan

# 5. Kafka UI
Start-Process -NoNewWindow powershell -ArgumentList "-NoProfile -Command `"kubectl port-forward svc/kafka-ui-service 8080:8080 -n kafka`""
Write-Host "[OK] Kafka UI: 127.0.0.1:8080" -ForegroundColor Cyan

Write-Host "`n>>> TOAN BO HE THONG DA SAN SANG! <<<" -ForegroundColor Green
Write-Host "Vui long KHONG tat cua so nay. Nhan Ctrl+C de dung tat ca." -ForegroundColor Yellow

# Giữ script không bị thoát
while ($true) {
    Start-Sleep -Seconds 3600
}
