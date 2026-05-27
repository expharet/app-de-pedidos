import streamlit as st
import pandas as pd
import json
import os
import io
import hashlib
import uuid
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
from PIL import Image
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ─── PAGE CONFIG ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Export Haret - Sistema de Pedidos",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ─── CONSTANTES ───────────────────────────────────────────────────────────────
ORDEN_ESTADOS = ["Recibido","Confirmado","Preparando","Enviado","Entregado","Cancelado"]
ESTADO_ICONS = {"Recibido":"📤","Confirmado":"✅","Preparando":"📦","Enviado":"🚚","Entregado":"✨","Cancelado":"❌"}

# Tramos de descuento por volumen (pallets)
TRAMOS_VOLUMEN = [
    {"min": 1,  "max": 2,  "descuento": 0.00, "label": "1-2 Pallets"},
    {"min": 3,  "max": 5,  "descuento": 0.05, "label": "3-5 Pallets (-5%)"},
    {"min": 6,  "max": 9,  "descuento": 0.10, "label": "6-9 Pallets (-10%)"},
    {"min": 10, "max": 19, "descuento": 0.12, "label": "10-19 Pallets (-12%)"},
    {"min": 20, "max": 9999, "descuento": 0.15, "label": "20+ Pallets (-15%)"},
]

MONEDAS = ["USD", "EUR", "GBP", "CHF", "AED", "CAD", "MXN", "BRL", "COP"]
MONEDA_SIMBOLO = {"USD": "$", "EUR": "€", "GBP": "£", "CHF": "Fr", "AED": "د.إ", "CAD": "CA$", "MXN": "MX$", "BRL": "R$", "COP": "COP$"}
# -- IDIOMA / LANGUAGE TRANSLATIONS --
LANG_TEXTS = {
    'es': {
        'step1': '### 1️⃣ Tus Datos',
        'step2': '### 2️⃣ Tipo de Precio y Destino',
        'step3': '### 3️⃣ Selecciona tus Productos',
        'step4': '### 4️⃣ Confirmar Pedido',
        'email_label': '📧 Tu correo electrónico',
        'email_ph': 'tu@empresa.com',
        'no_catalog': '⚠️ Catálogo no disponible. Contacte a order@exportharet.com',
        'enter_email': '📧 **Ingresa tu correo electrónico arriba para continuar**',
        'welcome_back': '✅ Bienvenido de vuelta, **{name}**!',
        'not_registered': '📝 Correo no registrado — completa tus datos para continuar.',
        'nombre_label': '👤 Nombre completo *',
        'empresa_label': '🏢 Empresa',
        'telefono_label': '📱 Teléfono / WhatsApp',
        'telefono_ph': '+34 600 000 000',
        'pais_label': '🌍 País',
        'auto_register': '🔒 Al guardar el pedido, tu cuenta quedará registrada automáticamente.',
        'tab_datos': '👤 Mis Datos',
        'tab_pedidos': '📦 Mis Pedidos ({n})',
        'no_orders': '📦 Aún no tienes pedidos. ¡Haz tu primer pedido a continuación!',
        'price_type_label': '💲 Tipo de precio',
        'price_type_help': 'FOB = Precio en origen (sin flete). CIF = Precio incluye flete al destino.',
        'dest_label': '🌍 Destino',
        'no_dest': '⚠️ No hay destinos configurados',
        'flete_caption': '🛫 Flete incluido: **${flete:.2f} USD/caja** | {orig} → {dest}',
        'cif_info': '📍 **Incoterm CIF** — Precio incluye costo + flete hasta **{dest}**. Embarcamos desde **{orig}**.',
        'fob_info': '📦 **FOB (Free On Board)** — El precio **no incluye flete**. Tú coordinas el transporte desde Ecuador.',
        'fob_origin': '📌 Origen de embarque: **Quito o Guayaquil, Ecuador**',
        'min_order_empty': '📋 **Pedido mínimo: 3 pallets** — Añade productos para comenzar tu pedido',
        'min_order_short': '📋 **Pedido mínimo: 3 pallets** — Tienes {plt:.1f} plt. Añade más productos.',
        'cart_fob': '📦 Precios FOB — El flete corre por tu cuenta desde Quito/Guayaquil, Ecuador',
        'clear_cart': '🗑️ Vaciar carrito',
        'notes_label': '📝 Notas / instrucciones especiales',
        'notes_ph': 'Ej: Entrega en almén frigorífico, embalaje especial...',
        'payment_terms': '📋 Términos de pago (opcional)',
        'confirm_btn': '📤 CONFIRMAR Y ENVIAR PEDIDO',
        'err_email': '❌ Ingresa tu correo electrónico',
        'err_nombre': '❌ Ingresa tu nombre completo',
        'err_cart': '❌ Agrega al menos un producto al carrito',
        'err_destino': '❌ Selecciona un destino para precio CIF',
        'order_confirmed': '✅ **Pedido {pid} confirmado y enviado**',
        'order_email_sent': '📧 Recibirás confirmación en **{email}** en 24-48h.',
        'download_pdf': '⬇️ Descargar Albarán PDF',
        'new_order_btn': '🔄 Nuevo Pedido',
        'quote_expander': '💬 Solicitar cotización especial',
        'quote_intro': '**¿Necesitas presupuesto personalizado?** Rellena el formulario y te contactamos en 24h.',
        'quote_name_lbl': 'Tu nombre / empresa',
        'quote_name_ph': 'Nombre o empresa',
        'quote_msg_lbl': 'Mensaje adicional',
        'quote_msg_ph': 'Condiciones especiales...',
        'send_quote': '📤 Enviar solicitud',
    },
    'en': {
        'step1': '### 1️⃣ Your Details',
        'step2': '### 2️⃣ Price Type & Destination',
        'step3': '### 3️⃣ Select your Products',
        'step4': '### 4️⃣ Confirm Order',
        'email_label': '📧 Your email address',
        'email_ph': 'you@company.com',
        'no_catalog': '⚠️ Catalogue not available. Contact order@exportharet.com',
        'enter_email': '📧 **Enter your email address above to continue**',
        'welcome_back': '✅ Welcome back, **{name}**!',
        'not_registered': '📝 Email not registered — please complete your details to continue.',
        'nombre_label': '👤 Full name *',
        'empresa_label': '🏢 Company',
        'telefono_label': '📱 Phone / WhatsApp',
        'telefono_ph': '+1 000 000 0000',
        'pais_label': '🌍 Country',
        'auto_register': '🔒 By placing your order, your account will be registered automatically.',
        'tab_datos': '👤 My Details',
        'tab_pedidos': '📦 My Orders ({n})',
        'no_orders': '📦 No orders yet. Place your first order below!',
        'price_type_label': '💲 Price type',
        'price_type_help': 'FOB = Ex-works price (no freight). CIF = Price includes freight to destination.',
        'dest_label': '🌍 Destination',
        'no_dest': '⚠️ No destinations configured',
        'flete_caption': '🛫 Freight included: **${flete:.2f} USD/box** | {orig} → {dest}',
        'cif_info': '📍 **Incoterm CIF** — Price includes cost + freight to **{dest}**. We ship from **{orig}**.',
        'fob_info': '📦 **FOB (Free On Board)** — Price **does not include freight**. You arrange transport from Ecuador.',
        'fob_origin': '📌 Port of origin: **Quito or Guayaquil, Ecuador**',
        'min_order_empty': '📋 **Minimum order: 3 pallets** — Add products to start your order',
        'min_order_short': '📋 **Minimum order: 3 pallets** — You have {plt:.1f} plt. Add more products.',
        'cart_fob': '📦 FOB prices — Freight is your responsibility from Quito/Guayaquil, Ecuador',
        'clear_cart': '🗑️ Clear cart',
        'notes_label': '📝 Notes / special instructions',
        'notes_ph': 'e.g. Delivery to cold storage, special packaging...',
        'payment_terms': '📋 Payment terms (optional)',
        'confirm_btn': '📤 CONFIRM AND SEND ORDER',
        'err_email': '❌ Please enter your email address',
        'err_nombre': '❌ Please enter your full name',
        'err_cart': '❌ Please add at least one product to your cart',
        'err_destino': '❌ Please select a destination for CIF pricing',
        'order_confirmed': '✅ **Order {pid} confirmed and sent**',
        'order_email_sent': '📧 Confirmation will be sent to **{email}** within 24-48h.',
        'download_pdf': '⬇️ Download Order PDF',
        'new_order_btn': '🔄 New Order',
        'quote_expander': '💬 Request special quote',
        'quote_intro': '**Need a custom quote?** Fill in the form and we will contact you within 24h.',
        'quote_name_lbl': 'Your name / company',
        'quote_name_ph': 'Your name or company',
        'quote_msg_lbl': 'Additional message',
        'quote_msg_ph': 'Special conditions...',
        'send_quote': '📤 Send request',
    }
}

# ── CSS personalizado y responsive ───────────────────────────────────────────
CUSTOM_CSS = """
<style>
/* === RESPONSIVE MÓVIL === */
@media (max-width: 768px) {
    .stApp { font-size: 14px !important; }
    div[data-testid="column"] { min-width: 0 !important; }
    .stNumberInput input { font-size: 16px !important; }
    .stSelectbox select { font-size: 16px !important; }
    .product-row { flex-wrap: wrap !important; }
}
/* === MINI CARRITO FLOTANTE === */
.cart-badge {
    background: #003E8C;
    color: white;
    border-radius: 12px;
    padding: 2px 10px;
    font-weight: bold;
    font-size: 0.85em;
}
/* === PROGRESS BAR MÍNIMO === */
.min-progress {
    height: 8px;
    background: #e0e0e0;
    border-radius: 4px;
    margin: 4px 0 8px 0;
}
.min-progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #f97316, #003E8C);
    border-radius: 4px;
    transition: width 0.3s ease;
}
/* === BOTONES === */
.stButton > button[kind="primary"] { background: #003E8C !important; border-color: #003E8C !important; }
.stButton > button[kind="primary"]:hover { background: #002d6b !important; }
/* === RESUMEN PEDIDO === */
.order-summary-box {
    background: #f8faff;
    border: 1.5px solid #003E8C;
    border-radius: 10px;
    padding: 16px;
    margin: 12px 0;
}
/* === PRODUCT ROW === */
.product-header { font-weight: 600; color: #555; font-size: 0.8em; border-bottom: 1px solid #eee; padding-bottom: 4px; margin-bottom: 4px; }
/* === LANG BUTTONS === */
div[data-testid="column"]:has(> div > div > button[title="Español"]),
div[data-testid="column"]:has(> div > div > button[title="English"]) {
    padding: 0 2px !important;
}
</style>
"""

PEDIDOS_FILE = "pedidos_data.json"
CLIENTS_FILE = "clientes.json"
HIST_FILE    = "precio_historial.json"
EMAIL_FILE   = "email_log.json"
DATA_FILE    = "precios_data.json"
APP_CONFIG_FILE = "app_config.json"

USERS = {
    "admin@exportharet.com":  {"pwd": hashlib.md5(b"admin123").hexdigest(),  "rol": "admin",  "nombre": "Administrador"},
    "ventas@exportharet.com": {"pwd": hashlib.md5(b"ventas123").hexdigest(), "rol": "ventas", "nombre": "Ventas"},
}

# ─── DATA HELPERS ───────────────────────────────────────────────────
def _load(path, default):
    try:
        if os.path.exists(path):
            with open(path,'r',encoding='utf-8') as f: return json.load(f)
    except: pass
    return default

def _save(path, data):
    try:
        with open(path,'w',encoding='utf-8') as f: json.dump(data,f,indent=2,ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f'Error guardando: {e}'); return False

@st.cache_data(ttl=60)
def load_data():
    return _load(DATA_FILE, {'products':[],'config':{'destinos':{},'grupos':{},'minimos':{}},'pedidos':[]})

def load_clients(): return _load(CLIENTS_FILE, {})
def load_pedidos(): return _load(PEDIDOS_FILE, [])
def load_historial(): return _load(HIST_FILE, [])
def load_email_log(): return _load(EMAIL_FILE, [])
def load_app_config():
    return _load(APP_CONFIG_FILE, {"app_title": "🚀 EXPORT HARET — Panel de Administración"})
def save_app_config(cfg): _save(APP_CONFIG_FILE, cfg)
def save_data(d): _save(DATA_FILE,d); st.cache_data.clear()
def save_clients(c): _save(CLIENTS_FILE,c)
def save_pedidos(p): _save(PEDIDOS_FILE,p)
def save_historial(h2): _save(HIST_FILE,h2)
def save_email_log(e): _save(EMAIL_FILE,e)

