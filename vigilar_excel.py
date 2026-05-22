"""
vigilar_excel.py — Export Haret
================================
Monitorea Cotizaciones.xlsx y publica cambios automáticamente en la app.

Usa polling (comprueba la fecha de modificación cada 3 s) en lugar de
watchdog, porque Excel en Mac guarda con archivos temporales y los eventos
de fichero no siempre se detectan correctamente.

Uso:
  .venv/bin/python3 vigilar_excel.py
  .venv/bin/python3 vigilar_excel.py --verbose
"""

import os, sys, time, json, io, base64, requests, traceback
from datetime import datetime
from pathlib import Path
from openpyxl import load_workbook

# ── Rutas ─────────────────────────────────────────────────────────────────────
BASE         = Path(__file__).parent
EXCEL_PATH   = BASE / "Documentacion" / "Precios" / "Cotizaciones.xlsx"
DATA_PATH    = BASE / "precios_data.json"
SECRETS_FILE = BASE / ".streamlit" / "secrets.toml"

GITHUB_OWNER = "expharet"
GITHUB_REPO  = "app-de-pedidos"
POLL_SECS    = 3       # comprobar cada 3 segundos
VERBOSE      = "--verbose" in sys.argv or "-v" in sys.argv

# ── Colores terminal ──────────────────────────────────────────────────────────
G = "\033[92m"; Y = "\033[93m"; R = "\033[91m"; B = "\033[1m"; X = "\033[0m"

def log(msg, color=""):
    print(f"{color}[{datetime.now().strftime('%H:%M:%S')}] {msg}{X}", flush=True)

# ── Leer secrets ──────────────────────────────────────────────────────────────
def _secret(key):
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text().splitlines():
            if key in line and "=" in line:
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(key, "")

GITHUB_TOKEN = _secret("GITHUB_TOKEN")

# ── Mapa columnas Excel → código producto ─────────────────────────────────────
COL_MAP = {
     4: "F-PSG10",    5: "F-PN016",    6: "F-PPA01",
     7: "F-PSR02",    8: "F-PSR05",    9: "F-PSM09",
    10: "F-TAS04",   11: "F-GNB010",  12: "F-MPS03",
    13: "F-CCN017",  14: "F-BCC013",  15: "F-AHSS012",
    16: "F-BBB06",   17: "F-ZPT020",  18: "F-TX020",
    19: "F-UVP08",   20: "F-UVP07",
}

# ── Leer Excel y calcular cambios ─────────────────────────────────────────────
def read_excel_and_diff(excel_path: Path, data: dict) -> tuple:
    """Devuelve (data_actualizada, lista_cambios)."""
    wb     = load_workbook(io.BytesIO(excel_path.read_bytes()), data_only=True)
    ws_cfg = wb["CONFIGURACION"]
    ws_pr  = wb["TABLA PRECIOS"]
    new    = json.loads(json.dumps(data))   # deep copy
    cfg    = new["config"]
    ch     = []

    # Parámetros CONFIGURACION
    for row in ws_cfg.iter_rows():
        for cell in row:
            v  = str(cell.value or "")
            c3 = ws_cfg.cell(row=cell.row, column=3).value
            if not isinstance(c3, (int, float)):
                continue
            val = float(c3)

            def _upd(key, label=None):
                label = label or key
                if abs(cfg.get(key, 0) - val) > 1e-4:
                    ch.append(f"{label}: {cfg.get(key)} → {val}")
                    cfg[key] = val

            if "Costo de la caja" in v:           _upd("costo_caja", "Costo caja")
            elif "Merma" in v and "%" in v:        _upd("merma_pct",  "Merma %")
            elif "DUE" in v and "fijo" in v:       _upd("due",        "DUE")
            elif "Peso pallet" in v:               _upd("peso_pallet","Peso pallet")
            elif "Tara de la caja" in v:           _upd("tara_caja",  "Tara caja")
            elif "transporte" in v.lower() and "costo" in v.lower():
                _upd("transporte_interno", "Transporte interno")

            # Tarifas destino
            dest = str(ws_cfg.cell(row=cell.row, column=2).value or "")
            if cell.column == 2 and dest in cfg.get("destinos", {}):
                if abs(cfg["destinos"][dest] - val) > 1e-4:
                    ch.append(f"Tarifa {dest}: {cfg['destinos'][dest]} → {val}")
                    cfg["destinos"][dest] = val

    # Últimos precios del historial (filas 32-83)
    latest = {}
    for col, cod in COL_MAP.items():
        last = None
        for r in range(32, 84):
            v = ws_pr.cell(row=r, column=col).value
            if isinstance(v, (int, float)) and v > 0:
                last = float(v)
        if last:
            latest[cod] = last

    for i, p in enumerate(new["products"]):
        if p["codigo"] in latest:
            np = latest[p["codigo"]]
            if abs(p["precio_compra"] - np) > 0.001:
                ch.append(f"{p['producto']}: ${p['precio_compra']:.2f} → ${np:.2f}")
                new["products"][i]["precio_compra"] = np

    return new, ch


