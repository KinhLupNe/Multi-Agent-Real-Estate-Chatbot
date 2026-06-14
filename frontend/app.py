"""
Streamlit frontend — BDS Chatbot + Analytics Dashboard.

Multi-chat persist: file `.chat_state.json` ngay cạnh module này, lưu mọi cuộc chat
+ active chat — reload tab vẫn giữ nguyên. Backend Zep memory isolate per chat_id.
"""
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
from theme import apply_theme, hero, kpi_cards, section, MOCHA
from chat_utils import get_response, get_conversation_name


# Cấu hình widget "Đặc điểm phổ biến" theo từng loại BĐS.
# Mỗi loại có set field coverage cao khác nhau (xem docs/DESIGN_BDS_ANALYTICS.md):
#   - chungcu không có no_floors (coverage 26%) → bỏ
#   - dat không có no_bedrooms/no_floors → dùng square + front_face
# Format: (label_hiển_thị, kind, field_es)
#   kind = "field" → categorical (số PN/WC/tầng, hướng...)
#   kind = "range" → continuous binned (diện tích, mặt tiền, đường trước)
DISTRIBUTION_LAYOUT: dict[str, list[tuple[str, str, str]]] = {
    "nhamatpho": [
        ("Số tầng", "field", "no_floors"),
    ],
    "nharieng": [
        ("Số phòng ngủ", "field", "no_bedrooms"),
        ("Số tầng", "field", "no_floors"),
    ],
    "chungcu": [
        ("Số phòng ngủ", "field", "no_bedrooms"),
        ("Số phòng tắm", "field", "no_bathrooms"),
    ],
    "bietthu": [
        ("Số phòng ngủ", "field", "no_bedrooms"),
        ("Số tầng", "field", "no_floors"),
    ],
    "dat": [
        ("Phân khúc diện tích", "range", "square"),
        ("Mặt tiền", "range", "front_face"),
    ],
    "khac": [
        ("Phân khúc diện tích", "range", "square"),
        ("Số tầng", "field", "no_floors"),
        ("Mặt tiền", "range", "front_face"),
    ],
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


# Multi-chat persist — toàn bộ state lưu vào file JSON cạnh module này.
# Schema: {"active_chat_id": str, "chats": {chat_id: {title, messages: [...]}}}
STATE_FILE = Path(__file__).parent / ".chat_state.json"


def _new_chat_dict() -> dict:
    return {
        "title": f"Cuộc hội thoại mới {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "messages": [],
    }


def _load_state() -> dict:
    """Đọc state từ disk. Tự migrate format cũ (1 chat) → format mới (multi-chat)."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            if "chats" in data and "active_chat_id" in data and data["chats"]:
                return data
            # Format cũ chỉ có {chat_id, messages} — convert sang multi-chat, giữ history.
            if "chat_id" in data and "messages" in data:
                cid = data["chat_id"]
                return {
                    "active_chat_id": cid,
                    "chats": {cid: {**_new_chat_dict(), "messages": data["messages"]}},
                }
        except (json.JSONDecodeError, OSError):
            pass
    first_id = str(uuid.uuid4())
    return {"active_chat_id": first_id, "chats": {first_id: _new_chat_dict()}}


def _save_state() -> None:
    data = {
        "active_chat_id": st.session_state.active_chat_id,
        "chats": st.session_state.chats,
    }
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_chat_state():
    if "chats" not in st.session_state:
        state = _load_state()
        st.session_state.chats = state["chats"]
        st.session_state.active_chat_id = state["active_chat_id"]
        if not STATE_FILE.exists():
            _save_state()


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
    if chat_id not in st.session_state.chats:
        return
    del st.session_state.chats[chat_id]
    if not st.session_state.chats:
        # Xóa hết → seed 1 cuộc mới để UI không trống.
        new_id = str(uuid.uuid4())
        st.session_state.chats[new_id] = _new_chat_dict()
        st.session_state.active_chat_id = new_id
    elif st.session_state.active_chat_id == chat_id:
        # Đang xóa chính cuộc đang mở → switch sang cuộc đầu tiên còn lại.
        st.session_state.active_chat_id = next(iter(st.session_state.chats))
    _save_state()


st.set_page_config(page_title="BDS Analytics", layout="wide", initial_sidebar_state="collapsed")
apply_theme()


def _truncate(s: str, n: int = 32) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _render_chat_list_panel():
    """Panel chat list — render bên trong cột trái của tab Chatbot."""
    st.markdown('<div class="chat-list-header">Cuộc hội thoại</div>', unsafe_allow_html=True)

    st.markdown('<div class="new-chat-btn">', unsafe_allow_html=True)
    if st.button("➕  Cuộc hội thoại mới", key="new_chat_button", use_container_width=True):
        _create_new_chat()
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="chat-list-divider"></div>', unsafe_allow_html=True)

    active_id = st.session_state.active_chat_id
    for cid, sess in list(st.session_state.chats.items()):
        is_active = cid == active_id
        wrapper_cls = "chat-list-wrapper active" if is_active else "chat-list-wrapper"
        col_sel, col_del = st.columns([6, 1])
        with col_sel:
            st.markdown(f'<div class="{wrapper_cls}">', unsafe_allow_html=True)
            if st.button(
                _truncate(sess["title"], 30),
                key=f"chat_btn_{cid}",
                use_container_width=True,
            ):
                _switch_chat(cid)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with col_del:
            st.markdown('<div class="chat-list-trash">', unsafe_allow_html=True)
            if st.button("✕", key=f"chat_del_{cid}", help="Xóa cuộc hội thoại"):
                _delete_chat(cid)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


hero("BDS Analytics", "Trợ lý + phân tích bất động sản Việt Nam")
tab_chat, tab_dash = st.tabs(["💬  Chatbot", "📊  Dashboard"])


# ─── Tab Chatbot — 2 cột: chat list trái (fixed) + chat area phải ───
with tab_chat:
    _ensure_chat_state()

    list_col, chat_col = st.columns([1, 3], gap="medium")

    with list_col:
        st.markdown('<div class="chat-list-panel">', unsafe_allow_html=True)
        _render_chat_list_panel()
        st.markdown('</div>', unsafe_allow_html=True)

    with chat_col:
        current = _current_chat()
        messages = current["messages"]

        # Empty state: cuộc chat trống → welcome card + 4 sample prompt buttons.
        # Click button = giả lập user gõ + gửi, lưu vào session_state để pickup ở chat_input scope dưới.
        SAMPLE_PROMPTS = [
            "Mua nhà mặt phố Hoàn Kiếm 50 tỷ",
            "Chung cư 2PN Cầu Giấy 3-5 tỷ",
            "Đất nền ở Đà Nẵng dưới 5 tỷ",
            "Biệt thự liền kề Hoài Đức",
        ]
        if not messages:
            st.markdown(
                '''
                <div class="empty-state">
                    <div class="empty-state-icon">🏠</div>
                    <h2>Bạn muốn tìm BĐS gì?</h2>
                    <p>Mình có thể tìm bài đăng từ database + phân tích thị trường giúp bạn.</p>
                    <div class="empty-state-hint">Thử bắt đầu với:</div>
                </div>
                ''',
                unsafe_allow_html=True,
            )
            st.markdown('<div class="sample-prompts">', unsafe_allow_html=True)
            sp_cols = st.columns(2)
            for i, sp in enumerate(SAMPLE_PROMPTS):
                if sp_cols[i % 2].button(sp, key=f"sample_{i}", use_container_width=True):
                    st.session_state.queued_prompt = sp
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="chat-messages-area">', unsafe_allow_html=True)
        # Anchor đặt NGAY TRƯỚC user message cuối cùng → JS sẽ scroll anchor lên top
        # viewport (pattern Claude/ChatGPT: user message vừa gửi nhảy lên đầu màn hình).
        last_user_idx = next(
            (i for i in range(len(messages) - 1, -1, -1) if messages[i]["role"] == "user"),
            None,
        )
        for i, message in enumerate(messages):
            if i == last_user_idx:
                st.markdown('<div id="last-user-anchor"></div>', unsafe_allow_html=True)
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        st.markdown('</div>', unsafe_allow_html=True)

        # Scroll user message vừa gửi lên top viewport. Retry 5 lần × 150ms vì
        # DOM Streamlit reflow async — anchor chưa chắc có sẵn ở tick đầu.
        if messages:
            st.components.v1.html(
                f"""
                <div data-msgs="{len(messages)}"></div>
                <script>
                    (function() {{
                        let tries = 0;
                        const scroll = () => {{
                            const doc = window.parent.document;
                            const anchor = doc.getElementById('last-user-anchor');
                            if (anchor) {{
                                anchor.scrollIntoView({{behavior: 'smooth', block: 'start'}});
                            }}
                            if (++tries < 5) setTimeout(scroll, 150);
                        }};
                        setTimeout(scroll, 50);
                    }})();
                </script>
                """,
                height=1,
            )

        # Input có thể đến từ 2 nguồn: chat_input (user gõ) hoặc sample button click (queued).
        typed = st.chat_input("Nhập tin nhắn của bạn...")
        queued = st.session_state.pop("queued_prompt", None)
        prompt = typed or queued
        if prompt:
            messages.append({"role": "user", "content": prompt})
            _save_state()
            # Render user msg + anchor riêng `new-user-msg-anchor` để scroll TỨC THÌ
            # (không cần chờ assistant trả lời). Browser execute JS song song khi spinner quay.
            st.markdown('<div id="new-user-msg-anchor"></div>', unsafe_allow_html=True)
            with st.chat_message("user"):
                st.markdown(prompt)
            st.components.v1.html(
                """
                <script>
                    (function() {
                        let tries = 0;
                        const scroll = () => {
                            const doc = window.parent.document;
                            const anchor = doc.getElementById('new-user-msg-anchor');
                            if (anchor) anchor.scrollIntoView({behavior: 'smooth', block: 'start'});
                            if (++tries < 8) setTimeout(scroll, 80);
                        };
                        setTimeout(scroll, 20);
                    })();
                </script>
                """,
                height=1,
            )

            # Backend cần chat_id ở item CUỐI để xác định Zep thread → nhúng vào message hiện tại.
            payload = [
                {**m, "chat_id": st.session_state.active_chat_id} if i == len(messages) - 1 else m
                for i, m in enumerate(messages)
            ]

            with st.chat_message("assistant"):
                with st.spinner("🤔  Đang suy nghĩ..."):
                    try:
                        response = get_response(payload)
                    except Exception as e:
                        st.error(f"Lỗi gọi server: {e}")
                        messages.pop()  # rollback user message
                        _save_state()
                        st.stop()

                relevant_q = "\n".join(response.get("follow_up_questions") or [])
                final_response = (
                    response.get("real_estate_findings", "")
                    + "\n\n# Phân tích:\n"
                    + response.get("analytics_and_advice", "")
                    + ("\n\n# Câu hỏi có thể bạn quan tâm:\n" + relevant_q if relevant_q else "")
                )
                st.markdown(final_response)

            messages.append({"role": "assistant", "content": final_response})

            # Sau turn đầu tiên: backend tự sinh tên cuộc chat từ câu hỏi → rerun để sidebar update.
            if len(messages) == 2:
                try:
                    current["title"] = get_conversation_name(messages)
                except Exception:
                    pass

            _save_state()
            if len(messages) == 2:
                st.rerun()


# ─── Tab Dashboard — analytics theo Tỉnh × Loại BĐS ───
with tab_dash:
    filter_col1, filter_col2 = st.columns([1, 2])
    with filter_col1:
        selected_province = st.selectbox(
            "Tỉnh/Thành phố",
            options=PROVINCES_LIST,
            index=PROVINCES_LIST.index("Hà Nội"),
            placeholder="Gõ tên tỉnh để tìm kiếm...",
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
            # Tỉnh là state phía server, KHÔNG nằm trong tham số các hàm fetch
            # (cache key chỉ có estate_type + listing_type). Nên phải xoá cache,
            # nếu không Streamlit trả lại data đã cache của tỉnh trước.
            st.cache_data.clear()
            st.toast(f"Đã chuyển dữ liệu sang: {selected_province}", icon="✅")
            st.rerun()

    listing_type_index = "buy"
    estate_type_index = {
        "Nhà mặt tiền": "nhamatpho",
        "Nhà riêng": "nharieng",
        "Chung cư": "chungcu",
        "Biệt thự": "bietthu",
        "Đất": "dat",
    }.get(estate_type, "nhamatpho")

    def process_data(df):
        # WINDOWS QUIRK: phải dùng 'int64' chứ không phải 'int'. Windows mặc định int=int32
        # (max ~2.1 tỷ) → giá BĐS thường > 2 tỷ sẽ overflow thành số âm.
        df_new = df.copy()
        for col in df_new.columns:
            if "Diện tích" in col:
                df_new[col] = df_new[col].fillna(0).round(0).astype("int64")
            if "Giá" in col:
                df_new[col] = df_new[col].fillna(0).round(-3).astype("int64")
        return df_new

    def _fmt_vnd(v: float) -> str:
        """Format số tiền VND ngắn gọn: 22e9 → '22.0 tỷ', 337e6 → '337 triệu'."""
        if v is None:
            return "—"
        v = float(v)
        if v >= 1_000_000_000:
            return f"{v/1_000_000_000:,.1f} tỷ"
        if v >= 1_000_000:
            return f"{v/1_000_000:,.0f} triệu"
        return f"{v:,.0f}"

    try:
        kpi = fetch_kpi(estate_type_index, listing_type_index)

        kpi_cards([
            {"label": "🏘️  Tổng tin đăng", "value": f"{int(kpi['total_listings']):,}"},
            {"label": "💰  Giá điển hình", "value": _fmt_vnd(kpi["median_price"])},
            {"label": "📐  Giá/m² điển hình", "value": _fmt_vnd(kpi["median_price_per_sq"])},
        ])

        section("Giá theo quận/huyện")
        price_by_district_df = process_data(price_by_district(estate_type_index, listing_type_index))
        price_per_square_df = process_data(price_per_square_by_district(estate_type_index, listing_type_index))

        col1, col2 = st.columns(2)

        with col1:
            fig = px.bar(
                price_by_district_df,
                x="Quận/Huyện",
                y="Giá Trung Bình (VNĐ)",
                title="Giá Trung Bình",
                color_discrete_sequence=[MOCHA["peach"]],
            )
            fig.update_layout(xaxis_tickangle=-45, showlegend=False, height=350, margin=dict(t=40, b=0, l=0, r=0), yaxis_tickformat=",")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            fig = px.bar(
                price_per_square_df,
                x="Quận/Huyện",
                y="Giá Trung Bình/m² (VNĐ)",
                title="Đơn Giá / m²",
                color_discrete_sequence=[MOCHA["sapphire"]],
            )
            fig.update_layout(xaxis_tickangle=-45, showlegend=False, height=350, margin=dict(t=40, b=0, l=0, r=0), yaxis_tickformat=",")
            st.plotly_chart(fig, use_container_width=True)

        section("Phân phối giá")
        seg_df = fetch_price_segments(estate_type_index, listing_type_index)
        if not seg_df.empty:
            fig = px.bar(
                seg_df, x="label", y="count", text="count",
                labels={"label": "Phân khúc", "count": "Số tin"},
                color_discrete_sequence=[MOCHA["green"]],
            )
            fig.update_traces(textposition="outside")
            fig.update_layout(height=350, showlegend=False, margin=dict(t=20, b=0))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Không có data phân khúc")

        section(f"Đặc điểm phổ biến — {estate_type}")

        _label_fmt = {
            "no_bedrooms": lambda v: f"{v} PN" if v != "Chưa rõ" else v,
            "no_bathrooms": lambda v: f"{v} WC" if v != "Chưa rõ" else v,
            "no_floors": lambda v: f"{v} tầng" if v != "Chưa rõ" else v,
        }

        def _render_dist_pie(container, title, kind, field):
            with container:
                st.markdown(f"**{title}**")
                df_x = (fetch_range_distribution if kind == "range"
                        else fetch_field_distribution)(
                    estate_type_index, listing_type_index, field
                )
                if df_x.empty or df_x["count"].sum() == 0:
                    st.info(f"Chưa có data cho {title}")
                    return
                fmt = _label_fmt.get(field)
                if fmt is not None:
                    df_x = df_x.copy()
                    df_x["value"] = df_x["value"].map(fmt)
                # "Chưa rõ" tô màu overlay mờ để phân biệt với data thật
                palette = [MOCHA["mauve"], MOCHA["peach"], MOCHA["green"], MOCHA["sapphire"],
                           MOCHA["pink"], MOCHA["yellow"], MOCHA["teal"], MOCHA["red"]]
                colors = []
                idx = 0
                for v in df_x["value"]:
                    if v == "Chưa rõ":
                        colors.append(MOCHA["overlay0"])
                    else:
                        colors.append(palette[idx % len(palette)])
                        idx += 1
                fig = px.pie(df_x, names="value", values="count", hole=0.5)
                fig.update_traces(
                    textposition="inside", textinfo="percent+label",
                    marker=dict(colors=colors, line=dict(color=MOCHA["base"], width=2)),
                )
                fig.update_layout(height=320, showlegend=False, margin=dict(t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

        layout = DISTRIBUTION_LAYOUT.get(estate_type_index, [])
        if layout:
            cols = st.columns(len(layout))
            for col, (title, kind, field) in zip(cols, layout):
                _render_dist_pie(col, title, kind, field)
        else:
            st.info("Loại BĐS này chưa có cấu hình đặc điểm")

        section(f"Bản đồ nhiệt — {estate_type} tại {selected_province}")
        price_map = create_price_heatmap(price_by_district_df, selected_province)
        st.components.v1.html(price_map._repr_html_(), height=520)

    except Exception as e:
        st.error(f"Có lỗi khi kết nối Elasticsearch / backend: {e}")
        st.info("Kiểm tra: 1) Docker ES đang chạy, 2) FastAPI đang chạy ở port 8000.")
