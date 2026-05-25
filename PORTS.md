# Cheat Sheet — Port các dịch vụ

Tổng hợp port của Kafka / Elasticsearch / Kibana / MinIO trên cluster AWS K8s và stack Docker local, kèm lệnh xem nhanh.

## Bảng port

| Dịch vụ | Môi trường | Endpoint nội bộ | Truy cập từ ngoài |
|---|---|---|---|
| Kibana | AWS K8s | `my-kibana-kb-http:5601` (ns `elastic`) | `http://<EC2-IP>:32077` (NodePort) |
| Elasticsearch | AWS K8s | `my-es-cluster-es-http:9200` (ns `elastic`) | ClusterIP — cần port-forward |
| Kafka (internal) | AWS K8s | `my-cluster-kafka-bootstrap:9092` (ns `kafka`) | — |
| Kafka (external) | AWS K8s | listener `9094` | `<EC2-IP>:32xxx` (NodePort động) — hiện code dùng `3.107.83.111:32047` |
| MinIO API | AWS K8s | `minio-service:9000` (ns `minio`) | ClusterIP — cần port-forward / đổi NodePort |
| MinIO Console | AWS K8s | `minio-service:9001` | ClusterIP — cần port-forward / đổi NodePort |
| Elasticsearch | Local Docker | `http://127.0.0.1:9200` | — |
| Kibana | Local Docker | `http://127.0.0.1:5601` | — |

NodePort động có thể đổi khi `kubectl apply` lại — luôn check bằng lệnh dưới trước khi mở browser.

## Xem port trên AWS

SSH vào EC2 control plane trước, rồi chạy:

```bash
kubectl get svc -A
```
```bash
kubectl get svc -n elastic
```
```bash
kubectl get svc -n kafka
```
```bash
kubectl get svc -n minio
```

Lấy NodePort của 1 service cụ thể:

```bash
kubectl get svc my-kibana-kb-http -n elastic -o jsonpath='{.spec.ports[0].nodePort}'
```

Public IP của EC2 node đang chạy lệnh:

```bash
curl -s http://169.254.169.254/latest/meta-data/public-ipv4
```

Password user `elastic`:

```bash
kubectl get secret my-es-cluster-es-elastic-user -n elastic -o go-template='{{.data.elastic | base64decode}}'
```

## Xem port local (Windows / PowerShell)

```powershell
docker ps
```
```powershell
docker compose -f local_es\docker-compose.yml ps
```
```powershell
Get-NetTCPConnection -LocalPort 9200 -State Listen
```
```powershell
netstat -ano | findstr :9200
```

## Expose service ClusterIP ra ngoài

Cách 1 — port-forward tạm (chạy trên EC2 hoặc máy có kubeconfig):

```bash
kubectl port-forward -n elastic svc/my-es-cluster-es-http 9200:9200
```
```bash
kubectl port-forward -n minio svc/minio-service 9001:9001
```

Bind ra mọi interface (vd để truy cập từ máy khác qua public IP EC2):

```bash
kubectl port-forward -n minio svc/minio-service --address 0.0.0.0 9001:9001
```

Cách 2 — đổi service sang NodePort (cố định). Sửa `Config/MinIO/minio-service.yaml`:

```yaml
spec:
  type: NodePort
  ports:
  - name: api
    port: 9000
    targetPort: 9000
    nodePort: 30900
  - name: console
    port: 9001
    targetPort: 9001
    nodePort: 30901
```

Apply lại:

```bash
kubectl apply -f Config/MinIO/minio-service.yaml
```

## Security Group EC2

Mọi NodePort (32077 Kibana, 32047 Kafka, 30900/30901 MinIO...) đều phải mở inbound TCP trên Security Group, nếu không sẽ timeout dù service trong cluster vẫn lên:

```bash
aws ec2 authorize-security-group-ingress \
  --group-id <sg-xxxxx> --protocol tcp --port 32077 --cidr <your-ip>/32
```

## Lỗi thường gặp

- `kubectl ... dial tcp [::1]:8080: connection refused` — chạy `kubectl` ở máy không có kubeconfig của cluster. SSH vào EC2 control plane, hoặc copy `~/.kube/config` về Windows và sửa server URL thành public IP.
- Kibana / MinIO UI mở browser bị timeout — thiếu rule inbound trên Security Group cho NodePort tương ứng.
- Producer Kafka kết nối được bootstrap nhưng send fail — `kafka-cluster.yaml` đang advertise IP cũ (`18.170.66.185` / `18.170.66.175`). Khi EC2 reboot đổi public IP phải update `advertisedHost` trong YAML và `kubectl apply` lại.