# ── Publicar en GitHub ────────────────────────────────────────────────────────
def publish(data: dict) -> bool:
    if not GITHUB_TOKEN:
        log("Token GitHub no configurado — cambios guardados solo en local.", Y)
        return False
    hdrs = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept":        "application/vnd.github.v3+json",
    }
    url     = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/precios_data.json"
    content = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode()
    ).decode()
    r_get = requests.get(url, headers=hdrs, timeout=15)
    if r_get.status_code != 200:
        log(f"Error obteniendo SHA: {r_get.status_code}", R)
        return False
    r_put = requests.put(url, headers=hdrs, timeout=20, json={
        "message": f"Sync Excel → {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "content": content,
        "sha":     r_get.json()["sha"],
    })
    return r_put.status_code in (200, 201)


# ── Notificación macOS ────────────────────────────────────────────────────────
def notify(title, msg):
    os.system(
        f'osascript -e \'display notification "{msg}" '
        f'with title "{title}" sound name "Glass"\''
    )


# ── Ciclo de polling ──────────────────────────────────────────────────────────
def run():
    print(f"\n{B}{'='*54}")
    print("  Export Haret — Vigilante automático de Excel")
    print(f"{'='*54}{X}")
    print(f"  Excel:   {EXCEL_PATH.name}")
    print(f"  Carpeta: {EXCEL_PATH.parent}")
    print(f"  GitHub:  {'✓ configurado' if GITHUB_TOKEN else '✗ sin token (solo local)'}")
    print(f"  Polling: cada {POLL_SECS} segundos\n")

    if not EXCEL_PATH.exists():
        log(f"ERROR: no se encuentra el Excel en:\n  {EXCEL_PATH}", R)
        sys.exit(1)
    if not DATA_PATH.exists():
        log(f"ERROR: no se encuentra precios_data.json en:\n  {DATA_PATH}", R)
        sys.exit(1)

    last_mtime = EXCEL_PATH.stat().st_mtime
    log(f"Vigilante activo — guarda el Excel para sincronizar. Ctrl+C para salir.", G + B)
    if VERBOSE:
        log(f"mtime inicial: {last_mtime}", "")

    while True:
        time.sleep(POLL_SECS)
        try:
            mtime = EXCEL_PATH.stat().st_mtime
        except FileNotFoundError:
            continue   # Excel temporalmente no accesible (guardando)

        if mtime <= last_mtime:
            continue   # sin cambios

        # El archivo cambió
        last_mtime = mtime
        log(f"Cambio detectado (mtime actualizado) — esperando 3 s a que Excel termine…", Y)
        time.sleep(3)   # dejar que Excel cierre el archivo

        try:
            with open(DATA_PATH) as f:
                data = json.load(f)

            new_data, changes = read_excel_and_diff(EXCEL_PATH, data)

            if not changes:
                log("Sin cambios de datos detectados.", "")
                continue

            log(f"{len(changes)} cambio(s):", G)
            for c in changes:
                print(f"   • {c}")

            # Guardar JSON local
            DATA_PATH.write_text(
                json.dumps(new_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            log("precios_data.json guardado ✓", G)

            # Publicar en GitHub
            log("Publicando en Streamlit Cloud…", Y)
            ok = publish(new_data)
            if ok:
                log(f"¡Publicado! La app se actualiza en ~1 min  ✅", G + B)
                notify("Export Haret",
                       f"{len(changes)} cambio(s) publicados desde Excel")
            else:
                log("Guardado local OK, pero no se pudo publicar en GitHub.", Y)

        except Exception:
            log(f"Error durante la sincronización:", R)
            traceback.print_exc()


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log("Vigilante detenido.", "")
