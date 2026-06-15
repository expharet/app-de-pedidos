"""
Export Haret · Sistema de diseño (tema visual central)
======================================================
Una sola fuente para el aspecto del portal: estética **premium** (verde de marca
+ acento naranja cálido), tipografía limpia, superficies con profundidad sutil,
mucho aire y componentes coherentes. Se inyecta una vez por página con `aplicar()`.
"""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root{
  --brand:#1B7A3C;        /* verde marca */
  --brand-700:#176836;    /* hover */
  --brand-dark:#0F4F29;   /* titulos / degradado */
  --brand-soft:#EAF3EC;   /* fondo verde suave */
  --accent:#C66A2E;       /* naranja calido */
  --accent-dark:#A8531E;
  --ink:#19231D;          /* texto */
  --muted:#65726B;        /* texto secundario */
  --line:#E7EDE8;         /* bordes */
  --bg:#F4F8F5;           /* fondo app */
  --card:#FFFFFF;
  --radius:16px;
  --radius-lg:20px;
  --shadow-sm:0 1px 2px rgba(20,60,40,.05);
  --shadow:0 1px 3px rgba(20,60,40,.05), 0 12px 32px rgba(20,60,40,.07);
  --shadow-lg:0 18px 44px rgba(20,60,40,.12);
}

