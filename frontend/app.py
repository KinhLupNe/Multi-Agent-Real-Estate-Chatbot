import json
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import plotly.express as px

from map_visualization import create_price_heatmap
from dashboard_utils import (
    set_active_province,
    price_by_district,
    price_per_square_by_district,
    fetch_kpi,
    fetch_price_segments,
    fetch_field_distribution,
    fetch_range_distribution,
)
from chat_utils import get_response, get_conversation_name

# --- CONFIG ---
DISTRIBUTION_LAYOUT = {
    "nhamatpho": [("Số tầng", "field", "no_floors")],
    "nharieng": [("Số phòng ngủ", "field", "no_bedrooms"), ("Số tầng", "field", "no_floors")],
    "chungcu": [("Số phòng ngủ", "field", "no_bedrooms"), ("Số phòng tắm", "field", "no_bathrooms")],
    "bietthu": [("Số phòng ngủ", "field", "no_bedrooms"), ("Số tầng", "field", "no_floors")],
    "dat": [("Phân khúc diện tích", "range", "square"), ("Mặt tiền", "range", "front_face")],
    "khac": [("Phân khúc diện tích", "range", "square"), ("Số tầng", "field", "no_floors"), ("Mặt tiền", "range", "front_face")],
}

PROVINCES_LIST = [
    "An Giang", "Bà Rịa - Vũng Tàu", "Bắc Giang", "Bắc Kạn", "Bạc Liêu",
    "Bắc Ninh", "Bến Tre", "Bình Định", "Bình Dương", "Bình Phước",
    "Bình Thuận", "Cà Mau", "Cần Thơ", "Cao Bằng", "Đà Nẵng",
    "Đắk Lắk", "Đắk Nông", "Điện Biên", "Đồng Nai", "Đồng Tháp",
    "Gia Lai", "Hà Giang", "Hà Nam", "Hà Nội", "Hà Tĩnh",
    "Hải Dương", "Hải Phòng", "Hậu Giang", "Hòa Bình", "TP. Hồ Chí Minh",
    "Hưng Yên", "Khánh Hòa", "Kiên Giang", "Kon Tum", "Lai Châu",
    "Lâm Đồng", "Lạng Sơn", "Lào Cai", "Long An", "Nam Định",
    "Nghệ An", "Ninh Bình", "Ninh Thuận", "Phú Thọ", "Phú Yên",
    "Quảng Bình", "Quảng Nam", "Quảng Ngãi", "Quảng Ninh", "Quảng Trị",
    "Sóc Trăng", "Sơn La", "Tây Ninh", "Thái Bình", "Thái Nguyên",
    "Thanh Hóa", "Thừa Thiên Huế", "Tiền Giang", "Trà Vinh", "Tuyên Quang",
    "Vĩnh Long", "Vĩnh Phúc", "Yên Bái",
]

STATE_FILE = Path(__file__).parent / ".chat_state.json"

# --- STATE MANAGEMENT ---
def _new_chat_dict() -> dict:
    return {"title": f"Cuộc hội thoại {datetime.now().strftime('%H:%M %d/%m')}", "messages": []}

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if "chats" in data and "active_chat_id" in data and data["chats"]:
                return data
            if "chat_id" in data and "messages" in data:
                cid = data["chat_id"]
                return {"active_chat_id": cid, "chats": {cid: {**_new_chat_dict(), "messages": data["messages"]}}}
        except (json.JSONDecodeError, OSError):
            pass
    first_id = str(uuid.uuid4())
    return {"active_chat_id": first_id, "chats": {first_id: _new_chat_dict()}}

def _save_state() -> None:
    data = {"active_chat_id": st.session_state.active_chat_id, "chats": st.session_state.chats}
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _ensure_chat_state():
    if "chats" not in st.session_state:
        state = _load_state()
        st.session_state.chats = state["chats"]
        st.session_state.active_chat_id = state["active_chat_id"]

def _current_chat() -> dict:
    return st.session_state.chats[st.session_state.active_chat_id]

def _create_new_chat():
    new_id = str(uuid.uuid4())
    st.session_state.chats[new_id] = _new_chat_dict()
    st.session_state.active_chat_id = new_id
    _save_state()

