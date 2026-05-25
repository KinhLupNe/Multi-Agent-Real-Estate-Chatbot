"""
FastAPI app — entry point của backend BĐS chatbot + analytics.

Endpoint chính:
  POST /chat                 — multi-agent pipeline (rewrite → plan → search → write)
  POST /chat/name_conversation — auto đặt tên cuộc chat từ câu đầu
  POST /set_active_province  — đổi province cho dashboard query
  GET  /dashboard/*          — các widget data cho frontend Streamlit
  GET  /get_price_*          — legacy endpoint của dashboard cũ
"""
import asyncio
from typing import Any

from fastapi import FastAPI, Body

from worker import (
    get_area_district,
    get_price_district,
    get_price_per_square_district,
    get_price_date,
    get_price_per_square_date,
    get_name_conversation,
    update_global_districts,
)
from elasticsearch_queries import (
    get_market_kpi as _get_market_kpi,
    get_price_segments as _get_price_segments,
    get_price_per_sq_quartiles_by_district as _get_pps_quartiles,
    get_listing_count_by_district as _get_listing_count,
    get_field_distribution as _get_field_dist,
    get_range_distribution as _get_range_dist,
    get_price_trend_monthly as _get_trend_monthly,
)
from manager import ResearchManager


app = FastAPI()
manager = ResearchManager(use_judge=True)


@app.post("/set_active_province/{province}")
def set_active_province_endpoint(province: str):
    success = update_global_districts(province)
    return {"status": "success" if success else "failed", "province": province}


# === Legacy endpoints (dashboard v1) — vẫn giữ vì frontend cũ có thể gọi ===

@app.get("/get_price_by_district/{listing_type}/{estate_type_index}")
def get_price_by_district(estate_type_index: str, listing_type: str):
    districts, avg_prices, median_prices = get_price_district(estate_type_index, listing_type)
    return {"districts": districts, "avg_prices": avg_prices, "median_prices": median_prices}


@app.get("/get_price_per_square_by_district/{listing_type}/{estate_type_index}")
def get_price_per_square_by_district(estate_type_index: str, listing_type: str):
    districts, avg_prices_per_square, median_prices_per_square = get_price_per_square_district(estate_type_index, listing_type)
    return {"districts": districts, "avg_prices_per_square": avg_prices_per_square, "median_prices_per_square": median_prices_per_square}


@app.get("/get_area_by_district/{listing_type}/{estate_type_index}")
def get_area_by_district(estate_type_index: str, listing_type: str):
    districts, avg_areas, median_areas = get_area_district(estate_type_index, listing_type)
    return {"districts": districts, "avg_areas": avg_areas, "median_areas": median_areas}


@app.get("/get_price_by_date/{listing_type}/{estate_type_index}/{selected_district}/{start_date}/{end_date}")
def get_price_by_date(estate_type_index: str, selected_district: str, start_date, end_date, listing_type: str):
    dates, avg_prices = get_price_date(estate_type_index, selected_district, start_date, end_date, listing_type)
    return {"dates": dates, "avg_prices": avg_prices}


@app.get("/get_price_per_square_by_date/{listing_type}/{estate_type_index}/{selected_district}/{start_date}/{end_date}")
def get_price_per_square_by_date(estate_type_index: str, selected_district: str, start_date, end_date, listing_type: str):
    dates, avg_prices_per_square = get_price_per_square_date(estate_type_index, selected_district, start_date, end_date, listing_type)
    return {"dates": dates, "avg_prices_per_square": avg_prices_per_square}


# === Dashboard v2 endpoints — dùng bởi frontend hiện tại ===

@app.get("/dashboard/kpi/{listing_type}/{estate_type_index}")
def dashboard_kpi(estate_type_index: str, listing_type: str):
    return _get_market_kpi(estate_type_index, listing_type)


@app.get("/dashboard/price_segments/{listing_type}/{estate_type_index}")
def dashboard_price_segments(estate_type_index: str, listing_type: str):
    return {"segments": _get_price_segments(estate_type_index, listing_type)}


