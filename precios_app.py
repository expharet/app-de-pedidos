"""Export Haret — Pedidos"""

import streamlit as st
import json
import os
import math
import io
import base64
import urllib.parse
import subprocess
import smtplib
import requests
import pandas as pd
from datetime import date, datetime
from pathlib import Path
from fpdf import FPDF
from openpyxl import load_workbook
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import socket
import qrcode
from PIL import Image


@st.cache_data(ttl=3600)          # Refresca cada hora
def fetch_live_eur_usd() -> tuple:
    """Tipo de cambio EUR/USD en tiempo real desde el Banco Central Europeo."""
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=USD",
            timeout=6
        )
        if r.status_code == 200:
            data_fx = r.json()
            rate    = float(data_fx["rates"]["USD"])
            day     = data_fx.get("date", "")
            return rate, f"🟢 En vivo BCE · {day}"
    except Exception:
        pass
    return None, "🔴 Sin conexión"


# ── Divisas por destino ───────────────────────────────────────────────────────
DESTINO_DIVISA = {
    "Madrid/España":   ("EUR", "€"),
    "París/Francia":   ("EUR", "€"),
    "Londres/UK":      ("GBP", "£"),
    "Suiza":           ("CHF", "Fr"),
    "Países Bajos":    ("EUR", "€"),
    "Dubai/EAU":       ("AED", "د.إ"),
    "Nueva York/USA":  ("USD", "$"),
    "Miami/USA":       ("USD", "$"),
    "(otros)":         ("EUR", "€"),
}

# Simbolos por codigo de moneda
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "AED": "د.إ",
    "CNY": "¥",
    "RUB": "₽",
    "CHF": "Fr",
}


def get_dest_currency(dest_name: str, cfg_data: dict):
    """Retorna (dest_code, dest_sym) para un destino, usando destinos_moneda si existe."""
    override = cfg_data.get("destinos_moneda", {}).get(dest_name) if dest_name else None
    if override:
        sym = CURRENCY_SYMBOLS.get(override, "$")
        return override, sym
    return DESTINO_DIVISA.get(dest_name, ("USD", "$"))

@st.cache_data(ttl=3600)
def fetch_dest_rate(dest_code: str) -> float:
    """USD → dest_code exchange rate (live BCE/Frankfurter)."""
    if dest_code == "USD":
        return 1.0
    try:
        r = requests.get(
            f"https://api.frankfurter.app/latest?from=USD&to={dest_code}",
            timeout=6,
        )
        if r.status_code == 200:
            return float(r.json()["rates"][dest_code])
    except Exception:
        pass
    return 1.0


# ── Prefijos telefónicos ──────────────────────────────────────────────────────
PHONE_PREFIXES = [
    ("🇪🇸 España",           "+34"),
    ("🇫🇷 Francia",          "+33"),
    ("🇬🇧 Reino Unido",      "+44"),
    ("🇩🇪 Alemania",         "+49"),
    ("🇳🇱 Países Bajos",     "+31"),
    ("🇨🇭 Suiza",            "+41"),
    ("🇦🇪 Emiratos Árabes",  "+971"),
    ("🇺🇸 USA / Canadá",     "+1"),
    ("🇪🇨 Ecuador",          "+593"),
    ("🇨🇴 Colombia",         "+57"),
    ("🇲🇽 México",           "+52"),
    ("🇧🇷 Brasil",           "+55"),
    ("🇦🇷 Argentina",        "+54"),
    ("🇵🇪 Perú",             "+51"),
    ("🇮🇹 Italia",           "+39"),
    ("🇵🇹 Portugal",         "+351"),
    ("🇧🇪 Bélgica",          "+32"),
    ("🇦🇹 Austria",          "+43"),
    ("🇸🇦 Arabia Saudí",     "+966"),
    ("🇶🇦 Qatar",            "+974"),
    ("🇰🇼 Kuwait",           "+965"),
    ("🇦🇺 Australia",        "+61"),
    ("🇯🇵 Japón",            "+81"),
    ("🇨🇳 China",            "+86"),
    ("🇷🇺 Rusia",            "+7"),
]


# ── Envío automático de email ─────────────────────────────────────────────────
def send_order_email(saved: dict, ai_full: list, pdf_bytes: bytes,
                     cfg_data: dict, wa_text: str) -> tuple:
    """Envía el albarán por email a order@exportharet.com."""
    try:
        smtp_user = st.secrets.get("SMTP_USER", "")
        smtp_pass = st.secrets.get("SMTP_PASS", "")
        smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", "587"))
    except Exception:
        smtp_user = smtp_pass = ""

    if not smtp_user or not smtp_pass:
        return False, "sin_smtp"

    try:
        msg             = MIMEMultipart()
        msg["From"]     = smtp_user
        msg["To"]       = "order@exportharet.com"
        msg["Reply-To"] = saved.get("email", "")
        msg["Subject"]  = (
            f"Nuevo Pedido — {saved['client_name']} — "
            f"{saved['destino']} — {date.today().strftime('%d/%m/%Y')}"
        )
        body = wa_text.replace("*", "").replace("━", "-")
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # PDF adjunto
        part = MIMEBase("application", "octet-stream")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        fname = f"Albaran_{saved['client_name'].replace(' ','_')}_{date.today()}.pdf"
        part.add_header("Content-Disposition", f'attachment; filename="{fname}"')
        msg.attach(part)

        with smtplib.SMTP(smtp_host, smtp_port) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, "order@exportharet.com", msg.as_string())

        return True, "ok"
    except Exception as e:
        return False, str(e)



def send_cancel_email(ped: dict) -> None:
    """Notifica por email que un pedido fue eliminado/cancelado."""
    try:
        smtp_user = st.secrets.get("SMTP_USER", "")
        smtp_pass = st.secrets.get("SMTP_PASS", "")
        smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", "587"))
    except Exception:
        smtp_user = smtp_pass = ""
    if not smtp_user or not smtp_pass:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        ped_id   = ped.get("id", "?")
        cliente  = ped.get("client_name", ped.get("email", "?"))
        fecha    = ped.get("fecha", "")
        destino  = ped.get("destino", "FOB")
        total    = ped.get("total_usd", 0)
        subject  = f"Pedido #{ped_id} CANCELADO/ELIMINADO - Export Haret"
        body     = (
            f"Se ha eliminado el pedido #{ped_id}.\n\n"
            f"Cliente:  {cliente}\n"
            f"Fecha:    {fecha}\n"
            f"Destino:  {destino}\n"
            f"Total USD: ${total:,.2f}\n\n"
            f"Este pedido ya no aparece en el sistema."
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = "order@exportharet.com"
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, ["order@exportharet.com"], msg.as_string())
    except Exception:
        pass  # silencioso si falla SMTP

# ── Estados de pedido ────────────────────────────────────────────────────────
ORDEN_ESTADOS = ["Recibido", "Confirmado", "En preparación", "Enviado", "Entregado"]
ORDEN_ESTADOS_COLORES = {
    "Recibido":       "🔵",
    "Confirmado":     "🟡",
    "En preparación": "🟠",
    "Enviado":        "🚀",
    "Entregado":      "✅",
}
ORDEN_ESTADOS_EN = {
    "Recibido":       "Received",
    "Confirmado":     "Confirmed",
    "En preparación": "In preparation",
    "Enviado":        "Shipped",
    "Entregado":      "Delivered",
}


def send_status_email(ped: dict, new_status: str) -> None:
    """Envía email al cliente cuando el admin cambia el estado del pedido."""
    try:
        smtp_user = st.secrets.get("SMTP_USER", "")
        smtp_pass = st.secrets.get("SMTP_PASS", "")
        smtp_host = st.secrets.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(st.secrets.get("SMTP_PORT", "587"))
        if not smtp_user or not smtp_pass:
            return
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText as _MIMEText
        client_email = ped.get("email", "")
        client_name  = ped.get("client_name", "")
        ped_id       = ped.get("id", "").upper()
        icono        = ORDEN_ESTADOS_COLORES.get(new_status, "📦")
        subject = f"[Export Haret] Tu pedido #{ped_id} — Estado: {icono} {new_status}"
        body = f"""Hola {client_name},

Tu pedido #{ped_id} ha cambiado de estado:

  {icono} {new_status}

Puedes consultar el detalle en:
https://exportharet-pedidos.streamlit.app/?view=cliente

Gracias por confiar en Export Haret.
El equipo de Export Haret
"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = smtp_user
        msg["To"]      = client_email
        msg.attach(_MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, [client_email], msg.as_string())
    except Exception:
        pass  # silencioso


def get_network_url(port: int = 8501) -> str:
    """Devuelve la URL accesible en red local (no localhost)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return f"http://{ip}:{port}"
    except Exception:
        return f"http://localhost:{port}"

# ── Base de datos de clientes ──────────────────────────────────────────────────
CLIENTES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clientes.json")

