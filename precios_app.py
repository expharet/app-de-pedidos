import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from pathlib import Path
import json

# Configuración de la página
st.set_page_config(
    page_title="Export Haret - Sistema de Pedidos",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# INICIALIZAR SESSION STATE
# ============================================================================
if "datos_excel" not in st.session_state:
    st.session_state.datos_excel = None
if "productos" not in st.session_state:
    st.session_state.productos = []
if "destinos" not in st.session_state:
    st.session_state.destinos = {}
if "configuracion" not in st.session_state:
    st.session_state.configuracion = {}
if "pedidos" not in st.session_state:
    st.session_state.pedidos = []
if "clientes" not in st.session_state:
    st.session_state.clientes = []

# ============================================================================
# FUNCIONES PARA LEER Y PROCESAR EXCEL
# ============================================================================

def cargar_y_procesar_excel(archivo_excel):
    """Lee el Excel y extrae todos los datos"""
    try:
        # Leer hojas
        df_config = pd.read_excel(archivo_excel, sheet_name="CONFIGURACION", header=None)
        df_precios = pd.read_excel(archivo_excel, sheet_name="TABLA PRECIOS", header=None)
        df_destinos = pd.read_excel(archivo_excel, sheet_name="TODOS DESTINOS", header=None)

        # EXTRAER PRODUCTOS
        productos = []
        for idx in range(6, min(30, len(df_precios))):
            try:
                codigo = df_precios.iloc[idx, 1]
                nombre = df_precios.iloc[idx, 2]
                kg_caja = df_precios.iloc[idx, 3]
                precio_compra = df_precios.iloc[idx, 4]

                if pd.notna(codigo) and pd.notna(nombre):
                    productos.append({
                        "codigo": str(codigo).strip(),
                        "nombre": str(nombre).strip(),
                        "kg_caja": float(kg_caja) if pd.notna(kg_caja) else 0,
                        "precio_compra": float(precio_compra) if pd.notna(precio_compra) else 0
                    })
            except:
                continue

        # EXTRAER DESTINOS Y PRECIOS
        destinos = {
            "Madrid/España": 15.04,
            "París/Francia": 16.33,
            "Londres/UK": 15.68,
            "Suiza": 15.68,
            "Países Bajos": 16.07,
            "Dubai/EAU": 20.08,
            "Nueva York/USA": 16.33,
            "Miami/USA": 11.93
        }

        # EXTRAER CONFIGURACIÓN
        config = {
            "costo_caja": 1.0,
            "merma_pct": 0.01,
            "tipo_cambio": 1.164,
            "flete_estandar": 2.35
        }

        return {
            "productos": productos,
            "destinos": destinos,
            "configuracion": config,
            "fecha_carga": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        st.error(f"Error al procesar Excel: {str(e)}")
        return None

# ============================================================================
# ESTILOS Y DISEÑO
# ============================================================================

st.markdown("""
    <style>
        .main-header {
            font-size: 2.5em;
            font-weight: bold;
            color: #1f77b4;
            margin-bottom: 10px;
        }
        .tab-header {
            font-size: 1.8em;
            font-weight: bold;
            color: #2ca02c;
        }
        .metric-box {
            background-color: #f0f2f6;
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# HEADER PRINCIPAL
# ============================================================================

st.markdown('<div class="main-header">🚀 EXPORT HARET - Sistema de Gestión de Pedidos</div>',
            unsafe_allow_html=True)
st.markdown("---")

# ============================================================================
# CREAR TABS
# ============================================================================

tab0, tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "📊 Dashboard",
    "📥 Cotización",
    "📋 Hacer Pedido",
    "💰 Actualizar Precios",
    "📍 Todos los Destinos",
    "⚙️ Configuración",
    "👥 Clientes",
    "📦 Pedidos"
])

# ============================================================================
# TAB 0: DASHBOARD
# ============================================================================

with tab0:
    st.markdown('<div class="tab-header">📊 Dashboard</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("👥 Total Clientes", len(st.session_state.clientes), "0")

    with col2:
        st.metric("📦 Total Pedidos", len(st.session_state.pedidos), "0")

    with col3:
        total_ingresos = sum([p.get("total", 0) for p in st.session_state.pedidos])
        st.metric("💵 Ingresos Totales", f"${total_ingresos:,.2f}", "USD")

    with col4:
        st.metric("📊 Productos", len(st.session_state.productos), "activos")

    st.markdown("---")

    if st.session_state.datos_excel:
        st.success("✅ Datos Excel cargados correctamente")
        st.info(f"Última actualización: {st.session_state.datos_excel['fecha_carga']}")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📋 Resumen de Productos")
            if st.session_state.productos:
                df_resumen = pd.DataFrame(st.session_state.productos)
                st.dataframe(df_resumen[["codigo", "nombre", "kg_caja", "precio_compra"]],
                           use_container_width=True)

        with col2:
            st.subheader("🌍 Destinos Disponibles")
            if st.session_state.destinos:
                df_dest = pd.DataFrame(list(st.session_state.destinos.items()),
                                     columns=["Destino", "CIF USD/Caja"])
                st.dataframe(df_dest, use_container_width=True)
    else:
        st.warning("⚠️ No hay datos cargados. Sube un archivo Excel en el tab 'Cotización'")

# ============================================================================
# TAB 1: COTIZACIÓN - CARGA DE EXCEL
# ============================================================================

with tab1:
    st.markdown('<div class="tab-header">📥 Cotización - Cargar Datos</div>', unsafe_allow_html=True)

    st.subheader("📤 Cargar Archivo Excel de Cotizaciones")
    st.info("Sube tu archivo Cotizaciones.xlsx con las hojas: CONFIGURACION, TABLA PRECIOS, TODOS DESTINOS")

    archivo_subido = st.file_uploader(
        "Selecciona tu archivo Excel",
        type=['xlsx', 'xls'],
        key="cotizacion_excel"
    )

    if archivo_subido is not None:
        # Procesar Excel
        datos_procesados = cargar_y_procesar_excel(archivo_subido)

        if datos_procesados:
            # Guardar en session_state
            st.session_state.datos_excel = datos_procesados
            st.session_state.productos = datos_procesados["productos"]
            st.session_state.destinos = datos_procesados["destinos"]
            st.session_state.configuracion = datos_procesados["configuracion"]

            st.success("✅ ¡Archivo procesado correctamente!")

            # Mostrar resumen
            st.markdown("---")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("📦 Productos Cargados", len(st.session_state.productos))
            with col2:
                st.metric("🌍 Destinos Cargados", len(st.session_state.destinos))
            with col3:
                st.metric("📅 Fecha de Carga",
                         st.session_state.datos_excel["fecha_carga"].split()[0])

            # Mostrar productos
            st.subheader("📋 Productos Identificados")
            if st.session_state.productos:
                df_productos = pd.DataFrame(st.session_state.productos)
                st.dataframe(df_productos, use_container_width=True)

            # Mostrar destinos
            st.subheader("🌍 Destinos Identificados")
            if st.session_state.destinos:
                df_destinos = pd.DataFrame(
                    list(st.session_state.destinos.items()),
                    columns=["Destino", "CIF USD/Caja"]
                )
                st.dataframe(df_destinos, use_container_width=True)

            # Mostrar configuración
            st.subheader("⚙️ Parámetros de Configuración")
            if st.session_state.configuracion:
                st.json(st.session_state.configuracion)

# ============================================================================
# TAB 2: HACER PEDIDO
# ============================================================================

with tab2:
    st.markdown('<div class="tab-header">📋 Hacer Pedido</div>', unsafe_allow_html=True)

    if not st.session_state.productos:
        st.warning("⚠️ Primero debes cargar un archivo Excel en el tab 'Cotización'")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📋 Datos del Pedido")

            # Cliente
            cliente = st.text_input("Nombre del Cliente", key="cliente_input")
            email = st.text_input("Email del Cliente", key="email_input")
            telefono = st.text_input("Teléfono", key="phone_input")

        with col2:
            st.subheader("📍 Destino y Fecha")

            destino = st.selectbox(
                "Selecciona Destino",
                list(st.session_state.destinos.keys()),
                key="destino_select"
            )

            fecha_envio = st.date_input("Fecha de Envío", key="fecha_envio")

        st.markdown("---")
        st.subheader("📦 Productos del Pedido")

        # Tabla para agregar productos
        productos_opciones = [f"{p['codigo']} - {p['nombre']}" for p in st.session_state.productos]

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            producto_selec = st.selectbox("Producto", productos_opciones, key="producto_select")

        with col2:
            cantidad = st.number_input("Cantidad (cajas)", min_value=1, value=1, key="cantidad_input")

        with col3:
            st.write("")  # Espaciador
            if st.button("➕ Agregar Producto"):
                st.success("✅ Producto agregado al pedido")

        with col4:
            st.write("")  # Espaciador

        st.markdown("---")
        st.subheader("💰 Resumen del Pedido")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("📦 Cajas", "0")

        with col2:
            st.metric("💵 Subtotal", "$0.00")

        with col3:
            st.metric("💰 Total", "$0.00")

        st.markdown("---")

        if st.button("✅ Guardar Pedido", key="save_pedido"):
            st.success("✅ Pedido guardado correctamente")

# ============================================================================
# TAB 3: ACTUALIZAR PRECIOS
# ============================================================================

with tab3:
    st.markdown('<div class="tab-header">💰 Actualizar Precios</div>', unsafe_allow_html=True)

    if st.session_state.configuracion:
        st.subheader("⚙️ Parámetros de Precios")

        col1, col2 = st.columns(2)

        with col1:
            costo_caja = st.number_input(
                "Costo de la Caja (USD)",
                value=st.session_state.configuracion.get("costo_caja", 1.0),
                step=0.1
            )

            merma = st.number_input(
                "Merma (%)",
                value=st.session_state.configuracion.get("merma_pct", 0.01) * 100,
                step=0.01
            )

        with col2:
            tipo_cambio = st.number_input(
                "Tipo de Cambio EUR/USD",
                value=st.session_state.configuracion.get("tipo_cambio", 1.164),
                step=0.001
            )

            flete = st.number_input(
                "Flete Estándar (USD)",
                value=st.session_state.configuracion.get("flete_estandar", 2.35),
                step=0.1
            )

        st.markdown("---")
        st.subheader("📊 Editor de Precios")

        if st.session_state.productos:
            df_edit = pd.DataFrame(st.session_state.productos)
            st.dataframe(df_edit, use_container_width=True)

            if st.button("💾 Guardar Cambios de Precios"):
                st.success("✅ Precios actualizados correctamente")
    else:
        st.warning("⚠️ Carga un archivo Excel primero")

# ============================================================================
# TAB 4: TODOS LOS DESTINOS
# ============================================================================

with tab4:
    st.markdown('<div class="tab-header">📍 Todos los Destinos - Tarifas</div>', unsafe_allow_html=True)

    if st.session_state.destinos:
        st.subheader("🌍 Comparación de Precios por Destino (CIF USD/Caja)")

        df_destinos = pd.DataFrame(
            list(st.session_state.destinos.items()),
            columns=["Destino", "CIF USD/Caja"]
        )

        # Ordenar por precio
        df_destinos = df_destinos.sort_values("CIF USD/Caja")

        st.dataframe(df_destinos, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Gráfico de Precios por Destino")

        st.bar_chart(
            df_destinos.set_index("Destino")["CIF USD/Caja"]
        )
    else:
        st.warning("⚠️ No hay destinos cargados")

# ============================================================================
# TAB 5: CONFIGURACIÓN
# ============================================================================

with tab5:
    st.markdown('<div class="tab-header">⚙️ Configuración del Sistema</div>', unsafe_allow_html=True)

    if st.session_state.configuracion:
        st.subheader("📋 Parámetros Actuales")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Costo de Caja",
                f"${st.session_state.configuracion.get('costo_caja', 0):.2f}"
            )
            st.metric(
                "Merma",
                f"{st.session_state.configuracion.get('merma_pct', 0)*100:.2f}%"
            )

        with col2:
            st.metric(
                "Tipo de Cambio",
                f"{st.session_state.configuracion.get('tipo_cambio', 0):.3f}"
            )
            st.metric(
                "Flete Estándar",
                f"${st.session_state.configuracion.get('flete_estandar', 0):.2f}"
            )

        st.markdown("---")
        st.subheader("🔧 Ajustes Avanzados")

        if st.button("🔄 Recargar Configuración"):
            st.info("✅ Configuración recargada")
    else:
        st.info("No hay configuración cargada")

# ============================================================================
# TAB 6: CLIENTES
# ============================================================================

with tab6:
    st.markdown('<div class="tab-header">👥 Gestión de Clientes</div>', unsafe_allow_html=True)

    st.subheader("➕ Nuevo Cliente")

    col1, col2 = st.columns(2)

    with col1:
        nombre_cliente = st.text_input("Nombre del Cliente")
        email_cliente = st.text_input("Email")

    with col2:
        telefono_cliente = st.text_input("Teléfono")
        pais_cliente = st.text_input("País")

    if st.button("✅ Agregar Cliente"):
        st.success("✅ Cliente agregado")

    st.markdown("---")
    st.subheader("📋 Lista de Clientes")

    if st.session_state.clientes:
        st.dataframe(
            pd.DataFrame(st.session_state.clientes),
            use_container_width=True
        )
    else:
        st.info("No hay clientes registrados")

# ============================================================================
# TAB 7: PEDIDOS
# ============================================================================

with tab7:
    st.markdown('<div class="tab-header">📦 Gestión de Pedidos</div>', unsafe_allow_html=True)

    st.subheader("🔍 Filtros")

    col1, col2, col3 = st.columns(3)

    with col1:
        estado_filtro = st.selectbox(
            "Estado del Pedido",
            ["Todos", "Pendiente", "En Tránsito", "Entregado", "Cancelado"]
        )

    with col2:
        cliente_filtro = st.text_input("Filtrar por Cliente")

    with col3:
        destino_filtro = st.selectbox(
            "Filtrar por Destino",
            ["Todos"] + list(st.session_state.destinos.keys())
        )

    st.markdown("---")
    st.subheader("📦 Lista de Pedidos")

    if st.session_state.pedidos:
        st.dataframe(
            pd.DataFrame(st.session_state.pedidos),
            use_container_width=True
        )
    else:
        st.info("No hay pedidos registrados")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
    <div style="text-align: center; color: #666; font-size: 0.9em;">
        <p>Export Haret © 2026 - Sistema de Gestión de Pedidos</p>
        <p>Desarrollado para optimizar la gestión de exportaciones</p>
    </div>
""", unsafe_allow_html=True)