@app.get("/dashboard/pps_quartiles/{listing_type}/{estate_type_index}")
def dashboard_pps_quartiles(estate_type_index: str, listing_type: str):
    return {"districts": _get_pps_quartiles(estate_type_index, listing_type)}


@app.get("/dashboard/listing_count/{listing_type}/{estate_type_index}")
def dashboard_listing_count(estate_type_index: str, listing_type: str):
    return _get_listing_count(estate_type_index, listing_type)


@app.get("/dashboard/field_dist/{listing_type}/{estate_type_index}/{field}")
def dashboard_field_dist(estate_type_index: str, listing_type: str, field: str):
    return {"items": _get_field_dist(field, estate_type_index, listing_type)}


@app.get("/dashboard/range_dist/{listing_type}/{estate_type_index}/{field}")
def dashboard_range_dist(estate_type_index: str, listing_type: str, field: str):
    return {"items": _get_range_dist(field, estate_type_index, listing_type)}


@app.get("/dashboard/trend_monthly/{listing_type}/{estate_type_index}")
def dashboard_trend_monthly(estate_type_index: str, listing_type: str, district: str = ""):
    return _get_trend_monthly(estate_type_index, listing_type, district or None)


# === Chat endpoints ===

@app.post("/chat/")
async def chat(chats: Any = Body(...)):
    """Pipeline 1 turn: load Zep memory → build prompt → ResearchManager.run → lưu memory async."""
    message = chats[-1]["content"]
    chat_id = chats[-1].get("chat_id", None)
    user_id = chats[-1].get("user_id", None)

    # Isolate memory per chat: mỗi chat_id = 1 Zep user riêng. Lý do: Zep 3.x
    # get_user_context trả user-level knowledge graph (cross-thread), nên cùng
    # user_id sẽ trộn data giữa các cuộc chat khác nhau.
    effective_user_id = user_id or (f"chat-{chat_id}" if chat_id else None)

    # Long-term memory từ Zep (graph summary tới ngày hôm trước).
    # Fail silent → vẫn chạy được khi Zep down hoặc session mới.
    memory_context = ""
    try:
        if chat_id and manager.client:
            memory = await manager.client.thread.get_user_context(thread_id=chat_id)
            ctx = getattr(memory, "context", None) if memory else None
            if ctx:
                memory_context = ctx
                print(f"💡 [ZEP] Tìm thấy ngữ cảnh: {memory_context[:100]}...")
    except Exception as e:
        print(f"⚠️ [ZEP] Không lấy được memory (có thể do session mới): {e}")

    # System prompt kèm RAG memory + 4 turn gần nhất + câu hỏi hiện tại.
    system_instruction = (
        "Bạn là trợ lý ảo bất động sản chuyên nghiệp tại Việt Nam.\n"
        "NHIỆM VỤ: Trả lời câu hỏi mới nhất của người dùng một cách chính xác, ngắn gọn.\n"
        "----------------\n"
        f"KÝ ỨC DÀI HẠN (THAM KHẢO):\n{memory_context}\n"
        "----------------\n"
        "LƯU Ý: Hãy ưu tiên câu hỏi hiện tại, chỉ sử dụng ký ức nếu nó liên quan trực tiếp."
    )
    messages_payload: list[dict] = [{"role": "system", "content": system_instruction}]
    if len(chats) > 1:
        messages_payload.extend(chats[-5:-1])
    messages_payload.append({"role": "user", "content": message})

    report, answer = await manager.run(messages_payload, effective_user_id, chat_id)

    # Lưu turn này vào Zep async — không block response trả về frontend.
    if chat_id:
        interaction_to_save = [
            {"role": "user", "content": message},
            {"role": "assistant", "content": answer},
        ]
        asyncio.create_task(manager.add_memory(interaction_to_save, chat_id, effective_user_id))

    return {
        "real_estate_findings": report.real_estate_findings,
        "analytics_and_advice": report.analytics_and_advice,
        "follow_up_questions": report.follow_up_questions,
    }


@app.post("/chat/name_conversation")
async def get_name(messages: Any = Body(...)):
    """Sinh tên ngắn cho cuộc chat từ câu đầu — gọi sau khi user gửi message #1."""
    name = await get_name_conversation(messages)
    return name
