"""
Catppuccin Mocha theme cho Streamlit + Plotly.
Inject CSS sâu hơn config.toml để style sidebar, hero header, KPI cards, chart.
"""
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Catppuccin Mocha palette
MOCHA = {
    "base": "#1e1e2e",
    "mantle": "#181825",
    "crust": "#11111b",
    "surface0": "#313244",
    "surface1": "#45475a",
    "surface2": "#585b70",
    "overlay0": "#6c7086",
    "overlay1": "#7f849c",
    "subtext0": "#a6adc8",
    "subtext1": "#bac2de",
    "text": "#cdd6f4",
    "lavender": "#b4befe",
    "blue": "#89b4fa",
    "sapphire": "#74c7ec",
    "sky": "#89dceb",
    "teal": "#94e2d5",
    "green": "#a6e3a1",
    "yellow": "#f9e2af",
    "peach": "#fab387",
    "maroon": "#eba0ac",
    "red": "#f38ba8",
    "mauve": "#cba6f7",
    "pink": "#f5c2e7",
}

CHART_COLORWAY = [
    MOCHA["mauve"], MOCHA["peach"], MOCHA["green"], MOCHA["sapphire"],
    MOCHA["pink"], MOCHA["yellow"], MOCHA["teal"], MOCHA["red"],
]


def _build_plotly_template() -> go.layout.Template:
    return go.layout.Template(
        layout=go.Layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=MOCHA["text"], family="Inter, system-ui, sans-serif"),
            colorway=CHART_COLORWAY,
            xaxis=dict(
                gridcolor=MOCHA["surface0"],
                linecolor=MOCHA["surface1"],
                zerolinecolor=MOCHA["surface1"],
                tickcolor=MOCHA["overlay0"],
                tickfont=dict(color=MOCHA["subtext0"]),
                title_font=dict(color=MOCHA["subtext1"]),
            ),
            yaxis=dict(
                gridcolor=MOCHA["surface0"],
                linecolor=MOCHA["surface1"],
                zerolinecolor=MOCHA["surface1"],
                tickcolor=MOCHA["overlay0"],
                tickfont=dict(color=MOCHA["subtext0"]),
                title_font=dict(color=MOCHA["subtext1"]),
            ),
            legend=dict(
                bgcolor="rgba(49,50,68,0.6)",
                bordercolor=MOCHA["surface1"],
                font=dict(color=MOCHA["subtext1"]),
            ),
            hoverlabel=dict(
                bgcolor=MOCHA["surface0"],
                bordercolor=MOCHA["mauve"],
                font=dict(color=MOCHA["text"]),
            ),
            title_font=dict(color=MOCHA["text"], size=16),
        )
    )