def _switch_chat(chat_id: str):
    if chat_id in st.session_state.chats:
        st.session_state.active_chat_id = chat_id
        _save_state()

def _delete_chat(chat_id: str):
    if chat_id in st.session_state.chats:
        del st.session_state.chats[chat_id]
        if not st.session_state.chats:
            new_id = str(uuid.uuid4())
            st.session_state.chats[new_id] = _new_chat_dict()
            st.session_state.active_chat_id = new_id
        elif st.session_state.active_chat_id == chat_id:
            st.session_state.active_chat_id = next(iter(st.session_state.chats))
        _save_state()

def _truncate(s: str, n: int = 32) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def _fmt_vnd(v: float) -> str:
    if v is None: return "—"
    v = float(v)
    if v >= 1_000_000_000: return f"{v/1_000_000_000:,.1f} tỷ"
    if v >= 1_000_000: return f"{v/1_000_000:,.0f} triệu"
    return f"{v:,.0f}"

def process_data(df):
    df_new = df.copy()
    for col in df_new.columns:
        if "Diện tích" in col:
            df_new[col] = df_new[col].fillna(0).round(0).astype("int64")
        if "Giá" in col:
            df_new[col] = df_new[col].fillna(0).round(-3).astype("int64")
    return df_new

# --- MAIN APP ---
st.set_page_config(page_title="BDS Analytics", layout="wide", page_icon="🏢")

_ensure_chat_state()

# --- SIDEBAR ---
st.sidebar.title("🏢 BDS Analytics")
page = st.sidebar.radio("Điều hướng", ["💬 Chatbot", "📊 Dashboard"])

if page == "💬 Chatbot":
    st.sidebar.divider()
    st.sidebar.subheader("Lịch sử trò chuyện")
    if st.sidebar.button("➕ Cuộc trò chuyện mới", use_container_width=True):
        _create_new_chat()
        st.rerun()
        
    chat_ids = list(st.session_state.chats.keys())
    active_idx = chat_ids.index(st.session_state.active_chat_id) if st.session_state.active_chat_id in chat_ids else 0
    selected_chat = st.sidebar.selectbox(
        "Chọn lịch sử:", 
        options=chat_ids, 
        index=active_idx,
        format_func=lambda cid: _truncate(st.session_state.chats[cid]["title"], 25)
    )
    
    if selected_chat != st.session_state.active_chat_id:
        _switch_chat(selected_chat)
        st.rerun()
        
    if st.sidebar.button("🗑️ Xoá cuộc trò chuyện này"):
        _delete_chat(st.session_state.active_chat_id)
        st.rerun()

# --- CHATBOT PAGE ---
if page == "💬 Chatbot":
    st.title("💬 Trợ lý Bất Động Sản")
    current = _current_chat()
    messages = current["messages"]

    if not messages:
        st.info("👋 Chào bạn! Hãy nhập câu hỏi về thị trường bất động sản (VD: 'Tìm nhà 3 tỷ ở Cầu Giấy').")

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Nhập tin nhắn của bạn..."):
        messages.append({"role": "user", "content": prompt})
        _save_state()
        with st.chat_message("user"):
            st.markdown(prompt)

        payload = [
            {**m, "chat_id": st.session_state.active_chat_id} if i == len(messages) - 1 else m
            for i, m in enumerate(messages)
        ]

        with st.chat_message("assistant"):
            with st.spinner("🤔 Đang suy nghĩ..."):
                try:
                    response = get_response(payload)
                    relevant_q = "\n".join(response.get("follow_up_questions") or [])
                    final_response = (
                        response.get("real_estate_findings", "")
                        + "\n\n### Phân tích:\n"
                        + response.get("analytics_and_advice", "")
                        + ("\n\n**Câu hỏi có thể bạn quan tâm:**\n" + relevant_q if relevant_q else "")
                    )
                    st.markdown(final_response)
                    messages.append({"role": "assistant", "content": final_response})
                    
                    if len(messages) == 2:
                        try:
                            current["title"] = get_conversation_name(messages)
                        except Exception:
                            pass
                    _save_state()
                    if len(messages) == 2:
                        st.rerun()
                except Exception as e:
                    st.error(f"Lỗi gọi server: {e}")
                    messages.pop()
                    _save_state()

