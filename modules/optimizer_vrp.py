"""
Algoritmo VRP Ajustado a la Realidad (Media 7.5 serv/día)
- Reparto equitativo estricto.
- Lógica de Cajas (Suministro/Depósito).
- Respeta límites humanos.
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
            # 1. Procesar lógica de negocio
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            # Filtrar válidos
            df = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df) == 0: 
                st.warning("⚠️ No hay direcciones válidas geocodificadas.")
                return {}

            # 2. Crear Matrices
            matriz_dist, matriz_tiempo, puntos, nodos_vertederos = self._crear_matrices(df)
            
            # 3. Configurar Vehículos
            num_vehiculos = int(self.parametros.get('vehiculos_c', 20)) # Por defecto 20 si no se dice nada
            
            # --- CÁLCULO INTELIGENTE DE CAPACIDAD (TUNING REAL) ---
            total_servicios = len(df)
            
            # Carga ideal matemática (ej: 150 serv / 20 camiones = 7.5)
            carga_promedio = total_servicios / max(1, num_vehiculos)
            
            # Definimos el límite superior permitido por camión.
            # Damos un margen de +3 servicios sobre la media para dar flexibilidad,
            # pero bloqueamos los excesos (nadie hará 20 si la media es 7.5).
            limite_paradas = int(carga_promedio + 4) 
            
            # Seguridad: Mínimo 5 paradas (por si son pocos servicios)
            limite_paradas = max(5, limite_paradas)

            # Debug para que veas en consola cómo piensa
            print(f"DEBUG: {total_servicios} servicios para {num_vehiculos} camiones.")
            print(f"DEBUG: Media ideal: {carga_promedio:.1f}. Límite tope puesto en: {limite_paradas}.")

            # 4. Configurar OR-Tools
            manager = pywrapcp.RoutingIndexManager(len(matriz_dist), num_vehiculos, 0)
            routing = pywrapcp.RoutingModel(manager)

            # A. Coste Distancia
            def distance_callback(from_index, to_index):
                return matriz_dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # B. Balanceo Estricto
            routing.AddConstantDimension(
                1, # Incremento
                limite_paradas, # Límite calculado arriba
                True,
                "ContadorServicios"
            )
            # Penalizar fuertemente que uno trabaje mucho más que otros
            count_dim = routing.GetDimensionOrDie("ContadorServicios")
            count_dim.SetGlobalSpanCostCoefficient(10000) # Penalización muy alta

            # C. Tiempo (Jornada laboral)
            def time_callback(from_index, to_index):
                # Viaje + 25 min servicio (ajustado a la realidad de cadenas)
                return matriz_tiempo[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)] + 1500
            
            time_callback_index = routing.RegisterTransitCallback(time_callback)
            
            # Máximo 10 horas
            routing.AddDimension(
                time_callback_index,
                3600, # Slack
                36000, # Max jornada (10h)
                False, 
                "Tiempo"
            )

            # D. Inventario Cajas
            demands = [0] + df['delta_cajas'].tolist() + [0, 0]
            def demand_callback(from_index):
                node = manager.IndexToNode(from_index)
                return demands[node] if node < len(demands) else 0

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index, 0, [5]*num_vehiculos, False, "InventarioCajas"
            )
            
            # Permitir salir con cajas
            inv_dim = routing.GetDimensionOrDie('InventarioCajas')
            for v in range(num_vehiculos):
                inv_dim.CumulVar(routing.Start(v)).SetRange(0, 5)

            # 5. Resolver
            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 20

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, df, nodos_vertederos)
            else:
                # Mensaje de error inteligente
                sugerencia = int(total_servicios / 8) + 1
                st.error(f"❌ No encuentro solución equilibrada. Tienes {num_vehiculos} camiones para {total_servicios} servicios.")
                st.warning(f"💡 PISTA: Para mantener una media de ~8 servicios, intenta poner al menos {sugerencia} camiones en el selector.")
                return {}

        except Exception as e:
            st.error(f"Error crítico en algoritmo: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        """Interpreta Concepto"""
        def analizar(row):
            texto = (str(row.get('Concepto', '')) + " " + str(row.get('Material', ''))).upper()
            tipo = 'RETIRADA'; delta = 0 
            if 'SUMINISTRO' in texto or 'ARIDO' in texto: tipo = 'SUMINISTRO'; delta = 1
            elif 'CAMBIO' in texto: tipo = 'CAMBIO'; delta = -1
            elif 'DEPOSITO' in texto: tipo = 'DEPOSITO'; delta = -1
            elif 'RETIRADA' in texto: tipo = 'RETIRADA'; delta = 0
            return pd.Series([tipo, delta])

        df[['tipo_servicio', 'delta_cajas']] = df.apply(analizar, axis=1)
        return df

    def _crear_matrices(self, df):
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
                        d = geodesic(puntos[i], puntos[j]).meters
                        matriz_dist[i][j] = int(d)
                        # Vel media 35km/h = 9.7 m/s
                        matriz_tiempo[i][j] = int(d / 9.7)
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
            
            cajas_inicio = solution.Value(inv_dim.CumulVar(index))
            
            # Saltar rutas vacías
            if routing.IsEnd(solution.Value(routing.NextVar(index))): continue
                
            ruta.append({'Tipo': 'INICIO', 'Direccion': f'Base - SALIR CON {cajas_inicio} CAJAS', 'Concepto': 'INICIO', 'Hora Pide': '08:00', 'Material': '-'})
            
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
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
                elif node in vertedero_map:
                    nombre = vertedero_map[node]
                    ruta.append({'Cliente': f'VERTEDERO {nombre}', 'Tipo': 'VERTIDO', 'Direccion': 'Descarga', 'Concepto': 'IR A VERTEDERO', 'Hora Pide': '-', 'Material': '-'})
                
                index = solution.Value(routing.NextVar(index))
            
            if len(ruta) > 1:
                rutas[f"Vehículo {vehicle_id + 1}"] = {
                    'servicios': ruta,
                    'estadisticas': {
                        'distancia_total_km': 0, 'tiempo_total_min': 0, 
                        'num_servicios': len(ruta)-1, 'combustible_estimado_l': 0
                    }
                }
        return rutas

    def exportar_excel(self, rutas, df_original):
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
        except: pass
        return output.getvalue()

    def exportar_kml(self, rutas): return b""