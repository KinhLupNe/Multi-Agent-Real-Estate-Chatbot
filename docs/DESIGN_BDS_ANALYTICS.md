# Thiết kế phân tích dữ liệu BĐS

## Mục tiêu
Dashboard trực quan thị trường BĐS theo `Tỉnh × Loại BĐS`, phục vụ 2 nhóm user khác nhau với góc nhìn riêng.

## Nguồn dữ liệu

- **5 ES index**: `nhamatpho_index`, `nharieng_index`, `chungcu_index`, `bietthu_index`, `dat_index`
- **~53.000 record** (snapshot 2026-05-21)
- **Field chính**:
  - `price`, `price/square`, `square` (giá / giá/m² / diện tích)
  - `post_date` + `day`, `month`, `year`
  - `address.{province, district, ward}`
  - `extra_infos.{no_bedrooms, no_bathrooms, no_floors, front_face, front_road, direction}`

### Coverage matrix đầy đủ (% docs có field non-null) — 33 fields

#### Nhóm 1 — Metadata & ID (100% cả 5 loại, dùng cho join/dedup, KHÔNG để filter)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Mục đích |
|---|---|---|---|---|---|---|
| `id` | 100% | 100% | 100% | 100% | 100% | Khóa chính |
| `post_id` | 100% | 100% | 100% | 100% | 100% | ID gốc từ source |
| `link` | 100% | 100% | 100% | 100% | 100% | URL gốc |
| `topic` | 100% | 100% | 100% | 100% | 100% | Loại BĐS (= index) |
| `estate_type` | 100% | 100% | 100% | 100% | 100% | Tên loại (vd "bán nhà mặt phố") |
| `kafka_timestamp` | 100% | 100% | 100% | 100% | 100% | Timestamp ingest |
| `created_at` | 100% | 100% | 100% | 100% | 100% | Timestamp tạo doc ES |

#### Nhóm 2 — Nội dung text (search full-text, không phải filter)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `title` | 100% | 99.9% | 100% | 100% | 100% | Hiển thị, BM25 search |
| `description` | 99.9% | 99.9% | 99.9% | 99.9% | 100% | BM25 search chi tiết |

#### Nhóm 3 — Liên hệ (98-100%)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `contact_info.phone` | 100% | 100% | 100% | 100% | 100% | Click-to-call (không phân tích) |
| `contact_info.name` | 96.4% | 98.9% | 99.1% | 99.3% | 100% | Phân biệt môi giới vs chủ |

#### Nhóm 4 — Địa lý cấp Tỉnh (99-100%)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `address.province` | 100% | 100% | 100% | 100% | 100% | ★ Filter tỉnh (chuẩn nested) |
| `province` | 100% | 99.9% | 99.7% | 99.7% | 100% | Filter tỉnh (legacy flat) |

#### Nhóm 5 — Địa lý chi tiết Quận/Phường (33-37% — yếu cho Đất)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `address.full_address` | 53.3% | 51.6% | 44.1% | 33.3% | 4.0% | Hiển thị địa chỉ |
| `address.district` | 53.2% | 51.6% | 43.6% | 33.0% | 4.0% | ★ Filter quận (nested) |
| `district` | 53.2% | 51.5% | 43.6% | 33.0% | 4.0% | Filter quận (legacy) |
| `address.ward` | 47.4% | 48.1% | 40.8% | 27.4% | 3.5% | Filter phường (nested) |
| `ward` | 47.4% | 48.1% | 40.8% | 27.4% | 3.5% | Filter phường (legacy) |

> ⚠ Đất gần như không có district/ward — query Đất theo quận sẽ trả ~4% data thật.

#### Nhóm 6 — Giá & Diện tích (★ widget chung tốt nhất, 85-100%)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `square` | 96.4% | 96.9% | 97.0% | 98.4% | 100% | ★★★ Filter diện tích, distribution m² |
| `price` | 90.9% | 91.6% | 85.4% | 87.0% | 90.4% | ★★★ Filter budget, KPI median |
| `price/square` | 89.9% | 90.0% | 83.6% | 86.0% | 90.4% | ★★★ Đơn giá m² (so sánh chéo quận/loại) |

