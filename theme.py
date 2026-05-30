"""
Export Haret · Sistema de diseño (tema visual central)
======================================================
Una sola fuente para el aspecto de la app: paleta premium sobria (verde de marca
+ acento naranja cálido y discreto), tipografía limpia, botones dinámicos y
componentes coherentes. Se inyecta una vez por página con `aplicar()`.
"""

THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root{
  --brand:#1B7A3C;        /* verde marca */
  --brand-700:#176836;    /* hover */
  --brand-dark:#0F4F29;   /* titulos / degradado */
  --brand-soft:#EAF3EC;   /* fondo verde suave */
  --accent:#CE7A32;       /* naranja calido, discreto */
  --accent-dark:#B5641F;
  --ink:#1B2620;          /* texto */
  --muted:#5F6F65;        /* texto secundario */
  --line:#E5ECE7;         /* bordes */
  --bg:#F6F9F7;           /* fondo app */
  --card:#FFFFFF;
  --radius:14px;
  --shadow:0 1px 2px rgba(20,60,40,.04), 0 8px 24px rgba(20,60,40,.06);
}

/* ---- tipografia y fondo ---- */
html, body, [class*="css"], .stApp, button, input, textarea, select{
  font-family:'Inter',-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
.stApp{ background:var(--bg); color:var(--ink); }
.block-container{ max-width:780px; padding-top:1.1rem; }
h1,h2,h3,h4{ color:var(--brand-dark); letter-spacing:-.2px; font-weight:700; }
a{ color:var(--brand); text-decoration:none; }
a:hover{ text-decoration:underline; }

/* ---- botones dinamicos ---- */
.stButton>button, .stDownloadButton>button, .stLinkButton>a, .stFormSubmitButton>button{
  border-radius:var(--radius); font-weight:600; padding:.62rem 1.05rem;
  border:1px solid var(--line); background:#fff; color:var(--ink);
  transition:transform .12s ease, box-shadow .2s ease, background .2s ease, border-color .2s ease, color .2s ease;
}
.stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover, .stFormSubmitButton>button:hover{
  transform:translateY(-1px); box-shadow:0 7px 18px rgba(20,60,40,.12); border-color:#cfe0d4;
}
.stButton>button:active, .stDownloadButton>button:active, .stFormSubmitButton>button:active{
  transform:translateY(0); box-shadow:0 2px 6px rgba(20,60,40,.10);
}
/* primario = verde marca (incluye botones de formulario: kind="primaryFormSubmit") */
.stButton>button[kind="primary"], .stDownloadButton>button,
.stFormSubmitButton>button[kind="primary"], .stFormSubmitButton>button[kind="primaryFormSubmit"]{
  background:var(--brand); border-color:var(--brand); color:#fff;
  box-shadow:0 2px 8px rgba(20,80,45,.20);
}
.stButton>button[kind="primary"]:hover, .stDownloadButton>button:hover,
.stFormSubmitButton>button[kind="primary"]:hover, .stFormSubmitButton>button[kind="primaryFormSubmit"]:hover{
  background:var(--brand-700); border-color:var(--brand-700);
  box-shadow:0 10px 22px rgba(20,80,45,.28);
}
/* secundario = contorno verde */
.stButton>button[kind="secondary"], .stFormSubmitButton>button[kind="secondaryFormSubmit"]{
  background:#fff; color:var(--brand); border-color:#cfe0d4; }
.stButton>button[kind="secondary"]:hover,
.stFormSubmitButton>button[kind="secondaryFormSubmit"]:hover{
  background:var(--brand-soft); border-color:var(--brand); }
/* link buttons */
.stLinkButton>a{ background:var(--brand-soft); color:var(--brand-dark); border-color:#cfe0d4; }
.stLinkButton>a:hover{ background:#dfeede; text-decoration:none; }

/* ---- inputs ---- */
.stTextInput input, .stNumberInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"]>div, .stMultiSelect div[data-baseweb="select"]>div{
  border-radius:12px !important; border-color:var(--line) !important; background:#fff !important;
}
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus{
  border-color:var(--brand) !important; box-shadow:0 0 0 3px rgba(27,122,60,.14) !important;
}
.stNumberInput button{ border-radius:10px; transition:background .15s ease; }
.stNumberInput button:hover{ background:var(--brand-soft); }

/* ---- tabs ---- */
.stTabs [data-baseweb="tab-list"]{ gap:6px; border-bottom:1px solid var(--line); }
.stTabs [data-baseweb="tab"]{ border-radius:10px 10px 0 0; font-weight:600; color:var(--muted); }
.stTabs [aria-selected="true"]{ color:var(--brand) !important; }
.stTabs [data-baseweb="tab-highlight"]{ background:var(--brand) !important; }

/* ---- metricas / expanders / alerts ---- */
[data-testid="stMetricValue"]{ color:var(--brand-dark); font-weight:700; }
.streamlit-expanderHeader, details summary{ font-weight:600; }
[data-testid="stExpander"]{ border-radius:var(--radius); border-color:var(--line); }

/* ---- dataframes ---- */
[data-testid="stDataFrame"]{ border-radius:12px; overflow:hidden; }

/* ---- acento sutil (no chillon) ---- */
.eh-accent{ color:var(--accent) !important; }

/* ---- cabecera de seccion premium (chip numerado + titulo) ---- */
.eh-sec{ display:flex; align-items:center; gap:12px; margin:26px 0 14px; }
.eh-sec-num{ width:32px; height:32px; border-radius:10px; flex:0 0 auto;
  display:flex; align-items:center; justify-content:center; color:#fff;
  font-weight:700; font-size:15px; font-variant-numeric:tabular-nums;
  background:linear-gradient(135deg, var(--brand) 0%, var(--brand-dark) 100%);
  box-shadow:0 5px 14px rgba(20,80,45,.28); }
.eh-sec-title{ font-size:21px; font-weight:700; color:var(--brand-dark); letter-spacing:-.3px; line-height:1.1; }

/* ---- alertas refinadas (sin azul chillon) ---- */
div[data-testid="stAlert"]{ border-radius:14px !important; border:1px solid var(--line);
  box-shadow:var(--shadow); }
div[data-testid="stAlert"] p{ font-size:.92rem; }

/* ---- tarjeta generica de marca (uso opcional) ---- */
.eh-card{ background:var(--card); border:1px solid var(--line); border-radius:var(--radius);
  padding:16px; box-shadow:var(--shadow); }

/* ---- separadores + foco accesible ---- */
hr{ border:none; border-top:1px solid var(--line); margin:.5rem 0; }
:focus-visible{ outline:2px solid var(--brand); outline-offset:2px; }

/* ---- densidad premium (espaciado mas apretado) ---- */
[data-testid="stVerticalBlock"]{ gap:.6rem; }
[data-testid="stElementContainer"]{ margin-bottom:0; }

/* ---- CTA final de confirmar = naranja acento (destaca como accion principal) ---- */
.st-key-portal_guardar button, .st-key-portal_guardar button[kind="primary"]{
  background:var(--accent) !important; border-color:var(--accent) !important; color:#fff !important;
  box-shadow:0 4px 14px rgba(206,122,50,.30) !important; font-weight:700 !important;
}
.st-key-portal_guardar button:hover{
  background:var(--accent-dark) !important; border-color:var(--accent-dark) !important;
  box-shadow:0 10px 24px rgba(206,122,50,.40) !important;
}

/* ---- movil ---- */
@media (max-width:768px){
  .block-container{ padding-left:.8rem; padding-right:.8rem; }
  .stNumberInput button{ min-width:44px; min-height:44px; font-size:1.15rem; }
  .stButton>button, .stDownloadButton>button{ padding:.7rem 1rem; }
}
</style>
"""


def aplicar():
    """Inyecta el tema. Llamar una vez al inicio de cada página."""
    import streamlit as st
    st.markdown(THEME_CSS, unsafe_allow_html=True)