def _css() -> str:
    m = MOCHA
    return f"""
    <style>
    /* === Fonts === */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"], .stApp, .stMarkdown {{
        font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    }}

    /* === Main background === */
    .stApp {{
        background: {m['base']};
    }}

    /* === HIDE sidebar entirely — layout v2 dùng top tabs === */
    [data-testid="stSidebar"], [data-testid="collapsedControl"] {{
        display: none !important;
    }}
    section.main, [data-testid="stAppViewContainer"] > section {{
        padding-left: 0 !important;
    }}

    /* Bảo đảm scroll hoạt động trên window — KHÔNG ép overflow visible lên stMain/stAppViewContainer
       vì đó là scroll container của Streamlit (sẽ làm mất chuột lăn + mũi tên) */
    html, body {{
        overflow-x: hidden !important;
        overflow-y: auto !important;
        height: auto !important;
    }}

    /* Chỉ ép overflow visible cho ancestor gần của các element fixed/sticky con,
       KHÔNG đụng vào stMain / stAppViewContainer / section.main */
    [data-testid="stMainBlockContainer"],
    [data-testid="stTabs"],
    [data-testid="stTabs"] > div,
    [data-testid="stTabs"] [role="tabpanel"],
    [data-testid="stHorizontalBlock"],
    [data-testid="stColumn"],
    [data-testid="stVerticalBlock"],
    [data-testid="stMarkdown"],
    .element-container {{
        overflow: visible !important;
    }}

    /* Đẩy main content xuống dưới hero (fixed) + tabs (fixed) */
    [data-testid="stMainBlockContainer"] {{
        padding-top: 96px !important;
    }}

    /* === Top nav tabs — FIXED dưới hero, mỏng nhưng đủ chỗ cho buttons === */
    [data-testid="stTabs"] [role="tablist"] {{
        background: {m['base']};
        border-radius: 0;
        padding: 0 2rem;
        gap: 0.3rem;
        margin: 0;
        border: none;
        border-bottom: 1px solid {m['surface0']};
        position: fixed;
        top: 38px;
        left: 0;
        right: 0;
        z-index: 999;
        box-shadow: 0 2px 10px rgba(0,0,0,0.3);
        height: 50px;
        display: flex;
        align-items: center;
    }}
    [data-testid="stTabs"] [role="tab"] {{
        background: transparent;
        color: {m['subtext0']};
        border-radius: 8px;
        padding: 0 1rem !important;
        font-weight: 600;
        font-size: 0.88rem;
        border: none;
        transition: all 0.15s ease;
        height: 34px !important;
        min-height: 34px !important;
        max-height: 34px !important;
        line-height: 1 !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }}
    /* Reset inner span/markdown wrapper của Streamlit tab button */
    [data-testid="stTabs"] [role="tab"] > div,
    [data-testid="stTabs"] [role="tab"] p {{
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1 !important;
    }}
    [data-testid="stTabs"] [role="tab"]:hover {{
        background: {m['surface0']};
        color: {m['text']};
    }}
    [data-testid="stTabs"] [role="tab"][aria-selected="true"] {{
        background: linear-gradient(135deg, {m['mauve']}, {m['blue']});
        color: {m['crust']};
        box-shadow: 0 2px 8px rgba(203,166,247,0.25);
    }}
    [data-testid="stTabs"] [data-baseweb="tab-highlight"],
    [data-testid="stTabs"] [data-baseweb="tab-border"] {{
        display: none;
    }}

    /* === Chat list buttons — giống tab Chatbot/Dashboard nhưng dọc === */
    .chat-list-wrapper .stButton > button {{
        background: transparent;
        color: {m['subtext0']};
        border: none;
        border-radius: 10px;
        text-align: left;
        padding: 0.55rem 1.1rem;
        font-weight: 600;
        font-size: 0.92rem;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        width: 100%;
        transition: all 0.15s ease;
    }}
    .chat-list-wrapper .stButton > button:hover {{
        background: {m['surface0']};
        color: {m['text']};
    }}
    .chat-list-wrapper .stButton > button:focus {{
        box-shadow: none;
    }}
    .chat-list-wrapper.active .stButton > button {{
        background: linear-gradient(135deg, {m['mauve']}, {m['blue']});
        color: {m['crust']};
        box-shadow: 0 2px 8px rgba(203,166,247,0.25);
    }}
    .chat-list-trash .stButton > button {{
        background: transparent;
        color: {m['overlay0']};
        border: none;
        padding: 0.35rem 0.5rem;
        font-size: 0.8rem;
    }}
    .chat-list-trash .stButton > button:hover {{
        color: {m['red']};
        background: rgba(243,139,168,0.1);
    }}

    /* === New chat button (primary) === */
    .new-chat-btn .stButton > button {{
        background: linear-gradient(135deg, {m['mauve']}, {m['blue']});
        color: {m['crust']};
        border: none;
        border-radius: 12px;
        padding: 0.6rem 1rem;
        font-weight: 600;
        font-size: 0.92rem;
        box-shadow: 0 3px 12px rgba(203,166,247,0.2);
        transition: all 0.15s ease;
    }}
    .new-chat-btn .stButton > button:hover {{
        transform: translateY(-1px);
        box-shadow: 0 5px 18px rgba(203,166,247,0.3);
    }}

    /* === Chat list panel — chỉ là marker, styling thực tế áp lên COLUMN === */
    .chat-list-panel {{
        display: none;  /* div marker không hiển thị */
    }}

    /* Toàn bộ COLUMN bên trái (chứa marker .chat-list-panel + new chat btn + chat items)
       → fixed cứng tới viewport */
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child:has(.chat-list-panel) {{
        position: fixed !important;
        top: 96px;
        left: 1.5rem;
        width: calc(25vw - 2rem);
        max-height: calc(100vh - 115px);
        overflow-y: auto;
        z-index: 50;
        background: {m['mantle']};
        border: 1px solid {m['surface0']};
        border-radius: 14px;
        padding: 1rem 0.85rem;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child:has(.chat-list-panel)::-webkit-scrollbar {{
        width: 6px;
    }}
    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child:has(.chat-list-panel)::-webkit-scrollbar-thumb {{
        background: {m['surface1']};
        border-radius: 3px;
    }}

    /* Column thứ 2 (chat messages) bù margin-left để không bị fixed col1 che */
    [data-testid="stHorizontalBlock"]:has(.chat-list-panel) > [data-testid="stColumn"]:nth-child(2) {{
        margin-left: calc(25vw - 1rem);
    }}
    .chat-list-panel::-webkit-scrollbar {{ width: 6px; }}
    .chat-list-panel::-webkit-scrollbar-thumb {{
        background: {m['surface1']};
        border-radius: 3px;
    }}
    .chat-list-header {{
        color: {m['mauve']};
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        margin: 0 0 0.5rem 0.25rem;
    }}
    .chat-list-divider {{
        height: 1px;
        background: {m['surface0']};
        margin: 0.6rem 0;
    }}

    /* === Hero header — slim, FIXED top full-width === */
    .bds-hero {{
        background: linear-gradient(135deg, {m['mauve']} 0%, {m['blue']} 45%, {m['sapphire']} 100%);
        padding: 0.35rem 2rem;
        margin: 0;
        box-shadow: 0 3px 14px rgba(0,0,0,0.3);
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 1000;
        overflow: hidden;
        display: flex;
        justify-content: space-between;
        align-items: center;
        height: 38px;
    }}
    .bds-hero::before {{
        content: '';
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 15% 30%, rgba(255,255,255,0.18), transparent 45%),
            radial-gradient(circle at 85% 70%, rgba(245,194,231,0.15), transparent 50%);
        pointer-events: none;
    }}
    .bds-hero-left {{
        position: relative;
        z-index: 1;
        display: flex;
        align-items: baseline;
        gap: 0.7rem;
    }}
    .bds-hero h1 {{
        color: {m['crust']};
        font-size: 0.92rem;
        font-weight: 700;
        margin: 0;
        letter-spacing: -0.01em;
        line-height: 1.2;
    }}
    .bds-hero p {{
        color: rgba(17,17,27,0.7);
        font-size: 0.72rem;
        margin: 0;
        font-weight: 500;
    }}
    .bds-hero-brand {{
        color: {m['crust']};
        font-size: 0.82rem;
        font-weight: 700;
        opacity: 0.5;
        letter-spacing: -0.01em;
        position: relative;
        z-index: 1;
    }}

    /* === KPI cards === */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 1rem;
        margin: 1rem 0 1.5rem;
    }}
    .kpi-card {{
        background: {m['surface0']};
        border: 1px solid {m['surface1']};
        border-radius: 14px;
        padding: 1.1rem 1.25rem;
        transition: all 0.2s ease;
    }}
    .kpi-card:hover {{
        border-color: {m['mauve']};
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    }}
    .kpi-label {{
        color: {m['subtext0']};
        font-size: 0.78rem;
        font-weight: 500;
        margin-bottom: 0.4rem;
        letter-spacing: 0.02em;
        text-transform: uppercase;
    }}
    .kpi-value {{
        color: {m['text']};
        font-size: 1.7rem;
        font-weight: 700;
        line-height: 1.1;
        letter-spacing: -0.01em;
    }}
    .kpi-delta {{
        color: {m['green']};
        font-size: 0.8rem;
        font-weight: 500;
        margin-top: 0.35rem;
    }}
    .kpi-delta.neg {{ color: {m['red']}; }}
    .kpi-delta.muted {{ color: {m['overlay0']}; }}

    /* === Chart container card === */
    .chart-card {{
        background: {m['surface0']};
        border: 1px solid {m['surface1']};
        border-radius: 14px;
        padding: 1.1rem 1.25rem;
        margin-bottom: 1rem;
    }}
    .chart-card h3 {{
        color: {m['text']};
        font-size: 1.05rem;
        font-weight: 600;
        margin: 0 0 0.75rem 0;
    }}
    .chart-card .caption {{
        color: {m['subtext0']};
        font-size: 0.82rem;
        font-weight: 400;
        margin: 0 0 0.5rem 0;
    }}

    /* === Section divider === */
    .section-title {{
        color: {m['mauve']};
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 1.5rem 0 0.75rem 0;
        padding-left: 0.25rem;
        border-left: 3px solid {m['mauve']};
    }}

    /* === Empty state — welcome khi cuộc chat trống === */
    .empty-state {{
        text-align: center;
        padding: 4rem 2rem 2rem;
        max-width: 720px;
        margin: 0 auto;
    }}
    .empty-state-icon {{
        font-size: 3rem;
        margin-bottom: 0.75rem;
        opacity: 0.9;
    }}
    .empty-state h2 {{
        color: {m['text']} !important;
        font-size: 1.5rem;
        font-weight: 700;
        margin: 0 0 0.5rem 0;
        background: linear-gradient(135deg, {m['mauve']}, {m['blue']});
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .empty-state p {{
        color: {m['subtext0']};
        font-size: 0.95rem;
        margin: 0 0 1.5rem 0;
    }}
    .empty-state-hint {{
        color: {m['overlay1']};
        font-size: 0.8rem;
        font-weight: 500;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        margin: 0 0 0.75rem 0;
    }}

    /* === Sample prompt buttons (chỉ trong empty state) === */
    .sample-prompts .stButton > button {{
        background: {m['surface0']};
        color: {m['subtext1']};
        border: 1px solid {m['surface1']};
        border-radius: 12px;
        padding: 0.9rem 1rem;
        font-weight: 500;
        font-size: 0.86rem;
        text-align: left;
        white-space: normal;
        height: auto;
        min-height: 64px;
        transition: all 0.15s ease;
        line-height: 1.4;
    }}
    .sample-prompts .stButton > button:hover {{
        background: {m['surface1']};
        color: {m['text']};
        border-color: {m['mauve']};
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(203,166,247,0.15);
    }}

    /* === Chat messages === */
    [data-testid="stChatMessage"] {{
        background: {m['surface0']};
        border: 1px solid {m['surface1']};
        border-radius: 14px;
        padding: 0.85rem 1.1rem;
        margin-bottom: 0.6rem;
    }}
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {{
        color: {m['text']};
        line-height: 1.55;
    }}

    /* === Chat input — fixed bottom, bắt đầu sau chat list panel === */
    [data-testid="stChatInput"] {{
        position: fixed;
        bottom: 1.25rem;
        left: calc(25vw + 0.5rem);
        right: 2rem;
        z-index: 999;
        background: {m['surface0']};
        border: 1px solid {m['surface1']};
        border-radius: 14px;
        box-shadow: 0 8px 30px rgba(0,0,0,0.4);
    }}
    [data-testid="stChatInput"]:focus-within {{
        border-color: {m['mauve']};
        box-shadow: 0 8px 30px rgba(0,0,0,0.5), 0 0 0 3px rgba(203,166,247,0.15);
    }}
    [data-testid="stChatInput"] textarea {{
        background: transparent !important;
        color: {m['text']} !important;
    }}

    /* Padding-bottom cho khu chat để messages không bị input che */
    .chat-messages-area {{
        padding-bottom: 6rem;
    }}
    /* Spacer cuối chat area: buộc page LUÔN có ~70vh chỗ scroll
       → user msg vừa gửi mới scroll-into-view block:'start' lên top được.
       Không có spacer này, page quá ngắn = browser không scroll được gì. */
    .chat-messages-area::after {{
        content: '';
        display: block;
        min-height: 70vh;
    }}

    /* Scroll-margin bù trừ hero (38px) + tabs (50px) + buffer = ~110px.
       Khi scrollIntoView block:'start', element sẽ dừng dưới tab bar chứ không bị che. */
    #new-user-msg-anchor,
    #last-user-anchor {{
        scroll-margin-top: 110px;
    }}

    /* === Radio buttons === */
    [data-testid="stRadio"] label {{
        color: {m['text']} !important;
    }}

    /* === Selectbox & inputs === */
    [data-baseweb="select"] > div {{
        background: {m['surface0']} !important;
        border-color: {m['surface1']} !important;
    }}

    /* === Info / Toast === */
    [data-testid="stAlert"] {{
        background: {m['surface0']};
        border-left: 4px solid {m['sapphire']};
        border-radius: 10px;
    }}

    /* === Headers === */
    h1, h2, h3, h4 {{
        color: {m['text']} !important;
    }}

    /* === Hide Streamlit header/toolbar HOÀN TOÀN ===
       stHeader là dải đen absolute top:0 height:60px z-index:999990 của Streamlit,
       cao hơn hero (z:1000) → che mất nửa trên tabs. Phải display:none, không chỉ visibility:hidden */
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stStatusWidget"],
    header[data-testid="stHeader"] {{
        display: none !important;
        height: 0 !important;
    }}
    #MainMenu, footer {{
        visibility: hidden;
    }}
    </style>
    """


