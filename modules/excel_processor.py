"""
Procesamiento de archivos Excel para servicios y conductores
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
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
            self.config = None
    
    def procesar_excel_servicios(self, file_buffer, sheet_name: str = None) -> pd.DataFrame:
        """Procesar archivo Excel de servicios"""
        try:
            # Leer Excel
            if sheet_name:
                df = pd.read_excel(file_buffer, sheet_name=sheet_name)
            else:
                xls = pd.ExcelFile(file_buffer)
                df = pd.read_excel(file_buffer, sheet_name=xls.sheet_names[0])
            
            # Guardar original
            df_original = df.copy()
            
            # Normalizar y limpiar
            df = self._normalizar_columnas(df)
            df = self._asegurar_columnas_minimas(df)
            df = self._limpiar_datos(df)
            df = self._añadir_columnas_calculadas(df)
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error procesando Excel: {str(e)}")
            raise
    
    def _normalizar_columnas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizar nombres de columnas"""
        mapeo_columnas = {
            'cliente': 'Cliente', 'nombre cliente': 'Cliente',
            'contacto': 'Contacto', 'telefono': 'Telefono', 'teléfono': 'Telefono',
            'direccion': 'Direccion', 'dirección': 'Direccion',
            'poblacion': 'Poblacion', 'población': 'Poblacion',
            'hora': 'Hora Pide', 'hora pide': 'Hora Pide',
            'material': 'Material', 'tipo': 'Material',
            'concepto': 'Concepto', 'concept': 'Concepto',
            'conductor': 'Conductor', 'driver': 'Conductor',
            'observaciones': 'Observaciones'
        }
        
        df_normalizado = df.copy()
        df_normalizado.columns = [str(col).strip() for col in df_normalizado.columns]
        
        nuevas_columnas = []
        for col in df_normalizado.columns:
            col_lower = col.lower()
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
        
        for col in df.columns:
            df[col] = df[col].replace(['nan', 'None', 'NULL', ''], np.nan)
            
        if 'Telefono' in df.columns:
            df['Telefono'] = df['Telefono'].astype(str).str.replace(r'[^0-9+]', '', regex=True)
            
        if 'Hora Pide' in df.columns:
            df['Hora Pide'] = df['Hora Pide'].apply(self._formatear_hora)
            
        return df.dropna(subset=['Direccion'])
    
    def _formatear_hora(self, val):
        """Formatear hora a HH:MM"""
        val = str(val).strip()
        if not val or val.lower() == 'nan': return '09:00'
        
        if val.replace('.', '').isdigit() and '.' in val:
            try:
                h = float(val)
                hours = int(h)
                minutes = int((h - hours) * 60)
                return f"{hours:02d}:{minutes:02d}"
            except: pass
            
        if val.isdigit() and len(val) in [3, 4]:
            val = val.zfill(4)
            return f"{val[:2]}:{val[2:]}"
            
        return val if ':' in val else '09:00'
    
    def _añadir_columnas_calculadas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añadir columnas lógicas"""
        # Generar ID único (convertido a string para evitar error 'int object')
        df['id_servicio'] = df.apply(
            lambda x: f"SERV_{str(x.name).zfill(4)}_{str(hash(str(x.get('Cliente', '')) + str(x.get('Direccion', ''))))[-8:]}",
            axis=1
        )
        
        df['prioridad'] = 2
        
        # Detectar tipo de servicio usando la nueva lógica
        df['tipo_servicio'] = df.apply(self._inferir_tipo_servicio, axis=1)
        
        # Detectar combos por columnas antiguas (backup)
        if 'Caja Depos' in df.columns and 'Caja Retir' in df.columns:
            df['es_combo'] = df.apply(
                lambda x: str(x.get('Caja Depos')).lower() in ['si', 'yes', '1'] and 
                          str(x.get('Caja Retir')).lower() in ['si', 'yes', '1'], 
                axis=1
            )
        else:
            df['es_combo'] = False
            
        return df

    def _inferir_tipo_servicio(self, fila) -> str:
        """Inferir tipo de servicio con lógica de CAMBIO y SUMINISTRO mejorada"""
        # Obtener valores limpiando nulos
        material = str(fila.get('Material', '')).upper()
        concepto = str(fila.get('Concepto', '')).upper()
        texto_completo = f"{material} {concepto}"
        
        if 'nan' in texto_completo.lower(): texto_completo = texto_completo.replace('nan', '')

        # 1. Detección de SUMINISTRO (Áridos)
        if 'SUMINISTRO' in texto_completo or 'ARIDO' in texto_completo or 'ÁRIDO' in texto_completo:
            return 'SUMINISTRO'

        # 2. Detección explícita de CAMBIO
        if 'CAMBIO' in texto_completo:
            return 'CAMBIO'
        
        # 3. Detección por columnas de cajas (Si marca SÍ en ambas)
        caja_depos = str(fila.get('Caja Depos', '')).upper()
        caja_retir = str(fila.get('Caja Retir', '')).upper()
        
        if caja_depos in ['SÍ', 'SI', '1', 'TRUE'] and caja_retir in ['SÍ', 'SI', '1', 'TRUE']:
            return 'CAMBIO'
            
        # 4. Resto de tipos
        if 'RETIRADA' in texto_completo or 'RECOGIDA' in texto_completo:
            return 'RETIRADA'
        elif 'DEPOSITO' in texto_completo or 'DEPÓSITO' in texto_completo or 'ENTREGA' in texto_completo:
            return 'DEPOSITO'
        else:
            # Por defecto
            return 'RETIRADA'

    def procesar_excel_conductores(self, file_buffer) -> pd.DataFrame:
        """Procesar excel de conductores"""
        try:
            df = pd.read_excel(file_buffer)
            df.columns = [str(c).lower() for c in df.columns]
            
            # Generar ID (convertido a string)
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
        try:
            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                self._escribir_plantilla(writer)
        except:
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                self._escribir_plantilla(writer)
        return buffer.getvalue()

    def _escribir_plantilla(self, writer):
        df = pd.DataFrame({
            'Cliente': ['Cliente A', 'Cliente B'],
            'Direccion': ['Calle Mayor 1, Madrid', 'Paseo Castellana 100, Madrid'],
            'Material': ['RETIRADA', 'DEPOSITO'],
            'Concepto': ['Suministro de arido', 'Cambio de caja'],
            'Hora Pide': ['09:00', '11:30'],
            'Telefono': ['600123456', '600999888']
        })
        df.to_excel(writer, sheet_name='Servicios', index=False)

    def generar_plantilla_conductores(self) -> bytes:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df = pd.DataFrame({
                'Nombre': ['Juan Perez'],
                'Telefono': ['600111222'],
                'Vehiculo': ['1234-BBB'],
                'Etiqueta_C': ['SI'],
                'Capacidad_m3': [6]
            })
            df.to_excel(writer, sheet_name='Conductores', index=False)
        return buffer.getvalue()