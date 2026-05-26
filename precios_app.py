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
    initial_sidebar_state="expanded"
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
PEDIDOS_FILE = "pedidos_data.json"
CLIENTS_FILE = "clientes.json"
HIST_FILE    = "precio_historial.json"
EMAIL_FILE   = "email_log.json"
DATA_FILE    = "precios_data.json"

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
        st.caption('👤 admin@exportharet.com / admin123')
        st.caption('👤 ventas@exportharet.com / ventas123')

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

# ─── TAB DASHBOARD ─────────────────────────────────────────────────────
def render_dashboard():
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
    with st.expander('⏱ SLA de Procesos', expanded=False):
        _,ss=calc_sla(pedidos)
        s1,s2,s3,s4=st.columns(4)
        s1.metric('✅ Cumplimiento',f"{ss['pct']:.1f}%",'Meta:95%')
        s2.metric('⚠️ Críticos',ss['crit'])
        s3.metric('⏱ Prom.h',f"{ss['prom']:.1f}h")
        s4.metric('📊 Trans.',ss['tot'])
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
        df=pd.DataFrame([{'Código':p.get('codigo',''),'Producto':p.get('descripcion','') or p.get('producto',''),'Precio CIF':f"${p.get('precio_cif_usd',0):.2f}"} for p in data['products'][:10]])
        st.dataframe(df,use_container_width=True,hide_index=True)

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
    hp_term=ht1.selectbox('\U0001F4CB T\xe9rminos de pago',TOPH,key='hp_term')
    hp_ent=ht2.text_input('\U0001F4C5 Fecha entrega estimada',placeholder='ej: 2026-06-20',key='hp_ent')
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
            ped={'id':pid,'client_email':c_email,'client_name':c_name,'destino':destino,'moneda':moneda,'productos':list(st.session_state.carrito),'total_usd':round(tot,2),'estado':'Recibido','fecha':datetime.now().isoformat(),'notas':notas,'terminos_pago':hp_term,'fecha_entrega':hp_ent,'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email}],'creado_por':st.session_state.user_email}
            todos=load_pedidos(); todos.append(ped); save_pedidos(todos)
            if c_email not in clients: clients[c_email]={'nombre':c_name,'email':c_email,'fecha_registro':datetime.now().isoformat(),'pedidos_ids':[]}
            clients[c_email]['pedidos_ids']=clients[c_email].get('pedidos_ids',[])+[pid]
            save_clients(clients)
            el=load_email_log(); el.append({'id':f'EMAIL-{len(el)+1:05d}','destinatario':c_email,'asunto':f'Pedido {pid} recibido','tipo':'confirmacion','fecha':datetime.now().isoformat(),'estado':'simulado'}); save_email_log(el)
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

# ─── TAB GESTION PEDIDOS ───────────────────────────────────────────────
def render_gestion_pedidos():
    st.markdown('## 📦 Gestión de Pedidos')
    pedidos=load_pedidos()
    f1,f2,f3=st.columns(3)
    fe=f1.selectbox('Estado',['Todos']+ORDEN_ESTADOS,key='gp_e')
    fc=f2.text_input('Cliente/ID',key='gp_c')
    fd=f3.selectbox('Destino',['Todos']+sorted(set(p.get('destino','') for p in pedidos if p.get('destino'))),key='gp_d')
    filt=[p for p in pedidos if (fe=='Todos' or p.get('estado')==fe) and (not fc or fc.lower() in (p.get('client_name','')+p.get('id','')).lower()) and (fd=='Todos' or p.get('destino')==fd)]
    _tot_filt = sum(p.get('total_usd',0) for p in filt)
    st.info(f'📦 **{len(filt)} pedidos** filtrados | 💰 Total: $**{_tot_filt:,.2f}** USD')
    if filt:
        xb=exportar_excel(filt)
        if xb: st.download_button('📥 Excel',data=xb,file_name=f'pedidos_{date.today()}.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.markdown('---')
    for ped in sorted(filt,key=lambda x:x.get('fecha',''),reverse=True)[:50]:
        icon=ESTADO_ICONS.get(ped.get('estado',''),'📦')
        with st.expander(f"{icon} #{ped.get('id','').upper()} • {ped.get('client_name','N/A')} • {ped.get('destino','')} • ${ped.get('total_usd',0):,.2f}"):
            cl1,cl2,cl3=st.columns(3)
            cl1.markdown(f"**Cliente:** {ped.get('client_name','')}"); cl1.markdown(f"**Email:** {ped.get('client_email','')}")
            cl2.markdown(f"**Destino:** {ped.get('destino','')}"); cl2.markdown(f"**Fecha:** {ped.get('fecha','')[:10]}")
            cl3.markdown(f"**Total:** ${ped.get('total_usd',0):,.2f}"); cl3.markdown(f"**Estado:** {ped.get('estado','')}")
            if ped.get('productos'):
                st.dataframe(
                    pd.DataFrame(ped['productos'])[['codigo','producto','cajas','pallets','precio_usd','total']].rename(
                        columns={'codigo':'Código','producto':'Producto','cajas':'Cajas','pallets':'Pallets','precio_usd':'Precio USD','total':'Total USD'}
                    ),use_container_width=True,hide_index=True)
            if ped.get('notas'): st.markdown(f"**Notas:** {ped['notas']}")
            # PDF albarán del pedido
            if REPORTLAB_OK:
                with st.expander('\u2712\uFE0F Editar pedido',expanded=False):
                    ec1,ec2=st.columns(2)
                    new_nom_g=ec1.text_input('Nombre',value=ped.get('client_name',''),key=f'g_nom_{ped.get("id","")}')
                    new_eml_g=ec2.text_input('Email',value=ped.get('client_email',''),key=f'g_eml_{ped.get("id","")}')
                    ed1,ed2=st.columns(2)
                    new_dst_g=ed1.text_input('Destino',value=ped.get('destino',''),key=f'g_dst_{ped.get("id","")}')
                    new_not_g=ed2.text_input('Notas',value=ped.get('notas',''),key=f'g_not_{ped.get("id","")}')
                    et1,et2=st.columns(2)
                    TOPTG=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de cr\xe9dito (LC)','Pago a 30 d\xedas','Pago a 60 d\xedas','Otro']
                    cur_tg=ped.get('terminos_pago',''); t_ig=TOPTG.index(cur_tg) if cur_tg in TOPTG else 0
                    new_ter_g=et1.selectbox('T\xe9rminos',TOPTG,index=t_ig,key=f'g_ter_{ped.get("id","")}')
                    new_ent_g=et2.text_input('Fecha entrega',value=ped.get('fecha_entrega',''),placeholder='ej: 2026-06-20',key=f'g_ent_{ped.get("id","")}')
                    ep_rg=[{'Cod':i.get('codigo',''),'Producto':i.get('producto',''),'Cajas':int(i.get('cajas',0)),'Precio_USD':float(i.get('precio_usd',0))} for i in ped.get('productos',[])]
                    if ep_rg:
                        ep_eg=st.data_editor(pd.DataFrame(ep_rg),column_config={'Cod':st.column_config.TextColumn('Cod',disabled=True),'Producto':st.column_config.TextColumn('Prod',disabled=True),'Cajas':st.column_config.NumberColumn('Cajas',min_value=1,step=1),'Precio_USD':st.column_config.NumberColumn('$/cj',format='$%.4f')},use_container_width=True,num_rows='dynamic',key=f'g_ep_{ped.get("id","")}',hide_index=True)
                        if st.button('\U0001F4BE Guardar cambios',key=f'g_save_{ped.get("id","")}',type='primary'):
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
                            save_pedidos(all_p); st.toast('\u2705 Pedido actualizado',icon='\u2705'); st.rerun()
                hist_g=ped.get('historial_estados',[])
                if hist_g:
                    with st.expander('\U0001F4DC Historial',expanded=False):
                        for h in reversed(hist_g):
                            h_ic=ESTADO_ICONS.get(h.get('estado',''),'\U0001F4DC'); h_fe=h.get('fecha','')[:16].replace('T',' ')
                            h_no=h.get('nota',''); no_s=f' \u2014 {h_no}' if h_no else ''
                            st.caption(f"{h_ic} **{h.get('estado','')}** \u2022 {h_fe} \u2022 {h.get('usuario','')}{no_s}")
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

# ─── TAB CONFIGURACION ───────────────────────────────────────────────
def render_configuracion():
    st.markdown('## ⚙️ Configuración del Sistema')
    st.markdown('### 👤 Usuarios del Sistema')
    df_u=pd.DataFrame([{'Email':e,'Nombre':v['nombre'],'Rol':v['rol']} for e,v in USERS.items()])
    st.dataframe(df_u,use_container_width=True,hide_index=True)
    st.markdown('---')
    st.markdown('### 📧 Log de Emails')
    elog=load_email_log()
    if elog:
        df_e=pd.DataFrame(elog[-20:][::-1])
        st.dataframe(df_e[['id','destinatario','asunto','tipo','fecha','estado']].rename(columns={'id':'ID','destinatario':'Para','asunto':'Asunto','tipo':'Tipo','fecha':'Fecha','estado':'Estado'}),use_container_width=True,hide_index=True)
    else: st.info('Sin emails registrados')
    st.markdown('---')
    st.markdown('### 📧 Estado SMTP (order@exportharet.com)')
    try:
        _smtp_cfg = st.secrets.get('email', {})
        _smtp_host = _smtp_cfg.get('smtp_host', '')
        if _smtp_host:
            st.success(f'✅ SMTP activo: {_smtp_cfg.get("smtp_user","?")} → {_smtp_host}:{_smtp_cfg.get("smtp_port",587)} | Emails van a order@exportharet.com')
        else:
            st.warning('⚠️ SMTP no configurado — emails registrados solo en log local. Agregar en Streamlit Secrets: [email] smtp_host / smtp_user / smtp_pass')
    except:
        st.info('ℹ️ No se pudo leer secrets. Configura SMTP en Streamlit Cloud → App settings → Secrets.')
    st.markdown('---')
    st.markdown('### 🗃️ Archivos de Datos')
    for fname in [DATA_FILE,CLIENTS_FILE,PEDIDOS_FILE,HIST_FILE,EMAIL_FILE]:
        exists=os.path.exists(fname)
        st.markdown(f"{'✅' if exists else '❌'} `{fname}`")

# ─── TAB CLIENTES ──────────────────────────────────────────────────────
def render_clientes():
    st.markdown('## 👥 Clientes')
    clients=load_clients(); pedidos=load_pedidos()
    if not clients: st.info('No hay clientes. Se crean al hacer pedidos.'); return
    rows=[]
    for e,c in clients.items():
        seg=segmentar(e,clients)
        mp=[p for p in pedidos if p.get('client_email')==e]
        rows.append({'Nombre':c.get('nombre',''),'Email':e,'Segmento':seg['badge'],'Pedidos':len(mp),'Facturación':f"${sum(p.get('total_usd',0) for p in mp):,.2f}",'Descuento':f"{seg['descuento']*100:.0f}%",'Crédito':f"${seg['credito']:,.0f}"})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.markdown('---')
    sel=st.selectbox('Detalle de cliente',['']+ list(clients.keys()),key='cli_d')
    if sel:
        c=clients[sel]; seg=segmentar(sel,clients); mp=[p for p in pedidos if p.get('client_email')==sel]
        d1,d2=st.columns(2)
        d1.markdown(f"**Nombre:** {c.get('nombre','')}\n\n**Email:** {sel}\n\n**Segmento:** {seg['badge']}")
        d2.markdown(f"**Pedidos:** {len(mp)}\n\n**Facturación:** ${sum(p.get('total_usd',0) for p in mp):,.2f}\n\n**Descuento:** {seg['descuento']*100:.0f}%")
        if mp:
            st.dataframe(pd.DataFrame([{'ID':p.get('id',''),'Destino':p.get('destino',''),'Total':f"${p.get('total_usd',0):,.2f}",'Estado':p.get('estado',''),'Fecha':p.get('fecha','')[:10]} for p in sorted(mp,key=lambda x:x.get('fecha',''),reverse=True)]),use_container_width=True,hide_index=True)
    st.markdown("---")
    st.markdown("### \U0001F50D Ficha de Cliente")
    _cl_list = list(clients.keys())
    if _cl_list:
        _sel=st.selectbox('Seleccionar cliente',_cl_list,format_func=lambda e:f"{clients[e].get('nombre','')} ({e})",key='sel_cl')
        if _sel:
            _c=clients[_sel]; _seg=segmentar(_sel,clients); _mp=[p for p in pedidos if p.get('client_email')==_sel]
            col_f1,col_f2=st.columns([3,1])
            with col_f1:
                st.markdown(f"#### \U0001F464 {_c.get('nombre','')} {_seg['badge']}")
                fc1,fc2=st.columns(2)
                f_nom=fc1.text_input('Nombre',value=_c.get('nombre',''),key='f_nom')
                f_emp=fc2.text_input('Empresa',value=_c.get('empresa',''),key='f_emp')
                fc3,fc4=st.columns(2)
                f_tel=fc3.text_input('Tel\xe9fono/WhatsApp',value=_c.get('telefono',''),key='f_tel')
                f_pais=fc4.text_input('Pa\xeds',value=_c.get('pais',''),key='f_pais')
                TOPTC=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de cr\xe9dito (LC)','Pago a 30 d\xedas','Pago a 60 d\xedas','Otro']
                cur_tc=_c.get('terminos_habituales',''); tc_idx=TOPTC.index(cur_tc) if cur_tc in TOPTC else 0
                f_term=st.selectbox('T\xe9rminos habituales',TOPTC,index=tc_idx,key='f_term')
                f_seg=st.text_input('\U0001F4C5 Pr\xf3ximo seguimiento',value=_c.get('proximo_seguimiento',''),placeholder='ej: 2026-07-01',key='f_seg')
                f_notas=st.text_area('\U0001F4CB Notas internas (solo admin)',value=_c.get('notas_internas',''),height=90,key='f_notas',placeholder='Preferencias, condiciones especiales...')
                if st.button('\U0001F4BE Guardar ficha',type='primary',key='save_ficha_cl'):
                    clients[_sel].update({'nombre':f_nom,'empresa':f_emp,'telefono':f_tel,'pais':f_pais,'terminos_habituales':f_term,'proximo_seguimiento':f_seg,'notas_internas':f_notas})
                    save_clients(clients); st.toast('\u2705 Ficha guardada',icon='\u2705'); st.rerun()
            with col_f2:
                st.metric('Pedidos',len(_mp))
                st.metric('Facturaci\xf3n',f"${sum(p.get('total_usd',0) for p in _mp):,.2f}")
                st.metric('Descuento',f"{_seg['descuento']*100:.0f}%")
                if _c.get('proximo_seguimiento'): st.info(f"\U0001F4C5 {_c.get('proximo_seguimiento')}")
            if _mp:
                st.markdown('#### \U0001F4DC Historial de pedidos')
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
        <h1 style="margin:0;font-size:1.6em">\U0001F680 Export Haret</h1>
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

    header_data = [[
        Paragraph('<font color="white"><b>Export Haret</b></font><br/><font color="#CCDDFF" size="9">Sistema de Pedidos — Frutas Exóticas Premium</font>', styles['Normal']),
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
        [Paragraph(f'<b>Tipo Precio:</b> {tipo}', styles['Normal']), Paragraph(f'<b>Destino:</b> {destino if tipo=="CIF" else "FOB (origen)"}', styles['Normal'])],
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

    # --- Notas ---
    if notas:
        story.append(Paragraph(f'<b>Notas:</b> {notas}', ParagraphStyle('notas', fontSize=9, textColor=GRIS, spaceBefore=4)))
        story.append(Spacer(1, 0.2*cm))

    # --- Pie de pagina ---
    story.append(HRFlowable(width='100%', thickness=1, color=AZUL))
    story.append(Spacer(1, 0.2*cm))
    footer_style = ParagraphStyle('footer', fontSize=8, textColor=GRIS, alignment=TA_CENTER)
    story.append(Paragraph('Export Haret © 2026 | order@exportharet.com | Frutas Exóticas Premium', footer_style))

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
            rates = __import__("json").loads(r.read())
        if rates.get("result") == "success":
            return rates.get("rates", {})
    except Exception:
        pass
    # Fallback con tasas aproximadas si no hay internet
    return {"USD":1,"EUR":0.92,"GBP":0.79,"CHF":0.89,"AED":3.67,"CAD":1.36,"MXN":17.5,"BRL":4.97,"COP":3950}

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
    """Envia el pedido por email a order@exportharet.com usando SMTP configurado en st.secrets.
    Requiere en .streamlit/secrets.toml:
      [email]
      smtp_host = '...'
      smtp_port = 587
      smtp_user = '...'
      smtp_pass = '...'
      from_addr = 'noreply@exportharet.com'
    Si no está configurado, solo registra en log."""
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
    # Build HTML body
    rows_html = ''
    for item in ped.get('productos', []):
        rows_html += (f'<tr><td style="padding:6px 10px;border:1px solid #ddd">{item.get("codigo","")}</td>'
            f'<td style="padding:6px 10px;border:1px solid #ddd">{item.get("producto","")}</td>'
            f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:center">{item.get("cajas",0)}</td>'
            f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:center">{item.get("pallets",0)}</td>'
            f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:right">${item.get("precio_usd",0):.2f}</td>'
            f'<td style="padding:6px 10px;border:1px solid #ddd;text-align:right;font-weight:bold">${item.get("total",0):,.2f}</td></tr>')
    dest_str = f'{tipo} → {destino}' if tipo == 'CIF' and destino else tipo
    html = f'''<html><body style="font-family:Arial,sans-serif;color:#333">
<div style="background:#003E8C;padding:16px 24px;border-radius:8px">
  <h2 style="color:white;margin:0">🚀 Export Haret — Nueva Orden Recibida</h2>
</div>
<div style="padding:16px 0">
  <table style="width:100%;border-collapse:collapse;font-size:14px">
    <tr><td style="padding:6px"><b>Nº Pedido:</b></td><td>{pid}</td>
        <td style="padding:6px"><b>Fecha:</b></td><td>{fecha}</td></tr>
    <tr><td style="padding:6px"><b>Cliente:</b></td><td>{nombre}</td>
        <td style="padding:6px"><b>Empresa:</b></td><td>{empresa or "-"}</td></tr>
    <tr><td style="padding:6px"><b>Email:</b></td><td>{email_c}</td>
        <td style="padding:6px"><b>Teléfono:</b></td><td>{telefono or "-"}</td></tr>
    <tr><td style="padding:6px"><b>País:</b></td><td>{pais or "-"}</td>
        <td style="padding:6px"><b>Destino:</b></td><td>{dest_str}</td></tr>
  </table>
  <h3 style="color:#003E8C;border-bottom:2px solid #003E8C;padding-bottom:6px">Productos</h3>
  <table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="background:#003E8C;color:white">
      <th style="padding:8px">Código</th><th style="padding:8px">Producto</th>
      <th style="padding:8px">Cajas</th><th style="padding:8px">Pallets</th>
      <th style="padding:8px">Precio/caja</th><th style="padding:8px">Total</th>
    </tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="text-align:right;font-size:16px;font-weight:bold;color:#003E8C">
    TOTAL: ${total_usd:,.2f} USD</p>
  {f'<p><b>Notas:</b> {notas}</p>' if notas else ''}
</div>
<p style="color:#888;font-size:11px">Export Haret © 2026 | order@exportharet.com</p>
</body></html>'''
    subject = f'📦 Nuevo Pedido {pid} — {nombre} ({empresa or email_c}) | ${total_usd:,.2f} USD'
    # Try SMTP send
    try:
        cfg = st.secrets.get('email', {})
        smtp_host = cfg.get('smtp_host', '')
        smtp_port = int(cfg.get('smtp_port', 587))
        smtp_user = cfg.get('smtp_user', '')
        smtp_pass = cfg.get('smtp_pass', '')
        from_addr = cfg.get('from_addr', smtp_user)
        if smtp_host and smtp_user and smtp_pass:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_addr
            msg['To'] = DEST
            msg['Reply-To'] = email_c
            msg.attach(MIMEText(html, 'html', 'utf-8'))
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(from_addr, [DEST], msg.as_string())
            log_email(DEST, subject, 'smtp_enviado')
        else:
            log_email(DEST, subject, 'smtp_sin_config')
    except Exception as e:
        log_email(DEST, subject, f'smtp_error:{str(e)[:80]}')

def render_portal_pedido():
    """Página pública para que los clientes hagan pedidos. No requiere login de staff."""
    data = load_data()
    prods = [p for p in data.get('products', []) if p.get('activo', True)]
    dests = data.get('config', {}).get('destinos', {})

    # Header
    st.markdown('<div style="background:linear-gradient(135deg,#003E8C,#0066CC,#0099FF);padding:20px 30px;border-radius:12px;margin-bottom:24px;text-align:center"><h1 style="color:white;margin:0;font-size:1.8em">🚀 Export Haret</h1><p style="color:rgba(255,255,255,0.85);margin:4px 0 0">Sistema de Pedidos — Frutas Exóticas Premium</p></div>',unsafe_allow_html=True)

    if not prods:
        st.warning('⚠️ Catálogo no disponible. Contacte a order@exportharet.com')
        return

    portal_clients = load_portal_clients()

    # Init session state for portal
    for k, v in [('portal_email',''),('portal_registered',False),('portal_client_data',{}),('portal_carrito',[])]:
        if k not in st.session_state: st.session_state[k] = v

    # ── PASO 1: Identificación del cliente ────────────────────────────────────
    st.markdown('### 1️⃣ Tus Datos')
    col_email, col_btn = st.columns([3, 1])
    email_input = col_email.text_input('📧 Tu correo electrónico', placeholder='tu@empresa.com', key='portal_email_input', value=st.session_state.portal_email)

    client_data = {}
    is_registered = False
    show_register = False

    if email_input:
        st.session_state.portal_email = email_input
        if email_input in portal_clients:
            is_registered = True
            client_data = dict(portal_clients[email_input])
            # Auto-relleno: poblar session_state cuando se reconoce el cliente
            if st.session_state.get('portal_last_email') != email_input:
                st.session_state['portal_nombre'] = client_data.get('nombre', '')
                st.session_state['portal_empresa'] = client_data.get('empresa', '')
                st.session_state['portal_telefono'] = client_data.get('telefono', '')
                st.session_state['portal_pais'] = client_data.get('pais', '')
                st.session_state['portal_last_email'] = email_input
            st.success(f'✅ Bienvenido de vuelta, **{client_data.get("nombre",email_input)}**!')
        else:
            if st.session_state.get('portal_last_email') != email_input:
                st.session_state['portal_last_email'] = email_input
            st.info('📝 Correo no registrado — completa tus datos para continuar.')
            show_register = True

    # Campos del cliente (auto-relleno si ya está registrado, editables siempre)
    if email_input:
        c1, c2 = st.columns(2)
        nombre  = c1.text_input('👤 Nombre completo', key='portal_nombre')
        empresa = c2.text_input('🏢 Empresa', key='portal_empresa')
        c3, c4 = st.columns(2)
        telefono = c3.text_input('📱 Teléfono / WhatsApp', placeholder='+34 600 000 000', key='portal_telefono')
        pais    = c4.text_input('🌍 País', key='portal_pais')
        if show_register:
            st.caption('Al guardar el pedido, tu cuenta quedará registrada automáticamente.')
    else:
        nombre = empresa = telefono = pais = ''
        st.markdown('---')
        st.markdown('**Ingresa tu correo para continuar** 👆')
        return

    # ── HISTORIAL DE PEDIDOS DEL CLIENTE ─────────────────────────────────────
    if email_input and st.session_state.portal_email:
        client_orders = [p for p in load_pedidos() if p.get('client_email','').lower() == email_input.lower()]
        if client_orders:
            with st.expander(f'📋 Mis Pedidos ({len(client_orders)})', expanded=False):
                for op in sorted(client_orders, key=lambda x: x.get('fecha',''), reverse=True):
                    op_id = op.get('id','')
                    op_fecha = op.get('fecha','')[:10]
                    op_estado = op.get('estado','Recibido')
                    op_total = op.get('total_usd',0)
                    op_tipo = op.get('tipo_precio','FOB')
                    op_dest = op.get('destino','')
                    icon = ESTADO_ICONS.get(op_estado, '📦')
                    col_info, col_acc = st.columns([5, 1])
                    col_info.markdown(
                        f'**{op_id}** &nbsp;|&nbsp; {op_fecha} &nbsp;|&nbsp; {icon} {op_estado} &nbsp;|&nbsp; '
                        f'{op_tipo}{" → " + op_dest if op_tipo=="CIF" and op_dest else ""} &nbsp;|&nbsp; '
                        f'**${op_total:,.2f} USD**'
                    )
                    can_cancel = op_estado not in ['Cancelado','Entregado','Enviado']
                    if can_cancel:
                        if col_acc.button('🗑️', key=f'cancel_{op_id}', help='Solicitar cancelación'):
                            st.session_state[f'confirm_cancel_{op_id}'] = True
                    else:
                        col_acc.caption(op_estado)
                    if st.session_state.get(f'confirm_cancel_{op_id}'):
                        st.warning(f'⚠️ ¿Confirmas la cancelación del pedido **{op_id}**? Esta acción no se puede deshacer.')
                        cc1, cc2, _ = st.columns([1,1,4])
                        if cc1.button('✅ Sí, cancelar', key=f'do_cancel_{op_id}'):
                            todos_peds = load_pedidos()
                            for tp in todos_peds:
                                if tp.get('id') == op_id:
                                    tp['estado'] = 'Cancelado'
                                    tp['historial_estados'] = tp.get('historial_estados',[]) + [{'estado':'Cancelado','fecha':datetime.now().isoformat(),'usuario':email_input}]
                                    break
                            save_pedidos(todos_peds)
                            log_email('order@exportharet.com', f'CANCELACION pedido {op_id} solicitada por {email_input}', 'cancelacion_cliente')
                            st.session_state[f'confirm_cancel_{op_id}'] = False
                            st.cache_data.clear()
                            st.success(f'✅ Pedido {op_id} cancelado. Se notificó a order@exportharet.com')
                            st.rerun()
                        if cc2.button('❌ No', key=f'no_cancel_{op_id}'):
                            st.session_state[f'confirm_cancel_{op_id}'] = False
                            st.rerun()
            st.markdown('')
    st.markdown('---')

    # ── PASO 2: Tipo de precio + Destino ─────────────────────────────────────
    st.markdown('### 2️⃣ Tipo de Precio y Destino')
    t1, t2 = st.columns([1, 2])
    tipo_precio = t1.radio('💲 Tipo de precio', ['FOB', 'CIF'], key='portal_tipo', horizontal=True,
        help='FOB = Precio en origen (sin flete). CIF = Precio incluye flete al destino.')
    destino = ''
    dest_flete = 0.0
    if tipo_precio == 'CIF':
        dest_opts = list(dests.keys()) if dests else []
        if not dest_opts:
            t2.warning('No hay destinos configurados')
        else:
            destino = t2.selectbox('🌍 Destino', dest_opts, key='portal_dest')
            dest_val = dests.get(destino, 0)
            dest_flete = float(dest_val) if isinstance(dest_val, (int, float)) else dest_val.get('factor', 0) if isinstance(dest_val, dict) else 0
            t2.caption(f'Flete incluido: ${dest_flete:.2f} USD/caja hacia {destino}')
    else:
        t2.info('**FOB** — Precio en origen. El flete corre por cuenta del comprador.')

    st.markdown('---')
    # ── PASO 3: Selección de Productos ───────────────────────────
    st.markdown('### 3️⃣ Selecciona tus Productos')
    # Mostrar tramo de volumen actual
    _current_pallets = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
    if _current_pallets > 0:
        _tramo = get_tramo_label(_current_pallets)
        _disc = get_descuento_volumen(_current_pallets)
        if _disc > 0:
            st.success(f'📉 Descuento por volumen activo: **{_tramo}** — {_disc*100:.0f}% de descuento en todos los precios 🎉')
        else:
            st.info(f'📦 Carrito actual: **{_current_pallets:.1f} pallets** | Agrega más para activar descuentos de volumen')
    else:
        st.caption('💡 Descuentos por volumen: 3-5 pallets -5% | 6-9 pallets -10% | 10-19 pallets -12% | 20+ pallets -15%')
    st.markdown('Ingresa la cantidad para cada producto que deseas agregar al carrito:')

    # Cabecera de la grilla
    hc = st.columns([4, 2, 2, 2, 1])
    hc[0].markdown('**Producto**')
    hc[1].markdown('**Precio USD/caja**')
    hc[2].markdown('**Cantidad**')
    hc[3].markdown('**Unidad**')
    hc[4].markdown('**+**')
    st.markdown('<hr style="margin:4px 0 8px">', unsafe_allow_html=True)

    for idx, p in enumerate(prods):
        cod = p.get('codigo','')
        nombre_prod = p.get('descripcion','') or p.get('producto','') or cod
        cxp = int(p.get('cajas_pallet', 200) or 200)
        # Precio con descuento por volumen acumulado en carrito
        _total_pallets = sum(i.get('pallets',0) for i in st.session_state.portal_carrito)
        precio_u = get_precio_con_volumen(cod, destino, tipo_precio, data, max(_total_pallets, 1))

        gc = st.columns([4, 2, 2, 2, 1])
        _grp_x=p.get('grupo','')
        _gi_x=data.get('config',{}).get('grupos',{}).get(_grp_x,{})
        _cxp_x=int(_gi_x.get('cajas_pallet',p.get('cajas_pallet',160))) if isinstance(_gi_x,dict) else 160
        _kg_x=float(p.get('kg_caja',0) or 0)
        _sp_x=cod+(f' | {_kg_x}kg/cj' if _kg_x else '')+(f' | {_cxp_x}cj/plt' if _cxp_x else '')
        gc[0].markdown(f'**{nombre_prod}**  \n<small style="color:#888">{_sp_x}</small>',unsafe_allow_html=True)
        _disc = get_descuento_volumen(max(_total_pallets,1))
        _disc_txt = f' <span style="color:#28a745;font-size:0.8em">-{_disc*100:.0f}%</span>' if _disc>0 else ''
        _mon_x=data.get('config',{}).get('destinos_moneda',{}).get(destino,'USD') if tipo_precio=='CIF' else 'USD'
        _rate_x=get_exchange_rates().get(_mon_x,1.0)
        _sym_x=MONEDA_SIMBOLO.get(_mon_x,_mon_x)
        _fob_x=get_fob_price(cod,data)
        _dv_x=data.get('config',{}).get('destinos',{}).get(destino,0)
        _fl_x=float(_dv_x.get('factor',_dv_x) if isinstance(_dv_x,dict) else _dv_x if isinstance(_dv_x,(int,float)) else 0)
        _ds_x=get_descuento_volumen(max(_total_pallets,1))
        if _mon_x!='USD' and tipo_precio=='CIF' and _rate_x!=1.0:
            _lp_x=round(precio_u*_rate_x,4)
            _ph_x=f'<span style="color:#003E8C;font-weight:bold">{_sym_x}{_lp_x:.4f}</span><br><small style="color:#888">${precio_u:.4f} USD{_disc_txt}</small>'
        else:
            _ph_x=f'<span style="color:#0066CC;font-weight:bold">${precio_u:.4f}</span>{_disc_txt}'
        if tipo_precio=='CIF' and _fob_x>0 and _fl_x>0:
            _ph_x+=f'<br><small style="color:#aaa">FOB ${_fob_x:.3f}+Flete ${_fl_x:.3f}'+('-'+f'{_ds_x*100:.0f}%' if _ds_x>0 else '')+'</small>'
        gc[1].markdown(_ph_x,unsafe_allow_html=True)
        qty_key = f'portal_qty_{cod}_{idx}'
        unit_key = f'portal_unit_{cod}_{idx}'
        qty_val = gc[2].number_input('Cant', min_value=0, value=0, step=1, key=qty_key, label_visibility='collapsed')
        unit_sel_raw = gc[3].selectbox('Unidad', ['📦 Pallets', '📦 Cajas'], key=unit_key, label_visibility='collapsed')
        unit_sel = 'Pallets' if unit_sel_raw.endswith('Pallets') else 'Cajas'
        if gc[4].button('➕', key=f'portal_add_{cod}_{idx}', help=f'Agregar {nombre_prod}'):
            if qty_val > 0:
                # Convertir a cajas
                if unit_sel == 'Pallets':
                    cajas_add = int(qty_val * cxp)
                    pallets_add = float(qty_val)
                else:
                    cajas_add = int(qty_val)
                    pallets_add = round(cajas_add / cxp, 2)
                total_item = round(cajas_add * precio_u, 2)
                item = {'codigo':cod,'producto':nombre_prod,'cajas':cajas_add,'pallets':pallets_add,'precio_usd':precio_u,'total':total_item,'unidad':unit_sel,'fob_usd':get_fob_price(cod,data),'flete_usd':float(dests.get(destino,0) if isinstance(dests.get(destino,0),(int,float)) else dests.get(destino,{}).get('factor',0) if isinstance(dests.get(destino,{}),dict) else 0),'descuento_vol':get_descuento_volumen(max(_total_pallets,1))}
                ex = next((i for i, x in enumerate(st.session_state.portal_carrito) if x['codigo'] == cod), None)
                if ex is not None:
                    st.session_state.portal_carrito[ex]['cajas'] += cajas_add
                    new_pallets = round(st.session_state.portal_carrito[ex]['cajas'] / cxp, 2)
                    st.session_state.portal_carrito[ex]['pallets'] = new_pallets
                    st.session_state.portal_carrito[ex]['total'] = round(st.session_state.portal_carrito[ex]['cajas'] * precio_u, 2)
                else:
                    st.session_state.portal_carrito.append(item)
                st.toast(f'✅ {nombre_prod} agregado: {cajas_add:,} cajas ({pallets_add:.1f} pallets) — ${total_item:,.2f} USD', icon='✅')
                st.rerun()
            else:
                st.toast(f'Ingresa una cantidad mayor a 0 para {nombre_prod}', icon='⚠️')

    # Carrito
    if st.session_state.portal_carrito:
        st.markdown('---')
        n_items = len(st.session_state.portal_carrito)
        tot = sum(i['total'] for i in st.session_state.portal_carrito)
        st.markdown(
            f'#### 🛒 Mi Carrito '
            f'<span style="background:#003E8C;color:white;padding:2px 10px;border-radius:20px;font-size:0.9em">'
            f'{n_items} producto(s) — Total: ${tot:,.2f} USD</span>',
            unsafe_allow_html=True)
        # Cabecera tabla carrito
        ch = st.columns([4, 2, 2, 2, 1])
        for hdr, lbl in zip(ch, ['**Producto**','**Cajas**','**Pallets**','**Total USD**','']):
            hdr.markdown(lbl)
        to_remove = None
        for ci, item in enumerate(st.session_state.portal_carrito):
            cc = st.columns([4, 2, 2, 2, 1])
            cc[0].markdown(f'{item["producto"]}  \n<small style="color:#888">{item["codigo"]}</small>', unsafe_allow_html=True)
            cc[1].markdown(str(item['cajas']))
            cc[2].markdown(f'{item["pallets"]:.2f}')
            cc[3].markdown(f'<strong style="color:#003E8C">${item["total"]:,.2f}</strong>', unsafe_allow_html=True)
            if cc[4].button('✕', key=f'portal_rem_{ci}', help='Eliminar producto'):
                to_remove = ci
        if to_remove is not None:
            st.session_state.portal_carrito.pop(to_remove)
            st.rerun()
        m1, m2, m3 = st.columns(3)
        m1.metric('📦 Total Cajas', f"{sum(i['cajas'] for i in st.session_state.portal_carrito):,}")
        m2.metric('📍 Total Pallets', f"{sum(i['pallets'] for i in st.session_state.portal_carrito):.2f}")
        m3.metric('💰 Total', f'${tot:,.2f} USD')
        # Show currency info for CIF orders
    _rates_portal = get_exchange_rates()
    if tipo_precio == 'CIF' and destino:
        _dv = data.get('config',{}).get('destinos',{}).get(destino,{})
        _moneda = _dv.get('moneda','USD') if isinstance(_dv,dict) else 'USD'
        _rate = _rates_portal.get(_moneda, 1)
        _tot_conv = round(tot * _rate, 2)
        _sym = MONEDA_SIMBOLO.get(_moneda, '')
        st.caption(f'Precios CIF — Destino: {destino} | Moneda: {_moneda} | Total equiv.: {_sym}{_tot_conv:,.2f} {_moneda} (1 USD = {_rate:.4f} {_moneda})')
    else:
        st.caption('Precios FOB — El flete corre por cuenta del comprador')
        rem_col, _ = st.columns([1, 3])
        if rem_col.button('🗑️ Vaciar Carrito', key='portal_vaciar'):
            st.session_state.portal_carrito = []
            st.rerun()
        st.markdown('---')
    # ── PASO 4: Confirmar y Enviar Pedido ────────────────────────────────────
    st.markdown('### 4️⃣ Confirmar Pedido')
    notas = st.text_area('📝 Notas / instrucciones especiales', placeholder='Ej: Entrega en almacén X, condiciones especiales...', key='portal_notas')

    # Mostrar resumen antes de confirmar
    if st.session_state.portal_carrito and email_input and nombre:
        tot_final = sum(i['total'] for i in st.session_state.portal_carrito)
        tipo_str = tipo_precio + (f' → {destino}' if tipo_precio == 'CIF' and destino else '')
        st.markdown(f'''
<div style="background:#f0f7ff;border:1px solid #003E8C;border-radius:8px;padding:12px 18px;margin:8px 0">
📋 <b>Resumen del Pedido</b><br>
&bull; Cliente: <b>{nombre}</b> ({email_input})<br>
&bull; Productos: <b>{len(st.session_state.portal_carrito)}</b><br>
&bull; Modalidad: <b>{tipo_str}</b><br>
&bull; <span style="font-size:1.1em">💰 Total: <b style="color:#003E8C">${tot_final:,.2f} USD</b></span>
</div>''', unsafe_allow_html=True)

    pt1,pt2=st.columns(2)
    TOPT=['','Pago anticipado 100%','50% adelanto / 50% contra documentos','30% adelanto / 70% contra BL','Carta de cr\xe9dito (LC)','Pago a 30 d\xedas','Pago a 60 d\xedas','Otro']
    p_term=pt1.selectbox('\U0001F4CB T\xe9rminos de pago (opcional)',TOPT,key='p_term')
    p_nota2=pt2.text_area('\U0001F4DD Notas',placeholder='Instrucciones especiales...',key='p_nota2',height=80)
    btn_guardar = st.button('📤 CONFIRMAR Y ENVIAR PEDIDO', type='primary', use_container_width=True, key='portal_guardar')

    if btn_guardar:
        if not email_input:
            st.error('❌ Ingresa tu correo electrónico')
        elif not nombre:
            st.error('❌ Ingresa tu nombre completo')
        elif not st.session_state.portal_carrito:
            st.error('❌ Agrega al menos un producto al carrito')
        elif tipo_precio == 'CIF' and not destino:
            st.error('❌ Selecciona un destino para precio CIF')
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
                'productos': list(st.session_state.portal_carrito),
                'total_usd': round(tot, 2),
                'estado': 'Recibido',
                'fecha': datetime.now().isoformat(),
                'notas':notas,'notas_adicionales':p_nota2,'terminos_pago':p_term,'historial_estados': [{'estado': 'Recibido', 'fecha': datetime.now().isoformat(), 'usuario': 'portal'}],
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
            st.success(f'✅ **Pedido {pid} enviado a order@exportharet.com** — Te contactaremos a {email_input} para la confirmación.')

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
            label='⬇️ Descargar Albarán PDF',
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
        wa_url = f'https://wa.me/+1?text={wa_encoded}'
        ac2.link_button('💬 Compartir por WhatsApp', wa_url, use_container_width=True)
        # Email
        subject = f'Pedido {pid_saved} — Export Haret'
        body = f'Mi pedido {pid_saved} por ${tot_wa:,.2f} USD ha sido confirmado.'
        mailto_url = f'mailto:order@exportharet.com?subject={subject.replace(" ","%20")}&body={body.replace(" ","%20")}'
        ac3.link_button('📧 Enviar por Email', mailto_url, use_container_width=True)

        if st.button('🆕 Hacer otro pedido', key='nuevo_portal'):
            st.session_state['ultimo_pedido'] = None
            st.rerun()

    st.markdown('---')
    st.markdown('---')
    with st.expander('U0001F4AC Solicitar cotización especial',expanded=False):
        st.markdown('**¿Necesitas presupuesto personalizado?** Rellena el formulario y te contactaremos en 24-48h.')
        _cc1,_cc2=st.columns(2)
        _cn=_cc1.text_input('Tu nombre / empresa',key='cnom',placeholder='Nombre o empresa')
        _ce=_cc2.text_input('Tu email',value=st.session_state.get('portal_email_input',''),key='ceml')
        _cd=_cc1.text_input('Destino',key='cdst',placeholder='ej: Madrid, España')
        _cplt=_cc2.number_input('Pallets aprox.',min_value=1,max_value=200,value=5,key='cplt')
        _cpro=st.text_area('Productos de interés',key='cpro',placeholder='ej: 3 pallets Granadilla...',height=70)
        _cmsg=st.text_area('Mensaje adicional',key='cmsg',placeholder='Condiciones especiales...',height=70)
        if st.button('U0001F4E8 Enviar solicitud de cotización',key='bcot',type='primary',use_container_width=True):
            if not _ce or not _cpro: st.error('Completa email y productos de interés')
            else:
                _cy=datetime.now().strftime('%Y');_cpv=[p for p in load_pedidos() if p.get('id','').startswith(f'COT-{_cy}')]
                _cid=f'COT-{_cy}-{len(_cpv)+1:04d}'
                _cp={'id':_cid,'tipo':'cotizacion_especial','client_name':_cn,'client_email':_ce,'destino':_cd,'pallets_aprox':_cplt,'productos_interes':_cpro,'mensaje':_cmsg,'estado':'Pendiente revisión','fecha':datetime.now().isoformat(),'total_usd':0,'productos':[],'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':'portal'}]}
                _ct=load_pedidos();_ct.append(_cp);save_pedidos(_ct);send_order_email(_cp)
                st.success(f'✅ Solicitud **{_cid}** enviada. Te contactaremos pronto.')
    st.markdown('<div style="text-align:center;color:#888"><small>Export Haret © 2026 | order@exportharet.com | Frutas Exóticas Premium</small></div>', unsafe_allow_html=True)

# ─── MAIN ────────────────────────────────────────────────────────────────────
    # Solicitud cotizacion especial (#12)
    st.markdown("---")
    with st.expander('\U0001F4AC Solicitar Cotizaci\xf3n Especial', expanded=False):
        st.markdown('\U0001F4E7 Env\xedanos tu solicitud y te preparamos una cotizaci\xf3n a medida.')
        sq1,sq2=st.columns(2)
        sq_nom=sq1.text_input('Nombre/Empresa',key='sq_nom')
        sq_email=sq2.text_input('Email',key='sq_email')
        sq3,sq4=st.columns(2)
        sq_dest=sq3.text_input('Destino',key='sq_dest')
        sq_vol=sq4.text_input('Volumen estimado (pallets)',key='sq_vol')
        sq_prods=st.text_area('Productos de inter\xe9s',placeholder='ej: 10 pallets Granadilla + 5 pallets Pitahaya...',key='sq_prods',height=80)
        sq_tel=st.text_input('Tel\xe9fono/WhatsApp',key='sq_tel')
        if st.button('\U0001F680 Enviar Solicitud de Cotizaci\xf3n',type='primary',key='btn_solicitud',use_container_width=True):
            if sq_nom and sq_email:
                _sol={'id':f'SOL-{datetime.now().strftime("%Y%m%d-%H%M%S")}','client_name':sq_nom,'client_email':sq_email,'destino':sq_dest,'tipo_precio':'CIF','productos':[{'codigo':'SOL','producto':sq_prods,'cajas':0,'pallets':0,'precio_usd':0,'total':0}],'total_usd':0,'estado':'Recibido','notas':f'SOLICITUD COTIZACION - Vol:{sq_vol} - Tel:{sq_tel}','fecha':datetime.now().isoformat(),'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':'portal-solicitud'}],'creado_por':'portal-solicitud'}
                _tods=load_pedidos(); _tods.append(_sol); save_pedidos(_tods)
                log_email(sq_email,f'Solicitud cotizacion {sq_dest}','portal_solicitud')
                send_order_email(_sol)
                st.success(f'\u2705 Solicitud enviada a order@exportharet.com - Te contactaremos en 24h a {sq_email}')
            else:
                st.warning('Por favor completa nombre y email')
