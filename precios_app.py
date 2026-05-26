import streamlit as st
import pandas as pd
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
if "destinos_monedas" not in st.session_state:
    st.session_state.destinos_monedas = {
        "Madrid/España": {"moneda": "EUR", "cif": 15.04},
        "París/Francia": {"moneda": "EUR", "cif": 16.33},
        "Londres/UK": {"moneda": "GBP", "cif": 15.68},
        "Suiza": {"moneda": "CHF", "cif": 15.68},
        "Países Bajos": {"moneda": "EUR", "cif": 16.07},
        "Dubai/EAU": {"moneda": "AED", "cif": 20.08},
        "Nueva York/USA": {"moneda": "USD", "cif": 16.33},
        "Miami/USA": {"moneda": "USD", "cif": 11.93}
    }
if "configuracion" not in st.session_state:
    st.session_state.configuracion = {
        "costo_caja": 1.0,
        "merma_pct": 0.01,
        "tipo_cambio_eur": 1.164,
        "tipo_cambio_gbp": 1.27,
        "tipo_cambio_chf": 1.1,
        "tipo_cambio_aed": 3.67,
        "flete_estandar": 2.35
    }
if "pedidos" not in st.session_state:
    st.session_state.pedidos = []
if "clientes" not in st.session_state:
    st.session_state.clientes = []
if "cambios_pendientes" not in st.session_state:
    st.session_state.cambios_pendientes = False

# ============================================================================
# FUNCIONES PARA LEER Y PROCESAR EXCEL
# ============================================================================