def apply_theme():
    """Inject CSS + register plotly template. Gọi 1 lần ở đầu mỗi page."""
    st.markdown(_css(), unsafe_allow_html=True)
    pio.templates["catppuccin_mocha"] = _build_plotly_template()
    pio.templates.default = "catppuccin_mocha"


def hero(title: str, subtitle: str = ""):
    sub_html = f'<p>{subtitle}</p>' if subtitle else ""
    st.markdown(
        f'''<div class="bds-hero">
            <div class="bds-hero-left">
                <h1>{title}</h1>
                {sub_html}
            </div>
            <div class="bds-hero-brand">❀ BDS</div>
        </div>''',
        unsafe_allow_html=True,
    )


def kpi_cards(items: list[dict]):
    """items: [{label, value, delta?, delta_kind?: 'pos'|'neg'|'muted'}]"""
    cards = []
    for it in items:
        delta_html = ""
        if it.get("delta"):
            kind = it.get("delta_kind", "pos")
            cls = {"pos": "", "neg": " neg", "muted": " muted"}.get(kind, "")
            delta_html = f'<div class="kpi-delta{cls}">{it["delta"]}</div>'
        cards.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{it["label"]}</div>'
            f'<div class="kpi-value">{it["value"]}</div>'
            f'{delta_html}'
            f'</div>'
        )
    st.markdown(f'<div class="kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def section(title: str):
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
