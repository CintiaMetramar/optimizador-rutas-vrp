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
        from config import Config
        self.config = Config
    
    def procesar_excel_servicios(self, file_buffer, 
                               sheet_name: str = None) -> pd.DataFrame:
        """
        Procesar archivo Excel de servicios
        
        Args:
            file_buffer: Archivo o buffer del Excel
            sheet_name: Nombre de la hoja (opcional)
        
        Returns:
            DataFrame procesado
        """
        
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
                    
                    # Verificar si tiene columnas esperadas
                    columnas_df = [str(col).strip() for col in df_temp.columns]
                    columnas_esperadas = [col.strip() for col in self.config.COLUMNAS_SERVICIOS[:5]]
                    
                    # Verificar coincidencias
                    coincidencias = sum(1 for col in columnas_esperadas if any(col in c for c in columnas_df))
                    
                    if coincidencias >= 2:  # Al menos 2 columnas coinciden
                        df = pd.read_excel(file_buffer, sheet_name=sheet)
                        break
                else:
                    # Si no se encuentra, usar la primera hoja
                    df = pd.read_excel(file_buffer, sheet_name=sheet_names[0])
            
            # Guardar original para referencia
            df_original = df.copy()
            
            # Normalizar nombres de columnas
            df = self._normalizar_columnas(df)
            
            # Asegurar columnas mínimas
            df = self._asegurar_columnas_minimas(df)
            
            # Limpiar datos
            df = self._limpiar_datos(df)
            
            # Añadir columnas calculadas
            df = self._añadir_columnas_calculadas(df)
            
            # Guardar metadatos
            df.attrs['original_columns'] = list(df_original.columns)
            df.attrs['processing_date'] = datetime.now().isoformat()
            df.attrs['row_count'] = len(df)
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error procesando Excel: {str(e)}")
            raise
    
    def _normalizar_columnas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizar nombres de columnas"""
        
        # Mapeo de columnas comunes
        mapeo_columnas = {
            # Columnas de cliente
            'cliente': 'Cliente',
            'nombre cliente': 'Cliente',
            'client': 'Cliente',
            'cliente (2)': 'Cliente (2)',
            'cliente2': 'Cliente (2)',
            'cliente (3)': 'Cliente (3)',
            'cliente3': 'Cliente (3)',
            
            # Columnas de contacto
            'contacto': 'Contacto',
            'teléfono': 'Telefono',
            'telefono': 'Telefono',
            'phone': 'Telefono',
            'movil': 'Telefono',
            'móvil': 'Telefono',
            
            # Columnas de dirección
            'dirección': 'Direccion',
            'direccion': 'Direccion',
            'address': 'Direccion',
            'dir': 'Direccion',
            'población': 'Poblacion',
            'poblacion': 'Poblacion',
            'city': 'Poblacion',
            'ciudad': 'Poblacion',
            
            # Columnas de horario
            'hora': 'Hora Pide',
            'hora pide': 'Hora Pide',
            'horario': 'Hora Pide',
            'time': 'Hora Pide',
            'hora condu': 'Hora Condu',
            'hora llam': 'Hora Llam',
            
            # Columnas de servicio
            'material': 'Material',
            'tipo': 'Material',
            'type': 'Material',
            'concepto': 'Concepto',
            'concept': 'Concepto',
            'caja depos': 'Caja Depos',
            'caja_depos': 'Caja Depos',
            'caja retir': 'Caja Retir',
            'caja_retir': 'Caja Retir',
            'cantidad': 'Cantidad',
            'qty': 'Cantidad',
            
            # Columnas financieras
            'precio': 'Precio',
            'price': 'Precio',
            'cobrado': 'Cobrado',
            'paid': 'Cobrado',
            'a cuenta': 'A Cuenta',
            'iva': 'Iva',
            'vat': 'Iva',
            
            # Columnas de conductor
            'conductor': 'Conductor',
            'driver': 'Conductor',
            'operario': 'Conductor',
            
            # Columnas de observaciones
            'observaciones': 'Observaciones',
            'notes': 'Observaciones',
            'comentarios': 'Observaciones',
            'observacionescobro': 'ObservacionesCobro',
            'notas cobro': 'ObservacionesCobro',
            
            # Otras columnas
            'fecha': 'Fecha',
            'date': 'Fecha',
            'aclaración': 'Aclaracion',
            'aclaracion': 'Aclaracion',
            'clarification': 'Aclaracion'
        }
        
        # Crear nuevo DataFrame con columnas normalizadas
        df_normalizado = df.copy()
        df_normalizado.columns = [str(col).strip() for col in df_normalizado.columns]
        
        # Aplicar mapeo
        nuevas_columnas = []
        for col in df_normalizado.columns:
            col_lower = col.lower()
            if col_lower in mapeo_columnas:
                nuevas_columnas.append(mapeo_columnas[col_lower])
            else:
                nuevas_columnas.append(col)
        
        df_normalizado.columns = nuevas_columnas
        
        return df_normalizado
    
    def _asegurar_columnas_minimas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Asegurar que existen las columnas mínimas requeridas"""
        
        columnas_requeridas = ['Cliente', 'Direccion', 'Material']
        
        for col in columnas_requeridas:
            if col not in df.columns:
                df[col] = None
        
        # Asegurar columnas de geocodificación
        if 'Poblacion' not in df.columns:
            df['Poblacion'] = 'Madrid'
        
        # Asegurar columnas de horario
        if 'Hora Pide' not in df.columns:
            df['Hora Pide'] = '09:00'
        
        # Asegurar columnas de conductor
        if 'Conductor' not in df.columns:
            df['Conductor'] = 'Por asignar'
        
        return df
    
    def _limpiar_datos(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpiar y estandarizar datos"""
        
        # Convertir todas las columnas a string para limpieza
        df = df.astype(str)
        
        # Limpiar cada columna según su tipo
        for col in df.columns:
            if col in ['Cliente', 'Contacto', 'Conductor', 'Poblacion', 'Aclaracion']:
                # Texto: eliminar espacios extra, mantener mayúsculas
                df[col] = df[col].str.strip()
                df[col] = df[col].replace(['nan', 'None', 'NULL', ''], np.nan)
            
            elif col in ['Telefono']:
                # Teléfono: mantener solo dígitos y +
                df[col] = df[col].str.replace(r'[^0-9+]', '', regex=True)
                df[col] = df[col].replace(['', 'nan', 'None'], np.nan)
            
            elif col in ['Direccion']:
                # Dirección: normalizar espacios y comas
                df[col] = df[col].str.replace(r'\s+', ' ', regex=True)
                df[col] = df[col].str.strip()
                df[col] = df[col].replace(['nan', 'None', ''], np.nan)
            
            elif col in ['Hora Pide', 'Hora Condu', 'Hora Llam']:
                # Horas: formatear a HH:MM
                df[col] = df[col].apply(self._formatear_hora)
            
            elif col in ['Material', 'Concepto']:
                # Texto: normalizar a mayúsculas
                df[col] = df[col].str.upper().str.strip()
                df[col] = df[col].replace(['NAN', 'NONE', ''], np.nan)
            
            elif col in ['Cantidad', 'Precio', 'Cobrado', 'A Cuenta', 'Iva']:
                # Números: convertir a float
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            elif col in ['Caja Depos', 'Caja Retir']:
                # Booleanos/Textos: normalizar
                df[col] = df[col].str.upper().str.strip()
                df[col] = df[col].replace(['SI', 'YES', 'TRUE', '1'], 'Sí')
                df[col] = df[col].replace(['NO', 'FALSE', '0'], 'No')
                df[col] = df[col].replace(['NAN', 'NONE', ''], np.nan)
        
        # Eliminar filas completamente vacías
        columnas_importantes = ['Cliente', 'Direccion', 'Material']
        mask = df[columnas_importantes].isna().all(axis=1)
        df = df[~mask].copy()
        
        # Resetear índice
        df = df.reset_index(drop=True)
        
        return df
    
    def _formatear_hora(self, hora_str: str) -> str:
        """Formatear string de hora a formato HH:MM"""
        if pd.isna(hora_str) or str(hora_str).lower() in ['nan', 'none', '']:
            return '09:00'
        
        try:
            # Intentar diferentes formatos
            hora_str = str(hora_str).strip()
            
            # Si ya está en formato HH:MM
            if ':' in hora_str:
                parts = hora_str.split(':')
                if len(parts) >= 2:
                    horas = parts[0].zfill(2)
                    minutos = parts[1][:2].zfill(2)
                    return f"{horas}:{minutos}"
            
            # Si es un número
            elif hora_str.replace('.', '').isdigit():
                # Interpretar como horas decimales
                horas_decimal = float(hora_str)
                horas = int(horas_decimal)
                minutos = int((horas_decimal - horas) * 60)
                return f"{horas:02d}:{minutos:02d}"
            
            # Si está en formato HHMM
            elif hora_str.isdigit() and len(hora_str) == 4:
                return f"{hora_str[:2]}:{hora_str[2:]}"
            
        except:
            pass
        
        return '09:00'
    
    def _añadir_columnas_calculadas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añadir columnas calculadas basadas en los datos"""
        
        # Inferir tipo de servicio basado en Material
        df['tipo_servicio'] = df.apply(self._inferir_tipo_servicio, axis=1)
        
        # Extraer fecha si existe
        if 'Fecha' in df.columns:
            df['fecha_servicio'] = pd.to_datetime(df['Fecha'], errors='coerce')
        else:
            df['fecha_servicio'] = datetime.now()
        
        # Crear ID único para cada servicio
        df['id_servicio'] = df.apply(
            lambda x: f"SERV_{x.name:04d}_{hash(str(x.get('Cliente', '')) + str(x.get('Direccion', '')))[:8]}",
            axis=1
        )
        
        # Calcular prioridad basada en horario y tipo
        df['prioridad'] = df.apply(self._calcular_prioridad, axis=1)
        
        # Determinar si es combo (depósito + retirada)
        df['es_combo'] = df.apply(
            lambda x: (
                str(x.get('Caja Depos', '')).upper() == 'SÍ' and 
                str(x.get('Caja Retir', '')).upper() == 'SÍ'
            ),
            axis=1
        )
        
        return df
    
    def _inferir_tipo_servicio(self, fila) -> str:
        """Inferir tipo de servicio basado en columnas"""
        material = str(fila.get('Material', '')).lower()
        
        if 'retirada' in material:
            return 'RETIRADA'
        elif 'deposito' in material or 'depósito' in material:
            return 'DEPOSITO'
        elif 'cambio' in material:
            return 'CAMBIO'
        elif 'recolección' in material or 'recogida' in material:
            return 'RECOGIDA'
        elif 'entrega' in material:
            return 'ENTREGA'
        else:
            # Intentar inferir de otras columnas
            caja_depos = str(fila.get('Caja Depos', '')).upper()
            caja_retir = str(fila.get('Caja Retir', '')).upper()
            
            if caja_depos == 'SÍ' and caja_retir == 'SÍ':
                return 'COMBO'
            elif caja_depos == 'SÍ':
                return 'DEPOSITO'
            elif caja_retir == 'SÍ':
                return 'RETIRADA'
            else:
                return 'SERVICIO_GENERAL'
    
    def _calcular_prioridad(self, fila) -> int:
        """Calcular prioridad del servicio (1=alta, 3=baja)"""
        
        prioridad = 2  # Media por defecto
        
        # Horario temprano = alta prioridad
        hora_str = str(fila.get('Hora Pide', '09:00'))
        try:
            hora = int(hora_str.split(':')[0])
            if hora < 10:
                prioridad = 1  # Alta
            elif hora > 16:
                prioridad = 3  # Baja
        except:
            pass
        
        # Tipo de servicio afecta prioridad
        tipo = str(fila.get('tipo_servicio', '')).upper()
        if tipo in ['RETIRADA', 'COMBO']:
            prioridad = min(prioridad, 2)  # Al menos media
        
        # Si tiene observaciones importantes
        observaciones = str(fila.get('Observaciones', '')).lower()
        if any(word in observaciones for word in ['urgente', 'urgent', 'inmediat', 'priority']):
            prioridad = 1
        
        return prioridad
    
    def procesar_excel_conductores(self, file_buffer) -> pd.DataFrame:
        """Procesar archivo Excel de conductores"""
        
        try:
            # Leer Excel
            df = pd.read_excel(file_buffer)
            
            # Normalizar columnas
            df.columns = [str(col).strip().lower() for col in df.columns]
            
            # Mapear columnas esperadas
            mapeo = {
                'nombre': 'Nombre',
                'conductor': 'Nombre',
                'driver': 'Nombre',
                'operario': 'Nombre',
                'teléfono': 'Telefono',
                'telefono': 'Telefono',
                'phone': 'Telefono',
                'whatsapp': 'Telefono',
                'vehículo': 'Vehiculo',
                'vehiculo': 'Vehiculo',
                'vehicle': 'Vehiculo',
                'matrícula': 'Vehiculo',
                'matricula': 'Vehiculo',
                'etiqueta_c': 'Etiqueta_C',
                'c': 'Etiqueta_C',
                'madrid_central': 'Etiqueta_C',
                'capacidad': 'Capacidad_m3',
                'capacidad_m3': 'Capacidad_m3',
                'volumen': 'Capacidad_m3',
                'activo': 'Activo',
                'active': 'Activo',
                'notas': 'Notas',
                'notes': 'Notas',
                'comentarios': 'Notas'
            }
            
            # Renombrar columnas
            nuevas_columnas = []
            for col in df.columns:
                if col in mapeo:
                    nuevas_columnas.append(mapeo[col])
                else:
                    nuevas_columnas.append(col.capitalize())
            
            df.columns = nuevas_columnas
            
            # Asegurar columnas requeridas
            columnas_requeridas = ['Nombre', 'Telefono', 'Etiqueta_C', 'Capacidad_m3']
            for col in columnas_requeridas:
                if col not in df.columns:
                    df[col] = None if col != 'Etiqueta_C' else False
                    if col == 'Capacidad_m3':
                        df[col] = 6  # Valor por defecto
            
            # Limpiar datos
            df = self._limpiar_datos_conductores(df)
            
            # Añadir columnas calculadas
            df['fecha_registro'] = datetime.now()
            df['id_conductor'] = df.apply(
                lambda x: f"COND_{hash(str(x.get('Nombre', '')))[:8]}",
                axis=1
            )
            
            return df
            
        except Exception as e:
            st.error(f"❌ Error procesando Excel de conductores: {str(e)}")
            raise
    
    def _limpiar_datos_conductores(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpiar datos de conductores"""
        
        # Limpiar nombres
        if 'Nombre' in df.columns:
            df['Nombre'] = df['Nombre'].astype(str).str.strip().str.title()
            df['Nombre'] = df['Nombre'].replace(['Nan', 'None', ''], np.nan)
        
        # Limpiar teléfonos
        if 'Telefono' in df.columns:
            df['Telefono'] = df['Telefono'].astype(str)
            df['Telefono'] = df['Telefono'].str.replace(r'[^0-9+]', '', regex=True)
            # Añadir +34 si no lo tiene y es español
            mask = df['Telefono'].str.len() == 9
            df.loc[mask, 'Telefono'] = '+34' + df.loc[mask, 'Telefono']
            df['Telefono'] = df['Telefono'].replace(['', 'nan'], np.nan)
        
        # Normalizar Etiqueta_C
        if 'Etiqueta_C' in df.columns:
            df['Etiqueta_C'] = df['Etiqueta_C'].astype(str).str.upper()
            df['Etiqueta_C'] = df['Etiqueta_C'].replace(['SI', 'YES', 'TRUE', '1', 'SÍ'], True)
            df['Etiqueta_C'] = df['Etiqueta_C'].replace(['NO', 'FALSE', '0'], False)
            df['Etiqueta_C'] = pd.to_numeric(df['Etiqueta_C'], errors='coerce').fillna(False).astype(bool)
        
        # Normalizar Capacidad_m3
        if 'Capacidad_m3' in df.columns:
            df['Capacidad_m3'] = pd.to_numeric(df['Capacidad_m3'], errors='coerce')
            df['Capacidad_m3'] = df['Capacidad_m3'].fillna(6)  # Valor por defecto
        
        # Normalizar Activo
        if 'Activo' in df.columns:
            df['Activo'] = df['Activo'].astype(str).str.upper()
            df['Activo'] = df['Activo'].replace(['SI', 'YES', 'TRUE', '1', 'SÍ'], True)
            df['Activo'] = df['Activo'].replace(['NO', 'FALSE', '0'], False)
            df['Activo'] = df['Activo'].fillna(True)  # Por defecto activo
        
        # Eliminar filas sin nombre
        if 'Nombre' in df.columns:
            df = df[df['Nombre'].notna()].copy()
        
        return df
    
    def generar_plantilla_servicios(self) -> bytes:
        """Generar plantilla Excel para servicios"""
        
        # Crear datos de ejemplo
        datos = {
            'Fecha': ['2024-01-15', '2024-01-15', '2024-01-15'],
            'Conductor': ['Juan Pérez', 'María García', 'Carlos López'],
            'Cliente': ['Empresa A', 'Empresa B', 'Empresa C'],
            'Cliente (2)': ['Contacto A', 'Contacto B', 'Contacto C'],
            'Contacto': ['Ana Martínez', 'Pedro Sánchez', 'Laura Gómez'],
            'Telefono': ['+34600123456', '+34600567890', '+34600987654'],
            'Direccion': ['Calle Gran Vía 123', 'Avenida de América 45', 'Paseo de la Castellana 89'],
            'Hora Pide': ['09:00', '11:30', '14:00'],
            'Poblacion': ['Madrid', 'Madrid', 'Madrid'],
            'Aclaracion': ['Entrar por patio', 'Llamar antes', 'Parking propio'],
            'Concepto': ['Servicio mensual', 'Servicio puntual', 'Contrato anual'],
            'Material': ['RETIRADA CONTENEDOR 6M3', 'DEPOSITO CONTENEDOR 6M3', 'CAMBIO CONTENEDOR'],
            'Observaciones': ['Urgente - cliente llama', 'Dejar factura', 'Necesita factura proforma'],
            'Precio': [150.00, 120.00, 180.00],
            'Cobrado': ['Sí', 'No', 'Parcial'],
            'Hora Condu': ['08:30', '10:45', '13:15'],
            'Hora Llam': ['08:45', '11:00', '13:30'],
            'Cliente (3)': ['Sede Central', 'Sede Norte', 'Sede Sur'],
            'Caja Depos': ['No', 'Sí', 'No'],
            'Cantidad': [1, 1, 1],
            'Caja Retir': ['Sí', 'No', 'Sí'],
            'A Cuenta': [0, 50, 100],
            'Iva': [21.0, 21.0, 21.0],
            'ObservacionesCobro': ['Pagado transferencia', 'Pendiente pago', 'Abonado 100€']
        }
        
        df = pd.DataFrame(datos)
        
        # Crear buffer para Excel
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Hoja 1: Datos de ejemplo
            df.to_excel(writer, sheet_name='Servicios_Ejemplo', index=False)
            
            # Hoja 2: Instrucciones
            instrucciones_data = []
            for col in self.config.COLUMNAS_SERVICIOS:
                desc = self._obtener_descripcion_columna(col)
                instrucciones_data.append({
                    'Columna': col,
                    'Descripción': desc['descripcion'],
                    'Requerido': desc['requerido'],
                    'Ejemplo': desc['ejemplo']
                })
            
            instrucciones_df = pd.DataFrame(instrucciones_data)
            instrucciones_df.to_excel(writer, sheet_name='Instrucciones', index=False)
            
            # Hoja 3: Tipos de servicio
            tipos_data = [
                {'Tipo': 'RETIRADA', 'Descripción': 'Recogida de contenedor lleno', 'Material Ejemplo': 'RETIRADA CONTENEDOR 6M3'},
                {'Tipo': 'DEPOSITO', 'Descripción': 'Dejar contenedor vacío', 'Material Ejemplo': 'DEPOSITO CONTENEDOR 6M3'},
                {'Tipo': 'CAMBIO', 'Descripción': 'Cambio de contenedor', 'Material Ejemplo': 'CAMBIO CONTENEDOR 6M3'},
                {'Tipo': 'COMBO', 'Descripción': 'Depósito + Retirada (Caja Depos=Sí y Caja Retir=Sí)', 'Material Ejemplo': 'SERVICIO COMPLETO'}
            ]
            
            tipos_df = pd.DataFrame(tipos_data)
            tipos_df.to_excel(writer, sheet_name='Tipos_Servicio', index=False)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _obtener_descripcion_columna(self, columna: str) -> Dict:
        """Obtener descripción de una columna"""
        
        descripciones = {
            'Fecha': {
                'descripcion': 'Fecha del servicio',
                'requerido': 'Recomendado',
                'ejemplo': '2024-01-15'
            },
            'Conductor': {
                'descripcion': 'Nombre del conductor asignado',
                'requerido': 'Recomendado',
                'ejemplo': 'Juan Pérez'
            },
            'Cliente': {
                'descripcion': 'Nombre del cliente',
                'requerido': 'OBLIGATORIO',
                'ejemplo': 'Empresa A'
            },
            'Direccion': {
                'descripcion': 'Dirección completa del servicio',
                'requerido': 'OBLIGATORIO',
                'ejemplo': 'Calle Gran Vía 123, Madrid'
            },
            'Hora Pide': {
                'descripcion': 'Hora solicitada por el cliente',
                'requerido': 'Recomendado',
                'ejemplo': '09:00 o 9.5 (9:30)'
            },
            'Poblacion': {
                'descripcion': 'Población/localidad',
                'requerido': 'Recomendado',
                'ejemplo': 'Madrid'
            },
            'Material': {
                'descripcion': 'Tipo de servicio y material',
                'requerido': 'OBLIGATORIO',
                'ejemplo': 'RETIRADA CONTENEDOR 6M3'
            },
            'Caja Depos': {
                'descripcion': 'Sí/No - Si se deja contenedor vacío',
                'requerido': 'Recomendado',
                'ejemplo': 'Sí o No'
            },
            'Caja Retir': {
                'descripcion': 'Sí/No - Si se retira contenedor lleno',
                'requerido': 'Recomendado',
                'ejemplo': 'Sí o No'
            },
            'Observaciones': {
                'descripcion': 'Notas importantes para el conductor',
                'requerido': 'Opcional',
                'ejemplo': 'Entrar por patio trasero'
            }
        }
        
        return descripciones.get(columna, {
            'descripcion': 'Columna adicional',
            'requerido': 'Opcional',
            'ejemplo': ''
        })
    
    def generar_plantilla_conductores(self) -> bytes:
        """Generar plantilla Excel para conductores"""
        
        # Crear datos de ejemplo
        datos = {
            'Nombre': ['Juan Pérez', 'María García', 'Carlos López', 'Ana Martínez'],
            'Telefono': ['+34600123456', '+34600567890', '+34600987654', '+34600453210'],
            'Vehiculo': ['1234ABC', '5678DEF', '9012GHI', '3456JKL'],
            'Etiqueta_C': [True, True, False, True],
            'Capacidad_m3': [6, 9, 3, 6],
            'Activo': [True, True, True, False],
            'Notas': ['Experiencia 5 años', 'Nuevo conductor', 'Solo retiradas', 'Vacaciones']
        }
        
        df = pd.DataFrame(datos)
        
        # Crear buffer para Excel
        buffer = io.BytesIO()
        
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Hoja 1: Datos de ejemplo
            df.to_excel(writer, sheet_name='Conductores_Ejemplo', index=False)
            
            # Hoja 2: Instrucciones
            instrucciones_data = []
            for col in self.config.COLUMNAS_CONDUCTORES:
                desc = self._obtener_descripcion_columna_conductor(col)
                instrucciones_data.append({
                    'Columna': col,
                    'Descripción': desc['descripcion'],
                    'Requerido': desc['requerido'],
                    'Ejemplo': desc['ejemplo']
                })
            
            instrucciones_df = pd.DataFrame(instrucciones_data)
            instrucciones_df.to_excel(writer, sheet_name='Instrucciones', index=False)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def _obtener_descripcion_columna_conductor(self, columna: str) -> Dict:
        """Obtener descripción de columna de conductor"""
        
        descripciones = {
            'Nombre': {
                'descripcion': 'Nombre completo del conductor',
                'requerido': 'OBLIGATORIO',
                'ejemplo': 'Juan Pérez'
            },
            'Telefono': {
                'descripcion': 'Teléfono para WhatsApp (con +34)',
                'requerido': 'OBLIGATORIO',
                'ejemplo': '+34600123456'
            },
            'Vehiculo': {
                'descripcion': 'Matrícula del vehículo asignado',
                'requerido': 'Recomendado',
                'ejemplo': '1234ABC'
            },
            'Etiqueta_C': {
                'descripcion': 'TRUE si puede entrar en Madrid Central',
                'requerido': 'OBLIGATORIO',
                'ejemplo': 'TRUE o FALSE'
            },
            'Capacidad_m3': {
                'descripcion': 'Capacidad del vehículo en metros cúbicos',
                'requerido': 'OBLIGATORIO',
                'ejemplo': '6 (para 6m³)'
            },
            'Activo': {
                'descripcion': 'TRUE si está activo, FALSE si no',
                'requerido': 'Recomendado',
                'ejemplo': 'TRUE'
            },
            'Notas': {
                'descripcion': 'Información adicional',
                'requerido': 'Opcional',
                'ejemplo': 'Experiencia 5 años'
            }
        }
        
        return descripciones.get(columna, {
            'descripcion': 'Columna adicional',
            'requerido': 'Opcional',
            'ejemplo': ''
        })
    
    def generar_reporte_servicios(self, df: pd.DataFrame) -> Dict:
        """Generar reporte de análisis de servicios"""
        
        reporte = {
            'general': {
                'total_servicios': len(df),
                'servicios_con_direccion': df['Direccion'].notna().sum(),
                'servicios_con_horario': df['Hora Pide'].notna().sum(),
                'servicios_con_conductor': df['Conductor'].notna().sum()
            },
            'por_tipo': {},
            'por_conductor': {},
            'por_horario': {},
            'problemas': []
        }
        
        # Análisis por tipo de servicio
        if 'tipo_servicio' in df.columns:
            tipos = df['tipo_servicio'].value_counts().to_dict()
            reporte['por_tipo'] = tipos
        
        # Análisis por conductor
        if 'Conductor' in df.columns:
            conductores = df['Conductor'].value_counts().head(10).to_dict()
            reporte['por_conductor'] = conductores
        
        # Análisis por horario
        if 'Hora Pide' in df.columns:
            # Agrupar por rangos horarios
            df['hora_grupo'] = df['Hora Pide'].apply(self._agrupar_horario)
            horarios = df['hora_grupo'].value_counts().to_dict()
            reporte['por_horario'] = horarios
        
        # Detectar problemas
        if 'geocodificado' in df.columns:
            no_geocodificados = df[df['geocodificado'] == False]
            if len(no_geocodificados) > 0:
                reporte['problemas'].append({
                    'tipo': 'geocodificacion',
                    'cantidad': len(no_geocodificados),
                    'ejemplos': no_geocodificados[['Cliente', 'Direccion']].head(3).to_dict('records')
                })
        
        # Servicios sin conductor asignado
        if 'Conductor' in df.columns:
            sin_conductor = df[df['Conductor'].isna() | (df['Conductor'] == 'Por asignar')]
            if len(sin_conductor) > 0:
                reporte['problemas'].append({
                    'tipo': 'sin_conductor',
                    'cantidad': len(sin_conductor),
                    'ejemplos': sin_conductor[['Cliente', 'Direccion']].head(3).to_dict('records')
                })
        
        return reporte
    
    def _agrupar_horario(self, hora_str: str) -> str:
        """Agrupar horario en rangos"""
        try:
            hora = int(hora_str.split(':')[0])
            if hora < 9:
                return '08:00-09:00'
            elif hora < 11:
                return '09:00-11:00'
            elif hora < 13:
                return '11:00-13:00'
            elif hora < 15:
                return '13:00-15:00'
            elif hora < 17:
                return '15:00-17:00'
            else:
                return '17:00+'
        except:
            return 'Sin horario'