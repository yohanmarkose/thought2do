"""Theme system for Streamlit.

Exposes DARK_THEME / LIGHT_THEME palettes and `get_custom_css(theme)`
which returns the global CSS string applied via `st.markdown` to
style backgrounds, buttons, inputs, task cards, priority badges,
category pills, and the recording-button pulse animation.
"""
from typing import Dict

import streamlit as st

DARK_THEME: Dict[str, str] = {
    "bg": "#0E1117",
    "secondary_bg": "#1A1D23",
    "card_bg": "#1E2128",
    "text": "#FAFAFA",
    "muted_text": "#C9D1D9",
    "accent": "#6C63FF",
    "accent_hover": "#5B53D9",
    "success": "#00D68F",
    "warning": "#FFB547",
    "danger": "#FF6B6B",
    "muted": "#8B949E",
    "priority_critical": "#FF6B6B",
    "priority_high": "#FFB547",
    "priority_medium": "#6C63FF",
    "priority_low": "#8B949E",
    "shadow": "rgba(0,0,0,0.35)",
}

LIGHT_THEME: Dict[str, str] = {
    "bg": "#FFFFFF",
    "secondary_bg": "#F6F8FA",
    "card_bg": "#FFFFFF",
    "text": "#24292F",
    "muted_text": "#57606A",
    "accent": "#6C63FF",
    "accent_hover": "#5B53D9",
    "success": "#00D68F",
    "warning": "#FFB547",
    "danger": "#FF6B6B",
    "muted": "#8B949E",
    "priority_critical": "#FF6B6B",
    "priority_high": "#FFB547",
    "priority_medium": "#6C63FF",
    "priority_low": "#8B949E",
    "shadow": "rgba(140,149,159,0.2)",
}


def get_theme() -> Dict[str, str]:
    """Return the active theme palette (reads `st.session_state.theme`)."""
    mode = st.session_state.get("theme", "dark")
    return LIGHT_THEME if mode == "light" else DARK_THEME


