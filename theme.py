"""
Export Haret · Pedidos — Sistema de diseño central
===================================================
Línea visual unificada con la app de CRM/Marketing: **"Ejecutivo neutro +
Esmeralda"** (premium SaaS). Lienzo gris-tinta frío, esmeralda como ÚNICO acento
de marca, tinta para CTAs secundarios, tipografía Inter con tracking ajustado,
bordes hairline fríos, mucho aire. Se inyecta una vez por página con `aplicar()`.
"""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700;800;900&display=swap');

:root{
  /* superficies — gris tinta neutro */
  --bg:#f5f7f8; --bg-soft:#eceff3; --card:#ffffff; --bg-elevated:#fbfcfd;
  /* marca — esmeralda (único acento) */
  --brand:#0c6e51; --brand-700:#0a5d44; --brand-dark:#084a37;
  --brand-soft:rgba(12,110,81,.075); --brand-ring:rgba(12,110,81,.16);
  --accent:#10a37a; --accent-dark:#0d8a67; --accent-soft:rgba(16,163,122,.12);
  /* tinta — secundario premium (negro elegante) */
  --ink:#1b2531; --ink-hover:#27323f; --on-ink:#ffffff;
  /* texto */
  --ink-text:#131a21; --muted:#566472; --muted-2:#8b95a3;
  /* bordes — hairline frío */
  --line:#e7eaef; --line-soft:#dce1e8; --line-strong:#c6ccd6;
  /* forma */
  --radius:14px; --radius-sm:10px; --radius-lg:20px;
  --shadow-sm:0 1px 2px rgba(18,28,42,.05), 0 2px 6px -2px rgba(18,28,42,.06);
  --shadow:0 4px 14px -4px rgba(18,28,42,.10), 0 2px 6px -2px rgba(18,28,42,.05);
  --shadow-lg:0 24px 54px -18px rgba(18,28,42,.24);
}

/* ---- tipografia y fondo ---- */
html, body, [class*="css"], .stApp, button, input, textarea, select{
  font-family:'Inter',-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
}
.stApp{ background:var(--bg); color:var(--ink-text); letter-spacing:-.006em; }
.block-container{ max-width:820px; padding-top:1.2rem; padding-bottom:88px; }
h1,h2,h3,h4{ color:var(--ink-text); letter-spacing:-.02em; font-weight:800; }
h4{ letter-spacing:.04em; }
p, label, span, li{ color:var(--ink-text); }
a{ color:var(--brand); text-decoration:none; font-weight:600; }
a:hover{ color:var(--brand-700); text-decoration:none; }

/* ---- botones ---- */
.stButton>button, .stDownloadButton>button, .stLinkButton>a, .stFormSubmitButton>button{
  border-radius:11px; font-weight:600; padding:.62rem 1.1rem; font-size:.92rem;
  border:1px solid var(--line-soft); background:var(--card); color:var(--ink-text); min-height:44px;
  letter-spacing:-.01em; box-shadow:var(--shadow-sm);
  transition:transform .12s ease, box-shadow .18s ease, background .16s ease, border-color .16s ease, color .16s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover, .stFormSubmitButton>button:hover{
  border-color:var(--line-strong); background:var(--bg-elevated); transform:translateY(-1px);
  box-shadow:var(--shadow);
}
.stButton>button:active, .stDownloadButton>button:active, .stFormSubmitButton>button:active{
  transform:translateY(0) scale(.99);
}
/* primario = esmeralda */
.stButton>button[kind="primary"], .stDownloadButton>button,
.stFormSubmitButton>button[kind="primary"], .stFormSubmitButton>button[kind="primaryFormSubmit"]{
  background:var(--brand); border-color:var(--brand); color:#fff;
  box-shadow:0 6px 16px -6px rgba(12,110,81,.45);
}
.stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover,
.stFormSubmitButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primaryFormSubmit"]:hover{
  background:var(--brand-700); border-color:var(--brand-700);
  box-shadow:0 12px 26px -8px rgba(12,110,81,.5);
}
/* secundario = contorno frio */
.stButton>button[kind="secondary"], .stFormSubmitButton>button[kind="secondaryFormSubmit"]{
  background:var(--card); color:var(--ink-text); border-color:var(--line-soft); }
.stButton>button[kind="secondary"]:hover,
.stFormSubmitButton>button[kind="secondaryFormSubmit"]:hover{
  background:var(--bg-soft); border-color:var(--line-strong); }