def cargar_y_procesar_excel(archivo_excel):
    """Lee el Excel y extrae todos los datos"""
    try:
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
                fob_base = df_precios.iloc[idx, 6]
                margen = df_precios.iloc[idx, 9]

                if pd.notna(codigo) and pd.notna(nombre):
                    productos.append({
                        "codigo": str(codigo).strip(),
                        "nombre": str(nombre).strip(),
                        "kg_caja": float(kg_caja) if pd.notna(kg_caja) else 0,
                        "precio_compra": float(precio_compra) if pd.notna(precio_compra) else 0,
                        "fob_base": float(fob_base) if pd.notna(fob_base) else 0,
                        "margen_pct": float(margen) if pd.notna(margen) else 0
                    })
            except:
                continue

        return {
            "productos": productos,
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
        .success-box {
            background-color: #d4edda;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #28a745;
        }
    </style>
""", unsafe_allow_html=True)

# ============================================================================
# HEADER PRINCIPAL
# ============================================================================

st.markdown('<div class="main-header">🚀 EXPORT HARET - Sistema de Gestión de Pedidos</div>',
            unsafe_allow_html=True)

# Mostrar si hay cambios pendientes
if st.session_state.cambios_pendientes:
    st.warning("⚠️ Hay cambios sin publicar. Haz clic en 'Publicar Cambios' para aplicarlos")

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
                st.dataframe(df_resumen[["codigo", "nombre", "kg_caja", "fob_base"]],
                           use_container_width=True)

        with col2:
            st.subheader("🌍 Destinos Disponibles")
            if st.session_state.destinos_monedas:
                df_dest = pd.DataFrame([
                    {"Destino": k, "Moneda": v["moneda"], "CIF USD": v["cif"]}
                    for k, v in st.session_state.destinos_monedas.items()
                ])
                st.dataframe(df_dest, use_container_width=True)
    else:
        st.warning("⚠️ No hay datos cargados. Sube un archivo Excel en el tab 'Cotización'")

# ============================================================================
# TAB 1: COTIZACIÓN - EDITABLE
# ============================================================================

with tab1:
    st.markdown('<div class="tab-header">📥 Cotización - Gestión de Datos</div>', unsafe_allow_html=True)

    # Sección de carga de Excel
    st.subheader("📤 Cargar Archivo Excel")
    st.info("Sube tu archivo Cotizaciones.xlsx con las hojas: CONFIGURACION, TABLA PRECIOS, TODOS DESTINOS")

    archivo_subido = st.file_uploader(
        "Selecciona tu archivo Excel",
        type=['xlsx', 'xls'],
        key="cotizacion_excel"
    )

    if archivo_subido is not None:
        datos_procesados = cargar_y_procesar_excel(archivo_subido)

        if datos_procesados:
            st.session_state.datos_excel = datos_procesados
            st.session_state.productos = datos_procesados["productos"]
            st.success("✅ Archivo procesado correctamente!")
            st.balloons()

    st.markdown("---")

    # TABLA EDITABLE DE PRODUCTOS
    st.subheader("📋 Productos Identificados - EDITABLE")

    if st.session_state.productos:
        df_productos_edit = pd.DataFrame(st.session_state.productos)

        # Data editor para productos
        df_productos_editado = st.data_editor(
            df_productos_edit,
            use_container_width=True,
            key="productos_editor",
            num_rows="dynamic"
        )

        # Detectar cambios
        if not df_productos_editado.equals(df_productos_edit):
            st.session_state.cambios_pendientes = True

    st.markdown("---")

    # TABLA EDITABLE DE DESTINOS
    st.subheader("🌍 Destinos Identificados - EDITABLE")

    # Crear DataFrame de destinos con monedas
    df_destinos_edit = pd.DataFrame([
        {
            "Destino": k,
            "Moneda": v["moneda"],
            "CIF USD/Caja": v["cif"]
        }
        for k, v in st.session_state.destinos_monedas.items()
    ])

    # Data editor para destinos
    df_destinos_editado = st.data_editor(
        df_destinos_edit,
        use_container_width=True,
        key="destinos_editor",
        num_rows="dynamic"
    )

    # Detectar cambios
    if not df_destinos_editado.equals(df_destinos_edit):
        st.session_state.cambios_pendientes = True

    st.markdown("---")

    # BOTÓN PUBLICAR CAMBIOS
    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        if st.button("🚀 PUBLICAR CAMBIOS", key="publish_btn", use_container_width=True):
            # Actualizar productos
            st.session_state.productos = df_productos_editado.to_dict('records')

            # Actualizar destinos y monedas
            nuevos_destinos = {}
            for idx, row in df_destinos_editado.iterrows():
                destino = row["Destino"]
                nuevos_destinos[destino] = {
                    "moneda": row["Moneda"],
                    "cif": row["CIF USD/Caja"]
                }
            st.session_state.destinos_monedas = nuevos_destinos

            st.session_state.cambios_pendientes = False

            st.markdown("""
                <div class="success-box">
                    <strong>✅ ¡Cambios Publicados!</strong><br>
                    Los datos han sido actualizados en toda la aplicación.
                </div>
            """, unsafe_allow_html=True)

            st.balloons()

    with col2:
        st.write("")  # Espaciador

    with col3:
        if st.button("❌ Descartar", key="discard_btn", use_container_width=True):
            st.session_state.cambios_pendientes = False
            st.rerun()

# ============================================================================
# TAB 2: HACER PEDIDO - INTELIGENTE
# ============================================================================

with tab2:
    st.markdown('<div class="tab-header">📋 Hacer Pedido</div>', unsafe_allow_html=True)

    if not st.session_state.productos:
        st.warning("⚠️ Primero debes cargar un archivo Excel en el tab 'Cotización'")
    else:
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📋 Datos del Cliente")
            cliente = st.text_input("Nombre del Cliente", key="cliente_input")
            email = st.text_input("Email del Cliente", key="email_input")
            telefono = st.text_input("Teléfono", key="phone_input")

        with col2:
            st.subheader("📍 Tipo de Precio")
            tipo_precio = st.radio(
                "Elige tipo de precio:",
                ["FOB (Precio de Salida)", "CIF (Precio con Envío)"],
                key="tipo_precio_radio"
            )

            if tipo_precio == "CIF (Precio con Envío)":
                destino_selec = st.selectbox(
                    "Selecciona País de Destino",
                    list(st.session_state.destinos_monedas.keys()),
                    key="destino_select"
                )
                moneda_destino = st.session_state.destinos_monedas[destino_selec]["moneda"]
                st.info(f"💱 Moneda: {moneda_destino}")
            else:
                destino_selec = None
                moneda_destino = "USD"

        st.markdown("---")
        st.subheader("📦 Agregar Productos al Pedido")

        # Selector de producto
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            productos_lista = [f"{p['codigo']} - {p['nombre']}" for p in st.session_state.productos]
            producto_selec_text = st.selectbox(
                "Selecciona Producto",
                productos_lista,
                key="producto_select"
            )
            # Obtener índice y producto
            producto_idx = [i for i, p in enumerate(st.session_state.productos)
                          if f"{p['codigo']} - {p['nombre']}" == producto_selec_text][0]
            producto_selec = st.session_state.productos[producto_idx]

        with col2:
            cantidad = st.number_input("Cantidad (cajas)", min_value=1, value=1, key="cantidad_input")

        with col3:
            # Mostrar precio según tipo
            if tipo_precio == "FOB (Precio de Salida)":
                precio = producto_selec.get("fob_base", 0)
                st.metric("💰 Precio FOB USD", f"${precio:.2f}")
            else:
                cif_base = st.session_state.destinos_monedas[destino_selec]["cif"]
                precio = cif_base
                st.metric(f"💰 Precio CIF {moneda_destino}", f"${precio:.2f}")

        with col4:
            st.write("")  # Espaciador
            if st.button("➕ Agregar", key="add_producto_btn"):
                st.success(f"✅ {producto_selec['nombre']} agregado")

        st.markdown("---")

        # TABLA DE PRODUCTOS EN PEDIDO (Simulada)
        st.subheader("📋 Productos en Este Pedido")

        data_pedido = {
            "Código": [producto_selec.get("codigo", "")],
            "Producto": [producto_selec.get("nombre", "")],
            "Cantidad": [cantidad],
            "Kg/Caja": [producto_selec.get("kg_caja", 0)],
            "Precio Unitario": [precio],
            "Subtotal": [cantidad * precio]
        }

        df_pedido = pd.DataFrame(data_pedido)
        st.dataframe(df_pedido, use_container_width=True)

        st.markdown("---")

        # RESUMEN FINANCIERO
        st.subheader("💰 Resumen del Pedido")

        col1, col2, col3 = st.columns(3)

        subtotal = cantidad * precio
        costo_caja = st.session_state.configuracion.get("costo_caja", 1.0)
        flete = st.session_state.configuracion.get("flete_estandar", 2.35)

        if tipo_precio == "CIF (Precio con Envío)":
            total_cif = subtotal + (cantidad * flete)
        else:
            total_cif = subtotal

        with col1:
            st.metric("📦 Total Cajas", cantidad)

        with col2:
            st.metric("💵 Subtotal", f"${subtotal:,.2f}")

        with col3:
            st.metric("💰 TOTAL", f"${total_cif:,.2f}")

        st.markdown("---")

        if st.button("✅ Guardar Pedido", key="save_pedido"):
            nuevo_pedido = {
                "cliente": cliente,
                "email": email,
                "telefono": telefono,
                "producto": producto_selec.get("nombre", ""),
                "cantidad": cantidad,
                "tipo_precio": tipo_precio,
                "destino": destino_selec if destino_selec else "FOB",
                "total": total_cif,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            st.session_state.pedidos.append(nuevo_pedido)

            st.markdown("""
                <div class="success-box">
                    <strong>✅ ¡Pedido Guardado!</strong><br>
                    El pedido ha sido registrado correctamente.
                </div>
            """, unsafe_allow_html=True)
            st.balloons()

# ============================================================================
# TAB 3: ACTUALIZAR PRECIOS
# ============================================================================

with tab3:
    st.markdown('<div class="tab-header">💰 Actualizar Precios</div>', unsafe_allow_html=True)

    st.subheader("⚙️ Parámetros de Conversión de Monedas")

    col1, col2 = st.columns(2)

    with col1:
        config_eur = st.number_input(
            "Tipo de Cambio EUR/USD",
            value=st.session_state.configuracion.get("tipo_cambio_eur", 1.164),
            step=0.001
        )

        config_gbp = st.number_input(
            "Tipo de Cambio GBP/USD",
            value=st.session_state.configuracion.get("tipo_cambio_gbp", 1.27),
            step=0.001
        )

    with col2:
        config_chf = st.number_input(
            "Tipo de Cambio CHF/USD",
            value=st.session_state.configuracion.get("tipo_cambio_chf", 1.1),
            step=0.001
        )

        config_aed = st.number_input(
            "Tipo de Cambio AED/USD",
            value=st.session_state.configuracion.get("tipo_cambio_aed", 3.67),
            step=0.001
        )

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        costo_caja = st.number_input(
            "Costo de la Caja (USD)",
            value=st.session_state.configuracion.get("costo_caja", 1.0),
            step=0.1
        )

    with col2:
        flete = st.number_input(
            "Flete Estándar (USD)",
            value=st.session_state.configuracion.get("flete_estandar", 2.35),
            step=0.1
        )

    if st.button("💾 Guardar Parámetros"):
        st.session_state.configuracion["tipo_cambio_eur"] = config_eur
        st.session_state.configuracion["tipo_cambio_gbp"] = config_gbp
        st.session_state.configuracion["tipo_cambio_chf"] = config_chf
        st.session_state.configuracion["tipo_cambio_aed"] = config_aed
        st.session_state.configuracion["costo_caja"] = costo_caja
        st.session_state.configuracion["flete_estandar"] = flete

        st.success("✅ Parámetros guardados")

# ============================================================================
# TAB 4: TODOS LOS DESTINOS
# ============================================================================

with tab4:
    st.markdown('<div class="tab-header">📍 Todos los Destinos - Tarifas</div>', unsafe_allow_html=True)

    if st.session_state.destinos_monedas:
        st.subheader("🌍 Comparación de Precios por Destino")

        df_destinos = pd.DataFrame([
            {"Destino": k, "Moneda": v["moneda"], "CIF USD/Caja": v["cif"]}
            for k, v in st.session_state.destinos_monedas.items()
        ])

        df_destinos = df_destinos.sort_values("CIF USD/Caja")

        st.dataframe(df_destinos, use_container_width=True)

        st.markdown("---")
        st.subheader("📊 Gráfico de Precios por Destino")

        df_grafico = df_destinos.set_index("Destino")["CIF USD/Caja"]
        st.bar_chart(df_grafico)
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
                "Flete Estándar",
                f"${st.session_state.configuracion.get('flete_estandar', 0):.2f}"
            )

        with col2:
            st.metric(
                "Tipo de Cambio EUR",
                f"{st.session_state.configuracion.get('tipo_cambio_eur', 0):.3f}"
            )
            st.metric(
                "Tipo de Cambio GBP",
                f"{st.session_state.configuracion.get('tipo_cambio_gbp', 0):.3f}"
            )

# ============================================================================
# TAB 6: CLIENTES
# ============================================================================

with tab6:
    st.markdown('<div class="tab-header">👥 Gestión de Clientes</div>', unsafe_allow_html=True)

    st.subheader("➕ Nuevo Cliente")

    col1, col2 = st.columns(2)

    with col1:
        nombre = st.text_input("Nombre del Cliente")
        email = st.text_input("Email")

    with col2:
        telefono = st.text_input("Teléfono")
        pais = st.text_input("País")

    if st.button("✅ Agregar Cliente"):
        nuevo_cliente = {"nombre": nombre, "email": email, "telefono": telefono, "pais": pais}
        st.session_state.clientes.append(nuevo_cliente)
        st.success("✅ Cliente agregado")

    st.markdown("---")
    st.subheader("📋 Lista de Clientes")

    if st.session_state.clientes:
        st.dataframe(pd.DataFrame(st.session_state.clientes), use_container_width=True)
    else:
        st.info("No hay clientes registrados")

# ============================================================================
# TAB 7: PEDIDOS
# ============================================================================

with tab7:
    st.markdown('<div class="tab-header">📦 Gestión de Pedidos</div>', unsafe_allow_html=True)

    if st.session_state.pedidos:
        st.dataframe(pd.DataFrame(st.session_state.pedidos), use_container_width=True)
    else:
        st.info("No hay pedidos registrados")

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("""
    <div style="text-align: center; color: #666; font-size: 0.9em;">
        <p>Export Haret © 2026 - Sistema Premium de Gestión de Pedidos</p>
        <p>✨ Tablas editables | 💡 Precios inteligentes | 📊 Análisis en tiempo real</p>
    </div>
""", unsafe_allow_html=True)