@st.cache_data(ttl=10)
def load_clients() -> dict:
    if os.path.exists(CLIENTES_FILE):
        try:
            with open(CLIENTES_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_clients(clients: dict):
    st.cache_data.clear()
    with open(CLIENTES_FILE, "w", encoding="utf-8") as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

def register_order(saved: dict, ai_full: list, cfg_data: dict):
    """Registra o actualiza el cliente y guarda el pedido en su historial."""
    email = saved.get("email", "").strip().lower()
    if not email:
        return
    clients = load_clients()
    today   = date.today().isoformat()

    # Crear/actualizar ficha del cliente
    if email not in clients:
        clients[email] = {
            "nombre":        saved["client_name"],
            "razon_social":  saved["razon_social"],
            "telefono":      saved.get("telefono", ""),
            "primer_pedido": today,
            "ultimo_pedido": today,
            "pedidos":       [],
        }
    else:
        c = clients[email]
        c["nombre"]       = saved["client_name"]   # actualizar por si cambió
        c["razon_social"] = saved["razon_social"]
        c["telefono"]     = saved.get("telefono", c.get("telefono",""))
        c["ultimo_pedido"] = today

    # Construir resumen del pedido
    productos_resumen = []
    for p, cajas in ai_full:
        r = calc_pedido(p, cfg_data, saved["destino"], saved["total_cajas"])
        productos_resumen.append({
            "producto":   p["producto"],
            "cajas":      cajas,
            "precio_usd": round(r["precio_caja_usd"], 4),
            "total_usd":  round(r["precio_caja_usd"] * cajas, 2),
        })

    pedido_id = f"PED-{today.replace('-','')}-{len(clients[email]['pedidos'])+1:03d}"
    clients[email]["pedidos"].append({
        "id":         pedido_id,
        "fecha":      today,
        "destino":    saved["destino"],
        "total_usd":  round(saved["total_usd"], 2),
        "dest_code":  saved.get("dest_code", "USD"),
        "dest_sym":   saved.get("dest_sym",  "$"),
        "dest_rate":  saved.get("dest_rate", 1.0),
        "total_loc":  round(saved["total_usd"] * saved.get("dest_rate", 1.0), 2),
        "pallets":    saved["total_pallets"],
        "cajas":      saved["total_cajas"],
        "productos":  productos_resumen,
    })

    save_clients(clients)

    # Publicar clientes.json en GitHub también
    _push_clients_to_github(clients)

def _push_clients_to_github(clients: dict):
    """Sube clientes.json a GitHub vía API."""
    try:
        _sp  = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        tok  = ""
        try:
            tok = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            pass
        if not tok and os.path.exists(_sp):
            for line in open(_sp):
                if "GITHUB_TOKEN" in line and "=" in line:
                    tok = line.split("=",1)[1].strip().strip('"').strip("'")
        if not tok:
            return
        hdrs    = {"Authorization": f"token {tok}",
                   "Accept": "application/vnd.github.v3+json"}
        api_url = "https://api.github.com/repos/expharet/app-de-pedidos/contents/clientes.json"
        content = base64.b64encode(
            json.dumps(clients, indent=2, ensure_ascii=False).encode()
        ).decode()
        r_get   = requests.get(api_url, headers=hdrs, timeout=10)
        sha     = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {"message": f"Registro cliente — {date.today().isoformat()}",
                   "content": content}
        if sha:
            payload["sha"] = sha
        requests.put(api_url, json=payload, headers=hdrs, timeout=15)
    except Exception:
        pass   # silencioso — no bloquear el flujo principal


def sync_from_cotizaciones(excel_bytes: bytes, current_data: dict) -> tuple:
    """
    Lee Cotizaciones.xlsx y devuelve (new_products, new_cfg, lista_cambios).
    Detecta cambios en precios de compra, tarifas de flete y parámetros.
    """
    from openpyxl import load_workbook
    import io as _io

    wb       = load_workbook(_io.BytesIO(excel_bytes), data_only=True)
    ws_cfg   = wb["CONFIGURACION"]
    ws_pr    = wb["TABLA PRECIOS"]
    new_cfg  = json.loads(json.dumps(current_data["config"]))
    changes  = []

    # ── Parámetros generales (busca por nombre de celda, robusto a cambios de fila) ──
    for row in ws_cfg.iter_rows():
        for cell in row:
            v = str(cell.value or "")
            c3 = ws_cfg.cell(row=cell.row, column=3).value
            if not isinstance(c3, (int, float)):
                continue
            val = float(c3)
            if "Costo de la caja" in v:
                if abs(new_cfg.get("costo_caja", 0) - val) > 0.0001:
                    changes.append(f"Costo caja: {new_cfg.get('costo_caja')} → {val}")
                    new_cfg["costo_caja"] = val
            elif "Merma" in v and "%" in v:
                if abs(new_cfg.get("merma_pct", 0) - val) > 0.0001:
                    changes.append(f"Merma %: {new_cfg.get('merma_pct')} → {val}")
                    new_cfg["merma_pct"] = val
            elif "DUE" in v and "fijo" in v:
                if abs(new_cfg.get("due", 0) - val) > 0.0001:
                    changes.append(f"DUE: {new_cfg.get('due')} → {val}")
                    new_cfg["due"] = val
            elif "Peso pallet" in v:
                if abs(new_cfg.get("peso_pallet", 0) - val) > 0.0001:
                    changes.append(f"Peso pallet: {new_cfg.get('peso_pallet')} → {val}")
                    new_cfg["peso_pallet"] = val
            elif "Tara de la caja" in v:
                if abs(new_cfg.get("tara_caja", 0) - val) > 0.0001:
                    changes.append(f"Tara caja: {new_cfg.get('tara_caja')} → {val}")
                    new_cfg["tara_caja"] = val
            elif "transporte interno" in v.lower() and "costo" in v.lower():
                if abs(new_cfg.get("transporte_interno", 0) - val) > 0.0001:
                    changes.append(f"Transporte interno: {new_cfg.get('transporte_interno')} → {val}")
                    new_cfg["transporte_interno"] = val
            # Tarifas de destino (columna B = nombre del destino, columna C = tarifa)
            dest_name = str(ws_cfg.cell(row=cell.row, column=2).value or "")
            if cell.column == 2 and dest_name in new_cfg.get("destinos", {}):
                if abs(new_cfg["destinos"][dest_name] - val) > 0.0001:
                    changes.append(f"Tarifa **{dest_name}**: {new_cfg['destinos'][dest_name]} → {val}")
                    new_cfg["destinos"][dest_name] = val

    # ── Últimos precios de compra desde historial (TABLA PRECIOS, filas 32-83) ──
    COL_MAP = {
         4: "F-PSG10",   # D Granadilla
         5: "F-PN016",   # E Lulo
         6: "F-PPA01",   # F Amarilla P
         7: "F-PSR02",   # G Roja P
         8: "F-PSR05",   # H Blanca P
         9: "F-PSM09",   # I Maracuyá
        10: "F-TAS04",   # J Tomate de árbol
        11: "F-GNB010",  # K Guanabana
        12: "F-MPS03",   # L Pepino dulce
        13: "F-CCN017",  # M Cacao
        14: "F-BCC013",  # N Babaco
        15: "F-AHSS012", # O Aguacate
        16: "F-BBB06",   # P Baby banano
        17: "F-ZPT020",  # Q Zapote Mamey
        18: "F-TX020",   # R Taxo
        19: "F-UVP08",   # S Physalis
        20: "F-UVP07",   # T Physalis-husk
    }
    latest = {}
    for col, codigo in COL_MAP.items():
        last = None
        for r in range(32, 84):
            v = ws_pr.cell(row=r, column=col).value
            if isinstance(v, (int, float)) and v > 0:
                last = float(v)
        if last:
            latest[codigo] = last

    new_products = []
    for p in current_data["products"]:
        np2 = dict(p)
        if p["codigo"] in latest:
            new_price = latest[p["codigo"]]
            if abs(np2["precio_compra"] - new_price) > 0.001:
                changes.append(
                    f"**{p['producto']}**: ${np2['precio_compra']:.2f} → ${new_price:.2f}")
                np2["precio_compra"] = new_price
        new_products.append(np2)

    return new_products, new_cfg, changes


def _load_page_icon():
    """Carga el favicon personalizado si existe, si no usa el emoji."""
    _fav = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.png")
    if os.path.exists(_fav):
        from PIL import Image as _PIL
        return _PIL.open(_fav)
    return "🌿"

st.set_page_config(
    page_title="Export Haret — Pedidos",
    page_icon=_load_page_icon(),
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "precios_data.json")

INITIAL_DATA = {
    "config": {
        "costo_caja": 1.0,
        "merma_pct": 0.01,
        "due": 280.0,
        "peso_pallet": 29.9,
        "tara_caja": 0.4,
        "transporte_interno": 60.0,
        "eur_usd": 1.164,
        "grupos": {
            "A": {"cajas_pallet": 160, "nombre": "Granadilla"},
            "B": {"cajas_pallet": 180, "nombre": "Pitahaya Amarilla"},
            "C": {"cajas_pallet": 160, "nombre": "Lulo · Maracuyá · Tomate · Taxo · Melon"},
            "D": {"cajas_pallet": 120, "nombre": "Cacao · Babaco"},
            "E": {"cajas_pallet": 160, "nombre": "Aguacate · Baby banano · Zapote · Caña"},
            "F": {"cajas_pallet": 120, "nombre": "Roja P · Blanca P"},
            "G": {"cajas_pallet": 160, "nombre": "Physalis sin cáscara"},
            "H": {"cajas_pallet": 160, "nombre": "Physalis con cáscara"},
            "I": {"cajas_pallet":  60, "nombre": "Guanabana"},
        },
        "public_url": "https://exportharet-pedidos.streamlit.app",
        "destinos": {
            "Madrid/España": 2.25,
            "París/Francia": 2.75,
            "Londres/UK": 2.60,
            "Suiza": 2.60,
            "Países Bajos": 2.60,
            "Dubai/EAU": 4.30,
            "Nueva York/USA": 1.20,
            "Miami/USA": 1.15,
            "(otros)": 2.10,
        },
    },
    "products": [
        {"codigo": "F-PSG10",  "producto": "Granadilla",     "kg_caja": 2.0,  "costo_caja_manual": 0.03, "precio_compra": 7.95,  "margen_pct": 0.08,  "grupo": "A", "activo": True},
        {"codigo": "F-PN016",  "producto": "Lulo",           "kg_caja": 2.5,  "costo_caja_manual": 0.03, "precio_compra": 6.50,  "margen_pct": 0.11,  "grupo": "C", "activo": True},
        {"codigo": "F-PPA01",  "producto": "Amarilla P",     "kg_caja": 2.5,  "costo_caja_manual": None, "precio_compra": 15.50, "margen_pct": 0.06,  "grupo": "B", "activo": True},
        {"codigo": "F-PSR02",  "producto": "Roja P",         "kg_caja": 4.5,  "costo_caja_manual": None, "precio_compra": 19.19, "margen_pct": 0.055, "grupo": "F", "activo": True},
        {"codigo": "F-PSR05",  "producto": "Blanca P",       "kg_caja": 4.5,  "costo_caja_manual": None, "precio_compra": 13.60, "margen_pct": 0.055, "grupo": "F", "activo": True},
        {"codigo": "F-PSM09",  "producto": "Maracuyá",       "kg_caja": 2.5,  "costo_caja_manual": 0.0,  "precio_compra": 7.00,  "margen_pct": 0.08,  "grupo": "C", "activo": True},
        {"codigo": "F-TAS04",  "producto": "Tomate de árbol","kg_caja": 2.5,  "costo_caja_manual": 0.0,  "precio_compra": 6.50,  "margen_pct": 0.10,  "grupo": "C", "activo": True},
        {"codigo": "F-GNB010", "producto": "Guanabana",      "kg_caja": 4.0,  "costo_caja_manual": None, "precio_compra": 13.14, "margen_pct": 0.12,  "grupo": "I", "activo": True},
        {"codigo": "F-MPS03",  "producto": "Pepino dulce",   "kg_caja": 3.0,  "costo_caja_manual": 0.0,  "precio_compra": 5.25,  "margen_pct": 0.09,  "grupo": "C", "activo": True},
        {"codigo": "F-CCN017", "producto": "Cacao",          "kg_caja": 3.0,  "costo_caja_manual": None, "precio_compra": 6.00,  "margen_pct": 0.11,  "grupo": "D", "activo": True},
        {"codigo": "F-BCC013", "producto": "Babaco",         "kg_caja": 3.0,  "costo_caja_manual": None, "precio_compra": 8.60,  "margen_pct": 0.10,  "grupo": "D", "activo": True},
        {"codigo": "F-AHSS012","producto": "Aguacate",       "kg_caja": 4.0,  "costo_caja_manual": None, "precio_compra": 8.55,  "margen_pct": 0.06,  "grupo": "E", "activo": True},
        {"codigo": "F-BBB06",  "producto": "Baby banano",    "kg_caja": 3.5,  "costo_caja_manual": None, "precio_compra": 13.20, "margen_pct": 0.06,  "grupo": "E", "activo": True},
        {"codigo": "F-ZPT020", "producto": "Zapote Mamey",   "kg_caja": 4.0,  "costo_caja_manual": None, "precio_compra": 12.00, "margen_pct": 0.18,  "grupo": "E", "activo": True},
        {"codigo": "F-TX020",  "producto": "Taxo",           "kg_caja": 2.5,  "costo_caja_manual": 0.0,  "precio_compra": 6.70,  "margen_pct": 0.10,  "grupo": "C", "activo": True},
        {"codigo": "F-UVP08",  "producto": "Physalis",       "kg_caja": 1.25, "costo_caja_manual": 0.0,  "precio_compra": 8.50,  "margen_pct": 0.11,  "grupo": "G", "activo": True},
        {"codigo": "F-UVP07",  "producto": "Physalis - husk","kg_caja": 1.5,  "costo_caja_manual": 0.0,  "precio_compra": 7.25,  "margen_pct": 0.11,  "grupo": "H", "activo": True},
        {"codigo": "F-SLK011", "producto": "Salack",         "kg_caja": 2.5,  "costo_caja_manual": 0.4,  "precio_compra": 12.20, "margen_pct": 0.10,  "grupo": "C", "activo": True},
        {"codigo": "F-CAZ021", "producto": "Caña de azúcar", "kg_caja": 4.0,  "costo_caja_manual": None, "precio_compra": 10.72, "margen_pct": 0.11,  "grupo": "E", "activo": True},
    ],
    "minimos": {
        "F-PSG10":  {"tipo": "cajas", "valor": 80},
        "F-PN016":  {"tipo": "cajas", "valor": 40},
        "F-TAS04":  {"tipo": "cajas", "valor": 40},
        "F-MPS03":  {"tipo": "cajas", "valor": 40},
        "F-TX020":  {"tipo": "cajas", "valor": 40},
        "F-PSM09":  {"tipo": "cajas", "valor": 160},
        "F-GNB010": {"tipo": "cajas", "valor": 60},
        "F-CCN017": {"tipo": "cajas", "valor": 120},
        "F-BCC013": {"tipo": "cajas", "valor": 120},
        "F-ZPT020": {"tipo": "cajas", "valor": 120},
        "F-PSR02":  {"tipo": "cajas", "valor": 360},
        "F-PSR05":  {"tipo": "cajas", "valor": 360},
        "F-PPA01":  {"tipo": "cajas", "valor": 360},
        "F-SLK011": {"tipo": "cajas", "valor": 160},
        "F-CAZ021": {"tipo": "cajas", "valor": 120},
        "F-UVP08":  {"tipo": "cajas", "valor": 50},
        "F-UVP07":  {"tipo": "cajas", "valor": 50},
    },
}


@st.cache_data(ttl=10)
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return json.loads(json.dumps(INITIAL_DATA))  # deep copy


def save_data(data):
    st.cache_data.clear()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def costo_caja(product, cfg):
    m = product.get("costo_caja_manual")
    return m if m is not None else cfg["costo_caja"] / product["kg_caja"]


def calc(product, cfg, destino, num_pallets):
    cc = costo_caja(product, cfg)
    fob_base = product["precio_compra"] + cc
    mp = cfg["merma_pct"]
    fob_merma = fob_base / (1 - mp)
    mgn = product["margen_pct"]
    fob_final = fob_merma / (1 - mgn)
    cajas = cfg["grupos"][product["grupo"]]["cajas_pallet"]
    tarifa = cfg["destinos"].get(destino, 0) if destino else 0
    flete = tarifa * (product["kg_caja"] + cfg["tara_caja"] + cfg["peso_pallet"] / cajas)
    cif = fob_final + flete
    due_c = cfg["due"] / (num_pallets * cajas)
    ti_c = cfg["transporte_interno"] / (num_pallets * cajas)
    pal_usd = cif + due_c + ti_c
    pal_eur = pal_usd / cfg["eur_usd"]
    return {
        "Costo caja": cc,
        "FOB base": fob_base,
        "FOB + Merma": fob_merma,
        "Margen %": mgn,
        "FOB Final": fob_final,
        "Flete": flete,
        "CIF USD": cif,
        "CIF $/kg": cif / product["kg_caja"],
        "Pal USD": pal_usd,
        "Pal EUR": pal_eur,
    }


def fmt(v, decimals=2):
    return f"{v:,.{decimals}f}"


def get_min_cajas(codigo, product, cfg):
    """Devuelve la cantidad mínima de cajas para un producto."""
    minimos = cfg.get("minimos", {})  # from data root, patched below
    m = minimos.get(codigo)
    if not m:
        return 0
    if m["tipo"] == "cajas":
        return int(m["valor"])
    cajas_pallet = cfg["grupos"][product["grupo"]]["cajas_pallet"]
    return int(m["valor"]) * cajas_pallet


def min_label(codigo, product, cfg):
    minimos = cfg.get("minimos", {})
    m = minimos.get(codigo)
    if not m:
        return "—"
    if m["tipo"] == "cajas":
        return f"{m['valor']} cajas"
    v = int(m["valor"])
    return f"{v} pallet{'s' if v > 1 else ''}"


def calc_pedido(product, cfg, destino, total_cajas_orden):
    """Precio/caja en un pedido mixto: DUE y transporte repartidos sobre total_cajas."""
    cc = costo_caja(product, cfg)
    fob_base = product["precio_compra"] + cc
    fob_merma = fob_base / (1 - cfg["merma_pct"])
    fob_final = fob_merma / (1 - product["margen_pct"])
    cajas_pal = cfg["grupos"][product["grupo"]]["cajas_pallet"]
    tarifa = cfg["destinos"][destino]
    flete = tarifa * (product["kg_caja"] + cfg["tara_caja"] + cfg["peso_pallet"] / cajas_pal)
    cif = fob_final + flete
    due_c = cfg["due"] / total_cajas_orden
    ti_c = cfg["transporte_interno"] / total_cajas_orden
    precio_caja = cif + due_c + ti_c
    return {
        "fob_final": fob_final,
        "flete": flete,
        "cif": cif,
        "due_caja": due_c,
        "ti_caja": ti_c,
        "precio_caja_usd": precio_caja,
        "precio_caja_eur": precio_caja / cfg["eur_usd"],
    }


# ── Albarán PDF ───────────────────────────────────────────────────────────────
def _font_path(filename: str) -> str:
    """Ruta a la fuente — busca en ./fonts/ primero, luego rutas del sistema."""
    local = os.path.join(os.path.dirname(__file__), "fonts", filename)
    if os.path.exists(local):
        return local
    # Fallback macOS
    mac_map = {
        "DejaVuSans.ttf":      "/Library/Fonts/Arial Unicode.ttf",
        "DejaVuSans-Bold.ttf": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    }
    return mac_map.get(filename, local)


def gen_albaran_pdf(client_name, razon_social, destino, active_items, total_cajas,
                    total_pallets, total_usd, cfg_data,
                    total_eur=None, client_email="", telefono="",
                    dest_code="USD", dest_sym="$", dest_rate=1.0, lang="ES",
                    total_flete=0.0):
    Tp  = TR.get(lang, TR["ES"])   # ← traducción al inicio, antes de todo uso
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    GREEN = (45, 106, 79)

    # Fuente DejaVu — cross-platform, soporta €, tildes, todos los caracteres
    pdf.add_font("U", "",  _font_path("DejaVuSans.ttf"),      uni=True)
    pdf.add_font("U", "B", _font_path("DejaVuSans-Bold.ttf"), uni=True)

    # ── Cabecera ──
    pdf.set_fill_color(*GREEN)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("U", "B", 20)
    pdf.set_xy(15, 6)
    pdf.cell(0, 10, "EXPORT HARET", ln=True)
    pdf.set_font("U", "", 9)
    pdf.set_x(15)
    pdf.cell(0, 5, "Exportadora de frutas ecuatorianas  ·  order@exportharet.com")
    pdf.ln(14)

    # ── Título albarán ──
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("U", "B", 14)
    pdf.cell(0, 10, Tp["pdf_title"], ln=True, align="C")
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.6)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Datos del cliente ──
    rate_label = cfg_data.get("_rate_label", "").replace("🟢","").replace("🟡","").strip()
    client_fields = [(Tp["pdf_client"],  client_name),
                     (Tp["pdf_company"], razon_social)]
    if client_email: client_fields.append((Tp["pdf_email"], client_email))
    if telefono:     client_fields.append((Tp["pdf_phone"], telefono))
    client_fields += [
        (Tp["pdf_date"],  date.today().strftime("%d/%m/%Y")),
        (Tp["pdf_dest"],  destino),
        (Tp["pdf_rate"],  f"{cfg_data['eur_usd']:.4f}  ({rate_label})"),
    ]
    _tarifa_pdf = cfg_data["destinos"].get(destino, 0)
    _flete_lbl  = "Flete / Freight" if lang == "ES" else "Freight rate"
    client_fields.append((_flete_lbl,
                          f"{_tarifa_pdf:.2f} USD/kg · CIF destino"))
    if dest_code not in ("USD",):
        client_fields.append((Tp["pdf_divisa"].format(code=dest_code),
                              f"1 USD = {dest_rate:.4f} {dest_sym}"))
    for label, value in client_fields:
        pdf.set_font("U", "B", 10)
        pdf.cell(38, 7, label)
        pdf.set_font("U", "", 10)
        pdf.cell(0, 7, value, ln=True)

    pdf.ln(3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Tabla de productos ──
    pdf.set_fill_color(*GREEN)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("U", "B", 9)
    widths  = [58, 22, 22, 40, 40]
    headers = [Tp["pdf_product"], Tp["pdf_boxes"], Tp["pdf_pallets"],
               Tp["pdf_price_usd"], Tp["pdf_total_usd"]]
    aligns  = ["L", "C", "C", "R", "R"]
    for w, h, a in zip(widths, headers, aligns):
        pdf.cell(w, 7, h, fill=True, align=a)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("U", "", 9)
    fill = False
    for p, cajas in active_items:
        r   = calc_pedido(p, cfg_data, destino, total_cajas)
        pal = cajas / cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        row_vals = [
            p["producto"],
            str(cajas),
            f"{pal:.2f}",
            f"${r['precio_caja_usd']:.2f}",
            f"${r['precio_caja_usd']*cajas:,.2f}",
        ]
        bg = (240, 248, 240) if fill else (255, 255, 255)
        pdf.set_fill_color(*bg)
        for w, v, a in zip(widths, row_vals, aligns):
            pdf.cell(w, 6, v, fill=True, align=a)
        pdf.ln()
        fill = not fill

    pdf.ln(3)
    pdf.set_draw_color(*GREEN)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Totales ──
    pdf.set_font("U", "", 10)
    pdf.cell(100, 7, Tp["pdf_total_pal"].format(n=total_pallets, c=f"{total_cajas:,}"))
    pdf.set_font("U", "B", 11)
    pdf.cell(0, 7, f"TOTAL USD:  ${total_usd:,.2f}", align="R", ln=True)
    pdf.cell(100, 7, "")
    if dest_code != "USD":
        total_loc_pdf = total_usd * dest_rate
        pdf.cell(0, 7, f"TOTAL {dest_code}:  {dest_sym}{total_loc_pdf:,.2f}", align="R", ln=True)

    # ── Pie ──
    pdf.ln(10)
    pdf.set_font("U", "", 8)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 5, Tp["pdf_footer"],
             align="C", ln=True)

    return bytes(pdf.output())


