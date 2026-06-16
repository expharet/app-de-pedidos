"""
Export Haret · Cola durable de pedidos (outbox a GitHub Gist)
=============================================================
La app de Pedidos vive en Streamlit Cloud (almacenamiento efímero) y tu Finanzas
vive en tu Mac (que puede estar apagado). Para que ningún pedido se pierda y el
Mac pueda ponerse al día al encender, cada cambio en los pedidos se vuelca a un
**Gist de GitHub**, que actúa como cola durable y gratuita que ambos lados leen.

Configuración tolerante (Streamlit Cloud → Settings → Secrets). Acepta cualquiera
de estos formatos:

    [github]
    token   = "ghp_xxx"
    gist_id = "abc123"

    # o sueltos en la raíz (también vale):
    GITHUB_TOKEN = "ghp_xxx"
    gist_id      = "abc123"

Si no está configurado, `publish()` es un no-op: la app funciona igual.
"""
from __future__ import annotations

import json
import os

import requests


def _buscar(*nombres: str) -> str:
    """Busca un valor en variables de entorno y en st.secrets (sección [github]
    y raíz), probando varias variantes de nombre. Devuelve '' si no lo encuentra."""
    # 1) variables de entorno
    for n in nombres:
        v = os.environ.get(n)
        if v:
            return str(v).strip()
    # 2) Streamlit secrets
    try:
        import streamlit as st  # type: ignore
        sec = st.secrets
        # sección [github]
        try:
            gh = dict(sec.get("github", {}))
        except Exception:
            gh = {}
        # raíz + sección, probando minúsculas/mayúsculas
        for n in nombres:
            for variante in (n, n.lower(), n.upper()):
                if variante in gh and gh[variante]:
                    return str(gh[variante]).strip()
                try:
                    if variante in sec and sec[variante]:
                        return str(sec[variante]).strip()
                except Exception:
                    pass
    except Exception:
        pass
    return ""


def _token() -> str:
    return _buscar("HARET_GH_TOKEN", "GITHUB_TOKEN", "github_token", "token")


def _gist_id() -> str:
    return _buscar("HARET_GIST_ID", "gist_id", "GIST_ID", "gist")


def configurado() -> bool:
    return bool(_token() and _gist_id())


def fetch() -> list | None:
    """Lee la lista de pedidos desde el Gist (cola durable). Sirve para recuperar
    'Mis Pedidos' tras un reinicio de Streamlit Cloud (disco efímero).
    Devuelve la lista, [] si el gist está vacío, o None si no hay config/falla."""
    token, gist_id = _token(), _gist_id()
    if not gist_id:
        return None
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}",
                         headers=headers, timeout=10)
        if r.status_code == 200:
            content = (r.json().get("files", {})
                       .get("pedidos_outbox.json", {}).get("content"))
            return json.loads(content) if content else []
    except (requests.RequestException, ValueError):
        pass
    return None


def _patch_file(filename: str, payload) -> bool:
    """Escribe (PATCH) un archivo dentro del Gist. No rompe nunca la app."""
    token, gist_id = _token(), _gist_id()
    if not (token and gist_id):
        return False
    try:
        r = requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"token {token}",
                     "Accept": "application/vnd.github+json"},
            json={"files": {filename: {
                "content": json.dumps(payload, ensure_ascii=False, indent=0)}}},
            timeout=10)
        return r.status_code in (200, 201)
    except requests.RequestException:
        return False


def publish(pedidos: list) -> bool:
    """Vuelca la lista completa de pedidos al Gist."""
    return _patch_file("pedidos_outbox.json", pedidos)


def publish_clients(clients: dict) -> bool:
    """Vuelca el padrón de clientes del portal al Gist (para que los clientes
    pre-registrados por el admin sobrevivan a los reinicios de Streamlit Cloud)."""
    return _patch_file("portal_clientes.json", clients)


def fetch_clients() -> dict | None:
    """Lee el padrón de clientes del portal desde el Gist (None si no hay/ falla)."""
    gist_id = _gist_id()
    if not gist_id:
        return None
    token = _token()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}",
                         headers=headers, timeout=10)
        if r.status_code == 200:
            content = (r.json().get("files", {})
                       .get("portal_clientes.json", {}).get("content"))
            return json.loads(content) if content else {}
    except (requests.RequestException, ValueError):
        pass
    return None


def publish_carts(carts: dict) -> bool:
    """Vuelca los carritos pendientes (por email) al Gist, para que el cliente
    pueda retomar su pedido sin terminar aunque Streamlit Cloud reinicie."""
    return _patch_file("portal_carritos.json", carts)


def fetch_carts() -> dict | None:
    """Lee los carritos pendientes del Gist (None si no hay/ falla)."""
    gist_id = _gist_id()
    if not gist_id:
        return None
    token = _token()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}",
                         headers=headers, timeout=10)
        if r.status_code == 200:
            content = (r.json().get("files", {})
                       .get("portal_carritos.json", {}).get("content"))
            return json.loads(content) if content else {}
    except (requests.RequestException, ValueError):
        pass
    return None


def publish_catalog(data: dict) -> bool:
    """Vuelca el catálogo (productos, precios, destinos, MÁRGENES, grupos…) al Gist
    para que los cambios del admin sobrevivan a reinicios de Streamlit Cloud y el
    cliente vea siempre los precios/márgenes actuales."""
    return _patch_file("precios_data.json", data)


def fetch_catalog() -> dict | None:
    """Lee el catálogo desde el Gist (None si no hay/ falla)."""
    gist_id = _gist_id()
    if not gist_id:
        return None
    token = _token()
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        r = requests.get(f"https://api.github.com/gists/{gist_id}",
                         headers=headers, timeout=10)
        if r.status_code == 200:
            content = (r.json().get("files", {})
                       .get("precios_data.json", {}).get("content"))
            return json.loads(content) if content else None
    except (requests.RequestException, ValueError):
        pass
    return None
