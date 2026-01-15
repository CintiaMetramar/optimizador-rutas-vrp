"""
Gestión de conductores: carga desde Excel, almacenamiento, asignación
"""

import pandas as pd
import json
import os
from typing import Dict, List, Any
from datetime import datetime

class ConductorManager:
    def __init__(self, data_dir="data"):
        """Inicializar gestor de conductores"""
        self.data_dir = data_dir
        self.conductores_file = os.path.join(data_dir, "conductores.json")
        
        # Crear directorio si no existe
        os.makedirs(data_dir, exist_ok=True)
        
        # Cargar conductores existentes
        self.conductores = self.cargar_conductores()
    
    def cargar_desde_excel(self, file_path_or_buffer) -> pd.DataFrame:
        """Cargar conductores desde archivo Excel"""
        
        # Leer Excel
        df = pd.read_excel(file_path_or_buffer)
        
        # Normalizar nombres de columnas
        df.columns = [str(col).strip().lower().replace(' ', '_') for col in df.columns]
        
        # Columnas esperadas
        columnas_esperadas = {
            'nombre': ['nombre', 'conductor', 'nombre_conductor'],
            'telefono': ['telefono', 'teléfono', 'whatsapp', 'movil', 'móvil'],
            'vehiculo': ['vehiculo', 'vehículo', 'matricula', 'matrícula'],
            'etiqueta_c': ['etiqueta_c', 'c', 'madrid_central'],
            'capacidad_m3': ['capacidad', 'capacidad_m3', 'volumen']
        }
        
        # Mapear columnas
        columnas_mapeadas = {}
        for col_esperada, alternativas in columnas_esperadas.items():
            for alt in alternativas:
                if alt in df.columns:
                    columnas_mapeadas[col_esperada] = alt
                    break
        
        # Renombrar columnas
        df = df.rename(columns={v: k for k, v in columnas_mapeadas.items()})
        
        # Asegurar columnas mínimas
        if 'nombre' not in df.columns:
            raise ValueError("El Excel debe contener al menos una columna 'nombre' o 'conductor'")
        
        # Rellenar valores por defecto
        if 'etiqueta_c' not in df.columns:
            df['etiqueta_c'] = False
        
        if 'capacidad_m3' not in df.columns:
            df['capacidad_m3'] = 6  # Valor por defecto
        
        if 'telefono' in df.columns:
            # Limpiar números de teléfono
            df['telefono'] = df['telefono'].astype(str).str.replace(r'[^0-9+]', '', regex=True)
        
        # Guardar en memoria
        self.conductores = df.to_dict('records')
        
        return df
    
    def cargar_conductores(self) -> List[Dict]:
        """Cargar conductores desde archivo JSON"""
        if os.path.exists(self.conductores_file):
            try:
                with open(self.conductores_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def guardar_conductores(self, df: pd.DataFrame = None):
        """Guardar conductores en archivo JSON"""
        if df is not None:
            self.conductores = df.to_dict('records')
        
        with open(self.conductores_file, 'w', encoding='utf-8') as f:
            json.dump(self.conductores, f, ensure_ascii=False, indent=2)
    
    def agregar_conductor(self, conductor_data: Dict):
        """Agregar un nuevo conductor"""
        # Validar datos mínimos
        if 'nombre' not in conductor_data:
            raise ValueError("El conductor debe tener al menos un nombre")
        
        # Añadir timestamp
        conductor_data['fecha_creacion'] = datetime.now().isoformat()
        conductor_data['ultima_actualizacion'] = datetime.now().isoformat()
        
        # Agregar a la lista
        self.conductores.append(conductor_data)
        
        # Guardar
        self.guardar_conductores()
    
    def actualizar_conductor(self, nombre: str, nuevos_datos: Dict):
        """Actualizar datos de un conductor existente"""
        for i, conductor in enumerate(self.conductores):
            if conductor['nombre'] == nombre:
                # Actualizar datos
                nuevos_datos['ultima_actualizacion'] = datetime.now().isoformat()
                self.conductores[i].update(nuevos_datos)
                
                # Guardar
                self.guardar_conductores()
                return True
        
        return False
    
    def eliminar_conductor(self, nombre: str):
        """Eliminar un conductor"""
        self.conductores = [c for c in self.conductores if c['nombre'] != nombre]
        self.guardar_conductores()
    
    def buscar_conductor(self, nombre: str) -> Dict:
        """Buscar conductor por nombre"""
        for conductor in self.conductores:
            if conductor['nombre'] == nombre:
                return conductor
        return None
    
    def obtener_conductores_etiqueta_c(self) -> List[Dict]:
        """Obtener conductores con vehículos etiqueta C"""
        return [c for c in self.conductores if c.get('etiqueta_c', False)]
    
    def obtener_conductores_por_capacidad(self, capacidad_min: int = 0) -> List[Dict]:
        """Obtener conductores con capacidad mínima"""
        return [c for c in self.conductores if c.get('capacidad_m3', 0) >= capacidad_min]
    
    def asignar_conductor_a_ruta(self, ruta_data: Dict) -> Dict:
        """Asignar conductor óptimo a una ruta"""
        
        if not self.conductores:
            return ruta_data
        
        # Requisitos de la ruta
        requiere_etiqueta_c = ruta_data.get('requiere_etiqueta_c', False)
        capacidad_necesaria = ruta_data.get('capacidad_necesaria', 6)
        num_servicios = len(ruta_data.get('servicios', []))
        
        # Filtrar conductores disponibles
        candidatos = self.conductores.copy()
        
        if requiere_etiqueta_c:
            candidatos = [c for c in candidatos if c.get('etiqueta_c', False)]
        
        candidatos = [c for c in candidatos if c.get('capacidad_m3', 0) >= capacidad_necesaria]
        
        if not candidatos:
            # Si no hay candidatos, usar cualquier conductor
            candidatos = self.conductores
        
        # Seleccionar conductor (por ahora el primero disponible)
        if candidatos:
            conductor = candidatos[0]
            ruta_data['conductor'] = conductor['nombre']
            ruta_data['telefono_conductor'] = conductor.get('telefono', '')
            ruta_data['vehiculo_asignado'] = conductor.get('vehiculo', '')
        
        return ruta_data
    
    def generar_reporte_conductores(self) -> pd.DataFrame:
        """Generar reporte de conductores"""
        df = pd.DataFrame(self.conductores)
        
        if not df.empty:
            # Calcular estadísticas
            total_conductores = len(df)
            con_etiqueta_c = df['etiqueta_c'].sum() if 'etiqueta_c' in df.columns else 0
            capacidad_promedio = df['capacidad_m3'].mean() if 'capacidad_m3' in df.columns else 0
        
        return df
