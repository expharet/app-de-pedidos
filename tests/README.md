# Tests — flujo de pedido (portal Export Haret)

Suite de regresión de las funciones puras que sostienen el pedido: precio por
volumen (FOB fijo / CIF por tramos), ajuste de flete por destino, conversión
cantidad↔(cajas, pallets), escapado HTML (anti-XSS) y dedupe de clientes.

## Ejecutar

```bash
.venv_run/bin/python -m pytest tests/ -q
```

(Si falta pytest: `.venv_run/bin/pip install pytest`.)

## Qué cubre

- `get_descuento_volumen` — tramos en cada frontera (1/2/3/5/6/9/10/19/20+).
- `cajas_y_pallets` — fuente única de la conversión; mismo resultado en pre-pass,
  bucle y resumen (raíz del bug de desfase "pones 3, cuenta 2").
- `get_precio_por_pallets` / `get_precio_cif_por_pallets` / `get_precio_con_volumen`
  — FOB fijo por volumen, CIF baja por tramos, ajuste de flete por destino.
- `_esc` — escapado HTML.
- `_dedupe_portal_clients` — fusión por email normalizado.

Los datos de prueba son **sintéticos** (no dependen del catálogo real), así que
los tests son deterministas y no tocan red ni ficheros.
