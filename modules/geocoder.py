"""
Módulo de geocodificación usando OpenStreetMap Nominatim
"""

import requests
import time
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Callable
from datetime import datetime
import os
import streamlit as st
from geopy.distance import geodesic

class GeocodificadorOffline:
    """Geocodificador usando OpenStreetMap Nominatim (gratuito)"""
    
    def __init__(self, cache_file: str = None):
        from config import Config
        
        self.base_url = "https://nominatim.openstreetmap.org/search"
        self.cache_file = cache_file or Config.GEOCACHE_FILE
        self.cache = self._cargar_cache()
        
        # Configuración
        self.timeout = 10
        self.wait_time = 1.0  # segundos entre consultas
        self.max_retries = 3
        
        # Estadísticas
        self.estadisticas = {
            'total_consultas': 0,
            'consultas_cache': 0,
            'consultas_api': 0,
            'errores': 0,
            'tiempo_total': 0
        }
    
    def _cargar_cache(self) -> Dict:
        """Cargar caché desde archivo"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache = json.load(f)
                    print(f"📂 Cache cargado: {len(cache)} entradas")
                    return cache
            except Exception as e:
                print(f"⚠️ Error cargando cache: {e}")
                return {}
        return {}
    
    def _guardar_cache(self):
        """Guardar caché en archivo"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Error guardando cache: {e}")
    
    def _crear_clave_cache(self, direccion: str, poblacion: str = "Madrid") -> str:
        """Crear clave única para caché"""
        return f"{direccion.strip().lower()}|{poblacion.strip().lower()}"
    
    def geocodificar(self, direccion: str, poblacion: str = "Madrid", 
                    intentar_variaciones: bool = True) -> Dict:
        """
        Geocodificar una dirección a coordenadas
        
        Returns:
            Dict con: lat, lon, es_madrid_central, zona_madrid, accuracy, cached
        """
        start_time = time.time()
        self.estadisticas['total_consultas'] += 1
        
        # Crear clave para caché
        clave = self._crear_clave_cache(direccion, poblacion)
        
        # Verificar caché
        if clave in self.cache:
            resultado = self.cache[clave].copy()
            resultado['cached'] = True
            resultado['timestamp'] = datetime.now().isoformat()
            self.estadisticas['consultas_cache'] += 1
            self.estadisticas['tiempo_total'] += time.time() - start_time
            return resultado
        
        # Si no está en caché, consultar API
        resultado = self._consultar_api(direccion, poblacion)
        
        # Si falla y hay que intentar variaciones
        if not resultado['success'] and intentar_variaciones:
            resultado = self._intentar_variaciones(direccion, poblacion)
        
        # Guardar en caché si fue exitoso
        if resultado['success']:
            resultado['cached'] = False
            resultado['timestamp'] = datetime.now().isoformat()
            self.cache[clave] = resultado.copy()
            self._guardar_cache()
        
        self.estadisticas['consultas_api'] += 1
        self.estadisticas['tiempo_total'] += time.time() - start_time
        
        return resultado
    
    def _consultar_api(self, direccion: str, poblacion: str) -> Dict:
        """Consultar API de Nominatim"""
        
        # Preparar consulta
        query = f"{direccion}, {poblacion}, España"
        
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'es',
            'addressdetails': 1
        }
        
        headers = {
            'User-Agent': 'OptimizadorRutasVRP/1.0 (contacto@empresa.com)'
        }
        
        for intento in range(self.max_retries):
            try:
                # Respetar rate limiting
                time.sleep(self.wait_time)
                
                response = requests.get(
                    self.base_url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data:
                        # Extraer coordenadas
                        item = data[0]
                        lat = float(item['lat'])
                        lon = float(item['lon'])
                        
                        # Determinar si está en Madrid Central
                        es_madrid_central = self._es_madrid_central(lat, lon)
                        
                        # Determinar zona de Madrid
                        zona_madrid = self._determinar_zona_madrid(lat, lon)
                        
                        # Calcular precisión
                        accuracy = self._calcular_precision(item)
                        
                        return {
                            'success': True,
                            'lat': lat,
                            'lon': lon,
                            'es_madrid_central': es_madrid_central,
                            'zona_madrid': zona_madrid,
                            'accuracy': accuracy,
                            'address': item.get('display_name', ''),
                            'original_query': query
                        }
                    else:
                        return {
                            'success': False,
                            'error': 'No se encontraron resultados',
                            'original_query': query
                        }
                
                elif response.status_code == 429:  # Too Many Requests
                    wait = (intento + 1) * 5  # Esperar más en cada reintento
                    print(f"⏳ Rate limit alcanzado, esperando {wait} segundos...")
                    time.sleep(wait)
                    continue
                    
                else:
                    return {
                        'success': False,
                        'error': f'HTTP {response.status_code}',
                        'original_query': query
                    }
                    
            except requests.exceptions.Timeout:
                return {
                    'success': False,
                    'error': 'Timeout',
                    'original_query': query
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                    'original_query': query
                }
        
        return {
            'success': False,
            'error': 'Máximo de reintentos alcanzado',
            'original_query': query
        }
    
    def _intentar_variaciones(self, direccion: str, poblacion: str) -> Dict:
        """Intentar diferentes variaciones de la dirección"""
        
        variaciones = [
            f"{direccion}, Madrid",  # Solo Madrid
            direccion,  # Solo la dirección
            f"{poblacion}, {direccion.split(',')[0]}",  # Invertido
        ]
        
        # Extraer número si existe
        import re
        match = re.search(r'\d+', direccion)
        if match:
            numero = match.group()
            variaciones.append(f"{direccion.split(numero)[0].strip()} {numero}, {poblacion}")
        
        for variacion in variaciones:
            print(f"  🔄 Intentando variación: {variacion}")
            resultado = self._consultar_api(variacion, poblacion)
            if resultado['success']:
                return resultado
        
        return {
            'success': False,
            'error': 'Todas las variaciones fallaron',
            'original_query': f"{direccion}, {poblacion}"
        }
    
    def _es_madrid_central(self, lat: float, lon: float) -> bool:
        """Determinar si está dentro de Madrid Central"""
        from config import Config
        
        bounds = Config.ZONAS_MADRID['CENTRO']['bounds']
        
        return (bounds['lat_min'] <= lat <= bounds['lat_max'] and
                bounds['lon_min'] <= lon <= bounds['lon_max'])
    
    def _determinar_zona_madrid(self, lat: float, lon: float) -> str:
        """Determinar zona de Madrid basada en coordenadas"""
        from config import Config
        
        for zona_nombre, zona_data in Config.ZONAS_MADRID.items():
            bounds = zona_data['bounds']
            if (bounds['lat_min'] <= lat <= bounds['lat_max'] and
                bounds['lon_min'] <= lon <= bounds['lon_max']):
                return zona_nombre
        
        # Si no cae en ninguna zona definida, calcular la más cercana
        return self._determinar_zona_por_proximidad(lat, lon)
    
    def _determinar_zona_por_proximidad(self, lat: float, lon: float) -> str:
        """Determinar zona por proximidad a centros de zona"""
        
        centros_zonas = {
            'CENTRO': (40.4168, -3.7038),
            'NORTE': (40.4667, -3.7000),
            'SUR': (40.3667, -3.7000),
            'ESTE': (40.4168, -3.6000),
            'OESTE': (40.4168, -3.8000)
        }
        
        distancias = {}
        for zona, centro in centros_zonas.items():
            distancia = self.calcular_distancia_km((lat, lon), centro)
            distancias[zona] = distancia
        
        return min(distancias, key=distancias.get)
    
    def _calcular_precision(self, item: Dict) -> str:
        """Calcular precisión de la geocodificación"""
        
        # Extraer type de Nominatim
        item_type = item.get('type', '')
        importance = float(item.get('importance', 0))
        
        if item_type == 'house':
            return 'ALTA'
        elif item_type == 'street':
            return 'MEDIA'
        elif importance > 0.7:
            return 'MEDIA-ALTA'
        elif importance > 0.4:
            return 'MEDIA'
        else:
            return 'BAJA'
    
    def calcular_distancia_km(self, coord1: Tuple[float, float], 
                             coord2: Tuple[float, float]) -> float:
        """Calcular distancia en km entre dos coordenadas"""
        return geodesic(coord1, coord2).kilometers
    
    def procesar_dataframe(self, df: pd.DataFrame,
                          direccion_col: str = 'Direccion',
                          poblacion_col: str = 'Poblacion',
                          progress_callback: Callable = None) -> pd.DataFrame:
        """
        Geocodificar todas las direcciones en un DataFrame
        
        Args:
            df: DataFrame con direcciones
            direccion_col: Nombre de columna con direcciones
            poblacion_col: Nombre de columna con población
            progress_callback: Función para reportar progreso
            
        Returns:
            DataFrame con columnas añadidas
        """
        
        print(f"📍 Iniciando geocodificación de {len(df)} direcciones...")
        
        resultados = []
        total = len(df)
        
        for idx, fila in df.iterrows():
            # Mostrar progreso
            if progress_callback:
                progress_callback((idx + 1) / total, 
                                 f"Geocodificando {idx + 1}/{total}")
            
            # Obtener dirección y población
            direccion = str(fila.get(direccion_col, '')).strip()
            poblacion = str(fila.get(poblacion_col, 'Madrid')).strip()
            
            # Si no hay dirección, saltar
            if not direccion or direccion.lower() in ['nan', 'none', '']:
                resultados.append({
                    'lat': None,
                    'lon': None,
                    'es_madrid_central': False,
                    'zona_madrid': 'DESCONOCIDA',
                    'accuracy': 'NULA',
                    'geocodificado': False,
                    'error': 'Dirección vacía'
                })
                continue
            
            # Geocodificar
            try:
                resultado = self.geocodificar(direccion, poblacion)
                
                if resultado['success']:
                    resultados.append({
                        'lat': resultado['lat'],
                        'lon': resultado['lon'],
                        'es_madrid_central': resultado['es_madrid_central'],
                        'zona_madrid': resultado['zona_madrid'],
                        'accuracy': resultado['accuracy'],
                        'geocodificado': True,
                        'error': None
                    })
                else:
                    resultados.append({
                        'lat': None,
                        'lon': None,
                        'es_madrid_central': False,
                        'zona_madrid': 'DESCONOCIDA',
                        'accuracy': 'NULA',
                        'geocodificado': False,
                        'error': resultado.get('error', 'Error desconocido')
                    })
                    
            except Exception as e:
                resultados.append({
                    'lat': None,
                    'lon': None,
                    'es_madrid_central': False,
                    'zona_madrid': 'DESCONOCIDA',
                    'accuracy': 'NULA',
                    'geocodificado': False,
                    'error': str(e)
                })
        
        # Añadir resultados al DataFrame
        df_resultado = df.copy()
        resultados_df = pd.DataFrame(resultados, index=df.index)
        df_resultado = pd.concat([df_resultado, resultados_df], axis=1)
        
        # Estadísticas finales
        exitosos = df_resultado['geocodificado'].sum()
        print(f"✅ Geocodificación completada: {exitosos}/{total} exitosas")
        print(f"📊 Cache hit rate: {self.estadisticas['consultas_cache']}/{self.estadisticas['total_consultas']}")
        print(f"⏱️ Tiempo total: {self.estadisticas['tiempo_total']:.1f}s")
        
        return df_resultado
    
    def obtener_estadisticas(self) -> Dict:
        """Obtener estadísticas de geocodificación"""
        return self.estadisticas.copy()
    
    def limpiar_cache(self, max_dias: int = 30):
        """Limpiar caché antiguo"""
        from datetime import datetime, timedelta
        
        limite = datetime.now() - timedelta(days=max_dias)
        claves_a_eliminar = []
        
        for clave, datos in self.cache.items():
            timestamp_str = datos.get('timestamp', '')
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                    if timestamp < limite:
                        claves_a_eliminar.append(clave)
                except:
                    claves_a_eliminar.append(clave)
        
        for clave in claves_a_eliminar:
            del self.cache[clave]
        
        self._guardar_cache()
        print(f"🧹 Cache limpiado: {len(claves_a_eliminar)} entradas eliminadas")