# --- DASHBOARD PAGE ---
elif page == "📊 Dashboard":
    st.title("📊 Dashboard Phân Tích")
    
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        selected_province = st.selectbox(
            "Tỉnh/Thành phố",
            options=PROVINCES_LIST,
            index=PROVINCES_LIST.index("Hà Nội") if "Hà Nội" in PROVINCES_LIST else 0,
        )
    with filter_col2:
        estate_type = st.radio(
            "Loại bất động sản",
            ["Nhà mặt tiền", "Nhà riêng", "Chung cư", "Biệt thự", "Đất"],
            horizontal=True,
        )

    if "current_province" not in st.session_state:
        st.session_state.current_province = ""

    if selected_province != st.session_state.current_province:
        success = set_active_province(selected_province)
        if success:
            st.session_state.current_province = selected_province
            st.toast(f"Đã chuyển dữ liệu sang: {selected_province}", icon="✅")

    listing_type_index = "buy"
    estate_type_index = {
        "Nhà mặt tiền": "nhamatpho",
        "Nhà riêng": "nharieng",
        "Chung cư": "chungcu",
        "Biệt thự": "bietthu",
        "Đất": "dat",
    }.get(estate_type, "nhamatpho")

    try:
        kpi = fetch_kpi(selected_province, estate_type_index, listing_type_index)
        
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Tổng tin đăng", f"{int(kpi['total_listings']):,}")
        kpi2.metric("Giá điển hình", _fmt_vnd(kpi["median_price"]))
        kpi3.metric("Giá/m² điển hình", _fmt_vnd(kpi["median_price_per_sq"]))
        st.divider()

        st.subheader("Giá theo Quận/Huyện")
        price_by_district_df = process_data(price_by_district(selected_province, estate_type_index, listing_type_index))
        price_per_square_df = process_data(price_per_square_by_district(selected_province, estate_type_index, listing_type_index))

        col1, col2 = st.columns(2)
        with col1:
            fig1 = px.bar(price_by_district_df, x="Quận/Huyện", y="Giá Trung Bình (VNĐ)")
            fig1.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig1, use_container_width=True)
        with col2:
            fig2 = px.bar(price_per_square_df, x="Quận/Huyện", y="Giá Trung Bình/m² (VNĐ)")
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)

        st.divider()
        st.subheader("Phân phối giá")
        seg_df = fetch_price_segments(selected_province, estate_type_index, listing_type_index)
        if not seg_df.empty:
            fig_seg = px.bar(seg_df, x="label", y="count", text="count", labels={"label": "Phân khúc", "count": "Số tin"})
            st.plotly_chart(fig_seg, use_container_width=True)
        else:
            st.info("Không có dữ liệu phân khúc")

        st.divider()
        st.subheader(f"Đặc điểm phổ biến — {estate_type}")
        layout = DISTRIBUTION_LAYOUT.get(estate_type_index, [])
        if layout:
            cols = st.columns(len(layout))
            for col, (title, kind, field) in zip(cols, layout):
                with col:
                    st.markdown(f"**{title}**")
                    df_x = (fetch_range_distribution if kind == "range" else fetch_field_distribution)(
                        selected_province, estate_type_index, listing_type_index, field
                    )
                    if not df_x.empty and df_x["count"].sum() > 0:
                        fig_pie = px.pie(df_x, names="value", values="count", hole=0.5)
                        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
                        st.plotly_chart(fig_pie, use_container_width=True)
                    else:
                        st.info("Chưa có data")
        else:
            st.info("Loại BĐS này chưa có cấu hình đặc điểm")

        st.divider()
        st.subheader(f"Bản đồ nhiệt — {estate_type} tại {selected_province}")
        price_map = create_price_heatmap(price_by_district_df, selected_province)
        st.components.v1.html(price_map._repr_html_(), height=500)

    except Exception as e:
        st.error(f"Có lỗi khi kết nối Elasticsearch / backend: {e}")
        st.info("Kiểm tra lại xem Elasticsearch và FastAPI (port 8000) đã chạy chưa.")
