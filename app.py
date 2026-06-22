from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.application import ChatApplicationService, ChatResponse
from src.config import get_settings
from src.ui.components import schema_suggestions


st.set_page_config(page_title="Gopak", layout="wide", initial_sidebar_state="collapsed")
settings = get_settings()


@st.cache_resource(show_spinner=False)
def get_service() -> ChatApplicationService:
    return ChatApplicationService(settings)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --bg: #F8F8FB;
            --sidebar: #F1F3F7;
            --assistant: #FFFFFF;
            --user: #EEF2FF;
            --border: #E5E7EF;
            --primary: #AEBCE8;
            --secondary: #C8DCC8;
            --text: #30323A;
            --muted: #7A7E89;
        }
        html, body, [class*="css"] {
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .stApp { background: var(--bg); color: var(--text); }
        [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
        [data-testid="stDeployButton"], [data-testid="collapsedControl"], #MainMenu, footer {
            display: none !important;
        }
        [data-testid="stSidebar"] {
            background: var(--sidebar);
            border-right: 1px solid var(--border);
        }
        .block-container { max-width: 900px; padding: 2.2rem 1.2rem 7rem; }
        .brand { font-size: 1.45rem; font-weight: 760; margin-bottom: 1.2rem; }
        .empty { color: var(--muted); text-align: center; padding: 18vh 0 1rem; font-size: 1.45rem; }
        .answer-card {
            background: var(--assistant);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1rem 1.1rem;
            margin: .35rem 0 .85rem;
        }
        .answer-title { color: var(--muted); font-size: .88rem; margin-bottom: .35rem; }
        .answer-value { font-size: 2rem; font-weight: 760; margin-bottom: .25rem; }
        .answer-summary, .meta-line { color: var(--muted); font-size: .92rem; }
        [data-testid="stChatMessage"] { background: transparent; padding: .2rem 0; }
        [data-testid="stChatMessageAvatarAssistant"], [data-testid="stChatMessageAvatarUser"] { display: none; }
        [data-testid="stChatMessageContent"] { width: 100%; max-width: 100%; margin-left: 0 !important; }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
            background: var(--assistant);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: .78rem .95rem;
        }
        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] {
            margin-left: auto;
            max-width: 78%;
            background: var(--user);
        }
        .stButton > button, .stDownloadButton > button {
            border: 1px solid var(--border);
            background: #fff;
            color: var(--text);
            border-radius: 999px;
            min-height: 2.35rem;
            font-weight: 650;
            box-shadow: none;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            border-color: var(--primary);
            background: #F6F8FF;
        }
        [data-testid="stChatInput"] {
            background: rgba(248, 248, 251, .94);
            border-top: 1px solid var(--border);
            backdrop-filter: blur(14px);
        }
        [data-testid="stChatInput"] textarea {
            border-radius: 18px !important;
            border: 1px solid var(--border) !important;
            background: #fff !important;
            box-shadow: none !important;
        }
        [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
        details { border: 1px solid var(--border) !important; border-radius: 8px !important; background: #fff !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_messages(conversation_id: str) -> list[dict]:
    detail = service.get_conversation(conversation_id)
    if not detail:
        return []
    return [{"role": item.role, "content": item.content} for item in detail.messages if item.role in {"user", "assistant"}]


def render_response(response: ChatResponse, debug: bool = False) -> None:
    if response.response_type == "scalar":
        st.markdown(
            f"""
            <div class="answer-card">
              <div class="answer-title">{response.title}</div>
              <div class="answer-value">{response.primary_value or ""}</div>
              <div class="answer-summary">{response.summary}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        if response.title:
            st.markdown(f"**{response.title}**")
        if response.summary:
            st.write(response.summary)

    if response.chart:
        data = pd.DataFrame(response.chart.data)
        if not data.empty and response.chart.y_keys:
            y_key = response.chart.y_keys[0]
            if response.chart.type == "line":
                st.line_chart(data, x=response.chart.x_key, y=y_key)
            elif response.chart.type == "pie":
                fig = px.pie(data, names=response.chart.x_key, values=y_key)
                st.plotly_chart(fig, width="stretch")
            else:
                st.bar_chart(data, x=response.chart.x_key, y=y_key)

    if response.table:
        st.dataframe(pd.DataFrame(response.table.rows, columns=response.table.columns), width="stretch", hide_index=True, height=360)

    if response.downloads:
        cols = st.columns([0.24, 0.24, 0.52])
        for idx, item in enumerate(response.downloads[:2]):
            path = service.resolve_artifact(item.id)
            if path:
                with cols[idx]:
                    st.download_button(item.label, data=path.read_bytes(), file_name=item.filename, mime=item.mime_type)

    if response.sources or response.filters or debug:
        with st.expander("Nguồn và bộ lọc", expanded=False):
            for source in response.sources:
                st.caption(f"{source.name} · {source.rows:,} dòng")
            for item in response.filters:
                st.caption(f"{item.label} {item.operator} {item.value}")
            if debug:
                st.json(response.metadata)


service = get_service()
inject_styles()

if "conversation_id" not in st.session_state:
    created = service.create_conversation()
    st.session_state.conversation_id = created.id
if "messages" not in st.session_state:
    st.session_state.messages = load_messages(st.session_state.conversation_id)

with st.sidebar:
    st.markdown('<div class="brand">Gopak</div>', unsafe_allow_html=True)
    if st.button("Chat mới", use_container_width=True):
        created = service.create_conversation()
        st.session_state.conversation_id = created.id
        st.session_state.messages = []
        st.rerun()

    conversations = service.list_conversations()
    for item in conversations:
        active = item.id == st.session_state.conversation_id
        label = f"{'• ' if active else ''}{item.title}"
        if st.button(label, key=f"conv_{item.id}", use_container_width=True):
            st.session_state.conversation_id = item.id
            st.session_state.messages = load_messages(item.id)
            st.rerun()

    st.write("")
    debug = st.toggle("Debug", value=False)
    health = service.health()
    if not health.ollama_available or not health.memory_available:
        st.caption("Hệ thống đang degraded")

st.markdown('<div class="brand">Gopak</div>', unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown('<div class="empty">Tôi có thể giúp gì cho bạn?</div>', unsafe_allow_html=True)
    suggested_question = None
    for idx, suggestion in enumerate(schema_suggestions(service.get_catalog())[:4]):
        if st.button(suggestion, key=f"suggestion_{idx}", use_container_width=True):
            suggested_question = suggestion
            break
else:
    suggested_question = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

typed_question = st.chat_input("")
question = typed_question or suggested_question
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Đang phân tích..."):
            response = service.process_message(st.session_state.conversation_id, question, debug=debug)
        render_response(response, debug=debug)
    st.session_state.messages.append({"role": "assistant", "content": response.primary_value or response.summary or response.title})
