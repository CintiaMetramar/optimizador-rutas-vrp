"""
Algoritmo VRP (Vehicle Routing Problem) avanzado para optimización de rutas
Incluye: Time Windows, Capacities, Pickup & Delivery, Multiple Depots
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
import math
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import itertools
from scipy.spatial import KDTree

class OptimizadorVRP:
    def __init__(self):
        """Inicializar optimizador VRP"""
        self.parametros = {}
        self.vertederos = {
            'norte': (40.3460, -3.7007),
            'sur': (40.3186, -3.6017)
        }
        
        # Factores de conversión
        self.VELOCIDAD_PROMEDIO = 30  # km/h
        self.CONSUMO_COMBUSTIBLE = 0.3  # L/km
        self.TIEMPO_SERVICIO = 30  # minutos
        
    def configurar(self, **kwargs):
        """Configurar parámetros de optimización"""
        self.parametros = kwargs
        
        # Actualizar valores
        if 'velocidad_promedio' in kwargs:
            self.VELOCIDAD_PROMEDIO = kwargs['velocidad_promedio']
        if 'tiempo_por_servicio' in kwargs:
            self.TIEMPO_SERVICIO = kwargs['tiempo_por_servicio']
    
    def calcular_distancia(self, coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calcular distancia Haversine entre dos coordenadas (km)"""
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        
        # Radio de la Tierra en km
        R = 6371.0
        
        # Convertir a radianes
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Diferencia
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # Fórmula Haversine
        a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def detectar_combinaciones(self, df: pd.DataFrame) -> List[Dict]:
        """Detectar combinaciones depósito-retirada cercanas"""
        if 'tipo_servicio' not in df.columns:
            # Inferir tipo de servicio
            df['tipo_servicio'] = df.apply(self._inferir_tipo_servicio, axis=1)
        
        # Separar depósitos y retiradas
        depositos = df[df['tipo_servicio'] == 'DEPOSITO'].copy()
        retiradas = df[df['tipo_servicio'] == 'RETIRADA'].copy()
        
        if len(depositos) == 0 or len(retiradas) == 0:
            return []
        
        # Crear KD-tree para búsqueda rápida
        coords_retiradas = list(zip(retiradas['lat'], retiradas['lon']))
        tree = KDTree(coords_retiradas)
        
        combos = []
        max_distancia = self.parametros.get('max_distancia_combo', 5)
        
        for idx_deposito, deposito in depositos.iterrows():
            if pd.isna(deposito['lat']) or pd.isna(deposito['lon']):
                continue
            
            # Buscar retirada más cercana
            distancia, idx_retirada = tree.query([(deposito['lat'], deposito['lon'])], k=1)
            
            if distancia[0] <= max_distancia:
                retirada = retiradas.iloc[idx_retirada[0]]
                
                combo = {
                    'deposito_id': deposito.name,
                    'retirada_id': retirada.name,
                    'distancia_km': distancia[0],
                    'deposito': deposito.to_dict(),
                    'retirada': retirada.to_dict()
                }
                combos.append(combo)
        
        # Ordenar por distancia
        combos.sort(key=lambda x: x['distancia_km'])
        
        return combos
    
    def _inferir_tipo_servicio(self, fila) -> str:
        """Inferir tipo de servicio basado en columnas"""
        material = str(fila.get('Material', '')).lower()
        
        if 'retirada' in material:
            return 'RETIRADA'
        elif 'deposito' in material or 'depósito' in material:
            return 'DEPOSITO'
        elif 'cambio' in material:
            return 'CAMBIO'
        else:
            # Intentar inferir de otras columnas
            caja_depos = fila.get('Caja Depos', '')
            caja_retir = fila.get('Caja Retir', '')
            
            if caja_depos and caja_retir:
                return 'COMBO'
            elif caja_depos:
                return 'DEPOSITO'
            elif caja_retir:
                return 'RETIRADA'
            else:
                return 'SERVICIO'
    
    def asignar_zonas(self, df: pd.DataFrame) -> pd.DataFrame:
        """Asignar zonas de Madrid a cada servicio"""
        df['zona_madrid'] = df.apply(self._determinar_zona, axis=1)
        return df
    
    def _determinar_zona(self, fila) -> str:
        """Determinar zona de Madrid basada en coordenadas"""
        lat = fila.get('lat')
        lon = fila.get('lon')
        
        if pd.isna(lat) or pd.isna(lon):
            return 'DESCONOCIDA'
        
        # Definir zonas de Madrid
        if lat > 40.48:
            return 'NORTE_EXTREMO'
        elif lat > 40.43:
            return 'NORTE'
        elif lat > 40.40:
            if lon < -3.73:
                return 'OESTE'
            elif lon > -3.65:
                return 'ESTE'
            else:
                return 'CENTRO_NUEVO'
        elif lat > 40.38:
            if lon < -3.68:
                return 'CARABANCHEL'
            else:
                return 'VALLECAS'
        elif lat > 40.33:
            return 'SUR'
        else:
            return 'SUR_EXTREMO'
    
    def clusterizar_por_zona(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """Dividir servicios por zonas para asignación a vehículos"""
        zonas = {}
        
        for zona in df['zona_madrid'].unique():
            if zona != 'DESCONOCIDA':
                zonas[zona] = df[df['zona_madrid'] == zona].copy()
        
        return zonas
    
    def optimizar_por_zona(self, df_zona: pd.DataFrame, zona_nombre: str) -> Dict:
        """Optimizar rutas dentro de una zona específica"""
        
        # Filtrar vehículos disponibles para esta zona
        vehiculos_c_disponibles = self.parametros.get('vehiculos_c', 10)
        
        # Determinar si se requieren vehículos C (Madrid Central)
        requiere_c = zona_nombre in ['CENTRO_NUEVO', 'CENTRO']
        
        # Número de vehículos a usar
        num_vehiculos = max(1, math.ceil(len(df_zona) / 15))  # Máximo 15 servicios por vehículo
        
        # Ajustar por capacidad de contenedores
        capacidad_vehiculo = self.parametros.get('capacidad_vehiculo', 5)
        num_vehiculos = max(num_vehiculos, math.ceil(len(df_zona) / capacidad_vehiculo))
        
        # Preparar datos para OR-Tools
        coordenadas = []
        demandas = []  # 1 por servicio
        time_windows = []
        
        for _, servicio in df_zona.iterrows():
            if pd.notna(servicio['lat']) and pd.notna(servicio['lon']):
                coordenadas.append((servicio['lat'], servicio['lon']))
                demandas.append(1)  # Cada servicio cuenta como 1 unidad
                
                # Time window basado en Hora Pide
                hora_pide = servicio.get('Hora Pide', '09:00')
                try:
                    hora_obj = datetime.strptime(str(hora_pide), '%H:%M')
                    inicio = hora_obj.hour * 60 + hora_obj.minute
                    fin = inicio + self.parametros.get('flexibilidad_horaria', 60)
                    time_windows.append((inicio, fin))
                except:
                    time_windows.append((480, 1020))  # 8:00 - 17:00
        
        if len(coordenadas) < 2:
            return {'ruta': [], 'estadisticas': {}}
        
        # Crear matriz de distancias
        num_nodos = len(coordenadas)
        dist_matrix = np.zeros((num_nodos, num_nodos))
        
        for i in range(num_nodos):
            for j in range(num_nodos):
                if i != j:
                    dist_matrix[i][j] = self.calcular_distancia(
                        coordenadas[i], coordenadas[j]
                    )
        
        # Crear modelo VRP con OR-Tools
        manager = pywrapcp.RoutingIndexManager(
            num_nodos, 
            num_vehiculos, 
            0  # Depósito inicial
        )
        
        routing = pywrapcp.RoutingModel(manager)
        
        # Definir función de coste por distancia
        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return int(dist_matrix[from_node][to_node] * 1000)  # Convertir a metros
        
        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        
        # Añadir restricción de capacidad
        def demand_callback(from_index):
            from_node = manager.IndexToNode(from_index)
            return demandas[from_node]
        
        demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
        routing.AddDimensionWithVehicleCapacity(
            demand_callback_index,
            0,  # slack
            [capacidad_vehiculo] * num_vehiculos,  # capacidades
            True,  # start cumul to zero
            'Capacity'
        )
        
        # Añadir restricción de tiempo
        def time_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            travel_time = int((dist_matrix[from_node][to_node] / self.VELOCIDAD_PROMEDIO) * 60)  # minutos
            service_time = self.TIEMPO_SERVICIO
            return travel_time + service_time
        
        time_callback_index = routing.RegisterTransitCallback(time_callback)
        routing.AddDimension(
            time_callback_index,
            60 * 8,  # slack máximo (8 horas)
            60 * 10,  # tiempo máximo por vehículo (10 horas)
            False,  # Don't force start cumul to zero
            'Time'
        )
        
        time_dimension = routing.GetDimensionOrDie('Time')
        
        # Añadir time windows
        for node_idx in range(num_nodos):
            index = manager.NodeToIndex(node_idx)
            time_dimension.CumulVar(index).SetRange(
                time_windows[node_idx][0],
                time_windows[node_idx][1]
            )
        
        # Configurar parámetros de búsqueda
        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        search_parameters.local_search_metaheuristic = (
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        )
        search_parameters.time_limit.seconds = 30
        
        # Resolver
        solution = routing.SolveWithParameters(search_parameters)
        
        if solution:
            return self._extraer_solucion(solution, routing, manager, df_zona, coordenadas, num_vehiculos)
        else:
            return {'ruta': [], 'estadisticas': {}}
    
    def _extraer_solucion(self, solution, routing, manager, df_zona, coordenadas, num_vehiculos):
        """Extraer solución de OR-Tools"""
        
        rutas = {}
        
        for vehicle_id in range(num_vehiculos):
            index = routing.Start(vehicle_id)
            ruta_nodos = []
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                ruta_nodos.append(node_index)
                index = solution.Value(routing.NextVar(index))
            
            if ruta_nodos:
                # Obtener servicios de esta ruta
                servicios_ruta = df_zona.iloc[ruta_nodos].copy()
                
                # Calcular estadísticas
                distancia_total = 0
                tiempo_total = self.TIEMPO_SERVICIO * len(ruta_nodos)  # Tiempo de servicio
                
                for i in range(len(ruta_nodos) - 1):
                    distancia_total += self.calcular_distancia(
                        coordenadas[ruta_nodos[i]],
                        coordenadas[ruta_nodos[i + 1]]
                    )
                    tiempo_total += (distancia_total / self.VELOCIDAD_PROMEDIO) * 60
                
                # Nombre del vehículo
                vehiculo_nombre = f"Veh_{vehicle_id + 1:02d}"
                if vehicle_id < self.parametros.get('vehiculos_c', 10):
                    vehiculo_nombre += "_C"
                
                rutas[vehiculo_nombre] = {
                    'servicios': servicios_ruta.to_dict('records'),
                    'estadisticas': {
                        'num_servicios': len(ruta_nodos),
                        'distancia_total_km': distancia_total,
                        'tiempo_total_min': tiempo_total,
                        'combustible_estimado_l': distancia_total * self.CONSUMO_COMBUSTIBLE,
                        'combos_detectados': 0  # Se calculará después
                    }
                }
        
        return rutas
    
    def optimizar(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Optimización principal VRP"""
        
        print(f"Iniciando optimización VRP para {len(df)} servicios...")
        
        # Paso 1: Asignar zonas
        df_con_zonas = self.asignar_zonas(df)
        
        # Paso 2: Detectar combinaciones
        combos = self.detectar_combinaciones(df_con_zonas)
        print(f"Detectados {len(combos)} combos depósito-retirada")
        
        # Paso 3: Clusterizar por zona
        zonas = self.clusterizar_por_zona(df_con_zonas)
        print(f"Servicios divididos en {len(zonas)} zonas")
        
        # Paso 4: Optimizar cada zona
        todas_rutas = {}
        
        for zona_nombre, df_zona in zonas.items():
            print(f"Optimizando zona {zona_nombre} ({len(df_zona)} servicios)...")
            
            rutas_zona = self.optimizar_por_zona(df_zona, zona_nombre)
            
            # Añadir combos a las estadísticas
            for vehiculo, ruta in rutas_zona.items():
                if 'servicios' in ruta:
                    # Contar combos en esta ruta
                    combos_en_ruta = 0
                    for combo in combos:
                        deposito_id = combo['deposito_id']
                        retirada_id = combo['retirada_id']
                        
                        # Verificar si ambos servicios están en esta ruta
                        servicios_ids = [s.get('id', '') for s in ruta['servicios']]
                        if deposito_id in servicios_ids and retirada_id in servicios_ids:
                            combos_en_ruta += 1
                    
                    ruta['estadisticas']['combos_detectados'] = combos_en_ruta
            
            todas_rutas.update(rutas_zona)
        
        # Paso 5: Asignar conductores a vehículos
        todas_rutas = self.asignar_conductores(todas_rutas, df_con_zonas)
        
        print(f"Optimización completada: {len(todas_rutas)} rutas generadas")
        
        return todas_rutas
    
    def asignar_conductores(self, rutas: Dict, df: pd.DataFrame) -> Dict:
        """Asignar conductores a las rutas basado en los servicios"""
        
        # Crear mapeo conductor -> servicios
        if 'Conductor' in df.columns:
            conductor_servicios = df.groupby('Conductor').size().to_dict()
            
            # Ordenar conductores por número de servicios
            conductores_ordenados = sorted(
                conductor_servicios.items(), 
                key=lambda x: x[1], 
                reverse=True
            )
            
            # Asignar conductores a rutas
            rutas_con_conductores = {}
            for i, (vehiculo, ruta) in enumerate(rutas.items()):
                if i < len(conductores_ordenados):
                    conductor = conductores_ordenados[i][0]
                else:
                    conductor = f"Conductor_{i+1}"
                
                # Crear copia de la ruta con conductor
                ruta_con_conductor = ruta.copy()
                ruta_con_conductor['conductor'] = conductor
                
                # Añadir conductor a cada servicio
                if 'servicios' in ruta_con_conductor:
                    for servicio in ruta_con_conductor['servicios']:
                        servicio['Conductor'] = conductor
                
                rutas_con_conductores[vehiculo] = ruta_con_conductor
            
            return rutas_con_conductores
        
        return rutas
    
    def exportar_excel(self, rutas: Dict, df_original: pd.DataFrame) -> bytes:
        """Exportar rutas optimizadas a Excel"""
        
        # Crear DataFrame consolidado
        datos_exportar = []
        
        for vehiculo, ruta in rutas.items():
            for servicio in ruta.get('servicios', []):
                fila = servicio.copy()
                fila['Vehiculo_Asignado'] = vehiculo
                fila['Conductor_Asignado'] = ruta.get('conductor', '')
                fila['Distancia_Ruta_km'] = ruta['estadisticas']['distancia_total_km']
                fila['Tiempo_Ruta_min'] = ruta['estadisticas']['tiempo_total_min']
                datos_exportar.append(fila)
        
        df_export = pd.DataFrame(datos_exportar)
        
        # Crear libro Excel con múltiples hojas
        with pd.ExcelWriter('temp_export.xlsx', engine='openpyxl') as writer:
            # Hoja 1: Servicios con asignaciones
            df_export.to_excel(writer, sheet_name='Rutas_Optimizadas', index=False)
            
            # Hoja 2: Resumen por vehículo
            resumen_data = []
            for vehiculo, ruta in rutas.items():
                resumen_data.append({
                    'Vehículo': vehiculo,
                    'Conductor': ruta.get('conductor', ''),
                    'Servicios': ruta['estadisticas']['num_servicios'],
                    'Distancia_km': ruta['estadisticas']['distancia_total_km'],
                    'Tiempo_min': ruta['estadisticas']['tiempo_total_min'],
                    'Combustible_L': ruta['estadisticas']['combustible_estimado_l'],
                    'Combos': ruta['estadisticas']['combos_detectados']
                })
            
            df_resumen = pd.DataFrame(resumen_data)
            df_resumen.to_excel(writer, sheet_name='Resumen_Vehiculos', index=False)
            
            # Hoja 3: Combos detectados
            combos_data = []
            for vehiculo, ruta in rutas.items():
                if ruta['estadisticas']['combos_detectados'] > 0:
                    combos_data.append({
                        'Vehículo': vehiculo,
                        'Combos_Detectados': ruta['estadisticas']['combos_detectados']
                    })
            
            if combos_data:
                df_combos = pd.DataFrame(combos_data)
                df_combos.to_excel(writer, sheet_name='Combos_Detectados', index=False)
        
        # Leer archivo como bytes
        with open('temp_export.xlsx', 'rb') as f:
            excel_bytes = f.read()
        
        # Eliminar archivo temporal
        import os
        if os.path.exists('temp_export.xlsx'):
            os.remove('temp_export.xlsx')
        
        return excel_bytes
    
    def exportar_kml(self, rutas: Dict) -> str:
        """Exportar rutas a formato KML para Google My Maps"""
        
        kml_template = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
{placemarks}
{routes}
</Document>
</kml>"""
        
        placemarks = []
        routes = []
        
        # Colores por tipo de vehículo
        colores = {
            'C': 'FF1400FF',  # Azul para vehículos C
            '_C': 'FF1400FF',
            'default': 'FF00A0FF'  # Azul claro para otros
        }
        
        # Añadir vertederos
        for nombre, (lat, lon) in self.vertederos.items():
            placemarks.append(f"""
  <Placemark>
    <name>Vertedero {nombre.title()}</name>
    <Style>
      <IconStyle>
        <color>ff0000ff</color>
        <scale>1.5</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href></Icon>
      </IconStyle>
    </Style>
    <Point>
      <coordinates>{lon},{lat},0</coordinates>
    </Point>
  </Placemark>""")
        
        # Añadir servicios y rutas
        for vehiculo, ruta in rutas.items():
            # Determinar color
            color = colores['default']
            for key in colores:
                if key in vehiculo and key != 'default':
                    color = colores[key]
                    break
            
            # Crear ruta (línea)
            coordenadas_ruta = []
            for servicio in ruta.get('servicios', []):
                if 'lat' in servicio and 'lon' in servicio:
                    lat = servicio['lat']
                    lon = servicio['lon']
                    coordenadas_ruta.append(f"{lon},{lat},0")
                    
                    # Placemark para el servicio
                    placemarks.append(f"""
  <Placemark>
    <name>{servicio.get('Cliente', 'Cliente')} - {vehiculo}</name>
    <description>
      {servicio.get('Direccion', '')}
      Hora: {servicio.get('Hora Pide', '')}
      Conductor: {ruta.get('conductor', '')}
    </description>
    <Style>
      <IconStyle>
        <color>{color}</color>
      </IconStyle>
    </Style>
    <Point>
      <coordinates>{lon},{lat},0</coordinates>
    </Point>
  </Placemark>""")
            
            # Añadir línea de ruta si hay suficientes puntos
            if len(coordenadas_ruta) > 1:
                routes.append(f"""
  <Placemark>
    <name>Ruta {vehiculo}</name>
    <Style>
      <LineStyle>
        <color>{color}</color>
        <width>3</width>
      </LineStyle>
    </Style>
    <LineString>
      <coordinates>
        {' '.join(coordenadas_ruta)}
      </coordinates>
    </LineString>
  </Placemark>""")
        
        return kml_template.format(
            placemarks='\n'.join(placemarks),
            routes='\n'.join(routes)
        )
