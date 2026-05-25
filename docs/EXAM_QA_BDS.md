# Bộ câu hỏi bảo vệ — Dự án BĐS Chatbot & Analytics

20 câu thầy có thể hỏi + gợi ý cách trả lời. Mỗi gợi ý kèm con số cụ thể từ data thật (53.000 record, 5 ES index), tránh nói chung chung.

> **Mẹo trả lời**: luôn dẫn ra số / file / công thức cụ thể, không nói "khá tốt / khá ổn / về cơ bản".

---

## A. NGHIỆP VỤ BĐS (7 câu)

### 1. Sản phẩm này phục vụ ai? User chính là ai?
- 2 nhóm chính: **người mua/thuê cá nhân** (cần định giá khu, lựa chọn) và **nhà đầu tư cá nhân** (cần trend, hotspot).
- Phụ: môi giới (định giá tin đăng), developer (research khu launch), ngân hàng (định giá thế chấp).
- Lý do tách 2 user → 2 tab dashboard riêng (xem `DESIGN_BDS_ANALYTICS.md`).

### 2. Tại sao chọn đúng 5 loại BĐS? Vì sao không có "cho thuê"?
- 5 loại: nhà mặt phố, nhà riêng, chung cư, biệt thự, đất — phủ ~95% tin rao trên thị trường mua bán.
- Đã từng có "cho thuê": kiểm tra ES → coverage gần 0% (crawler chưa cover đầy đủ) → **xóa option** để không lừa user (commit `nhamatpho` không có rent data trả về 0).

### 3. KPI nghiệp vụ quan trọng nhất là gì?
- **Median giá/m² theo quận** — chuẩn hóa được giữa khu (so với giá tuyệt đối phụ thuộc diện tích).
- **Supply velocity** = tin mới 7d / tin mới 30d trước → đo nhiệt thị trường.
- **Skew (mean - median)/median** → phát hiện outlier/cấu trúc data lệch.
- Tổng tin / total listings là metric phụ — không đại diện thị trường thật vì có tin "ma".

### 4. Em phân biệt người mua và nhà đầu tư thế nào về mặt data?
| | Người mua | Nhà đầu tư |
|---|---|---|
| Quan tâm | Snapshot hiện tại | Trend theo thời gian |
| Filter chính | Tỉnh + giá + loại | Tỉnh + thời gian |
| Widget | KPI, bar quận, pie đặc điểm | Line trend, growth %, supply-vs-price scatter |
| Output | "Tìm 5 căn phù hợp" | "Quận X đang tăng 8%/tháng" |

### 5. Số liệu dashboard có đại diện thị trường thật không?
- KHÔNG hoàn toàn. Đây là **proxy từ supply rao**, không phải giao dịch thật.
- 3 lệch chính: (a) Source bias — chỉ 1-2 sàn; (b) Tin ma — 1 căn nhiều môi giới rao; (c) Giá rao cao hơn giá chốt 5-15%.
- Xem chi tiết `BUSINESS_ANALYSIS_BDS.md` mục "Bias & giới hạn".
- Mitigation đã làm: filter cứng `PRICE_MIN/MAX`, `SQUARE_MIN/MAX` trong `elasticsearch_queries.py`.

### 6. Em xử lý outlier thế nào?
4 loại outlier đã filter ở `elasticsearch_queries.py:30-35`:
- `price = 0` (tin "liên hệ") → filter `PRICE_MIN = 1`
- `price > 1.000 tỷ` → parse sai → `PRICE_MAX = 1_000_000_000_000`
- `price/square > 5 tỷ/m²` → đất vàng HN max ~1 tỷ/m² → `PRICE_PER_SQ_MAX = 5_000_000_000`
- `square < 10m²` → crawler nhầm "5 tầng" thành "5m²" → `SQUARE_MIN = 10`

Sau filter còn 89-97% data tùy loại — đủ representative.

### 7. Tại sao dùng median, không dùng mean để đại diện giá?
- BĐS phân phối **right-skewed** (vài căn 200 tỷ kéo mean lên).
- Skew ratio `(mean - median) / median` thực tế ~50-100% → mean lệch nghiêm trọng.
- Mean chỉ dùng khi tính tổng GTV thị trường (cho nhà nước / báo cáo vĩ mô).

---

## B. DỮ LIỆU BĐS (7 câu)

