"""
🚛 OPTIMIZADOR DE RUTAS VRP - Gestión Inteligente de Residuos
Aplicación completa con Streamlit + Algoritmo VRP + WhatsApp Web
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tempfile
import os
import webbrowser
import time
import json
from typing import Dict, List, Any
import io

# IMPORTAR CON TRY/EXCEPT PARA MANEJAR FALLOS
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_AVAILABLE = True
except ImportError:
    st.warning("⚠️ Folium no está instalado. Algunas funciones de mapa no estarán disponibles.")
    FOLIUM_AVAILABLE = False
    # Crear objetos dummy para evitar errores
    folium = None
    st_folium = lambda *args, **kwargs: None

# Módulos personalizados - importar con try/except
try:
    from modules.geocoder import GeocodificadorOffline
    from modules.optimizer_vrp import OptimizadorVRP
    from modules.whatsapp_web import WhatsAppLinkGenerator
    from modules.excel_processor import ExcelProcessor
    from modules.conductor_manager import ConductorManager
    MODULES_AVAILABLE = True
except ImportError as e:
    st.error(f"⚠️ Error importando módulos: {e}")
    st.info("Asegúrate de que los módulos estén en la carpeta 'modules/'")
    MODULES_AVAILABLE = False
    # Crear clases dummy
    class DummyClass:
        def __init__(self, *args, **kwargs): pass
        def __getattr__(self, name): return lambda *args, **kwargs: None
    GeocodificadorOffline = OptimizadorVRP = WhatsAppLinkGenerator = ExcelProcessor = ConductorManager = DummyClass

# ============================================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================================

st.set_page_config(
    page_title="OPTIMIZADOR VRP - Gestión de Residuos",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://github.com/tuusuario/optimizador-rutas-vrp',
        'Report a bug': None,
        'About': "Sistema inteligente de optimización de rutas VRP"
    }
)

# ============================================================================
# CSS PERSONALIZADO
# ============================================================================

st.markdown("""
<style>
    /* Títulos */
    h1, h2, h3 {
        color: #1E3A8A;
        font-weight: 700;
    }
    
    /* Tarjetas de métricas */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 10px 0;
    }
    
    .metric-value {
        font-size: 28px;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .metric-label {
        font-size: 14px;
        opacity: 0.9;
    }
    
    /* Tarjetas de rutas */
    .route-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        margin: 15px 0;
        border-left: 5px solid #25D366;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    /* Botones */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        padding: 10px 24px;
    }
    
    /* Badges */
    .badge {
        display: inline-block;
        padding: 4px 8px;
        border-radius: 12px;
        font-size: 12px;
        font-weight: 600;
        margin: 2px;
    }
    
    .badge-success {
        background-color: #10B981;
        color: white;
    }
    
    .badge-warning {
        background-color: #F59E0B;
        color: white;
    }
    
    .badge-danger {
        background-color: #EF4444;
        color: white;
    }
    
    /* Animación simple */
    .fade-in {
        animation: fadeIn 0.5s ease-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; }
        to { opacity: 1; }
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# CLASE PRINCIPAL DE LA APLICACIÓN
# ============================================================================

