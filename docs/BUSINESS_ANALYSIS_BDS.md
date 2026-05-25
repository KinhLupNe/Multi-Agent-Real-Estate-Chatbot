# Phân tích nghiệp vụ — Khi xem dữ liệu BĐS

> File này KHÔNG nói về schema hay biểu đồ — nó nói về **góc nhìn** khi đọc dữ liệu BĐS:
> ai đang xem, họ muốn trả lời câu gì, số nào đáng tin, số nào nên ngờ.

---

## 1. Bối cảnh thị trường VN

- BĐS là tài sản lớn nhất của hộ gia đình VN trung bình.
- Thị trường **kém minh bạch**: giá rao ≠ giá giao dịch, không có MLS (Multiple Listing Service) như Mỹ.
- Source data chủ yếu: tin rao của môi giới trên sàn (Batdongsan, Alonhadat, Nhadat24h...).
- ⇒ Dashboard này **không phải** chân lý thị trường. Nó là **proxy** từ supply rao bán, lệch sang phía môi giới và lệch sang phía giá kỳ vọng (asking price).

## 2. Ai xem dữ liệu BĐS — và họ muốn quyết định gì?

| Stakeholder | Quyết định họ cần ra | Loại câu hỏi |
|---|---|---|
| **Người mua/thuê cá nhân** | Có nên xuống tiền căn này không? Trả giá bao nhiêu? | "Giá khu này khoảng bao nhiêu?" "Căn này có quá đắt không?" |
| **Môi giới** | Tin nào dễ chốt? Khu nào đang hot để chạy ads? | "Tin tăng nhanh nhất ở đâu?" "Buyer profile khu X?" |
| **Nhà đầu tư cá nhân (lướt sóng / dài hạn)** | Mua khu nào, lúc nào, lướt hay giữ? | "Quận nào growth nhanh nhưng giá còn thấp?" "Khi nào giá đỉnh?" |
| **Chủ dự án / Developer** | Định giá căn hộ mới? Pricing strategy? Khu nào còn cầu? | "Median giá/m² khu này 2 năm qua?" "Phân khúc nào supply yếu?" |
| **Phân tích thị trường / Báo chí / Nhà nước** | Báo cáo xu hướng vĩ mô | "Thị trường có dấu hiệu bong bóng không?" "Khu vực nào cần can thiệp?" |
| **Ngân hàng / Định giá tài sản thế chấp** | Định giá tài sản đảm bảo | "Giá tham chiếu phường X cho căn Y m²?" |

Mỗi stakeholder nhìn **cùng một biểu đồ** nhưng quan tâm **khía cạnh khác nhau** — design dashboard phải có chế độ view tách bạch (xem [`DESIGN_BDS_ANALYTICS.md`](DESIGN_BDS_ANALYTICS.md) Tab A / Tab B).

## 3. KPI nghiệp vụ (khác KPI kỹ thuật)

KPI kỹ thuật (tổng tin, giá median) là **đo lường tức thời**. KPI nghiệp vụ là **diễn giải**:

| KPI nghiệp vụ | Công thức (đề xuất từ data hiện có) | Ý nghĩa |
|---|---|---|
| **Mức rao chênh giữa quận** | (P95 - P5) của price/m² theo quận | Quận nào chia tầng cao-thấp rõ rệt → có thể arbitrage |
| **Tốc độ tăng giá** | (median price tháng N) / (median price tháng N-3) - 1 | Hotspot khi >5%/tháng |
| **Supply velocity** | Số tin mới 7 ngày / 30 ngày trước | >1.5x → thị trường đang nóng phía bán |
| **Mức độ tập trung môi giới** | % tin có `contact_info.name` lặp lại ≥5 lần | Cao → tin "ma", giá rao kém phản ánh thực |
| **Coverage địa lý** | % tin có `district` non-null trong tỉnh | <50% → kết quả per-quận không đại diện |
| **Skew giá** | (mean - median) / median | >50% → có outlier mạnh, ưu tiên đọc median |
| **Thanh khoản proxy** | Số tin biến mất khỏi DB sau N ngày | Không có data direct (cần snapshot) |

## 4. Cách đọc số — kỹ năng cơ bản

### a. Median vs Mean
BĐS giá phân phối **right-skewed** (vài căn 200 tỷ kéo mean lên). **Luôn dùng median** để đại diện. Mean chỉ dùng khi cần tính tổng giá trị thị trường.

### b. Giá tuyệt đối vs Giá/m²
- "Quận Hoàn Kiếm giá median 30 tỷ" — vô nghĩa nếu không biết diện tích.
- "Hoàn Kiếm 350 triệu/m², Hà Đông 80 triệu/m²" — so sánh đúng.
- Dùng `price/square` khi so sánh **khu vs khu** hoặc **loại vs loại**.

### c. Outlier (parse sai từ crawler)
- Giá = 1 đồng / 0 VNĐ → tin "liên hệ" — đã filter ở `PRICE_MIN = 1`.
- Giá > 1.000 tỷ → parse sai (thường chữ "triệu/m²" thành "triệu" tổng).
- Diện tích < 10m² → crawler nhầm "5 tầng" thành "5m²".
- Giá/m² > 5 tỷ/m² → đất vàng HN tối đa ~1 tỷ/m², trên đó là sai.
→ Filter cứng trong `elasticsearch_queries.py:30-35`.

### d. Confounder: cấu trúc supply đổi
"Median giá tháng này tăng 10%" có 2 cách giải thích:
1. **Giá thực sự tăng** — nhu cầu tăng.
2. **Cấu trúc tin đổi** — tháng này nhiều môi giới đăng tin nhà cao cấp hơn, không phải giá tăng.

→ Khi báo cáo trend, **kèm theo phân bố loại BĐS theo tháng** để loại confounder.