def get_custom_css(theme: Dict[str, str]) -> str:
    """Build a single <style> block worth of CSS using the theme palette.

    The returned string does NOT include the surrounding <style> tags — the
    caller is expected to wrap it (the landing page wraps once; each
    multipage page could wrap again if it wants to re-inject).
    """
    t = theme
    return f"""
    /* ---------- Theme transition (smooth color switching) ---------- */
    .stApp, .stApp *, section[data-testid="stSidebar"], section[data-testid="stSidebar"] * {{
        transition: background-color 0.25s ease, color 0.25s ease, border-color 0.25s ease;
    }}

    /* ---------- Base page ---------- */
    .stApp {{
        background-color: {t['bg']};
        color: {t['text']};
    }}
    .stApp, .stApp p, .stApp label, .stApp span, .stApp div {{
        color: {t['text']};
    }}

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {{
        background-color: {t['secondary_bg']};
        border-right: 1px solid {t['muted']}30;
    }}
    section[data-testid="stSidebar"] * {{
        color: {t['text']};
    }}

    /* ---------- Primary buttons ---------- */
    .stButton > button,
    .stForm button,
    .stDownloadButton > button {{
        background-color: {t['accent']};
        color: #FFFFFF;
        border: none;
        font-weight: 500;
        border-radius: 0.5rem;
        transition: all 0.2s ease;
    }}
    .stButton > button:hover,
    .stForm button:hover,
    .stDownloadButton > button:hover {{
        background-color: {t['accent_hover']};
        transform: translateY(-1px);
        box-shadow: 0 4px 10px {t['shadow']};
    }}
    .stButton > button:focus,
    .stForm button:focus {{
        outline: 2px solid {t['accent']}80;
        outline-offset: 2px;
    }}

    /* ---------- Inputs ---------- */
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input,
    .stDateInput input {{
        background-color: {t['card_bg']};
        color: {t['text']};
        border: 1px solid {t['muted']}55;
        border-radius: 0.5rem;
    }}
    .stTextInput input:focus,
    .stTextArea textarea:focus {{
        border-color: {t['accent']};
        box-shadow: 0 0 0 2px {t['accent']}33;
    }}
    .stSelectbox > div[data-baseweb="select"] > div {{
        background-color: {t['card_bg']};
        border-color: {t['muted']}55;
        color: {t['text']};
    }}

    /* ---------- Tabs ---------- */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0.5rem;
        border-bottom: 1px solid {t['muted']}33;
    }}
    .stTabs [data-baseweb="tab"] {{
        color: {t['muted_text']};
    }}
    .stTabs [aria-selected="true"] {{
        color: {t['accent']};
    }}

    /* ---------- Task cards ---------- */
    .task-card {{
        background: {t['card_bg']};
        border: 1px solid {t['muted']}22;
        border-left: 4px solid {t['muted']};
        padding: 0.9rem 1rem;
        border-radius: 0.6rem;
        margin-bottom: 0.75rem;
        transition: all 0.2s ease;
    }}
    .task-card:hover {{
        box-shadow: 0 6px 14px {t['shadow']};
        transform: translateY(-1px);
    }}
    .task-card-critical {{ border-left-color: {t['priority_critical']}; }}
    .task-card-high     {{ border-left-color: {t['priority_high']};     }}
    .task-card-medium   {{ border-left-color: {t['priority_medium']};   }}
    .task-card-low      {{ border-left-color: {t['priority_low']};      }}

    /* ---------- Badges ---------- */
    .badge {{
        display: inline-block;
        padding: 0.15rem 0.6rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 0.3rem;
        white-space: nowrap;
    }}
    .badge-critical {{ background: {t['priority_critical']}; color: #FFFFFF; }}
    .badge-high     {{ background: {t['priority_high']};     color: #1a1a1a; }}
    .badge-medium   {{ background: {t['priority_medium']};   color: #FFFFFF; }}
    .badge-low      {{ background: {t['priority_low']};      color: #FFFFFF; }}
    .badge-status-pending     {{ background: {t['accent']}33;   color: {t['accent']}; }}
    .badge-status-in-progress {{ background: {t['warning']}33;  color: {t['warning']}; }}
    .badge-status-completed   {{ background: {t['success']}33;  color: {t['success']}; }}
    .badge-status-cancelled   {{ background: {t['muted']}33;    color: {t['muted']}; }}

    /* ---------- Category pill ---------- */
    .category-pill {{
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 0.4rem;
        font-size: 0.72rem;
        background: {t['secondary_bg']};
        color: {t['muted_text']};
        border: 1px solid {t['muted']}55;
        margin-right: 0.3rem;
    }}

    /* ---------- Landing page ---------- */
    .landing-hero {{
        text-align: center;
        padding: 3rem 0 1.5rem 0;
    }}
    .landing-title {{
        font-size: 3.6rem;
        font-weight: 700;
        margin: 0;
        background: linear-gradient(135deg, {t['accent']} 0%, {t['priority_critical']} 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }}
    .landing-tagline {{
        font-size: 1.4rem;
        font-weight: 300;
        letter-spacing: 0.05em;
        margin: 0.5rem 0 0.25rem 0;
        color: {t['text']};
    }}
    .landing-sub {{
        color: {t['muted_text']};
        font-size: 1rem;
        max-width: 520px;
        margin: 0.5rem auto 0 auto;
    }}

    /* ---------- Scrollbar ---------- */
    ::-webkit-scrollbar        {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-track  {{ background: {t['secondary_bg']}; }}
    ::-webkit-scrollbar-thumb  {{ background: {t['muted']}; border-radius: 4px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {t['accent']}; }}

    /* ---------- Pulsing glow (active recording button) ---------- */
    @keyframes pulse-glow {{
        0%, 100% {{ box-shadow: 0 0 0 0   {t['priority_critical']}b3; }}
        50%      {{ box-shadow: 0 0 0 14px {t['priority_critical']}00; }}
    }}
    .recording-active {{
        animation: pulse-glow 1.4s ease-in-out infinite;
    }}

    /* ---------- Typography ---------- */
    .stApp h1 {{
        font-weight: 700;
        letter-spacing: -0.02em;
        margin-bottom: 0.25rem;
    }}
    .stApp h2 {{
        font-weight: 650;
        letter-spacing: -0.01em;
    }}
    .stApp h3, .stApp h4, .stApp h5 {{
        font-weight: 600;
    }}

    /* ---------- Chat empty state ---------- */
    .chat-empty {{
        text-align: center;
        padding: 3rem 1rem;
        background: {t['secondary_bg']};
        border: 1px dashed {t['muted']}55;
        border-radius: 1rem;
    }}
    .chat-empty-icon {{
        font-size: 2.8rem;
        margin-bottom: 0.75rem;
    }}
    .chat-empty-title {{
        font-size: 1.15rem;
        font-weight: 600;
        color: {t['text']};
        margin-bottom: 0.5rem;
    }}
    .chat-empty-sub {{
        color: {t['muted_text']};
        font-size: 0.9rem;
        max-width: 560px;
        margin: 0 auto;
        line-height: 1.55;
    }}
    .chat-empty-sub em {{
        color: {t['accent']};
        font-style: normal;
        font-weight: 500;
    }}

    /* ---------- Chat bubble refinement ---------- */
    [data-testid="stChatMessage"] {{
        background: {t['card_bg']};
        border: 1px solid {t['muted']}22;
        border-radius: 0.9rem;
        padding: 0.75rem 1rem !important;
        margin-bottom: 0.6rem;
    }}
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
        background: {t['accent']}14;
        border-color: {t['accent']}40;
    }}

    /* ---------- Metric cards ---------- */
    [data-testid="stMetric"] {{
        background: {t['card_bg']};
        border: 1px solid {t['muted']}22;
        border-radius: 0.7rem;
        padding: 0.85rem 1rem;
        transition: all 0.2s ease;
    }}
    [data-testid="stMetric"]:hover {{
        border-color: {t['accent']}55;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px {t['shadow']};
    }}
    [data-testid="stMetricLabel"] {{
        color: {t['muted_text']} !important;
        font-size: 0.78rem !important;
        font-weight: 500 !important;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }}
    [data-testid="stMetricValue"] {{
        font-size: 1.7rem !important;
        font-weight: 700 !important;
        color: {t['text']} !important;
    }}

    /* ---------- Dividers ---------- */
    hr {{
        border-color: {t['muted']}33 !important;
        margin: 1rem 0 !important;
    }}

    /* ---------- Expanders ---------- */
    [data-testid="stExpander"] details {{
        background: {t['card_bg']};
        border: 1px solid {t['muted']}22;
        border-radius: 0.6rem;
    }}
    [data-testid="stExpander"] summary {{
        font-weight: 500;
        padding: 0.5rem 0.75rem !important;
    }}

    /* ---------- Tabs ---------- */
    .stTabs [data-baseweb="tab-list"] {{
        background: {t['secondary_bg']};
        padding: 0.3rem;
        border-radius: 0.6rem;
        border-bottom: none;
    }}
    .stTabs [data-baseweb="tab"] {{
        background: transparent;
        padding: 0.5rem 1rem;
        border-radius: 0.4rem;
        font-weight: 500;
    }}
    .stTabs [aria-selected="true"] {{
        background: {t['card_bg']};
        color: {t['accent']} !important;
        box-shadow: 0 1px 3px {t['shadow']};
    }}

    /* ---------- Secondary buttons ---------- */
    .stButton > button[kind="secondary"] {{
        background: {t['secondary_bg']};
        color: {t['text']};
        border: 1px solid {t['muted']}44;
    }}
    .stButton > button[kind="secondary"]:hover {{
        background: {t['card_bg']};
        border-color: {t['accent']}77;
        color: {t['accent']};
    }}

    /* ---------- Task card body cleanup ---------- */
    .task-card {{
        margin-bottom: 0.55rem;
    }}

    /* ---------- Assistant page section headers ---------- */
    .chat-section-label {{
        display: flex;
        align-items: center;
        gap: 0.6rem;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: {t['muted']};
        margin: 0.25rem 0 0.75rem 0;
    }}
    .chat-section-label::after {{
        content: '';
        flex: 1;
        height: 1px;
        background: linear-gradient(to right, {t['muted']}55, transparent);
    }}

    .input-section-banner {{
        background: linear-gradient(135deg, {t['secondary_bg']} 0%, {t['card_bg']} 100%);
        border: 1px solid {t['accent']}44;
        border-top: 3px solid {t['accent']};
        border-radius: 0.9rem 0.9rem 0 0;
        padding: 0.8rem 1.1rem;
        margin-top: 1.75rem;
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }}
    .input-section-icon {{
        font-size: 1.15rem;
    }}
    .input-section-title {{
        font-size: 0.88rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: {t['accent']};
    }}
    .input-section-sub {{
        font-size: 0.78rem;
        color: {t['muted_text']};
        margin-left: auto;
        font-style: italic;
    }}
    """