#### Nhóm 7 — Đặc điểm nhà ở (50-85% cho 4 loại nhà, ~1% cho Đất)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `extra_infos.no_bedrooms` | 67.5% | 80.0% | 85.3% | 64.8% | 1.2% | Filter số PN (loại nhà ở) |
| `extra_infos.no_bathrooms` | 64.0% | 75.4% | 81.8% | 60.6% | 1.0% | Filter số WC (loại nhà ở) |
| `extra_infos.no_floors` | 72.9% | 74.3% | 25.6% | 75.5% | 0.8% | Filter số tầng (nhà phố/riêng/biệt thự) |

> Chung cư hợp lý ít có "số tầng" (chính nó là 1 tầng trong toà). Đất 0% → KHÔNG hiện filter này khi loại=Đất.

#### Nhóm 8 — Đặc trưng Đất (32-73%, tốt cho Đất, yếu cho khác)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `extra_infos.front_face` | 31.6% | 31.8% | 0.4% | 40.3% | 73.0% | ★ Filter mặt tiền (m) cho Đất + Biệt thự |
| `extra_infos.front_road` | 25.5% | 29.6% | 0.5% | 36.1% | 70.5% | ★ Filter đường trước (m) cho Đất |

#### Nhóm 9 — Thời gian (post_date 100%, day/month/year ~42%)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Use case |
|---|---|---|---|---|---|---|
| `post_date` | 100% | 100% | 100% | 100% | 100% | ★★ Trend, growth, peak hour |
| `day` | 55.9% | 52.7% | 43.7% | 25.6% | 33.5% | Filter ngày trong tháng (parse phụ) |
| `month` | 55.9% | 52.7% | 43.7% | 25.6% | 33.5% | Group by tháng |
| `year` | 55.9% | 52.7% | 43.7% | 25.6% | 33.5% | Group by năm |

> `day/month/year` chỉ điền cho ~42% — KHÔNG dùng làm filter. Dùng trực tiếp `post_date` (date range query) sẽ cover 100%.

#### Nhóm 10 — Field gần rỗng (BỎ HẲN khỏi UI)

| Field | Nhà phố | Nhà riêng | Chung cư | Biệt thự | Đất | Lý do |
|---|---|---|---|---|---|---|
| `extra_infos.direction` | 6.5% | 7.6% | 7.5% | 10.1% | 18.1% | Hướng nhà — crawler hiếm parse được |
| `extra_infos.ultilization_square` | 1.2% | 1.0% | 0.6% | 0.6% | 2.1% | Diện tích sử dụng — gần rỗng |
| `extra_infos.yo_construction` | 0.1% | 0.2% | 0.1% | 0.1% | 0.1% | Năm xây — gần như không có |

### Quy tắc thiết kế widget rút ra

| Tier | Coverage | Field | Khuyến nghị |
|---|---|---|---|
| Tier 1 | ≥85% all 5 | `square`, `price`, `price/square`, `post_date`, `address.province` | Widget chung mọi loại |
| Tier 2 | 50-85%, 3-4 loại | `no_bedrooms`, `no_bathrooms`, `no_floors` | Widget loại nhà ở (ẩn cho Đất) |
| Tier 3 | ≥70% 1 loại | `front_face`, `front_road` | Widget riêng Đất |
| Tier 4 | 30-50% all | `address.district`, `address.ward` | Filter có chú thích "data thưa cho Đất" |
| Tier 5 | <10% | `direction`, `ultilization_square`, `yo_construction` | **Bỏ hẳn** |

## 2 nhóm user — mối quan tâm

### A. Người mua / người tìm nhà
**Câu hỏi điển hình:**
- "Giá nhà X ở khu Y khoảng bao nhiêu?"
- "Có bao nhiêu lựa chọn dưới ngân sách Z?"
- "Khu nào giá rẻ/đắt nhất trong tỉnh?"
- "Loại nhà này diện tích trung bình là bao nhiêu?"

**Widget phục vụ:**
| Widget | Field | Mục đích |
|---|---|---|
| KPI Tổng tin / Giá median / Giá/m² median | `price`, `price/square` | Cái nhìn nhanh |
| Bar giá TB theo quận | `price`, `district` | So sánh khu |
| Bar đơn giá m² theo quận | `price/square`, `district` | So sánh khu (chuẩn hóa) |
| Bar phân khúc giá | `price` bin | Lọc theo budget |
| Pie đặc điểm (PN/WC/tầng/diện tích) | `extra_infos.*`, `square` | Hiểu cấu trúc thị trường |
| Heatmap giá trên bản đồ | `district` + `price` | Trực quan hóa địa lý |

