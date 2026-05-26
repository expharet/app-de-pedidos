"""Exportar Haret — Pedidos"""

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


@st.cache_data(ttl=3600)  # Refresca cada hora
def fetch_live_eur_usd() -> tuple:
    """Tipo de cambio EUR/USD en tiempo real desde el Banco Central Europeo."""
    try:
        r = requests.get(
            "https://api.frankfurter.app/latest?from=EUR&to=USD",
            timeout=6
        )
        if r.status_code == 200:
            data_fx = r.json()
            rate = float(data_fx["rates"]["USD"])
            day = data_fx.get("date", "")
            return rate, f"🟢 Live ECB · {day}"
    except Exception:
        pass
    return None, "🔴 No connection"


# ── Currencies by destination ─────────────────────────────────────────────────
DEST_CURRENCY = {
    "Madrid/España": ("EUR", "€"),
    "París/Francia": ("EUR", "€"),
    "Londres/Reino Unido": ("GBP", "£"),
    "Suiza": ("CHF", "Fr"),
    "Países Bajos": ("EUR", "€"),
    "Dubai/EAU": ("AED", "د.إ"),
    "Nueva York/Estados Unidos": ("USD", "$"),
    "Miami/EE. UU.": ("USD", "$"),
    "(otros)": ("EUR", "€"),
}

# Símbolos por código de moneda
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
    return DEST_CURRENCY.get(dest_name, ("USD", "$"))

@st.cache_data(ttl=3600)
def fetch_dest_rate(dest_code: str) -> float:
    """Tipo de cambio USD → dest_code (ECB/Frankfurter en tiempo real)."""
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


# ── Phone prefixes ───────────────────────────────────────────────────────────
PHONE_PREFIXES = [
    ("🇪🇸 España", "+34"),
    ("🇫🇷 Francia", "+33"),
    ("🇬🇧 Reino Unido", "+44"),
    ("🇩🇪 Alemania", "+49"),
    ("🇳🇱 Países Bajos", "+31"),
    ("🇨🇭 Suiza", "+41"),
    ("🇦🇪 Emiratos Árabes", "+971"),
    ("🇺🇸 EE.UU. / Canadá", "+1"),
    ("🇪🇨 Ecuador", "+593"),
    ("🇨🇴 Colombia", "+57"),
    ("🇲🇽 México", "+52"),
    ("🇧🇷 Brasil", "+55"),
    ("🇦🇷 Argentina", "+54"),
    ("🇵🇪 Perú", "+51"),
    ("🇮🇹 Italia", "+39"),
    ("🇵🇹 Portugal", "+351"),
    ("🇧🇪 Bélgica", "+32"),
    ("🇦🇹 Austria", "+43"),
    ("🇸🇦 Arabia Saudí", "+966"),
    ("🇶🇦 Qatar", "+974"),
    ("🇰🇼 Kuwait", "+965"),
    ("🇦🇺 Australia", "+61"),
    ("🇯🇵 Japón", "+81"),
    ("🇨🇳 China", "+86"),
    ("🇷🇺 Rusia", "+7"),
]


# ── Automatic email sending ──────────────────────────────────────────────────
def send_order_email(saved: dict, ai_full: list, pdf_bytes: bytes,
                     cfg_data: dict, wa_text: str) -> tuple:
    """Envía el albarán por correo electrónico a order@exportharet.com."""
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
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = "order@exportharet.com"
        msg["Reply-To"] = saved.get("email", "")
        msg["Subject"] = (
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
    """Notifica por correo electrónico que un pedido fue eliminado/cancelado."""
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
        ped_id = ped.get("id", "?")
        client = ped.get("client_name", ped.get("email", "?"))
        fecha = ped.get("fecha", "")
        destino = ped.get("destino", "FOB")
        total = ped.get("total_usd", 0)
        subject = f"Pedido #{ped_id} CANCELADO/ELIMINADO - Export Haret"
        body = (
            f"Se ha eliminado el pedido #{ped_id}.\n\n"
            f"Cliente: {client}\n"
            f"Fecha: {fecha}\n"
            f"Destino: {destino}\n"
            f"Total USD: ${total:,.2f}\n\n"
            f"Este pedido ya no aparece en el sistema."
        )
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = "order@exportharet.com"
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, ["order@exportharet.com"], msg.as_string())
    except Exception:
        pass  # silencio si falla SMTP

