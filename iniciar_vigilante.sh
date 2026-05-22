#!/bin/bash
# iniciar_vigilante.sh
# Doble clic para arrancar el vigilante automático de Excel
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "======================================"
echo "  Export Haret — Vigilante de Excel"
echo "======================================"
echo ""
echo "El vigilante está activo."
echo "Cada vez que guardes Cotizaciones.xlsx"
echo "los precios se actualizarán en la app."
echo ""
echo "Cierra esta ventana para detenerlo."
echo ""

.venv/bin/python3 vigilar_excel.py --verbose
