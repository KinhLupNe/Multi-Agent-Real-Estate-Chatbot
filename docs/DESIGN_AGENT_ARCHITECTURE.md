# Kiến trúc tác tử — Backend BĐS Chatbot

## Mục tiêu
Multi-agent system trả lời câu hỏi BĐS bằng tiếng Việt: tìm bài đăng từ ES nội bộ, bổ sung thông tin web khi cần, tổng hợp thành báo cáo + gợi ý câu tiếp.

## Sơ đồ tổng thể

```
Frontend (Streamlit)
   │  POST /chat  { chats: [...messages] }
   ▼
FastAPI (main.py)
   ├─ effective_user_id = "chat-{chat_id}"   ← isolate per chat
   ├─ memory_context = Zep.thread.get_user_context(chat_id)
   └─ messages_payload = [system + memory] + history[-4:] + câu mới
        │
        ▼
   ┌──────────────────────────────────────────────────────┐
   │  ResearchManager (orchestrator)                      │
   │                                                      │
   │  0. QueryRewriter   → câu standalone                 │
   │  1. PlannerAgent    → (intent, tools[])              │
   │                                                      │
   │  if intent ∈ {chitchat, off_topic}:                  │
   │      → response cố định (không LLM, không search)    │
   │                                                      │
   │  else (bds_query):                                   │
   │      ├─ "search_db" → SearchDB ↔ Judge (≤2 vòng)    │
   │      └─ "search_web" → SearchWeb                     │
   │                                                      │
   │  2. WriterAgent → RealEstateAdvice                   │
   │  3. asyncio.create_task(Zep.add_memory(...))         │
   └──────────────────────────────────────────────────────┘
```

## Nhiệm vụ từng tác tử

| Tác tử | Model | Trách nhiệm |
|---|---|---|
| QueryRewriter | gpt-4o-mini | Gộp filter từ history vào câu hiện tại → standalone query. Fallback câu gốc nếu fail. |
| Planner | gpt-4o-mini | Phân loại `intent ∈ {bds_query, chitchat, off_topic}` + chọn tool. Short-circuit chitchat/off_topic. |
| SearchDB | gpt-4o-mini + ES | Build ES DSL theo loại BĐS, query 5 index (nhamatpho/nharieng/chungcu/bietthu/dat). |
| Judge | gpt-4o-mini | Chấm posts có khớp query không. needs_improvement → feedback → SearchDB rewrite (loop ≤2). |
| SearchWeb | OpenAI / Gemini | Search Internet cho trend giá, dự án mới, kiến thức chung. |
| Writer | gpt-4o-mini | Tổng hợp posts + findings → `{findings, summary, analysis, follow_up_questions[3]}`. |
| Zep (memory) | Cloud SDK 3.x | `user_id = "chat-{chat_id}"` ↔ thread cùng tên → memory cách ly per chat. Trả `context` cho turn sau. |

## Flow multi-turn (ví dụ)

**Turn 1**: "Mua nhà mặt tiền HN Hoàn Kiếm"
1. Rewriter skip (history rỗng)
2. Planner → `{intent: bds_query, tools: [search_db]}`
3. SearchDB → ES `nhamatpho_index` (province=HN, district=Hoàn Kiếm)
4. Judge: pass
5. Writer → 5 bài + phân tích
6. Async: lưu Zep thread `chat-abc`, user `chat-abc`

**Turn 2**: "Với 50 tỷ thì mua được cái nào"
1. **Rewriter** đọc history → "Mua nhà mặt tiền HN Hoàn Kiếm với ngân sách 50 tỷ thì mua được cái nào"
2. Planner → tools=[search_db]
3. SearchDB → ES + `price ≤ 50_000_000_000`
4. ... (filter Hoàn Kiếm vẫn được giữ)

## Memory: rewriter vs Zep

| | Rewriter | Zep |
|---|---|---|
| Phạm vi | 5 turn gần nhất (~10 message) | Toàn bộ lịch sử chat |
| Hình thức | Câu standalone tươi | Knowledge graph + summary |
| Mục đích | Cho search agent xử lý đúng câu CỤ THỂ | Cho writer/system prompt giữ context DÀI |
| Cost | 1 LLM call mỗi turn | 0 (Zep tự xử) |

Cả hai bổ sung lẫn nhau — rewriter cho precision, Zep cho recall dài hạn.

## Failure modes (graceful degradation)

| Tác tử fail | Hành vi |
|---|---|
| Rewriter | Dùng câu gốc |
| Planner | Default `bds_query + [search_db]` |
| SearchDB | posts=[], Writer trả "không tìm thấy" |
| Judge | Accept posts hiện tại (không loop) |
| SearchWeb | findings=None, Writer chỉ dùng posts |
| Writer | Trả `RealEstateAdvice` fallback "lỗi tạo báo cáo" |
| Zep | memory_context="", pipeline vẫn chạy |

Mọi lỗi đều log console, không break user-facing response.
