"""
Suite de regresión del flujo de pedido (Export Haret · portal de Pedidos).

Cubre las funciones puras de precio/volumen/conversión y la conversión
cantidad↔(cajas, pallets) — el corazón del pedido. Si un cambio futuro
reintroduce los bugs de desfase/precio, estos tests fallan.

Ejecutar:  .venv_run/bin/python -m pytest tests/ -q
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import precios_app as P  # noqa: E402


# ── Datos sintéticos (NO dependen del catálogo real) ────────────────────────
# precios_plt = tabla de volumen CIF (índice = pallets-1), incluye flete ref Madrid.
DATA = {
    "products": [
        {
            "codigo": "F-001",
            "grupo": "A",
            "precio_fob_final": 10.0,                 # FOB fijo (no varía por volumen)
            "precios_plt": [20.0, 20.0, 18.0, 18.0, 18.0, 16.0],
        },
        {
            "codigo": "F-NOPLT",                      # sin tabla → fallback compra+margen
            "grupo": "A",
            "precio_compra": 5.0,
            "margen_pct": 0.20,
        },
    ],
    "config": {
        "flete_ref": 2.35,
        "destinos": {"UK": 3.35, "Spain": 2.35, "DUBAI": {"factor": 4.10}},
        "grupos": {"A": {"cajas_pallet": 160, "kg_caja": 2.0}},
    },
}


# ── get_descuento_volumen: tramos correctos en cada frontera ────────────────
def test_descuento_tramos_fronteras():
    assert P.get_descuento_volumen(1) == 0.00
    assert P.get_descuento_volumen(2) == 0.00
    assert P.get_descuento_volumen(3) == 0.10
    assert P.get_descuento_volumen(5) == 0.10
    assert P.get_descuento_volumen(6) == 0.12
    assert P.get_descuento_volumen(9) == 0.12
    assert P.get_descuento_volumen(10) == 0.14
    assert P.get_descuento_volumen(19) == 0.14
    assert P.get_descuento_volumen(20) == 0.15
    assert P.get_descuento_volumen(1000) == 0.15


def test_descuento_valores_invalidos_caen_en_minimo():
    assert P.get_descuento_volumen(0) == 0.00     # se trata como 1 pallet
    assert P.get_descuento_volumen(-5) == 0.00
    assert P.get_descuento_volumen("x") == 0.00


def test_tramos_volumen_sin_huecos_ni_solapes():
    tr = sorted(P.TRAMOS_VOLUMEN, key=lambda t: t["min"])
    assert tr[0]["min"] == 1
    for a, b in zip(tr, tr[1:]):
        assert b["min"] == a["max"] + 1, "los tramos deben encadenar sin hueco/solape"


# ── cajas_y_pallets: la fuente única de la conversión cantidad↔cajas/pallets ─
def test_cajas_pallets_unidad_pallets():
    assert P.cajas_y_pallets(3, "Pallets", 160) == (480, 3.0)
    assert P.cajas_y_pallets(1, "Pallets", 120) == (120, 1.0)


def test_cajas_pallets_unidad_cajas():
    assert P.cajas_y_pallets(480, "Cajas", 160) == (480, 3.0)
    assert P.cajas_y_pallets(80, "Cajas", 160) == (80, 0.5)   # pallet parcial


def test_cajas_pallets_cero_y_negativo():
    assert P.cajas_y_pallets(0, "Pallets", 160) == (0, 0.0)
    assert P.cajas_y_pallets(-2, "Cajas", 160) == (0, 0.0)


def test_cajas_pallets_cxp_invalido_no_revienta():
    # cxp 0/None → se trata como 1 (evita división por cero)
    assert P.cajas_y_pallets(3, "Cajas", 0) == (3, 3.0)
    assert P.cajas_y_pallets(3, "Cajas", None) == (3, 3.0)


def test_cajas_pallets_ida_y_vuelta_consistente():
    # 3 pallets y 480 cajas deben dar EXACTAMENTE lo mismo (raíz del bug de desfase)
    assert P.cajas_y_pallets(3, "Pallets", 160) == P.cajas_y_pallets(480, "Cajas", 160)


# ── Precio FOB: FIJO, no baja por volumen ───────────────────────────────────
def test_fob_precio_fijo_por_volumen():
    p1 = P.get_precio_con_volumen("F-001", "", "FOB", DATA, 1)
    p10 = P.get_precio_con_volumen("F-001", "", "FOB", DATA, 10)
    assert p1 == 10.0
    assert p1 == p10, "el precio FOB NO debe variar por volumen"


def test_fob_fallback_compra_mas_margen():
    # sin precio_fob_final → precio_compra * (1+margen)
    assert P.get_precio_por_pallets("F-NOPLT", 1, DATA, tipo_precio="FOB") == 6.0


def test_get_fob_price_helper():
    assert P.get_fob_price("F-001", DATA) == 10.0
    assert P.get_fob_price("NO-EXISTE", DATA) == 0.0


# ── Precio CIF: baja por volumen según precios_plt ──────────────────────────
def test_cif_baja_por_volumen():
    # base Madrid (precios_plt) por tramo de pallets, destino Spain (flete ref → sin ajuste)
    assert P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, 1) == 20.0
    assert P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, 3) == 18.0
    assert P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, 6) == 16.0


def test_cif_volumen_monotono_no_creciente():
    precios = [P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, n) for n in range(1, 11)]
    assert precios == sorted(precios, reverse=True), "a más pallets, precio <= "


def test_cif_indice_se_capa_al_maximo_de_la_tabla():
    # pallets mayores que la tabla → usa el último (más barato), no peta
    assert P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, 99) == 16.0


# ── CIF por destino: ajusta el flete real (base - flete_ref + flete_destino) ─
def test_cif_ajuste_flete_por_destino():
    base = P.get_precio_por_pallets("F-001", 3, DATA)  # 18.0 (incluye flete ref 2.35)
    # UK flete 3.35 → 18 - 2.35 + 3.35 = 19.0
    assert P.get_precio_cif_por_pallets("F-001", 3, "UK", DATA) == 19.0
    # Spain flete 2.35 (== ref) → sin cambio
    assert P.get_precio_cif_por_pallets("F-001", 3, "Spain", DATA) == base
    # destino con dict {factor} → 18 - 2.35 + 4.10 = 19.75
    assert P.get_precio_cif_por_pallets("F-001", 3, "DUBAI", DATA) == 19.75


def test_cif_destino_desconocido_usa_flete_ref():
    base = P.get_precio_por_pallets("F-001", 3, DATA)
    assert P.get_precio_cif_por_pallets("F-001", 3, "MARTE", DATA) == base


def test_get_precio_con_volumen_enruta_fob_vs_cif():
    cif = P.get_precio_con_volumen("F-001", "UK", "CIF", DATA, 3)
    fob = P.get_precio_con_volumen("F-001", "UK", "FOB", DATA, 3)
    assert cif == 19.0
    assert fob == 10.0


# ── Total de la línea de pedido: cajas * precio, redondeado ─────────────────
def test_total_linea_redondeo():
    precio = P.get_precio_con_volumen("F-001", "Spain", "CIF", DATA, 3)  # 18.0
    cajas, _ = P.cajas_y_pallets(3, "Pallets", 160)                      # 480
    assert round(cajas * precio, 2) == 8640.00


# ── _esc: escapa HTML (anti-XSS en email/markdown) ──────────────────────────
def test_esc_escapa_html():
    assert P._esc("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
    assert P._esc('a"&<>b') == "a&quot;&amp;&lt;&gt;b"
    assert P._esc(None) == ""
    assert P._esc(123) == "123"


# ── _dedupe_portal_clients: fusiona por email normalizado (anti-duplicados) ──
def test_dedupe_fusiona_por_email_normalizado():
    pc = {
        "  Cliente@X.com ": {"nombre": "Frutas X", "pedidos": ["p1"]},
        "cliente@x.com": {"empresa": "X SL", "pedidos": ["p2"]},
    }
    out = P._dedupe_portal_clients(pc)
    assert list(out.keys()) == ["cliente@x.com"]
    rec = out["cliente@x.com"]
    assert rec["nombre"] == "Frutas X"          # completa campos faltantes
    assert rec["empresa"] == "X SL"
    assert set(rec["pedidos"]) == {"p1", "p2"}   # une las listas de pedidos


def test_dedupe_descarta_claves_vacias_o_no_dict():
    pc = {"": {"nombre": "x"}, "ok@x.com": {"nombre": "y"}, "bad@x.com": "no-dict"}
    out = P._dedupe_portal_clients(pc)
    assert list(out.keys()) == ["ok@x.com"]


# ── Símbolos de moneda (conversión de divisa en el portal) ──────────────────
def test_simbolos_moneda_principales():
    assert P.MONEDA_SIMBOLO["USD"] == "$"
    assert P.MONEDA_SIMBOLO["EUR"] == "€"
    assert P.MONEDA_SIMBOLO["GBP"] == "£"