# ── Order states ─────────────────────────────────────────────────────────────
ORDER_STATES = ["Recibido", "Confirmado", "En preparación", "Enviado", "Entregado"]
ORDER_STATES_COLORS = {
    "Recibido": "🔵",
    "Confirmado": "🟡",
    "En preparación": "🟠",
    "Enviado": "🚀",
    "Entregado": "✅",
}
ORDER_STATES_EN = {
    "Recibido": "Received",
    "Confirmado": "Confirmed",
    "En preparación": "En preparación",
    "Enviado": "Shipped",
    "Entregado": "Delivered",
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
        client_name = ped.get("client_name", "")
        ped_id = ped.get("id", "").upper()
        icon = ORDER_STATES_COLORS.get(new_status, "📦")
        subject = f"[Export Haret] Tu pedido #{ped_id} — Estado: {icon} {new_status}"
        body = f"""Hola {client_name},

Tu pedido #{ped_id} ha cambiado de estado:

  {icon} {new_status}

Puedes consultar el detalle en:
https://exportharet-pedidos.streamlit.app/?view=cliente

Gracias por confiar en Export Haret.
El equipo de Export Haret
"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = client_email
        msg.attach(_MIMEText(body, "plain", "utf-8"))
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as srv:
            srv.starttls()
            srv.login(smtp_user, smtp_pass)
            srv.sendmail(smtp_user, [client_email], msg.as_string())
    except Exception:
        pass  # silencio


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

# ── Client database ──────────────────────────────────────────────────────────
CLIENTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clientes.json")

@st.cache_data(ttl=10)
def load_clients() -> dict:
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_clients(clients: dict):
    st.cache_data.clear()
    with open(CLIENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(clients, f, indent=2, ensure_ascii=False)

def register_order(saved: dict, ai_full: list, cfg_data: dict):
    """Registra o actualiza el cliente y guarda el pedido en su historial."""
    email = saved.get("email", "").strip().lower()
    if not email:
        return
    clients = load_clients()
    hoy = date.today().isoformat()

    # Crear/actualizar ficha del cliente
    if email not in clients:
        clients[email] = {
            "nombre": saved["client_name"],
            "razon_social": saved["razon_social"],
            "telefono": saved.get("telefono", ""),
            "primer_pedido": hoy,
            "ultimo_pedido": hoy,
            "pedidos": [],
        }
    else:
        c = clients[email]
        c["nombre"] = saved["client_name"]  # actualizar por si cambió
        c["razon_social"] = saved["razon_social"]
        c["telefono"] = saved.get("telefono", c.get("telefono", ""))
        c["ultimo_pedido"] = hoy

    # Construir resumen del pedido
    productos_resumen = []
    for p, cajas in ai_full:
        r = calc_pedido(p, cfg_data, saved["destino"], saved["total_cajas"])
        productos_resumen.append({
            "producto": p["producto"],
            "cajas": cajas,
            "precio_usd": round(r["precio_caja_usd"], 4),
            "total_usd": round(r["precio_caja_usd"] * cajas, 2),
        })

    pedido_id = f'PED-{hoy.replace("-","")}-{datetime.now().strftime("%H%M%S")}'
    clients[email]["pedidos"].append({
        "id": pedido_id,
        "fecha": hoy,
        "destino": saved["destino"],
        "total_usd": round(saved["total_usd"], 2),
        "dest_code": saved.get("dest_code", "USD"),
        "dest_sym": saved.get("dest_sym", "$"),
        "dest_rate": saved.get("dest_rate", 1.0),
        "total_loc": round(saved["total_usd"] * saved.get("dest_rate", 1.0), 2),
        "pallets": saved["total_pallets"],
        "cajas": saved["total_cajas"],
        "productos": productos_resumen,
    })

    save_clients(clients)

    # Publicar clientes.json en GitHub también
    _push_clients_to_github(clients)

def _push_clients_to_github(clients: dict):
    """Sube clientes.json a GitHub vía API."""
    try:
        _sp = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        tok = ""
        try:
            tok = st.secrets.get("GITHUB_TOKEN", "")
        except Exception:
            pass
        if not tok and os.path.exists(_sp):
            for line in open(_sp):
                if "GITHUB_TOKEN" in line and "=" in line:
                    tok = line.split("=", 1)[1].strip().strip('"').strip("'")
        if not tok:
            return
        hdrs = {"Authorization": f"token {tok}",
                "Accept": "application/vnd.github.v3+json"}
        api_url = "https://api.github.com/repos/expharet/app-de-pedidos/contents/clientes.json"
        content = base64.b64encode(
            json.dumps(clients, indent=2, ensure_ascii=False).encode()
        ).decode()
        r_get = requests.get(api_url, headers=hdrs, timeout=10)
        sha = r_get.json().get("sha", "") if r_get.status_code == 200 else ""
        payload = {"message": f"Registro cliente — {date.today().isoformat()}",
                   "content": content}
        if sha:
            payload["sha"] = sha
        requests.put(api_url, json=payload, headers=hdrs, timeout=15)
    except Exception:
        pass  # silencioso — no bloquear el flujo principal


def sync_from_cotizaciones(excel_bytes: bytes, current_data: dict) -> tuple:
    """
    Lee Cotizaciones.xlsx y devuelve (new_products, new_cfg, lista_cambios).
    Detecta cambios en precios de compra, tarifas de flete y parámetros.
    """
    from openpyxl import load_workbook
    import io as _io

    wb = load_workbook(_io.BytesIO(excel_bytes), data_only=True)
    ws_cfg = wb["CONFIGURACIÓN"]
    ws_pr = wb["TABLA PRECIOS"]
    new_cfg = json.loads(json.dumps(current_data["config"]))
    cambios = []

    # ── General parameters (robust to row changes) ──
    for row in ws_cfg.iter_rows():
        for cell in row:
            v = str(cell.value or "")
            c3 = ws_cfg.cell(row=cell.row, column=3).value
            if not isinstance(c3, (int, float)):
                continue
            val = float(c3)
            if "Costo de la caja" in v:
                if abs(new_cfg.get("costo_caja", 0) - val) > 0.0001:
                    cambios.append(f"Costo caja: {new_cfg.get('costo_caja')} → {val}")
                    new_cfg["costo_caja"] = val
            elif "Merma" in v and "%" in v:
                if abs(new_cfg.get("merma_pct", 0) - val) > 0.0001:
                    cambios.append(f"Merma %: {new_cfg.get('merma_pct')} → {val}")
                    new_cfg["merma_pct"] = val
            elif "DUE" in v and "fijo" in v:
                if abs(new_cfg.get("due", 0) - val) > 0.0001:
                    cambios.append(f"VENCIMIENTO: {new_cfg.get('due')} → {val}")
                    new_cfg["due"] = val
            elif "Palet de peso" in v:
                if abs(new_cfg.get("peso_pallet", 0) - val) > 0.0001:
                    cambios.append(f"Palet de peso: {new_cfg.get('peso_pallet')} → {val}")
                    new_cfg["peso_pallet"] = val
            elif "Tara de la caja" in v:
                if abs(new_cfg.get("tara_caja", 0) - val) > 0.0001:
                    cambios.append(f"Tara caja: {new_cfg.get('tara_caja')} → {val}")
                    new_cfg["tara_caja"] = val
            elif "transporte interno" in v.lower() and "costo" in v.lower():
                if abs(new_cfg.get("transporte_interno", 0) - val) > 0.0001:
                    cambios.append(f"Transporte interno: {new_cfg.get('transporte_interno')} → {val}")
                    new_cfg["transporte_interno"] = val
            # Destination rates (column B = destination name, column C = rate)
            dest_name = str(ws_cfg.cell(row=cell.row, column=2).value or "")
            if cell.column == 2 and dest_name in new_cfg.get("destinos", {}):
                if abs(new_cfg["destinos"][dest_name] - val) > 0.0001:
                    cambios.append(f"Tarifa **{dest_name}**: {new_cfg['destinos'][dest_name]} → {val}")
                    new_cfg["destinos"][dest_name] = val

    # ── Latest purchase prices from history (TABLA PRECIOS, rows 32-83) ──
    COL_MAP = {
        4: "F-PSG10",  # D Granadilla
        5: "F-PN016",  # E Lulo
        6: "F-PPA01",  # F Amarilla P
        7: "F-PSR02",  # G Roja P
        8: "F-PSR05",  # H Blanca P
        9: "F-PSM09",  # I Maracuyá
        10: "F-TAS04",  # J Tomate de árbol
        11: "F-GNB010",  # K Guanabana
        12: "F-MPS03",  # L Pepino dulce
        13: "F-CCN017",  # M Cacao
        14: "F-BCC013",  # N Babaco
        15: "F-AHSS012",  # O Aguacate
        16: "F-BBB06",  # P Baby banano
        17: "F-ZPT020",  # Q Zapote Mamey
        18: "F-TX020",  # R Taxo
        19: "F-UVP08",  # S Physalis
        20: "F-UVP07",  # T Physalis-husk
    }
    latest = {}
    for col, codigo in COL_MAP.items():
        ultimo = None
        for r in range(32, 84):
            v = ws_pr.cell(row=r, column=col).value
            if isinstance(v, (int, float)) and v > 0:
                ultimo = float(v)
        if ultimo:
            latest[codigo] = ultimo

    new_products = []
    for p in current_data["productos"]:
        np2 = dict(p)
        if p["código"] in latest:
            new_price = latest[p["código"]]
            if abs(np2["precio_compra"] - new_price) > 0.001:
                cambios.append(
                    f"**{p['producto']}**: ${np2['precio_compra']:.2f} → ${new_price:.2f}")
                np2["precio_compra"] = new_price
        new_products.append(np2)

    return new_products, new_cfg, cambios


def _load_page_icon():
    """Carga el favicon personalizado si existe, si no usa el emoji."""
    _fav = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favicon.png")
    if os.path.exists(_fav):
        from PIL import Image as _PIL
        return _PIL.open(_fav)
    return "🌿"

st.set_page_config(
    page_title="Exportar Haret — Pedidos",
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
            "C": {"cajas_pallet": 160, "nombre": "Lulo · Maracuyá · Tomate · Taxo · Melón"},
            "D": {"cajas_pallet": 120, "nombre": "Cacao · Babaco"},
            "E": {"cajas_pallet": 160, "nombre": "Aguacate · Baby banano · Zapote · Caña"},
            "F": {"cajas_pallet": 120, "nombre": "Roja P · Blanca P"},
            "G": {"cajas_pallet": 160, "nombre": "Physalis sin cáscara"},
            "H": {"cajas_pallet": 160, "nombre": "Physalis con cáscara"},
            "I": {"cajas_pallet": 60, "nombre": "Guanabana"},
        },
        "public_url": "https://exportharet-pedidos.streamlit.app",
        "destinos": {
            "Madrid/España": 2.25,
            "París/Francia": 2.75,
            "Londres/Reino Unido": 2.60,
            "Suiza": 2.60,
            "Países Bajos": 2.60,
            "Dubai/EAU": 4.30,
            "Nueva York/EE. UU.": 1.20,
            "Miami/EE. UU.": 1.15,
            "(otros)": 2.10,
        },
    },
    "productos": [
        {"codigo": "F-PSG10", "producto": "Granadilla", "kg_caja": 2.0, "costo_caja_manual": 0.03, "precio_compra": 7.95, "margen_pct": 0.08, "grupo": "A", "activo": True},
        {"codigo": "F-PN016", "producto": "Lulo", "kg_caja": 2.5, "costo_caja_manual": 0.03, "precio_compra": 6.50, "margen_pct": 0.11, "grupo": "C", "activo": True},
        {"codigo": "F-PPA01", "producto": "Amarilla P", "kg_caja": 2.5, "costo_caja_manual": None, "precio_compra": 15.50, "margen_pct": 0.06, "grupo": "B", "activo": True},
        {"codigo": "F-PSR02", "producto": "Roja P", "kg_caja": 4.5, "costo_caja_manual": None, "precio_compra": 19.19, "margen_pct": 0.055, "grupo": "F", "activo": True},
        {"codigo": "F-PSR05", "producto": "Blanca P", "kg_caja": 4.5, "costo_caja_manual": None, "precio_compra": 13.60, "margen_pct": 0.055, "grupo": "F", "activo": True},
        {"codigo": "F-PSM09", "producto": "Maracuyá", "kg_caja": 2.5, "costo_caja_manual": 0.0, "precio_compra": 7.00, "margen_pct": 0.08, "grupo": "C", "activo": True},
        {"codigo": "F-TAS04", "producto": "Tomate de árbol", "kg_caja": 2.5, "costo_caja_manual": 0.0, "precio_compra": 6.50, "margen_pct": 0.10, "grupo": "C", "activo": True},
        {"codigo": "F-GNB010", "producto": "Guanabana", "kg_caja": 4.0, "costo_caja_manual": None, "precio_compra": 13.14, "margen_pct": 0.12, "grupo": "I", "activo": True},
        {"codigo": "F-MPS03", "producto": "Pepino dulce", "kg_caja": 3.0, "costo_caja_manual": 0.0, "precio_compra": 5.25, "margen_pct": 0.09, "grupo": "C", "activo": True},
        {"codigo": "F-CCN017", "producto": "Cacao", "kg_caja": 3.0, "costo_caja_manual": None, "precio_compra": 6.00, "margen_pct": 0.11, "grupo": "D", "activo": True},
        {"codigo": "F-BCC013", "producto": "Babaco", "kg_caja": 3.0, "costo_caja_manual": None, "precio_compra": 8.60, "margen_pct": 0.10, "grupo": "D", "activo": True},
        {"codigo": "F-AHSS012", "producto": "Aguacate", "kg_caja": 4.0, "costo_caja_manual": None, "precio_compra": 8.55, "margen_pct": 0.06, "grupo": "E", "activo": True},
        {"codigo": "F-BBB06", "producto": "Baby banano", "kg_caja": 3.5, "costo_caja_manual": None, "precio_compra": 13.20, "margen_pct": 0.06, "grupo": "E", "activo": True},
        {"codigo": "F-ZPT020", "producto": "Zapote Mamey", "kg_caja": 4.0, "costo_caja_manual": None, "precio_compra": 12.00, "margen_pct": 0.18, "grupo": "E", "activo": True},
        {"codigo": "F-TX020", "producto": "Taxo", "kg_caja": 2.5, "costo_caja_manual": 0.0, "precio_compra": 6.70, "margen_pct": 0.10, "grupo": "C", "activo": True},
        {"codigo": "F-UVP08", "producto": "Physalis", "kg_caja": 1.25, "costo_caja_manual": 0.0, "precio_compra": 8.50, "margen_pct": 0.11, "grupo": "G", "activo": True},
        {"codigo": "F-UVP07", "producto": "Physalis - cáscara", "kg_caja": 1.5, "costo_caja_manual": 0.0, "precio_compra": 7.25, "margen_pct": 0.11, "grupo": "H", "activo": True},
        {"codigo": "F-SLK011", "producto": "Salack", "kg_caja": 2.5, "costo_caja_manual": 0.4, "precio_compra": 12.20, "margen_pct": 0.10, "grupo": "C", "activo": True},
        {"codigo": "F-CAZ021", "producto": "Caña de azúcar", "kg_caja": 4.0, "costo_caja_manual": None, "precio_compra": 10.72, "margen_pct": 0.11, "grupo": "E", "activo": True},
    ],
    "minimos": {
        "F-PSG10": {"tipo": "cajas", "valor": 80},
        "F-PN016": {"tipo": "cajas", "valor": 40},
        "F-TAS04": {"tipo": "cajas", "valor": 40},
        "F-MPS03": {"tipo": "cajas", "valor": 40},
        "F-TX020": {"tipo": "cajas", "valor": 40},
        "F-PSM09": {"tipo": "cajas", "valor": 160},
        "F-GNB010": {"tipo": "cajas", "valor": 60},
        "F-CCN017": {"tipo": "cajas", "valor": 120},
        "F-BCC013": {"tipo": "cajas", "valor": 120},
        "F-ZPT020": {"tipo": "cajas", "valor": 120},
        "F-PSR02": {"tipo": "cajas", "valor": 360},
        "F-PSR05": {"tipo": "cajas", "valor": 360},
        "F-PPA01": {"tipo": "cajas", "valor": 360},
        "F-SLK011": {"tipo": "cajas", "valor": 160},
        "F-CAZ021": {"tipo": "cajas", "valor": 120},
        "F-UVP08": {"tipo": "cajas", "valor": 50},
        "F-UVP07": {"tipo": "cajas", "valor": 50},
    },
}


@st.cache_data(ttl=10)
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return json.loads(json.dumps(INITIAL_DATA))  # copia profunda


def save_data(data):
    st.cache_data.clear()
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def cost_box(producto, cfg):
    m = producto.get("costo_caja_manual")
    return m if m is not None else cfg["costo_caja"] / producto["kg_caja"]


def calc(producto, cfg, destino, num_pallets):
    cc = cost_box(producto, cfg)
    fob_base = producto["precio_compra"] + cc
    mp = cfg["merma_pct"]
    fob_merma = fob_base / (1 - mp)
    mgn = producto["margen_pct"]
    fob_final = fob_merma / (1 - mgn)
    cajas = cfg["grupos"][producto["grupo"]]["cajas_pallet"]
    tarifa = cfg["destinos"].get(destino, 0) if destino else 0
    flete = tarifa * (producto["kg_caja"] + cfg["tara_caja"] + cfg["peso_pallet"] / cajas)
    cif = fob_final + flete
    due_c = cfg["due"] / (num_pallets * cajas)
    ti_c = cfg["transporte_interno"] / (num_pallets * cajas)
    pal_usd = cif + due_c + ti_c
    pal_eur = pal_usd / cfg["eur_usd"]
    return {
        "Costo caja": cc,
        "Base FOB": fob_base,
        "FOB + Merma": fob_merma,
        "Margen %": mgn,
        "FOB Final": fob_final,
        "Flete": flete,
        "CIF USD": cif,
        "CIF $/kg": cif / producto["kg_caja"],
        "Pal USD": pal_usd,
        "Pal EUR": pal_eur,
    }


def fmt(v, decimals=2):
    return f"{v:,.{decimals}f}"


def get_min_boxes(codigo, producto, cfg):
    """Devuelve la cantidad mínima de cajas para un producto."""
    minimos = cfg.get("minimos", {})
    m = minimos.get(codigo)
    if not m:
        return 0
    if m["tipo"] == "cajas":
        return int(m["valor"])
    cajas_pallet = cfg["grupos"][producto["grupo"]]["cajas_pallet"]
    return int(m["valor"]) * cajas_pallet


def min_label(codigo, producto, cfg):
    minimos = cfg.get("minimos", {})
    m = minimos.get(codigo)
    if not m:
        return "-"
    if m["tipo"] == "cajas":
        return f"{m['valor']} cajas"
    v = int(m["valor"])
    return f"{v} palé{'s' if v > 1 else ''}"


def calc_pedido(producto, cfg, destino, total_cajas_orden):
    """Precio/caja en un pedido mixto: DUE y transporte repartidos sobre total_cajas."""
    cc = cost_box(producto, cfg)
    fob_base = producto["precio_compra"] + cc
    fob_merma = fob_base / (1 - cfg["merma_pct"])
    fob_final = fob_merma / (1 - producto["margen_pct"])
    cajas_pal = cfg["grupos"][producto["grupo"]]["cajas_pallet"]
    tarifa = cfg["destinos"][destino]
    flete = tarifa * (producto["kg_caja"] + cfg["tara_caja"] + cfg["peso_pallet"] / cajas_pal)
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


# ── PDF Albarán ──────────────────────────────────────────────────────────────
def _font_path(filename: str) -> str:
    """Ruta a la fuente — busca en ./fonts/ primero, luego rutas del sistema."""
    local = os.path.join(os.path.dirname(__file__), "fonts", filename)
    if os.path.exists(local):
        return local
    # macOS de respaldo
    mac_map = {
        "DejaVuSans.ttf": "/Library/Fonts/Arial Unicode.ttf",
        "DejaVuSans-Bold.ttf": "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    }
    return mac_map.get(filename, local)


def gen_albaran_pdf(nombre_cliente, razón_social, destino, elementos_activos, total_cajas,
                    palets_totales, dólares_totales, datos_cfg,
                    total_eur=None, client_email="", telefono="",
                    dest_code="USD", dest_sym="$", dest_rate=1.0, lang="ES",
                    total_flete=0.0):
    Tp = TR.get(lang, TR["ES"])  # ← traducción al inicio, antes de todo uso
    pdf = FPDF()
    pdf.add_page()
    pdf.set_margins(15, 15, 15)
    VERDE = (45, 106, 79)

    # Fuente DejaVu — multiplataforma, soporta €, tildes, todos los caracteres
    pdf.add_font("U", "", _font_path("DejaVuSans.ttf"), uni=True)
    pdf.add_font("U", "B", _font_path("DejaVuSans-Bold.ttf"), uni=True)

    # ── Cabecera ──
    pdf.set_fill_color(*VERDE)
    pdf.rect(0, 0, 210, 28, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("U", "B", 20)
    pdf.set_xy(15, 6)
    pdf.cell(0, 10, "EXPORT HARET", ln=True)
    pdf.set_font("U", "", 9)
    pdf.set_x(15)
    pdf.cell(0, 5, "Exportadora de frutas ecuatorianas · order@exportharet.com")
    pdf.ln(14)

    # ── Título albarán ──
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("U", "B", 14)
    pdf.cell(0, 10, Tp["pdf_title"], ln=True, align="C")
    pdf.set_draw_color(*VERDE)
    pdf.set_line_width(0.6)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Datos del cliente ──
    rate_label = datos_cfg.get("_rate_label", "").replace("🟢", "").replace("🟡", "").strip()
    campos_cliente = [(Tp["pdf_client"], nombre_cliente),
                     (Tp["pdf_company"], razón_social)]
    if client_email:
        campos_cliente.append((Tp["pdf_email"], client_email))
    if telefono:
        campos_cliente.append((Tp["pdf_phone"], telefono))
    campos_cliente += [
        (Tp["pdf_date"], date.today().strftime("%d/%m/%Y")),
        (Tp["pdf_dest"], destino),
        (Tp["pdf_rate"], f"{datos_cfg['eur_usd']:.4f} ({rate_label})"),
    ]
    _tarifa_pdf = datos_cfg["destinos"].get(destino, 0)
    _flete_lbl = "Flete / Tarifa" if lang == "ES" else "Tarifa de flete"
    campos_cliente.append((_flete_lbl,
                          f"{_tarifa_pdf:.2f} USD/kg · CIF destino"))
    if dest_code not in ("USD",):
        campos_cliente.append((Tp["pdf_divisa"].format(code=dest_code),
                              f"1 USD = {dest_rate:.4f} {dest_sym}"))
    for etiqueta, valor in campos_cliente:
        pdf.set_font("U", "B", 10)
        pdf.cell(38, 7, etiqueta)
        pdf.set_font("U", "", 10)
        pdf.cell(0, 7, valor, ln=True)

    pdf.ln(3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Tabla de productos ──
    pdf.set_fill_color(*VERDE)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("U", "B", 9)
    anchos = [58, 22, 22, 40, 40]
    encabezados = [Tp["pdf_product"], Tp["pdf_boxes"], Tp["pdf_pallets"],
               Tp["pdf_price_usd"], Tp["pdf_total_usd"]]
    alinea = ["L", "C", "C", "R", "R"]
    for w, h, a in zip(anchos, encabezados, alinea):
        pdf.cell(w, 7, h, fill=True, align=a)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("U", "", 9)
    rellenar = False
    for p, cajas in elementos_activos:
        r = calc_pedido(p, datos_cfg, destino, total_cajas)
        pal = cajas / datos_cfg["grupos"][p["grupo"]]["cajas_pallet"]
        valores_fila = [
            p["producto"],
            str(cajas),
            f"{pal:.2f}",
            f"${r['precio_caja_usd']:.2f}",
            f"${r['precio_caja_usd']*cajas:,.2f}",
        ]
        bg = (240, 248, 240) if rellenar else (255, 255, 255)
        pdf.set_fill_color(*bg)
        for w, v, a in zip(anchos, valores_fila, alinea):
            pdf.cell(w, 6, v, fill=True, align=a)
        pdf.ln()
        rellenar = not rellenar

    pdf.ln(3)
    pdf.set_draw_color(*VERDE)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Totales ──
    pdf.set_font("U", "", 10)
    pdf.cell(100, 7, Tp["pdf_total_pal"].format(n=palets_totales, c=f"{total_cajas:,}"))
    pdf.set_font("U", "B", 11)
    pdf.cell(0, 7, f"TOTAL USD: ${dólares_totales:,.2f}", align="R", ln=True)
    pdf.cell(100, 7, "")
    if dest_code != "USD":
        total_loc_pdf = dólares_totales * dest_rate
        pdf.cell(0, 7, f"TOTAL {dest_code}: {dest_sym}{total_loc_pdf:,.2f}", align="R", ln=True)

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
    lineas = [
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
        lineas.append(f"• {p['producto']}: {cajas} cajas ({pal:.2f} pal) — ${total:,.2f}")
    total_loc = total_usd * dest_rate
    lineas += [
        "━━━━━━━━━━━━━━━━━━━━━",
        Tw["wa_summary"].format(c=f"{total_cajas:,}", p=total_pallets),
        f"💵 *Total USD: ${total_usd:,.2f}*",
    ]
    if dest_code != "USD":
        lineas.append(f"💱 *Total {dest_code}: {dest_sym}{total_loc:,.2f}*")
    return "\n".join(lineas)


TR = {
    "ES": {
        "lang_label": "Idioma/Idioma",
        "title": "## 🌿 Exportar Haret — Pedidos",
        "client_section": "#### 👤 Datos del cliente",
        "name": "Nombre del cliente *",
        "name_ph": "Nombre completo",
        "company": "Razón social / Empresa *",
        "company_ph": "Empresa SL",
        "email": "📧 Correo electrónico de contacto *",
        "email_ph": "cliente@empresa.com",
        "prefix": "📞 País / Prefijo *",
        "phone": "Número de teléfono *",
        "phone_ph": "612 345 678",
        "dest": "🌍 Destino *",
        "min_order": "Mínimo de orden: **{n} pallets** totales.",
        "dest_currency": "Divisa del destino: **{code} ({sym})** · 1 USD = {rate:.4f} {code}",
        "currency_usd": "Divisa: **USD ($)**",
        "products": "#### 📦 Productos del pedido",
        "unit_col": "Unidad",
        "qty_col": "Cantidad",
        "boxes_col": "= Cajas",
        "opt_pal": "📦 Palets",
        "opt_caj": "🗃️ Cajas",
        "min_pal": "mín. {n} palet{s} ({c} cajas)",
        "min_caj": "mín. {n} cajas",
        "hint": " ↑ Elige **📦 Pallets** o **🗃️ Cajas** e ingresa la cantidad de cada producto.",
        "pallets_m": "Palets",
        "boxes_m": "Cajas",
        "weight_m": "Peso neto",
        "progress_ok": "✅ {n} palets — pedido válido",
        "progress_low": "🔴 {n} de {min} pallets mínimos — faltan {f} pallet{s}",
        "warn_fields": "⚠️ Completa todos los datos del cliente para confirmar.",
        "warn_pallets": "⚠️ Faltan {f} pallet{s} para alcanzar el mínimo de {min}.",
        "below_min": "⚠️ **{prod}**: pediste {got} cajas — mínimo es {need} cajas.",
        "confirm_btn": "✅ Confirmar Pedido",
        "confirmed_ok": "✅ Pedido confirmado — {name} · {dest}",
        "email_auto_ok": "📨 Pedido enviado automáticamente a **order@exportharet.com**",
        "email_no_smtp": "💡 Configura SMTP en los secretos para envío automático.",
        "email_error": "⚠️ No se pudo enviar correo electrónico: {e}",
        "pdf_btn": "📄 Descargar Albarán PDF",
        "wa_btn": "📱 Enviar por WhatsApp",
        "mail_btn": "📧 Enviar por Email",
        "new_btn": "🔄 Nuevo",
        "pdf_title": "ALBARÁN DE PEDIDO",
        "pdf_client": "Cliente:",
        "pdf_company": "Razón social:",
        "pdf_email": "Correo electrónico:",
        "pdf_phone": "Teléfono:",
        "pdf_date": "Fecha:",
        "pdf_dest": "Destino:",
        "pdf_rate": "EUR/USD:",
        "pdf_divisa": "Divisa {code}:",
        "pdf_product": "Producto",
        "pdf_boxes": "Cajas",
        "pdf_pallets": "Palets",
        "pdf_price_usd": "Precio/caja USD",
        "pdf_total_usd": "Total USD",
        "pdf_total_pal": "Total pallets: {n} · Total cajas: {c}",
        "pdf_footer": "Export Haret · order@exportharet.com · Documento generado automáticamente",
        "wa_header": "🌿 *PEDIDO — EXPORTAR HARET*",
        "wa_client": "👤 Cliente:",
        "wa_company": "🏢 Razón social:",
        "wa_date": "📅 Fecha:",
        "wa_dest": "✈️ Destino:",
        "wa_products": "*PRODUCTOS:*",
        "wa_summary": "📦 Total: {c} cajas | {p} pallets",
    },
    "EN": {
        "lang_label": "Language/Idioma",
        "title": "## 🌿 Export Haret — Orders",
        "client_section": "#### 👤 Client Information",
        "name": "Client Name *",
        "name_ph": "Full Name",
        "company": "Company / Business Name *",
        "company_ph": "Company Ltd.",
        "email": "📧 Contact Email *",
        "email_ph": "client@company.com",
        "prefix": "📞 Country / Prefix *",
        "phone": "Phone Number *",
        "phone_ph": "612 345 678",
        "dest": "🌍 Destination *",
        "min_order": "Minimum order: **{n} pallets** total.",
        "dest_currency": "Destination currency: **{code} ({sym})** · 1 USD = {rate:.4f} {code}",
        "currency_usd": "Currency: **USD ($)**",
        "products": "#### 📦 Order Products",
        "unit_col": "Unit",
        "qty_col": "Quantity",
        "boxes_col": "= Boxes",
        "opt_pal": "📦 Pallets",
        "opt_caj": "🗃️ Boxes",
        "min_pal": "min. {n} pallet{s} ({c} boxes)",
        "min_caj": "min. {n} boxes",
        "hint": " ↑ Choose **📦 Pallets** or **🗃️ Boxes** and enter the quantity for each product.",
        "pallets_m": "Pallets",
        "boxes_m": "Boxes",
        "weight_m": "Net Weight",
        "progress_ok": "✅ {n} pallets — valid order",
        "progress_low": "🔴 {n} of {min} minimum pallets — add {f} pallet{s}",
        "warn_fields": "⚠️ Complete all customer information to confirm.",
        "warn_pallets": "⚠️ Need {f} pallet{s} more to reach minimum of {min}.",
        "below_min": "⚠️ **{prod}**: you entered {got} boxes; minimum is {need} boxes.",
        "confirm_btn": "✅ Confirm Order",
        "confirmed_ok": "✅ Order confirmed — {name} · {dest}",
        "email_auto_ok": "📨 Order sent automatically to **order@exportharet.com**",
        "email_no_smtp": "💡 Configure SMTP secrets for automatic email sending.",
        "email_error": "⚠️ Could not send email: {e}",
        "pdf_btn": "📄 Download Order PDF",
        "wa_btn": "📱 Send via WhatsApp",
        "mail_btn": "📧 Send via Email",
        "new_btn": "🔄 New Order",
        "pdf_title": "ORDER CONFIRMATION",
        "pdf_client": "Client:",
        "pdf_company": "Company:",
        "pdf_email": "Email:",
        "pdf_phone": "Phone:",
        "pdf_date": "Date:",
        "pdf_dest": "Destination:",
        "pdf_rate": "EUR/USD:",
        "pdf_divisa": "{code} rate:",
        "pdf_product": "Product",
        "pdf_boxes": "Boxes",
        "pdf_pallets": "Pallets",
        "pdf_price_usd": "Price/box USD",
        "pdf_total_usd": "Total USD",
        "pdf_total_pal": "Total pallets: {n} · Total boxes: {c}",
        "pdf_footer": "Export Haret · order@exportharet.com · Document generated automatically",
        "wa_header": "🌿 *ORDER — EXPORT HARET*",
        "wa_client": "👤 Client:",
        "wa_company": "🏢 Company:",
        "wa_date": "📅 Date:",
        "wa_dest": "✈️ Destination:",
        "wa_products": "*PRODUCTS:*",
        "wa_summary": "📦 Total: {c} boxes | {p} pallets",
    },
}


def render_order_form(cfg_data, products_list, standalone=False,
                      show_header=True, require_email=True):
    """Formulario de pedido.
    standalone=True → vista cliente (?view=cliente)
    show_header=False → oculta logo/título/idioma (ya mostrado por el portal)
    require_email=False → salta la verificación de correo electrónico (ya hecha por el portal)
    """
    MIN_PALLETS = 3

    # ── Language selector ────────────────────────────────────────────────────
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

    # ── Client access / Registration ────────────────────────────────────────
    _clients_db = load_clients()
    _sfx = "cl" if standalone else "adm"
    _verified_k = f"cliente_verificado_{_sfx}"
    _cdata_k = f"client_data_{_sfx}"

    if _verified_k not in st.session_state:
        st.session_state[_verified_k] = False
    if _cdata_k not in st.session_state:
        st.session_state[_cdata_k] = {}

    # ── STEP 1: Client identification ───────────────────────────────────────
    if require_email and not st.session_state[_verified_k]:

        if lang == "EN":
            _lbl_email = "📧 Enter your email to continue"
            _hint_email = "We'll identify you or create your account automatically"
            _btn_cont = "Continue →"
            _welcome_txt = lambda n, np_: f"👋 Welcome back, **{n}**!"
            _ped_prev = lambda np_: (f"You have **{np_}** previous order{'s' if np_!=1 else ''}."
                                        if np_ > 0 else "")
            _confirm_btn = "✅ Continue"
            _change_btn = "↩️ Different email"
            _reg_title = "#### 📝 Complete your information"
            _reg_hint = "Quick registration: just a moment"
            _reg_cont = "✅ Register and Continue"
            _reg_back = "← Back"
        else:
            _lbl_email = "📧 Ingresa tu correo para continuar"
            _hint_email = "Te identificamos o creamos tu cuenta automáticamente"
            _btn_cont = "Continuar →"
            _welcome_txt = lambda n, np_: f"👋 ¡Hola de nuevo, **{n}**!"
            _ped_prev = lambda np_: (f"Tienes **{np_}** pedido{'s' if np_!=1 else ''} anterior{'es' if np_!=1 else ''}."
                                        if np_ > 0 else "")
            _confirm_btn = "✅ Continuar"
            _change_btn = "↩️ Otro correo"
            _reg_title = "#### 📝 Completa tus datos"
            _reg_hint = "Solo un momento — registro rápido"
            _reg_cont = "✅ Registrarme y Continuar"
            _reg_back = "← Volver"

        _mode_k = f"access_mode_{_sfx}"
        if _mode_k not in st.session_state:
            st.session_state[_mode_k] = "email"  # estado inicial: input de email

        _mode = st.session_state[_mode_k]

        # ── Email screen (single input) ────────────────────────────────────
        if _mode == "email":
            st.markdown(f"##### {_lbl_email}")
            st.caption(_hint_email)
            _ea1, _ea2 = st.columns([4, 1])
            with _ea1:
                _email_input = st.text_input(
                    "email", label_visibility="collapsed",
                    key=f"access_email_{_sfx}",
                    placeholder="name@company.com",
                )
            with _ea2:
                _cont_clicked = st.button(_btn_cont, type="primary",
                                          use_container_width=True,
                                          key=f"btn_cont_{_sfx}")

            if _cont_clicked:
                _ec = _email_input.strip().lower()
                if not _ec:
                    st.warning("Por favor ingresa tu correo." if lang == "ES" else "Please enter your email.")
                elif _ec in _clients_db:
                    st.session_state[f"found_email_{_sfx}"] = _ec
                    st.session_state[_mode_k] = "welcome"
                    st.rerun()
                else:
                    # Email nuevo: llevar a registro con email guardado
                    st.session_state[f"reg_email_val_{_sfx}"] = _ec
                    st.session_state[_mode_k] = "register"
                    st.rerun()

        # ── Welcome existing client ─────────────────────────────────────────
        elif _mode == "welcome":
            _found_email = st.session_state.get(f"found_email_{_sfx}", "")
            if _found_email and _found_email in _clients_db:
                c = _clients_db[_found_email]
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
                            "nombre": c["nombre"],
                            "razon_social": c["razon_social"],
                            "email": _found_email,
                            "telefono": c.get("telefono", ""),
                            "last_destino": (c["pedidos"][-1]["destino"]
                                             if c.get("pedidos") else ""),
                        }
                        st.session_state[_verified_k] = True
                        st.session_state[_mode_k] = "email"
                        # Limpiar widgets de datos para que se prellenen con la nueva cuenta
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

        # ── New client registration ────────────────────────────────────────
        elif _mode == "register":
            _pre_email_val = st.session_state.get(f"reg_email_val_{_sfx}", "")
            st.markdown(_reg_title)
            st.caption(_reg_hint)
            nf1, nf2 = st.columns(2)
            with nf1:
                _ne = st.text_input(
                    "📧 Email", key=f"reg_email_{_sfx}",
                    placeholder="name@company.com",
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
                    "email": _email_reg, "telefono": _pn.strip(),
                }
                st.session_state[_verified_k] = True
                st.session_state[_mode_k] = "email"
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

    # ── STEP 2: Client data ────────────────────────────────────────────────
    _cd = st.session_state.get(_cdata_k, {})

    if standalone:
        # Vista cliente: campos pre-rellenados con los datos del login, editables
        _lbl_datos = "##### 👤 Tus datos" if lang == "ES" else "##### 👤 Your details"
        _lbl_edit = ("_Puedes editar cualquier campo si es necesario_"
                      if lang == "ES" else
                      "_You can edit any field if necessary_")
        st.markdown(_lbl_datos)
        st.caption(_lbl_edit)

        _ci1, _ci2 = st.columns(2)
        with _ci1:
            client_name = st.text_input(T["name"], key=f"cl_name_{_sfx}",
                                         value=_cd.get("nombre", ""),
                                         placeholder=T["name_ph"])
            client_email = st.text_input("📧 Email", key=f"cl_email_{_sfx}",
                                         value=_cd.get("email", ""),
                                         placeholder="name@company.com")
        with _ci2:
            razon_social = st.text_input(T["company"], key=f"cl_razon_{_sfx}",
                                         value=_cd.get("razon_social", ""),
                                         placeholder=T["company_ph"])
            phone_full = st.text_input(T["phone"], key=f"cl_phone_{_sfx}",
                                         value=_cd.get("telefono", ""),
                                         placeholder=T["phone_ph"])

        # Botón cambiar cuenta — limpia todo el estado correctamente
        _logout_lbl = "↩️ Cambiar cuenta" if lang == "ES" else "↩️ Change account"
        if st.button(_logout_lbl, key=f"btn_logout_{_sfx}"):
            st.session_state[_verified_k] = False
            st.session_state[_cdata_k] = {}
            st.session_state[f"access_mode_{_sfx}"] = "email"
            for _wk in [f"cl_name_{_sfx}", f"cl_email_{_sfx}",
                        f"cl_razon_{_sfx}", f"cl_phone_{_sfx}",
                        f"access_email_{_sfx}", f"found_email_{_sfx}",
                        f"reg_email_val_{_sfx}"]:
                st.session_state.pop(_wk, None)
            st.rerun()

    else:
        # Vista admin: campos directos de texto (siempre vacíos)
        st.markdown("##### 👤 Datos del cliente")
        _ai1, _ai2 = st.columns(2)
        with _ai1:
            client_name = st.text_input(T["name"], key="adm_name",
                                         placeholder=T["name_ph"])
            client_email = st.text_input("📧 Email", key="adm_email",
                                         placeholder="cliente@empresa.com")
        with _ai2:
            razon_social = st.text_input(T["company"], key="adm_razon",
                                         placeholder=T["company_ph"])
            _prefix_labels = [f"{nombre} {código}" for nombre, código in PHONE_PREFIXES]
            _pi_adm = st.selectbox(T["prefix"], range(len(PHONE_PREFIXES)),
                                   format_func=lambda i: _prefix_labels[i],
                                   key="adm_prefix_sel")
            _pn_adm = st.text_input(T["phone"], key="adm_phone",
                                    placeholder=T["phone_ph"])
            phone_full = f"{PHONE_PREFIXES[_pi_adm][1]} {_pn_adm}".strip()

    # ── Destination (first, so customer sees prices from the start) ─────────
    _dest_options = list(cfg_data["destinos"].keys())
    # Pre-select last used destination if exists
    _last_dest = _cd.get("last_destino", "") if standalone else ""
    _dest_idx = (_dest_options.index(_last_dest)
                  if _last_dest in _dest_options else 0)
    # --- Shipping type: FOB (sin flecha) or CIF (with arrow to destination)
    _fob_cif = st.radio(
        "Tipo de envío" if lang == "ES" else "Shipping type",
        ["FOB", "CIF Destino"],
        horizontal=True, key=f"fob_cif_{_sfx}",
        help="FOB: sin flecha. CIF Destino: incluye flecha al destino." if lang == "ES" else "FOB: no freight. CIF Destination: includes freight to destination."
    )

    if _fob_cif == "CIF Destino":
        ped_dest = st.selectbox(T["dest"], _dest_options, index=_dest_idx, key="cl_dest_sel")
        dest_code, dest_sym = get_dest_currency(ped_dest, cfg_data)
        dest_rate = fetch_dest_rate(dest_code)
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
                 "📅 Prices and shipping updated every Tuesday. For reference simulation."
        )
        st.caption(_nota)

    st.markdown("---")
    st.markdown(T["products"])

    OPT_PAL = T["opt_pal"]
    OPT_CAJ = T["opt_caj"]
    sfx = "cl" if standalone else "adm"

    # Solo productos activos (disponibles para pedido)
    lista_productos = [p for p in products_list if p.get("activo", True)]

    # Cabecera de columnas
    h1, h2, h3, h4 = st.columns([3, 1.8, 1.4, 1])
    h2.markdown(f"<small style='color:#888'>{T['unit_col']}</small>", unsafe_allow_html=True)
    h3.markdown(f"<small style='color:#888'>{T['qty_col']}</small>", unsafe_allow_html=True)
    h4.markdown(f"<small style='color:#888'>{T['boxes_col']}</small>", unsafe_allow_html=True)

    st.markdown("<hr style='margin:4px 0 8px 0'>", unsafe_allow_html=True)

    active_items = []
    below_minimum = []  # [(nombre, cajas_pedidas, cajas_minimo)]

    for p in lista_productos:
        cajas_pal = cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        cod = p["código"]
        min_c = get_min_boxes(cod, p, cfg_data)

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
                    lbl = T["min_pal"].format(n=pals, s="s" if pals > 1 else "", c=min_c)
                else:
                    lbl = T["min_caj"].format(n=min_c)
                st.caption(f"{_kg_str} · {lbl}")
            else:
                st.caption(_kg_str)

        with c2:
            unidad = st.selectbox(
                "u", [OPT_PAL, OPT_CAJ],
                label_visibility="collapsed",
                key=f"unit_{cod}_{sfx}",
            )

        with c3:
            is_pal = unidad == OPT_PAL
            cantidad = st.number_input(
                "q",
                min_value=0,
                step=1,
                format="%d",
                label_visibility="collapsed",
                key=f"qty_{cod}_{sfx}",
            )

        with c4:
            if cantidad > 0:
                cajas = int(cantidad) * cajas_pal if is_pal else int(cantidad)
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

    # — Customer notes (optional)
    _notas_lbl = "📋 Notas / Observaciones (opcional)" if lang == "ES" else "📋 Notes / Comments (optional)"
    st.text_area(_notas_lbl, key=f"notas_cl_{sfx}", height=80,
                 placeholder="Fecha preferida de entrega, instrucciones especiales..." if lang == "ES"
                 else "Preferred delivery date, special instructions...")

    # ==== Real-time summary (sidebar) ====
    with st.sidebar:
        if active_items:
            st.markdown("---")
            st.markdown("### 🛒 " + ("Resumen del pedido" if lang == "ES" else "Order Summary"))
            _tot_cajas_rt = sum(q for p, q in active_items)
            _tot_pallets_rt = sum(
                math.ceil(q/cfg_data["grupos"].get(p["grupo"], {}).get("cajas_pallet", 1))
                for p, q in active_items
            )
            st.metric("📦 Palets", f"{_tot_pallets_rt:.1f}")
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
        math.ceil(c/cfg_data["grupos"][g]["cajas_pallet"])
        for g, c in group_cajas.items()
    )

    # Progress bar
    faltan = max(0, MIN_PALLETS - total_pallets)
    pct = min(total_pallets / MIN_PALLETS, 1.0)
    if total_pallets < MIN_PALLETS:
        st.progress(pct, text=T["progress_low"].format(
            n=total_pallets, min=MIN_PALLETS, f=faltan, s="s" if faltan != 1 else ""))
    else:
        st.progress(1.0, text=T["progress_ok"].format(n=total_pallets))

    # Divisa local del destino
    dest_code, dest_sym = get_dest_currency(ped_dest, cfg_data)
    dest_rate = fetch_dest_rate(dest_code)
    show_local = dest_code not in ("USD",)
    loc_total_col = f"Total {dest_sym}{dest_code}" if show_local else None

    tarifa_dest = cfg_data["destinos"].get(ped_dest, 0) if ped_dest else 0

    rows = []
    for p, cajas in active_items:
        r = calc_pedido(p, cfg_data, ped_dest, total_cajas)
        cajas_pal = cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        row = {
            "Producto": p["producto"],
            "Palets": round(cajas / cajas_pal, 2),
            "Cajas": cajas,
            "Precio/caja $": r["precio_caja_usd"],
            "Total USD": r["precio_caja_usd"] * cajas,
        }
        if show_local:
            row[f"{dest_sym}/caja"] = r["precio_caja_usd"] * dest_rate
            row[loc_total_col] = r["precio_caja_usd"] * cajas * dest_rate
        rows.append(row)

    sum_df = pd.DataFrame(rows)
    total_usd = sum_df["Total USD"].sum()
    total_loc = sum_df[loc_total_col].sum() if show_local else None
    peso_kg = sum(p["kg_caja"] * q for p, q in active_items)

    # Métricas resumen
    if show_local and total_loc:
        _mcols = st.columns(5)
        _mcols[0].metric(T["pallets_m"], str(total_pallets))
        _mcols[1].metric(T["boxes_m"], f"{total_cajas:,}")
        _mcols[2].metric(T["weight_m"], f"{peso_kg:,.0f} kg")
        _mcols[3].metric("Total USD", f"${total_usd:,.2f}")
        _mcols[4].metric(f"Total {dest_code}", f"{dest_sym}{total_loc:,.2f}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(T["pallets_m"], str(total_pallets))
        c2.metric(T["boxes_m"], f"{total_cajas:,}")
        c3.metric(T["weight_m"], f"{peso_kg:,.0f} kg")
        c4.metric("Total USD", f"${total_usd:,.2f}")

    # Tarifa de flecha del destino — información complementaria
    if ped_dest:  # solo mostrar tarifa cuando es CIF
        _flete_info = (f"🚢 Tarifa flete {ped_dest}: **{tarifa_dest:.2f} USD/kg** · CIF destino"
                       if lang == "ES" else
                       f"🚢 Shipping rate {ped_dest}: **{tarifa_dest:.2f} USD/kg** · CIF destination")
        st.caption(_flete_info)

    def hl(col):
        return ["background-color:#e8f5e9;font-weight:bold"] * len(col) if "Total" in col.name else [""] * len(col)

    fmt = {"Palets": "{:.2f}", "Cajas": "{:,.0f}", "Precio/caja $": "${:.2f}", "Total USD": "${:,.2f}"}
    if show_local:
        fmt[f"{dest_sym}/caja"] = f"{dest_sym}{{:.2f}}"
        fmt[loc_total_col] = f"{dest_sym}{{:.2f}}"

    st.dataframe(
        sum_df.style.apply(hl, axis=0).format(fmt),
        use_container_width=True, hide_index=True,
    )

    with st.expander("📦 Detail by product group"):
        pal_rows = []
        for g, c in group_cajas.items():
            cap = cfg_data["grupos"][g]["cajas_pallet"]
            pals = math.ceil(c / cap)
            pal_rows.append({
                "Grupo": g, "Productos": cfg_data["grupos"][g]["nombre"],
                "Cajas": c, "Cajas/pallet": cap, "Pallets físicos": pals,
                "Ocupación": f"{c/(pals*cap)*100:.1f}%",
            })
        st.dataframe(pd.DataFrame(pal_rows), hide_index=True, use_container_width=True)

    st.markdown("---")

    # ── Confirm ──
    confirm_key = "confirm_cl" if standalone else "confirm_admin"
    albaran_key = f"albaran_{confirm_key}"
    _email_sent_key = f"email_sent_{confirm_key}"
    puede_confirmar = (total_pallets >= MIN_PALLETS
                     and bool(client_name) and bool(razon_social)
                     and bool(client_email))

    if not client_name or not razon_social or not client_email:
        st.warning(T["warn_fields"])
    elif total_pallets < MIN_PALLETS:
        st.warning(T["warn_pallets"].format(f=faltan, s="s" if faltan != 1 else "", min=MIN_PALLETS))
    if below_minimum:
        for nombre, pedido, minimo in below_minimum:
            st.error(T["below_min"].format(prod=nombre, got=pedido, need=minimo))

    puede_confirmar = puede_confirmar and len(below_minimum) == 0

    if st.button(T["confirm_btn"], type="primary", disabled=not puede_confirmar, key=confirm_key):
        with st.spinner("Procesando pedido..."):
            # Guardar todo lo necesario en session_state — independiente del estado del formulario
            cod_map = {p["código"]: p for p in products_list}
            st.session_state[albaran_key] = {
                "client_name": client_name,
                "razon_social": razon_social,
                "email": client_email,
                "telefono": phone_full,
                "destino": ped_dest,
                "notas_cliente": st.session_state.get(f"notas_cl_{sfx}", ""),
                "estado": "Recibido",
                "ai_codigos": [(p["código"], q) for p, q in active_items],
                "total_cajas": total_cajas,
                "total_pallets": total_pallets,
                "total_usd": total_usd,
                "total_loc": total_loc,
                "dest_code": dest_code,
                "dest_sym": dest_sym,
                "dest_rate": dest_rate,
                "lang": lang,
            }

    # ── Show albarán (persists aunque el formulario cambie) ──
    guardado = st.session_state.get(albaran_key)
    if guardado:
        _Ts = TR.get(guardado.get("lang", "ES"), TR["ES"])
        st.success(_Ts["confirmed_ok"].format(name=guardado["client_name"], dest=guardado["destino"]))
        st.info("📋 Pedido #" + str(guardado.get("id", "")) + " registrado correctamente.")

        cod_map = {p["código"]: p for p in products_list}
        ai_full = [(cod_map[c], q) for c, q in guardado["ai_codigos"] if c in cod_map]

        try:
            _dc = guardado.get("dest_code", "USD")
            _ds = guardado.get("dest_sym", "$")
            _dr = guardado.get("dest_rate", 1.0)
            _lang = guardado.get("lang", "ES")
            pdf_bytes = gen_albaran_pdf(
                guardado["client_name"], guardado["razon_social"], guardado["destino"],
                ai_full, guardado["total_cajas"], guardado["total_pallets"],
                guardado["total_usd"], cfg_data,
                client_email=guardado.get("email", ""),
                telefono=guardado.get("telefono", ""),
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr, lang=_lang,
                total_flete=guardado.get("total_flete", 0.0),
            )
            wa_text = gen_wa_text(
                guardado["client_name"], guardado["razon_social"], guardado["destino"],
                ai_full, guardado["total_cajas"], guardado["total_pallets"],
                guardado["total_usd"], cfg_data,
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr, lang=_lang,
            )
            # Añadir datos de contacto al mensaje WhatsApp
            extra = []
            if guardado.get("email"):
                extra.append(f"📧 {guardado['email']}")
            if guardado.get("telefono"):
                extra.append(f"📞 {guardado['telefono']}")
            if extra:
                wa_text = wa_text.replace("━━━━━━━━━━━━━━━━━━━━━\n*PRODUCTOS:*",
                    "━━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(extra) +
                    "\n━━━━━━━━━━━━━━━━━━━━━\n*PRODUCTOS:*")

            fname = f"Albaran_{guardado['client_name'].replace(' ','_')}_{date.today()}.pdf"
            wa_url = "https://wa.me/?text=" + urllib.parse.quote(wa_text)
            subj = urllib.parse.quote(f"Pedido Export Haret – {guardado['client_name']}")
            body = urllib.parse.quote(wa_text.replace("*", ""))
            mail_url = f"mailto:order@exportharet.com?subject={subj}&body={body}"

            # ── Register client and order ────────────────────────────────────
            register_order(guardado, ai_full, cfg_data)

            # — Automatic SMTP sending (only once) ────────────────────────
            if not st.session_state.get(_email_sent_key, False):
                email_ok, email_msg = send_order_email(guardado, ai_full, pdf_bytes, cfg_data, wa_text)
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


# ── Client order history ────────────────────────────────────────────────────

def render_order_history(client_email: str, lang: str = "ES"):
    """Muestra los pedidos anteriores de un cliente con estados visuales."""
    clients = load_clients()
    data = load_data()
    c = clients.get(client_email, {})
    pedidos = c.get("pedidos", [])

    if lang == "EN":
        titulo = "### 📋 Your Orders"
        sin_ped = "You don't have any previous orders yet."
        lbl_tot = "Total USD"
        lbl_pal = "Pallets"
        lbl_cajas = "Boxes"
        lbl_prod = "**Products:**"
        lbl_estado = "Status"
        lbl_notas = "Notes"
        lbl_fecha = "Date"
    else:
        titulo = "### 📋 Mis Pedidos"
        sin_ped = "Aún no tienes pedidos anteriores."
        lbl_tot = "Total USD"
        lbl_pal = "Palets"
        lbl_cajas = "Cajas"
        lbl_prod = "**Productos:**"
        lbl_estado = "Estado"
        lbl_notas = "Notas"
        lbl_fecha = "Fecha"

    st.markdown(titulo)
    if not pedidos:
        st.info(sin_ped)
        return

    for ped in reversed(pedidos):
        ped_id = ped.get("id", "").upper()
        ped_dest = ped.get("destino", "")
        ped_tot = ped.get("total_usd", 0)
        ped_pals = ped.get("pallets", 0)
        ped_caj = sum(p.get("cajas", 0) for p in ped.get("productos", []))
        ped_fecha = ped.get("fecha", ped.get("date", ""))[:10]
        ped_notas = ped.get("notas", ped.get("notes", ""))
        _e_estado = ped.get("estado", "Recibido")
        icono_e = ORDER_STATES_COLORS.get(_e_estado, "📦")
        _e_colors = {
            "Recibido": "blue",
            "Confirmado": "orange",
            "En preparación": "orange",
            "Enviado": "violet",
            "Entregado": "green",
        }
        badge_color = _e_colors.get(_e_estado, "blue")
        # Barra de progreso
        try:
            prog_idx = ORDER_STATES.index(_e_estado)
        except ValueError:
            prog_idx = 0
        prog_pct = int((prog_idx / (len(ORDER_STATES) - 1)) * 100)

        lbl_en = ORDER_STATES_EN.get(_e_estado, _e_estado) if lang == "ES" else _e_estado

        with st.expander(f"{icono_e} **#{ped_id}** — {ped_dest} | {ped_fecha} | :{badge_color}[{lbl_en}]", expanded=False):
            st.progress(prog_pct, text=f"{lbl_estado}: {lbl_en}")
            col1, col2, col3 = st.columns(3)
            col1.metric(lbl_tot, f"${ped_tot:,.2f}")
            col2.metric(lbl_pal, ped_pals)
            col3.metric(lbl_cajas, ped_caj)
            prods = ped.get("productos", [])
            if prods:
                st.markdown(lbl_prod)
                for p in prods:
                    pnom = p.get("nombre", p.get("name", p.get("codigo", "")))
                    pcaj = p.get("cajas", 0)
                    st.markdown(f" - {pnom}: {pcaj} cajas")
            if ped_notas:
                st.caption(f"📝 {lbl_notas}: {ped_notas}")


# ── Client view (URL ?view=cliente) ──────────────────────────────────────────

# --- Load global data (available in client and admin view) ---
data = load_data()
cfg = data["config"]
productos = data.get("productos", [])

IS_CLIENT = st.query_params.get("view", "") == "cliente"

if IS_CLIENT:
    _verificado = st.session_state.get("client_verified_cl", False)
    _cdata = st.session_state.get("client_data_cl", {})

    if not _verificado:
        # ── Access/registration screen ──────────────────────────────────────
        render_order_form(cfg, productos, standalone=True,
                          show_header=True, require_email=True)
    else:
        # ── Client portal (already identified) ───────────────────────────────
        _lang = "EN" if "EN" in st.session_state.get("order_lang", "🇪🇸 ES") else "ES"

        # Header: centered logo
        _lp = os.path.join(os.path.dirname(__file__), "logo.png")
        _pc1, _pc2, _pc3 = st.columns([1, 2, 1])
        with _pc2:
            if os.path.exists(_lp):
                st.image(_lp, width=200)

        # Welcome bar + logout
        _ph1, _ph2 = st.columns([5, 1])
        with _ph1:
            st.markdown(
                f"👤 **{_cdata.get('nombre','')}**  |  "
                f"🏢 {_cdata.get('razon_social','')}  |  "
                f"📧 {_cdata.get('email','')}  |  "
                f"📞 {_cdata.get('telefono','—')}"
            )
        with _ph2:
            _exit_lbl = "🚪 Exit" if _lang == "EN" else "🚪 Salir"
            if st.button(_exit_lbl, key="portal_exit", use_container_width=True):
                st.session_state["client_verified_cl"] = False
                st.session_state["client_data_cl"] = {}
                st.rerun()

        st.markdown("---")

        # Tabs: New Order | My Orders
        if _lang == "EN":
            _tab1, _tab2 = st.tabs(["🛒 New Order", "📋 My Orders"])
        else:
            _tab1, _tab2 = st.tabs(["🛒 Nuevo Pedido", "📋 Mis Pedidos"])

        with _tab1:
            render_order_form(cfg, productos, standalone=True,
                              show_header=False, require_email=False)
        with _tab2:
            render_order_history(_cdata.get("email", ""), lang=_lang)

    st.stop()

# ── Admin authentication ─────────────────────────────────────────────────────
def _get_cred(key: str, default: str) -> str:
    try:
        return st.secrets.get(key, default)
    except Exception:
        # Fallback: read from local secrets.toml
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
    # ── Login screen ─────────────────────────────────────────────────────────
    _logo_login = os.path.join(os.path.dirname(__file__), "logo.png")
    lc1, lc2, lc3 = st.columns([1, 2, 1])
    with lc2:
        st.markdown("<br>", unsafe_allow_html=True)
        if os.path.exists(_logo_login):
            st.image(_logo_login, width=220)
        st.markdown("## Panel de administración")
        st.markdown("---")
        with st.form("login_form"):
            usr = st.text_input("👤 Usuario", placeholder="exportharet")
            pwd = st.text_input("🔒 Contraseña", type="password", placeholder="••••••••")
            ok = st.form_submit_button("Iniciar sesión", type="primary",
                                         use_container_width=True)
            if ok:
                if usr == ADMIN_USER and pwd == ADMIN_PASS:
                    st.session_state.admin_ok = True
                    st.rerun()
                else:
                    st.error("❌ Usuario o contraseña incorrectos.")

        st.markdown(
            "<center><small style='color:#aaa'>¿Cliente? Acceda al formulario de pedido en<br>"
            f"<a href='{get_network_url(8501)}/?view=cliente' target='_blank'>"
            "exportharet-pedidos.streamlit.app/?view=cliente</a></small></center>",
            unsafe_allow_html=True,
        )
    st.stop()

# ── Sidebar (admin only) ─────────────────────────────────────────────────────
with st.sidebar:
    # Logo: use local file if exists, otherwise green placeholder
    _logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    if os.path.exists(_logo_path):
        st.image(_logo_path, use_container_width=True)
    else:
        st.image("https://placehold.co/220x70/2d6a4f/white?text=Export+Haret", use_container_width=True)
    st.markdown("---")
    destino = st.selectbox("🌍 Destino", list(cfg["destinos"].keys()), key="sidebar_dest_sel")
    num_pallets = st.slider("📦 Pallets", 1, 23, 1)
    st.markdown("---")
    st.markdown(
        f"**1 EUR = {cfg['eur_usd']:.4f} USD** \n"
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
st.markdown("## 🌿 Exportar Haret — Pedidos")
st.markdown(
    f"**Destino:** {destino}  |  "
    f"**1 EUR = {cfg['eur_usd']:.4f} USD**  "
    f"<small style='color:#888'>{cfg.get('_rate_label','')}</small>",
    unsafe_allow_html=True,
)

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["📊 Dashboard", "📋 Cotización", "🛒 Hacer pedido", "✏️ Actualizar precios", "🌐 Todos los destinos", "⚙️ Configuración", "👥 Clientes", "📦 Pedidos"])

# ── TAB 0: Dashboard ─────────────────────────────────────────────────────────
with tab0:
    st.markdown("### 📊 Dashboard — Resumen del negocio")
    _clients = load_clients()
    _total_clients = len(_clients)
    _total_orders = sum(len(c.get("pedidos", [])) for c in _clients.values())
    _total_revenue = sum(
        sum(p.get("total_usd", 0) for p in c.get("pedidos", []))
        for c in _clients.values()
    )

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("👥 Clientes", _total_clients)
    col_b.metric("📦 Pedidos totales", _total_orders)
    col_c.metric("💰 Ingresos USD", f"${_total_revenue:,.2f}")

    st.markdown("---")
    st.info("📊 Resumen actualizado. Selecciona otra pestaña para ver detalles o realizar acciones.")

# ── TAB 1: Cotización (Upload Cotizaciones.xlsx) ──────────────────────────────
with tab1:
    st.markdown("### 📋 Cotización — Actualizar desde Cotizaciones.xlsx")
    st.caption("Sube tu archivo Cotizaciones.xlsx para actualizar precios de compra y tarifas de flete.")

    _uploaded_file = st.file_uploader("📁 Sube Cotizaciones.xlsx", type="xlsx", key="upload_cotizaciones")
    if _uploaded_file:
        try:
            excel_bytes = _uploaded_file.read()
            new_products, new_cfg, cambios = sync_from_cotizaciones(excel_bytes, data)

            if cambios:
                st.success(f"✅ Se detectaron **{len(cambios)}** cambios:")
                for cambio in cambios:
                    st.markdown(f" - {cambio}")

                if st.button("💾 Guardar cambios", type="primary", key="btn_save_cotizaciones"):
                    data["productos"] = new_products
                    data["config"] = new_cfg
                    save_data(data)
                    st.success("✅ Cambios guardados correctamente.")
                    st.rerun()
            else:
                st.info("ℹ️ No hay cambios detectados en la cotización.")
        except Exception as e:
            st.error(f"❌ Error procesando archivo: {e}")

# ── TAB 2: Hacer pedido (Admin form) ─────────────────────────────────────────
with tab2:
    st.markdown("### 🛒 Hacer pedido — Panel de administrador")
    st.caption("Crea un pedido en nombre de un cliente.")
    render_order_form(cfg, productos, standalone=False, show_header=False, require_email=False)

# ── TAB 3: Actualizar precios ────────────────────────────────────────────────
with tab3:
    st.markdown("### ✏️ Actualizar precios")
    st.caption("Edita precios de compra, tarifas de flete y otros parámetros.")

    # General parameters
    st.markdown("#### ⚙️ Parámetros generales")
    _cfg_cols = st.columns(3)

    with _cfg_cols[0]:
        new_cost_caja = st.number_input(
            "Costo caja (USD)",
            value=cfg.get("costo_caja", 0.0),
            key="edit_costo_caja"
        )
    with _cfg_cols[1]:
        new_merma = st.number_input(
            "Merma %",
            value=cfg.get("merma_pct", 0.0),
            key="edit_merma_pct"
        )
    with _cfg_cols[2]:
        new_due = st.number_input(
            "DUE (días)",
            value=cfg.get("due", 0),
            key="edit_due"
        )

    # Product prices
    st.markdown("#### 📦 Precios de productos")
    _prod_data = []
    for p in productos:
        _prod_data.append({
            "Producto": p.get("producto", ""),
            "Código": p.get("código", ""),
            "Precio compra": p.get("precio_compra", 0.0),
        })

    _df_prods = pd.DataFrame(_prod_data)
    st.dataframe(_df_prods, use_container_width=True, key="df_products_view")

    if st.button("💾 Guardar cambios", type="primary", key="btn_save_precios"):
        cfg["costo_caja"] = new_cost_caja
        cfg["merma_pct"] = new_merma
        cfg["due"] = new_due
        data["config"] = cfg
        save_data(data)
        st.success("✅ Precios actualizados correctamente.")
        st.rerun()

# ── TAB 4: Todos los destinos ────────────────────────────────────────────────
with tab4:
    st.markdown("### 🌐 Todos los destinos")
    st.caption("Resumen de tarifas de flete por destino.")

    destinos_data = []
    for dest_name, dest_rate in cfg.get("destinos", {}).items():
        destinos_data.append({
            "Destino": dest_name,
            "Tarifa (USD/kg)": dest_rate,
        })

    _df_dests = pd.DataFrame(destinos_data)
    st.dataframe(_df_dests, use_container_width=True, key="df_destinations_view")

# ── TAB 5: Configuración ─────────────────────────────────────────────────────
with tab5:
    st.markdown("### ⚙️ Configuración")
    st.caption("Parámetros principales del sistema.")

    cfg_cols = st.columns(2)
    with cfg_cols[0]:
        st.markdown(f"**EUR → USD:** {cfg.get('eur_usd', 1.0):.4f}")
        st.caption(cfg.get('_rate_label', 'Rate label'))
    with cfg_cols[1]:
        st.markdown(f"**Min. Palets:** {cfg.get('min_pallets', 3)}")

    st.markdown("---")
    st.markdown("#### 📊 Parámetros de cálculo")
    st.markdown(f"- **Costo caja:** ${cfg.get('costo_caja', 0.0):.2f}")
    st.markdown(f"- **Merma %:** {cfg.get('merma_pct', 0.0)}%")
    st.markdown(f"- **DUE (días):** {cfg.get('due', 0)}")
    st.markdown(f"- **Peso pallet:** {cfg.get('peso_pallet', 0.0)} kg")
    st.markdown(f"- **Tara caja:** {cfg.get('tara_caja', 0.0)} kg")

# ── TAB 6: Clientes ──────────────────────────────────────────────────────────
with tab6:
    st.markdown("### 👥 Clientes")
    st.caption("Base de datos de clientes registrados.")

    _clients_db = load_clients()

    if not _clients_db:
        st.info("ℹ️ No hay clientes registrados aún.")
    else:
        clients_data = []
        for email, client_info in _clients_db.items():
            clients_data.append({
                "Email": email,
                "Nombre": client_info.get("nombre", ""),
                "Razón Social": client_info.get("razon_social", ""),
                "Teléfono": client_info.get("telefono", "—"),
                "Pedidos": len(client_info.get("pedidos", [])),
                "Primer pedido": client_info.get("primer_pedido", "—"),
                "Último pedido": client_info.get("ultimo_pedido", "—"),
            })

        _df_clients = pd.DataFrame(clients_data)
        st.dataframe(_df_clients, use_container_width=True, key="df_clients_view")

# ── TAB 7: Pedidos ───────────────────────────────────────────────────────────
with tab7:
    st.markdown("### 📦 Pedidos")
    st.caption("Historial y gestión de todos los pedidos.")

    _clients_db = load_clients()
    all_orders = []

    for email, client_info in _clients_db.items():
        for order in client_info.get("pedidos", []):
            all_orders.append({
                "ID Pedido": order.get("id", "").upper(),
                "Cliente": client_info.get("nombre", ""),
                "Email": email,
                "Fecha": order.get("fecha", ""),
                "Destino": order.get("destino", ""),
                "Total USD": order.get("total_usd", 0),
                "Cajas": sum(p.get("cajas", 0) for p in order.get("productos", [])),
                "Estado": order.get("estado", "Recibido"),
            })

    if not all_orders:
        st.info("ℹ️ No hay pedidos registrados aún.")
    else:
        _df_orders = pd.DataFrame(all_orders)
        st.dataframe(_df_orders, use_container_width=True, key="df_orders_view")

        # Order state selector
        st.markdown("---")
        st.markdown("#### ✏️ Actualizar estado de pedido")
        selected_order_id = st.selectbox(
            "Selecciona un pedido",
            [o["ID Pedido"] for o in all_orders],
            key="select_order_to_update"
        )

        if selected_order_id:
            new_state = st.selectbox(
                "Nuevo estado",
                ORDER_STATES,
                key="select_new_order_state"
            )

            if st.button("💾 Actualizar estado", type="primary", key="btn_update_order_state"):
                # Find and update the order
                for email, client_info in _clients_db.items():
                    for order in client_info.get("pedidos", []):
                        if order.get("id", "").upper() == selected_order_id:
                            order["estado"] = new_state
                            save_clients(_clients_db)
                            send_status_email(order, new_state)
                            st.success(f"✅ Pedido actualizado a: {new_state}")
                            st.rerun()
                            break