### B. Nhà đầu tư / người làm dự án
**Câu hỏi điển hình:**
- "Quận nào đang nóng (tin đăng tăng)?"
- "Trend giá/m² 3-6 tháng gần đây?"
- "Khu nào supply nhiều mà giá thấp → cơ hội?"
- "Giờ nào trong ngày đăng bài nhiều?" (proxy hoạt động sàn)
- "Phân bố loại BĐS trong từng quận?"

**Widget đề xuất bổ sung (chưa có):**
| Widget | Field | Mục đích |
|---|---|---|
| Line trend giá/m² theo tháng | `price/square`, `post_date.month` | Tracking xu hướng |
| Line số tin mới theo tuần/ngày | `post_date` | Đo supply velocity |
| Top 10 quận tăng trưởng % | `district`, `post_date` | Spot hotspot |
| Stacked bar loại BĐS / quận | `topic`, `district` | Cơ cấu thị trường khu |
| Histogram giờ đăng | `post_date.hour` | Peak hour marketing |
| Bubble (supply, median price) | `count`, `price` per district | Tìm undervalue |

## Dimension cắt dữ liệu

| Dimension | Field | User A (mua) | User B (đầu tư) |
|---|---|---|---|
| Thời gian | `post_date` | Tin mới nhất | Trend, growth |
| Giờ trong ngày | `post_date.hour` | — | Peak hour |
| Địa điểm | `province / district / ward` | Lọc khu mình quan tâm | Heatmap supply |
| Loại BĐS | `topic` | Chọn 1 loại | So sánh giữa loại |
| Giá | `price`, `price/square` | Budget filter | Phân khúc + quartile |
| Diện tích | `square` | Filter | Distribution |
| Đặc điểm | `extra_infos.*` | Lọc số PN/WC | Insight cơ cấu |

## Layout đề xuất

```
┌────────────────────────────────────────────────────┐
│ [Filter] Tỉnh ▼   Loại BĐS ⊙ ⊙ ⊙ ⊙ ⊙             │
├────────────────────────────────────────────────────┤
│ KPI: Tổng tin | Giá median | Giá/m² median         │
├────────────────────────────────────────────────────┤
│ [Tab 1: Cho người mua]                             │
│   Giá TB / Đơn giá m² theo quận (bar)              │
│   Phân khúc giá (bar)                              │
│   Đặc điểm phổ biến (pie: diện tích/PN/tầng)       │
│   Bản đồ nhiệt giá                                 │
├────────────────────────────────────────────────────┤
│ [Tab 2: Cho nhà đầu tư] ← THÊM MỚI                │
│   Trend giá/m² theo tháng (line)                   │
│   Số tin mới 30 ngày + growth % (line)             │
│   Top 10 quận tăng trưởng (bar)                    │
│   Stacked bar loại BĐS / quận                      │
│   Peak hour đăng bài (histogram)                   │
│   Bubble supply × price (scatter)                  │
└────────────────────────────────────────────────────┘
```

## Câu hỏi khảo sát (validate với user thật)

**Cho user A:**
1. Bạn xem dashboard lúc nào: trước hay sau khi liên hệ môi giới?
2. Widget nào nhìn đầu tiên?
3. Filter dùng nhiều nhất: tỉnh / loại / giá / diện tích?
4. Có cần so sánh nhiều quận cùng lúc không?

**Cho user B:**
1. Quan tâm supply hay price hơn?
2. Time window: tuần / tháng / quý?
3. Có cần export Excel để phân tích sâu?
4. Source data (Batdongsan.com, Nhadat24h, Alonhadat...) có quan trọng?

## Roadmap

- [x] Tab "Người mua" (đã có, đã trim widget)
- [ ] Tab "Nhà đầu tư" với 6 widget thời gian + supply
- [ ] Lưu state filter user vào URL/session
- [ ] Compare mode: 2 tỉnh side-by-side
- [ ] Export CSV / PNG cho từng chart
- [ ] Alert engine: "quận X giá tăng > 10% / tháng → notify"
