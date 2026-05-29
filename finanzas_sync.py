"""
Export Haret · Sincronización Pedidos → Finanzas (hub)
======================================================
Módulo drop-in para la app de Pedidos (Streamlit). Empuja cada pedido al sistema
Finanzas, que es la única fuente de verdad del flujo pedido→cobro:

    pedido (Recibido)  →  cliente + cotización
    Confirmado+        →  convierte la cotización en ENVÍO y avanza su estado (FSM)

Diseño:
- Degradación elegante: si Finanzas no responde, NADA se rompe. `sync_pedido`
  devuelve mensajes y el pedido se guarda igual en los JSON de la app.
- Idempotente: guarda en el propio dict del pedido los ids de Finanzas
  (`finanzas_cliente_id`, `finanzas_cot_id`, `finanzas_envio_id`,
  `finanzas_codigo`) para no duplicar en reintentos.
- Configuración por entorno (Streamlit Secrets o variables de entorno):
    HARET_API_URL   (ej. https://tu-tunel.trycloudflare.com ; default localhost:8080)
    HARET_API_KEY   (opcional; si Finanzas la exige, va como X-API-Key)

USO en la app de Pedidos (3 puntos):
    import finanzas_sync
    # 1) tras crear un pedido nuevo (portal y admin), después de save_pedidos(...):
    finanzas_sync.sync_pedido(ped); save_pedidos(todos)   # ped quedó enriquecido
    # 2) tras cambiar el estado de un pedido (botones de estado / selectbox):
    finanzas_sync.sync_pedido(_pp)   # _pp es el pedido modificado; luego save_pedidos
"""
from __future__ import annotations

import os
from typing import Any

import requests

try:  # leer también de Streamlit Secrets si está disponible
    import streamlit as st  # type: ignore
    _SECRETS = dict(st.secrets.get("finanzas", {})) if hasattr(st, "secrets") else {}
except Exception:
    _SECRETS = {}

BASE_URL = (os.environ.get("HARET_API_URL")
            or _SECRETS.get("api_url")
            or "http://localhost:8080").rstrip("/")
API_KEY = (os.environ.get("HARET_API_KEY") or _SECRETS.get("api_key") or "").strip()
TIMEOUT = 8

# Mapa estado de Pedidos → estado objetivo en la FSM del envío de Finanzas
ESTADO_MAP = {
    "Recibido": "COTIZADO",
    "Confirmado": "CONFIRMADO",
    "Preparando": "EN_PRODUCCION",
    "Enviado": "EN_TRANSITO",
    "Entregado": "ENTREGADO",
    "Cancelado": "CANCELADO",
}
# Camino lineal "feliz" de la FSM, para avanzar paso a paso (no se puede saltar)
PATH = ["COTIZADO", "CONFIRMADO", "EN_PRODUCCION", "EMBARCADO",
        "EN_TRANSITO", "ENTREGADO", "PENDIENTE_COBRO", "COBRADO"]
# Estados de Pedidos que justifican crear ya el envío
ESTADOS_CON_ENVIO = {"Confirmado", "Preparando", "Enviado", "Entregado"}


def _headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    return h


def _auth_only() -> dict[str, str]:
    return {"X-API-Key": API_KEY} if API_KEY else {}


