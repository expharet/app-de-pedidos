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
    st.markdown('### ⏱ SLA')
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
        df=pd.DataFrame([{'Código':p.get('codigo',''),'Producto':p.get('descripcion',''),'Precio CIF':f"${p.get('precio_cif_usd',0):.2f}"} for p in data['products'][:10]])
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


def render_cotizacion():
    st.markdown('## 📄 Cotización - Gestión de Datos')
    data = load_data()
    prods = data.get('products', [])
    dests = data.get('config', {}).get('destinos', {})
    # Mostrar estado actual
    prods_con_precio = [p for p in prods if (p.get('precio_cif_usd', 0) or p.get('precio_compra', 0)) > 0]
    if prods_con_precio:
        st.success(f'✅ Datos cargados: **{len(prods_con_precio)} productos con precio** y **{len(dests)} destinos** listos para usar.')
    elif prods:
        st.warning(f'⚠️ {len(prods)} productos encontrados pero sin precios. Sube el archivo Excel para actualizar.')
    else:
        st.warning('⚠️ No hay datos cargados. Sube tu archivo Excel para importar productos y destinos.')
    st.info('📎 Sube tu archivo Cotizaciones.xlsx con las hojas: CONFIGURACION, TABLA PRECIOS, TODOS DESTINOS')
    uploaded = st.file_uploader('Actualizar archivo Excel (reemplaza los precios actuales)', type=['xlsx', 'xls'], key='xl_up')
    if uploaded:
        try:
            xl_bytes = uploaded.getvalue()
            with open('Cotizaciones.xlsx', 'wb') as f: f.write(xl_bytes)
            products, destinos_cfg = parse_excel_file(uploaded)
            prods_validos = [p for p in products if p.get('precio_cif_usd', 0) > 0]
            if not prods_validos:
                st.error('❌ No se encontraron precios válidos. Verifica que la hoja TABLA PRECIOS tenga datos en las filas 32-83.')
            else:
                nueva = load_data()
                nueva['products'] = products
                nueva['config']['destinos'] = destinos_cfg
                save_data(nueva)
                st.success(f'✅ {len(prods_validos)} productos actualizados con precios correctos.')
                st.rerun()
        except Exception as e:
            st.error(f'❌ Error procesando el archivo: {e}')
    data = load_data()
    prods = data.get('products', [])
    dests = data.get('config', {}).get('destinos', {})
    if prods:
        st.markdown('---')
        st.markdown(f'### 📋 Productos ({len(prods)})')
        df_prods = pd.DataFrame([{
            'Código': p.get('codigo', ''),
            'Descripción': p.get('descripcion', p.get('producto', '')),
            'Precio Compra USD': p.get('precio_cif_usd', 0) or p.get('precio_compra', 0),
            'Cajas/Pallet': p.get('cajas_pallet', 200),
        } for p in prods if p.get('activo', True)])
        st.dataframe(df_prods, use_container_width=True, hide_index=True)
    if dests:
        st.markdown(f'### 🌍 Destinos y Fletes ({len(dests)})')
        df_dests = pd.DataFrame([{
            'Destino': k,
            'Flete USD/caja': float(v) if isinstance(v, (int, float)) else v.get('factor', 0) if isinstance(v, dict) else 0
        } for k, v in dests.items()])
        st.dataframe(df_dests, use_container_width=True, hide_index=True)


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
        if seg: precio=round(precio*(1-seg['descuento']),2)
        cxp=pd_.get('cajas_pallet',200) or 200
        pallets=round(cajas/cxp,2)
        item={'codigo':cod,'producto':pd_.get('descripcion',''),'cajas':cajas,'pallets':pallets,'precio_usd':precio,'total':round(cajas*precio,2)}
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
    if st.button('📤 GUARDAR PEDIDO',type='primary',use_container_width=True):
        if not c_email: st.error('❌ Ingresa email del cliente')
        elif not c_name: st.error('❌ Ingresa nombre del cliente')
        elif not st.session_state.carrito: st.error('❌ Agrega productos al carrito')
        else:
            pid='PED-'+datetime.now().strftime('%Y%m%d-%H%M%S')
            tot=sum(i['total'] for i in st.session_state.carrito)
            ped={'id':pid,'client_email':c_email,'client_name':c_name,'destino':destino,'moneda':moneda,'productos':list(st.session_state.carrito),'total_usd':round(tot,2),'estado':'Recibido','fecha':datetime.now().isoformat(),'notas':notas,'historial_estados':[{'estado':'Recibido','fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email}],'creado_por':st.session_state.user_email}
            todos=load_pedidos(); todos.append(ped); save_pedidos(todos)
            if c_email not in clients: clients[c_email]={'nombre':c_name,'email':c_email,'fecha_registro':datetime.now().isoformat(),'pedidos_ids':[]}
            clients[c_email]['pedidos_ids']=clients[c_email].get('pedidos_ids',[])+[pid]
            save_clients(clients)
            el=load_email_log(); el.append({'id':f'EMAIL-{len(el)+1:05d}','destinatario':c_email,'asunto':f'Pedido {pid} recibido','tipo':'confirmacion','fecha':datetime.now().isoformat(),'estado':'simulado'}); save_email_log(el)
            st.session_state.carrito=[]
            st.success(f'✅ Pedido {pid} creado por ${tot:,.2f}')
            st.balloons(); st.cache_data.clear()

# ─── TAB PRECIOS ─────────────────────────────────────────────────────────
def render_actualizar_precios():
    st.markdown('## 💰 Actualizar Precios')
    data=load_data(); prods=data.get('products',[])
    if not prods: st.info('⚠️ No hay productos. Sube tu Excel en Cotización.'); return
    st.markdown('### 📄 Precios - EDITABLE')
    df=pd.DataFrame([{'Código':p.get('codigo',''),'Descripción':p.get('descripcion',''),'Precio CIF USD':p.get('precio_cif_usd',0),'Cajas/Pallet':p.get('cajas_pallet',200)} for p in prods])
    edited=st.data_editor(df,use_container_width=True,hide_index=True,key='precios_ed',num_rows='fixed')
    if st.button('💾 Guardar Precios',type='primary'):
        cambios=0
        for i,row in edited.iterrows():
            cod=row['Código']; np2=float(row['Precio CIF USD'])
            orig=next((p for p in prods if p.get('codigo')==cod),None)
            if orig and abs(np2-orig.get('precio_cif_usd',0))>0.001:
                reg_cambio_precio(cod,orig.get('precio_cif_usd',0),np2)
                orig['precio_cif_usd']=np2; cambios+=1
        if cambios>0: save_data(data); st.success(f'✅ {cambios} precios actualizados')
        else: st.info('Sin cambios')
    st.markdown('---')
    st.markdown('### 📈 Historial de Cambios')
    hist=load_historial()
    if hist:
        df_h=pd.DataFrame(hist[-30:][::-1])
        df_h['fecha']=pd.to_datetime(df_h['fecha']).dt.strftime('%d/%m/%Y %H:%M')
        st.dataframe(df_h[['fecha','producto','antes','despues','cambio_pct','usuario','motivo']].rename(columns={'fecha':'Fecha','producto':'Producto','antes':'Antes','despues':'Después','cambio_pct':'Cambio%','usuario':'Usuario','motivo':'Motivo'}),use_container_width=True,hide_index=True)
        h1,h2,h3=st.columns(3)
        h1.metric('📝 Total',len(hist)); h2.metric('📈 Aumentos',sum(1 for h2x in hist if h2x.get('cambio_pct',0)>0)); h3.metric('⚠️ >20%',sum(1 for h2x in hist if abs(h2x.get('cambio_pct',0))>20))
    else: st.info('Sin historial de cambios')

# ─── TAB DESTINOS ────────────────────────────────────────────────────────
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
    st.markdown(f'**✅ {len(filt)} pedidos**')
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
            if ped.get('productos'): st.dataframe(pd.DataFrame(ped['productos'])[['codigo','producto','cajas','pallets','precio_usd','total']],use_container_width=True,hide_index=True)
            if ped.get('notas'): st.markdown(f"**Notas:** {ped['notas']}")
            st.markdown('**Cambiar Estado:**')
            ac1,ac2=st.columns([2,1])
            ns=ac1.selectbox('Nuevo estado',ORDEN_ESTADOS,index=ORDEN_ESTADOS.index(ped.get('estado','Recibido')) if ped.get('estado') in ORDEN_ESTADOS else 0,key=f'est_{ped["id"]}')
            ac2.markdown('<br>',unsafe_allow_html=True)
            if ac2.button('✅ Actualizar',key=f'upd_{ped["id"]}'):
                todos=load_pedidos()
                for i,p in enumerate(todos):
                    if p.get('id')==ped.get('id'):
                        todos[i]['estado']=ns
                        todos[i].setdefault('historial_estados',[]).append({'estado':ns,'fecha':datetime.now().isoformat(),'usuario':st.session_state.user_email})
                        break
                save_pedidos(todos); st.success(f'✅ Estado: {ns}'); st.cache_data.clear(); st.rerun()

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
        rows.append({'Email':e,'Nombre':c.get('nombre',''),'Segmento':seg['badge'],'Pedidos':len(mp),'Facturación':f"${sum(p.get('total_usd',0) for p in mp):,.2f}",'Descuento':f"{seg['descuento']*100:.0f}%",'Crédito':f"${seg['credito']:,.0f}"})
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

# ─── TAB REPORTES ──────────────────────────────────────────────────────
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
def main():
    init_session()
    auto_load_excel()
    if not st.session_state.logged_in:
        login_page()
        return

    # Header
    st.markdown('<div style="background:linear-gradient(90deg,#003E8C,#0066CC);padding:16px 24px;border-radius:8px;margin-bottom:20px;"><h2 style="color:white;margin:0">🚀 EXPORT HARET - Sistema de Gestión de Pedidos v5.0</h2></div>', unsafe_allow_html=True)

    # Sidebar
    st.sidebar.markdown(f'# 🚀 Export Haret v5.0')
    st.sidebar.markdown(f'**{st.session_state.user_nombre}** | {st.session_state.user_rol}')
    st.sidebar.markdown('---')
    pedidos=load_pedidos(); clients=load_clients()
    st.sidebar.metric('📦 Pedidos',len(pedidos))
    st.sidebar.metric('💵 Facturación',f"${sum(p.get('total_usd',0) for p in pedidos):,.0f}")
    st.sidebar.metric('👥 Clientes',len(clients))
    pending=len([p for p in pedidos if p.get('estado') in ['Recibido','Confirmado','Preparando']])
    st.sidebar.metric('⏳ En proceso',pending)
    st.sidebar.markdown('---')
    if st.sidebar.button('🚪 Cerrar Sesión',use_container_width=True):
        st.session_state.logged_in=False; st.rerun()
    st.sidebar.caption('Export Haret © 2026')

    # Tabs
    tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8=st.tabs([
        '📊 Dashboard',
        '📄 Cotización',
        '🛒 Hacer Pedido',
        '💰 Precios',
        '🌍 Destinos',
        '⚙️ Config.',
        '📦 Pedidos',
        '👥 Clientes',
    ])

    with tab1: render_dashboard()
    with tab2: render_cotizacion()
    with tab3: render_hacer_pedido()
    with tab4: render_actualizar_precios()
    with tab5: render_destinos()
    with tab6: render_configuracion()
    with tab7: render_gestion_pedidos()
    with tab8: render_clientes()

    st.markdown('---')
    st.markdown('<div style="text-align:center;color:#888;"><small>🚀 Export Haret v5.0 © 2026 | Sistema Profesional de Gestión de Pedidos</small></div>',unsafe_allow_html=True)

if __name__=='__main__':
    main()
