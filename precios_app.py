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
from datetime import date
from fpdf import FPDF
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

st.set_page_config(
    page_title="Export Haret — Pedidos",
    page_icon="🌿",
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


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    return json.loads(json.dumps(INITIAL_DATA))  # deep copy


def save_data(data):
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
    tarifa = cfg["destinos"][destino]
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
                    dest_code="USD", dest_sym="$", dest_rate=1.0):
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
    pdf.cell(0, 10, "ALBARÁN DE PEDIDO", ln=True, align="C")
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.6)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    # ── Datos del cliente ──
    rate_label = cfg_data.get("_rate_label", "").replace("🟢","").replace("🟡","").strip()
    dest_code_pdf, dest_sym_pdf = DESTINO_DIVISA.get(destino, ("USD","$"))
    dest_rate_pdf = fetch_dest_rate(dest_code_pdf)
    client_fields = [
        ("Cliente:",      client_name),
        ("Razón social:", razon_social),
    ]
    if client_email: client_fields.append(("Email:",     client_email))
    if telefono:     client_fields.append(("Teléfono:",  telefono))
    client_fields += [
        ("Fecha:",   date.today().strftime("%d/%m/%Y")),
        ("Destino:", destino),
        ("EUR/USD:", f"{cfg_data['eur_usd']:.4f}  ({rate_label})"),
    ]
    if dest_code_pdf not in ("USD",):
        client_fields.append((f"Divisa {dest_code_pdf}:", f"1 USD = {dest_rate_pdf:.4f} {dest_sym_pdf}"))
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
    headers = ["Producto", "Cajas", "Pallets", "Precio/caja USD", "Total USD"]
    aligns  = ["L", "C", "C", "R", "R"]
    for w, h, a in zip(widths, headers, aligns):
        pdf.cell(w, 7, h, fill=True, align=a)
    pdf.ln()

    pdf.set_text_color(0, 0, 0)
    pdf.set_font("U", "", 9)
    fill = False
    for p, cajas in active_items:
        r = calc_pedido(p, cfg_data, destino, total_cajas)
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
    pdf.cell(100, 7, f"Total pallets: {total_pallets}   ·   Total cajas: {total_cajas:,}")
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
    pdf.cell(0, 5, "Export Haret  ·  order@exportharet.com  ·  Documento generado automáticamente",
             align="C", ln=True)

    return bytes(pdf.output())


def gen_wa_text(client_name, razon_social, destino, active_items,
                total_cajas, total_pallets, total_usd, cfg_data,
                total_eur=None, dest_code="USD", dest_sym="$", dest_rate=1.0):
    lines = [
        "🌿 *PEDIDO — EXPORT HARET*",
        "━━━━━━━━━━━━━━━━━━━━━",
        f"👤 Cliente: {client_name}",
        f"🏢 Razón social: {razon_social}",
        f"📅 Fecha: {date.today().strftime('%d/%m/%Y')}",
        f"✈️ Destino: {destino}",
        "━━━━━━━━━━━━━━━━━━━━━",
        "*PRODUCTOS:*",
    ]
    for p, cajas in active_items:
        r = calc_pedido(p, cfg_data, destino, total_cajas)
        pal = cajas / cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        total = r["precio_caja_usd"] * cajas
        lines.append(f"• {p['producto']}: {cajas} cajas ({pal:.2f} pal) — ${total:,.2f}")
    total_loc = total_usd * dest_rate
    lines += [
        "━━━━━━━━━━━━━━━━━━━━━",
        f"📦 Total: {total_cajas:,} cajas  |  {total_pallets} pallets",
        f"💵 *Total USD: ${total_usd:,.2f}*",
    ]
    if dest_code != "USD":
        lines.append(f"💱 *Total {dest_code}: {dest_sym}{total_loc:,.2f}*")
    return "\n".join(lines)