.stLinkButton>a{ background:var(--bg-soft); color:var(--brand); border-color:var(--line); }
.stLinkButton>a:hover{ background:#e3ebf0; }

/* ---- inputs ---- */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"]>div, .stMultiSelect div[data-baseweb="select"]>div{
  border-radius:11px !important; border-color:var(--line-soft) !important; background:var(--card) !important;
}
.stTextInput input, .stNumberInput input{ min-height:44px !important; font-size:.96rem !important; }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus{
  border-color:var(--brand) !important; box-shadow:0 0 0 3px var(--brand-ring) !important;
}
.stNumberInput button{ border-radius:9px; transition:background .15s ease;
  background:var(--bg-soft); color:var(--brand); font-weight:700; }
.stNumberInput button:hover{ background:#e3ebf0; }

/* ---- SUPERFICIES: contenedores con borde y formularios = tarjetas ---- */
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--card); border:1px solid var(--line) !important; border-radius:var(--radius) !important;
  box-shadow:var(--shadow-sm); transition:box-shadow .2s ease, border-color .2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{ box-shadow:var(--shadow); border-color:var(--line-soft); }
[data-testid="stForm"]{
  background:var(--card); border:1px solid var(--line) !important; border-radius:var(--radius) !important;
  box-shadow:var(--shadow-sm); padding:1.1rem 1.2rem !important;
}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"]{ gap:4px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ border-radius:9px 9px 0 0; font-weight:600; color:var(--muted); letter-spacing:-.01em; }
.stTabs [aria-selected="true"]{ color:var(--brand) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--brand) !important; }

/* ---- metricas / expanders / alerts ---- */
[data-testid="stMetricValue"]{ color:var(--brand-dark); font-weight:800; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.streamlit-expanderHeader, details summary{ font-weight:600; }
[data-testid="stExpander"]{ border-radius:var(--radius-sm); border-color:var(--line); box-shadow:var(--shadow-sm); }
[data-testid="stDataFrame"]{ border-radius:11px; overflow:hidden; box-shadow:var(--shadow-sm); }

.eh-accent{ color:var(--accent) !important; }

/* ---- cabecera de seccion (chip numerado + titulo) ---- */
.eh-sec{ display:flex; align-items:center; gap:13px; margin:30px 0 16px; }
.eh-sec-num{ width:33px; height:33px; border-radius:10px; flex:0 0 auto;
  display:flex; align-items:center; justify-content:center; color:#fff;
  font-weight:800; font-size:14px; font-variant-numeric:tabular-nums;
  background:var(--brand);
  box-shadow:0 6px 16px -6px rgba(12,110,81,.45); }
.eh-sec-title{ font-size:21px; font-weight:800; color:var(--ink-text); letter-spacing:-.02em; line-height:1.1; }

/* ---- alertas refinadas ---- */
div[data-testid="stAlert"]{ border-radius:12px !important; border:1px solid var(--line);
  box-shadow:var(--shadow-sm); }
div[data-testid="stAlert"] p{ font-size:.92rem; }

.eh-card{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:16px; box-shadow:var(--shadow-sm); }

hr{ border:none; border-top:1px solid var(--line); margin:.5rem 0; }
:focus-visible{ outline:none; box-shadow:0 0 0 3px var(--brand-ring); }

/* ---- densidad / aire ---- */
[data-testid="stVerticalBlock"]{ gap:.65rem; }
[data-testid="stElementContainer"]{ margin-bottom:0; }

/* ---- CTA final de confirmar = esmeralda (mono-marca) ---- */
.st-key-portal_guardar button, .st-key-portal_guardar button[kind="primary"]{
  background:var(--brand) !important; border-color:var(--brand) !important; color:#fff !important;
  box-shadow:0 8px 20px -8px rgba(12,110,81,.5) !important; font-weight:700 !important; min-height:52px !important;
  font-size:1.02rem !important;
}
.st-key-portal_guardar button:hover{
  background:var(--brand-700) !important; border-color:var(--brand-700) !important;
  box-shadow:0 14px 30px -8px rgba(12,110,81,.55) !important;
}

/* ---- movil ---- */
@media (max-width:768px){
  .block-container{ padding-left:.85rem; padding-right:.85rem; }
  .stNumberInput button{ min-width:44px; min-height:44px; font-size:1.2rem; }
  .stButton>button, .stDownloadButton>button{ padding:.7rem 1rem; }
  .eh-sec-title{ font-size:19px; }
}
</style>
"""


def aplicar():
    """Inyecta el tema. Llamar una vez al inicio de cada página."""
    import streamlit as st
    st.markdown(THEME_CSS, unsafe_allow_html=True)
