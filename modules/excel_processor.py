"""
Procesamiento de archivos Excel para servicios y conductores
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import io
from datetime import datetime
import streamlit as st

class ExcelProcessor:
    """Procesador de archivos Excel para la aplicación"""
    
    def __init__(self):
        # Importación diferida para evitar ciclos
        try:
            from config import Config
            self.config = Config
        except ImportError:
            # Fallback si no encuentra config (para pruebas)
            self.config = None
    
    def procesar_excel_servicios(self, file_buffer, sheet_name: str = None) -> pd.DataFrame:
        """Procesar archivo Excel de servicios"""
        try:
            # Leer Excel
            if sheet_name:
                df = pd.read_excel(file_buffer, sheet_name=sheet_name)
            else:
                # Intentar detectar la hoja correcta
                xls = pd.ExcelFile(file_buffer)
                sheet_names = xls.sheet_names
                
                # Buscar hoja con datos (no vacía y con columnas conocidas)
                for sheet in sheet_names:
                    df_temp = pd.read_excel(file_buffer, sheet_name=sheet, nrows=5)
                    # Verificar si tiene columnas esperadas (si config está disponible)
                    if self.config:
                        columnas_df = [str(col).strip() for col in df_temp.columns]
                        columnas_esperadas = [col.strip() for col in self.config.COLUMNAS_SERVICIOS[:5]]
                        coincidencias = sum(1 for col in columnas_esperadas if any(col in c for c in columnas_df))
                        if coincidencias >= 2:
                            df = pd.read_excel(file_buffer, sheet_name=sheet)
                            break
                else:
                    df = pd.read_excel(file_buffer, sheet_name=sheet_names[0])
            
            # Guardar original
            df_original = df.copy()
            
            # Normalizar y limpiar
            df = self._normalizar_columnas(df)
            df = self._asegurar_columnas_minimas(df)
            df = self._limpiar_datos(df)
            df = self._añadir_columnas_calculadas(df)
            
            # Metadatos
            df.attrs['original_columns'] = list(df_original.columns)
            df.attrs['processing_date'] = datetime.now().isoformat()
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error procesando Excel: {str(e)}")
            raise
    
    def _normalizar_columnas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizar nombres de columnas"""
        # Mapeo de columnas comunes
        mapeo_columnas = {
            'cliente': 'Cliente', 'nombre cliente': 'Cliente', 'client': 'Cliente',
            'contacto': 'Contacto', 'telefono': 'Telefono', 'teléfono': 'Telefono', 'phone': 'Telefono',
            'direccion': 'Direccion', 'dirección': 'Direccion', 'address': 'Direccion',
            'poblacion': 'Poblacion', 'población': 'Poblacion', 'city': 'Poblacion',
            'hora': 'Hora Pide', 'hora pide': 'Hora Pide', 'horario': 'Hora Pide',
            'material': 'Material', 'tipo': 'Material', 'servicio': 'Material',
            'conductor': 'Conductor', 'driver': 'Conductor', 'chofer': 'Conductor',
            'observaciones': 'Observaciones', 'notas': 'Observaciones'
        }
        
        df_normalizado = df.copy()
        # Convertir columnas a string y limpiar espacios
        df_normalizado.columns = [str(col).strip() for col in df_normalizado.columns]
        
        nuevas_columnas = []
        for col in df_normalizado.columns:
            col_lower = col.lower()
            # Buscar coincidencia exacta o parcial
            encontrado = False
            for key, val in mapeo_columnas.items():
                if key == col_lower:
                    nuevas_columnas.append(val)
                    encontrado = True
                    break
            if not encontrado:
                nuevas_columnas.append(col)
        
        df_normalizado.columns = nuevas_columnas
        return df_normalizado
    
    def _asegurar_columnas_minimas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Asegurar columnas requeridas"""
        cols_minimas = ['Cliente', 'Direccion', 'Material', 'Hora Pide', 'Poblacion', 'Conductor']
        for col in cols_minimas:
            if col not in df.columns:
                df[col] = '' if col != 'Conductor' else 'Por asignar'
        return df
    
    def _limpiar_datos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpieza general de datos"""
        df = df.astype(str)
        
        # Limpiar 'nan', 'None'
        for col in df.columns:
            df[col] = df[col].replace(['nan', 'None', 'NULL', ''], np.nan)
            
        # Limpiar teléfonos
        if 'Telefono' in df.columns:
            df['Telefono'] = df['Telefono'].astype(str).str.replace(r'[^0-9+]', '', regex=True)
            
        # Formatear horas
        if 'Hora Pide' in df.columns:
            df['Hora Pide'] = df['Hora Pide'].apply(self._formatear_hora)
            
        return df.dropna(subset=['Direccion']) # Eliminar filas sin dirección
    
    def _formatear_hora(self, val):
        """Formatear hora a HH:MM"""
        val = str(val).strip()
        if not val or val.lower() == 'nan': return '09:00'
        
        # Si es formato decimal (9.5 -> 09:30)
        if val.replace('.', '').isdigit() and '.' in val:
            try:
                h = float(val)
                hours = int(h)
                minutes = int((h - hours) * 60)
                return f"{hours:02d}:{minutes:02d}"
            except: pass
            
        # Si es formato HHMM
        if val.isdigit() and len(val) in [3, 4]:
            val = val.zfill(4)
            return f"{val[:2]}:{val[2:]}"
            
        return val if ':' in val else '09:00'
    
    def _añadir_columnas_calculadas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añadir columnas lógicas"""
        
        # CORRECCIÓN AQUÍ: Convertir hash a string antes de recortar
        df['id_servicio'] = df.apply(
            lambda x: f"SERV_{str(x.name).zfill(4)}_{str(hash(str(x.get('Cliente', '')) + str(x.get('Direccion', ''))))[-8:]}",
            axis=1
        )
        
        # Prioridad básica
        df['prioridad'] = 2
        
        # Detectar combos (Depósito + Retirada)
        if 'Caja Depos' in df.columns and 'Caja Retir' in df.columns:
            df['es_combo'] = df.apply(
                lambda x: str(x.get('Caja Depos')).lower() in ['si', 'yes', '1'] and 
                          str(x.get('Caja Retir')).lower() in ['si', 'yes', '1'], 
                axis=1
            )
        else:
            df['es_combo'] = False
            
        return df

    def procesar_excel_conductores(self, file_buffer) -> pd.DataFrame:
        """Procesar excel de conductores (Backup)"""
        try:
            df = pd.read_excel(file_buffer)
            # Normalización simple
            df.columns = [str(c).lower() for c in df.columns]
            
            # CORRECCIÓN AQUÍ TAMBIÉN
            df['id_conductor'] = df.apply(
                lambda x: f"COND_{str(hash(str(x.get('nombre', 'unknown'))))[-8:]}",
                axis=1
            )
            return df
        except Exception as e:
            st.error(f"Error conductores: {e}")
            return pd.DataFrame()

    def generar_plantilla_servicios(self) -> bytes:
        """Generar Excel de ejemplo"""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df = pd.DataFrame({
                'Cliente': ['Cliente A', 'Cliente B'],
                'Direccion': ['Calle Mayor 1, Madrid', 'Paseo Castellana 100, Madrid'],
                'Material': ['RETIRADA', 'DEPOSITO'],
                'Hora Pide': ['09:00', '11:30'],
                'Telefono': ['600123456', '600999888']
            })
            df.to_excel(writer, sheet_name='Servicios', index=False)
        return buffer.getvalue()

    def generar_plantilla_conductores(self) -> bytes:
        """Generar Excel de conductores"""
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df = pd.DataFrame({
                'Nombre': ['Juan Perez', 'Maria Garcia'],
                'Telefono': ['600111222', '600333444'],
                'Vehiculo': ['1234-BBB', '5678-CCC'],
                'Etiqueta_C': ['SI', 'NO'],
                'Capacidad_m3': [6, 12]
            })
            df.to_excel(writer, sheet_name='Conductores', index=False)
        return buffer.getvalue()
            return 'Sin horario'