def gen_wa_text(client_name, razon_social, destino, active_items,
                total_cajas, total_pallets, total_usd, cfg_data,
                total_eur=None, dest_code="USD", dest_sym="$", dest_rate=1.0, lang="ES"):
    Tw = TR.get(lang, TR["ES"])
    lines = [
        Tw["wa_header"],
        "━━━━━━━━━━━━━━━━━━━━━",
        f"{Tw['wa_client']} {client_name}",
        f"{Tw['wa_company']} {razon_social}",
        f"{Tw['wa_date']} {date.today().strftime('%d/%m/%Y')}",
        f"{Tw['wa_dest']} {destino}",
        "━━━━━━━━━━━━━━━━━━━━━",
        Tw["wa_products"],
    ]
    for p, cajas in active_items:
        r = calc_pedido(p, cfg_data, destino, total_cajas)
        pal = cajas / cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        total = r["precio_caja_usd"] * cajas
        lines.append(f"• {p['producto']}: {cajas} cajas ({pal:.2f} pal) — ${total:,.2f}")
    total_loc = total_usd * dest_rate
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━",
        Tw["wa_summary"].format(c=f"{total_cajas:,}", p=total_pallets),
        f"💵 *Total USD: ${total_usd:,.2f}*",
    ]
    if dest_code != "USD":
        lines.append(f"💱 *Total {dest_code}: {dest_sym}{total_loc:,.2f}*")
    return "\n".join(lines)


TR = {
    "ES": {
        "lang_label":      "Idioma / Language",
        "title":           "## 🌿 Export Haret — Pedidos",
        "client_section":  "#### 👤 Datos del cliente",
        "name":            "Nombre del cliente *",
        "name_ph":         "Nombre completo",
        "company":         "Razón social / Empresa *",
        "company_ph":      "Empresa S.L.",
        "email":           "📧 Email de contacto *",
        "email_ph":        "cliente@empresa.com",
        "prefix":          "📞 País / Prefijo *",
        "phone":           "Número de teléfono *",
        "phone_ph":        "612 345 678",
        "dest":            "🌍 Destino *",
        "min_order":       "Mínimo de orden: **{n} pallets** totales.",
        "dest_currency":   "Divisa del destino: **{code} ({sym})** · 1 USD = {rate:.4f} {code}",
        "currency_usd":    "Divisa: **USD ($)**",
        "products":        "#### 📦 Productos del pedido",
        "unit_col":        "Unidad",
        "qty_col":         "Cantidad",
        "boxes_col":       "= Cajas",
        "opt_pal":         "📦 Pallets",
        "opt_caj":         "🗃️ Cajas",
        "min_pal":         "mín. {n} pallet{s} ({c} cajas)",
        "min_caj":         "mín. {n} cajas",
        "hint":            "↑ Elige **📦 Pallets** o **🗃️ Cajas** e ingresa la cantidad de cada producto.",
        "pallets_m":       "Pallets",
        "cajas_m":         "Cajas",
        "weight_m":        "Peso neto",
        "progress_ok":     "✅ {n} pallets — pedido válido",
        "progress_low":    "🔴 {n} de {min} pallets mínimos — faltan {f} pallet{s}",
        "warn_fields":     "⚠️ Completa todos los datos del cliente para confirmar.",
        "warn_pallets":    "⚠️ Faltan {f} pallet{s} para alcanzar el mínimo de {min}.",
        "below_min":       "⚠️ **{prod}**: pediste {got} cajas — mínimo es {need} cajas.",
        "confirm_btn":     "✅ Confirmar Pedido",
        "confirmed_ok":    "✅ Pedido confirmado — {name} · {dest}",
        "email_auto_ok":   "📨 Pedido enviado automáticamente a **order@exportharet.com**",
        "email_no_smtp":   "💡 Configura SMTP en los secretos para envío automático.",
        "email_error":     "⚠️ No se pudo enviar email: {e}",
        "pdf_btn":         "📄 Descargar Albarán PDF",
        "wa_btn":          "📱 Enviar por WhatsApp",
        "mail_btn":        "📧 Enviar por Email",
        "new_btn":         "🔄 Nuevo",
        "pdf_title":       "ALBARÁN DE PEDIDO",
        "pdf_client":      "Cliente:",
        "pdf_company":     "Razón social:",
        "pdf_email":       "Email:",
        "pdf_phone":       "Teléfono:",
        "pdf_date":        "Fecha:",
        "pdf_dest":        "Destino:",
        "pdf_rate":        "EUR/USD:",
        "pdf_divisa":      "Divisa {code}:",
        "pdf_product":     "Producto",
        "pdf_boxes":       "Cajas",
        "pdf_pallets":     "Pallets",
        "pdf_price_usd":   "Precio/caja USD",
        "pdf_total_usd":   "Total USD",
        "pdf_total_pal":   "Total pallets: {n}   ·   Total cajas: {c}",
        "pdf_footer":      "Export Haret  ·  order@exportharet.com  ·  Documento generado automáticamente",
        "wa_header":       "🌿 *PEDIDO — EXPORT HARET*",
        "wa_client":       "👤 Cliente:",
        "wa_company":      "🏢 Razón social:",
        "wa_date":         "📅 Fecha:",
        "wa_dest":         "✈️ Destino:",
        "wa_products":     "*PRODUCTOS:*",
        "wa_summary":      "📦 Total: {c} cajas  |  {p} pallets",
    },
    "EN": {
        "lang_label":      "Idioma / Language",
        "title":           "## 🌿 Export Haret — Orders",
        "client_section":  "#### 👤 Client Information",
        "name":            "Client Name *",
        "name_ph":         "Full name",
        "company":         "Company / Business Name *",
        "company_ph":      "Company Ltd.",
        "email":           "📧 Contact Email *",
        "email_ph":        "client@company.com",
        "prefix":          "📞 Country / Prefix *",
        "phone":           "Phone Number *",
        "phone_ph":        "612 345 678",
        "dest":            "🌍 Destination *",
        "min_order":       "Minimum order: **{n} pallets** total.",
        "dest_currency":   "Destination currency: **{code} ({sym})** · 1 USD = {rate:.4f} {code}",
        "currency_usd":    "Currency: **USD ($)**",
        "products":        "#### 📦 Order Products",
        "unit_col":        "Unit",
        "qty_col":         "Quantity",
        "boxes_col":       "= Boxes",
        "opt_pal":         "📦 Pallets",
        "opt_caj":         "🗃️ Boxes",
        "min_pal":         "min. {n} pallet{s} ({c} boxes)",
        "min_caj":         "min. {n} boxes",
        "hint":            "↑ Choose **📦 Pallets** or **🗃️ Boxes** and enter the quantity for each product.",
        "pallets_m":       "Pallets",
        "cajas_m":         "Boxes",
        "weight_m":        "Net Weight",
        "progress_ok":     "✅ {n} pallets — valid order",
        "progress_low":    "🔴 {n} of {min} minimum pallets — add {f} more pallet{s}",
        "warn_fields":     "⚠️ Please fill in all client information to confirm.",
        "warn_pallets":    "⚠️ {f} more pallet{s} needed to reach the minimum of {min}.",
        "below_min":       "⚠️ **{prod}**: you entered {got} boxes — minimum is {need} boxes.",
        "confirm_btn":     "✅ Confirm Order",
        "confirmed_ok":    "✅ Order confirmed — {name} · {dest}",
        "email_auto_ok":   "📨 Order automatically sent to **order@exportharet.com**",
        "email_no_smtp":   "💡 Configure SMTP secrets for automatic email sending.",
        "email_error":     "⚠️ Could not send email: {e}",
        "pdf_btn":         "📄 Download Order PDF",
        "wa_btn":          "📱 Send via WhatsApp",
        "mail_btn":        "📧 Send via Email",
        "new_btn":         "🔄 New Order",
        "pdf_title":       "ORDER CONFIRMATION",
        "pdf_client":      "Client:",
        "pdf_company":     "Company:",
        "pdf_email":       "Email:",
        "pdf_phone":       "Phone:",
        "pdf_date":        "Date:",
        "pdf_dest":        "Destination:",
        "pdf_rate":        "EUR/USD:",
        "pdf_divisa":      "{code} rate:",
        "pdf_product":     "Product",
        "pdf_boxes":       "Boxes",
        "pdf_pallets":     "Pallets",
        "pdf_price_usd":   "Price/box USD",
        "pdf_total_usd":   "Total USD",
        "pdf_total_pal":   "Total pallets: {n}   ·   Total boxes: {c}",
        "pdf_footer":      "Export Haret  ·  order@exportharet.com  ·  Automatically generated document",
        "wa_header":       "🌿 *ORDER — EXPORT HARET*",
        "wa_client":       "👤 Client:",
        "wa_company":      "🏢 Company:",
        "wa_date":         "📅 Date:",
        "wa_dest":         "✈️ Destination:",
        "wa_products":     "*PRODUCTS:*",
        "wa_summary":      "📦 Total: {c} boxes  |  {p} pallets",
    },
}


