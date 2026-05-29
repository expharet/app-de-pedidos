"""
Export Haret · Cola durable de pedidos (outbox a GitHub Gist)
=============================================================
La app de Pedidos vive en Streamlit Cloud (almacenamiento efímero) y tu Finanzas
vive en tu Mac (que puede estar apagado). Para que ningún pedido se pierda y el
Mac pueda ponerse al día al encender, cada cambio en los pedidos se vuelca a un
**Gist de GitHub**, que actúa como cola durable y gratuita que ambos lados leen.

Configuración (Streamlit Cloud → Settings → Secrets):
    [github]
    token   = "ghp_xxx"        # PAT con permiso 'gist'
    gist_id = "abcdef123..."   # id del gist (secreto) creado una vez

Si no está configurado, `publish()` es un no-op: la app funciona igual.
"""
from __future__ import annotations

import json
import os

import requests

try:
    import streamlit as st  # type: ignore
    _SEC = dict(st.secrets.get("github", {})) if hasattr(st, "secrets") else {}
except Exception:
    _SEC = {}

TOKEN = (os.environ.get("HARET_GH_TOKEN") or _SEC.get("token") or "").strip()
GIST_ID = (os.environ.get("HARET_GIST_ID") or _SEC.get("gist_id") or "").strip()
FILENAME = "pedidos_outbox.json"


def configurado() -> bool:
    return bool(TOKEN and GIST_ID)


def publish(pedidos: list) -> bool:
    """Vuelca la lista completa de pedidos al Gist. No rompe nunca la app."""
    if not configurado():
        return False
    try:
        r = requests.patch(
            f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"token {TOKEN}",
                     "Accept": "application/vnd.github+json"},
            json={"files": {FILENAME: {
                "content": json.dumps(pedidos, ensure_ascii=False, indent=0)}}},
            timeout=10)
        return r.status_code in (200, 201)
    except requests.RequestException:
        return False