### 8. Em có bao nhiêu data? Crawl từ đâu? Tần suất?
- ~53.000 record tính tới snapshot 2026-05-21.
- 5 ES index: `nhamatpho_index`, `nharieng_index`, `chungcu_index`, `bietthu_index`, `dat_index`.
- Source: Scrapy spider crawl Batdongsan.com.vn, Alonhadat, Nhadat24h... (xem `Crawler/crawlerbds/spiders/`).
- Pipeline: Scrapy → Kafka (6 topic) → Spark Streaming/Batching → MinIO + ES (Strimzi K8s).
- Tần suất: spider chạy theo cron, batch ingest mỗi vài giờ.

### 9. Coverage field thấp em xử lý ra sao? (vd direction 10%, no_floors chung cư 26%)
3 nguyên tắc:
- **Coverage ≥85% cả 5 loại** (square, price, price/m²) → widget chung mọi loại.
- **Coverage 50-85% với 3-4 loại** (no_bedrooms, no_floors) → widget hiển thị có ĐIỀU KIỆN, ẩn cho loại không có data (vd ẩn `no_floors` khi chọn Chung cư hoặc Đất).
- **Coverage <10%** (direction, yo_construction) → **bỏ hẳn** khỏi UI, không cố nhồi.

Tất cả pie chart đều có slice "Chưa rõ" tô màu xám để **honest** về missing data, không giả vờ data đầy đủ.

### 10. Tại sao dùng Elasticsearch thay vì PostgreSQL / MongoDB?
- **Search full-text tiếng Việt** (title, description) → ES BM25 sẵn có, tokenizer Vietnamese tốt.
- **Aggregation nhanh** cho dashboard (percentiles, histogram, terms) — ES tối ưu hơn SQL khi không có index sẵn.
- **Schema linh hoạt** — `extra_infos.*` mỗi loại BĐS field khác nhau → ES dynamic mapping.
- **Tích hợp Kibana** sẵn để dev debug.
- Trade-off: ES không tốt cho update tần suất cao, nhưng BĐS data write-once.

### 11. Tại sao chia 5 index thay vì 1 index gộp?
- Mỗi loại BĐS có **schema `extra_infos.*` khác nhau** (đất có `front_road`, chung cư không; chung cư có `no_bedrooms` >85%, đất 1%).
- Gộp 1 index → sparse field → tốn storage + mapping conflict.
- Chia 5 → query song song khi cần cross-loại (`nhamatpho_index,nharieng_index,...`), vẫn đủ nhanh.
- Pipeline v3 đã refactor sang 6 Kafka topic + 6 ES index flat (xem memory project).

### 12. Em chống tin "ma" trùng lặp thế nào?
- **Hiện tại**: chưa có dedup chính thức. Tin trùng vẫn count riêng.
- **Đã ý thức được**: trong `BUSINESS_ANALYSIS_BDS.md` đã ghi rõ là **limitation**.
- **Roadmap**: dedup theo `(address + price ± 5% + square ± 5%)` hash → group cùng 1 căn.
- Tạm thời mitigate bằng: KPI "tổng tin" KHÔNG được dùng làm proxy cho "số căn thật".

### 13. Pipeline ingest data thế nào? Real-time hay batch?
**Hybrid**:
- **Streaming**: Scrapy spider push từng tin lên Kafka topic → Spark Structured Streaming consume → write thẳng vào ES.
- **Batching**: Spark batch job chạy theo schedule để recompute aggregate (vd field `price/square` derived, hoặc reindex).
- Storage layer: MinIO làm raw landing zone (cho replay nếu cần re-ingest).
- Triển khai: Docker → K8s Strimzi cho Kafka, Spark Operator cho jobs.

### 14. Schema/field em quan tâm nhất? Vì sao?
Top 3 theo mức độ "actionable":
1. **`price/square`** — chuẩn hóa giá giữa khu vực + loại BĐS, là KPI nghiệp vụ chính.
2. **`address.district`** — phân tích geographic, nhưng coverage chỉ 33-53% (Đất 4%) → là **field cần cải thiện crawler**.
3. **`post_date`** — phân tích trend thời gian; coverage 100% nhưng `day/month/year` derived chỉ 42% → cần fix Spark batch job tính lại.

---

## C. NGƯỜI MUA (6 câu)