def render_order_form(cfg_data, products_list, standalone=False,
                      show_header=True, require_email=True):
    """Formulario de pedido.
    standalone=True  → vista cliente (?view=cliente)
    show_header=False → oculta logo/título/idioma (ya mostrado por el portal)
    require_email=False → salta la verificación de email (ya hecha por el portal)
    """
    MIN_PALLETS = 3

    # ── Selector de idioma ──────────────────────────────────────────────────────
    lang_key = "order_lang"
    if lang_key not in st.session_state:
        st.session_state[lang_key] = "ES"

    if show_header:
        lang_col, _ = st.columns([1, 5])
        with lang_col:
            lang = st.radio(
                "🌐",
                ["🇪🇸 ES", "🇬🇧 EN"],
                horizontal=True,
                key=lang_key,
                label_visibility="collapsed",
            )
        lang = "EN" if "EN" in lang else "ES"
    else:
        lang = "EN" if "EN" in st.session_state.get(lang_key, "🇪🇸 ES") else "ES"
    T = TR[lang]
    MIN_PALLETS = cfg_data.get("config", {}).get("min_pallets", MIN_PALLETS)

    if standalone and show_header:
        _logo_path_s = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(_logo_path_s):
            st.image(_logo_path_s, width=180)
        st.markdown(T["title"])
        st.markdown("---")

    # ── Acceso / Registro del cliente ─────────────────────────────────────────
    _clients_db  = load_clients()
    _sfx         = "cl" if standalone else "adm"
    _verified_k  = f"client_verified_{_sfx}"
    _cdata_k     = f"client_data_{_sfx}"

    if _verified_k not in st.session_state:
        st.session_state[_verified_k] = False
    if _cdata_k not in st.session_state:
        st.session_state[_cdata_k]    = {}

    # ── PASO 1: Identificación del cliente ────────────────────────────────────
    if require_email and not st.session_state[_verified_k]:

        if lang == "EN":
            _lbl_email   = "📧 Enter your email to continue"
            _hint_email  = "We'll identify you or create your account automatically"
            _btn_cont    = "Continue →"
            _welcome_txt = lambda n, np_: f"👋 Welcome back, **{n}**!"
            _ped_prev    = lambda np_: (f"You have **{np_}** previous order{'s' if np_!=1 else ''}."
                                        if np_ > 0 else "")
            _confirm_btn = "✅ Continue"
            _change_btn  = "↩️ Different email"
            _reg_title   = "#### 📝 Complete your details"
            _reg_hint    = "Quick registration — only takes a moment"
            _reg_cont    = "✅ Register & Continue"
            _reg_back    = "← Back"
        else:
            _lbl_email   = "📧 Ingresa tu correo para continuar"
            _hint_email  = "Te identificamos o creamos tu cuenta automáticamente"
            _btn_cont    = "Continuar →"
            _welcome_txt = lambda n, np_: f"👋 ¡Hola de nuevo, **{n}**!"
            _ped_prev    = lambda np_: (f"Tienes **{np_}** pedido{'s' if np_!=1 else ''} anterior{'es' if np_!=1 else ''}."
                                        if np_ > 0 else "")
            _confirm_btn = "✅ Continuar"
            _change_btn  = "↩️ Otro correo"
            _reg_title   = "#### 📝 Completa tus datos"
            _reg_hint    = "Solo un momento — registro rápido"
            _reg_cont    = "✅ Registrarme y Continuar"
            _reg_back    = "← Volver"

        _mode_k = f"access_mode_{_sfx}"
        if _mode_k not in st.session_state:
            st.session_state[_mode_k] = "email"   # estado inicial: input de email

        _mode = st.session_state[_mode_k]

        # ── Pantalla email (entrada única) ────────────────────────────────────
        if _mode == "email":
            st.markdown(f"##### {_lbl_email}")
            st.caption(_hint_email)
            _ea1, _ea2 = st.columns([4, 1])
            with _ea1:
                _email_input = st.text_input(
                    "email", label_visibility="collapsed",
                    key=f"email_access_{_sfx}",
                    placeholder="nombre@empresa.com",
                )
            with _ea2:
                _cont_clicked = st.button(_btn_cont, type="primary",
                                          use_container_width=True,
                                          key=f"btn_cont_{_sfx}")

            if _cont_clicked:
                _ec = _email_input.strip().lower()
                if not _ec:
                    st.warning("Ingresa tu correo." if lang == "ES" else "Please enter your email.")
                elif _ec in _clients_db:
                    st.session_state[f"found_email_{_sfx}"] = _ec
                    st.session_state[_mode_k] = "welcome"
                    st.rerun()
                else:
                    # Email nuevo: llevar a registro con email guardado
                    st.session_state[f"reg_email_val_{_sfx}"] = _ec
                    st.session_state[_mode_k] = "register"
                    st.rerun()

        # ── Bienvenida cliente existente ──────────────────────────────────────
        elif _mode == "welcome":
            _found_email = st.session_state.get(f"found_email_{_sfx}", "")
            if _found_email and _found_email in _clients_db:
                c   = _clients_db[_found_email]
                _np = len(c.get("pedidos", []))
                st.success(_welcome_txt(c["nombre"], _np))
                _pp = _ped_prev(_np)
                if _pp:
                    st.markdown(_pp)
                _ult = c.get("ultimo_pedido", "")
                if _ult:
                    st.caption(f"{'Last order' if lang=='EN' else 'Último pedido'}: {_ult}")
                bc1, bc2 = st.columns([3, 1])
                with bc1:
                    if st.button(_confirm_btn, type="primary",
                                 use_container_width=True, key=f"btn_confirm_{_sfx}"):
                        st.session_state[_cdata_k] = {
                            "nombre":       c["nombre"],
                            "razon_social": c["razon_social"],
                            "email":        _found_email,
                            "telefono":     c.get("telefono", ""),
                            "last_destino": (c["pedidos"][-1]["destino"]
                                             if c.get("pedidos") else ""),
                        }
                        st.session_state[_verified_k] = True
                        st.session_state[_mode_k]     = "email"
                        # Limpiar widgets de datos para que se pre-rellenen con la nueva cuenta
                        for _wk in [f"cl_name_{_sfx}", f"cl_email_{_sfx}",
                                    f"cl_razon_{_sfx}", f"cl_phone_{_sfx}"]:
                            st.session_state.pop(_wk, None)
                        st.rerun()
                with bc2:
                    if st.button(_change_btn, use_container_width=True,
                                 key=f"btn_change_{_sfx}"):
                        st.session_state[_mode_k] = "email"
                        st.session_state.pop(f"found_email_{_sfx}", None)
                        st.rerun()
            else:
                st.session_state[_mode_k] = "email"
                st.rerun()

        # ── Registro nuevo cliente ────────────────────────────────────────────
        elif _mode == "register":
            _pre_email_val = st.session_state.get(f"reg_email_val_{_sfx}", "")
            st.markdown(_reg_title)
            st.caption(_reg_hint)
            nf1, nf2 = st.columns(2)
            with nf1:
                _ne = st.text_input(
                    "📧 Email", key=f"reg_email_{_sfx}",
                    placeholder="nombre@empresa.com",
                    value=(_pre_email_val
                           if f"reg_email_{_sfx}" not in st.session_state
                           else st.session_state[f"reg_email_{_sfx}"]),
                )
                _nn = st.text_input(T["name"], key=f"new_name_{_sfx}",
                                    placeholder=T["name_ph"])
            with nf2:
                _nr = st.text_input(T["company"], key=f"new_razon_{_sfx}",
                                    placeholder=T["company_ph"])
                _pn = st.text_input(T["phone"], key=f"new_phone_{_sfx}",
                                    placeholder=T["phone_ph"])

            _can_reg = bool(_ne and _nn and _nr)
            if st.button(_reg_cont, type="primary",
                         disabled=not _can_reg, key=f"btn_reg_ok_{_sfx}"):
                _email_reg = _ne.strip().lower()
                st.session_state[_cdata_k] = {
                    "nombre": _nn, "razon_social": _nr,
                    "email":  _email_reg, "telefono": _pn.strip(),
                }
                st.session_state[_verified_k] = True
                st.session_state[_mode_k]     = "email"
                st.session_state.pop(f"reg_email_val_{_sfx}", None)
                for _wk in [f"cl_name_{_sfx}", f"cl_email_{_sfx}",
                            f"cl_razon_{_sfx}", f"cl_phone_{_sfx}"]:
                    st.session_state.pop(_wk, None)
                st.rerun()

            if st.button(_reg_back, key=f"back_from_reg_{_sfx}"):
                st.session_state[_mode_k] = "email"
                st.rerun()

        # No continuar hasta que el cliente se haya identificado
        return

    # ── PASO 2: Datos del cliente ─────────────────────────────────────────────
    _cd = st.session_state.get(_cdata_k, {})

    if standalone:
        # Vista cliente: campos pre-rellenados con los datos del login, editables
        _lbl_datos = "##### 👤 Tus datos" if lang == "ES" else "##### 👤 Your details"
        _lbl_edit  = ("_Puedes editar cualquier campo si es necesario_"
                      if lang == "ES" else
                      "_You can edit any field if needed_")
        st.markdown(_lbl_datos)
        st.caption(_lbl_edit)

        _ci1, _ci2 = st.columns(2)
        with _ci1:
            client_name  = st.text_input(T["name"],   key=f"cl_name_{_sfx}",
                                         value=_cd.get("nombre", ""),
                                         placeholder=T["name_ph"])
            client_email = st.text_input("📧 Email",  key=f"cl_email_{_sfx}",
                                         value=_cd.get("email", ""),
                                         placeholder="nombre@empresa.com")
        with _ci2:
            razon_social = st.text_input(T["company"], key=f"cl_razon_{_sfx}",
                                         value=_cd.get("razon_social", ""),
                                         placeholder=T["company_ph"])
            phone_full   = st.text_input(T["phone"],   key=f"cl_phone_{_sfx}",
                                         value=_cd.get("telefono", ""),
                                         placeholder=T["phone_ph"])

        # Botón cambiar cuenta — limpia todo el estado correctamente
        _logout_lbl = "↩️ Cambiar cuenta" if lang == "ES" else "↩️ Change account"
        if st.button(_logout_lbl, key=f"btn_logout_{_sfx}"):
            st.session_state[_verified_k] = False
            st.session_state[_cdata_k]    = {}
            st.session_state[f"access_mode_{_sfx}"] = "email"
            for _wk in [f"cl_name_{_sfx}", f"cl_email_{_sfx}",
                        f"cl_razon_{_sfx}", f"cl_phone_{_sfx}",
                        f"email_access_{_sfx}", f"found_email_{_sfx}",
                        f"reg_email_val_{_sfx}"]:
                st.session_state.pop(_wk, None)
            st.rerun()

    else:
        # Vista admin: campos directos de texto (siempre vacíos)
        st.markdown("##### 👤 Datos del cliente")
        _ai1, _ai2 = st.columns(2)
        with _ai1:
            client_name  = st.text_input(T["name"],    key="adm_name",
                                         placeholder=T["name_ph"])
            client_email = st.text_input("📧 Email",   key="adm_email",
                                         placeholder="cliente@empresa.com")
        with _ai2:
            razon_social = st.text_input(T["company"], key="adm_razon",
                                         placeholder=T["company_ph"])
            _prefix_labels = [f"{name}  {code}" for name, code in PHONE_PREFIXES]
            _pi_adm = st.selectbox(T["prefix"], range(len(PHONE_PREFIXES)),
                                   format_func=lambda i: _prefix_labels[i],
                                   key="adm_prefix")
            _pn_adm = st.text_input(T["phone"], key="adm_phone",
                                    placeholder=T["phone_ph"])
            phone_full = f"{PHONE_PREFIXES[_pi_adm][1]} {_pn_adm}".strip()

    # ── Destino (primero, para que el cliente vea precios desde el inicio) ──────
    _dest_options = list(cfg_data["destinos"].keys())
    # Pre-seleccionar último destino usado si existe
    _last_dest = _cd.get("last_destino", "") if standalone else ""
    _dest_idx  = (_dest_options.index(_last_dest)
                  if _last_dest in _dest_options else 0)
    # --- Tipo de envio: FOB (sin flete) o CIF (con flete a destino)
    _fob_cif = st.radio(
        "Tipo de envío" if lang == "ES" else "Shipment type",
        ["FOB", "CIF Destino"],
        horizontal=True, key=f"fob_cif_{_sfx}",
        help="FOB: sin flete. CIF Destino: incluye flete al destino."
    )

    if _fob_cif == "CIF Destino":
        ped_dest = st.selectbox(T["dest"], _dest_options, index=_dest_idx, key="cl_dest")
        dest_code, dest_sym = get_dest_currency(ped_dest, cfg_data)
        dest_rate           = fetch_dest_rate(dest_code)
    else:
        ped_dest = None  # FOB: sin destino
        dest_code, dest_sym = "USD", "$"
        dest_rate = 1.0
        st.info("✅ " + ("Precio FOB — sin flete incluido" if lang == "ES" else "FOB price — freight not included"))
    if dest_code == "USD":
        st.info(T["min_order"].format(n=MIN_PALLETS) + "\n\n" + T["currency_usd"])
    else:
        st.info(
            T["min_order"].format(n=MIN_PALLETS) + "\n\n" +
            T["dest_currency"].format(code=dest_code, sym=dest_sym, rate=dest_rate)
        )

    # Nota discreta de precios variables — solo vista cliente
    if standalone:
        _nota = ("📅 Precios y fletes actualizados cada Martes. Simulación orientativa."
                 if lang == "ES" else
                 "📅 Prices and freight updated every Tuesday. Reference simulation.")
        st.caption(_nota)

    st.markdown("---")
    st.markdown(T["products"])

    OPT_PAL = T["opt_pal"]
    OPT_CAJ = T["opt_caj"]
    sfx     = "cl" if standalone else "adm"

    # Solo productos activos (disponibles para pedido)
    products_list = [p for p in products_list if p.get("activo", True)]

    # Cabecera de columnas
    h1, h2, h3, h4 = st.columns([3, 1.8, 1.4, 1])
    h2.markdown(f"<small style='color:#888'>{T['unit_col']}</small>", unsafe_allow_html=True)
    h3.markdown(f"<small style='color:#888'>{T['qty_col']}</small>",  unsafe_allow_html=True)
    h4.markdown(f"<small style='color:#888'>{T['boxes_col']}</small>", unsafe_allow_html=True)

    st.markdown("<hr style='margin:4px 0 8px 0'>", unsafe_allow_html=True)

    active_items  = []
    below_minimum = []   # [(nombre, cajas_pedidas, cajas_minimo)]

    for p in products_list:
        cajas_pal = cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        cod       = p["codigo"]
        min_c     = get_min_cajas(cod, p, cfg_data)

        c1, c2, c3, c4 = st.columns([3, 1.8, 1.4, 1.2])

        with c1:
            st.markdown(f"**{p['producto']}**")
            # Kg por caja + mínimo
            _kg = p.get("kg_caja", 0)
            _kg_str = (f"{int(_kg)} kg/caja" if _kg == int(_kg) else f"{_kg:.1f} kg/caja")
            if lang == "EN":
                _kg_str = _kg_str.replace("caja", "box")
            if min_c > 0:
                if min_c % cajas_pal == 0:
                    pals = min_c // cajas_pal
                    lbl = T["min_pal"].format(n=pals, s="s" if pals>1 else "", c=min_c)
                else:
                    lbl = T["min_caj"].format(n=min_c)
                st.caption(f"{_kg_str} · {lbl}")
            else:
                st.caption(_kg_str)

        with c2:
            unit = st.selectbox(
                "u", [OPT_PAL, OPT_CAJ],
                label_visibility="collapsed",
                key=f"unit_{cod}_{_sfx}",
            )

        with c3:
            is_pal = unit == OPT_PAL
            qty = st.number_input(
                "q",
                min_value=0,
                step=1,
                format="%d",
                label_visibility="collapsed",
                key=f"qty_{cod}_{_sfx}",
            )

        with c4:
            if qty > 0:
                cajas = int(qty) * cajas_pal if is_pal else int(qty)
                if min_c > 0 and cajas < min_c:
                    st.markdown(
                        f"<span style='color:#c62828;font-weight:bold'>⚠ {cajas}</span>",
                        unsafe_allow_html=True,
                    )
                    below_minimum.append((p["producto"], cajas, min_c))
                else:
                    st.markdown(
                        f"<span style='color:#2d6a4f;font-weight:bold'>✓ {cajas}</span>",
                        unsafe_allow_html=True,
                    )
                active_items.append((p, cajas))
            else:
                st.markdown("<span style='color:#ccc'>—</span>", unsafe_allow_html=True)

    active_items = [(p, q) for p, q in active_items if q > 0]

    st.markdown("---")


    # — Notas del cliente (opcional)
    _notas_lbl = "📋 Notas / Observaciones (opcional)" if lang == "ES" else "📋 Notes / Comments (optional)"
    st.text_area(_notas_lbl, key=f"notas_cl_{_sfx}", height=80,
                 placeholder="Fecha preferida de entrega, instrucciones especiales..." if lang == "ES"
                 else "Preferred delivery date, special instructions...")


    # ==== Resumen en tiempo real (sidebar) ====
    with st.sidebar:
        if active_items:
            st.markdown("---")
            st.markdown("### 🛒 " + ("Resumen pedido" if lang == "ES" else "Order Summary"))
            _tot_cajas_rt  = sum(q for p, q in active_items)
            _tot_pallets_rt = sum(
                math.ceil(q / cfg_data["grupos"].get(p["grupo"], {}).get("cajas_pallet", 1))
                for p, q in active_items
            )
            st.metric("📦 Pallets", f"{_tot_pallets_rt:.1f}")
            st.metric("📦 Cajas totales", f"{_tot_cajas_rt:,}")
            for _p, _cj in active_items:
                st.caption(f"\U0001f4e6 {_p['producto']}: {_cj:,} cajas")

    if not active_items:
        st.caption(T["hint"])
        return

    total_cajas = sum(q for _, q in active_items)
    group_cajas = {}
    for p, q in active_items:
        g = p["grupo"]
        group_cajas[g] = group_cajas.get(g, 0) + q
    total_pallets = sum(
        math.ceil(c / cfg_data["grupos"][g]["cajas_pallet"])
        for g, c in group_cajas.items()
    )

    # Barra de progreso
    faltan = max(0, MIN_PALLETS - total_pallets)
    pct = min(total_pallets / MIN_PALLETS, 1.0)
    if total_pallets < MIN_PALLETS:
        st.progress(pct, text=T["progress_low"].format(
            n=total_pallets, min=MIN_PALLETS, f=faltan, s="s" if faltan!=1 else ""))
    else:
        st.progress(1.0, text=T["progress_ok"].format(n=total_pallets))

    # Divisa local del destino
    dest_code, dest_sym = get_dest_currency(ped_dest, cfg_data)
    dest_rate           = fetch_dest_rate(dest_code)
    show_local          = dest_code not in ("USD",)
    loc_total_col       = f"Total {dest_sym}{dest_code}" if show_local else None

    tarifa_dest = cfg_data["destinos"].get(ped_dest, 0) if ped_dest else 0

    rows = []
    for p, cajas in active_items:
        r         = calc_pedido(p, cfg_data, ped_dest, total_cajas)
        cajas_pal = cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        row = {
            "Producto":      p["producto"],
            "Pallets":       round(cajas / cajas_pal, 2),
            "Cajas":         cajas,
            "Precio/caja $": r["precio_caja_usd"],
            "Total USD":     r["precio_caja_usd"] * cajas,
        }
        if show_local:
            row[f"{dest_sym}/caja"] = r["precio_caja_usd"] * dest_rate
            row[loc_total_col]      = r["precio_caja_usd"] * cajas * dest_rate
        rows.append(row)

    sum_df    = pd.DataFrame(rows)
    total_usd = sum_df["Total USD"].sum()
    total_loc = sum_df[loc_total_col].sum() if show_local else None
    peso_kg   = sum(p["kg_caja"] * q for p, q in active_items)

    # Métricas resumen
    if show_local and total_loc:
        _mcols = st.columns(5)
        _mcols[0].metric(T["pallets_m"], str(total_pallets))
        _mcols[1].metric(T["cajas_m"],   f"{total_cajas:,}")
        _mcols[2].metric(T["weight_m"],  f"{peso_kg:,.0f} kg")
        _mcols[3].metric("Total USD",    f"${total_usd:,.2f}")
        _mcols[4].metric(f"Total {dest_code}", f"{dest_sym}{total_loc:,.2f}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(T["pallets_m"], str(total_pallets))
        c2.metric(T["cajas_m"],   f"{total_cajas:,}")
        c3.metric(T["weight_m"],  f"{peso_kg:,.0f} kg")
        c4.metric("Total USD",    f"${total_usd:,.2f}")

    # Tarifa de flete del destino — info complementaria
    if ped_dest:  # solo mostrar tarifa cuando es CIF
        _flete_info = (f"🚢 Tarifa flete {ped_dest}: **{tarifa_dest:.2f} USD/kg** · CIF destino"
                       if lang == "ES" else
                       f"🚢 Freight rate {ped_dest}: **{tarifa_dest:.2f} USD/kg** · CIF destination")
        st.caption(_flete_info)

    def hl(col):
        return ["background-color:#e8f5e9;font-weight:bold"] * len(col) if "Total" in col.name else [""] * len(col)

    fmt = {"Pallets": "{:.2f}", "Cajas": "{:,.0f}", "Precio/caja $": "${:.2f}", "Total USD": "${:.2f}"}
    if show_local:
        fmt[f"{dest_sym}/caja"] = f"{dest_sym}{{:.2f}}"
        fmt[loc_total_col]      = f"{dest_sym}{{:.2f}}"

    st.dataframe(
        sum_df.style.apply(hl, axis=0).format(fmt),
        use_container_width=True, hide_index=True,
    )

    with st.expander("📦 Detalle de pallets por grupo"):
        pal_rows = []
        for g, c in group_cajas.items():
            cap  = cfg_data["grupos"][g]["cajas_pallet"]
            pals = math.ceil(c / cap)
            pal_rows.append({
                "Grupo": g, "Productos": cfg_data["grupos"][g]["nombre"],
                "Cajas": c, "Cajas/pallet": cap, "Pallets físicos": pals,
                "Ocupación": f"{c/(pals*cap)*100:.1f}%",
            })
        st.dataframe(pd.DataFrame(pal_rows), hide_index=True, use_container_width=True)

    st.markdown("---")

    # ── Confirmar ──
    confirm_key   = "confirm_cl" if standalone else "confirm_admin"
    albaran_key   = f"albaran_{confirm_key}"
    _email_sent_key = f"email_sent_{confirm_key}"
    can_confirm   = (total_pallets >= MIN_PALLETS
                     and bool(client_name) and bool(razon_social)
                     and bool(client_email))

    if not client_name or not razon_social or not client_email:
        st.warning(T["warn_fields"])
    elif total_pallets < MIN_PALLETS:
        st.warning(T["warn_pallets"].format(f=faltan, s="s" if faltan!=1 else "", min=MIN_PALLETS))
    if below_minimum:
        for nombre, pedido, minimo in below_minimum:
            st.error(T["below_min"].format(prod=nombre, got=pedido, need=minimo))

    can_confirm = can_confirm and len(below_minimum) == 0

    if st.button(T["confirm_btn"], type="primary", disabled=not can_confirm, key=confirm_key):
        with st.spinner("Procesando pedido..."):
            # Guardar todo lo necesario en session_state — independiente del estado del formulario
            cod_map = {p["codigo"]: p for p in products_list}
            st.session_state[albaran_key] = {
            "client_name":  client_name,
            "razon_social": razon_social,
            "email":        client_email,
            "telefono":     phone_full,
            "destino":      ped_dest,
            "notas_cliente":   st.session_state.get(f"notas_cl_{_sfx}", ""),
            "estado":          "Recibido",
            "ai_codigos":   [(p["codigo"], q) for p, q in active_items],
            "total_cajas":  total_cajas,
            "total_pallets": total_pallets,
            "total_usd":    total_usd,
            "total_loc":    total_loc,
            "dest_code":    dest_code,
            "dest_sym":     dest_sym,
            "dest_rate":    dest_rate,
            "lang":         lang,
            }

    # ── Mostrar albarán (persiste aunque el formulario cambie) ──
    saved = st.session_state.get(albaran_key)
    if saved:
        _Ts = TR.get(saved.get("lang","ES"), TR["ES"])
        st.success(_Ts["confirmed_ok"].format(name=saved["client_name"], dest=saved["destino"]))
        st.info("📋 Pedido #" + str(saved.get("id", "")) + " registrado correctamente.")

        cod_map = {p["codigo"]: p for p in products_list}
        ai_full = [(cod_map[c], q) for c, q in saved["ai_codigos"] if c in cod_map]

        try:
            _dc   = saved.get("dest_code","USD")
            _ds   = saved.get("dest_sym","$")
            _dr   = saved.get("dest_rate", 1.0)
            _lang = saved.get("lang","ES")
            pdf_bytes = gen_albaran_pdf(
                saved["client_name"], saved["razon_social"], saved["destino"],
                ai_full, saved["total_cajas"], saved["total_pallets"],
                saved["total_usd"], cfg_data,
                client_email=saved.get("email",""),
                telefono=saved.get("telefono",""),
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr, lang=_lang,
                total_flete=saved.get("total_flete", 0.0),
            )
            wa_text = gen_wa_text(
                saved["client_name"], saved["razon_social"], saved["destino"],
                ai_full, saved["total_cajas"], saved["total_pallets"],
                saved["total_usd"], cfg_data,
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr, lang=_lang,
            )
            # Añadir datos de contacto al mensaje WhatsApp
            extra = []
            if saved.get("email"):    extra.append(f"📧 {saved['email']}")
            if saved.get("telefono"): extra.append(f"📞 {saved['telefono']}")
            if extra:
                wa_text = wa_text.replace("━━━━━━━━━━━━━━━━━━━━━\n*PRODUCTOS:*",
                    "━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(extra) +
                    "\n━━━━━━━━━━━━━━━━━━━━━\n*PRODUCTOS:*")

            fname    = f"Albaran_{saved['client_name'].replace(' ','_')}_{date.today()}.pdf"
            wa_url   = "https://wa.me/?text=" + urllib.parse.quote(wa_text)
            subj     = urllib.parse.quote(f"Pedido Export Haret – {saved['client_name']}")
            body     = urllib.parse.quote(wa_text.replace("*", ""))
            mail_url = f"mailto:order@exportharet.com?subject={subj}&body={body}"

            # ── Registrar cliente y pedido ────────────────────────────────────
            register_order(saved, ai_full, cfg_data)

            # — Envío automático por SMTP (solo una vez) ————————————————————
            if not st.session_state.get(_email_sent_key, False):
                email_ok, email_msg = send_order_email(saved, ai_full, pdf_bytes, cfg_data, wa_text)
                if email_ok:
                    st.success(_Ts["email_auto_ok"])
                    st.session_state[_email_sent_key] = True
                elif email_msg == "sin_smtp":
                    st.info(_Ts["email_no_smtp"])
                    st.session_state[_email_sent_key] = True
                else:
                    st.warning(_Ts["email_error"].format(e=email_msg))

            ba1, ba2, ba3, ba4 = st.columns([2, 2, 2, 1])
            with ba1:
                st.download_button(_Ts["pdf_btn"], pdf_bytes,
                                   file_name=fname, mime="application/pdf",
                                   use_container_width=True)
            with ba2:
                st.link_button(_Ts["wa_btn"], wa_url, use_container_width=True)
            with ba3:
                st.link_button(_Ts["mail_btn"], mail_url, use_container_width=True)
            with ba4:
                if st.button(_Ts["new_btn"], key=f"new_{confirm_key}", use_container_width=True):
                    del st.session_state[albaran_key]
                    st.session_state.pop(_email_sent_key, None)
                    st.rerun()
        except Exception as e:
            st.error(f"Error generando el albarán: {e}")


# ── Historial de pedidos del cliente ─────────────────────────────────────────

def render_order_history(client_email: str, lang: str = "ES"):
    """Muestra los pedidos anteriores de un cliente con estados visuales."""
    clients = load_clients()
    data    = load_data()
    c       = clients.get(client_email, {})
    pedidos = c.get("pedidos", [])

    if lang == "EN":
        titulo    = "### 📋 Your Orders"
        sin_ped   = "You have no previous orders yet."
        lbl_tot   = "Total USD"
        lbl_pal   = "Pallets"
        lbl_cajas = "Boxes"
        lbl_prod  = "**Products:**"
        lbl_estado = "Status"
        lbl_notas  = "Notes"
        lbl_fecha  = "Date"
    else:
        titulo    = "### 📋 Mis Pedidos"
        sin_ped   = "Aún no tienes pedidos anteriores."
        lbl_tot   = "Total USD"
        lbl_pal   = "Pallets"
        lbl_cajas = "Cajas"
        lbl_prod  = "**Productos:**"
        lbl_estado = "Estado"
        lbl_notas  = "Notas"
        lbl_fecha  = "Fecha"

    st.markdown(titulo)
    if not pedidos:
        st.info(sin_ped)
        return

    for ped in reversed(pedidos):
        ped_id   = ped.get("id", "").upper()
        ped_dest = ped.get("destino", "")
        ped_tot  = ped.get("total_usd", 0)
        ped_pals = ped.get("num_pallets", ped.get("pallets", 0))
        ped_caj  = sum(p.get("cajas", 0) for p in ped.get("productos", []))
        ped_fecha= ped.get("fecha", ped.get("date", ""))[:10]
        ped_notas= ped.get("notas", ped.get("notes", ""))
        _e_estado = ped.get("estado", "Recibido")
        icono_e  = ORDEN_ESTADOS_COLORES.get(_e_estado, "📦")
        _e_colors = {
            "Recibido":       "blue",
            "Confirmado":     "orange",
            "En preparación": "orange",
            "Enviado":        "violet",
            "Entregado":      "green",
        }
        badge_color = _e_colors.get(_e_estado, "blue")
        # Barra de progreso
        try:
            prog_idx = ORDEN_ESTADOS.index(_e_estado)
        except ValueError:
            prog_idx = 0
        prog_pct = int((prog_idx / (len(ORDEN_ESTADOS)-1)) * 100)
        
        lbl_en = ORDEN_ESTADOS_EN.get(_e_estado, _e_estado) if lang == "EN" else _e_estado
        
        with st.expander(f"{icono_e} **#{ped_id}** — {ped_dest} | {ped_fecha} | :{badge_color}[{lbl_en}]", expanded=False):
            st.progress(prog_pct, text=f"{lbl_estado}: {lbl_en}")
            col1, col2, col3 = st.columns(3)
            col1.metric(lbl_tot,   f"${ped_tot:,.2f}")
            col2.metric(lbl_pal,   ped_pals)
            col3.metric(lbl_cajas, ped_caj)
            prods = ped.get("productos", [])
            if prods:
                st.markdown(lbl_prod)
                for p in prods:
                    pnom = p.get("nombre", p.get("name", p.get("codigo", "")))
                    pcaj = p.get("cajas", 0)
                    ppal = p.get("pallets", 0)
                    st.markdown(f"  - {pnom}: {pcaj} cajas / {ppal} pallets")
            if ped_notas:
                st.caption(f"📝 {lbl_notas}: {ped_notas}")
            # Botón eliminar (solo si no está entregado/enviado)
            if _e_estado not in ("Enviado", "Entregado"):
                _del_key = f"del_cl_{ped['id']}"
                _c_del, _c_cost = st.columns([1, 2])
                with _c_del:
                    if st.button("🗑️ Eliminar", key=_del_key, type="secondary", use_container_width=True):
                        st.session_state[f"confirm_del_cl_{ped['id']}"] = True
                if st.session_state.get(f"confirm_del_cl_{ped['id']}", False):
                    st.warning(f"¿Eliminar pedido #{ped_id}? No se puede deshacer.")
                    _cc1, _cc2 = st.columns(2)
                    with _cc1:
                        if st.button("✅ Sí, eliminar", key=f"yes_cl_{ped['id']}", type="primary"):
                            _cls2 = load_clients()
                            if client_email in _cls2:
                                _cls2[client_email]["pedidos"] = [o for o in _cls2[client_email].get("pedidos", []) if o.get("id") != ped["id"]]
                                save_clients(_cls2)
                            send_cancel_email(ped)
                            del st.session_state[f"confirm_del_cl_{ped['id']}"]
                            st.success("Pedido eliminado."); st.rerun()
                    with _cc2:
                        if st.button("❌ Cancelar", key=f"no_cl_{ped['id']}"):
                            del st.session_state[f"confirm_del_cl_{ped['id']}"]
                            st.rerun()

# ── Vista cliente (URL ?view=cliente) ─────────────────────────────────────────

# --- Cargar datos globales (disponibles en vista cliente y admin) ---
data     = load_data()
cfg      = data["config"]
products = data.get("products", [])

IS_CLIENT = st.query_params.get("view", "") == "cliente"

if IS_CLIENT:
    _verified = st.session_state.get("client_verified_cl", False)
    _cdata    = st.session_state.get("client_data_cl", {})

    if not _verified:
        # ── Pantalla de acceso/registro ────────────────────────────────────────
        render_order_form(cfg, products, standalone=True,
                          show_header=True, require_email=True)
    else:
        # ── Portal del cliente (ya identificado) ───────────────────────────────
        _lang = "EN" if "EN" in st.session_state.get("order_lang", "🇪🇸 ES") else "ES"

        # Cabecera: logo centrado
        _lp = os.path.join(os.path.dirname(__file__), "logo.png")
        _pc1, _pc2, _pc3 = st.columns([1, 2, 1])
        with _pc2:
            if os.path.exists(_lp):
                st.image(_lp, width=200)

        # Barra de bienvenida + logout
        _ph1, _ph2 = st.columns([5, 1])
        with _ph1:
            st.markdown(
                f"👤 **{_cdata.get('nombre','')}** &nbsp;|&nbsp; "
                f"🏢 {_cdata.get('razon_social','')} &nbsp;|&nbsp; "
                f"📧 {_cdata.get('email','')} &nbsp;|&nbsp; "
                f"📞 {_cdata.get('telefono','—')}"
            )
        with _ph2:
            _exit_lbl = "🚪 Salir" if _lang == "ES" else "🚪 Exit"
            if st.button(_exit_lbl, key="portal_exit", use_container_width=True):
                st.session_state["client_verified_cl"] = False
                st.session_state["client_data_cl"]     = {}
                st.rerun()

        st.markdown("---")

        # Tabs: Nuevo Pedido | Mis Pedidos
        if _lang == "EN":
            _tab1, _tab2 = st.tabs(["🛒 New Order", "📋 My Orders"])
        else:
            _tab1, _tab2 = st.tabs(["🛒 Nuevo Pedido", "📋 Mis Pedidos"])

        with _tab1:
            render_order_form(cfg, products, standalone=True,
                              show_header=False, require_email=False)
        with _tab2:
            render_order_history(_cdata.get("email", ""), lang=_lang)

    st.stop()

# ── Autenticación admin ────────────────────────────────────────────────────────
def _get_cred(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        # Fallback: leer del secrets.toml local
        _sp = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        if os.path.exists(_sp):
            for line in open(_sp):
                if key in line and "=" in line:
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        return default

ADMIN_USER = _get_cred("ADMIN_USER", "exportharet")
ADMIN_PASS = _get_cred("ADMIN_PASS", "Haret2026$")

if "admin_ok" not in st.session_state:
    st.session_state.admin_ok = False

if not st.session_state.admin_ok:
    # ── Pantalla de login ──────────────────────────────────────────────────
    _logo_login = os.path.join(os.path.dirname(__file__), "logo.png")
    lc1, lc2, lc3 = st.columns([1, 2, 1])
    with lc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if os.path.exists(_logo_login):
            st.image(_logo_login, width=220)
        st.markdown("## Panel de administración")
        st.markdown("---")
        with st.form("login_form"):
            usr = st.text_input("👤 Usuario",  placeholder="exportharet")
            pwd = st.text_input("🔒 Contraseña", type="password", placeholder="••••••••")
            ok  = st.form_submit_button("Iniciar sesión", type="primary",
                                         use_container_width=True)
            if ok:
                if usr == ADMIN_USER and pwd == ADMIN_PASS:
                    st.session_state.admin_ok = True
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")

        st.markdown(
            "<center><small style='color:#aaa'>¿Cliente? Accede al formulario de pedido en<br>"
            f"<a href='{get_network_url(8501)}/?view=cliente' target='_blank'>"
            "exportharet-pedidos.streamlit.app/?view=cliente</a></small></center>",
            unsafe_allow_html=True,
        )
    st.stop()

# ── Sidebar (solo admin) ───────────────────────────────────────────────────────
with st.sidebar:
    # Logo: usa archivo local si existe, si no placeholder verde
    _logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(_logo_path):
        st.image(_logo_path, use_container_width=True)
    else:
        st.image("https://placehold.co/220x70/2d6a4f/white?text=Export+Haret", use_container_width=True)
    st.markdown("---")
    destino = st.selectbox("🌍 Destino", list(cfg["destinos"].keys()))
    num_pallets = st.slider("📦 Pallets", 1, 23, 1)
    st.markdown("---")
    st.markdown(
        f"**1 EUR = {cfg['eur_usd']:.4f} USD**  \n"
        f"<small>{cfg.get('_rate_label','')}</small>",
        unsafe_allow_html=True,
    )
    st.caption(f"Tarifa: **{cfg['destinos'][destino]} USD/kg**")
    st.caption(f"Vigente: {date.today().strftime('%d/%m/%Y')}")
    st.markdown("---")
    st.caption(f"👤 {ADMIN_USER}")
    if st.button("🚪 Cerrar sesión", use_container_width=True):
        st.session_state.admin_ok = False
        st.rerun()

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🌿 Export Haret — Pedidos")
st.markdown(
    f"**Destino:** {destino} &nbsp;|&nbsp; "
    f"**1 EUR = {cfg['eur_usd']:.4f} USD** &nbsp;"
    f"<small style='color:#888'>{cfg.get('_rate_label','')}</small>",
    unsafe_allow_html=True,
)

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Dashboard", "📋 Cotización", "🛒 Hacer pedido", "✏️ Actualizar precios", "🌐 Todos los destinos", "⚙️ Configuración", "👥 Clientes", "📦 Pedidos"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — COTIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════
with tab0:
    # ── DASHBOARD RESUMEN ────────────────────────────────────────────────────────────────────
    st.markdown("## 📊 Dashboard de Pedidos")
    _dash_clients = load_clients()
    _all_peds = []
    for _ce, _cd in _dash_clients.items():
        for _p in _cd.get("pedidos", []):
            _all_peds.append({**_p, "_client_email": _ce})
    import datetime as _dt
    _hoy      = _dt.date.today()
    _semana   = _hoy - _dt.timedelta(days=7)
    _mes      = _hoy - _dt.timedelta(days=30)
    _peds_sem = [p for p in _all_peds if p.get("fecha", p.get("date",""))[:10] >= str(_semana)]
    _peds_mes = [p for p in _all_peds if p.get("fecha", p.get("date",""))[:10] >= str(_mes)]
    _pendientes = [p for p in _all_peds if p.get("estado","Recibido") in ("Recibido","Confirmado","En preparación")]
    _enviados   = [p for p in _all_peds if p.get("estado","Recibido") == "Enviado"]
    _entregados = [p for p in _all_peds if p.get("estado","Recibido") == "Entregado"]
    _vol_sem  = sum(p.get("total_usd",0) for p in _peds_sem)
    _vol_mes  = sum(p.get("total_usd",0) for p in _peds_mes)
    _vol_tot  = sum(p.get("total_usd",0) for p in _all_peds)
    # KPIs
    st.markdown("### 📅 Resumen rápido")
    _kc1, _kc2, _kc3, _kc4 = st.columns(4)
    _kc1.metric("📦 Total pedidos",   len(_all_peds))
    _kc2.metric("⏳ Esta semana",          len(_peds_sem), delta=f"${_vol_sem:,.0f}")
    _kc3.metric("📆 Este mes",         len(_peds_mes), delta=f"${_vol_mes:,.0f}")
    _kc4.metric("💵 Volumen total",    f"${_vol_tot:,.2f}")
    st.markdown("---")
    # Estado breakdown
    st.markdown("### 📋 Estado de pedidos")
    _ec1, _ec2, _ec3, _ec4, _ec5 = st.columns(5)
    _cnt_e = {e: sum(1 for p in _all_peds if p.get("estado","Recibido")==e) for e in ORDEN_ESTADOS}
    _ec1.metric("🔵 Recibidos",       _cnt_e.get("Recibido",0))
    _ec2.metric("🟡 Confirmados",      _cnt_e.get("Confirmado",0))
    _ec3.metric("🟠 En preparación", _cnt_e.get("En preparación",0))
    _ec4.metric("🚀 Enviados",          _cnt_e.get("Enviado",0))
    _ec5.metric("✅ Entregados",            _cnt_e.get("Entregado",0))
    st.markdown("---")
    # Pedidos pendientes urgentes
    if _pendientes:
        st.markdown(f"### ⚠️ Pedidos pendientes de gestión ({len(_pendientes)})")
        for _pp in sorted(_pendientes, key=lambda x: x.get("fecha",""))[:10]:
            _pid   = _pp.get("id","").upper()
            _pest  = _pp.get("estado","Recibido")
            _pico  = ORDEN_ESTADOS_COLORES.get(_pest,"📦")
            _pdest = _pp.get("destino","")
            _pfech = _pp.get("fecha", _pp.get("date",""))[:10]
            _pcli  = _pp.get("client_name", _pp.get("_client_email",""))
            _ptot  = _pp.get("total_usd",0)
            st.markdown(f"- {_pico} **#{_pid}** | {_pcli} | {_pdest} | {_pfech} | `{_pest}` | **${_ptot:,.2f}**")
    else:
        st.success("✅ No hay pedidos pendientes. ¡Todo gestionado!")

with tab1:
    pal_usd_col = f"USD {num_pallets} Pal"
    pal_eur_col = f"EUR {num_pallets} Pal"

    rows = []
    for p in products:
        r = calc(p, cfg, destino, num_pallets)
        rows.append({
            "Código": p["codigo"],
            "Producto": p["producto"],
            "kg/caja": p["kg_caja"],
            "Compra $": p["precio_compra"],
            "Costo caja": r["Costo caja"],
            "FOB base": r["FOB base"],
            "FOB+Merma": r["FOB + Merma"],
            "Margen %": r["Margen %"],
            "FOB Final": r["FOB Final"],
            "Flete": r["Flete"],
            "CIF USD": r["CIF USD"],
            "CIF $/kg": r["CIF $/kg"],
            pal_usd_col: r["Pal USD"],
            pal_eur_col: r["Pal EUR"],
        })

    df = pd.DataFrame(rows)

    def highlight_cols(col):
        if "CIF" in col.name or "Pal" in col.name:
            return ["background-color: #e8f5e9; font-weight: bold"] * len(col)
        return [""] * len(col)

    styled = (
        df.style
        .apply(highlight_cols, axis=0)
        .format({
            "kg/caja": "{:.2f}",
            "Compra $": "${:.2f}",
            "Costo caja": "${:.4f}",
            "FOB base": "${:.4f}",
            "FOB+Merma": "${:.4f}",
            "Margen %": "{:.1%}",
            "FOB Final": "${:.4f}",
            "Flete": "${:.4f}",
            "CIF USD": "${:.4f}",
            "CIF $/kg": "${:.4f}",
            pal_usd_col: "${:.2f}",
            pal_eur_col: "€{:.2f}",
        })
    )

    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Summary metrics (reusar filas ya calculadas)
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    pal_usd_vals = df[pal_usd_col].tolist()
    pal_eur_vals = df[pal_eur_col].tolist()
    col1.metric("Precio mínimo (USD)", f"${min(pal_usd_vals):.2f}")
    col2.metric("Precio máximo (USD)", f"${max(pal_usd_vals):.2f}")
    col3.metric("Precio mínimo (EUR)", f"€{min(pal_eur_vals):.2f}")
    col4.metric("Precio máximo (EUR)", f"€{max(pal_eur_vals):.2f}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — HACER PEDIDO
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    render_order_form(cfg, products, standalone=False, require_email=False)

    # ── Panel de enlace para cliente ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔗 Compartir formulario de pedido con el cliente")

    # Usar siempre la URL pública configurada (Streamlit Cloud)
    base_url   = cfg.get("public_url", "https://exportharet-pedidos.streamlit.app").rstrip("/")
    client_url = f"{base_url}/?view=cliente"

    cl1, cl2 = st.columns([3, 1])
    with cl1:
        st.info(
            f"Comparte este enlace con el cliente para que acceda directamente "
            f"al formulario de pedido sin ver ningún panel de administración:\n\n"
            f"**`{client_url}`**"
        )
        # Botones de compartir el enlace
        wa_share = "https://wa.me/?text=" + urllib.parse.quote(
            f"¡Consulta los precios mediante una simulación de Orden!\n{client_url}"
        )
        mail_share = (
            "mailto:?subject=" + urllib.parse.quote("Formulario de pedido — Export Haret")
            + "&body=" + urllib.parse.quote(
                f"Hola,\n\nAccede al siguiente enlace para realizar tu pedido:\n\n{client_url}\n\nSaludos,\nExport Haret"
            )
        )
        sb1, sb2 = st.columns(2)
        with sb1:
            st.link_button("📱 Compartir por WhatsApp", wa_share, use_container_width=True)
        with sb2:
            st.link_button("📧 Compartir por Email", mail_share, use_container_width=True)

    with cl2:
        # QR code
        try:
            qr = qrcode.QRCode(version=1, box_size=4, border=2)
            qr.add_data(client_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="#2d6a4f", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Escanear para abrir", use_container_width=True)
        except Exception:
            st.caption("QR no disponible")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ACTUALIZAR PRECIOS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown("### ✏️ Actualizar precios de compra")

    # ── Leer precios del Excel si existe ──────────────────────────────────────
    _XLS = Path(os.path.dirname(__file__)) / "Documentacion" / "Precios" / "Cotizaciones.xlsx"
    _excel_prices = {}   # {codigo: precio_excel}

    if _XLS.exists():
        try:
            _wb  = load_workbook(io.BytesIO(_XLS.read_bytes()), data_only=True)
            _wsp = _wb["TABLA PRECIOS"]
            _COL = {
                4:"F-PSG10",5:"F-PN016",6:"F-PPA01",7:"F-PSR02",8:"F-PSR05",
                9:"F-PSM09",10:"F-TAS04",11:"F-GNB010",12:"F-MPS03",13:"F-CCN017",
                14:"F-BCC013",15:"F-AHSS012",16:"F-BBB06",17:"F-ZPT020",
                18:"F-TX020",19:"F-UVP08",20:"F-UVP07",
            }
            for col, cod in _COL.items():
                last = None
                for r in range(32, 84):
                    v = _wsp.cell(row=r, column=col).value
                    if isinstance(v, (int, float)) and v > 0:
                        last = float(v)
                if last:
                    _excel_prices[cod] = last

            # Estado de sincronización
            _diffs = [p for p in products
                      if p["codigo"] in _excel_prices
                      and abs(p["precio_compra"] - _excel_prices[p["codigo"]]) > 0.001]

            xc1, xc2 = st.columns([4, 1])
            with xc1:
                if _diffs:
                    st.warning(
                        f"⚠️ El Excel tiene **{len(_diffs)} precio(s) diferente(s)** "
                        f"a la app. Las filas en 🟡 amarillo son los cambios pendientes."
                    )
                else:
                    st.success("✅ Los precios de la app están sincronizados con el Excel.")
            with xc2:
                _xls_mtime = datetime.fromtimestamp(_XLS.stat().st_mtime)
                st.caption(f"Excel actualizado:\n**{_xls_mtime.strftime('%d/%m %H:%M')}**")

        except Exception as e:
            st.info(f"No se pudo leer el Excel: {e}")
    else:
        st.info(
            "💡 Conecta el Excel para sincronización automática. "
            "El archivo debe estar en:\n"
            f"`{_XLS}`"
        )

    st.markdown("---")

    # ── Tabla de precios (con precios Excel si disponibles) ───────────────────
    edit_rows = []
    for p in products:
        excel_p = _excel_prices.get(p["codigo"])
        edit_rows.append({
            "Código":                  p["codigo"],
            "Producto":                p["producto"],
            "kg/caja":                 p["kg_caja"],
            "Precio app (USD)":        p["precio_compra"],
            "Precio Excel (USD)":      excel_p if excel_p else p["precio_compra"],
            "Margen %":                round(p["margen_pct"] * 100, 1),
            "Grupo":                   p["grupo"],
        })

    edit_df = pd.DataFrame(edit_rows)

    # Resaltar filas donde Excel ≠ app
    def _hl_diff(row):
        cod     = row["Código"]
        excel_v = _excel_prices.get(cod)
        app_v   = row["Precio app (USD)"]
        if excel_v and abs(app_v - excel_v) > 0.001:
            return ["background-color:#fff9c4"] * len(row)
        return [""] * len(row)

    cols_disabled = ["Código", "Producto", "kg/caja", "Grupo", "Precio Excel (USD)"]
    if not _excel_prices:
        cols_disabled.append("Precio Excel (USD)")

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        disabled=cols_disabled,
        column_config={
            "Precio app (USD)":   st.column_config.NumberColumn(
                "Precio app $", min_value=0.0, step=0.01, format="$%.2f",
                help="Precio actual en la app — editable"),
            "Precio Excel (USD)": st.column_config.NumberColumn(
                "Precio Excel $", format="$%.2f",
                help="Último precio del historial en Cotizaciones.xlsx — solo lectura"),
            "Margen %": st.column_config.NumberColumn(
                "Margen %", min_value=0.0, max_value=100.0, step=0.5, format="%.1f%%"),
        },
        key="price_editor",
    )

    if _excel_prices and edit_df.style.apply(_hl_diff, axis=1):
        st.caption("🟡 Filas amarillas = precio diferente entre Excel y app")

    # ── Botones de acción ─────────────────────────────────────────────────────
    b1, b2, b3, b4 = st.columns([2, 2, 2, 2])

    with b1:
        if st.button("💾 Guardar cambios", type="primary", use_container_width=True):
            for i, row in edited.iterrows():
                products[i]["precio_compra"] = float(row["Precio app (USD)"])
                products[i]["margen_pct"]    = float(row["Margen %"]) / 100.0
            save_data(data)
            st.success("✅ Guardado.")
            st.rerun()

    with b2:
        if _excel_prices and st.button("📊 Aplicar precios Excel",
                                        use_container_width=True,
                                        help="Copia los precios del Excel a la app"):
            changed = 0
            for p in products:
                if p["codigo"] in _excel_prices:
                    new_p = _excel_prices[p["codigo"]]
                    if abs(p["precio_compra"] - new_p) > 0.001:
                        p["precio_compra"] = new_p
                        changed += 1
            save_data(data)
            st.success(f"✅ {changed} precio(s) actualizados desde Excel.")
            st.rerun()

    with b3:
        if st.button("🚀 Guardar y Publicar",
                     use_container_width=True,
                     help="Guarda los cambios y los publica en Streamlit Cloud"):
            for i, row in edited.iterrows():
                products[i]["precio_compra"] = float(row["Precio app (USD)"])
                products[i]["margen_pct"]    = float(row["Margen %"]) / 100.0
            save_data(data)
            # Publicar via GitHub API
            try:
                _tok = st.secrets.get("GITHUB_TOKEN","") if hasattr(st,"secrets") else ""
                if not _tok:
                    _sp = os.path.join(os.path.dirname(__file__),".streamlit","secrets.toml")
                    if os.path.exists(_sp):
                        for _l in open(_sp):
                            if "GITHUB_TOKEN" in _l:
                                _tok = _l.split("=",1)[1].strip().strip('"').strip("'")
                if _tok:
                    _hdrs  = {"Authorization":f"token {_tok}","Accept":"application/vnd.github.v3+json"}
                    _aurl  = "https://api.github.com/repos/expharet/app-de-pedidos/contents/precios_data.json"
                    _cnt   = base64.b64encode(json.dumps(data,indent=2,ensure_ascii=False).encode()).decode()
                    _sha   = requests.get(_aurl,headers=_hdrs,timeout=10).json()["sha"]
                    _r     = requests.put(_aurl,headers=_hdrs,timeout=20,json={
                        "message": f"Actualizar precios — {date.today().strftime('%d/%m/%Y')}",
                        "content": _cnt, "sha": _sha})
                    if _r.status_code in (200,201):
                        st.success("🚀 Publicado en Streamlit Cloud — activo en ~1 min.")
                    else:
                        st.error("Error publicando.")
                else:
                    st.warning("Token GitHub no configurado.")
            except Exception as _e:
                st.error(f"Error: {_e}")

    with b4:
        if st.button("↩️ Restablecer originales", use_container_width=True):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.session_state.data = json.loads(json.dumps(INITIAL_DATA))
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TODOS LOS DESTINOS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown("### Comparación de precios — Todos los destinos")
    currency = st.radio("Moneda", ["USD", "EUR"], horizontal=True)
    pals_all = st.slider("Pallets", 1, 23, 1, key="pals_all")

    all_rows = []
    for p in products:
        row = {"Producto": p["producto"], "kg/caja": p["kg_caja"]}
        for dest in cfg["destinos"]:
            r = calc(p, cfg, dest, pals_all)
            v = r["Pal EUR"] if currency == "EUR" else r["Pal USD"]
            sym = "€" if currency == "EUR" else "$"
            row[dest] = v
        all_rows.append(row)

    adf = pd.DataFrame(all_rows)
    dest_cols = list(cfg["destinos"].keys())

    def color_by_value(val):
        if not isinstance(val, float):
            return ""
        return ""

    sym = "€" if currency == "EUR" else "$"
    fmt_dict = {c: f"{sym}{{:.2f}}" for c in dest_cols}

    # highlight min/max per row
    def highlight_minmax(row):
        styles = [""] * len(row)
        numeric = [(i, row[c]) for i, c in enumerate(row.index) if c in dest_cols]
        if not numeric:
            return styles
        vals = [v for _, v in numeric]
        mn, mx = min(vals), max(vals)
        for i, v in numeric:
            if v == mn:
                styles[i] = "background-color: #c8e6c9; font-weight: bold"
            elif v == mx:
                styles[i] = "background-color: #ffcdd2"
        return styles

    styled_all = adf.style.apply(highlight_minmax, axis=1).format(fmt_dict)
    st.dataframe(styled_all, use_container_width=True, hide_index=True)
    st.caption("🟢 Precio más bajo por producto &nbsp;|&nbsp; 🔴 Precio más alto por producto")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown("### Parámetros generales")

    c1, c2 = st.columns(2)
    with c1:
        new_eur_usd = st.number_input("EUR / USD (tipo de cambio)", value=cfg["eur_usd"], step=0.001, format="%.4f")
        new_due = st.number_input("DUE (USD / envío)", value=cfg["due"], step=1.0)
        new_ti = st.number_input("Transporte interno (USD / envío)", value=cfg["transporte_interno"], step=1.0)
    with c2:
        new_merma = st.number_input("Merma (%)", value=cfg["merma_pct"] * 100, step=0.1, format="%.2f")
        new_costo_caja = st.number_input("Costo de caja (USD / caja, base)", value=cfg["costo_caja"], step=0.01)
        new_peso_pallet = st.number_input("Peso pallet + plástico (kg)", value=cfg["peso_pallet"], step=0.1)

        # Mínimo de pallets por pedido
        new_min_pallets = st.number_input(
            "📦 Mínimo de pallets por pedido",
            min_value=1, max_value=20,
            value=int(cfg.get("min_pallets", 3)),
            step=1, key="cfg_min_pallets"
        )

    st.markdown("---")
    new_public_url = st.text_input(
        "🌐 URL pública de la app (para compartir con clientes)",
        value=cfg.get("public_url", "https://exportharet-pedidos.streamlit.app"),
        help="URL de Streamlit Cloud. Se usa en los botones de WhatsApp, Email y QR.",
    )

    st.markdown("---")
    st.markdown("### Tarifas por destino (USD/kg aéreo)")

    dest_rows = [
        {
            "Destino": k,
            "Tarifa USD/kg": v,
            "Moneda": cfg.get("destinos_moneda", {}).get(k, DESTINO_DIVISA.get(k, ("USD", "$"))[0]),
        }
        for k, v in cfg["destinos"].items()
    ]
    dest_df = pd.DataFrame(dest_rows)
    edited_dest = st.data_editor(
        dest_df,
        use_container_width=False,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Tarifa USD/kg": st.column_config.NumberColumn("Tarifa USD/kg", min_value=0.0, step=0.05, format="%.2f"),
                "Moneda": st.column_config.SelectboxColumn("Moneda", options=["USD","EUR","GBP","JPY","AED","CNY","RUB","CHF"], required=True),
        },
        key="dest_editor",
    )

    st.caption("💡 La columna Moneda se detecta automáticamente por el nombre del destino (DESTINO_DIVISA).")
    st.markdown("---")
    st.markdown("### Grupos de producto (cajas / pallet)")

    grupo_rows = [
        {"Grupo": k, "Cajas/Pallet": v["cajas_pallet"], "Productos": v["nombre"]}
        for k, v in cfg["grupos"].items()
    ]
    grupo_df = pd.DataFrame(grupo_rows)
    edited_grupos = st.data_editor(
        grupo_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Cajas/Pallet": st.column_config.NumberColumn("Cajas/Pallet", min_value=1, step=1)
        },
        key="grupo_editor",
    )

    st.markdown("---")
    if st.button("💾 Guardar configuración", type="primary"):
        cfg["eur_usd"] = new_eur_usd
        cfg["due"] = new_due
        cfg["transporte_interno"] = new_ti
        cfg["merma_pct"] = new_merma / 100.0
        cfg["costo_caja"] = new_costo_caja
        cfg["peso_pallet"] = new_peso_pallet
        cfg["public_url"] = new_public_url.rstrip("/")
        # Mejora 1: rebuild destinos (supports rename)
        new_destinos = {}
        new_destinos_moneda = {}
        for _, row in edited_dest.iterrows():
            _dname = str(row["Destino"]).strip()
            if _dname:
                new_destinos[_dname] = float(row["Tarifa USD/kg"])
                new_destinos_moneda[_dname] = str(row.get("Moneda", "USD")).strip() or "USD"
        cfg["destinos"] = new_destinos
        cfg["destinos_moneda"] = new_destinos_moneda
        new_grupos = {}
        for _, _grow in edited_grupos.iterrows():
            _gkey  = str(_grow.get("Grupo","")).strip().upper()
            _gname = str(_grow.get("Productos","")).strip()
            _gcaj  = int(_grow.get("Cajas/Pallet",160))
            if _gkey:
                _existing = cfg["grupos"].get(_gkey, {})
                new_grupos[_gkey] = {
                    "cajas_pallet": _gcaj,
                    "nombre": _gname if _gname else _existing.get("nombre",_gkey),
                }
        cfg["grupos"] = new_grupos
        save_data(data)
        st.success("✅ Configuración guardada.")
        st.rerun()

    st.markdown("---")
    st.markdown("### Gestión de productos")
    st.markdown("Activa o desactiva la disponibilidad con un clic en la columna **✓ Pedido**:")

    prod_df = pd.DataFrame([
        {
            "✓ Pedido":          p.get("activo", True),
            "Producto":          p["producto"],
            "Código":            p["codigo"],
            "kg/caja":           p["kg_caja"],
            "Costo caja manual": p["costo_caja_manual"],
            "Precio compra":     p["precio_compra"],
            "Margen %":          round(p["margen_pct"] * 100, 1),
            "Grupo":             p["grupo"],
        }
        for p in products
    ])

    edited_prods = st.data_editor(
        prod_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "✓ Pedido":   st.column_config.CheckboxColumn(
                "✓ Pedido", width="small",
                help="Activa para que el producto aparezca en el formulario de pedido"),
            "Producto":   st.column_config.TextColumn("Producto"),
            "Código":     st.column_config.TextColumn("Código", width="small"),
            "Grupo":      st.column_config.SelectboxColumn("Grupo", options=list(cfg["grupos"].keys()), width="small"),
            "kg/caja":    st.column_config.NumberColumn("kg/caja", min_value=0.1, step=0.25, width="small"),
            "Costo caja manual": st.column_config.NumberColumn(
                "Costo caja", help="Vacío = costo_base / kg", width="small"),
            "Precio compra": st.column_config.NumberColumn("Compra $", min_value=0.0, step=0.01, format="$%.2f"),
            "Margen %":   st.column_config.NumberColumn("Margen %", min_value=0.0, max_value=100.0, step=0.5, width="small"),
        },
        key="prod_editor",
    )

    if st.button("💾 Guardar lista de productos", type="secondary"):
        new_products = []
        for _, row in edited_prods.iterrows():
            new_products.append({
                "codigo":            row["Código"],
                "producto":          row["Producto"],
                "kg_caja":           float(row["kg/caja"]),
                "costo_caja_manual": float(row["Costo caja manual"]) if pd.notna(row["Costo caja manual"]) else None,
                "precio_compra":     float(row["Precio compra"]),
                "margen_pct":        float(row["Margen %"]) / 100.0,
                "grupo":             row["Grupo"],
                "activo":            bool(row["✓ Pedido"]),
            })
        data["products"] = new_products
        save_data(data)
        st.success("✅ Lista de productos actualizada.")
        st.rerun()

    # ── Logo de la empresa ────────────────────────────────────────────────────
    st.markdown("---")
    # ── Sincronizar con Excel Cotizaciones ────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📊 Sincronizar con Excel Cotizaciones")

    xc1, xc2 = st.columns([3, 2])
    with xc1:
        st.markdown(
            "Sube el archivo **Cotizaciones.xlsx** para importar automáticamente:\n"
            "- Precios de compra de cada producto (última semana del historial)\n"
            "- Tarifas de flete por destino\n"
            "- Parámetros generales (DUE, merma, peso pallet…)"
        )
        excel_up = st.file_uploader(
            "Cotizaciones.xlsx", type=["xlsx", "xlsm"],
            key="excel_sync", label_visibility="collapsed"
        )

    with xc2:
        # Botón para cargar automáticamente desde ruta local si existe
        _xls_local = os.path.join(
            os.path.dirname(__file__),
            "Documentacion", "Precios", "Cotizaciones.xlsx"
        )
        if os.path.exists(_xls_local):
            st.info("📂 Archivo local detectado en el proyecto")
            if st.button("🔄 Sincronizar desde archivo local", use_container_width=True):
                with open(_xls_local, "rb") as f:
                    st.session_state["_excel_sync_bytes"] = f.read()
        else:
            st.caption("El archivo local no está en la carpeta del proyecto.")

    # Procesar el Excel (subido o local)
    _xbytes = None
    if excel_up:
        _xbytes = excel_up.read()
    elif st.session_state.get("_excel_sync_bytes"):
        _xbytes = st.session_state.pop("_excel_sync_bytes")

    if _xbytes:
        with st.spinner("Leyendo Cotizaciones.xlsx…"):
            try:
                new_prods, new_cfg_excel, ch = sync_from_cotizaciones(_xbytes, data)
            except Exception as e:
                st.error(f"Error al leer el Excel: {e}")
                new_prods = new_cfg_excel = ch = None

        if ch is not None:
            if ch:
                st.markdown(f"**Se detectaron {len(ch)} cambios:**")
                for c in ch:
                    st.markdown(f"- {c}")
                if st.button("✅ Aplicar todos los cambios", type="primary",
                             key="apply_excel_sync"):
                    data["products"] = new_prods
                    data["config"]   = new_cfg_excel
                    data["config"]["minimos"] = minimos  # conservar mínimos
                    save_data(data)
                    st.success("✅ Datos sincronizados desde Cotizaciones.xlsx")
                    st.rerun()
            else:
                st.success("✅ Los datos ya están sincronizados — no hay cambios.")

    # ── Logo de la empresa ────────────────────────────────────────────────────
    st.markdown("#### 🖼️ Logo de la empresa")

    _logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    col_logo, col_upload = st.columns([1, 2])

    with col_logo:
        if os.path.exists(_logo_path):
            st.image(_logo_path, caption="Logo actual", use_container_width=True)
        else:
            st.info("Sin logo configurado")

    with col_upload:
        st.markdown("**Logo principal** (PNG/JPG, fondo blanco o transparente):")
        uploaded = st.file_uploader(
            "Logo principal",
            type=["png", "jpg", "jpeg", "webp"],
            key="logo_uploader",
            label_visibility="collapsed",
        )
        if uploaded:
            from PIL import Image as PILImage
            img_obj = PILImage.open(io.BytesIO(uploaded.read())).convert("RGBA")
            buf = io.BytesIO(); img_obj.save(buf, format="PNG")
            with open(_logo_path, "wb") as f: f.write(buf.getvalue())
            st.success("✅ Logo guardado. Pulsa **🚀 Publicar en la nube**.")
            st.image(_logo_path, caption="Nuevo logo", width=200)

        st.markdown("**Icono del navegador** (cuadrado PNG, mín. 64×64):")
        _fav_path = os.path.join(os.path.dirname(__file__), "favicon.png")
        fav_up = st.file_uploader(
            "Icono navegador",
            type=["png", "jpg", "jpeg"],
            key="fav_uploader",
            label_visibility="collapsed",
        )
        if fav_up:
            from PIL import Image as PILImage
            fav_obj = PILImage.open(io.BytesIO(fav_up.read())).convert("RGBA")
            # Recortar a cuadrado y escalar
            side = min(fav_obj.size)
            w, h = fav_obj.size
            fav_obj = fav_obj.crop(((w-side)//2,(h-side)//2,(w+side)//2,(h+side)//2))
            fav_obj = fav_obj.resize((256,256))
            buf2 = io.BytesIO(); fav_obj.save(buf2, format="PNG")
            with open(_fav_path, "wb") as f: f.write(buf2.getvalue())
            st.success("✅ Icono guardado. Pulsa **🚀 Publicar en la nube**.")
            st.image(_fav_path, caption="Nuevo icono", width=80)
        elif os.path.exists(_fav_path):
            st.image(_fav_path, caption="Icono actual", width=80)

    # ── Publicar en la nube ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### ☁️ Publicar cambios en la nube")
    st.info(
        "Después de guardar cualquier cambio (precios, configuración, productos), "
        "pulsa este botón para que los clientes vean los nuevos datos al instante."
    )

    if st.button("🚀 Publicar en la nube", type="primary", use_container_width=False):
        with st.spinner("Publicando en Streamlit Cloud..."):
            try:
                # Token desde secrets (Streamlit Cloud) o archivo local
                gh_token = st.secrets.get("GITHUB_TOKEN", "") if hasattr(st, "secrets") else ""
                if not gh_token:
                    # Fallback: leer de archivo local de secretos
                    secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
                    if os.path.exists(secrets_path):
                        with open(secrets_path) as sf:
                            for line in sf:
                                if "GITHUB_TOKEN" in line:
                                    gh_token = line.split("=")[-1].strip().strip('"').strip("'")

                if not gh_token:
                    st.error("❌ Token de GitHub no configurado. Contacta al administrador.")
                    st.stop()

                # Contenido actual del archivo de datos
                data_content = json.dumps(data, indent=2, ensure_ascii=False)
                content_b64  = base64.b64encode(data_content.encode()).decode()

                api_url = "https://api.github.com/repos/expharet/app-de-pedidos/contents/precios_data.json"
                headers = {
                    "Authorization": f"token {gh_token}",
                    "Accept":        "application/vnd.github.v3+json",
                }

                # Obtener SHA actual del archivo (necesario para actualizarlo)
                r_get = requests.get(api_url, headers=headers, timeout=15)
                if r_get.status_code != 200:
                    st.error(f"❌ Error leyendo archivo en GitHub: {r_get.status_code}")
                    st.stop()
                sha = r_get.json()["sha"]

                # Publicar el archivo actualizado
                payload = {
                    "message": f"Actualizar precios — {date.today().strftime('%d/%m/%Y')}",
                    "content": content_b64,
                    "sha":     sha,
                }
                r_put = requests.put(api_url, json=payload, headers=headers, timeout=20)

                # También subir logo y favicon si existen
                for _fname in ["logo.png", "favicon.png"]:
                    _lp = os.path.join(os.path.dirname(__file__), _fname)
                    if os.path.exists(_lp):
                        with open(_lp, "rb") as lf:
                            _img_b64 = base64.b64encode(lf.read()).decode()
                        _img_url = f"https://api.github.com/repos/expharet/app-de-pedidos/contents/{_fname}"
                        _rg = requests.get(_img_url, headers=headers, timeout=10)
                        _sha = _rg.json().get("sha","") if _rg.status_code == 200 else ""
                        _pl = {"message": f"Actualizar {_fname} — {date.today().strftime('%d/%m/%Y')}",
                               "content": _img_b64}
                        if _sha: _pl["sha"] = _sha
                        requests.put(_img_url, json=_pl, headers=headers, timeout=20)

                if r_put.status_code in (200, 201):
                    st.success(
                        "✅ **¡Publicado!** Los cambios están en la nube. "
                        "La app se actualizará en 1-2 minutos:\n\n"
                        "🌐 https://exportharet-pedidos.streamlit.app"
                    )
                else:
                    msg = r_put.json().get("message", str(r_put.status_code))
                    st.error(f"❌ Error publicando: {msg}")

            except requests.Timeout:
                st.error("⏱ Tiempo de espera agotado. Comprueba tu conexión.")
            except Exception as e:
                st.error(f"❌ Error inesperado: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — CLIENTES
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown("### 👥 Base de datos de clientes")

    all_clients = load_clients()

    if not all_clients:
        st.info("Aún no hay clientes registrados. Los clientes se registran automáticamente al confirmar su primer pedido.")
    else:
        # ── Métricas generales ──
        total_clientes = len(all_clients)
        total_pedidos  = sum(len(c.get("pedidos",[])) for c in all_clients.values())
        total_facturado = sum(
            p["total_usd"]
            for c in all_clients.values()
            for p in c.get("pedidos", [])
        )
        mc1, mc2, mc3 = st.columns(3)
        mc1.metric("👤 Clientes registrados", total_clientes)
        mc2.metric("📦 Pedidos totales",       total_pedidos)
        mc3.metric("💵 Facturación total USD",  f"${total_facturado:,.2f}")

        st.markdown("---")

        # ── Buscador ──
        search = st.text_input("🔍 Buscar por nombre, empresa o email", key="client_search",
                               placeholder="Escribe para filtrar...")

        # ── Tabla resumen de clientes ──
        client_rows = []
        for email, c in all_clients.items():
            pedidos = c.get("pedidos", [])
            total   = sum(p["total_usd"] for p in pedidos)
            client_rows.append({
                "Email":          email,
                "Nombre":         c.get("nombre",""),
                "Empresa":        c.get("razon_social",""),
                "Teléfono":       c.get("telefono",""),
                "Pedidos":        len(pedidos),
                "Total USD":      total,
                "Primer pedido":  c.get("primer_pedido",""),
                "Último pedido":  c.get("ultimo_pedido",""),
            })

        df_clients = pd.DataFrame(client_rows)

        # Aplicar filtro
        if search:
            mask = (
                df_clients["Email"].str.contains(search, case=False, na=False) |
                df_clients["Nombre"].str.contains(search, case=False, na=False) |
                df_clients["Empresa"].str.contains(search, case=False, na=False)
            )
            df_clients = df_clients[mask]

        def hl_clients(col):
            if col.name == "Total USD":
                return ["background-color:#e8f5e9;font-weight:bold"] * len(col)
            return [""] * len(col)

        st.dataframe(
            df_clients.style.apply(hl_clients, axis=0).format({"Total USD": "${:,.2f}"}),
            use_container_width=True, hide_index=True
        )

        st.markdown("---")
        st.markdown("#### 📋 Historial de pedidos por cliente")

        # Selector de cliente para ver detalle
        email_sel = st.selectbox(
            "Selecciona un cliente",
            options=list(all_clients.keys()),
            format_func=lambda e: f"{all_clients[e].get('nombre','')} — {e}",
            key="client_selector"
        )

        if email_sel and email_sel in all_clients:
            c = all_clients[email_sel]
            pedidos = c.get("pedidos", [])

            # Ficha del cliente
            fi1, fi2, fi3, fi4 = st.columns(4)
            fi1.markdown(f"**{c.get('nombre','')}**  \n{c.get('razon_social','')}")
            fi2.markdown(f"📧 {email_sel}")
            fi3.markdown(f"📞 {c.get('telefono','—')}")
            fi4.markdown(f"📦 **{len(pedidos)}** pedido{'s' if len(pedidos)!=1 else ''}")

            # --- Mejora 2: Bloquear / Eliminar cliente ---
            st.markdown("---")
            _cb1, _cb2 = st.columns(2)
            _is_blocked = c.get("bloqueado", False)
            with _cb1:
                _lbl = "🔒 Desbloquear" if _is_blocked else "🔒 Bloquear"
                if st.button(_lbl, key=f"block_{email_sel}", use_container_width=True):
                    all_clients[email_sel]["bloqueado"] = not _is_blocked
                    save_clients(all_clients); st.rerun()
            if _is_blocked: st.warning("⚠️ Cliente bloqueado.")
            with _cb2:
                if st.button("🗑️ Eliminar cliente", key=f"del_cl_{email_sel}", type="secondary", use_container_width=True):
                    st.session_state[f"confirm_del_cl_{email_sel}"] = True
            if st.session_state.get(f"confirm_del_cl_{email_sel}", False):
                st.error(f"¿Eliminar al cliente {email_sel} permanentemente?")
                _cd1, _cd2 = st.columns(2)
                with _cd1:
                    if st.button("✅ Confirmar", key=f"yes_del_cl_{email_sel}", type="primary"):
                        del all_clients[email_sel]; save_clients(all_clients)
                        del st.session_state[f"confirm_del_cl_{email_sel}"]
                        st.success("Cliente eliminado."); st.rerun()
                with _cd2:
                    if st.button("❌ Cancelar", key=f"cancel_del_cl_{email_sel}"):
                        del st.session_state[f"confirm_del_cl_{email_sel}"]; st.rerun()

            if not pedidos:
                st.caption("Este cliente aún no tiene pedidos registrados.")
            else:
                for ped in reversed(pedidos):   # más reciente primero
                    with st.expander(
                        f"🗓️ {ped['fecha']}  ·  {ped['id']}  ·  "
                        f"{ped['destino']}  ·  ${ped['total_usd']:,.2f}  "
                        f"({ped['pallets']} pal · {ped['cajas']} cajas)"
                    ):
                        prod_df = pd.DataFrame(ped.get("productos", []))
                        if not prod_df.empty:
                            st.dataframe(
                                prod_df.style.format({
                                    "precio_usd": "${:.2f}",
                                    "total_usd":  "${:.2f}",
                                }),
                                use_container_width=True, hide_index=True
                            )
                        # Totales
                        dc, ds, dr = ped.get("dest_code","USD"), ped.get("dest_sym","$"), ped.get("dest_rate",1.0)
                        st.markdown(
                            f"**Total USD:** ${ped['total_usd']:,.2f}"
                            + (f"  ·  **Total {dc}:** {ds}{ped.get('total_loc', ped['total_usd']*dr):,.2f}" if dc != "USD" else "")
                        )
                        # --- Mejora 3+5: Eliminar pedido / Coste-Beneficio ---
                        st.markdown("---")
                        _del_key = f"del_{ped['id']}"
                        _c_del, _c_cost = st.columns([1, 2])
                        with _c_del:
                            if st.button("🗑️ Eliminar", key=_del_key, type="secondary", use_container_width=True):
                                st.session_state[f"confirm_del_{ped['id']}"] = True
                        if st.session_state.get(f"confirm_del_{ped['id']}", False):
                            st.warning(f"¿Eliminar pedido {ped['id']}? No se puede deshacer.")
                            _cc1, _cc2 = st.columns(2)
                            with _cc1:
                                if st.button("✅ Sí, eliminar", key=f"yes_{ped['id']}", type="primary"):
                                    _cls = load_clients()
                                    if email_sel in _cls:
                                        _cls[email_sel]["pedidos"] = [o for o in _cls[email_sel].get("pedidos", []) if o.get("id") != ped["id"]]
                                        save_clients(_cls)
                                    send_cancel_email(ped)
                                    del st.session_state[f"confirm_del_{ped['id']}"]
                                    st.success("Pedido eliminado."); st.rerun()
                            with _cc2:
                                if st.button("❌ Cancelar", key=f"cancel_{ped['id']}"):
                                    del st.session_state[f"confirm_del_{ped['id']}"]
                                    st.rerun()
                        with _c_cost:
                            _ped_dest  = ped.get("destino", list(data["config"].get("destinos", {"?":0}).keys())[0])
                            _ped_cajas = max(sum(p.get("cajas",0) for p in ped.get("productos",[])), 1)
                            _tc = 0.0
                            for _p in ped.get("productos", []):
                                _pcode  = _p.get("codigo", "")
                                _pdata  = next((x for x in data.get("products",[]) if x.get("codigo")==_pcode), {})
                                _pcajas = _p.get("cajas", 0)
                                if not _pdata or not _pcajas: continue
                                _cc         = _pdata.get("costo_caja_manual") or data["config"].get("costo_caja",0)/max(_pdata.get("kg_caja",1),0.001)
                                _fob_m_pct  = data["config"].get("merma_pct", 0)
                                _fob_merma  = (_pdata.get("precio_compra",0)+_cc)/(1-_fob_m_pct) if _fob_m_pct<1 else _pdata.get("precio_compra",0)+_cc
                                _tarifa     = data["config"].get("destinos",{}).get(_ped_dest, 0)
                                _grp        = data["config"].get("grupos",{}).get(_pdata.get("grupo",""),{})
                                _cpallet    = _grp.get("cajas_pallet", 160) if isinstance(_grp,dict) else 160
                                _flete_u    = _tarifa*(_pdata.get("kg_caja",0)+data["config"].get("tara_caja",0)+data["config"].get("peso_pallet",0)/max(_cpallet,1))
                                _due_u      = data["config"].get("due",0)/max(_ped_cajas,1)
                                _tc        += (_fob_merma + _flete_u + _due_u) * _pcajas
                            _tv = ped.get("total_usd", 0)
                            _pct = ((_tv-_tc)/_tv*100) if _tv else 0
                            st.markdown(f"💰 Coste: **${_tc:,.2f}** | Venta: **${_tv:,.2f}** | Beneficio: **${_tv-_tc:,.2f}** ({_pct:.1f}%)")

with tab7:
    # ── GESTION DE PEDIDOS (estado + notas admin) ──────────────────────────────────
    st.markdown("## 📦 Gestión de Pedidos")
    _gp_clients = load_clients()
    _gp_all = []
    for _gce, _gcd in _gp_clients.items():
        for _gp in _gcd.get("pedidos", []):
            _gp_all.append({**_gp, "_client_email": _gce})
    if not _gp_all:
        st.info("No hay pedidos todavía.")
    else:
        # Filtros
        _gf1, _gf2 = st.columns([2,2])
        _filt_estado = _gf1.selectbox("Filtrar por estado", ["Todos"] + ORDEN_ESTADOS, key="gp_filt_est")
        _filt_texto  = _gf2.text_input("Buscar cliente o ID", key="gp_filt_txt").strip().lower()
        _gp_filtered = [
            p for p in _gp_all
            if (_filt_estado == "Todos" or p.get("estado","Recibido") == _filt_estado)
            and (_filt_texto == "" or _filt_texto in p.get("client_name","").lower()
                 or _filt_texto in p.get("id","").lower()
                 or _filt_texto in p.get("_client_email","").lower())
        ]
        st.markdown(f"**{len(_gp_filtered)} pedidos** encontrados")
        st.markdown("---")
        for _ped in sorted(_gp_filtered, key=lambda x: x.get("fecha",""), reverse=True):
            _pid   = _ped.get("id","").upper()
            _pest  = _ped.get("estado","Recibido")
            _pico  = ORDEN_ESTADOS_COLORES.get(_pest,"📦")
            _pdest = _ped.get("destino","")
            _pfech = _ped.get("fecha", _ped.get("date",""))[:10]
            _pcli  = _ped.get("client_name", _ped.get("_client_email",""))
            _ptot  = _ped.get("total_usd",0)
            _pnotas_adm = _ped.get("notas_admin","")
            _pce   = _ped.get("_client_email","")
            with st.expander(f"{_pico} **#{_pid}** | {_pcli} | {_pdest} | {_pfech} | ${_ptot:,.2f}", expanded=False):
                _col_est, _col_notas = st.columns([1,2])
                with _col_est:
                    st.markdown("**Cambiar estado:**")
                    try:
                        _cur_idx = ORDEN_ESTADOS.index(_pest)
                    except ValueError:
                        _cur_idx = 0
                    _new_est = st.selectbox(
                        "Estado",
                        ORDEN_ESTADOS,
                        index=_cur_idx,
                        key=f"est_{_ped['id']}",
                        label_visibility="collapsed"
                    )
                    if st.button("💾 Guardar estado", key=f"save_est_{_ped['id']}", type="primary"):
                        _gu_cls = load_clients()
                        if _pce in _gu_cls:
                            for _o in _gu_cls[_pce].get("pedidos",[]):
                                if _o.get("id") == _ped["id"]:
                                    _old_est = _o.get("estado","Recibido")
                                    _o["estado"] = _new_est
                                    if "historial_estados" not in _o:
                                        _o["historial_estados"] = []
                                    import datetime as _dtt
                                    _o["historial_estados"].append({
                                        "de": _old_est,
                                        "a":  _new_est,
                                        "fecha": str(_dtt.datetime.now())[:19]
                                    })
                                    break
                            save_clients(_gu_cls)
                            if _new_est != _pest:
                                send_status_email(_ped, _new_est)
                        st.success(f"Estado actualizado: {_new_est}"); st.rerun()
                with _col_notas:
                    st.markdown("**Notas internas (solo admin):**")
                    _nota_nueva = st.text_area(
                        "Notas admin",
                        value=_pnotas_adm,
                        key=f"nota_{_ped['id']}",
                        label_visibility="collapsed",
                        height=80
                    )
                    if st.button("📝 Guardar nota", key=f"save_nota_{_ped['id']}"):
                        _gn_cls = load_clients()
                        if _pce in _gn_cls:
                            for _o2 in _gn_cls[_pce].get("pedidos",[]):
                                if _o2.get("id") == _ped["id"]:
                                    _o2["notas_admin"] = _nota_nueva
                                    break
                            save_clients(_gn_cls)
                        st.success("Nota guardada."); st.rerun()
                # Historial de estados
                _hist = _ped.get("historial_estados",[])
                if _hist:
                    st.markdown("**Historial de estados:**")
                    for _h in _hist:
                        st.caption(f"  {_h.get('fecha','')} — {_h.get('de','')} → {_h.get('a','')}")