def main():
    init_session()
    auto_load_excel()

    # Determine mode: 'portal' (public) or 'admin' (staff)
    # Support ?view=cliente URL param to always show portal
    if 'app_mode' not in st.session_state:
        _qp = st.query_params
        if _qp.get('view', '') == 'cliente':
            st.session_state.app_mode = 'portal'
        else:
            st.session_state.app_mode = 'portal'

    # ── MODO PORTAL (PÚBLICO) ─────────────────────────────────────────────────
    if st.session_state.app_mode == 'portal':
        # Small admin access link in sidebar
        st.sidebar.markdown('### 🚀 Export Haret')
        st.sidebar.caption('Portal de Pedidos')
        st.sidebar.markdown('---')
        if st.sidebar.button('🔐 Acceso Administración', use_container_width=True, key='go_admin'):
            st.session_state.app_mode = 'admin'
            st.rerun()
        st.sidebar.caption('Export Haret © 2026')
        render_portal_pedido()
        return

    # ── MODO ADMIN (STAFF LOGIN REQUERIDO) ────────────────────────────────────
    if not st.session_state.logged_in:
        # Show back to portal button
        col_back, col_form = st.columns([1, 3])
        with col_back:
            if st.button('← Portal Clientes', key='go_portal'):
                st.session_state.app_mode = 'portal'
                st.rerun()
        with col_form:
            login_page()
        return

    # Admin panel
    st.markdown('<div style="background:linear-gradient(90deg,#003E8C,#0066CC);padding:16px 24px;border-radius:8px;margin-bottom:20px;"><h2 style="color:white;margin:0">🚀 EXPORT HARET — Panel de Administración</h2></div>', unsafe_allow_html=True)
    st.sidebar.markdown(f'# 🚀 Export Haret')
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