### 15. User flow điển hình của 1 người mua?
```
1. Vào Dashboard chọn tỉnh + loại BĐS
2. Đọc KPI median giá/m² → đặt expectation
3. Xem bar giá theo quận → khoanh vùng quận khả thi
4. Xem pie distribution diện tích → ước lượng size phù hợp budget
5. Switch sang Tab Chatbot, hỏi cụ thể "tìm nhà phố Cầu Giấy 5-7 tỷ, ≥50m²"
6. Chatbot trả về list bài + analytics + 3 câu hỏi gợi ý
7. Click link tin → contact môi giới (out-of-app)
```

### 16. Tại sao có cả Chatbot và Dashboard? Có trùng chức năng không?
KHÔNG trùng:
| | Dashboard | Chatbot |
|---|---|---|
| Mode | Explorative (lướt số) | Goal-oriented (hỏi-đáp) |
| Output | Biểu đồ tổng quan | List bài cụ thể + tư vấn |
| Input | Filter (tỉnh, loại) | Câu hỏi tự nhiên |
| Khi nào dùng | Pha "đặt expectation" | Pha "shortlist tin" |

User thường dùng dashboard TRƯỚC để hiểu khu, sau đó hỏi chatbot để cá nhân hóa.

### 17. Em xử lý người mua hỏi mơ hồ ("tôi muốn mua nhà") thế nào?
- Planner agent có rule: câu BĐS mơ hồ vẫn xếp vào `intent=bds_query` (không reject).
- SearchDB tự build query với filter loose → trả ra mẫu đa dạng.
- Writer agent sinh 3 **câu hỏi follow-up** ở cuối response (vd "Bạn muốn mua tỉnh nào?", "Ngân sách bao nhiêu?") → guide user dần.
- Nếu hỏi chitchat ("xin chào", "bạn làm được gì") → trả response cố định, **không tốn LLM call**.

### 18. Chatbot tự đặt tên cuộc hội thoại — vì sao cần?
- User có thể có **nhiều cuộc chat song song** (multi-chat, đã refactor).
- Tên auto từ câu đầu (vd "Mua nhà Hoàn Kiếm 50 tỷ") giúp user tìm lại cuộc cũ trong sidebar.
- Implement: sau message thứ 1, gọi `/chat/name_conversation` → backend dùng LLM tóm tắt → lưu vào title.

### 19. Em làm sao đảm bảo chatbot nhớ context giữa các câu hỏi?
2 layer memory bổ sung nhau:
- **Query Rewriter** (gpt-4o-mini, mới thêm): mỗi turn rewrite câu hiện tại thành standalone dựa trên 5 turn gần nhất. Vd "với 50 tỷ thì sao" → "Mua nhà mặt phố Hà Nội Hoàn Kiếm với 50 tỷ thì sao".
- **Zep Cloud Memory**: lưu dài hạn dạng knowledge graph, isolate per chat (`user_id = "chat-{chat_id}"`). Trả `memory_context` cho writer ở mọi turn.
- Lý do cần cả 2: rewriter cho precision (search agent dùng), Zep cho recall dài (50+ turn).

### 20. Nếu data có 1 căn nhà bị parse giá sai (vd giá 1 đồng), user thấy thế nào?
- ES query đã filter ở backend: `PRICE_MIN = 1` loại "liên hệ", `PRICE_MAX = 1.000 tỷ` loại parse sai.
- Tuy nhiên list bài cụ thể trong chatbot **có thể vẫn lọt** record giá lẻ nếu nằm trong range filter.
- Mitigation cho user: response có slice "Giá: liên hệ" / "Giá không xác định" — không hiển thị "1 VNĐ" gây confusion.
- Cải thiện: thêm tag confidence cho mỗi field parsed, lọc low-confidence khi rank top kết quả.

---

## Tips cuối khi bảo vệ

1. **Luôn dẫn file cụ thể**: "Em xử lý ở `elasticsearch_queries.py:30-35`" — thầy thấy em đã đụng tới code, không nói lý thuyết.
2. **Đừng tránh limitation**: nói thẳng "tin ma chưa dedup, đó là roadmap" — đáng tin hơn là giả vờ hoàn hảo.
3. **Phân biệt số đo & số diễn giải**: "tổng tin 53k là số đo; còn 'thị trường nóng' là **diễn giải**, cần kiểm chứng thêm".
4. **Khi không biết → đề xuất cách tìm hiểu**: "câu này em chưa nghiên cứu kỹ, nhưng nếu cần em sẽ check bằng cách X".