def disponible() -> bool:
    try:
        return requests.get(f"{BASE_URL}/api/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False


# --------------------------------------------------------------- clientes
def upsert_cliente(razon_social: str, **campos: Any) -> int | None:
    razon = (razon_social or "").strip()
    if not razon:
        return None
    try:
        r = requests.get(f"{BASE_URL}/api/clientes/buscar",
                         params={"razon_social": razon}, timeout=TIMEOUT)
        if r.status_code == 200:
            return int(r.json()["id"])
        payload = {"razon_social": razon, **{k: v for k, v in campos.items() if v}}
        r = requests.post(f"{BASE_URL}/api/clientes", json=payload,
                         headers=_headers(), timeout=TIMEOUT)
        if r.status_code == 200:
            return int(r.json()["id"])
        if r.status_code == 409:
            r2 = requests.get(f"{BASE_URL}/api/clientes/buscar",
                             params={"razon_social": razon}, timeout=TIMEOUT)
            if r2.status_code == 200:
                return int(r2.json()["id"])
    except requests.RequestException:
        pass
    return None


# ------------------------------------------------------------ cotizaciones
def crear_cotizacion(cliente_id: int, productos: list[dict], moneda: str,
                     numero: str | None, notas: str | None) -> dict | None:
    payload: dict[str, Any] = {"cliente_id": cliente_id, "productos": productos,
                               "moneda": moneda}
    if numero:
        payload["numero"] = numero
    if notas:
        payload["notas"] = notas
    try:
        r = requests.post(f"{BASE_URL}/api/cotizaciones", json=payload,
                         headers=_headers(), timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


def convertir_cotizacion(cot_id: int) -> dict | None:
    """Acepta y convierte la cotización en envío. Devuelve {envio_id, codigo}."""
    try:
        requests.post(f"{BASE_URL}/api/cotizaciones/{cot_id}/estado",
                      json={"estado": "ACEPTADA"}, headers=_headers(), timeout=TIMEOUT)
        r = requests.post(f"{BASE_URL}/api/cotizaciones/{cot_id}/convertir",
                         headers=_auth_only(), timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except requests.RequestException:
        pass
    return None


# ----------------------------------------------------------------- envíos
def _estado_envio(envio_id: int) -> str | None:
    try:
        r = requests.get(f"{BASE_URL}/api/envios", timeout=TIMEOUT)
        if r.status_code == 200:
            for e in r.json():
                if e.get("id") == envio_id:
                    return e.get("estado")
    except requests.RequestException:
        pass
    return None


def transicionar(envio_id: int, nuevo_estado: str, motivo: str = "") -> bool:
    try:
        r = requests.post(f"{BASE_URL}/api/envios/{envio_id}/transicionar",
                         data={"nuevo_estado": nuevo_estado, "motivo": motivo},
                         headers=_auth_only(), timeout=TIMEOUT)
        return r.status_code == 200
    except requests.RequestException:
        return False


def transicionar_hasta(envio_id: int, objetivo: str) -> str:
    """Avanza el envío por la FSM paso a paso hasta `objetivo`. Devuelve mensaje."""
    actual = _estado_envio(envio_id)
    if actual is None:
        return "no se pudo leer el estado del envío"
    if objetivo == "CANCELADO":
        return ("envío cancelado" if transicionar(envio_id, "CANCELADO", "cancelado en Pedidos")
                else "no se pudo cancelar")
    if actual not in PATH or objetivo not in PATH:
        return f"estado fuera del camino lineal ({actual}→{objetivo})"
    i, j = PATH.index(actual), PATH.index(objetivo)
    if j <= i:
        return f"ya estaba en {actual}"
    for paso in PATH[i + 1:j + 1]:
        if not transicionar(envio_id, paso, "sincronizado desde Pedidos"):
            return f"avanzó hasta {paso} y falló ahí"
    return f"envío avanzado {actual} → {objetivo}"


# ---------------------------------------------------- orquestador principal
def sync_pedido(ped: dict) -> tuple[dict, list[str]]:
    """Sincroniza un pedido con Finanzas. Mutar y devolver el mismo dict + mensajes.
    Las cotizaciones especiales (tipo 'cotizacion_especial') se ignoran."""
    msgs: list[str] = []
    if ped.get("tipo") == "cotizacion_especial":
        return ped, ["pedido de cotización especial: no se sincroniza"]

    razon = (ped.get("client_name") or ped.get("client_email") or "").strip()
    cid = ped.get("finanzas_cliente_id") or upsert_cliente(
        razon,
        email=ped.get("client_email"),
        pais=ped.get("pais"),
        telefono=ped.get("telefono"),
        moneda_facturacion="USD",
        notas="Alta desde app Pedidos")
    if not cid:
        return ped, ["⚠️ Finanzas no disponible: pedido NO sincronizado"]
    ped["finanzas_cliente_id"] = cid
    msgs.append(f"cliente id {cid}")

    # cotización (una sola vez)
    if not ped.get("finanzas_cot_id"):
        productos = [{
            "codigo": it.get("codigo", ""),
            "nombre": it.get("producto", ""),
            "cantidad": it.get("cajas", 0),
            "pallets": it.get("pallets", 0),
            "precio_usd": it.get("precio_usd", 0),
            "importe": it.get("total", 0),
        } for it in ped.get("productos", [])]
        cot = crear_cotizacion(
            cid, productos, moneda="USD", numero=ped.get("id"),
            notas=f"Pedido {ped.get('id')} · {ped.get('tipo_precio','')} {ped.get('destino','')}")
        if cot:
            ped["finanzas_cot_id"] = cot["id"]
            msgs.append(f"cotización {cot.get('numero')}")
        else:
            msgs.append("⚠️ no se pudo crear la cotización")
            return ped, msgs

    estado = ped.get("estado", "Recibido")
    objetivo = ESTADO_MAP.get(estado)

    # crear envío cuando el pedido se confirma o avanza
    if not ped.get("finanzas_envio_id") and (
            estado in ESTADOS_CON_ENVIO or estado == "Cancelado"):
        env = convertir_cotizacion(ped["finanzas_cot_id"])
        if env:
            ped["finanzas_envio_id"] = env["envio_id"]
            ped["finanzas_codigo"] = env.get("codigo")
            msgs.append(f"envío {env.get('codigo')} creado")
        else:
            msgs.append("⚠️ no se pudo convertir a envío")
            return ped, msgs

    # avanzar la FSM del envío al estado objetivo
    if ped.get("finanzas_envio_id") and objetivo and estado != "Recibido":
        msgs.append(transicionar_hasta(ped["finanzas_envio_id"], objetivo))

    return ped, msgs