class OptimizadorVRPApp:
    def __init__(self):
        """Inicializar aplicación con manejo de errores"""
        if not MODULES_AVAILABLE:
            st.error("❌ Módulos no disponibles. Verifica la instalación.")
            return
            
        self.geocoder = GeocodificadorOffline()
        self.optimizer = OptimizadorVRP()
        self.whatsapp = WhatsAppLinkGenerator()
        self.excel_processor = ExcelProcessor()
        self.conductor_manager = ConductorManager()
        
        # Configuración inicial
        self.vertederos = {
            'norte': {
                'nombre': 'Vertedero Norte',
                'direccion': 'C. Laguna del Marquesado, 16, Madrid',
                'coords': [40.3460, -3.7007]
            },
            'sur': {
                'nombre': 'Vertedero Sur',
                'direccion': 'Ctra. Vertedero Municipal Valdemingómez, Madrid',
                'coords': [40.3186, -3.6017]
            }
        }
        
        # Inicializar estado de sesión
        self.init_session_state()
    
    def init_session_state(self):
        """Inicializar variables de sesión"""
        if 'paso_actual' not in st.session_state:
            st.session_state.paso_actual = 1
        if 'df_servicios' not in st.session_state:
            st.session_state.df_servicios = None
        if 'df_geocodificado' not in st.session_state:
            st.session_state.df_geocodificado = None
        if 'rutas_optimizadas' not in st.session_state:
            st.session_state.rutas_optimizadas = None
        if 'conductores_cargados' not in st.session_state:
            st.session_state.conductores_cargados = False
        if 'parametros' not in st.session_state:
            st.session_state.parametros = {}

    def mostrar_header(self):
        """Mostrar cabecera de la aplicación"""
        st.title("🚛 Optimizador de Rutas VRP")
        st.markdown("Gestión Inteligente de Residuos y Rutas")
        st.markdown("---")

    def mostrar_sidebar(self):
        """Muestra la barra lateral de navegación"""
        with st.sidebar:
            st.header("Navegación")
            
            # Paso 1: Cargar
            paso1 = st.container()
            with paso1:
                col1, col2 = st.columns([1, 4])
                with col1:
                    icono = '✅' if st.session_state.paso_actual > 1 else '1️⃣'
                    st.markdown(f"<h3>{icono}</h3>", unsafe_allow_html=True)
                with col2:
                    st.markdown("**Cargar Datos**")

            # Paso 2: Geocodificar
            paso2 = st.container()
            with paso2:
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.markdown(f"<h3>{'✅' if st.session_state.paso_actual > 2 else '2️⃣'}</h3>", 
                               unsafe_allow_html=True)
                with col2:
                    st.markdown("**Geocodificar**")
            
            # Paso 3: Optimizar
            paso3 = st.container()
            with paso3:
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.markdown(f"<h3>{'✅' if st.session_state.paso_actual > 3 else '3️⃣'}</h3>", 
                               unsafe_allow_html=True)
                with col2:
                    st.markdown("**Optimizar Rutas**")
            
            # Paso 4: Enviar
            paso4 = st.container()
            with paso4:
                col1, col2 = st.columns([1, 4])
                with col1:
                    st.markdown(f"<h3>{'✅' if st.session_state.paso_actual > 4 else '4️⃣'}</h3>", 
                               unsafe_allow_html=True)
                with col2:
                    st.markdown("**Enviar a Conductores**")
            
            st.divider()
            
            # Panel de estadísticas
            st.markdown("### 📊 ESTADÍSTICAS")
            
            if st.session_state.df_servicios is not None:
                df = st.session_state.df_servicios
                st.metric("Servicios cargados", len(df))
                
                if 'Conductor' in df.columns:
                    conductores = df['Conductor'].nunique()
                    st.metric("Conductores asignados", conductores)
            
            st.divider()
            
            # Botón de reset
            if st.button("🔄 Reiniciar Proceso", use_container_width=True):
                for key in list(st.session_state.keys()):
                    if key != 'paso_actual':
                        del st.session_state[key]
                st.session_state.paso_actual = 1
                st.rerun()
    
    def paso_1_cargar_datos(self):
        """Paso 1: Cargar datos de servicios y conductores"""
        st.header("📥 PASO 1: CARGAR DATOS")
        
        tab1, tab2 = st.tabs(["📋 Servicios del Día", "👥 Gestión de Conductores"])
        
        with tab1:
            st.markdown("""
            ### Subir Excel de Servicios
            Sube tu archivo Excel con los servicios del día. 
            **Formato requerido:** Mantén las mismas columnas que usas actualmente.
            """)
            
            uploaded_file = st.file_uploader(
                "Seleccionar archivo Excel",
                type=['xlsx', 'xls'],
                key="upload_servicios"
            )
            
            if uploaded_file:
                try:
                    # Procesar archivo
                    with st.spinner("Procesando archivo..."):
                        df = self.excel_processor.procesar_excel_servicios(uploaded_file)
                        
                        # Guardar en sesión
                        st.session_state.df_servicios = df
                        st.session_state.paso_actual = max(st.session_state.paso_actual, 2)
                        
                        # Mostrar resumen
                        st.success(f"✅ Archivo cargado: {len(df)} servicios")
                        
                        # Mostrar vista previa
                        with st.expander("👁️ VER DATOS CARGADOS", expanded=True):
                            st.dataframe(df, use_container_width=True)
                            
                            # Estadísticas
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total servicios", len(df))
                            with col2:
                                if 'Conductor' in df.columns:
                                    st.metric("Conductores", df['Conductor'].nunique())
                            with col3:
                                if 'Material' in df.columns:
                                    retiradas = df['Material'].str.contains('retirada', case=False, na=False).sum()
                                    st.metric("Retiradas", retiradas)
                
                except Exception as e:
                    st.error(f"❌ Error al procesar el archivo: {str(e)}")
            
            # Botón para descargar plantilla
            st.download_button(
                label="📋 Descargar Plantilla Excel",
                data=self.excel_processor.generar_plantilla_servicios(),
                file_name="plantilla_servicios.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with tab2:
            st.markdown("""
            ### Gestión de Conductores
            Gestiona la información de conductores: nombre, teléfono, vehículo, etc.
            """)
            
            # Subir Excel de conductores
            uploaded_conductores = st.file_uploader(
                "Subir Excel de conductores",
                type=['xlsx', 'xls'],
                key="upload_conductores"
            )
            
            if uploaded_conductores:
                try:
                    with st.spinner("Cargando conductores..."):
                        conductores_df = self.conductor_manager.cargar_desde_excel(uploaded_conductores)
                        st.session_state.conductores_cargados = True
                        
                        st.success(f"✅ {len(conductores_df)} conductores cargados")
                        
                        # Mostrar conductores
                        st.dataframe(conductores_df, use_container_width=True)
                        
                        # Opciones para gestionar conductores
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button("💾 Guardar Conductores", use_container_width=True):
                                self.conductor_manager.guardar_conductores(conductores_df)
                                st.success("✅ Conductores guardados en base de datos")
                        
                        with col2:
                            if st.button("🔄 Cargar desde BD", use_container_width=True):
                                conductores_bd = self.conductor_manager.cargar_conductores()
                                if conductores_bd is not None:
                                    st.success(f"✅ {len(conductores_bd)} conductores cargados desde BD")
                                    st.dataframe(conductores_bd, use_container_width=True)
                
                except Exception as e:
                    st.error(f"❌ Error al cargar conductores: {str(e)}")
            
            # Gestión manual de conductores
            with st.expander("✏️ Añadir/Editar Conductor Manualmente"):
                nombre = st.text_input("Nombre del conductor")
                telefono = st.text_input("Teléfono (WhatsApp)")
                vehiculo = st.text_input("Vehículo asignado")
                etiqueta_c = st.checkbox("Tiene etiqueta C")
                capacidad = st.selectbox("Capacidad vehículo (m³)", [3, 6, 9, 12, 15])
                
                if st.button("➕ Añadir Conductor"):
                    if nombre and telefono:
                        nuevo_conductor = {
                            'nombre': nombre,
                            'telefono': telefono,
                            'vehiculo': vehiculo,
                            'etiqueta_c': etiqueta_c,
                            'capacidad_m3': capacidad
                        }
                        self.conductor_manager.agregar_conductor(nuevo_conductor)
                        st.success(f"✅ Conductor {nombre} añadido")
                        st.rerun()
            
            # Botón para descargar plantilla conductores
            st.download_button(
                label="👥 Descargar Plantilla Conductores",
                data=self.excel_processor.generar_plantilla_conductores(),
                file_name="plantilla_conductores.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    
    def paso_2_geocodificar(self):
        """Paso 2: Geocodificar direcciones"""
        st.header("🗺️ PASO 2: GEOCODIFICAR DIRECCIONES")
        
        if st.session_state.df_servicios is None:
            st.warning("⚠️ Primero carga los datos en el Paso 1")
            return
        
        st.markdown("""
        ### Conversión de Direcciones a Coordenadas
        El sistema convertirá automáticamente todas las direcciones a coordenadas GPS
        usando OpenStreetMap (gratuito).
        """)
        
        # Parámetros de geocodificación
        with st.expander("⚙️ Configuración de Geocodificación"):
            usar_cache = st.checkbox("Usar caché de geocodificaciones", value=True)
            tiempo_espera = st.slider("Tiempo entre consultas (segundos)", 0.5, 3.0, 1.0, 0.5)
        
        if st.button("📍 Iniciar Geocodificación", type="primary"):
            with st.spinner("Geocodificando direcciones..."):
                # Configurar geocodificador
                self.geocoder.tiempo_espera = tiempo_espera
                self.geocoder.usar_cache = usar_cache
                
                # Progreso
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Geocodificar
                df_geo = self.geocoder.procesar_dataframe(
                    st.session_state.df_servicios,
                    progress_callback=lambda pct, msg: (
                        progress_bar.progress(pct),
                        status_text.text(msg)
                    )
                )
                
                # Guardar resultados
                st.session_state.df_geocodificado = df_geo
                st.session_state.paso_actual = 3  # Forzar el paso 3
                st.rerun()  # <--- ESTA LÍNEA ES CRUCIAL, si falta, la app no se refresca
                
                # Mostrar resultados
                st.success(f"✅ {df_geo['geocodificado'].sum()}/{len(df_geo)} direcciones geocodificadas")
                
                # Mapa con resultados
                self.mostrar_mapa_geocodificado(df_geo)
                
                # Estadísticas
                self.mostrar_estadisticas_geocodificacion(df_geo)
    
    def mostrar_mapa_geocodificado(self, df):
        """Mostrar mapa con direcciones geocodificadas"""
        st.subheader("📍 MAPA DE UBICACIONES")
        
        # Crear mapa centrado en Madrid
        m = folium.Map(location=[40.4168, -3.7038], zoom_start=11, tiles='OpenStreetMap')
        
        # Añadir vertederos
        for nombre, datos in self.vertederos.items():
            folium.Marker(
                location=datos['coords'],
                popup=folium.Popup(f"<b>{datos['nombre']}</b><br>{datos['direccion']}", max_width=300),
                tooltip=datos['nombre'],
                icon=folium.Icon(color='red', icon='trash', prefix='fa')
            ).add_to(m)
        
        # Añadir clientes (solo los geocodificados)
        df_geocodificado = df[df['geocodificado'] == True]
        
        for idx, row in df_geocodificado.iterrows():
            # Color según tipo de servicio
            color = 'blue'
            if 'Material' in row:
                if 'retirada' in str(row['Material']).lower():
                    color = 'green'
                elif 'deposito' in str(row['Material']).lower():
                    color = 'orange'
            
            # Crear popup
            popup_html = f"""
            <div style="font-family: Arial; width: 250px;">
                <h4 style="margin: 0; color: #1E3A8A;">{row.get('Cliente', 'Cliente')}</h4>
                <hr style="margin: 5px 0;">
                <p style="margin: 2px 0;"><b>Dirección:</b> {row.get('Direccion', '')}</p>
                <p style="margin: 2px 0;"><b>Hora:</b> {row.get('Hora Pide', '')}</p>
                <p style="margin: 2px 0;"><b>Tipo:</b> {row.get('Material', '')}</p>
                <p style="margin: 2px 0;"><b>Conductor:</b> {row.get('Conductor', '')}</p>
            </div>
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=row.get('Cliente', 'Cliente'),
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.7
            ).add_to(m)
        
        # Mostrar mapa
        st_folium(m, width=800, height=500, returned_objects=[])
        
        # Leyenda
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("🔴 **Vertedero**")
        with col2:
            st.markdown("🔵 **Servicio general**")
        with col3:
            st.markdown("🟢 **Retirada**")
        with col4:
            st.markdown("🟠 **Depósito**")
    
    def mostrar_estadisticas_geocodificacion(self, df):
        """Mostrar estadísticas de geocodificación"""
        st.subheader("📊 ESTADÍSTICAS DE GEOCODIFICACIÓN")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            exitosos = df['geocodificado'].sum()
            total = len(df)
            st.metric("Geocodificados", f"{exitosos}/{total}", 
                     delta=f"{exitosos/total*100:.1f}%" if total > 0 else "0%")
        
        with col2:
            madrid_central = df['es_madrid_central'].sum()
            st.metric("Madrid Central", madrid_central)
        
        with col3:
            if 'zona_madrid' in df.columns:
                zonas = df['zona_madrid'].nunique()
                st.metric("Zonas diferentes", zonas)
        
        with col4:
            if 'Conductor' in df.columns:
                conductores = df['Conductor'].nunique()
                st.metric("Conductores afectados", conductores)
        
        # Mostrar problemas de geocodificación
        if exitosos < total:
            st.warning("⚠️ Algunas direcciones no se pudieron geocodificar")
            problemas = df[df['geocodificado'] == False]
            
            with st.expander("🔍 Ver direcciones con problemas"):
                st.dataframe(problemas[['Cliente', 'Direccion', 'Poblacion']], 
                           use_container_width=True)
                
                # Opción para corregir manualmente
                if st.button("✏️ Corregir Manualmente"):
                    st.info("Funcionalidad en desarrollo. Por ahora, verifica las direcciones en el Excel.")
    
    def paso_3_optimizar(self):
        """Paso 3: Optimizar rutas con algoritmo VRP"""
        st.header("🔄 PASO 3: OPTIMIZAR RUTAS VRP")
        
        if st.session_state.df_geocodificado is None:
            st.warning("⚠️ Primero geocodifica las direcciones en el Paso 2")
            return
        
        st.markdown("""
        ### Algoritmo de Optimización VRP (Vehicle Routing Problem)
        El sistema calculará las rutas óptimas considerando:
        - Distancias reales entre puntos
        - Horarios solicitados por clientes
        - Capacidad de los vehículos (hasta 5 contenedores)
        - Combinaciones depósito-retirada (hasta 5km)
        - Restricciones Madrid Central (solo vehículos C)
        """)
        
        # Configuración de parámetros
        with st.expander("⚙️ PARÁMETROS DE OPTIMIZACIÓN", expanded=True):
            col1, col2 = st.columns(2)
            
            with col1:
                max_distancia_combo = st.slider(
                    "Distancia máxima para combos (km)",
                    min_value=1, max_value=10, value=5, step=1
                )
                
                flexibilidad_horaria = st.slider(
                    "Flexibilidad horaria (minutos)",
                    min_value=30, max_value=180, value=60, step=15
                )
                
                vehiculos_c_disponibles = st.number_input(
                    "Vehículos con etiqueta C disponibles",
                    min_value=1, max_value=20, value=10, step=1
                )
            
            with col2:
                capacidad_vehiculo = st.selectbox(
                    "Capacidad por vehículo (contenedores)",
                    options=[3, 5, 7, 10],
                    index=1,
                    help="Número máximo de contenedores que puede llevar un vehículo"
                )
                
                velocidad_promedio = st.slider(
                    "Velocidad promedio (km/h)",
                    min_value=20, max_value=60, value=30, step=5
                )
                
                tiempo_por_servicio = st.slider(
                    "Tiempo por servicio (minutos)",
                    min_value=10, max_value=60, value=30, step=5
                )
        
        # Algoritmo de optimización a usar
        algoritmo = st.selectbox(
            "Seleccionar algoritmo de optimización",
            ["VRP con Tiempo Windows", "VRP con Capacidades", "VRP Híbrido (Recomendado)"],
            index=2
        )
        
        # Botón para optimizar
        if st.button("🚀 EJECUTAR OPTIMIZACIÓN VRP", type="primary", use_container_width=True):
            with st.spinner("Ejecutando algoritmo VRP. Esto puede tomar unos minutos..."):
                # Guardar parámetros
                st.session_state.parametros = {
                    'max_distancia_combo': max_distancia_combo,
                    'flexibilidad_horaria': flexibilidad_horaria,
                    'vehiculos_c': vehiculos_c_disponibles,
                    'capacidad_vehiculo': capacidad_vehiculo,
                    'velocidad_promedio': velocidad_promedio,
                    'tiempo_por_servicio': tiempo_por_servicio,
                    'algoritmo': algoritmo
                }
                
                # Configurar optimizador
                self.optimizer.configurar(**st.session_state.parametros)
                
     
                # Ejecutar optimización
                rutas = self.optimizer.optimizar(st.session_state.df_geocodificado)
                
                # Guardar resultados (CORREGIDO)
                if rutas:
                    st.session_state.rutas_optimizadas = rutas
                    st.session_state.paso_actual = max(st.session_state.paso_actual, 4)
                    st.success(f"✅ {len(rutas)} rutas optimizadas generadas")
                    
                    # Mostrar resumen
                    self.mostrar_resumen_optimizacion(rutas)
                    self.mostrar_rutas_detalladas(rutas)
                else:
                    st.error("❌ No se pudieron generar rutas válidas.")
                
                # Guardar resultados
                st.session_state.rutas_optimizadas = rutas
                st.session_state.paso_actual = max(st.session_state.paso_actual, 4)
                
                # Mostrar resultados
                st.success(f"✅ {len(rutas)} rutas optimizadas generadas")
                
                # Mostrar resumen
                self.mostrar_resumen_optimizacion(rutas)
                
                # Mostrar rutas detalladas
                self.mostrar_rutas_detalladas(rutas)
    
    def mostrar_resumen_optimizacion(self, rutas):
        """Mostrar resumen de la optimización"""
        st.subheader("📊 RESUMEN DE OPTIMIZACIÓN")
        
        # Calcular métricas
        total_km = sum(r['estadisticas']['distancia_total_km'] for r in rutas.values())
        total_tiempo = sum(r['estadisticas']['tiempo_total_min'] for r in rutas.values())
        total_servicios = sum(r['estadisticas']['num_servicios'] for r in rutas.values())
        total_combustible = sum(r['estadisticas']['combustible_estimado_l'] for r in rutas.values())
        
        # Métricas principales
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">🏁</div>
                <div class="metric-value">{:.1f} km</div>
                <div class="metric-label">DISTANCIA TOTAL</div>
            </div>
            """.format(total_km), unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">⏱️</div>
                <div class="metric-value">{:.1f} h</div>
                <div class="metric-label">TIEMPO TOTAL</div>
            </div>
            """.format(total_tiempo/60), unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">⛽</div>
                <div class="metric-value">{:.1f} L</div>
                <div class="metric-label">COMBUSTIBLE</div>
            </div>
            """.format(total_combustible), unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
            <div class="metric-card">
                <div class="metric-value">📦</div>
                <div class="metric-value">{}</div>
                <div class="metric-label">SERVICIOS</div>
            </div>
            """.format(total_servicios), unsafe_allow_html=True)
        
        # Gráfico de distribución
        st.subheader("📈 DISTRIBUCIÓN POR VEHÍCULO")
        
        # Crear DataFrame para gráfico
        datos_rutas = []
        for vehiculo, ruta in rutas.items():
            datos_rutas.append({
                'Vehículo': vehiculo,
                'Distancia (km)': ruta['estadisticas']['distancia_total_km'],
                'Tiempo (h)': ruta['estadisticas']['tiempo_total_min'] / 60,
                'Servicios': ruta['estadisticas']['num_servicios'],
                'Combustible (L)': ruta['estadisticas']['combustible_estimado_l']
            })
        
        df_rutas = pd.DataFrame(datos_rutas)
        
        # Mostrar tabla
        st.dataframe(df_rutas, use_container_width=True)
        
        # Mostrar combinaciones encontradas
        combos_totales = sum(r['estadisticas']['combos_detectados'] for r in rutas.values())
        if combos_totales > 0:
            st.info(f"🔗 Se detectaron {combos_totales} combinaciones depósito-retirada")
    
    def mostrar_rutas_detalladas(self, rutas):
        """Mostrar rutas optimizadas en detalle"""
        st.subheader("📋 RUTAS OPTIMIZADAS")
        
        for vehiculo, ruta in rutas.items():
            with st.expander(
                f"🚚 **{vehiculo}** - {ruta['estadisticas']['num_servicios']} servicios | "
                f"{ruta['estadisticas']['distancia_total_km']:.1f} km | "
                f"{ruta['estadisticas']['tiempo_total_min']:.0f} min",
                expanded=False
            ):
                # Estadísticas de la ruta
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Distancia", f"{ruta['estadisticas']['distancia_total_km']:.1f} km")
                
                with col2:
                    st.metric("Tiempo", f"{ruta['estadisticas']['tiempo_total_min']:.0f} min")
                
                with col3:
                    st.metric("Combustible", f"{ruta['estadisticas']['combustible_estimado_l']:.1f} L")
                
                with col4:
                    st.metric("Combos", ruta['estadisticas']['combos_detectados'])
                
                # Tabla de servicios
                st.markdown("#### 📍 ITINERARIO DETALLADO")
                
                servicios_df = pd.DataFrame(ruta['servicios'])
                st.dataframe(servicios_df, use_container_width=True)
                
                # Mapa de la ruta
                st.markdown("#### 🗺️ MAPA DE LA RUTA")
                self.mostrar_mapa_ruta(ruta, vehiculo)
                
                # Botón para enviar por WhatsApp
                st.markdown("#### 📱 ENVIAR RUTA")
                self.boton_whatsapp_ruta(vehiculo, ruta)
    
    def mostrar_mapa_ruta(self, ruta, vehiculo):
        """Mostrar mapa de una ruta específica"""
        # Crear mapa
        m = folium.Map(location=[40.4168, -3.7038], zoom_start=12)
        
        # Añadir vertederos
        for nombre, datos in self.vertederos.items():
            folium.Marker(
                datos['coords'],
                popup=datos['nombre'],
                icon=folium.Icon(color='red', icon='trash', prefix='fa')
            ).add_to(m)
        
        # Añadir puntos de la ruta
        puntos = []
        for servicio in ruta['servicios']:
            if 'lat' in servicio and 'lon' in servicio:
                punto = [servicio['lat'], servicio['lon']]
                puntos.append(punto)
                
                # Marcador
                folium.Marker(
                    punto,
                    popup=f"{servicio.get('Cliente', 'Cliente')}<br>{servicio.get('Direccion', '')}",
                    icon=folium.Icon(color='blue', icon='info-sign')
                ).add_to(m)
        
        # Dibujar línea de la ruta si hay suficientes puntos
        if len(puntos) > 1:
            folium.PolyLine(
                puntos,
                color='blue',
                weight=3,
                opacity=0.7,
                popup=f"Ruta {vehiculo}"
            ).add_to(m)
        
        # Mostrar mapa
        st_folium(m, width=800, height=400)
    
    def boton_whatsapp_ruta(self, vehiculo, ruta):
        """Crear botón para enviar ruta por WhatsApp"""
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            # Vista previa del mensaje
            with st.expander("👁️ VER MENSAJE WHATSAPP"):
                mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
                st.text_area("", mensaje, height=200, key=f"msg_{vehiculo}")
        
        with col2:
            # Generar enlace WhatsApp
            mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
            enlace = self.whatsapp.generar_enlace_whatsapp(mensaje)
            
            # Botón para abrir WhatsApp
            if st.button(f"📤 Enviar {vehiculo}", key=f"btn_{vehiculo}", use_container_width=True):
                webbrowser.open_new_tab(enlace)
                st.success(f"✅ Abriendo WhatsApp para {vehiculo}")
        
        with col3:
            # Descargar mensaje como texto
            mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
            st.download_button(
                label="💾 Descargar",
                data=mensaje,
                file_name=f"ruta_{vehiculo}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                mime="text/plain",
                use_container_width=True
            )
    
    def paso_4_enviar(self):
        """Paso 4: Enviar rutas a conductores"""
        st.header("📱 PASO 4: ENVIAR A CONDUCTORES")
        
        if st.session_state.rutas_optimizadas is None:
            st.warning("⚠️ Primero optimiza las rutas en el Paso 3")
            return
        
        st.markdown("""
        ### Envío Masivo por WhatsApp Web
        Envía todas las rutas optimizadas a los conductores mediante WhatsApp Web.
        El sistema abrirá una pestaña por cada conductor con el mensaje predefinido.
        """)
        
        # Opciones de envío
        with st.expander("⚙️ CONFIGURACIÓN DE ENVÍO"):
            modo_envio = st.radio(
                "Modo de envío",
                ["Uno por uno", "Todos a la vez"],
                help="Todos a la vez abrirá varias pestañas de WhatsApp"
            )
            
            incluir_detalles = st.checkbox("Incluir detalles completos", value=True)
            solicitar_confirmacion = st.checkbox("Solicitar confirmación", value=True)
        
        # Panel de envío
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📤 ENVIAR TODAS LAS RUTAS", type="primary", use_container_width=True):
                st.info("⚠️ Se abrirán varias pestañas de WhatsApp Web")
                
                # Contador
                enviados = 0
                status = st.empty()
                
                for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
                    status.text(f"Enviando {vehiculo}...")
                    
                    # Generar y abrir enlace
                    mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
                    enlace = self.whatsapp.generar_enlace_whatsapp(mensaje)
                    webbrowser.open_new_tab(enlace)
                    
                    enviados += 1
                    time.sleep(1)  # Pequeña pausa entre aperturas
                
                status.text("")
                st.success(f"✅ {enviados} rutas enviadas a WhatsApp Web")
        
        with col2:
            # Exportar todos los mensajes
            if st.button("💾 EXPORTAR TODOS LOS MENSAJES", use_container_width=True):
                todos_mensajes = []
                
                for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
                    mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
                    todos_mensajes.append(f"=== {vehiculo} ===\n{mensaje}\n\n")
                
                contenido = "".join(todos_mensajes)
                
                st.download_button(
                    label="📥 Descargar archivo",
                    data=contenido,
                    file_name=f"mensajes_whatsapp_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain"
                )
        
        # Panel de mensajes individuales
        st.subheader("✏️ MENSAJES INDIVIDUALES")
        
        for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
            self.boton_whatsapp_ruta(vehiculo, ruta)
    
    def panel_exportacion(self):
        """Panel de exportación de resultados"""
        st.header("💾 EXPORTAR RESULTADOS")
        
        if st.session_state.rutas_optimizadas is None:
            st.warning("⚠️ No hay rutas optimizadas para exportar")
            return
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # Exportar a Excel
            if st.button("📊 Exportar a Excel", use_container_width=True):
                excel_bytes = self.optimizer.exportar_excel(
                    st.session_state.rutas_optimizadas,
                    st.session_state.df_geocodificado
                )
                
                st.download_button(
                    label="📥 Descargar Excel",
                    data=excel_bytes,
                    file_name=f"rutas_optimizadas_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
        
        with col2:
            # Exportar a KML
            if st.button("🗺️ Exportar a KML", use_container_width=True):
                kml_content = self.optimizer.exportar_kml(st.session_state.rutas_optimizadas)
                
                st.download_button(
                    label="📥 Descargar KML",
                    data=kml_content,
                    file_name=f"rutas_{datetime.now().strftime('%Y%m%d_%H%M')}.kml",
                    mime="application/vnd.google-earth.kml+xml",
                    use_container_width=True
                )
        
        with col3:
            # Exportar informe PDF
            if st.button("📄 Generar Informe", use_container_width=True):
                informe = self.generar_informe_completo()
                
                st.download_button(
                    label="📥 Descargar Informe",
                    data=informe,
                    file_name=f"informe_rutas_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                    mime="text/plain",
                    use_container_width=True
                )
    
    def generar_informe_completo(self):
        """Generar informe completo en texto"""
        informe = []
        informe.append("=" * 60)
        informe.append("INFORME DE OPTIMIZACIÓN DE RUTAS")
        informe.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        informe.append("=" * 60)
        informe.append("")
        
        # Resumen general
        if st.session_state.rutas_optimizadas:
            total_km = sum(r['estadisticas']['distancia_total_km'] for r in st.session_state.rutas_optimizadas.values())
            total_tiempo = sum(r['estadisticas']['tiempo_total_min'] for r in st.session_state.rutas_optimizadas.values())
            total_servicios = sum(r['estadisticas']['num_servicios'] for r in st.session_state.rutas_optimizadas.values())
            
            informe.append("📊 RESUMEN GENERAL:")
            informe.append(f"  • Rutas generadas: {len(st.session_state.rutas_optimizadas)}")
            informe.append(f"  • Distancia total: {total_km:.1f} km")
            informe.append(f"  • Tiempo total: {total_tiempo/60:.1f} horas")
            informe.append(f"  • Servicios asignados: {total_servicios}")
            informe.append("")
        
        # Parámetros usados
        informe.append("⚙️ PARÁMETROS DE OPTIMIZACIÓN:")
        for key, value in st.session_state.parametros.items():
            informe.append(f"  • {key}: {value}")
        informe.append("")
        
        # Rutas detalladas
        informe.append("🚛 RUTAS OPTIMIZADAS:")
        for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
            stats = ruta['estadisticas']
            informe.append(f"\n{vehiculo}:")
            informe.append(f"  • Servicios: {stats['num_servicios']}")
            informe.append(f"  • Distancia: {stats['distancia_total_km']:.1f} km")
            informe.append(f"  • Tiempo: {stats['tiempo_total_min']:.0f} min")
            informe.append(f"  • Combustible: {stats['combustible_estimado_l']:.1f} L")
            informe.append(f"  • Combos: {stats['combos_detectados']}")
        
        return "\n".join(informe)
    
    def run(self):
        """Ejecutar aplicación completa"""
        # Mostrar header
        self.mostrar_header()
        
        # Mostrar sidebar
        self.mostrar_sidebar()
        
        # Contenido principal basado en el paso actual
        st.markdown(f"<div class='fade-in'>", unsafe_allow_html=True)
        
        if st.session_state.paso_actual == 1:
            self.paso_1_cargar_datos()
        
        elif st.session_state.paso_actual == 2:
            self.paso_2_geocodificar()
        
        elif st.session_state.paso_actual == 3:
            self.paso_3_optimizar()
        
        elif st.session_state.paso_actual >= 4:
            self.paso_4_enviar()
            self.panel_exportacion()
        
        st.markdown("</div>", unsafe_allow_html=True)

# ============================================================================
# EJECUCIÓN PRINCIPAL CON MANEJO DE ERRORES
# ============================================================================

def main():
    """Función principal con manejo de errores"""
    
    # Mostrar mensaje de advertencia si folium no está disponible
    if not FOLIUM_AVAILABLE:
        st.warning("""
        ⚠️ **Folium no está instalado**
        
        Para ver los mapas, instala folium:
        ```
        pip install folium==0.14.0 streamlit-folium==0.15.1
        ```
        
        La aplicación funcionará sin mapas por ahora.
        """)
    
    # Mostrar mensaje si los módulos no están disponibles
    if not MODULES_AVAILABLE:
        st.error("""
        ❌ **Módulos no encontrados**
        
        Asegúrate de que la carpeta 'modules/' contenga:
        - geocoder.py
        - optimizer_vrp.py  
        - whatsapp_web.py
        - excel_processor.py
        - conductor_manager.py
        """)
        
        # Mostrar estructura esperada
        with st.expander("📁 Estructura de archivos esperada"):
            st.code("""
            optimizador-rutas-vrp/
            ├── app.py
            ├── requirements.txt
            ├── config.py
            ├── modules/
            │   ├── __init__.py
            │   ├── geocoder.py
            │   ├── optimizer_vrp.py
            │   ├── whatsapp_web.py
            │   ├── excel_processor.py
            │   └── conductor_manager.py
            ├── data/
            └── templates/
            """)
        
        return
    
    # Inicializar y ejecutar aplicación
    try:
        app = OptimizadorVRPApp()
        app.run()
    except Exception as e:
        st.error(f"❌ Error en la aplicación: {str(e)}")
        st.info("Revisa la consola para más detalles.")

if __name__ == "__main__":

    main()