def render_order_form(cfg_data, products_list, standalone=False):
    """Formulario de pedido. standalone=True = vista cliente, False = pestaña admin."""
    MIN_PALLETS = 3

    if standalone:
        _logo_path_s = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(_logo_path_s):
            st.image(_logo_path_s, width=180)
        st.markdown("## 🌿 Export Haret — Pedidos")
        st.markdown("---")

    # ── Datos del cliente ──
    st.markdown("#### 👤 Datos del cliente")
    cc1, cc2 = st.columns(2)
    with cc1:
        client_name  = st.text_input("Nombre del cliente *", key="cl_name",
                                      placeholder="Nombre completo")
        razon_social = st.text_input("Razón social / Empresa *", key="cl_razon",
                                      placeholder="Empresa S.L.")
        client_email = st.text_input("📧 Email de contacto *", key="cl_email",
                                      placeholder="cliente@empresa.com")
        # Teléfono con prefijo de país
        prefix_labels = [f"{name}  {code}" for name, code in PHONE_PREFIXES]
        prefix_idx    = st.selectbox("📞 País / Prefijo *", range(len(PHONE_PREFIXES)),
                                      format_func=lambda i: prefix_labels[i],
                                      key="cl_phone_prefix")
        phone_num     = st.text_input("Número de teléfono *", key="cl_phone_num",
                                       placeholder="612 345 678")
        phone_full    = f"{PHONE_PREFIXES[prefix_idx][1]} {phone_num}".strip()

    with cc2:
        ped_dest = st.selectbox("🌍 Destino *", list(cfg_data["destinos"].keys()),
                                 key="cl_dest")
        # Divisa del destino
        dest_code, dest_sym = DESTINO_DIVISA.get(ped_dest, ("USD", "$"))
        dest_rate           = fetch_dest_rate(dest_code)
        if dest_code == "USD":
            st.info(f"Mínimo de orden: **{MIN_PALLETS} pallets** totales.\n\nDivisa: **USD ($)**")
        else:
            st.info(
                f"Mínimo de orden: **{MIN_PALLETS} pallets** totales.\n\n"
                f"Divisa del destino: **{dest_code} ({dest_sym})** · "
                f"1 USD = {dest_rate:.4f} {dest_code}"
            )

    st.markdown("---")
    st.markdown("#### 📦 Productos del pedido")

    OPT_PAL = "📦 Pallets"
    OPT_CAJ = "🗃️ Cajas"
    sfx     = "cl" if standalone else "adm"

    # Solo productos activos (disponibles para pedido)
    products_list = [p for p in products_list if p.get("activo", True)]

    # Cabecera de columnas
    h1, h2, h3, h4 = st.columns([3, 1.8, 1.4, 1])
    h2.markdown("<small style='color:#888'>Unidad</small>", unsafe_allow_html=True)
    h3.markdown("<small style='color:#888'>Cantidad</small>", unsafe_allow_html=True)
    h4.markdown("<small style='color:#888'>= Cajas</small>", unsafe_allow_html=True)

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
            if min_c > 0:
                if min_c % cajas_pal == 0:
                    pals = min_c // cajas_pal
                    lbl = f"mín. {pals} pallet{'s' if pals>1 else ''} ({min_c} cajas)"
                else:
                    lbl = f"mín. {min_c} cajas"
                st.caption(lbl)

        with c2:
            unit = st.selectbox(
                "u", [OPT_PAL, OPT_CAJ],
                label_visibility="collapsed",
                key=f"unit_{cod}_{sfx}",
            )

        with c3:
            is_pal = unit == OPT_PAL
            qty = st.number_input(
                "q",
                min_value=0,
                step=1,
                format="%d",
                label_visibility="collapsed",
                key=f"qty_{cod}_{sfx}",
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

    if not active_items:
        st.caption("↑ Elige **📦 Pallets** o **🗃️ Cajas** e ingresa la cantidad de cada producto.")
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
        st.progress(pct, text=f"🔴 {total_pallets} de {MIN_PALLETS} pallets mínimos — faltan {faltan} pallet{'s' if faltan != 1 else ''}")
    else:
        st.progress(1.0, text=f"✅ {total_pallets} pallets — pedido válido")

    # Divisa local del destino
    dest_code, dest_sym = DESTINO_DIVISA.get(ped_dest, ("USD", "$"))
    dest_rate           = fetch_dest_rate(dest_code)
    show_local          = dest_code not in ("USD",)
    loc_total_col       = f"Total {dest_sym}{dest_code}" if show_local else None

    rows = []
    for p, cajas in active_items:
        r = calc_pedido(p, cfg_data, ped_dest, total_cajas)
        cajas_pal = cfg_data["grupos"][p["grupo"]]["cajas_pallet"]
        row = {
            "Producto":      p["producto"],
            "Pallets":       round(cajas / cajas_pal, 2),
            "Cajas":         cajas,
            "Precio/caja $": r["precio_caja_usd"],
            "Total USD":     r["precio_caja_usd"] * cajas,
        }
        if show_local:
            row[f"{dest_sym}/caja"]  = r["precio_caja_usd"] * dest_rate
            row[loc_total_col]       = r["precio_caja_usd"] * cajas * dest_rate
        rows.append(row)

    sum_df    = pd.DataFrame(rows)
    total_usd = sum_df["Total USD"].sum()
    total_loc = sum_df[loc_total_col].sum() if show_local else None
    peso_kg   = sum(p["kg_caja"] * q for p, q in active_items)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pallets",   str(total_pallets))
    c2.metric("Cajas",     f"{total_cajas:,}")
    c3.metric("Peso neto", f"{peso_kg:,.0f} kg")
    c4.metric("Total USD", f"${total_usd:,.2f}")
    if show_local and total_loc:
        c5.metric(f"Total {dest_code}", f"{dest_sym}{total_loc:,.2f}")
    else:
        c5.metric("Pallets físicos", str(total_pallets))

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
    can_confirm   = (total_pallets >= MIN_PALLETS
                     and bool(client_name) and bool(razon_social)
                     and bool(client_email) and bool(phone_num))

    if not client_name or not razon_social or not client_email or not phone_num:
        st.warning("⚠️ Completa todos los datos del cliente para confirmar.")
    elif total_pallets < MIN_PALLETS:
        st.warning(f"⚠️ Faltan {faltan} pallet{'s' if faltan != 1 else ''} para alcanzar el mínimo de {MIN_PALLETS}.")
    if below_minimum:
        for nombre, pedido, minimo in below_minimum:
            st.error(f"⚠️ **{nombre}**: pediste {pedido} cajas — mínimo es {minimo} cajas.")

    can_confirm = can_confirm and len(below_minimum) == 0

    btn_label = "✅ Confirmar Pedido"
    if st.button(btn_label, type="primary", disabled=not can_confirm, key=confirm_key):
        # Guardar todo lo necesario en session_state — independiente del estado del formulario
        cod_map = {p["codigo"]: p for p in products_list}
        st.session_state[albaran_key] = {
            "client_name":  client_name,
            "razon_social": razon_social,
            "email":        client_email,
            "telefono":     phone_full,
            "destino":      ped_dest,
            "ai_codigos":   [(p["codigo"], q) for p, q in active_items],
            "total_cajas":  total_cajas,
            "total_pallets": total_pallets,
            "total_usd":    total_usd,
            "total_loc":    total_loc,
            "dest_code":    dest_code,
            "dest_sym":     dest_sym,
            "dest_rate":    dest_rate,
        }

    # ── Mostrar albarán (persiste aunque el formulario cambie) ──
    saved = st.session_state.get(albaran_key)
    if saved:
        st.success(f"✅ Pedido confirmado — {saved['client_name']} · {saved['destino']}")

        cod_map = {p["codigo"]: p for p in products_list}
        ai_full = [(cod_map[c], q) for c, q in saved["ai_codigos"] if c in cod_map]

        try:
            _dc = saved.get("dest_code","USD")
            _ds = saved.get("dest_sym","$")
            _dr = saved.get("dest_rate", 1.0)
            pdf_bytes = gen_albaran_pdf(
                saved["client_name"], saved["razon_social"], saved["destino"],
                ai_full, saved["total_cajas"], saved["total_pallets"],
                saved["total_usd"], cfg_data,
                client_email=saved.get("email",""),
                telefono=saved.get("telefono",""),
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr,
            )
            wa_text = gen_wa_text(
                saved["client_name"], saved["razon_social"], saved["destino"],
                ai_full, saved["total_cajas"], saved["total_pallets"],
                saved["total_usd"], cfg_data,
                dest_code=_dc, dest_sym=_ds, dest_rate=_dr,
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

            # ── Envío automático por SMTP ──────────────────────────────────────
            email_ok, email_msg = send_order_email(saved, ai_full, pdf_bytes, cfg_data, wa_text)
            if email_ok:
                st.success("📨 Pedido enviado automáticamente a **order@exportharet.com**")
            elif email_msg == "sin_smtp":
                st.info("💡 Configura SMTP_USER / SMTP_PASS en los secretos para envío automático.")
            else:
                st.warning(f"⚠️ No se pudo enviar email automático: {email_msg}")

            ba1, ba2, ba3, ba4 = st.columns([2, 2, 2, 1])
            with ba1:
                st.download_button("📄 Descargar Albarán PDF", pdf_bytes,
                                   file_name=fname, mime="application/pdf",
                                   use_container_width=True)
            with ba2:
                st.link_button("📱 Enviar por WhatsApp", wa_url, use_container_width=True)
            with ba3:
                st.link_button("📧 Enviar por Email", mail_url, use_container_width=True)
            with ba4:
                if st.button("🔄 Nuevo", key=f"new_{confirm_key}", use_container_width=True):
                    del st.session_state[albaran_key]
                    st.rerun()
        except Exception as e:
            st.error(f"Error generando el albarán: {e}")


# ── Load ──────────────────────────────────────────────────────────────────────
if "data" not in st.session_state:
    st.session_state.data = load_data()

data = st.session_state.data
cfg = data["config"]
products = data["products"]
minimos = data.get("minimos", INITIAL_DATA["minimos"])
cfg["minimos"] = minimos

# ── Tipo de cambio en vivo (BCE, actualizado cada hora) ───────────────────────
_live_rate, _rate_label = fetch_live_eur_usd()
if _live_rate:
    cfg["eur_usd"] = _live_rate      # usada en calc(), calc_pedido() y albarán
    cfg["_rate_label"] = _rate_label
else:
    cfg["_rate_label"] = f"🟡 Manual · {cfg['eur_usd']:.4f}"

# ── Vista cliente (URL ?view=cliente) ─────────────────────────────────────────
IS_CLIENT = st.query_params.get("view", "") == "cliente"

if IS_CLIENT:
    render_order_form(cfg, products, standalone=True)
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

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("## 🌿 Export Haret — Pedidos")
st.markdown(
    f"**Destino:** {destino} &nbsp;|&nbsp; "
    f"**1 EUR = {cfg['eur_usd']:.4f} USD** &nbsp;"
    f"<small style='color:#888'>{cfg.get('_rate_label','')}</small>",
    unsafe_allow_html=True,
)

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Cotización", "🛒 Hacer pedido", "✏️ Actualizar precios", "🌐 Todos los destinos", "⚙️ Configuración"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — COTIZACIÓN
# ══════════════════════════════════════════════════════════════════════════════
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
    render_order_form(cfg, products, standalone=False)

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
            f"Hola, aquí puedes hacer tu pedido a Export Haret:\n{client_url}"
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
    st.markdown("### Actualizar precios de compra")
    st.info("Edita los precios de compra directamente en la tabla. Los cambios se guardan al presionar **Guardar**.")

    edit_df = pd.DataFrame([
        {
            "Código": p["codigo"],
            "Producto": p["producto"],
            "kg/caja": p["kg_caja"],
            "Precio compra (USD/caja)": p["precio_compra"],
            "Margen %": round(p["margen_pct"] * 100, 1),
            "Grupo": p["grupo"],
        }
        for p in products
    ])

    edited = st.data_editor(
        edit_df,
        use_container_width=True,
        hide_index=True,
        disabled=["Código", "Producto", "kg/caja", "Grupo"],
        column_config={
            "Precio compra (USD/caja)": st.column_config.NumberColumn(
                "Precio compra (USD/caja)", min_value=0.0, step=0.01, format="$%.2f"
            ),
            "Margen %": st.column_config.NumberColumn(
                "Margen %", min_value=0.0, max_value=100.0, step=0.5, format="%.1f%%"
            ),
        },
        key="price_editor",
    )

    col_save, col_reset = st.columns([1, 5])
    with col_save:
        if st.button("💾 Guardar", type="primary", use_container_width=True):
            for i, row in edited.iterrows():
                products[i]["precio_compra"] = float(row["Precio compra (USD/caja)"])
                products[i]["margen_pct"] = float(row["Margen %"]) / 100.0
            save_data(data)
            st.success("✅ Precios guardados correctamente.")
            st.rerun()
    with col_reset:
        if st.button("↩️ Restablecer datos originales", use_container_width=False):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.session_state.data = json.loads(json.dumps(INITIAL_DATA))
            st.rerun()

    st.markdown("---")
    st.markdown("#### Desglose de costos (precio actual)")
    breakdown_dest = st.selectbox("Destino para desglose", list(cfg["destinos"].keys()), key="breakdown_dest")
    breakdown_pals = st.slider("Pallets para desglose", 1, 23, 1, key="breakdown_pals")

    brows = []
    for p in products:
        r = calc(p, cfg, breakdown_dest, breakdown_pals)
        brows.append({
            "Producto": p["producto"],
            "Compra": p["precio_compra"],
            "Costo caja": r["Costo caja"],
            "Merma": r["FOB + Merma"] - r["FOB base"],
            "Margen": r["FOB Final"] - r["FOB + Merma"],
            "Flete": r["Flete"],
            "DUE/caja": r["Pal USD"] - r["CIF USD"] - (cfg["transporte_interno"] / (breakdown_pals * cfg["grupos"][p["grupo"]]["cajas_pallet"])),
            "Transporte": cfg["transporte_interno"] / (breakdown_pals * cfg["grupos"][p["grupo"]]["cajas_pallet"]),
            "→ Precio final": r["Pal USD"],
        })

    bdf = pd.DataFrame(brows)
    st.dataframe(
        bdf.style.format({c: "${:.4f}" for c in bdf.columns if c not in ("Producto",)}),
        use_container_width=True,
        hide_index=True,
    )


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

    st.markdown("---")
    new_public_url = st.text_input(
        "🌐 URL pública de la app (para compartir con clientes)",
        value=cfg.get("public_url", "https://exportharet-pedidos.streamlit.app"),
        help="URL de Streamlit Cloud. Se usa en los botones de WhatsApp, Email y QR.",
    )

    st.markdown("---")
    st.markdown("### Tarifas por destino (USD/kg aéreo)")

    dest_rows = [{"Destino": k, "Tarifa USD/kg": v} for k, v in cfg["destinos"].items()]
    dest_df = pd.DataFrame(dest_rows)
    edited_dest = st.data_editor(
        dest_df,
        use_container_width=False,
        hide_index=True,
        disabled=["Destino"],
        column_config={
            "Tarifa USD/kg": st.column_config.NumberColumn("Tarifa USD/kg", min_value=0.0, step=0.05, format="%.2f")
        },
        key="dest_editor",
    )

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
        disabled=["Grupo", "Productos"],
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
        for _, row in edited_dest.iterrows():
            cfg["destinos"][row["Destino"]] = float(row["Tarifa USD/kg"])
        for _, row in edited_grupos.iterrows():
            cfg["grupos"][row["Grupo"]]["cajas_pallet"] = int(row["Cajas/Pallet"])
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
    st.markdown("#### 🖼️ Logo de la empresa")

    _logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
    col_logo, col_upload = st.columns([1, 2])

    with col_logo:
        if os.path.exists(_logo_path):
            st.image(_logo_path, caption="Logo actual", use_container_width=True)
        else:
            st.info("Sin logo configurado")

    with col_upload:
        st.markdown("Sube tu logo en formato **PNG o JPG** (fondo transparente o blanco recomendado):")
        uploaded = st.file_uploader(
            "Seleccionar imagen",
            type=["png", "jpg", "jpeg", "webp"],
            key="logo_uploader",
            label_visibility="collapsed",
        )
        if uploaded:
            img_bytes = uploaded.read()
            # Convertir a PNG si no lo es
            from PIL import Image as PILImage
            img_obj = PILImage.open(io.BytesIO(img_bytes)).convert("RGBA")
            buf = io.BytesIO()
            img_obj.save(buf, format="PNG")
            with open(_logo_path, "wb") as f:
                f.write(buf.getvalue())
            st.success("✅ Logo guardado. Pulsa **🚀 Publicar en la nube** para que aparezca en la app.")
            st.image(_logo_path, caption="Nuevo logo", width=200)

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

                # También subir el logo si existe
                _lp = os.path.join(os.path.dirname(__file__), "logo.png")
                if os.path.exists(_lp):
                    with open(_lp, "rb") as lf:
                        logo_b64 = base64.b64encode(lf.read()).decode()
                    logo_url = "https://api.github.com/repos/expharet/app-de-pedidos/contents/logo.png"
                    r_logo_get = requests.get(logo_url, headers=headers, timeout=10)
                    logo_sha = r_logo_get.json().get("sha", "") if r_logo_get.status_code == 200 else ""
                    logo_payload = {
                        "message": f"Actualizar logo — {date.today().strftime('%d/%m/%Y')}",
                        "content": logo_b64,
                        **({"sha": logo_sha} if logo_sha else {}),
                    }
                    requests.put(logo_url, json=logo_payload, headers=headers, timeout=20)

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