/* ---- tipografia y fondo ---- */
html, body, [class*="css"], .stApp, button, input, textarea, select{
  font-family:'Inter',-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
.stApp{ background:var(--bg); color:var(--ink); }
.block-container{ max-width:820px; padding-top:1.2rem; padding-bottom:88px; }
h1,h2,h3,h4{ color:var(--brand-dark); letter-spacing:-.4px; font-weight:800; }
p, label, span, li{ color:var(--ink); }
a{ color:var(--brand); text-decoration:none; font-weight:600; }
a:hover{ text-decoration:underline; }

/* ---- botones (dinamicos, redondeados) ---- */
.stButton>button, .stDownloadButton>button, .stLinkButton>a, .stFormSubmitButton>button{
  border-radius:14px; font-weight:700; padding:.7rem 1.15rem; font-size:.96rem;
  border:1px solid var(--line); background:#fff; color:var(--ink); min-height:46px;
  transition:transform .12s ease, box-shadow .2s ease, background .2s ease, border-color .2s ease, color .2s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover, .stFormSubmitButton>button:hover{
  transform:translateY(-1px); box-shadow:0 9px 22px rgba(20,60,40,.13); border-color:#cfe0d4;
}
.stButton>button:active, .stDownloadButton>button:active, .stFormSubmitButton>button:active{
  transform:translateY(0) scale(.99); box-shadow:0 2px 6px rgba(20,60,40,.10);
}
/* primario = verde marca */
.stButton>button[kind="primary"], .stDownloadButton>button,
.stFormSubmitButton>button[kind="primary"], .stFormSubmitButton>button[kind="primaryFormSubmit"]{
  background:var(--brand); border-color:var(--brand); color:#fff;
  box-shadow:0 6px 16px rgba(20,80,45,.22);
}
.stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover,
.stFormSubmitButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primaryFormSubmit"]:hover{
  background:var(--brand-700); border-color:var(--brand-700);
  box-shadow:0 12px 26px rgba(20,80,45,.30);
}
/* secundario = contorno verde */
.stButton>button[kind="secondary"], .stFormSubmitButton>button[kind="secondaryFormSubmit"]{
  background:#fff; color:var(--brand); border-color:#cfe0d4; }
.stButton>button[kind="secondary"]:hover,
.stFormSubmitButton>button[kind="secondaryFormSubmit"]:hover{
  background:var(--brand-soft); border-color:var(--brand); }
.stLinkButton>a{ background:var(--brand-soft); color:var(--brand-dark); border-color:#cfe0d4; }
.stLinkButton>a:hover{ background:#dfeede; text-decoration:none; }

/* ---- inputs comodos ---- */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"]>div, .stMultiSelect div[data-baseweb="select"]>div{
  border-radius:13px !important; border-color:var(--line) !important; background:#fff !important;
}
.stTextInput input, .stNumberInput input{ min-height:46px !important; font-size:1rem !important; }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus{
  border-color:var(--brand) !important; box-shadow:0 0 0 3px rgba(27,122,60,.15) !important;
}
.stNumberInput button{ border-radius:11px; transition:background .15s ease;
  background:var(--brand-soft); color:var(--brand); font-weight:800; }
.stNumberInput button:hover{ background:#dcebe0; }

/* ---- SUPERFICIES PREMIUM: contenedores con borde y formularios = tarjetas elevadas ---- */
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--card); border:1px solid var(--line) !important; border-radius:var(--radius-lg) !important;
  box-shadow:var(--shadow); transition:box-shadow .2s ease, transform .2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover{ box-shadow:var(--shadow-lg); }
[data-testid="stForm"]{
  background:var(--card); border:1px solid var(--line) !important; border-radius:var(--radius-lg) !important;
  box-shadow:var(--shadow); padding:1.1rem 1.2rem !important;
}

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"]{ gap:6px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ border-radius:10px 10px 0 0; font-weight:700; color:var(--muted); }
.stTabs [aria-selected="true"]{ color:var(--brand) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--brand) !important; }

/* ---- metricas / expanders / alerts ---- */
[data-testid="stMetricValue"]{ color:var(--brand-dark); font-weight:800; }
.streamlit-expanderHeader, details summary{ font-weight:700; }
[data-testid="stExpander"]{ border-radius:var(--radius); border-color:var(--line); box-shadow:var(--shadow-sm); }
[data-testid="stDataFrame"]{ border-radius:13px; overflow:hidden; box-shadow:var(--shadow-sm); }

.eh-accent{ color:var(--accent) !important; }

/* ---- cabecera de seccion premium (chip numerado + titulo) ---- */
.eh-sec{ display:flex; align-items:center; gap:13px; margin:30px 0 16px; }
.eh-sec-num{ width:34px; height:34px; border-radius:11px; flex:0 0 auto;
  display:flex; align-items:center; justify-content:center; color:#fff;
  font-weight:800; font-size:15px; font-variant-numeric:tabular-nums;
  background:linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
  box-shadow:0 6px 16px rgba(20,80,45,.30); }
.eh-sec-title{ font-size:22px; font-weight:800; color:var(--brand-dark); letter-spacing:-.4px; line-height:1.1; }

/* ---- alertas refinadas ---- */
div[data-testid="stAlert"]{ border-radius:15px !important; border:1px solid var(--line);
  box-shadow:var(--shadow-sm); }
div[data-testid="stAlert"] p{ font-size:.93rem; }

.eh-card{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:16px; box-shadow:var(--shadow); }

hr{ border:none; border-top:1px solid var(--line); margin:.5rem 0; }
:focus-visible{ outline:2px solid var(--brand); outline-offset:2px; }

/* ---- densidad / aire premium ---- */
[data-testid="stVerticalBlock"]{ gap:.65rem; }
[data-testid="stElementContainer"]{ margin-bottom:0; }

/* ---- CTA final de confirmar = naranja acento ---- */
.st-key-portal_guardar button, .st-key-portal_guardar button[kind="primary"]{
  background:var(--accent) !important; border-color:var(--accent) !important; color:#fff !important;
  box-shadow:0 6px 18px rgba(198,106,46,.32) !important; font-weight:800 !important; min-height:52px !important;
  font-size:1.05rem !important;
}
.st-key-portal_guardar button:hover{
  background:var(--accent-dark) !important; border-color:var(--accent-dark) !important;
  box-shadow:0 12px 28px rgba(198,106,46,.42) !important;
}

/* ---- movil ---- */
@media (max-width:768px){
  .block-container{ padding-left:.85rem; padding-right:.85rem; }
  .stNumberInput button{ min-width:46px; min-height:46px; font-size:1.2rem; }
  .stButton>button, .stDownloadButton>button{ padding:.75rem 1rem; }
  .eh-sec-title{ font-size:20px; }
}
</style>
"""


def aplicar():
    """Inyecta el tema. Llamar una vez al inicio de cada página."""
    import streamlit as st
    st.markdown(THEME_CSS, unsafe_allow_html=True)