### e. Coverage không đều
- Đất hầu như không có `district`/`no_floors` → KHÔNG so sánh Đất với các loại khác trên metric phụ thuộc field này.
- Chung cư không có `no_floors` (hiển nhiên, nó nằm trong toà) — coverage 26% là noise.

## 5. Bias & giới hạn của data crawl

| Bias | Hệ quả |
|---|---|
| **Source bias** | 1-2 sàn rao chiếm 80% tin → bias kiểu khách hàng của sàn đó (vd alonhadat thiên về tỉnh lẻ, batdongsan.com.vn nặng HN/HCM) |
| **Tin "ma"** (cùng căn đăng nhiều môi giới) | Count tin ≠ count căn thật. Phải dedup theo `address + price ± 5% + square ± 5%` |
| **Giá rao ≠ giá giao dịch** | Giá rao thường cao hơn 5-15% so với giá chốt thực |
| **Post_date = ngày đăng tin** | Không phải ngày bán. Tin có thể nằm đó nhiều tháng. |
| **Survivor bias** | Tin "đã bán" thường bị môi giới gỡ → DB chỉ thấy tin còn rao = supply tồn |
| **Coverage Đất thưa cấp quận** | Đất ở tỉnh lẻ không có địa chỉ chi tiết, không thể analytics quận-level |
| **Không có demand-side** | Data chỉ có **supply** (tin rao). Demand (lượt xem, lượt liên hệ) không có. |

## 6. Workflow điển hình — đọc dashboard

### Người mua (user A) — flow
```
1. Chọn tỉnh → loại BĐS
2. Xem KPI median giá/m² → đặt expectation
3. Xem bar giá theo quận → khoanh vùng quận khả thi
4. Xem distribution diện tích → ước lượng size phù hợp budget
5. Vào chatbot hỏi cụ thể: "Cho list nhà phố Cầu Giấy 5-7 tỷ, ≥50m²"
6. Click link tin → contact môi giới
```

### Nhà đầu tư (user B) — flow
```
1. Chọn tỉnh
2. Xem trend giá/m² 12 tháng theo quận → spot quận growth >5%/tháng
3. Xem supply velocity (tin mới / 30 ngày trước) → confirm khu hot
4. Xem bubble (supply, median price) → tìm khu supply thấp + giá thấp (arbitrage)
5. Đối chiếu với phân bố loại BĐS theo tỉnh → loại nào dominate
6. Quyết định: mua khu nào, loại gì
```

### Developer / chủ dự án — flow
```
1. Chọn tỉnh nơi sắp launch
2. Xem distribution diện tích các căn đang rao → định size mới phù hợp gap
3. Xem giá/m² median quận đó → định giá launch ±10% so với median
4. Xem peak hour đăng bài → schedule ads campaign
5. Xem top môi giới hoạt động → lên kế hoạch partner B2B
```

## 7. Câu hỏi PHẢI tự hỏi khi xem mọi biểu đồ

1. **Mẫu này đại diện cho cái gì?** (toàn thị trường? Chỉ supply rao? Chỉ 1 sàn?)
2. **Số liệu mới đến đâu?** (post_date có recent không, hay snapshot 6 tháng trước?)
3. **Coverage có đủ không?** (n < 100 → mọi median đều noise)
4. **Mean hay Median?** (BĐS LUÔN dùng median trừ khi tính tổng GTV)
5. **Có outlier không?** (đỉnh nhọn vô lý ở 1 bin → check parse error)
6. **Confounder?** (giá tăng do giá hay do cấu trúc supply đổi?)
7. **Trend hay snapshot?** (1 con số trung bình không cho biết hướng đi)

## 8. Cảnh báo về kết luận thường gặp (anti-pattern)

| Câu nói sai | Tại sao sai | Cách nói đúng |
|---|---|---|
| "Quận X giá BĐS tăng 20% năm nay" | Có thể là `price` tăng do diện tích trung bình tăng | "Giá/m² tăng X%, diện tích trung bình tăng Y%" |
| "Thị trường nóng, tin tăng 50%" | Có thể do thêm môi giới crawl được, không phải nhu cầu | "Số tin tăng 50%, kèm số môi giới unique tăng Z%" |
| "Khu Y rẻ nhất tỉnh" | Có thể coverage tin khu Y thấp, mẫu nhỏ | "Median giá khu Y thấp nhất (n=N tin)" |
| "Đất Y triệu/m² ở tỉnh Z" | Đất phụ thuộc front_road, mặt tiền, pháp lý — số đơn giá chỉ là gợi ý | "Median Y, range [P25, P75]; lưu ý đất phụ thuộc giấy tờ" |

## 9. Liên kết các kỹ năng → dashboard

| Kỹ năng nghiệp vụ | Widget phục vụ trong dashboard |
|---|---|
| Đặt expectation giá | KPI median + bar quận |
| Loại outlier khi đọc | Distribution price (xem skewness) + phân khúc giá |
| Đo trend | Line trend giá/m² theo tháng (cần thêm) |
| Đo hotspot | Top quận growth% (cần thêm) |
| Đánh giá đại diện | Số tin per quận (đã có gián tiếp qua bar count) |
| Phát hiện cấu trúc đổi | Stacked bar loại BĐS / tháng (cần thêm) |

## 10. Tài liệu liên quan

- [`DESIGN_AGENT_ARCHITECTURE.md`](DESIGN_AGENT_ARCHITECTURE.md) — backend chatbot xử lý query thế nào
- [`DESIGN_BDS_ANALYTICS.md`](DESIGN_BDS_ANALYTICS.md) — chi tiết widget + coverage field
- `research_common_fields.py` (root) — script verify coverage khi data thay đổi