# ─── AUTH ────────────────────────────────────────────────────────────────
def init_session():
    defaults = {'logged_in':False,'user_email':'','user_rol':'','user_nombre':'','carrito':[]}
    for k,v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def login_page():
    st.markdown('<div style="text-align:center;padding:40px 0 20px"><h1>🚀 Export Haret</h1><h3 style="color:#666">Sistema de Gestión de Pedidos</h3></div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns([1,1.2,1])
    with c2:
        st.markdown('### 🔐 Iniciar Sesión')
        email = st.text_input('Email', placeholder='usuario@exportharet.com')
        pwd = st.text_input('Contraseña', type='password')
        if st.button('Entrar →', use_container_width=True, type='primary'):
            h = hashlib.md5(pwd.encode()).hexdigest()
            if email in USERS and USERS[email]['pwd'] == h:
                st.session_state.logged_in = True
                st.session_state.user_email = email
                st.session_state.user_rol = USERS[email]['rol']
                st.session_state.user_nombre = USERS[email]['nombre']
                st.rerun()
            else: st.error('❌ Email o contraseña incorrectos')
        st.markdown('---')
    st.caption('🔒 Acceso restringido al personal autorizado.')
    # credentials hidden for security

# ─── BUSINESS LOGIC ──────────────────────────────────────────────────────
def segmentar(email, clients):
    peds = [p for p in load_pedidos() if p.get('client_email') == email]
    if not peds: return {'segmento':'Nuevo','descuento':0.0,'credito':10000,'badge':'🆕 Nuevo'}
    hoy = datetime.now()
    p30 = [p for p in peds if (hoy-datetime.fromisoformat(p.get('fecha',hoy.isoformat()))).days<=30]
    fac = sum(p.get('total_usd',0) for p in p30)
    if fac>=5000 or len(p30)>=10: return {'segmento':'VIP','descuento':0.05,'credito':50000,'badge':'⭐ VIP'}
    if len(peds)>=2: return {'segmento':'Regular','descuento':0.02,'credito':25000,'badge':'⚫ Regular'}
    return {'segmento':'Nuevo','descuento':0.0,'credito':10000,'badge':'🆕 Nuevo'}

def get_precio(codigo, destino, data):
    """Calcula precio CIF = precio_compra + flete_destino."""
    for p in data.get('products', []):
        if p.get('codigo') == codigo:
            # Support both old key names
            base = p.get('precio_cif_usd', 0) or p.get('precio_compra', 0)
            dest_val = data.get('config', {}).get('destinos', {}).get(destino, 0)
            if isinstance(dest_val, dict):
                # New format: {'moneda': 'USD', 'factor': 2.35} — factor = flete USD/caja
                flete = dest_val.get('factor', 0.0)
            elif isinstance(dest_val, (int, float)):
                # Original format: flete en USD/caja directamente
                flete = float(dest_val)
            else:
                flete = 0.0
            return round(base + flete, 2)
    return 0.0

def reg_cambio_precio(cod, antes, desp, motivo='Manual'):
    if antes==desp: return
    pct = ((desp-antes)/antes*100) if antes>0 else 0
    h2 = load_historial()
    h2.append({'id':f'CHG-{len(h2)+1:05d}','fecha':datetime.now().isoformat(),'producto':cod,'antes':antes,'despues':desp,'cambio_pct':round(pct,2),'usuario':st.session_state.get('user_email','sistema'),'motivo':motivo})
    save_historial(h2)
    if abs(pct)>20: st.warning(f'⚠️ Cambio >20% en {cod}: {pct:+.1f}%')

def exportar_excel(pedidos):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except: st.error('Instalar openpyxl'); return None
    wb = Workbook()
    ws1 = wb.active; ws1.title='Resumen'
    ws1['A1'] = 'EXPORT HARET - REPORTE'; ws1['A1'].font=Font(bold=True,color='FFFFFF'); ws1['A1'].fill=PatternFill(start_color='003E8C',end_color='003E8C',fill_type='solid')
    estados={}
    for p in pedidos:
        e=p.get('estado','Recibido'); estados[e]=estados.get(e,{'c':0,'t':0}); estados[e]['c']+=1; estados[e]['t']+=p.get('total_usd',0)
    ws1.append(['ESTADO','PEDIDOS','TOTAL USD'])
    for e,d in sorted(estados.items()): ws1.append([e,d['c'],round(d['t'],2)])
    ws2=wb.create_sheet('Pedidos')
    ws2.append(['ID','CLIENTE','EMAIL','ESTADO','DESTINO','TOTAL USD','FECHA'])
    for cell in ws2[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill(start_color='003E8C',end_color='003E8C',fill_type='solid')
    for p in sorted(pedidos,key=lambda x:x.get('fecha',''),reverse=True):
        ws2.append([p.get('id','').upper(),p.get('client_name',''),p.get('client_email',''),p.get('estado',''),p.get('destino',''),round(p.get('total_usd',0),2),p.get('fecha','')[:10]])
    ws3=wb.create_sheet('Productos')
    ws3.append(['CODIGO','PRODUCTO','CAJAS','PALLETS','PRECIO','TOTAL'])
    for cell in ws3[1]: cell.font=Font(bold=True,color='FFFFFF'); cell.fill=PatternFill(start_color='003E8C',end_color='003E8C',fill_type='solid')
    for p in pedidos:
        for pr in p.get('productos',[]): ws3.append([pr.get('codigo',''),pr.get('producto',''),pr.get('cajas',0),round(pr.get('pallets',0),2),round(pr.get('precio_usd',0),2),round(pr.get('cajas',0)*pr.get('precio_usd',0),2)])
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return out.getvalue()

def calc_sla(pedidos):
    metas={'Recibido_Confirmado':4,'Confirmado_Preparando':2,'Preparando_Enviado':48,'Enviado_Entregado':168}
    slas=[]
    for p in pedidos:
        hist=sorted(p.get('historial_estados',[]),key=lambda x:x.get('fecha',''))
        for i in range(len(hist)-1):
            try:
                de=hist[i].get('estado',''); a=hist[i+1].get('estado','')
                t1=datetime.fromisoformat(hist[i]['fecha']); t2=datetime.fromisoformat(hist[i+1]['fecha'])
                h2=(t2-t1).total_seconds()/3600
                meta=metas.get(f'{de}_{a}')
                if meta: slas.append({'p':p.get('id',''),'tr':f'{de}→{a}','h':round(h2,1),'m':meta,'ok':h2<=meta})
            except: pass
    tot=len(slas) or 1
    ok=sum(1 for s in slas if s['ok'])
    return slas,{'pct':round(ok/tot*100,1),'crit':tot-ok,'tot':len(slas),'prom':round(sum(s['h'] for s in slas)/tot,1)}

# ─── TAB DASHBOARD ─────────────────────────────────────────────
def render_dashboard():
    import os as _os
    if _os.path.exists('logo.png'):
        from PIL import Image as _Img
        _logo = _Img.open('logo.png')
        _lc1, _lc2, _lc3 = st.columns([1, 2, 1])
        with _lc2: st.image(_logo, width=220)
    st.markdown('## 📊 Dashboard Ejecutivo')
    pedidos=load_pedidos(); clients=load_clients(); data=load_data()
    c1,c2,c3,c4=st.columns(4)
    fac=sum(p.get('total_usd',0) for p in pedidos)
    vip=sum(1 for e in clients if segmentar(e,clients)['segmento']=='VIP')
    hoy_peds=len([p for p in pedidos if p.get('fecha','')[:10]==str(date.today())])
    c1.metric('📦 Pedidos',f'{len(pedidos):,}')
    c2.metric('💵 Facturación',f'${fac:,.0f}','USD')
    c3.metric('👥 Clientes',f'{len(clients):,}',f'{vip} VIP')
    c4.metric('📬 Hoy',hoy_peds,'nuevos')
    st.markdown('---')
    st.markdown('### 📋 Pedidos por Estado')
    ec={}
    for p in pedidos: ec[p.get('estado','Recibido')]=ec.get(p.get('estado','Recibido'),0)+1
    if ec:
        cols=st.columns(len(ORDEN_ESTADOS))
        for i,e in enumerate(ORDEN_ESTADOS): cols[i].metric(f"{ESTADO_ICONS.get(e,'')} {e}",ec.get(e,0))
    else: st.info('ℹ️ No hay pedidos. Crea uno en el tab **Hacer Pedido**.')
    st.markdown('---')
    st.markdown('### 📈 Facturación Mensual (USD)')
    if pedidos:
        _mes_data = {}
        for _p in pedidos:
            _fe = _p.get('fecha','')[:7]
            if _fe: _mes_data[_fe] = _mes_data.get(_fe, 0) + _p.get('total_usd', 0)
        if _mes_data:
            _meses_sorted = sorted(_mes_data.keys())[-12:]
            _df_chart = pd.DataFrame({'Mes': _meses_sorted, 'Total USD': [round(_mes_data[m], 2) for m in _meses_sorted]}).set_index('Mes')
            st.bar_chart(_df_chart, use_container_width=True, height=250)
    else: st.info('📊 Gráfico disponible cuando haya pedidos.')
    st.markdown('---')
    with st.expander('⏱ SLA de Procesos', expanded=False):
        _,ss=calc_sla(pedidos)
        s1,s2,s3,s4=st.columns(4)
        s1.metric('✅ Cumplimiento',f"{ss['pct']:.1f}%",'Meta:95%')
        s2.metric('⚠️ Críticos',ss['crit'])
        s3.metric('⏱ Prom.h',f"{ss['prom']:.1f}h")
        s4.metric('📊 Trans.',ss['tot'])
    st.markdown('---')
    st.markdown('---')
    # —— Alertas pedidos nuevos ——
    _nuevos = [p for p in pedidos if p.get('estado','') == 'Recibido']
    if _nuevos:
        st.markdown(f'### 🔔 Pedidos Nuevos Sin Atender ({len(_nuevos)})')
        _col_alerta = 'background:#fff3cd;border-left:4px solid #ffc107;border-radius:6px;padding:10px 14px;margin:4px 0'
        for _np in sorted(_nuevos, key=lambda x: x.get('fecha',''), reverse=True)[:5]:
            _np_id = _np.get('id','').upper()
            _np_cliente = _np.get('client_name','')
            _np_total = _np.get('total_usd',0)
            _np_fecha = _np.get('fecha','')[:16].replace('T',' ')
            _np_dest = _np.get('destino','')
            st.markdown(f'<div style="{_col_alerta}">📦 <b>{_np_id}</b> — {_np_cliente} — <b>${_np_total:,.2f} USD</b> — {_np_dest} — <small style="color:#888">{_np_fecha}</small></div>', unsafe_allow_html=True)
        if len(_nuevos) > 5:
            st.caption(f'... y {len(_nuevos)-5} pedido(s) más en el tab 📦 Pedidos')
    st.markdown('---')
    st.markdown('### ⭐ Segmentación')
    segs={'VIP':0,'Regular':0,'Nuevo':0}
    for e in clients: seg=segmentar(e,clients)['segmento']; segs[seg]=segs.get(seg,0)+1
    sg1,sg2,sg3=st.columns(3)
    sg1.metric('⭐ VIP',segs.get('VIP',0),'+5% desc.')
    sg2.metric('⚫ Regular',segs.get('Regular',0),'+2% desc.')
    sg3.metric('🆕 Nuevo',segs.get('Nuevo',0))
    if data.get('products',[]):
        st.markdown('---')
        st.markdown(f"### 📦 Productos ({len(data['products'])} activos)")
        _df_prods = pd.DataFrame([{'Código':p.get('codigo',''),'Producto':p.get('descripcion','') or p.get('producto',''),'Precio Compra':f"${p.get('precio_compra',0):.4f}",'Margen':f"{float(p.get('margen_pct',0.1) or 0.1)*100:.0f}%",'Activo':'✅' if p.get('activo',True) else '❌'} for p in data['products'][:15]])
        st.dataframe(_df_prods,use_container_width=True,hide_index=True)

# ─── TAB COTIZACION ───────────────────────────────────────────────────

# ── Mapa columnas Excel → código producto (igual que vigilar_excel.py) ──────
COL_MAP = {
     4: "F-PSG10",    5: "F-PN016",    6: "F-PPA01",
     7: "F-PSR02",    8: "F-PSR05",    9: "F-PSM09",
    10: "F-TAS04",   11: "F-GNB010",  12: "F-MPS03",
    13: "F-CCN017",  14: "F-BCC013",  15: "F-AHSS012",
    16: "F-BBB06",   17: "F-ZPT020",  18: "F-TX020",
    19: "F-UVP08",   20: "F-UVP07",
}

def parse_excel_file(xl_path):
    """
    Parsea Cotizaciones.xlsx usando openpyxl (igual que vigilar_excel.py).
    Lee precios de la hoja TABLA PRECIOS (columnas 4-20, filas 32-83)
    y destinos/config de la hoja CONFIGURACION.
    Devuelve (products_updated, destinos_cfg) o raises exception.
    """
    from openpyxl import load_workbook
    import io as _io

    # Leer archivo
    if isinstance(xl_path, str):
        with open(xl_path, 'rb') as f:
            wb_bytes = f.read()
    else:
        wb_bytes = xl_path.getvalue()

    wb = load_workbook(_io.BytesIO(wb_bytes), data_only=True)

    # Cargar datos existentes para mantener metadata de productos
    data = load_data()
    products_existing = {p['codigo']: p for p in data.get('products', [])}

    # ── Leer precios de TABLA PRECIOS ────────────────────────────
    if 'TABLA PRECIOS' not in wb.sheetnames:
        raise ValueError("No se encontró la hoja 'TABLA PRECIOS'")
    ws_pr = wb['TABLA PRECIOS']

    # Para cada producto, tomar el último valor numérico > 0 en filas 32-83
    latest_prices = {}
    for col, cod in COL_MAP.items():
        last = None
        for r in range(32, 84):
            v = ws_pr.cell(row=r, column=col).value
            if isinstance(v, (int, float)) and v > 0:
                last = float(v)
        if last is not None:
            latest_prices[cod] = last

    # Construir lista de productos
    products = []
    for col, cod in sorted(COL_MAP.items()):
        precio = latest_prices.get(cod, 0.0)
        existing = products_existing.get(cod, {})
        # Preserve all existing product metadata, only update price
        prod_data = dict(existing) if existing else {}
        prod_data.update({
            'codigo': cod,
            'descripcion': existing.get('descripcion', '') or existing.get('producto', ''),
            'precio_cif_usd': precio,
            'precio_compra': precio,
        })
        if 'cajas_pallet' not in prod_data:
            prod_data['cajas_pallet'] = 200
        products.append(prod_data)

    # ── Leer destinos y config de CONFIGURACION ──────────────────
    destinos_cfg = {}
    config_existing = data.get('config', {})
    if 'CONFIGURACION' in wb.sheetnames:
        ws_cfg = wb['CONFIGURACION']
        for row in ws_cfg.iter_rows():
            for cell in row:
                v = str(cell.value or '')
                dest = str(ws_cfg.cell(row=cell.row, column=2).value or '')
                c3 = ws_cfg.cell(row=cell.row, column=3).value
                if cell.column == 2 and dest and isinstance(c3, (int, float)) and c3 > 0:
                    if dest in config_existing.get('destinos', {}):
                        destinos_cfg[dest] = float(c3)
        # Si no se leyeron destinos del Excel, mantener los existentes
        if not destinos_cfg:
            destinos_cfg = config_existing.get('destinos', {})
    else:
        destinos_cfg = config_existing.get('destinos', {})

    return products, destinos_cfg

def auto_load_excel():
    """Auto-carga Cotizaciones.xlsx al inicio si los productos no tienen precios válidos."""
    data = load_data()
    prods = data.get('products', [])
    # Re-parsear si no hay productos con precio_cif_usd válido
    has_prices = any(
        (p.get('precio_cif_usd', 0) or p.get('precio_compra', 0)) > 0
        for p in prods
    )
    if has_prices:
        return  # ya hay precios válidos
    xl_path = 'Cotizaciones.xlsx'
    if not os.path.exists(xl_path):
        return  # esperar upload manual
    try:
        products, destinos_cfg = parse_excel_file(xl_path)
        if products and any(p.get('precio_cif_usd', 0) > 0 for p in products):
            nueva = data.copy()
            nueva['products'] = products
            nueva['config'] = data.get('config', {})
            nueva['config']['destinos'] = destinos_cfg
            save_data(nueva)
    except Exception:
        pass  # ignorar errores de auto-carga

def render_catalogo():
    """Tab unificado: Tabla de precios tipo Excel + Destinos + Importar."""
    st.markdown("## 📊 Catálogo, Precios & Destinos")
    data = load_data()
    prods = data.get('products', [])
    cfg   = data.get('config', {})
    dests = cfg.get('destinos', {})
    dests_moneda = cfg.get('destinos_moneda', {})

    sub1, sub2, sub3 = st.tabs(['📈 Tabla de Precios', '🌍 Destinos & Monedas', '📂 Importar Excel'])

    # SUB-TAB 1: TABLA DE PRECIOS
    with sub1:
        st.markdown("### 📋 Tabla Maestra de Precios")
        prods_activos = [p for p in prods if p.get('activo', True)]
        dest_list     = list(dests.keys())
        if not prods_activos:
            st.info("No hay productos activos.")
            return
        if not dest_list:
            st.info("No hay destinos configurados. Agrega destinos primero.")
            return

        col_dest, col_pal, col_cur = st.columns([2, 2, 1.5])
        with col_dest:
            destino_sel = st.selectbox(
                "📍 Destino",
                dest_list,
                key="cat_destino_sel",
                help="Selecciona el destino para ver los precios CIF"
            )
        with col_pal:
            pallets_sel = st.slider(
                "🚜 Pallets (vista CIF)",
                min_value=1, max_value=20, value=3,
                key="cat_pallets_sel",
                help="Mueve el slider para ver como cambian los precios CIF segun el volumen"
            )
        with col_cur:
            moneda_dest = dests_moneda.get(destino_sel, 'USD')
            rates = get_exchange_rates()
            st.metric("💱 Moneda Destino", moneda_dest)

        desc_pct  = get_descuento_volumen(pallets_sel)
        tramo_lbl = get_tramo_label(pallets_sel)
        if desc_pct > 0:
            st.success(f"🏷\ufe0f Tramo activo: **{tramo_lbl}** \u2014 Descuento: **{desc_pct*100:.0f}%** sobre precio CIF")
        else:
            st.info(f"🏷\ufe0f Tramo: **{tramo_lbl}** \u2014 Sin descuento por volumen (minimo 3 pallets)")

        flete_caja = dests.get(destino_sel, 0)
        if isinstance(flete_caja, dict):
            flete_caja = flete_caja.get('factor', 0)

        overhead  = float(cfg.get('costo_caja', 0) or 0)
        merma_pct = float(cfg.get('merma_pct', 0) or 0)
        grupos    = cfg.get('grupos', {})

        # Build main price table
        rows = []
        for p in prods_activos:
            cod           = p.get('codigo', '')
            nombre        = p.get('producto', '') or p.get('descripcion', '')
            grupo         = p.get('grupo', '')
            g_info        = grupos.get(grupo, {}) if isinstance(grupos.get(grupo, {}), dict) else {}
            cxp           = int(g_info.get('cajas_pallet', p.get('cajas_pallet', 160)) or 160)
            precio_compra = float(p.get('precio_compra', 0) or 0)
            margen_pct    = float(p.get('margen_pct', 0.1) or 0.1)
            costo_total   = precio_compra + overhead * (1 + merma_pct)
            fob_caja      = round(costo_total * (1 + margen_pct), 4)
            cif_base      = fob_caja + flete_caja
            cif_vol       = round(cif_base * (1 - desc_pct), 4)
            fob_pallet    = round(fob_caja * cxp, 2)
            cif_pallet    = round(cif_vol * cxp, 2)
            row = {
                'Cod':           cod,
                'Producto':      nombre,
                'Gr':            grupo,
                'Cj/Plt':        cxp,
                'P.Compra $/cj': round(precio_compra, 4),
                'Margen':        f"{margen_pct*100:.0f}%",
                'FOB $/cj':      round(fob_caja, 4),
                'FOB $/plt':     fob_pallet,
                f'CIF {pallets_sel}P $/cj':  cif_vol,
                f'CIF {pallets_sel}P $/plt': cif_pallet,
            }
            if moneda_dest != 'USD':
                rate = rates.get(moneda_dest, 1.0)
                sym  = MONEDA_SIMBOLO.get(moneda_dest, moneda_dest)
                row[f'CIF {pallets_sel}P {sym}/cj']  = round(cif_vol * rate, 4)
                row[f'CIF {pallets_sel}P {sym}/plt'] = round(cif_pallet * rate, 2)
            rows.append(row)

        df = pd.DataFrame(rows).set_index('Cod')
        cif_cols = [c for c in df.columns if c.startswith('CIF')]
        fob_cols = [c for c in df.columns if c.startswith('FOB')]

        def _color_col(col):
            styles = []
            for _ in col:
                if col.name in cif_cols:
                    styles.append('background-color:#d4edda;font-weight:bold;color:#155724')
                elif col.name in fob_cols:
                    styles.append('background-color:#fff3cd;font-weight:bold;color:#856404')
                elif col.name == 'Margen':
                    styles.append('color:#0066cc;font-weight:bold')
                else:
                    styles.append('')
            return styles

        styled_df = df.style.apply(_color_col, axis=0)
        st.dataframe(styled_df, use_container_width=True, height=min(80 + 35*len(rows), 620))

        # Full CIF table 1-20 pallets
        with st.expander("📅 Ver tabla CIF completa \u2014 pallets 1 a 20", expanded=False):
            st.markdown(f"**Destino: {destino_sel}** | CIF en USD/caja para cada volumen de pallets")
            pal_rows = []
            for npal in range(1, 21):
                d_p  = get_descuento_volumen(npal)
                tl_p = get_tramo_label(npal)
                pr   = {'Pallets': npal, 'Tramo': tl_p, 'Dto.': f"{d_p*100:.0f}%"}
                for p2 in prods_activos:
                    cod_p  = p2.get('codigo', '')
                    grp_p  = p2.get('grupo', '')
                    g_i    = grupos.get(grp_p, {}) if isinstance(grupos.get(grp_p, {}), dict) else {}
                    cxp2   = int(g_i.get('cajas_pallet', p2.get('cajas_pallet', 160)) or 160)
                    pc2    = float(p2.get('precio_compra', 0) or 0)
                    mg2    = float(p2.get('margen_pct', 0.1) or 0.1)
                    ct2    = pc2 + overhead * (1 + merma_pct)
                    fob2   = ct2 * (1 + mg2)
                    cif2   = round((fob2 + flete_caja) * (1 - d_p), 4)
                    pr[f'{cod_p} $/cj']  = cif2
                    pr[f'{cod_p} $/plt'] = round(cif2 * cxp2, 2)
                pal_rows.append(pr)
            df2 = pd.DataFrame(pal_rows).set_index('Pallets')
            def _hl_row(row):
                clr = 'background-color:#c3e6cb;font-weight:bold' if row.name == pallets_sel else ''
                return [clr]*len(row)
            st.dataframe(df2.style.apply(_hl_row, axis=1), use_container_width=True, height=420)

        # Edit costs & margins
        st.markdown("---")
        st.markdown("### \u2699\ufe0f Editar Costos y Margenes")
        st.caption("Modifica precio de compra y margen de cada producto. FOB/CIF se recalculan automaticamente.")
        edit_rows = []
        for p in prods:
            edit_rows.append({
                'Cod':            p.get('codigo',''),
                'Producto':       p.get('producto','') or p.get('descripcion',''),
                'Activo':         bool(p.get('activo', True)),
                'P.Compra $/cj':  float(p.get('precio_compra', 0) or 0),
                'Margen %':       round(float(p.get('margen_pct', 0.1) or 0.1)*100, 1),
                'Grupo':          p.get('grupo', ''),
            })
        df_edit = pd.DataFrame(edit_rows)
        edited = st.data_editor(
            df_edit,
            column_config={
                'Cod':           st.column_config.TextColumn('Codigo', disabled=True, width='small'),
                'Producto':      st.column_config.TextColumn('Producto', width='medium'),
                'Activo':        st.column_config.CheckboxColumn('Activo', width='small'),
                'P.Compra $/cj': st.column_config.NumberColumn('P.Compra $/cj', format="$%.4f", step=0.01),
                'Margen %':      st.column_config.NumberColumn('Margen %', format="%.1f%%", step=0.5, min_value=0, max_value=100),
                'Grupo':         st.column_config.SelectboxColumn('Grupo', options=['A','B','C','D','E','F','G','H','I','J','K']),
            },
            use_container_width=True,
            num_rows='dynamic',
            key='edit_productos_tabla',
            hide_index=True,
        )
        if st.button("💾 Guardar Cambios de Precios", type='primary', use_container_width=True, key='btn_guardar_precios'):
            new_prods    = []
            old_by_cod   = {p.get('codigo'): p for p in prods}
            for _, row in edited.iterrows():
                cod_row = str(row.get('Cod',''))
                if cod_row in old_by_cod:
                    upd = dict(old_by_cod[cod_row])
                    upd['producto']      = str(row['Producto'])
                    upd['descripcion']   = str(row['Producto'])
                    upd['activo']        = bool(row['Activo'])
                    upd['precio_compra'] = float(row['P.Compra $/cj'])
                    upd['margen_pct']    = round(float(row['Margen %']) / 100, 4)
                    upd['grupo']         = str(row['Grupo'])
                    new_prods.append(upd)
                elif cod_row:
                    new_prods.append({
                        'codigo':        cod_row,
                        'producto':      str(row.get('Producto','')),
                        'descripcion':   str(row.get('Producto','')),
                        'precio_compra': float(row.get('P.Compra $/cj', 0)),
                        'margen_pct':    round(float(row.get('Margen %', 10)) / 100, 4),
                        'grupo':         str(row.get('Grupo','A')),
                        'activo':        bool(row.get('Activo', True)),
                        'cajas_pallet':  160,
                        'tramos_precio': [],
                    })
            data['products'] = new_prods
            save_data(data)
            st.toast("Precios y margenes guardados", icon='\u2705')
            st.rerun()

    # SUB-TAB 2: DESTINOS & MONEDAS
    with sub2:
        st.markdown("### 🌍 Gestionar Destinos & Fletes")
        st.caption("Flete en USD/caja. La moneda define la divisa mostrada al cliente.")
        dest_rows = []
        for dest_name, val in dests.items():
            flete_v  = val.get('factor', val) if isinstance(val, dict) else val
            moneda_v = dests_moneda.get(dest_name, 'USD')
            dest_rows.append({'Destino': dest_name, 'Flete $/cj': float(flete_v), 'Moneda': moneda_v})
        df_dest = pd.DataFrame(dest_rows)
        edited_dest = st.data_editor(
            df_dest,
            column_config={
                'Destino':    st.column_config.TextColumn('Destino', width='large'),
                'Flete $/cj': st.column_config.NumberColumn('Flete $/cj', format="$%.4f", step=0.01),
                'Moneda':     st.column_config.SelectboxColumn('Moneda', options=MONEDAS),
            },
            use_container_width=True,
            num_rows='dynamic',
            key='edit_destinos_tabla',
            hide_index=True,
        )
        if st.button("💾 Guardar Destinos", type='primary', use_container_width=True, key='btn_guardar_destinos'):
            new_dests  = {}
            new_moneda = {}
            for _, row in edited_dest.iterrows():
                if row.get('Destino'):
                    new_dests[str(row['Destino'])]  = float(row['Flete $/cj'])
                    new_moneda[str(row['Destino'])] = str(row['Moneda'])
            data['config']['destinos']        = new_dests
            data['config']['destinos_moneda'] = new_moneda
            save_data(data)
            st.toast("Destinos guardados", icon='\u2705')
            st.rerun()

        st.markdown("---")
        st.markdown("### 💹 Tipos de Cambio en Tiempo Real")
        rates2 = get_exchange_rates()
        lbl2   = data.get('config', {}).get('_rate_label', '')
        r_cols = st.columns(min(len(rates2), 9))
        for i2, (cur2, rate2) in enumerate(list(rates2.items())[:9]):
            with r_cols[i2]:
                sym2 = MONEDA_SIMBOLO.get(cur2, cur2)
                st.metric(f"USD/{cur2}", f"{sym2}{rate2:.4f}", help=lbl2)

    # SUB-TAB 3: IMPORTAR EXCEL
    with sub3:
        st.markdown("### 📂 Importar desde Excel")
        uploaded = st.file_uploader("Sube el archivo Excel de precios", type=["xlsx","xls"], key="excel_uploader_cat")
        if uploaded:
            try:
                parsed = parse_excel_file(uploaded)
                if parsed:
                    st.success(f"Se encontraron {len(parsed)} productos en el Excel.")
                    prev = {p.get('codigo'): p for p in prods}
                    new_count = 0
                    upd_count = 0
                    for np in parsed:
                        cod2 = np.get('codigo','')
                        if cod2 in prev:
                            prev[cod2].update({k: v for k, v in np.items() if v is not None})
                            upd_count += 1
                        else:
                            prods.append(np)
                            new_count += 1
                    data['products'] = list(prev.values()) + [p for p in prods if p.get('codigo') not in prev]
                    save_data(data)
                    st.success(f"Importado: {upd_count} actualizados, {new_count} nuevos.")
                    st.rerun()
                else:
                    st.warning("No se encontraron productos validos en el archivo.")
            except Exception as e:
                st.error(f"Error al importar: {e}")

def render_hacer_pedido():
    st.markdown('## 🛒 Crear Nuevo Pedido')
    data=load_data(); prods=data.get('products',[]); dests=data.get('config',{}).get('destinos',{})
    if not prods:
        st.warning('⚠️ No hay productos. Ve al tab **Cotización** y sube tu archivo Excel primero.')
        return
    clients=load_clients()
    # Paso 1: Cliente
    st.markdown('### 1️⃣ Datos del Cliente')
    cl1,cl2=st.columns(2)
    c_email=cl1.text_input('📧 Email',placeholder='cliente@empresa.com',key='hp_email')
    c_name=cl2.text_input('👤 Nombre',placeholder='Nombre / Empresa',key='hp_nombre')
    seg=None
    if c_email and c_email in clients:
        c=clients[c_email]; seg=segmentar(c_email,clients)
        st.success(f'✅ Cliente: {c.get("nombre","")} | {seg["badge"]} | Desc: {seg["descuento"]*100:.0f}%')
        if not c_name: c_name=c.get('nombre','')
    elif c_email: st.info('🆕 Cliente nuevo - se registrará al guardar')
    # Paso 2: Destino
    st.markdown('### 2️⃣ Destino')
    dest_opts=list(dests.keys()) if dests else ['Madrid/España','París/Francia','Londres/UK','Miami/USA']
    destino=st.selectbox('🌍 Destino',dest_opts,key='hp_dest')
    dest_v=dests.get(destino,{}) if dests else {}
    moneda=dest_v.get('moneda','USD') if isinstance(dest_v,dict) else 'USD'
    dest_factor=dest_v.get('factor',1.0) if isinstance(dest_v,dict) else (float(dest_v) if isinstance(dest_v,(int,float)) else 1.0)
    st.caption(f'Moneda destino: {moneda}')
    # Paso 3: Productos
    st.markdown('### 3️⃣ Agregar Productos')
    pc1,pc2,pc3=st.columns([3,1,1])
    prod_opts=[p.get('codigo','')+' - '+(p.get('descripcion','') or p.get('producto','')) for p in prods]
    psel=pc1.selectbox('Producto',['Seleccionar...']+prod_opts,key='hp_prod')
    cajas=pc2.number_input('Cajas',min_value=1,value=100,step=50,key='hp_cajas')
    pc3.markdown('<br>',unsafe_allow_html=True)
    if pc3.button('➕ Agregar') and psel!='Seleccionar...':
        cod=psel.split(' - ')[0]
        pd_=next((p for p in prods if p.get('codigo')==cod),{})
        precio=get_precio(cod,destino,data)
        # Aplicar descuento de segmento Y descuento de volumen
        _cart_pals = sum(i.get('pallets',0) for i in st.session_state.carrito)
        _vol_disc = get_descuento_volumen(max(_cart_pals,1))
        _seg_disc = seg['descuento'] if seg else 0
        _total_disc = min(_vol_disc + _seg_disc, 0.30)  # Max 30% combined
        precio = round(precio * (1 - _total_disc), 2)
        cxp=pd_.get('cajas_pallet',200) or 200
        pallets=round(cajas/cxp,2)
        item={'codigo':cod,'producto':pd_.get('descripcion','') or pd_.get('producto',''),'cajas':cajas,'pallets':pallets,'precio_usd':precio,'total':round(cajas*precio,2)}
        ex_idx=next((i for i,x in enumerate(st.session_state.carrito) if x['codigo']==cod),None)
        if ex_idx is not None:
            st.session_state.carrito[ex_idx]['cajas']+=cajas
            st.session_state.carrito[ex_idx]['total']=round(st.session_state.carrito[ex_idx]['cajas']*precio,2)
        else: st.session_state.carrito.append(item)
        st.rerun()
    # Carrito
    if st.session_state.carrito:
        st.markdown('#### 🛒 Carrito')
        st.dataframe(pd.DataFrame(st.session_state.carrito)[['codigo','producto','cajas','pallets','precio_usd','total']],use_container_width=True,hide_index=True)
        tot=sum(i['total'] for i in st.session_state.carrito)
        tc1,tc2,tc3=st.columns(3)
        tc1.metric('📦 Cajas',f'{sum(i["cajas"] for i in st.session_state.carrito):,}')
        tc2.metric('📍 Pallets',f'{sum(i["pallets"] for i in st.session_state.carrito):.1f}')
        tc3.metric('💰 Total',f'${tot:,.2f}')
        if st.button('🗑️ Vaciar',key='vaciar'): st.session_state.carrito=[]; st.rerun()
    # Paso 4
    st.markdown('### 4️⃣ Confirmar')
    notas=st.text_area('Notas',placeholder='Instrucciones especiales...',key='hp_notas')
    ht1,ht2=st.columns(2)
    TOPH=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de cr\xe9dito (LC)','Pago a 30 d\xedas','Pago a 60 d\xedas','Otro']
    hp_term=ht1.selectbox('\📋 T\xe9rminos de pago',TOPH,key='hp_term')
    hp_ent=ht2.text_input('\📅 Fecha entrega estimada',placeholder='ej: 2026-06-20',key='hp_ent')
    notas_internas=st.text_area('🔒 Notas internas (no visibles al cliente)',placeholder='Instrucciones de almacén, condiciones especiales...',key='hp_notas_int',height=60)
    if st.session_state.carrito:
        _tot_pre = sum(i['total'] for i in st.session_state.carrito)
        _plt_pre = sum(i.get('pallets',0) for i in st.session_state.carrito)
        st.markdown(
            f'<div style="background:#f0f7ff;border:1px solid #003E8C;border-radius:8px;padding:12px 18px;margin:8px 0">'
            f'📋 <b>Resumen</b><br>'
            f'&bull; Cliente: <b>{c_name}</b> ({c_email})<br>'
            f'&bull; Destino: <b>{destino}</b><br>'
            f'&bull; Productos: <b>{len(st.session_state.carrito)}</b> &nbsp; Pallets: <b>{_plt_pre:.2f}</b><br>'
            f'&bull; 💰 Total: <b style="color:#003E8C">${_tot_pre:,.2f} USD</b>'
            f'</div>',
            unsafe_allow_html=True
        )
    if st.button('📤 GUARDAR PEDIDO',type='primary',use_container_width=True):
        if not c_email: st.error('❌ Ingresa email del cliente')
        elif not c_name: st.error('❌ Ingresa nombre del cliente')
        elif not st.session_state.carrito: st.error('❌ Agrega productos al carrito')
        else:
            _tod_h=load_pedidos()
            _yn_h=datetime.now().strftime('%Y')
            _pc_h=[p for p in _tod_h if p.get('id','').startswith(f'PED-{_yn_h}')]
            pid=f'PED-{_yn_h}-{len(_pc_h)+1:04d}'
            tot=sum(i['total'] for i in st.session_state.carrito)
            ped={'id':pid,'client_email':c_email,'client_name':c_name,'destino':destino,'moneda':moneda,'productos':list(st.session_state.carrito),'total_usd':round(tot,2),'estado':'Recibido','fecha':datetime.now().isoformat(),'notas':notas,'notas_internas':notas_internas,'terminos_pago':hp_term,'fecha_entrega':hp_ent,'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email}],'creado_por':st.session_state.user_email}
            todos=load_pedidos(); todos.append(ped); save_pedidos(todos)
            if c_email not in clients: clients[c_email]={'nombre':c_name,'email':c_email,'fecha_registro':datetime.now().isoformat(),'pedidos_ids':[]}
            clients[c_email]['pedidos_ids']=clients[c_email].get('pedidos_ids',[])+[pid]
            save_clients(clients)
            try:
                send_order_email(ped)
                _email_status = 'enviado'
            except Exception:
                _email_status = 'fallido'
            el=load_email_log(); el.append({'id':f'EMAIL-{len(el)+1:05d}','destinatario':c_email,'asunto':f'Pedido {pid} recibido','tipo':'confirmacion','fecha':datetime.now().isoformat(),'estado':_email_status}); save_email_log(el)
            st.session_state.carrito=[]
            st.success(f'✅ Pedido {pid} creado por ${tot:,.2f}')
            st.cache_data.clear()

# ─── TAB PRECIOS ─────────────────────────────────────────────────────────
def render_destinos():
    st.markdown('## 🌍 Todos los Destinos - Tarifas')
    data=load_data(); dests=data.get('config',{}).get('destinos',{})
    if not dests: st.info('⚠️ Sube el Excel en Cotización para ver los destinos.'); return
    rows_d=[]
    for k,v in dests.items():
        if isinstance(v,dict): rows_d.append({'Destino':k,'Moneda':v.get('moneda','USD'),'CIF':v.get('factor',1.0)})
        else: rows_d.append({'Destino':k,'Moneda':'USD/EUR','CIF USD':round(float(v),2) if isinstance(v,(int,float)) else 0})
    st.dataframe(pd.DataFrame(rows_d),use_container_width=True,hide_index=True)

# ─── TAB GESTION PEDIDOS ──────────────────────────────────────────────
def render_gestion_pedidos():
    st.markdown('## 📦 Gestión de Pedidos')
    pedidos=load_pedidos()
    f1,f2,f3=st.columns(3)
    fe=f1.selectbox('Estado',['Todos']+ORDEN_ESTADOS,key='gp_e')
    fc=f2.text_input('Cliente/ID',key='gp_c')
    fd=f3.selectbox('Destino',['Todos']+sorted(set(p.get('destino','') for p in pedidos if p.get('destino'))),key='gp_d')
    fd1,fd2=st.columns(2)
    _fecha_desde = fd1.date_input('📅 Desde', value=date.today() - timedelta(days=90), key='gp_desde')
    _fecha_hasta = fd2.date_input('📅 Hasta', value=date.today(), key='gp_hasta')
    filt=[p for p in pedidos if
        (fe=='Todos' or p.get('estado')==fe) and
        (not fc or fc.lower() in (p.get('client_name','')+p.get('id','')).lower()) and
        (fd=='Todos' or p.get('destino')==fd) and
        (str(_fecha_desde) <= p.get('fecha','')[:10] <= str(_fecha_hasta))
    ]
    _tot_filt = sum(p.get('total_usd',0) for p in filt)
    st.info(f'📦 **{len(filt)} pedidos** filtrados | 💰 Total: $**{_tot_filt:,.2f}** USD')
    if filt:
        xb=exportar_excel(filt)
        if xb: st.download_button('📥 Excel',data=xb,file_name=f'pedidos_{date.today()}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.markdown('---')
    for ped in sorted(filt,key=lambda x:x.get('fecha',''),reverse=True):
        icon=ESTADO_ICONS.get(ped.get('estado',''),'📦')
        with st.expander(f"{icon} #{ped.get('id','').upper()} • {ped.get('client_name','N/A')} • {ped.get('destino','')} • ${ped.get('total_usd',0):,.2f}"):
            cl1,cl2,cl3=st.columns(3)
            cl1.markdown(f"**Cliente:** {ped.get('client_name','')}"); cl1.markdown(f"**Email:** {ped.get('client_email','')}")
            cl2.markdown(f"**Destino:** {ped.get('destino','')}"); cl2.markdown(f"**Fecha:** {ped.get('fecha','')[:10]}")
            cl3.markdown(f"**Total:** ${ped.get('total_usd',0):,.2f}"); cl3.markdown(f"**Estado:** {ped.get('estado','')}")
            _bl_key = f'bl_{ped.get("id","")}'
            _bl_val = ped.get('bl_numero','')
            _bl_new = st.text_input('🛳️ Nº BL / Contenedor', value=_bl_val, key=_bl_key, placeholder='ej: MSKU1234567')
            if _bl_new != _bl_val:
                _all_p2 = load_pedidos()
                for _ip2, _pp2 in enumerate(_all_p2):
                    if _pp2.get('id') == ped.get('id'): _all_p2[_ip2]['bl_numero'] = _bl_new; break
                save_pedidos(_all_p2); st.cache_data.clear()
            if ped.get('productos'):
                st.dataframe(pd.DataFrame(ped['productos'])[['codigo','producto','cajas','pallets','precio_usd','total']].rename(columns={'codigo':'Código','producto':'Producto','cajas':'Cajas','pallets':'Pallets','precio_usd':'Precio USD','total':'Total USD'}),use_container_width=True,hide_index=True)
            if ped.get('notas'): st.markdown(f"**Notas:** {ped['notas']}")
            if REPORTLAB_OK:
                with st.expander('✒️ Editar pedido',expanded=False):
                    ec1,ec2=st.columns(2)
                    new_nom_g=ec1.text_input('Nombre',value=ped.get('client_name',''),key=f'g_nom_{ped.get("id","")}' )
                    new_eml_g=ec2.text_input('Email',value=ped.get('client_email',''),key=f'g_eml_{ped.get("id","")}')
                    ed1,ed2=st.columns(2)
                    new_dst_g=ed1.text_input('Destino',value=ped.get('destino',''),key=f'g_dst_{ped.get("id","")}' )
                    new_not_g=ed2.text_input('Notas',value=ped.get('notas',''),key=f'g_not_{ped.get("id","")}')
                    et1,et2=st.columns(2)
                    TOPTG=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de crédito (LC)','Pago a 30 días','Pago a 60 días','Otro']
                    cur_tg=ped.get('terminos_pago',''); t_ig=TOPTG.index(cur_tg) if cur_tg in TOPTG else 0
                    new_ter_g=et1.selectbox('Términos',TOPTG,index=t_ig,key=f'g_ter_{ped.get("id","")}')
                    new_ent_g=et2.text_input('Fecha entrega',value=ped.get('fecha_entrega',''),placeholder='ej: 2026-06-20',key=f'g_ent_{ped.get("id","")}')
                    ep_rg=[{'Cod':i.get('codigo',''),'Producto':i.get('producto',''),'Cajas':int(i.get('cajas',0)),'Precio_USD':float(i.get('precio_usd',0))} for i in ped.get('productos',[])]
                    if ep_rg:
                        ep_eg=st.data_editor(pd.DataFrame(ep_rg),column_config={'Cod':st.column_config.TextColumn('Cod',disabled=True),'Producto':st.column_config.TextColumn('Prod',disabled=True),'Cajas':st.column_config.NumberColumn('Cajas',min_value=1,step=1),'Precio_USD':st.column_config.NumberColumn('$/cj',format='$%.4f')},use_container_width=True,num_rows='dynamic',key=f'g_ep_{ped.get("id","")}',hide_index=True)
                    if st.button('💾 Guardar cambios',key=f'g_save_{ped.get("id","")}',type='primary'):
                        all_p=load_pedidos(); dd_g=load_data()
                        for _i,_p in enumerate(all_p):
                            if _p.get('id')==ped.get('id'):
                                all_p[_i].update({'client_name':new_nom_g,'client_email':new_eml_g,'destino':new_dst_g,'notas':new_not_g,'terminos_pago':new_ter_g,'fecha_entrega':new_ent_g})
                                nw_it=[]
                                for _,rr in ep_eg.iterrows():
                                    c3=int(rr['Cajas']); gp3=next((p.get('grupo','') for p in dd_g.get('products',[]) if p.get('codigo')==rr['Cod']),'')
                                    gi3=dd_g.get('config',{}).get('grupos',{}).get(gp3,{}); cx3=gi3.get('cajas_pallet',160) if isinstance(gi3,dict) else 160
                                    nw_it.append({'codigo':str(rr['Cod']),'producto':str(rr['Producto']),'cajas':c3,'pallets':round(c3/cx3,2),'precio_usd':float(rr['Precio_USD']),'total':round(c3*float(rr['Precio_USD']),2)})
                                all_p[_i]['productos']=nw_it; all_p[_i]['total_usd']=round(sum(it['total'] for it in nw_it),2)
                                all_p[_i].setdefault('historial_estados',[]).append({'estado':'Editado','fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email,'nota':'Editado manualmente'})
                                break
                        save_pedidos(all_p); st.toast('✅ Pedido actualizado',icon='✅'); st.rerun()
            hist_g=ped.get('historial_estados',[])
            if hist_g:
                with st.expander('📜 Historial',expanded=False):
                    for h in reversed(hist_g):
                        h_ic=ESTADO_ICONS.get(h.get('estado',''),'📜'); h_fe=h.get('fecha','')[:16].replace('T',' ')
                        h_no=h.get('nota',''); no_s=f' — {h_no}' if h_no else ''
                        st.caption(f"{h_ic} **{h.get('estado','')}** • {h_fe} • {h.get('usuario','')}{no_s}")
            _pdf_b, _pdf_m, _pdf_x = build_order_pdf(ped)
            st.download_button('⬇️ Albarán PDF', data=_pdf_b, file_name=f"{ped.get('id','ped')}{_pdf_x}", mime=_pdf_m, key=f'pdf_adm_{ped.get("id","")}', use_container_width=True)
            st.markdown('**Cambiar Estado — clic rápido:**')
            estado_actual = ped.get('estado','Recibido')
            qb_cols = st.columns(len(ORDEN_ESTADOS))
            for qi, qe in enumerate(ORDEN_ESTADOS):
                _icon = ESTADO_ICONS.get(qe,'')
                _is_current = (qe == estado_actual)
                if qb_cols[qi].button(f'{_icon} {qe}', key=f'qb_{ped["id"]}_{qe}', type='primary' if _is_current else 'secondary', use_container_width=True):
                    if not _is_current:
                        todos=load_pedidos()
                        for _i,_p in enumerate(todos):
                            if _p.get('id')==ped.get('id'):
                                todos[_i]['estado']=qe
                                todos[_i].setdefault('historial_estados',[]).append({'estado':qe,'fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email})
                                break
                        save_pedidos(todos); st.cache_data.clear(); st.rerun()

# ─── TAB CONFIGURACION ──────────────────────────────────────────────
def render_configuracion():
    st.markdown('## ⚙️ Configuración del Sistema')
    st.markdown('### 👤 Usuarios del Sistema')
    _users_file = 'users_custom.json'
    _users_data = _load(_users_file, {})
    _all_users_display = []
    for _ue, _uv in USERS.items():
        _all_users_display.append({'Email': _ue, 'Nombre': _uv['nombre'], 'Rol': _uv['rol'], 'Tipo': '🔒 Sistema'})
    for _ue, _uv in _users_data.items():
        if _ue not in USERS:
            _all_users_display.append({'Email': _ue, 'Nombre': _uv.get('nombre',''), 'Rol': _uv.get('rol','ventas'), 'Tipo': '👤 Custom'})
    st.dataframe(pd.DataFrame(_all_users_display), use_container_width=True, hide_index=True)
    with st.expander('➕ Agregar / Cambiar Contraseña de Usuario', expanded=False):
        _un1, _un2 = st.columns(2)
        _new_email = _un1.text_input('📧 Email del usuario', key='cfg_new_email', placeholder='usuario@exportharet.com')
        _new_nombre = _un2.text_input('👤 Nombre', key='cfg_new_nombre')
        _np1, _np2, _np3 = st.columns(3)
        _new_pwd = _np1.text_input('🔑 Contraseña', type='password', key='cfg_new_pwd')
        _new_rol = _np2.selectbox('Rol', ['admin', 'ventas'], key='cfg_new_rol')
        _np3.markdown('<br>', unsafe_allow_html=True)
        if _np3.button('💾 Guardar Usuario', key='cfg_save_user', type='primary'):
            if not _new_email or not _new_pwd:
                st.error('Email y contraseña son obligatorios')
            else:
                _users_data[_new_email] = {'pwd': hashlib.md5(_new_pwd.encode()).hexdigest(), 'rol': _new_rol, 'nombre': _new_nombre or _new_email}
                _save(_users_file, _users_data)
                st.toast(f'✅ Usuario {_new_email} guardado', icon='✅')
                st.rerun()
    if _users_data:
        with st.expander('🗑️ Eliminar Usuario Custom', expanded=False):
            _del_user = st.selectbox('Usuario a eliminar', list(_users_data.keys()), key='cfg_del_user')
            if st.button('🗑️ Eliminar', key='cfg_del_btn', type='secondary'):
                del _users_data[_del_user]
                _save(_users_file, _users_data)
                st.toast(f'✅ Usuario {_del_user} eliminado')
                st.rerun()
    st.markdown('---')
    st.markdown('### 📧 Log de Emails')
    elog=load_email_log()
    if elog:
        df_e=pd.DataFrame(elog[-20:][::-1])
        st.dataframe(df_e[['id','destinatario','asunto','tipo','fecha','estado']].rename(columns={'id':'ID','destinatario':'Para','asunto':'Asunto','tipo':'Tipo','fecha':'Fecha','estado':'Estado'}),use_container_width=True,hide_index=True)
    else: st.info('Sin emails registrados')
    st.markdown('---')
    st.markdown('---')
    st.markdown('### 📨 Emails de Pedidos')
    _pend_e = _load('pending_emails.json', [])
    _unsent_e = [e for e in _pend_e if not e.get('sent')]
    if _unsent_e:
        st.error(f'⚠️ {len(_unsent_e)} pedido(s) sin email enviado — configurar SMTP en Streamlit Secrets')
        for _ue in reversed(_unsent_e[-5:]):
            st.caption(f'❌ {_ue.get("id","")} | {_ue.get("fecha","")[:16]} | {_ue.get("cliente","")} | ${_ue.get("total",0):,.2f} | {_ue.get("error","")}')
    elif _pend_e:
        st.success(f'✅ {len([e for e in _pend_e if e.get("sent")])} email(s) enviados correctamente')
    else:
        st.info('📬 Sin historial de emails aún')
    st.markdown('---')
    st.markdown('### 📧 Estado SMTP (order@exportharet.com)')
    try:
        _smtp_cfg = st.secrets.get('email', {})
        _smtp_host = _smtp_cfg.get('smtp_host', '')
        if _smtp_host:
            st.success(f'✅ SMTP activo: {_smtp_cfg.get("smtp_user","?")} → {_smtp_host}:{_smtp_cfg.get("smtp_port",587)} | Emails van a order@exportharet.com')
        else:
            st.warning('⚠️ SMTP no configurado — agregar en Streamlit Secrets: [email] smtp_host / smtp_user / smtp_pass')
    except:
        st.info('ℹ️ Configura SMTP en Streamlit Cloud → App settings → Secrets.')
    st.markdown('---')
    st.markdown('### 🗃️ Archivos de Datos')
    for fname in [DATA_FILE,CLIENTS_FILE,PEDIDOS_FILE,HIST_FILE,EMAIL_FILE]:
        exists=os.path.exists(fname)
        st.markdown(f"{'\u2705' if exists else '\u274C'} `{fname}`")
    st.markdown('---')
    st.markdown('### 🖼️ Logotipo de la Aplicación')
    _logo_col1, _logo_col2 = st.columns([2, 1])
    with _logo_col1:
        _logo_file = st.file_uploader('Subir nuevo logo (PNG o JPG)', type=['png','jpg','jpeg'], key='cfg_logo_upload')
        if _logo_file is not None:
            with open('logo.png', 'wb') as _lf: _lf.write(_logo_file.getbuffer())
            st.success('✅ Logo actualizado. Recarga la página para verlo.')
    with _logo_col2:
        import os as _oscfg
        if _oscfg.path.exists('logo.png'):
            from PIL import Image as _ImgCfg
            st.image(_ImgCfg.open('logo.png'), width=140)
        else:
            st.info('Sin logo')
    st.markdown('---')
    st.markdown('### ✏️ Título de la Aplicación')
    _cur_cfg = load_app_config()
    _cur_title = _cur_cfg.get("app_title", "🚀 EXPORT HARET — Panel de Administración")
    _new_title = st.text_input('Título del panel de administración', value=_cur_title, key='cfg_app_title', help='Aparece en el header y sidebar del panel admin.')
    if st.button('💾 Guardar Título', key='cfg_save_title'):
        _cur_cfg["app_title"] = _new_title
        save_app_config(_cur_cfg)
        st.success('✅ Título guardado. Recarga para verlo en el header y sidebar.')

# ─── TAB CLIENTES ──────────────────────────────────────────────
def render_clientes():
    st.markdown('## 👥 Clientes')
    clients=load_clients(); pedidos=load_pedidos()
    if not clients: st.info('No hay clientes. Se crean al hacer pedidos.'); return
    _search = st.text_input('🔍 Buscar cliente', key='cli_search', placeholder='Nombre, email, empresa...')
    rows=[]
    for e,c in clients.items():
        if _search and _search.lower() not in (e + c.get('nombre','') + c.get('empresa','')).lower(): continue
        seg=segmentar(e,clients)
        mp=[p for p in pedidos if p.get('client_email')==e]
        rows.append({'Nombre':c.get('nombre',''),'Email':e,'Empresa':c.get('empresa',''),'País':c.get('pais',''),'Segmento':seg['badge'],'Pedidos':len(mp),'Facturación':f"${sum(p.get('total_usd',0) for p in mp):,.2f}",'Descuento':f"{seg['descuento']*100:.0f}%"})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f'{len(rows)} de {len(clients)} clientes')
    with st.expander('🗑️ Eliminar Cliente', expanded=False):
        _cli_opts = list(clients.keys())
        _del_cli = st.selectbox('Cliente a eliminar', _cli_opts, format_func=lambda e: f"{clients[e].get('nombre','')} ({e})", key='cli_del_sel')
        _cli_peds = [p for p in pedidos if p.get('client_email') == _del_cli]
        if _cli_peds: st.warning(f'⚠️ Este cliente tiene {len(_cli_peds)} pedidos. Se conservarán los pedidos.')
        if st.button('🗑️ Eliminar Cliente', key='cli_del_btn', type='secondary'):
            if _del_cli in clients:
                del clients[_del_cli]; save_clients(clients)
                st.toast(f'✅ Cliente {_del_cli} eliminado'); st.rerun()
    st.markdown('---')
    sel=st.selectbox('Detalle de cliente',['']+list(clients.keys()),key='cli_d')
    if sel:
        c=clients[sel]; seg=segmentar(sel,clients); mp=[p for p in pedidos if p.get('client_email')==sel]
        d1,d2=st.columns(2)
        d1.markdown(f"**Nombre:** {c.get('nombre','')}")
        d1.markdown(f"**Email:** {sel}")
        d1.markdown(f"**Segmento:** {seg['badge']}")
        d2.markdown(f"**Pedidos:** {len(mp)}")
        d2.markdown(f"**Facturación:** ${sum(p.get('total_usd',0) for p in mp):,.2f}")
        d2.markdown(f"**Descuento:** {seg['descuento']*100:.0f}%")
        if mp:
            st.dataframe(pd.DataFrame([{'ID':p.get('id',''),'Destino':p.get('destino',''),'Total':f"${p.get('total_usd',0):,.2f}",'Estado':p.get('estado',''),'Fecha':p.get('fecha','')[:10]} for p in sorted(mp,key=lambda x:x.get('fecha',''),reverse=True)]),use_container_width=True,hide_index=True)
    st.markdown("---")
    st.markdown("### 🔍 Ficha de Cliente")
    _cl_list = list(clients.keys())
    if _cl_list:
        _sel=st.selectbox('Seleccionar cliente',_cl_list,format_func=lambda e:f"{clients[e].get('nombre','')} ({e})",key='sel_cl')
        if _sel:
            _c=clients[_sel]; _seg=segmentar(_sel,clients); _mp=[p for p in pedidos if p.get('client_email')==_sel]
            col_f1,col_f2=st.columns([3,1])
            with col_f1:
                st.markdown(f"#### 👤 {_c.get('nombre','')} {_seg['badge']}")
                fc1,fc2=st.columns(2)
                f_nom=fc1.text_input('Nombre',value=_c.get('nombre',''),key='f_nom')
                f_emp=fc2.text_input('Empresa',value=_c.get('empresa',''),key='f_emp')
                fc3,fc4=st.columns(2)
                f_tel=fc3.text_input('Teléfono/WhatsApp',value=_c.get('telefono',''),key='f_tel')
                f_pais=fc4.text_input('País',value=_c.get('pais',''),key='f_pais')
                TOPTC=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de crédito (LC)','Pago a 30 días','Pago a 60 días','Otro']
                cur_tc=_c.get('terminos_habituales',''); tc_idx=TOPTC.index(cur_tc) if cur_tc in TOPTC else 0
                f_term=st.selectbox('Términos habituales',TOPTC,index=tc_idx,key='f_term')
                f_seg=st.text_input('📅 Próximo seguimiento',value=_c.get('proximo_seguimiento',''),placeholder='ej: 2026-07-01',key='f_seg')
                f_notas=st.text_area('📋 Notas internas (solo admin)',value=_c.get('notas_internas',''),height=90,key='f_notas',placeholder='Preferencias, condiciones especiales...')
                if st.button('💾 Guardar ficha',type='primary',key='save_ficha_cl'):
                    clients[_sel].update({'nombre':f_nom,'empresa':f_emp,'telefono':f_tel,'pais':f_pais,'terminos_habituales':f_term,'proximo_seguimiento':f_seg,'notas_internas':f_notas})
                    save_clients(clients); st.toast('✅ Ficha guardada',icon='✅'); st.rerun()
            with col_f2:
                st.metric('Pedidos',len(_mp))
                st.metric('Facturación',f"${sum(p.get('total_usd',0) for p in _mp):,.2f}")
                st.metric('Descuento',f"{_seg['descuento']*100:.0f}%")
                if _c.get('proximo_seguimiento'): st.info(f"📅 {_c.get('proximo_seguimiento')}")
            if _mp:
                st.markdown('#### 📜 Historial de pedidos')
                st.dataframe(pd.DataFrame([{'ID':p.get('id',''),'Destino':p.get('destino',''),'Total':f"${p.get('total_usd',0):,.2f}",'Terminos':p.get('terminos_pago',''),'Estado':p.get('estado',''),'Fecha':p.get('fecha','')[:10]} for p in sorted(_mp,key=lambda x:x.get('fecha',''),reverse=True)]),use_container_width=True,hide_index=True)

def render_reportes():
    st.markdown('## 📊 Reportes y Analytics')
    pedidos=load_pedidos(); clients=load_clients()
    if not pedidos: st.info('No hay pedidos para analizar.'); return
    fc1,fc2=st.columns(2)
    fd=fc1.date_input('Desde',value=date.today()-timedelta(days=30),key='r_from')
    fh=fc2.date_input('Hasta',value=date.today(),key='r_to')
    pf=[p for p in pedidos if str(fd)<=p.get('fecha','')[:10]<=str(fh)]
    st.markdown(f'**{len(pf)} pedidos en el período**')
    k1,k2,k3,k4=st.columns(4)
    fac=sum(p.get('total_usd',0) for p in pf)
    k1.metric('💰 Facturación',f'${fac:,.0f}')
    k2.metric('📦 Pedidos',len(pf))
    k3.metric('🎫 Ticket Prom.',f'${fac/len(pf):,.0f}' if pf else '$0')
    k4.metric('✅ Entregados',len([p for p in pf if p.get('estado')=='Entregado']))
    st.markdown('---')
    st.markdown('### 🌍 Por Destino')
    dd={}
    for p in pf: dd[p.get('destino','Otros')]=dd.get(p.get('destino','Otros'),0)+p.get('total_usd',0)
    if dd: st.dataframe(pd.DataFrame(sorted(dd.items(),key=lambda x:x[1],reverse=True),columns=['Destino','Total USD']),use_container_width=True,hide_index=True)
    st.markdown('---')
    st.markdown('### 👑 Top Clientes')
    cf={}
    for p in pf: cf[p.get('client_email','')]=cf.get(p.get('client_email',''),0)+p.get('total_usd',0)
    if cf:
        t10=sorted(cf.items(),key=lambda x:x[1],reverse=True)[:10]
        st.dataframe(pd.DataFrame([{'Cliente':clients.get(e,{}).get('nombre',e),'Email':e,'Total':f'${v:,.2f}'} for e,v in t10]),use_container_width=True,hide_index=True)
    if pf:
        st.markdown('---')
        xb=exportar_excel(pf)
        if xb: st.download_button('📥 Exportar Reporte',data=xb,file_name=f'reporte_{fd}_{fh}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')

# ─── MAIN ─────────────────────────────────────────────────────────────────

# ─── PORTAL CLIENT FILES ─────────────────────────────────────────────────────
PORTAL_CLIENTS_FILE = 'portal_clientes.json'

def load_portal_clients():
    return _load(PORTAL_CLIENTS_FILE, {})

def save_portal_clients(c):
    _save(PORTAL_CLIENTS_FILE, c)

def get_fob_price(codigo, data):
    for p in data.get('products', []):
        if p.get('codigo') == codigo:
            return round(float(p.get('precio_cif_usd', 0) or p.get('precio_compra', 0)), 2)
    return 0.0

def get_cif_price(codigo, destino, data):
    return get_precio(codigo, destino, data)

def build_order_html(ped):
    rows=''
    for item in ped.get('productos',[]):
        cod=item.get('codigo',''); prod=item.get('producto','')
        cajas=item.get('cajas',0); pallets=item.get('pallets',0)
        precio=item.get('precio_usd',0); total=item.get('total',0)
        fob_u=item.get('fob_usd',precio); flete_u=item.get('flete_usd',0); dto=item.get('descuento_vol',0)
        rows+=(f'<tr><td style="padding:7px;border:1px solid #e0e0e0">{cod}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0">{prod}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:center">{cajas}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:center">{pallets}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:right;color:#856404">${fob_u:.4f}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:right;color:#888">${flete_u:.4f}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:center;color:#28a745">{dto*100:.0f}%</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:right;font-weight:bold;color:#003E8C">${precio:.4f}</td>'
               f'<td style="padding:7px;border:1px solid #e0e0e0;text-align:right;font-weight:bold">${total:,.2f}</td></tr>')
    pid=ped.get('id',''); fecha=ped.get('fecha','')[:10]; nombre=ped.get('client_name','')
    email_c=ped.get('client_email',''); empresa=ped.get('empresa',''); telefono=ped.get('telefono','')
    pais=ped.get('pais',''); tipo=ped.get('tipo_precio','FOB'); destino=ped.get('destino','')
    total_usd=ped.get('total_usd',0); notas=ped.get('notas',''); estado=ped.get('estado','Recibido')
    terminos=ped.get('terminos_pago',''); f_entrega=ped.get('fecha_entrega','')
    incoterm=f'{tipo} {destino}' if tipo=='CIF' and destino else tipo
    t_row=f'<tr><td colspan="2" style="padding:6px;font-weight:bold;background:#f8f9fa">T\xe9rminos de pago:</td><td colspan="7" style="padding:6px">{terminos}</td></tr>' if terminos else ''
    e_row=f'<tr><td colspan="2" style="padding:6px;font-weight:bold;background:#f8f9fa">Entrega estimada:</td><td colspan="7" style="padding:6px">{f_entrega}</td></tr>' if f_entrega else ''
    return f'''<div style="font-family:Arial,sans-serif;max-width:750px;margin:0 auto;padding:20px">
      <div style="background:linear-gradient(135deg,#003E8C,#0066CC);color:white;padding:24px;border-radius:10px;margin-bottom:20px">
        <h1 style="margin:0;font-size:1.6em">\🚀 Export Haret</h1>
        <p style="margin:4px 0 0;opacity:.85">Confirmaci\xf3n de Pedido | Frutas Ex\xf3ticas Premium</p>
      </div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px">
        <tr><td style="padding:6px;font-weight:bold">N\xba Pedido:</td><td style="padding:6px">{pid}</td>
            <td style="padding:6px;font-weight:bold">Estado:</td><td style="padding:6px">{estado}</td></tr>
        <tr><td style="padding:6px;font-weight:bold">Cliente:</td><td style="padding:6px">{nombre}</td>
            <td style="padding:6px;font-weight:bold">Empresa:</td><td style="padding:6px">{empresa}</td></tr>
        <tr><td style="padding:6px;font-weight:bold">Email:</td><td style="padding:6px">{email_c}</td>
            <td style="padding:6px;font-weight:bold">Tel\xe9fono:</td><td style="padding:6px">{telefono}</td></tr>
        <tr><td style="padding:6px;font-weight:bold">Pa\xeds:</td><td style="padding:6px">{pais}</td>
            <td style="padding:6px;font-weight:bold">Fecha:</td><td style="padding:6px">{fecha}</td></tr>
        <tr><td style="padding:6px;font-weight:bold">Incoterm:</td><td style="padding:6px">{incoterm}</td>
            <td style="padding:6px;font-weight:bold">Destino:</td><td style="padding:6px">{destino}</td></tr>
        {t_row}{e_row}
      </table>
      <h3 style="border-bottom:2px solid #003E8C;padding-bottom:6px">Detalle de Productos</h3>
      <table style="width:100%;border-collapse:collapse;font-size:.88em">
        <thead><tr style="background:#003E8C;color:white">
          <th style="padding:8px">C\xf3d</th><th style="padding:8px">Producto</th>
          <th style="padding:8px">Cajas</th><th style="padding:8px">Pallets</th>
          <th style="padding:8px">FOB $/cj</th><th style="padding:8px">Flete $/cj</th>
          <th style="padding:8px">Dto.Vol</th><th style="padding:8px">Precio $/cj</th>
          <th style="padding:8px">Total USD</th>
        </tr></thead><tbody>{rows}</tbody>
        <tfoot><tr style="background:#e8f0fe">
          <td colspan="8" style="padding:10px;text-align:right;font-weight:bold">TOTAL:</td>
          <td style="padding:10px;font-weight:bold;font-size:1.15em;color:#003E8C">${total_usd:,.2f} USD</td>
        </tr></tfoot></table>
      {f'<p style="margin-top:14px"><b>Notas:</b> {notas}</p>' if notas else ''}
      <p style="margin-top:20px;color:#666;font-size:.83em;border-top:1px solid #eee;padding-top:10px">
        Pedido recibido en order@exportharet.com | Export Haret \u00a9 2026</p>
    </div>'''
def build_order_pdf(ped):
    """Genera un PDF albaran del pedido con reportlab. Retorna bytes del PDF."""
    buf = io.BytesIO()
    pid = ped.get('id','')
    fecha = ped.get('fecha','')[:10]
    estado = ped.get('estado','Recibido')
    nombre = ped.get('client_name','')
    email_c = ped.get('client_email','')
    empresa = ped.get('empresa','')
    telefono = ped.get('telefono','')
    pais = ped.get('pais','')
    tipo = ped.get('tipo_precio','FOB')
    destino = ped.get('destino','')
    total_usd = ped.get('total_usd', 0)
    notas = ped.get('notas','')
    moneda_dest = ped.get('moneda_dest', 'USD')
    flete_usd_caja = ped.get('flete_usd_caja', 0.0)
    tasa_cambio = ped.get('tasa_cambio', 1.0)
    total_moneda_dest = ped.get('total_moneda_dest', total_usd)
    sym_dest = MONEDA_SIMBOLO.get(moneda_dest, moneda_dest)

    if not REPORTLAB_OK:
        # Fallback: devolver HTML como bytes
        return build_order_html(ped).encode('utf-8'), 'text/html', '.html'

    doc = SimpleDocTemplate(buf, pagesize=A4,
        rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Colores corporativos
    AZUL = colors.HexColor('#003E8C')
    AZUL_LIGHT = colors.HexColor('#E8F0FA')
    GRIS = colors.HexColor('#666666')

    # --- Cabecera ---
    header_style = ParagraphStyle('header', fontSize=22, textColor=colors.white,
        fontName='Helvetica-Bold', spaceAfter=4, alignment=TA_LEFT)
    sub_style = ParagraphStyle('sub', fontSize=10, textColor=colors.HexColor('#CCDDFF'),
        fontName='Helvetica', alignment=TA_LEFT)

    # Logo en cabecera
    _logo_cell = Paragraph('<font color="white" size="20"><b>Export Haret</b></font><br/><font color="#CCDDFF" size="9">Sistema de Pedidos — Frutas Exóticas Premium</font>', styles['Normal'])
    try:
        from reportlab.platypus import Image as RLImage
        import os as _os
        if _os.path.exists('logo.png'):
            _img = RLImage('logo.png', width=4.5*cm, height=1.5*cm)
            _logo_cell = _img
    except Exception:
        pass
    header_data = [[
        _logo_cell,
        Paragraph(f'<font color="white" size="9"><b>ALBARÁN / ORDEN DE PEDIDO</b><br/>{pid}<br/>{fecha}</font>', styles['Normal'])
    ]]
    header_table = Table(header_data, colWidths=[10*cm, 7*cm])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), AZUL),
        ('PADDING', (0,0), (-1,-1), 12),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.4*cm))

    # --- Datos cliente + pedido ---
    info_data = [
        [Paragraph('<b>DATOS DEL CLIENTE</b>', styles['Normal']), Paragraph('<b>DETALLES DEL PEDIDO</b>', styles['Normal'])],
        [Paragraph(f'<b>Nombre:</b> {nombre}', styles['Normal']), Paragraph(f'<b>Nº Pedido:</b> {pid}', styles['Normal'])],
        [Paragraph(f'<b>Empresa:</b> {empresa or "-"}', styles['Normal']), Paragraph(f'<b>Fecha:</b> {fecha}', styles['Normal'])],
        [Paragraph(f'<b>Email:</b> {email_c}', styles['Normal']), Paragraph(f'<b>Estado:</b> {estado}', styles['Normal'])],
        [Paragraph(f'<b>Teléfono:</b> {telefono or "-"}', styles['Normal']), Paragraph(f'<b>País:</b> {pais or "-"}', styles['Normal'])],
        [Paragraph(f'<b>Incoterm:</b> {tipo}' + (f' | Flete: ${flete_usd_caja:.2f} USD/caja' if tipo=="CIF" and flete_usd_caja>0 else ''), styles['Normal']),
         Paragraph(f'<b>Destino:</b> {destino if tipo=="CIF" and destino else "FOB (en origen)"}<br/><font color="#888888" size="8">Embarcamos desde Quito/Guayaquil, Ecuador</font>', styles['Normal'])],
    ]
    info_table = Table(info_data, colWidths=[9*cm, 8*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), AZUL_LIGHT),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (-1,0), AZUL),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('FONTSIZE', (0,1), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8F9FA')]),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.4*cm))

    # --- Tabla de productos ---
    prod_title = Paragraph('<b>DETALLE DE PRODUCTOS</b>', ParagraphStyle('ptitle', fontSize=10, textColor=AZUL, fontName='Helvetica-Bold', spaceBefore=6))
    story.append(prod_title)
    story.append(Spacer(1, 0.2*cm))

    prod_header = ['Código', 'Producto', 'Cajas', 'Pallets', 'Precio/caja', 'Total USD']
    prod_rows = [prod_header]
    for item in ped.get('productos', []):
        prod_rows.append([
            item.get('codigo',''),
            item.get('producto',''),
            str(item.get('cajas',0)),
            str(item.get('pallets',0)),
            f'${item.get("precio_usd",0):.2f}',
            f'${item.get("total",0):,.2f}',
        ])
    # Total row
    prod_rows.append(['', '', '', '', Paragraph('<b>TOTAL:</b>', styles['Normal']), Paragraph(f'<b>${total_usd:,.2f} USD</b>', styles['Normal'])])

    col_widths = [2.2*cm, 5.8*cm, 1.8*cm, 1.8*cm, 2.4*cm, 3*cm]
    prod_table = Table(prod_rows, colWidths=col_widths, repeatRows=1)
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), AZUL),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'),
        ('ALIGN', (4,0), (-1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-2), 0.5, colors.HexColor('#DDDDDD')),
        ('ROWBACKGROUNDS', (0,1), (-1,-2), [colors.white, colors.HexColor('#F0F4FF')]),
        ('BACKGROUND', (0,-1), (-1,-1), AZUL_LIGHT),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('LINEABOVE', (0,-1), (-1,-1), 1.5, AZUL),
    ]))
    story.append(prod_table)
    story.append(Spacer(1, 0.4*cm))

    # --- Resumen Financiero ---
    _fin_rows = [
        [Paragraph('<b>RESUMEN FINANCIERO</b>', ParagraphStyle('fintit', fontSize=9, textColor=AZUL, fontName='Helvetica-Bold')), '', ''],
        [Paragraph('<b>Total USD (divisa comercial):</b>', styles['Normal']),
         Paragraph(f'<b>${total_usd:,.2f} USD</b>', styles['Normal']),
         Paragraph('Divisa de referencia comercial', ParagraphStyle('fin_note2', fontSize=8, textColor=colors.HexColor('#888888')))],
    ]
    if moneda_dest != 'USD':
        _fin_rows.append([
            Paragraph(f'<b>Total {moneda_dest} (referencia):</b>', styles['Normal']),
            Paragraph(f'<b>{sym_dest}{total_moneda_dest:,.2f} {moneda_dest}</b>', styles['Normal']),
            Paragraph(f'Cotización: 1 USD = {tasa_cambio:.4f} {moneda_dest}', ParagraphStyle('fin_note3', fontSize=8, textColor=colors.HexColor('#888888')))])
    if tipo == 'CIF' and flete_usd_caja > 0:
        _n_cajas = sum(int(p.get('cajas',0)) for p in ped.get('productos',[]))
        _total_flete = round(flete_usd_caja * _n_cajas, 2)
        _fin_rows.append([
            Paragraph('<b>Desglose flete CIF:</b>', styles['Normal']),
            Paragraph(f'${_total_flete:,.2f} USD ({_n_cajas} cajas x ${flete_usd_caja:.2f})', styles['Normal']),
            Paragraph('Incluido en precio CIF', ParagraphStyle('fin_note4', fontSize=8, textColor=colors.HexColor('#666666')))])
    _fin_table = Table(_fin_rows, colWidths=[5.5*cm, 4.5*cm, 7*cm])
    _fin_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), AZUL_LIGHT),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,0), (-1,0), AZUL),
        ('SPAN', (0,0), (-1,0)),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#DDDDDD')),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8F9FA')]),
        ('LINEBELOW', (0,-1), (-1,-1), 1.5, AZUL),
    ]))
    story.append(_fin_table)
    story.append(Spacer(1, 0.3*cm))
    # --- Notas ---
    if notas:
        story.append(Paragraph(f'<b>Notas:</b> {notas}', ParagraphStyle('notas', fontSize=9, textColor=GRIS, spaceBefore=4)))
        story.append(Spacer(1, 0.2*cm))

    # PATCH 24: Tabla de embalaje / packaging table
    story.append(Spacer(1, 0.4*cm))
    packing_title = Paragraph('<b>TABLA DE EMBALAJE ESTIMADA</b>', ParagraphStyle('ptitle2', fontSize=10, textColor=AZUL, fontName='Helvetica-Bold', spaceBefore=6))
    story.append(packing_title)
    story.append(Spacer(1, 0.2*cm))
    packing_header = ['Producto', 'Pallets', 'Cajas', 'Kg/Caja', 'Peso Total Est.', 'Cajas/Pallet']
    packing_rows = [packing_header]
    _total_weight = 0
    _total_pal_pk = 0
    _total_caj_pk = 0
    for _pk_item in ped.get('productos', []):
        _pk_cajas = int(_pk_item.get('cajas', 0))
        _pk_pallets = float(_pk_item.get('pallets', 0))
        _pk_name = _pk_item.get('producto', '')
        # Try to get kg_caja from product data
        _pk_kg = 0
        for _pp in get_data().get('products', []):
            if _pp.get('codigo','') == _pk_item.get('codigo',''):
                _pk_kg = float(_pp.get('kg_caja', 0) or 0)
                break
        _pk_weight = round(_pk_cajas * _pk_kg, 1) if _pk_kg else 0
        _pk_cxp = round(_pk_cajas / _pk_pallets, 0) if _pk_pallets > 0 else 0
        _total_weight += _pk_weight
        _total_pal_pk += _pk_pallets
        _total_caj_pk += _pk_cajas
        packing_rows.append([
            _pk_name,
            f'{_pk_pallets:.1f}',
            str(_pk_cajas),
            f'{_pk_kg:.1f} kg' if _pk_kg else '—',
            f'{_pk_weight:,.0f} kg' if _pk_weight else '—',
            str(int(_pk_cxp)) if _pk_cxp else '—',
        ])
    packing_rows.append(['', f'{_total_pal_pk:.1f}', str(_total_caj_pk), '', f'{_total_weight:,.0f} kg' if _total_weight else '—', ''])
    pk_col_widths = [5*cm, 2*cm, 2*cm, 2.5*cm, 3*cm, 2.5*cm]
    pk_table = Table(packing_rows, colWidths=pk_col_widths, repeatRows=1)
    pk_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), AZUL),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F5F5F5')]),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#DDEEFF')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BOX', (0, 0), (-1, -1), 0.5, AZUL),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#CCCCCC')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(pk_table)
    story.append(Spacer(1, 0.2*cm))
    pk_note = Paragraph('<i>* Pesos totales son estimados. El peso real puede variar ±5% según calibre y variedad. No incluye embalaje de pallet.</i>', ParagraphStyle('pknote', fontSize=7, textColor=GRIS))
    story.append(pk_note)
    story.append(Spacer(1, 0.3*cm))

    # --- Pie de pagina ---
    story.append(HRFlowable(width='100%', thickness=1, color=AZUL))
    story.append(Spacer(1, 0.2*cm))
    footer_style = ParagraphStyle('footer', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    story.append(Paragraph('Export Haret © 2026 | order@exportharet.com | Frutas Exóticas Premium de Ecuador', footer_style))
    story.append(Paragraph('Los precios USD son la divisa comercial. Precios en moneda destino son referenciales y sujetos a cotización.', ParagraphStyle('footer2', fontSize=7, textColor=colors.HexColor('#AAAAAA'), alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue(), 'application/pdf', '.pdf'

def get_descuento_volumen(pallets):
    """Retorna el descuento (0.0-0.15) según los pallets pedidos."""
    for t in TRAMOS_VOLUMEN:
        if t["min"] <= pallets <= t["max"]:
            return t["descuento"]
    return TRAMOS_VOLUMEN[-1]["descuento"]

def get_precio_con_volumen(codigo, destino, tipo_precio, data, pallets):
    """Precio base (FOB o CIF) con descuento por volumen aplicado."""
    if tipo_precio == "CIF" and destino:
        base = get_cif_price(codigo, destino, data)
    else:
        base = get_fob_price(codigo, data)
    # Descuento por tramo de volumen
    desc = get_descuento_volumen(pallets)
    # Descuento extra por producto si tiene tramos personalizados
    for p in data.get("products", []):
        if p.get("codigo") == codigo and p.get("tramos_precio"):
            for t in p["tramos_precio"]:
                if t.get("min", 0) <= pallets <= t.get("max", 9999):
                    desc = t.get("descuento", desc)
                    break
    return round(base * (1 - desc), 4)

def get_tramo_label(pallets):
    """Retorna la etiqueta del tramo de volumen actual."""
    for t in TRAMOS_VOLUMEN:
        if t["min"] <= pallets <= t["max"]:
            return t["label"]
    return TRAMOS_VOLUMEN[-1]["label"]

@st.cache_data(ttl=3600)
def get_exchange_rates():
    """Obtiene cotizaciones en tiempo real desde exchangerate-api.com (free tier)."""
    try:
        import urllib.request
        url = "https://open.er-api.com/v6/latest/USD"
        with urllib.request.urlopen(url, timeout=5) as r:
            rates_data = __import__("json").loads(r.read())
        if rates_data.get("result") == "success":
            return rates_data.get("rates", {})
    except Exception:
        pass
    return {"USD":1,"EUR":0.92,"GBP":0.79,"CHF":0.89,"AED":3.67,"CAD":1.36,"MXN":17.5,"BRL":4.97,"COP":3950}

@st.cache_data(ttl=3600)
def get_exchange_rates_meta():
    """Cotizaciones con metadatos: timestamp, fuente, live flag."""
    try:
        import urllib.request
        url = "https://open.er-api.com/v6/latest/USD"
        with urllib.request.urlopen(url, timeout=5) as r:
            rd = __import__("json").loads(r.read())
        if rd.get("result") == "success":
            ts_str = rd.get("time_last_update_utc", "")
            try:
                from datetime import datetime as _dt
                ts_dt = _dt.strptime(ts_str, "%a, %d %b %Y %H:%M:%S +0000")
                ts_fmt = ts_dt.strftime("%d/%m/%Y %H:%M UTC")
            except Exception:
                ts_fmt = ts_str[:16] if ts_str else datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC")
            return {"rates": rd.get("rates", {}), "ts": ts_fmt, "source": "open.er-api.com", "live": True}
    except Exception:
        pass
    ts_fmt = datetime.utcnow().strftime("%d/%m/%Y %H:%M UTC") + " (aprox.)"
    return {"rates": {"USD":1,"EUR":0.92,"GBP":0.79,"CHF":0.89,"AED":3.67,"CAD":1.36,"MXN":17.5,"BRL":4.97,"COP":3950}, "ts": ts_fmt, "source": "referencia", "live": False}

def convertir_precio(precio_usd, moneda):
    """Convierte precio USD a la moneda destino."""
    if moneda == "USD":
        return precio_usd
    rates = get_exchange_rates()
    rate = rates.get(moneda, 1)
    return round(precio_usd * rate, 4)

def log_email(destinatario, asunto, tipo_email):
    el = load_email_log()
    el.append({'id': f'EMAIL-{len(el)+1:05d}', 'destinatario': destinatario, 'asunto': asunto, 'tipo': tipo_email, 'fecha': datetime.now().isoformat(), 'estado': 'simulado'})
    save_email_log(el)

# ─── PORTAL PÚBLICO DE PEDIDOS ───────────────────────────────────────────────
def send_order_email(ped):
    """Envia el pedido por email a order@exportharet.com.
    Requiere en .streamlit/secrets.toml:
    [email]
    smtp_host = 'smtp.gmail.com'
    smtp_port = 587
    smtp_user = 'tu@gmail.com'
    smtp_pass = 'app_password'
    from_addr = 'tu@gmail.com'
    """
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    DEST = 'order@exportharet.com'
    pid = ped.get('id','')
    nombre = ped.get('client_name','')
    email_c = ped.get('client_email','')
    empresa = ped.get('empresa','')
    telefono = ped.get('telefono','')
    pais = ped.get('pais','')
    tipo = ped.get('tipo_precio','FOB')
    destino = ped.get('destino','')
    total_usd = ped.get('total_usd',0)
    fecha = ped.get('fecha','')[:10]
    notas = ped.get('notas','')
    rows_html = ''
    for item in ped.get('productos', []):
        rows_html += (f'<tr><td style="padding:6px 10px;border:1px solid #ddd">{item.get("codigo","")}</td>'
                      f'<td style="padding:6px 10px;border:1px solid #ddd">{item.get("producto","")}</td>'
                      f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:center">{item.get("cajas",0)}</td>'
                      f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:center">{item.get("pallets",0)}</td>'
                      f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:right">${item.get("precio_usd",0):.2f}</td>'
                      f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:bold">${item.get("total",0):,.2f}</td></tr>')
    dest_str = f'{tipo} \u2192 {destino}' if tipo == 'CIF' and destino else tipo
    _notas_html = f'<p><b>Notas:</b> {notas}</p>' if notas else ''
    html = (f'<html><body style="font-family:Arial,sans-serif;color:#333">'
            f'<div style="background:#003E8C;padding:16px 24px;border-radius:8px">'
            f'<h2 style="color:white;margin:0">\🚀 Export Haret \u2014 Nueva Orden Recibida</h2>'
            f'</div><div style="padding:16px 0">'
            f'<table style="width:100%;border-collapse:collapse;font-size:14px">'
            f'<tr><td style="padding:6px"><b>N\u00ba Pedido:</b></td><td>{pid}</td>'
            f'<td style="padding:6px"><b>Fecha:</b></td><td>{fecha}</td></tr>'
            f'<tr><td style="padding:6px"><b>Cliente:</b></td><td>{nombre}</td>'
            f'<td style="padding:6px"><b>Empresa:</b></td><td>{empresa or "-"}</td></tr>'
            f'<tr><td style="padding:6px"><b>Email:</b></td><td>{email_c}</td>'
            f'<td style="padding:6px"><b>Tel\u00e9fono:</b></td><td>{telefono or "-"}</td></tr>'
            f'<tr><td style="padding:6px"><b>Pa\u00eds:</b></td><td>{pais or "-"}</td>'
            f'<td style="padding:6px"><b>Destino:</b></td><td>{dest_str}</td></tr>'
            f'</table>'
            f'<h3 style="color:#003E8C;border-bottom:2px solid #003E8C;padding-bottom:6px">Productos</h3>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px">'
            f'<thead><tr style="background:#003E8C;color:white">'
            f'<th style="padding:8px">C\u00f3digo</th><th style="padding:8px">Producto</th>'
            f'<th style="padding:8px">Cajas</th><th style="padding:8px">Pallets</th>'
            f'<th style="padding:8px">Precio/caja</th><th style="padding:8px">Total</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>'
            f'<p style="text-align:right;font-size:16px;font-weight:bold;color:#003E8C">'
            f'TOTAL: ${total_usd:,.2f} USD</p>'
            f'{_notas_html}'
            f'</div><p style="color:#888;font-size:11px">Export Haret \u00a9 2026 | order@exportharet.com</p>'
            f'</body></html>')
    subject = f'\📦 Nuevo Pedido {pid} \u2014 {nombre} ({empresa or email_c}) | ${total_usd:,.2f} USD'
    sent = False
    error_msg = ''
    try:
        cfg = {}
        try:
            cfg = st.secrets.get('email', {})
        except Exception:
            cfg = {}
        smtp_host = cfg.get('smtp_host', '')
        smtp_port = int(cfg.get('smtp_port', 587))
        smtp_user = cfg.get('smtp_user', '')
        smtp_pass = cfg.get('smtp_pass', '')
        from_addr = cfg.get('from_addr', smtp_user) or smtp_user
        if smtp_host and smtp_user and smtp_pass:
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = from_addr
            msg['To'] = DEST
            msg['Reply-To'] = email_c
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            # PATCH 23: Attach PDF to email
            try:
                from email.mime.base import MIMEBase
                from email import encoders as _enc
                _pdf_bytes, _pdf_mime, _pdf_ext = build_order_pdf(ped)
                _pdf_part = MIMEBase('application', 'octet-stream')
                _pdf_part.set_payload(_pdf_bytes)
                _enc.encode_base64(_pdf_part)
                _pdf_part.add_header('Content-Disposition', f'attachment; filename="{pid}{_pdf_ext}"')
                msg.attach(_pdf_part)
            except Exception as _pe2:
                log_email(DEST, subject, f'pdf_attach_error:{str(_pe2)[:100]}')
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [DEST], msg.as_string())
            log_email(DEST, subject, 'smtp_enviado')
            sent = True
        else:
            _missing = []
            if not smtp_host: _missing.append('smtp_host')
            if not smtp_user: _missing.append('smtp_user')
            if not smtp_pass: _missing.append('smtp_pass')
            error_msg = f'SMTP no configurado. Faltan: {", ".join(_missing)}. Ir a Streamlit Cloud → App settings → Secrets y agregar [email] smtp_host / smtp_user / smtp_pass / smtp_port / from_addr'
            log_email(DEST, subject, f'smtp_sin_config: {error_msg}')
    except Exception as e:
        error_msg = str(e)[:200]
        log_email(DEST, subject, f'smtp_error:{error_msg}')
    # Siempre guardar en pending_emails.json para auditoria
    try:
        _pf = 'pending_emails.json'
        _pe = _load(_pf, [])
        _pe.append({'id': pid, 'fecha': datetime.now().isoformat(), 'destinatario': DEST,
                    'asunto': subject, 'cliente': nombre, 'email_cliente': email_c,
                    'total': total_usd, 'sent': sent, 'error': error_msg})
        _save(_pf, _pe)
    except Exception:
        pass

def render_portal_pedido():
    """Página pública para que los clientes hagan pedidos. No requiere login de staff."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    data = load_data()
    prods = [p for p in data.get('products', []) if p.get('activo', True)]
    dests = data.get('config', {}).get('destinos', {})

    # Header
    import os as _os2
    if _os2.path.exists('logo.png'):
        from PIL import Image as _Img2
        _logo2 = _Img2.open('logo.png')
        _ph1, _ph2, _ph3 = st.columns([1, 2, 1])
        with _ph2: st.image(_logo2, width=200)
        st.markdown('<div style="text-align:center;margin-bottom:16px"><p style="color:#666;margin:0">Sistema de Pedidos — Frutas Exóticas Premium | order@exportharet.com</p></div>',unsafe_allow_html=True)
    else:
        st.markdown('<div style="background:linear-gradient(135deg,#003E8C,#0066CC,#0099FF);padding:20px 30px;border-radius:12px;margin-bottom:24px;text-align:center"><h1 style="color:white;margin:0;font-size:1.8em">🚀 Export Haret</h1><p style="color:rgba(255,255,255,0.85);margin:4px 0 0">Sistema de Pedidos — Frutas Exóticas Premium</p></div>',unsafe_allow_html=True)
    if not prods:
        st.warning(_T['no_catalog'])
        return

    portal_clients = load_portal_clients()

    # Init session state for portal
    # -- Selector de idioma (con rerun al cambiar) --
    if 'portal_lang' not in st.session_state:
        st.session_state['portal_lang'] = 'es'
    # PATCH 5: Language selector as flag buttons
    _cur_lang = st.session_state.get('portal_lang', 'es')
    _lbtn_c1, _lbtn_c2, _lbtn_c3 = st.columns([8, 1, 1])
    with _lbtn_c2:
        _es_type = 'primary' if _cur_lang == 'es' else 'secondary'
        if st.button('🇪🇸', key='btn_lang_es', help='Español', use_container_width=True, type=_es_type):
            if _cur_lang != 'es':
                st.session_state['portal_lang'] = 'es'
                st.rerun()
    with _lbtn_c3:
        _en_type = 'primary' if _cur_lang == 'en' else 'secondary'
        if st.button('🇬🇧', key='btn_lang_en', help='English', use_container_width=True, type=_en_type):
            if _cur_lang != 'en':
                st.session_state['portal_lang'] = 'en'
                st.rerun()
    _T = LANG_TEXTS[st.session_state.portal_lang]

    for k, v in [('portal_email',''),('portal_registered',False),('portal_client_data',{}),('portal_carrito',[])]:
        if k not in st.session_state: st.session_state[k] = v

    # Pre-fill email from last confirmed order (persistence #17)
    if not st.session_state.get('portal_email') and st.session_state.get('_portal_last_confirmed_email'):
        st.session_state['portal_email'] = st.session_state['_portal_last_confirmed_email']
    # ── PASO 1: Identificación del cliente ────────────────────────────────────
    # Progress bar - steps indicator
    _step1_done = bool(st.session_state.get('portal_email',''))
    _step2_done = bool(st.session_state.get('portal_carrito',[]))
    _step_html = '''<div style="display:flex;align-items:center;gap:0;margin:0 0 18px 0;background:#f8faff;border-radius:10px;padding:10px 16px">
  <div style="flex:1;text-align:center">
    <div style="background:#003E8C;color:white;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85em">1</div>
    <div style="font-size:0.75em;color:#003E8C;font-weight:bold;margin-top:2px">Tus Datos</div>
  </div>
  <div style="flex:0.5;height:3px;background:#ccd9ee;border-radius:2px"></div>
  <div style="flex:1;text-align:center">
    <div style="background:#6c9fd4;color:white;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85em">2</div>
    <div style="font-size:0.75em;color:#6c9fd4;margin-top:2px">Precio & Destino</div>
  </div>
  <div style="flex:0.5;height:3px;background:#ccd9ee;border-radius:2px"></div>
  <div style="flex:1;text-align:center">
    <div style="background:#6c9fd4;color:white;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85em">3</div>
    <div style="font-size:0.75em;color:#6c9fd4;margin-top:2px">Productos</div>
  </div>
  <div style="flex:0.5;height:3px;background:#ccd9ee;border-radius:2px"></div>
  <div style="flex:1;text-align:center">
    <div style="background:#6c9fd4;color:white;border-radius:50%;width:28px;height:28px;display:inline-flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85em">4</div>
    <div style="font-size:0.75em;color:#6c9fd4;margin-top:2px">Confirmar</div>
  </div>
</div>'''
    st.markdown(_step_html, unsafe_allow_html=True)
    st.markdown(_T['step1'])
    email_input = st.text_input(_T['email_label'], placeholder=_T['email_ph'], key='portal_email_input', value=st.session_state.portal_email)

    client_data = {}
    is_registered = False
    show_register = False

    if email_input:
        st.session_state.portal_email = email_input
        if email_input in portal_clients:
            is_registered = True
            client_data = dict(portal_clients[email_input])
            if st.session_state.get('portal_last_email') != email_input:
                st.session_state['portal_nombre'] = client_data.get('nombre', '')
                st.session_state['portal_empresa'] = client_data.get('empresa', '')
                st.session_state['portal_telefono'] = client_data.get('telefono', '')
                st.session_state['portal_pais'] = client_data.get('pais', '')
                st.session_state['portal_last_email'] = email_input
            st.success(_T['welcome_back'].format(name=client_data.get('nombre',email_input)))
        else:
            if st.session_state.get('portal_last_email') != email_input:
                st.session_state['portal_last_email'] = email_input
                # Pre-rellenar nombre/empresa desde pedidos anteriores
                _prev_ords = [p for p in load_pedidos() if p.get('client_email','').lower() == email_input.lower()]
                if _prev_ords:
                    _last_ord = sorted(_prev_ords, key=lambda x: x.get('fecha',''))[-1]
                    if not st.session_state.get('portal_nombre'):
                        st.session_state['portal_nombre'] = _last_ord.get('client_name','')
                    if not st.session_state.get('portal_empresa'):
                        st.session_state['portal_empresa'] = _last_ord.get('client_empresa','')
            st.info(_T['not_registered'])
            show_register = True

    if email_input:
        _client_orders_all = [p for p in load_pedidos() if p.get('client_email','').lower() == email_input.lower()]
        _n_orders = len(_client_orders_all)
        tab_datos, tab_historial = st.tabs([_T['tab_datos'], _T['tab_pedidos'].format(n=_n_orders)])

        with tab_datos:
            c1, c2 = st.columns(2)
            nombre = c1.text_input(_T['nombre_label'], key='portal_nombre', value=st.session_state.get('portal_nombre',''))
            empresa = c2.text_input(_T['empresa_label'], key='portal_empresa', value=st.session_state.get('portal_empresa',''))
            c3, c4 = st.columns(2)
            telefono = c3.text_input(_T['telefono_label'], placeholder=_T['telefono_ph'], key='portal_telefono', value=st.session_state.get('portal_telefono',''))
            _paises_opts = ['Afghanistan','Albania','Algeria','Andorra','Angola','Argentina','Armenia','Australia','Austria','Azerbaijan','Bahrain','Bangladesh','Belarus','Belgium','Belize','Benin','Bolivia','Bosnia and Herzegovina','Botswana','Brazil','Bulgaria','Burkina Faso','Cambodia','Cameroon','Canada','Chile','China','Colombia','Congo','Costa Rica','Croatia','Cuba','Czech Republic','Denmark','Dominican Republic','Ecuador','Egypt','El Salvador','Estonia','Ethiopia','Finland','France','Georgia','Germany','Ghana','Greece','Guatemala','Haiti','Honduras','Hungary','India','Indonesia','Iran','Iraq','Ireland','Israel','Italy','Jamaica','Japan','Jordan','Kazakhstan','Kenya','Kuwait','Latvia','Lebanon','Libya','Lithuania','Luxembourg','Madagascar','Malaysia','Mali','Malta','Mexico','Moldova','Mongolia','Morocco','Mozambique','Myanmar','Netherlands','New Zealand','Nicaragua','Nigeria','Norway','Oman','Pakistan','Panama','Paraguay','Peru','Philippines','Poland','Portugal','Qatar','Romania','Russia','Rwanda','Saudi Arabia','Senegal','Serbia','Singapore','Slovakia','Slovenia','Somalia','South Africa','South Korea','Spain','Sri Lanka','Sudan','Sweden','Switzerland','Syria','Taiwan','Tanzania','Thailand','Tunisia','Turkey','Uganda','Ukraine','United Arab Emirates','United Kingdom','United States','Uruguay','Uzbekistan','Venezuela','Vietnam','Yemen','Zambia','Zimbabwe']
            _pais_cur = st.session_state.get('portal_pais','Spain')
            _pais_idx = _paises_opts.index(_pais_cur) if _pais_cur in _paises_opts else _paises_opts.index('Spain')
            pais = c4.selectbox(_T['pais_label'], options=_paises_opts, index=_pais_idx, key='portal_pais')
            if show_register:
                st.caption(_T['auto_register'])

        with tab_historial:
            if not _client_orders_all:
                st.info(_T['no_orders'])
            else:
                st.markdown(f'#### 📋 {_n_orders} Pedido(s) realizados')
                for op in sorted(_client_orders_all, key=lambda x: x.get('fecha',''), reverse=True):
                    op_id = op.get('id','')
                    op_fecha = op.get('fecha','')[:10]
                    op_estado = op.get('estado','Recibido')
                    op_total = op.get('total_usd',0)
                    op_tipo = op.get('tipo_precio','FOB')
                    op_dest = op.get('destino','')
                    op_icon = ESTADO_ICONS.get(op_estado, '📦')
                    _clr_map = {'Recibido':'#0066cc','Confirmado':'#28a745','Preparando':'#fd7e14','Enviado':'#6f42c1','Entregado':'#20c997','Cancelado':'#dc3545'}
                    _col = _clr_map.get(op_estado,'#666')
                    with st.expander(f'{op_icon} {op_id} | {op_fecha} | {op_tipo} | ${op_total:,.2f} USD', expanded=False):
                        sc1, sc2, sc3 = st.columns(3)
                        sc1.markdown('**Estado:**')
                        sc1.markdown(f'<span style="color:{_col};font-weight:bold">{op_icon} {op_estado}</span>', unsafe_allow_html=True)
                        sc2.markdown(f'**Tipo:** {op_tipo}')
                        sc2.markdown(f'**Destino:** {op_dest if op_tipo=="CIF" and op_dest else "FOB (desde Ecuador)"}')
                        sc3.markdown(f'**Fecha:** {op_fecha}')
                        sc3.markdown(f'**Total:** ${op_total:,.2f} USD')
                        op_hist = op.get('historial_estados', [])
                        if op_hist:
                            st.markdown('**📍 Seguimiento:**')
                            _pasos_tr = ['Recibido','Confirmado','Preparando','Enviado','Entregado']
                            _idx_act = _pasos_tr.index(op_estado) if op_estado in _pasos_tr else -1
                            _pc = st.columns(len(_pasos_tr))
                            for _pi, _pe in enumerate(_pasos_tr):
                                _ic = ESTADO_ICONS.get(_pe,'')
                                _is_active = _pi == _idx_act and op_estado != 'Cancelado'
                                _is_done = _pi < _idx_act and op_estado != 'Cancelado'
                                if _is_active:
                                    _pc[_pi].markdown(f'<div style="text-align:center;background:#003E8C;color:white;border-radius:8px;padding:5px 2px;font-size:0.75em"><b>{_ic}<br>{_pe}</b></div>', unsafe_allow_html=True)
                                elif _is_done:
                                    _pc[_pi].markdown(f'<div style="text-align:center;background:#d4edda;color:#155724;border-radius:8px;padding:5px 2px;font-size:0.75em">{_ic}<br>{_pe}</div>', unsafe_allow_html=True)
                                else:
                                    _pc[_pi].markdown(f'<div style="text-align:center;background:#f0f0f0;color:#aaa;border-radius:8px;padding:5px 2px;font-size:0.75em">{_ic}<br>{_pe}</div>', unsafe_allow_html=True)
                            st.markdown('')
                            with st.expander('📜 Historial completo', expanded=False):
                                for _h in reversed(op_hist):
                                    _h_ic = ESTADO_ICONS.get(_h.get('estado',''),'📜')
                                    _h_fe = _h.get('fecha','')[:16].replace('T',' ')
                                    _h_no = _h.get('nota','')
                                    _no_str = f' — {_h_no}' if _h_no else ''
                                    st.caption(f'{_h_ic} **{_h.get("estado","")}** • {_h_fe}{_no_str}')
                        if op.get('productos'):
                            st.markdown('**Productos:**')
                            for _pit in op.get('productos',[]):
                                st.caption(f'• {_pit.get("producto","")} — {_pit.get("cajas",0)} cj | {_pit.get("pallets",0):.2f} plt | ${_pit.get("total",0):,.2f}')
                        can_cancel = op_estado not in ['Cancelado','Entregado','Enviado']
                        # PATCH 17: Repetir pedido button
                        _rp_c1, _rp_c2, _rp_c3 = st.columns([1, 1, 3])
                        if _rp_c1.button(f'\U0001f501 Repetir', key=f'repeat_{op_id}', help='Cargar en carrito', use_container_width=True):
                            _repeat_prods = op.get('productos', [])
                            if _repeat_prods:
                                st.session_state.portal_carrito = []
                                _rep_data = load_data()
                                for _rp in _repeat_prods:
                                    _rp_cod = _rp.get('codigo','')
                                    _rp_cajas = int(_rp.get('cajas',0))
                                    _rp_pallets = float(_rp.get('pallets',0))
                                    _rp_unit = _rp.get('unidad','Pallets')
                                    _rp_prod = _rp.get('producto','')
                                    _rp_precio = float(_rp.get('precio_usd',0))
                                    _rp_total = float(_rp.get('total',0))
                                    if _rp_cajas > 0:
                                        st.session_state.portal_carrito.append({'codigo':_rp_cod,'producto':_rp_prod,'cajas':_rp_cajas,'pallets':_rp_pallets,'precio_usd':_rp_precio,'total':_rp_total,'unidad':_rp_unit})
                                        for _ri, _p2 in enumerate(_rep_data.get('products',[])):
                                            if _p2.get('codigo','') == _rp_cod:
                                                _rqv = _rp_pallets if _rp_unit=='Pallets' else _rp_cajas
                                                st.session_state[f'portal_qty_{_rp_cod}_{_ri}'] = int(_rqv)
                                                st.session_state[f'portal_unit_{_rp_cod}_{_ri}'] = _rp_unit
                                                break
                                st.success(f'\u2705 Pedido {op_id} cargado. Revisa y confirma.')
                                st.rerun()
                            else:
                                st.warning('Este pedido no tiene productos registrados.')
                        if can_cancel:
                            if _rp_c2.button(f'\ud83d\uddd1 Cancelar', key=f'cancel_{op_id}', type='secondary', use_container_width=True):
                                st.session_state[f'confirm_cancel_{op_id}'] = True
                        if st.session_state.get(f'confirm_cancel_{op_id}'):
                            st.warning(f'⚠️ ¿Confirmas la cancelación del pedido **{op_id}**? Se notificará a nuestro equipo.')
                            _cc1, _cc2, _ = st.columns([1,1,4])
                            if _cc1.button('✅ Sí, cancelar', key=f'do_cancel_{op_id}'):
                                _all_peds = load_pedidos()
                                for _tp in _all_peds:
                                    if _tp.get('id') == op_id:
                                        _tp['estado'] = 'Cancelado'
                                        _tp['historial_estados'] = _tp.get('historial_estados',[]) + [{'estado':'Cancelado','fecha':datetime.now().isoformat(),'usuario':email_input,'nota':'Cancelado por cliente via portal'}]
                                        break
                                save_pedidos(_all_peds)
                                log_email('order@exportharet.com', f'CANCELACION {op_id} solicitada por {email_input}', 'cancelacion_cliente')
                                st.session_state[f'confirm_cancel_{op_id}'] = False
                                st.cache_data.clear()
                                st.success(f'✅ Pedido {op_id} cancelado. Notificación enviada a order@exportharet.com')
                                st.rerun()
                            if _cc2.button('❌ No', key=f'no_cancel_{op_id}'):
                                st.session_state[f'confirm_cancel_{op_id}'] = False
                                st.rerun()
        st.markdown('---')
    else:
        nombre = empresa = telefono = pais = ''
        st.info(_T['enter_email'])
        return
    # ── PASO 2: Tipo de precio + Destino ─────────────────────────────────────
    st.markdown(_T['step2'])
    t1, t2 = st.columns([1, 2])
    tipo_precio = t1.radio(_T['price_type_label'], ['FOB', 'CIF'], key='portal_tipo', horizontal=True,
        help=_T['price_type_help'])
    destino = ''
    dest_flete = 0.0
    if tipo_precio == 'CIF':
        dest_opts = list(dests.keys()) if dests else []
        if not dest_opts:
            t2.warning(_T['no_dest'])
        else:
            destino = t2.selectbox(_T['dest_label'], dest_opts, key='portal_dest')
            dest_val = dests.get(destino, 0)
            dest_flete = float(dest_val) if isinstance(dest_val, (int, float)) else dest_val.get('factor', 0) if isinstance(dest_val, dict) else 0
            _puerto_orig = 'Quito/Guayaquil, Ecuador'
            t2.caption(_T['flete_caption'].format(flete=dest_flete, orig=_puerto_orig, dest=destino))
            t2.info(_T['cif_info'].format(dest=destino, orig=_puerto_orig))
    else:
        t2.info(_T['fob_info'])
        t2.caption(_T['fob_origin'])

    st.markdown('---')
    # ── PASO 3: Selección de Productos ───────────────────────────────
    st.markdown(_T['step3'])
    # Banner pedido mínimo
    _current_pallets = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
    # ── Indicador de volumen
    _desc_actual = get_descuento_volumen(max(_current_pallets, 1)) if _current_pallets >= 1 else 0.0
    _next_tramo = None
    _pallets_para_siguiente = 0
    for _t in TRAMOS_VOLUMEN:
        if _t['descuento'] > _desc_actual:
            _next_tramo = _t
            _pallets_para_siguiente = max(0, _t['min'] - _current_pallets)
            break
    # PATCH 9: Progress bar toward minimum order
    _min_order = 3
    _progress_pct = min(1.0, _current_pallets / _min_order)
    _progress_fill_pct = int(_progress_pct * 100)
    if _current_pallets == 0:
        _min_valido = False
        _progress_color = '#e0e0e0'
        _progress_text = _T.get('min_order_empty', '📋 Pedido mínimo: 3 pallets — Añade productos para comenzar')
        _progress_icon = '⚪'
    elif _current_pallets < _min_order:
        _min_valido = False
        _progress_color = '#f97316'
        _needed = _min_order - _current_pallets
        _progress_text = f'⚠️ {_current_pallets:.1f}/{_min_order} pallets — Faltan {_needed:.1f} pallets para el mínimo'
        _progress_icon = '🟡'
    else:
        _min_valido = True
        _progress_color = '#16a34a'
        _next_hint = ''
        if _next_tramo and _pallets_para_siguiente > 0:
            _next_hint = f' | Con {int(_next_tramo["min"])}+ pallets el precio baja aún más 🚀'
        _progress_text = f'✅ {_current_pallets:.1f}/{_min_order} pallets{_next_hint}'
        _progress_icon = '🟢'
    st.markdown(
        f'<div style="margin: 4px 0 2px 0; font-size:0.88rem">{_progress_icon} {_progress_text}</div>'
        f'<div style="height:8px;background:#e9ecef;border-radius:6px;margin-bottom:8px">'
        f'<div style="height:100%;width:{_progress_fill_pct}%;background:{_progress_color};border-radius:6px;transition:width 0.4s"></div>'
        f'</div>',
        unsafe_allow_html=True
    )
    # PATCH 2: Live mini-carrito summary
    _cart_total_usd = sum(i.get('total',0) for i in st.session_state.portal_carrito)
    _cart_total_pal = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
    _cart_total_caj = sum(i.get('cajas',0) for i in st.session_state.portal_carrito)
    _cart_items = len([i for i in st.session_state.portal_carrito if i.get('cajas',0) > 0])
    if _cart_items > 0:
        _cart_dest_mon = data.get('config',{}).get('destinos_moneda',{}).get(destino,'USD') if tipo_precio=='CIF' else 'USD'
        _cart_rate = get_exchange_rates().get(_cart_dest_mon, 1.0)
        _cart_sym = MONEDA_SIMBOLO.get(_cart_dest_mon, _cart_dest_mon)
        _cart_total_dest = round(_cart_total_usd * _cart_rate, 2) if _cart_dest_mon != 'USD' and _cart_rate != 1.0 else None
        _alt_total = f'  ~  {_cart_sym}{_cart_total_dest:,.2f} {_cart_dest_mon}' if _cart_total_dest else ''
        _s_prods = 's' if _cart_items != 1 else ''
        _cart_html = (
            f'<div style="background:#e8f0fe;border:1.5px solid #003E8C;border-radius:8px;padding:8px 14px;margin:6px 0;display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-weight:600;color:#003E8C">🛒 Carrito: {_cart_items} producto{_s_prods} | {_cart_total_pal:.1f} pal | {_cart_total_caj:,} cj</span>'
            f'<span style="font-weight:700;color:#003E8C;font-size:1.1em">💰 ${_cart_total_usd:,.2f} USD{_alt_total}</span>'
            f'</div>'
        )
        st.markdown(_cart_html, unsafe_allow_html=True)
    hc = st.columns([4, 2, 3, 2, 2])
    hc[0].markdown('**Producto**')
    hc[1].markdown('**Precio/cja**')
    hc[2].markdown('**Cantidad**')
    hc[3].markdown('**Unidad**')
    hc[4].markdown('**Cajas**')
    st.markdown('<hr style="margin:4px 0 6px;border-color:#e0e0e0">', unsafe_allow_html=True)

    # Reconstruir carrito basado en los valores actuales de los inputs
    _new_carrito = []
    for idx, p in enumerate(prods):
        cod = p.get('codigo','')
        nombre_prod = p.get('descripcion','') or p.get('producto','') or cod
        _grp_x = p.get('grupo','')
        _gi_x = data.get('config',{}).get('grupos',{}).get(_grp_x,{})
        cxp = int(_gi_x.get('cajas_pallet',p.get('cajas_pallet',160))) if isinstance(_gi_x,dict) else 160
        _kg_x = float(p.get('kg_caja',0) or 0)
        _total_pallets_now = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
        precio_u = get_precio_con_volumen(cod, destino, tipo_precio, data, max(_total_pallets_now, 1))
        _dv_x = data.get('config',{}).get('destinos',{}).get(destino,0)
        _fl_x = float(_dv_x.get('factor',_dv_x) if isinstance(_dv_x,dict) else _dv_x if isinstance(_dv_x,(int,float)) else 0)
        qty_key = f'portal_qty_{cod}_{idx}'
        unit_key = f'portal_unit_{cod}_{idx}'

        # Leer valor previo del carrito para pre-llenar
        _ex_item = next((x for x in st.session_state.portal_carrito if x.get('codigo') == cod), None)
        _ex_unit = _ex_item.get('unidad','Pallets') if _ex_item else 'Pallets'
        if _ex_item:
            if _ex_unit == 'Pallets':
                _ex_qty = int(_ex_item.get('pallets',0))
            else:
                _ex_qty = int(_ex_item.get('cajas',0))
        else:
            _ex_qty = 0

        gc = st.columns([4, 2, 3, 2, 2])
        # Col 0: Nombre + specs del producto
        _kg_lbl = f'{_kg_x:.1f} kg/caja'.replace('.',',') if _kg_x else ''
        gc[0].markdown(
            f'**{nombre_prod}**' + (f'  \n<small style="color:#888">{_kg_lbl}</small>' if _kg_lbl else ''),
            unsafe_allow_html=True
        )
        # Col 1: Precio por caja
        _mon_x = data.get('config',{}).get('destinos_moneda',{}).get(destino,'USD') if tipo_precio=='CIF' else 'USD'
        _rate_x = get_exchange_rates().get(_mon_x,1.0)
        _sym_x = MONEDA_SIMBOLO.get(_mon_x,_mon_x)
        _fob_x = get_fob_price(cod,data)
        # Precio segun volumen actual
        if _mon_x != 'USD' and tipo_precio == 'CIF' and _rate_x != 1.0:
            _lp_x = round(precio_u * _rate_x, 2)
            gc[1].markdown(f'<b style="color:#003E8C">{_sym_x}{_lp_x:.2f}</b>', unsafe_allow_html=True)
        else:
            gc[1].markdown(f'<b style="color:#003E8C">${precio_u:.2f}</b>', unsafe_allow_html=True)
        # Col 2: Cantidad con +/- nativo
        qty_val = gc[2].number_input(
            'Cantidad', min_value=0, value=_ex_qty, step=1,
            key=qty_key, label_visibility='collapsed'
        )
        # Col 3: Unidad
        _unit_opts = ['Pallets', 'Cajas']
        _unit_default = 0 if _ex_unit == 'Pallets' else 1
        unit_sel_raw = gc[3].selectbox(
            'Unidad', _unit_opts, index=_unit_default,
            key=unit_key, label_visibility='collapsed'
        )
        unit_sel = unit_sel_raw
        # Col 4: Cajas calculadas (solo informacion) — PATCH 8
        if qty_val > 0:
            if unit_sel == 'Pallets':
                _n_cajas = int(qty_val * cxp)
                _n_pallets = float(qty_val)
                _cajas_label = f'**{_n_cajas:,}** cj'
                _cajas_sub = f'<small style="color:#888">{int(qty_val)}p × {cxp}cj/p</small>'
            else:
                _n_cajas = int(qty_val)
                _n_pallets = round(_n_cajas / cxp, 2)
                _cajas_label = f'**{_n_cajas:,}** cj'
                _cajas_sub = f'<small style="color:#888">≈ {_n_pallets:.1f} pal</small>'
            gc[4].markdown(f'{_cajas_label}\n{_cajas_sub}', unsafe_allow_html=True)
            # Agregar al nuevo carrito
            _new_carrito.append({
                'codigo': cod, 'producto': nombre_prod,
                'cajas': _n_cajas, 'pallets': _n_pallets,
                'precio_usd': precio_u,
                'total': round(_n_cajas * precio_u, 2),
                'unidad': unit_sel,
                'fob_usd': _fob_x,
                'flete_usd': _fl_x,
                'descuento_vol': get_descuento_volumen(max(_total_pallets_now,1))
            })
        else:
            gc[4].markdown('<span style="color:#ccc;font-size:0.85rem">—</span>', unsafe_allow_html=True)

        st.markdown('<hr style="margin:2px 0 2px;border-color:#f0f0f0">', unsafe_allow_html=True)

    # Sincronizar carrito automáticamente
    if _new_carrito != st.session_state.portal_carrito:
        st.session_state.portal_carrito = _new_carrito
        st.rerun()
    # Carrito
    if st.session_state.portal_carrito:
        st.markdown('---')
        _tot_c = sum(i['total'] for i in st.session_state.portal_carrito)
        _plt_c = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
        _cj_c = sum(i.get('cajas',0) for i in st.session_state.portal_carrito)
        # Cotización en tiempo real
        _rates_meta = get_exchange_rates_meta()
        _rates_portal = _rates_meta['rates']
        _rate_ts = _rates_meta['ts']
        _rate_live = _rates_meta['live']
        _rate_src = _rates_meta['source']
        _eur_rate = _rates_portal.get('EUR', 0.92)
        # Moneda destino
        _moneda_dest = 'USD'
        if tipo_precio == 'CIF' and destino:
            _dv2 = data.get('config',{}).get('destinos',{}).get(destino,{})
            _moneda_dest = _dv2.get('moneda','USD') if isinstance(_dv2,dict) else 'USD'
        _dest_rate = _rates_portal.get(_moneda_dest, 1)
        _show_dest = _moneda_dest not in ('USD', 'EUR')
        # ── Tabla resumen ──
        st.markdown(
            '<div style="background:#f8faff;border:1px solid #ccd9ee;border-radius:10px;padding:14px 18px 10px;margin:8px 0"><b style="font-size:1.05em;color:#003E8C">🛒 Resumen del Pedido</b></div>',
            unsafe_allow_html=True
        )
        # Headers tabla
        _rh = st.columns([3, 1, 1, 1, 2, 2])
        _rh[0].markdown('**Producto**')
        _rh[1].markdown('**$/caja**')
        _rh[2].markdown('**Pallets**')
        _rh[3].markdown('**Cajas**')
        _rh[4].markdown('**Total USD**')
        _rh[5].markdown('**€ Total EUR**')
        st.markdown('<hr style="margin:3px 0 5px;border-color:#ddd">', unsafe_allow_html=True)
        # Filas por producto
        for _ci, _item in enumerate(st.session_state.portal_carrito):
            _item_eur = round(_item['total'] * _eur_rate, 2)
            _rc = st.columns([3, 1, 1, 1, 2, 2])
            _rc[0].markdown(f'**{_item["producto"]}**')
            _rc[1].markdown(f'${_item["precio_usd"]:.2f}')
            _rc[2].markdown(f'{_item["pallets"]:.2f}')
            _rc[3].markdown(f'{_item["cajas"]:,}')
            _rc[4].markdown(f'<b style="color:#003E8C">${_item["total"]:,.2f}</b>', unsafe_allow_html=True)
            _rc[5].markdown(f'<span style="color:#1a7a3c">€{_item_eur:,.2f}</span>', unsafe_allow_html=True)
        st.markdown('<hr style="margin:5px 0 8px;border-color:#003E8C">', unsafe_allow_html=True)
        # Fila TOTAL
        _tot_eur = round(_tot_c * _eur_rate, 2)
        _rt = st.columns([3, 1, 1, 1, 2, 2])
        _rt[0].markdown('**TOTAL**')
        _rt[1].markdown('')
        _rt[2].markdown(f'**{_plt_c:.2f}**')
        _rt[3].markdown(f'**{_cj_c:,}**')
        _rt[4].markdown(f'<b style="color:#003E8C;font-size:1.1em">${_tot_c:,.2f} USD</b>', unsafe_allow_html=True)
        _rt[5].markdown(f'<b style="color:#1a7a3c;font-size:1.1em">€{_tot_eur:,.2f}</b>', unsafe_allow_html=True)
        # Moneda destino adicional (si no es USD ni EUR)
        if _show_dest:
            _tot_dest = round(_tot_c * _dest_rate, 2)
            _sym_dest = MONEDA_SIMBOLO.get(_moneda_dest, _moneda_dest)
            st.markdown(
                f'<div style="background:#f0fff4;border:1px solid #c3e6cb;border-radius:6px;padding:8px 14px;margin:6px 0">💱 <b>Equiv. {_moneda_dest}</b> (ref.): <b style="color:#1a7a3c">{_sym_dest}{_tot_dest:,.2f} {_moneda_dest}</b> <small style="color:#888">1 USD = {_dest_rate:.4f} {_moneda_dest}</small></div>',
                unsafe_allow_html=True
            )
        # Nota tipo de precio y tasa EUR
        _live_lbl = '🟢 En vivo' if _rate_live else '⚪ Aprox.'
        st.markdown(
            f'<div style="margin:6px 0;padding:5px 0"><small style="color:#777">💱 1 USD = <b>€{_eur_rate:.4f} EUR</b> — {_live_lbl} | Fuente: {_rate_src} | Actualizado: {_rate_ts}</small><br><small style="color:#999"><i>Precios en EUR son de referencia. La transacción se realiza en USD.</i></small></div>',
            unsafe_allow_html=True
        )
        if tipo_precio == 'FOB':
            st.caption(_T['cart_fob'])
        if st.button(_T['clear_cart'], key='portal_vaciar', use_container_width=False):
            st.session_state.portal_carrito = []
            st.rerun()
    st.markdown('---')

    if st.session_state.portal_carrito:
            # ── PASO 4: Confirmar y Enviar Pedido ────────────────────────────────────
        st.markdown(_T['step4'])
        notas = st.text_area('📝 Notas / instrucciones especiales', placeholder='Ej: Entrega en almacén X, condiciones especiales...', key='portal_notas')

        TOPT=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de cr\xe9dito (LC)','Pago a 30 d\xedas','Pago a 60 d\xedas','Otro']
        p_term=st.selectbox('\📋 T\xe9rminos de pago (opcional)',TOPT,key='p_term')
        # PATCH 19: Full order summary before confirm
        if st.session_state.portal_carrito and email_input and nombre:
            tot_final = sum(i['total'] for i in st.session_state.portal_carrito)
            _tot_pal_fin = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
            _tot_caj_fin = sum(i.get('cajas',0) for i in st.session_state.portal_carrito)
            tipo_str = tipo_precio + (f' → {destino}' if tipo_precio == 'CIF' and destino else '')
            # Destination currency
            _fin_mon = data.get('config',{}).get('destinos_moneda',{}).get(destino,'USD') if tipo_precio=='CIF' else 'USD'
            _fin_rate = get_exchange_rates().get(_fin_mon, 1.0)
            _fin_sym = MONEDA_SIMBOLO.get(_fin_mon, _fin_mon)
            _fin_dest_total = round(tot_final * _fin_rate, 2) if _fin_mon != 'USD' and _fin_rate != 1.0 else None
            _fin_alt = f'<br><span style="font-size:0.88em;color:#555">≈ {_fin_sym}{_fin_dest_total:,.2f} {_fin_mon}</span>' if _fin_dest_total else ''
            # Build product table rows
            _prod_rows_html = ''
            for _pfi in st.session_state.portal_carrito:
                if _pfi.get('cajas', 0) > 0:
                    _prod_rows_html += (
                        f'<tr><td style="padding:3px 8px">{_pfi.get("codigo","")}</td>'
                        f'<td style="padding:3px 8px">{_pfi.get("producto","")}</td>'
                        f'<td style="padding:3px 8px;text-align:center">{int(_pfi.get("pallets",0)):.0f} pal / {int(_pfi.get("cajas",0))} cj</td>'
                        f'<td style="padding:3px 8px;text-align:right">${_pfi.get("precio_usd",0):.2f}</td>'
                        f'<td style="padding:3px 8px;text-align:right;font-weight:600">${_pfi.get("total",0):,.2f}</td></tr>'
                    )
            st.markdown(
                f'<div style="background:#f0f7ff;border:2px solid #003E8C;border-radius:10px;padding:16px 20px;margin:10px 0">'
                f'<h4 style="margin:0 0 10px 0;color:#003E8C">📝 Resumen del Pedido</h4>'
                f'<p style="margin:2px 0"><b>Cliente:</b> {nombre} ({email_input})</p>'
                f'<p style="margin:2px 0"><b>Empresa:</b> {empresa or "N/A"} &nbsp;|&nbsp; <b>País:</b> {pais or "N/A"}</p>'
                f'<p style="margin:2px 0"><b>Modalidad:</b> {tipo_str} &nbsp;|&nbsp; <b>T. pago:</b> {p_term or "Por confirmar"}</p>'
                f'<table style="width:100%;border-collapse:collapse;margin:10px 0;font-size:0.9em">'
                f'<thead><tr style="background:#003E8C;color:white">'
                f'<th style="padding:4px 8px;text-align:left">Cód</th>'
                f'<th style="padding:4px 8px;text-align:left">Producto</th>'
                f'<th style="padding:4px 8px;text-align:center">Cantidad</th>'
                f'<th style="padding:4px 8px;text-align:right">$/cja</th>'
                f'<th style="padding:4px 8px;text-align:right">Total USD</th></tr></thead>'
                f'<tbody>{_prod_rows_html}</tbody>'
                f'<tfoot><tr style="background:#e8f0fe"><td colspan="3" style="padding:5px 8px;font-weight:700">TOTAL: {_tot_pal_fin:.1f} pallets | {_tot_caj_fin:,} cajas</td>'
                f'<td></td><td style="padding:5px 8px;text-align:right;font-weight:700;font-size:1.05em"><b>${tot_final:,.2f} USD</b>{_fin_alt}</td></tr></tfoot>'
                f'</table>'
                f'</div>',
                unsafe_allow_html=True
            )

        btn_guardar = st.button(_T['confirm_btn'], type='primary', use_container_width=True, key='portal_guardar')

        if btn_guardar:
            if not email_input:
                st.error(_T['err_email'])
            elif not nombre:
                st.error(_T['err_nombre'])
            elif not st.session_state.portal_carrito:
                st.error(_T['err_cart'])
            elif tipo_precio == 'CIF' and not destino:
                st.error(_T['err_destino'])
            else:
                _tod_p=load_pedidos()
                _yn_p=datetime.now().strftime('%Y')
                _pc_p=[p for p in _tod_p if p.get('id','').startswith(f'PED-{_yn_p}')]
                pid=f'PED-{_yn_p}-{len(_pc_p)+1:04d}'
                tot = sum(i['total'] for i in st.session_state.portal_carrito)
                ped = {
                    'id': pid,
                    'client_email': email_input,
                    'client_name': nombre,
                    'empresa': empresa,
                    'telefono': telefono,
                    'pais': pais,
                    'tipo_precio': tipo_precio,
                    'destino': destino if tipo_precio == 'CIF' else 'FOB',
                    'moneda': 'USD',
            'moneda_dest': _moneda_dest,
            'flete_usd_caja': dest_flete if tipo_precio == 'CIF' else 0.0,
            'tasa_cambio': round(_rates_portal.get(_moneda_dest, 1.0), 4),
            'total_moneda_dest': round(round(tot, 2) * _rates_portal.get(_moneda_dest, 1.0), 2),
                    'productos': list(st.session_state.portal_carrito),
                    'total_usd': round(tot, 2),
                    'estado': 'Recibido',
                    'fecha': datetime.now().isoformat(),
                    'notas':notas,'terminos_pago':p_term,'historial_estados': [{'estado': 'Recibido', 'fecha': datetime.now().isoformat(), 'usuario': 'portal'}],
                    'creado_por': 'portal',
                }
                # Guardar pedido
                todos = load_pedidos()
                todos.append(ped)
                save_pedidos(todos)
                # Registrar / actualizar cliente en portal
                portal_clients[email_input] = {
                    'nombre': nombre, 'empresa': empresa, 'telefono': telefono,
                    'pais': pais, 'email': email_input,
                    'fecha_registro': portal_clients.get(email_input, {}).get('fecha_registro', datetime.now().isoformat()),
                    'pedidos': portal_clients.get(email_input, {}).get('pedidos', []) + [pid],
                }
                save_portal_clients(portal_clients)
                # Log email y envio real a order@exportharet.com
                log_email(email_input, f'Confirmación pedido {pid}', 'portal_cliente')
                send_order_email(ped)
                st.cache_data.clear()

                # Guardar pedido en session para acciones post-guardado
                st.session_state['ultimo_pedido'] = ped
                st.session_state.portal_carrito = []
                st.success(_T['order_confirmed'].format(pid=pid))
                st.info(f"📧 Tu pedido ha sido enviado a **order@exportharet.com** para su confirmación. Nuestro equipo te contactará en 24-48h. Sigue el estado en la pestaña **Mis Pedidos** ↑")

    # ── Acciones post-pedido ─────────────────────────────────────────────────
    if st.session_state.get('ultimo_pedido'):
        ped_saved = st.session_state['ultimo_pedido']
        pid_saved = ped_saved.get('id','')
        st.markdown('---')
        st.markdown(f'#### ✅ Pedido **{pid_saved}** guardado')
        pdf_bytes, pdf_mime, pdf_ext = build_order_pdf(ped_saved)
        # Acciones en columnas
        ac1, ac2, ac3 = st.columns(3)
        # Descargar PDF albarán
        ac1.download_button(
            label=_T['download_pdf'],
            data=pdf_bytes,
            file_name=f'{pid_saved}{pdf_ext}',
            mime=pdf_mime,
            use_container_width=True,
            key='dl_pedido'
        )
        # WhatsApp
        tot_wa = ped_saved.get('total_usd', 0)
        _prods_str = ', '.join([str(i.get('cajas','')) + ' cajas ' + str(i.get('producto','')) for i in ped_saved.get('productos',[])])
        _tipo_wa = ped_saved.get('tipo_precio', '')
        _dest_wa = ped_saved.get('destino', '')
        wa_text = f'Pedido {pid_saved} Export Haret | ${tot_wa:,.2f} USD | {_tipo_wa} {_dest_wa} | {_prods_str}'
        wa_encoded = wa_text.replace(' ', '%20').replace('\n', '%0A')
        wa_url = f'https://wa.me/34641076116?text={wa_encoded}'
        ac2.link_button('💬 WhatsApp', wa_url, use_container_width=True)
        # Email
        subject = f'Pedido {pid_saved} — Export Haret'
        body = f'Mi pedido {pid_saved} por ${tot_wa:,.2f} USD ha sido confirmado.'
        mailto_url = f'mailto:order@exportharet.com?subject={subject.replace(" ","%20")}&body={body.replace(" ","%20")}'
        ac3.link_button('📧 Email', mailto_url, use_container_width=True)

        if st.button(_T['new_order_btn'], key='nuevo_portal'):
            st.session_state['ultimo_pedido'] = None
            st.rerun()

    st.markdown('---')
    st.markdown('---')
    with st.expander(_T['quote_expander'],expanded=False):
        st.markdown(_T['quote_intro'])
        _cc1,_cc2=st.columns(2)
        _cn=_cc1.text_input(_T['quote_name_lbl'],key='cnom',placeholder=_T['quote_name_ph'])
        _ce=_cc2.text_input(_T['email_label'],value=st.session_state.get('portal_email_input',''),key='ceml')
        _cd=_cc1.text_input('Destino',key='cdst',placeholder='ej: Madrid, España')
        _cplt=_cc2.number_input('Pallets aprox.',min_value=1,max_value=200,value=5,key='cplt')
        _cpro=st.text_area('Productos de interés',key='cpro',placeholder='ej: 3 pallets Granadilla...',height=70)
        _cmsg=st.text_area(_T['quote_msg_lbl'],key='cmsg',placeholder=_T['quote_msg_ph'],height=70)
        if st.button(_T['send_quote'], key='bcot', type='primary', use_container_width=True):
            if not _ce or not _cpro: st.error('Completa email y productos de interés')
            else:
                _cy=datetime.now().strftime('%Y');_cpv=[p for p in load_pedidos() if p.get('id','').startswith(f'COT-{_cy}')]
                _cid=f'COT-{_cy}-{len(_cpv)+1:04d}'
                _cp={'id':_cid,'tipo':'cotizacion_especial','client_name':_cn,'client_email':_ce,'destino':_cd,'pallets_aprox':_cplt,'productos_interes':_cpro,'mensaje':_cmsg,'estado':'Pendiente revisión','fecha':datetime.now().isoformat(),'total_usd':0,'productos':[],'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':'portal'}]}
                _ct=load_pedidos();_ct.append(_cp);save_pedidos(_ct);send_order_email(_cp)
                st.success(f'✅ Solicitud **{_cid}** enviada. Te contactaremos pronto.')
    st.markdown('<div style="text-align:center;color:#888"><small>Export Haret © 2026 | order@exportharet.com | Frutas Exóticas Premium</small></div>', unsafe_allow_html=True)

# ─── MAIN ────────────────────────────────────────────────────────────────────
def main():
    init_session()
    auto_load_excel()

    # Determine mode: 'portal' (public) or 'admin' (staff)
    # Support ?view=cliente URL param to always show portal
    if 'app_mode' not in st.session_state:
        _qp = st.query_params
        _view = _qp.get('view', '')
        if _view == 'admin':
            st.session_state.app_mode = 'admin'
        else:
            st.session_state.app_mode = 'portal'
    # Allow switching to admin via URL even if session already set
    elif st.query_params.get('view', '') == 'admin' and st.session_state.app_mode == 'portal':
        st.session_state.app_mode = 'admin'
        st.rerun()

    # ── MODO PORTAL (PÚBLICO) ─────────────────────────────────────────────────
    if st.session_state.app_mode == 'portal':
        # Small admin access link in sidebar
        st.sidebar.markdown('### 🚀 Export Haret')
        st.sidebar.caption('Portal de Pedidos')
        st.sidebar.markdown('---')
        st.sidebar.markdown('<p style="text-align:center;margin:4px 0 8px"><a href="?view=admin" target="_self" style="color:#aaa;font-size:0.75em;text-decoration:none">🔒 Acceso administración</a></p>', unsafe_allow_html=True)
        st.sidebar.markdown('---')
        st.sidebar.caption('Export Haret © 2026 | order@exportharet.com')
        render_portal_pedido()
        return

    # ── MODO ADMIN (STAFF LOGIN REQUERIDO) ────────────────────────────────────
    if not st.session_state.logged_in:
        # Show back to portal button
        col_back, col_form = st.columns([1, 3])
        with col_back:
            if st.button('← Portal Clientes', key='go_portal'):
                st.session_state.app_mode = 'portal'
                st.query_params.clear()
                st.rerun()
        with col_form:
            login_page()
        return

    # Admin panel
    import os as _osa
    if _osa.path.exists('logo.png'):
        from PIL import Image as _ImgA
        _logoA = _ImgA.open('logo.png')
        _al1, _al2, _al3 = st.columns([2, 1, 2])
        with _al2: st.image(_logoA, width=160)
    _app_title = load_app_config().get("app_title", "🚀 EXPORT HARET — Panel de Administración")
    st.markdown(f'<div style="background:linear-gradient(90deg,#003E8C,#0066CC);padding:16px 24px;border-radius:8px;margin-bottom:20px;"><h2 style="color:white;margin:0">{_app_title}</h2></div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'# {_app_title}')
    st.sidebar.markdown(f'**{st.session_state.user_nombre}** | {st.session_state.user_rol}')
    st.sidebar.markdown('---')
    pedidos = load_pedidos()
    clients = load_clients()
    st.sidebar.metric('📦 Pedidos', len(pedidos))
    st.sidebar.metric('💵 Facturación', f"${sum(p.get('total_usd',0) for p in pedidos):,.0f}")
    st.sidebar.metric('👥 Clientes', len(clients))
    pending = len([p for p in pedidos if p.get('estado') in ['Recibido','Confirmado','Preparando']])
    st.sidebar.metric('⏳ En proceso', pending)
    st.sidebar.markdown('---')
    st.sidebar.markdown('---')
    if st.sidebar.button('🌐 Ver Portal Clientes', use_container_width=True, key='admin_go_portal'):
        st.session_state.app_mode = 'portal'
        st.session_state.logged_in = False
        st.query_params.clear()
        st.rerun()
    if st.sidebar.button('🚪 Cerrar Sesión', use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    st.sidebar.caption('Export Haret © 2026 | order@exportharet.com')

    tab1,tab2,tab3,tab4,tab5,tab6=st.tabs([
        '📊 Dashboard',
        '📄 Catálogo & Precios',
        '🛒 Hacer Pedido',
        '⚙️ Configuración',
        '📦 Pedidos',
        '👥 Clientes',
    ])
    with tab1: render_dashboard()
    with tab2: render_catalogo()
    with tab3: render_hacer_pedido()
    with tab4: render_configuracion()
    with tab5: render_gestion_pedidos()
    with tab6: render_clientes()
    st.markdown('---')
    st.markdown('<div style="text-align:center;color:#888;"><small>🚀 Export Haret © 2026 | Sistema Profesional de Gestión de Pedidos</small></div>',unsafe_allow_html=True)

if __name__=='__main__':
    main()
