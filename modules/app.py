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
    folium = None
    st_folium = lambda *args, **kwargs: None

# Módulos personalizados
try:
    from modules.geocoder import GeocodificadorOffline
    from modules.optimizer_vrp import OptimizadorVRP
    from modules.whatsapp_web import WhatsAppLinkGenerator
    from modules.excel_processor import ExcelProcessor
    from modules.conductor_manager import ConductorManager
    MODULES_AVAILABLE = True
except ImportError as e:
    st.error(f"⚠️ Error importando módulos: {e}")
    st.info("Asegúrate de que los módulos estén en la carpeta 'modules/' y exista config.py")
    MODULES_AVAILABLE = False
    # Clases dummy para evitar crash total
    class Dummy: pass
    GeocodificadorOffline = OptimizadorVRP = WhatsAppLinkGenerator = ExcelProcessor = ConductorManager = Dummy

# ============================================================================
# CONFIGURACIÓN DE PÁGINA
# ============================================================================

st.set_page_config(
    page_title="OPTIMIZADOR VRP - Gestión de Residuos",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# CSS PERSONALIZADO
# ============================================================================

st.markdown("""
<style>
    h1, h2, h3 { color: #1E3A8A; font-weight: 700; }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin: 10px 0;
    }
    .metric-value { font-size: 28px; font-weight: bold; margin: 10px 0; }
    .metric-label { font-size: 14px; opacity: 0.9; }
    .stButton > button { border-radius: 8px; font-weight: 600; padding: 10px 24px; }
    .fade-in { animation: fadeIn 0.5s ease-out; }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
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
        
        # Vertederos (para visualización en mapa)
        self.vertederos = {
            'norte': {
                'nombre': 'Laguna del Marquesado',
                'direccion': 'C. Laguna del Marquesado, 16, Madrid',
                'coords': [40.3460, -3.7007]
            },
            'sur': {
                'nombre': 'Valdemingómez',
                'direccion': 'Ctra. Vertedero Municipal Valdemingómez, Madrid',
                'coords': [40.3186, -3.6017]
            }
        }
        
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
        """Muestra la barra lateral de navegación interactiva"""
        with st.sidebar:
            st.image("https://img.icons8.com/color/96/delivery--v1.png", width=80)
            st.title("Gestión de Residuos")
            st.divider()
            
            st.header("Navegación")
            
            # --- BOTONES DE NAVEGACIÓN ---
            
            # Paso 1: Cargar Datos
            icono1 = '✅' if st.session_state.paso_actual > 1 else '1️⃣'
            tipo_btn1 = "primary" if st.session_state.paso_actual == 1 else "secondary"
            if st.button(f"{icono1} Cargar Datos", key="nav_p1", type=tipo_btn1, use_container_width=True):
                st.session_state.paso_actual = 1
                st.rerun()

            # Paso 2: Geocodificar
            disabled_p2 = st.session_state.df_servicios is None
            icono2 = '✅' if st.session_state.paso_actual > 2 else '2️⃣'
            tipo_btn2 = "primary" if st.session_state.paso_actual == 2 else "secondary"
            if st.button(f"{icono2} Geocodificar", key="nav_p2", type=tipo_btn2, disabled=disabled_p2, use_container_width=True):
                st.session_state.paso_actual = 2
                st.rerun()

            # Paso 3: Optimizar
            disabled_p3 = st.session_state.df_geocodificado is None
            icono3 = '✅' if st.session_state.paso_actual > 3 else '3️⃣'
            tipo_btn3 = "primary" if st.session_state.paso_actual == 3 else "secondary"
            if st.button(f"{icono3} Optimizar Rutas", key="nav_p3", type=tipo_btn3, disabled=disabled_p3, use_container_width=True):
                st.session_state.paso_actual = 3
                st.rerun()

            # Paso 4: Enviar
            disabled_p4 = st.session_state.rutas_optimizadas is None
            icono4 = '✅' if st.session_state.paso_actual > 4 else '4️⃣'
            tipo_btn4 = "primary" if st.session_state.paso_actual >= 4 else "secondary"
            if st.button(f"{icono4} Enviar Rutas", key="nav_p4", type=tipo_btn4, disabled=disabled_p4, use_container_width=True):
                st.session_state.paso_actual = 4
                st.rerun()
            
            st.divider()
            
            # Panel de estadísticas rápido
            if st.session_state.df_servicios is not None:
                st.caption(f"📦 Servicios cargados: {len(st.session_state.df_servicios)}")
            
            st.divider()
            
            # Botón de Reset
            if st.button("🔄 Reiniciar Todo", type="primary", use_container_width=True):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.session_state.paso_actual = 1
                st.rerun()
    
    def paso_1_cargar_datos(self):
        st.header("📥 PASO 1: CARGAR DATOS")
        tab1, tab2 = st.tabs(["📋 Servicios del Día", "👥 Gestión de Conductores"])
uploaded_conductores = st.file_uploader("Subir Excel de conductores", type=['xlsx', 'xls'], key="upload_conductores")
            if uploaded_conductores:
                try:
                    with st.spinner("Cargando conductores..."):
                        conductores_df = self.conductor_manager.cargar_desde_excel(uploaded_conductores)
                        st.session_state.df_conductores = conductores_df # <--- LÍNEA NUEVA IMPORTANTE
                        st.session_state.conductores_cargados = True
                        st.success(f"✅ {len(conductores_df)} conductores cargados")
                        st.dataframe(conductores_df, use_container_width=True)
        
        with tab1:
            uploaded_file = st.file_uploader("Seleccionar archivo Excel", type=['xlsx', 'xls'], key="upload_servicios")
            if uploaded_file:
                try:
                    with st.spinner("Procesando archivo..."):
                        df = self.excel_processor.procesar_excel_servicios(uploaded_file)
                        st.session_state.df_servicios = df
                        st.session_state.paso_actual = max(st.session_state.paso_actual, 2)
                        st.success(f"✅ Archivo cargado: {len(df)} servicios")
                        with st.expander("👁️ VER DATOS CARGADOS", expanded=True):
                            st.dataframe(df, use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Error al procesar el archivo: {str(e)}")
            
            st.download_button(
                label="📋 Descargar Plantilla Servicios",
                data=self.excel_processor.generar_plantilla_servicios(),
                file_name="plantilla_servicios.xlsx"
            )
        
        with tab2:
            uploaded_conductores = st.file_uploader("Subir Excel de conductores", type=['xlsx', 'xls'], key="upload_conductores")
            if uploaded_conductores:
                try:
                    with st.spinner("Cargando conductores..."):
                        conductores_df = self.conductor_manager.cargar_desde_excel(uploaded_conductores)
                        st.session_state.conductores_cargados = True
                        st.success(f"✅ {len(conductores_df)} conductores cargados")
                        st.dataframe(conductores_df, use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Error al cargar conductores: {str(e)}")

    def paso_2_geocodificar(self):
        st.header("🗺️ PASO 2: GEOCODIFICAR DIRECCIONES")
        
        if st.session_state.df_servicios is None:
            st.warning("⚠️ Primero carga los datos en el Paso 1")
            return
        
        st.info("El sistema convertirá las direcciones en coordenadas GPS para optimizar las rutas.")
        
        if st.button("📍 Iniciar Geocodificación", type="primary"):
            with st.spinner("Geocodificando direcciones..."):
                df_geo = self.geocoder.procesar_dataframe(
                    st.session_state.df_servicios,
                    progress_callback=lambda pct, msg: None # Simplificado
                )
                
                st.session_state.df_geocodificado = df_geo
                st.session_state.paso_actual = 3
                st.rerun()
                
   def paso_3_optimizar(self):
        st.header("🔄 PASO 3: OPTIMIZAR RUTAS VRP")
        
        if st.session_state.df_geocodificado is None:
            st.warning("⚠️ Primero geocodifica las direcciones")
            return
            
        st.subheader("👨‍✈️ Asignación de Conductores")
        
        # 1. Selector de Conductores
        if hasattr(st.session_state, 'df_conductores') and st.session_state.df_conductores is not None:
            # Buscar la columna que contenga el nombre (suele ser 'nombre' o 'Nombre')
            col_nombre = [c for c in st.session_state.df_conductores.columns if 'nombre' in c.lower() or 'conductor' in c.lower()]
            lista_nombres = st.session_state.df_conductores[col_nombre[0]].tolist() if col_nombre else [f"Conductor {i+1}" for i in range(len(st.session_state.df_conductores))]
            
            # Quitar nulos
            lista_nombres = [str(n) for n in lista_nombres if str(n).strip() != 'nan']
            
            conductores_activos = st.multiselect(
                "Selecciona los conductores que trabajarán mañana:",
                options=lista_nombres,
                default=lista_nombres, # Por defecto todos marcados
                help="Desmarca a los que estén de vacaciones o de baja."
            )
            vehiculos = len(conductores_activos)
        else:
            st.warning("No has subido el Excel de Conductores. Usando asignación genérica.")
            vehiculos = st.number_input("Número de Vehículos", min_value=1, value=5)
            conductores_activos = None

        st.info(f"🚚 Se van a optimizar rutas para **{vehiculos}** conductores activos.")

        # 2. Botón de Ejecutar
        if st.button("🚀 EJECUTAR OPTIMIZACIÓN", type="primary", use_container_width=True):
            if vehiculos == 0:
                st.error("❌ Debes seleccionar al menos un conductor.")
                return
                
            with st.spinner("Calculando rutas óptimas..."):
                # Le pasamos tanto el número como los nombres al optimizador
                self.optimizer.configurar(vehiculos_c=vehiculos, nombres_conductores=conductores_activos)
                
                rutas = self.optimizer.optimizar(st.session_state.df_geocodificado)
                
                if rutas:
                    st.session_state.rutas_optimizadas = rutas
                    st.session_state.paso_actual = 4
                    st.success(f"✅ Rutas generadas correctamente para {len(rutas)} conductores")
                    self.mostrar_resumen_optimizacion(rutas)
                    self.mostrar_rutas_detalladas(rutas)
                else:
                    st.error("❌ No se pudieron generar rutas.")

    def mostrar_resumen_optimizacion(self, rutas):
        st.subheader("📊 RESUMEN")
        cols = st.columns(len(rutas))
        for i, (vehiculo, datos) in enumerate(rutas.items()):
            stats = datos['estadisticas']
            with cols[i % len(cols)]:
                st.metric(vehiculo, f"{stats['num_servicios']} servicios", f"{stats['distancia_total_km']:.1f} km")

    def mostrar_rutas_detalladas(self, rutas):
        for vehiculo, ruta in rutas.items():
            with st.expander(f"🚚 {vehiculo}", expanded=False):
                st.dataframe(pd.DataFrame(ruta['servicios']), use_container_width=True)
                self.boton_whatsapp_ruta(vehiculo, ruta)

    def boton_whatsapp_ruta(self, vehiculo, ruta):
        col1, col2 = st.columns([3, 1])
        with col1:
            mensaje = self.whatsapp.generar_mensaje_ruta(vehiculo, ruta)
            st.text_area("Mensaje", mensaje, height=100, key=f"txt_{vehiculo}")
        with col2:
            enlace = self.whatsapp.generar_enlace_whatsapp(mensaje)
            st.link_button("📤 Enviar", enlace)

    def paso_4_enviar(self):
        st.header("📱 PASO 4: ENVIAR A CONDUCTORES")
        if st.session_state.rutas_optimizadas:
            for v, r in st.session_state.rutas_optimizadas.items():
                self.boton_whatsapp_ruta(v, r)

    def panel_exportacion(self):
        st.header("💾 EXPORTAR RESULTADOS")
        if not st.session_state.rutas_optimizadas: return
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            excel_data = self.optimizer.exportar_excel(st.session_state.rutas_optimizadas, None)
            st.download_button("📊 Excel", excel_data, "rutas.xlsx")
            
        with col4:
            # BOTÓN MY MAPS
            csv_data = "Name,Description,Latitude,Longitude\n"
            for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
                for i, s in enumerate(ruta['servicios']):
                    if 'lat' in s:
                        nombre = f"{vehiculo} - {i}. {s.get('Concepto', 'Punto')}".replace(',', ' ')
                        desc = f"{s.get('Direccion', '')} - {s.get('Hora Pide', '')}".replace(',', ' ')
                        csv_data += f"{nombre},{desc},{s['lat']},{s['lon']}\n"
            
            st.download_button("🗺️ CSV My Maps", csv_data, "mymaps.csv", "text/csv")

    def run(self):
        self.mostrar_header()
        self.mostrar_sidebar()
        
        if st.session_state.paso_actual == 1:
            self.paso_1_cargar_datos()
        elif st.session_state.paso_actual == 2:
            self.paso_2_geocodificar()
        elif st.session_state.paso_actual == 3:
            self.paso_3_optimizar()
        elif st.session_state.paso_actual >= 4:
            self.paso_4_enviar()
            self.panel_exportacion()

# ============================================================================
# MAIN
# ============================================================================

def main():
    if not MODULES_AVAILABLE:
        st.error("Instala las librerías: pip install -r requirements.txt")
        return
        
    try:
        app = OptimizadorVRPApp()
        app.run()
    except Exception as e:
        st.error(f"❌ Error crítico: {str(e)}")

if __name__ == "__main__":
    main()