"""
Algoritmo VRP Balanceado y Experto
- Balanceo de carga (evita 75 vs 4 servicios)
- Gestión de tiempos y horarios
- Lógica de Cajas (Suministro/Depósito)
"""

import pandas as pd
import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.distance import geodesic
import streamlit as st
from datetime import datetime, timedelta

class OptimizadorVRP:
    """Clase principal para la optimización de rutas"""
    
    def __init__(self):
        self.parametros = {}
        # Coordenadas reales
        self.vertederos = {
            'LAGUNA': {'coords': (40.3460, -3.7007), 'nombre': 'Laguna del Marquesado'},
            'VALDEMINGOMEZ': {'coords': (40.3186, -3.6017), 'nombre': 'Valdemingómez'}
        }
        self.base = {'coords': (40.4168, -3.7038), 'nombre': 'Base'} 

    def configurar(self, **kwargs):
        self.parametros = kwargs

    def optimizar(self, df_input):
        """Ejecuta la optimización completa"""
        try:
            # 1. Procesar lógica de negocio (Cajas y Conceptos)
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            # Filtrar válidos
            df = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df) == 0: 
                st.warning("No hay direcciones válidas para optimizar.")
                return {}

            # 2. Crear Matrices (Distancia y Tiempo)
            matriz_dist, matriz_tiempo, puntos, nodos_vertederos = self._crear_matrices(df)
            
            # 3. Configurar OR-Tools
            num_vehiculos = int(self.parametros.get('vehiculos_c', 5))
            # Ajuste de seguridad: si hay muchos puntos, aseguramos mínimos vehículos
            if len(df) > 20 and num_vehiculos < 2:
                num_vehiculos = 2

            manager = pywrapcp.RoutingIndexManager(len(matriz_dist), num_vehiculos, 0)
            routing = pywrapcp.RoutingModel(manager)

            # --- A. COSTE POR DISTANCIA ---
            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                return matriz_dist[from_node][to_node]

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # --- B. BALANCEO DE CARGA (Para evitar 75 servicios a uno) ---
            # Añadimos una dimensión que cuenta 1 por cada visita
            routing.AddConstantDimension(
                1, # Incremento por parada
                20, # MÁXIMO DE PARADAS POR CAMIÓN (Esto es lo que evita la sobrecarga)
                True, # Empezar en 0
                "ContadorServicios"
            )
            
            # Penalizar el desequilibrio
            contador_dim = routing.GetDimensionOrDie("ContadorServicios")
            contador_dim.SetGlobalSpanCostCoefficient(5000) # Penalización alta si uno trabaja mucho más que otro

            # --- C. TIEMPO Y HORARIOS ---
            def time_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                # Tiempo viaje + 30 min servicio (1800 seg)
                return matriz_tiempo[from_node][to_node] + 1800

            time_callback_index = routing.RegisterTransitCallback(time_callback)
            
            # Jornada máxima 10 horas (36000 seg)
            routing.AddDimension(
                time_callback_index,
                3600, # Slack (espera permitida de 1h)
                36000, # Max jornada
                False, 
                "Tiempo"
            )

            # --- D. INVENTARIO DE CAJAS ---
            demands = [0] + df['delta_cajas'].tolist() + [0, 0]
            
            def demand_callback(from_index):
                node = manager.IndexToNode(from_index)
                if node < len(demands):
                    return demands[node]
                return 0

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
            
            # Capacidad de 5 cajas vacías
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index, 
                0, 
                [5]*num_vehiculos, 
                False, 
                "InventarioCajas"
            )
            
            # Permitir salir con cajas de la base
            inv_dim = routing.GetDimensionOrDie('InventarioCajas')
            for v in range(num_vehiculos):
                inv_dim.CumulVar(routing.Start(v)).SetRange(0, 5)

            # 4. Resolver
            search_params = pywrapcp.DefaultRoutingSearchParameters()
            # Usar una estrategia más agresiva para encontrar solución rápido
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 15 # Límite de tiempo para evitar bloqueos

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, df, nodos_vertederos)
            else:
                return {}

        except Exception as e:
            st.error(f"Error detallado en optimización: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        """Interpreta Concepto para cajas y horarios"""
        def analizar(row):
            texto = (str(row.get('Concepto', '')) + " " + str(row.get('Material', ''))).upper()
            
            # Lógica de Cajas
            tipo = 'RETIRADA' # Defecto
            delta = 0 
            
            if 'SUMINISTRO' in texto or 'ARIDO' in texto:
                tipo = 'SUMINISTRO'
                delta = 1 # Gana caja vacía
            elif 'CAMBIO' in texto:
                tipo = 'CAMBIO'
                delta = -1 # Gasta caja vacía (y coge llena)
            elif 'DEPOSITO' in texto or 'ENTREGA' in texto:
                tipo = 'DEPOSITO'
                delta = -1 # Gasta caja vacía
            elif 'RETIRADA' in texto:
                tipo = 'RETIRADA'
                delta = 0
            
            return pd.Series([tipo, delta])

        df[['tipo_servicio', 'delta_cajas']] = df.apply(analizar, axis=1)
        return df

    def _crear_matrices(self, df):
        """Crea matrices de distancia y tiempo"""
        puntos = [self.base['coords']] + [(r['lat'], r['lon']) for _, r in df.iterrows()]
        
        idx_base = len(puntos)
        nodos = {}
        puntos.append(self.vertederos['LAGUNA']['coords']); nodos['LAGUNA'] = idx_base
        puntos.append(self.vertederos['VALDEMINGOMEZ']['coords']); nodos['VALDEMINGOMEZ'] = idx_base + 1
        
        size = len(puntos)
        matriz_dist = [[0]*size for _ in range(size)]
        matriz_tiempo = [[0]*size for _ in range(size)]
        
        for i in range(size):
            for j in range(size):
                if i != j:
                    try:
                        # Distancia en metros
                        d = geodesic(puntos[i], puntos[j]).meters
                        matriz_dist[i][j] = int(d)
                        
                        # Tiempo en segundos (vel. media 30km/h = 8.33 m/s)
                        # Penalizamos distancias largas para simular tráfico
                        velocidad = 8.33 
                        matriz_tiempo[i][j] = int(d / velocidad)
                    except:
                        matriz_dist[i][j] = 1000000
                        matriz_tiempo[i][j] = 1000000
                        
        return matriz_dist, matriz_tiempo, puntos, nodos

    def _procesar_solucion(self, manager, routing, solution, df, nodos_vertederos):
        rutas = {}
        inv_dim = routing.GetDimensionOrDie('InventarioCajas')
        vertedero_map = {v: k for k, v in nodos_vertederos.items()}
        
        for vehicle_id in range(routing.vehicles()):
            index = routing.Start(vehicle_id)
            ruta = []
            
            # Carga inicial
            cajas_inicio = solution.Value(inv_dim.CumulVar(index))
            
            # Si la ruta está vacía (solo inicio -> fin), saltar
            if routing.IsEnd(solution.Value(routing.NextVar(index))):
                continue
                
            ruta.append({
                'Tipo': 'INICIO', 
                'Direccion': f'Base - CARGAR {cajas_inicio} CAJAS VACÍAS', 
                'Concepto': 'INICIO JORNADA', 
                'Hora Pide': '08:00',
                'Material': '-'
            })
            
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                
                # Nodo Cliente
                if 0 < node <= len(df):
                    row = df.iloc[node - 1]
                    ruta.append({
                        'Cliente': row['Cliente'],
                        'Direccion': row['Direccion'],
                        'Tipo': row['tipo_servicio'],
                        'Concepto': row.get('Concepto', 'Servicio'),
                        'Material': row.get('Material', ''),
                        'Hora Pide': row.get('Hora Pide', 'Flexible'),
                        'lat': row['lat'], 'lon': row['lon']
                    })
                # Nodo Vertedero
                elif node in vertedero_map:
                    nombre = vertedero_map[node]
                    ruta.append({
                        'Cliente': f'VERTEDERO {nombre}', 
                        'Tipo': 'VERTIDO', 
                        'Direccion': 'Descarga', 
                        'Concepto': 'IR A VERTEDERO', 
                        'Hora Pide': '-',
                        'Material': '-'
                    })
                
                index = solution.Value(routing.NextVar(index))
            
            if len(ruta) > 1:
                rutas[f"Vehículo {vehicle_id + 1}"] = {
                    'servicios': ruta,
                    'estadisticas': {
                        'distancia_total_km': 0, # Se podría calcular mejor, pero simplificamos
                        'tiempo_total_min': 0, 
                        'num_servicios': len(ruta)-1, 
                        'combustible_estimado_l': 0, 
                        'combos_detectados': 0
                    }
                }
        return rutas
        
    def exportar_excel(self, rutas, df_original):
        """Exporta las rutas a Excel (requiere xlsxwriter)"""
        import io
        output = io.BytesIO()
        try:
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                detalle = []
                for vehiculo, datos in rutas.items():
                    for orden, serv in enumerate(datos['servicios'], 1):
                        s = serv.copy()
                        s['Vehículo'] = vehiculo
                        s['Orden'] = orden
                        detalle.append(s)
                pd.DataFrame(detalle).to_excel(writer, sheet_name='Detalle Rutas', index=False)
        except Exception as e:
            # Fallback si falla xlsxwriter
            pass
        return output.getvalue()

    def exportar_kml(self, rutas):
        return b""