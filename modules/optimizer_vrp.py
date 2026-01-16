"""
Algoritmo VRP Experto para Cadenas (Skip Loaders) - Lógica Estricta
- Inicio: Valdemingómez 7:00 AM.
- Regla Basculación: CAMBIO o RETIRADA obligan a ir a Vertedero inmediatamente.
- Gestión de Inventario: El cambio consume la última caja vacía.
- Vertederos Virtuales: Permite múltiples viajes a descargar en el mismo día.
"""

import pandas as pd
import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.distance import geodesic
import streamlit as st
from datetime import datetime, timedelta

class OptimizadorVRP:
    def __init__(self):
        self.parametros = {}
        # Coordenadas reales
        self.vertederos_reales = {
            'LAGUNA': {'coords': (40.3460, -3.7007), 'nombre': 'Laguna del Marquesado'},
            'VALDEMINGOMEZ': {'coords': (40.3186, -3.6017), 'nombre': 'Valdemingómez'}
        }
        # AHORA LA BASE ES VALDEMINGÓMEZ
        self.base = {'coords': (40.3186, -3.6017), 'nombre': 'Base Valdemingómez'} 

    def configurar(self, **kwargs):
        self.parametros = kwargs

    def optimizar(self, df_input):
        try:
            # 1. Procesar lógica de negocio
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            # Filtrar válidos
            df_clientes = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df_clientes) == 0: 
                st.warning("⚠️ No hay direcciones válidas.")
                return {}

            # 2. GENERAR NODOS (Clientes + Vertederos Virtuales)
            # Para permitir que los camiones vayan muchas veces al vertedero,
            # creamos "copias" virtuales de los vertederos.
            num_vehiculos = int(self.parametros.get('vehiculos_c', 20))
            
            # Matriz maestra de nodos
            nodos = []
            
            # Nodo 0: Base
            nodos.append({'tipo': 'BASE', 'coords': self.base['coords'], 'nombre': 'Base', 'demand_full': 0, 'demand_empty': 0})
            
            # Nodos 1..N: Clientes
            for idx, row in df_clientes.iterrows():
                nodos.append({
                    'tipo': 'CLIENTE',
                    'coords': (row['lat'], row['lon']),
                    'nombre': row['Cliente'],
                    'direccion': row['Direccion'],
                    'concepto': row['Concepto'],
                    'tipo_servicio': row['tipo_servicio'],
                    'hora_pide': row.get('Hora Pide', 'Flexible'),
                    'material': row.get('Material', ''),
                    'demand_full': row['demand_full'],   # 1 si genera caja sucia
                    'demand_empty': row['demand_empty'], # 1 si gasta caja limpia
                    'id_original': idx
                })
            
            # Nodos N+1..M: Vertederos Virtuales
            # Creamos suficientes copias para que no falten sitios donde descargar
            # Estimamos: (Num Clientes / 2) copias de vertederos
            num_copias = max(len(df_clientes), num_vehiculos * 4)
            
            indices_vertederos = []
            for i in range(num_copias):
                # Alternamos entre Laguna y Valdemingómez
                v_key = 'VALDEMINGOMEZ' if i % 2 == 0 else 'LAGUNA'
                v_data = self.vertederos_reales[v_key]
                
                nodos.append({
                    'tipo': 'VERTEDERO',
                    'coords': v_data['coords'],
                    'nombre': v_data['nombre'],
                    'demand_full': -1, # Descarga 1 caja llena
                    'demand_empty': 0  # No afecta vacías (se asume que llega sin ellas)
                })
                indices_vertederos.append(len(nodos) - 1)

            # 3. Crear Matriz de Distancias y Tiempos
            matriz_dist, matriz_tiempo = self._crear_matrices(nodos)
            
            # 4. Configurar OR-Tools
            manager = pywrapcp.RoutingIndexManager(len(nodos), num_vehiculos, 0)
            routing = pywrapcp.RoutingModel(manager)

            # A. Coste Distancia
            def distance_callback(from_index, to_index):
                return matriz_dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # B. TIEMPO (Jornada laboral desde las 7:00)
            def time_callback(from_index, to_index):
                # Viaje + 20 min servicio fijo
                return matriz_tiempo[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)] + 1200
            
            time_callback_index = routing.RegisterTransitCallback(time_callback)
            routing.AddDimension(
                time_callback_index,
                3600, # Espera
                43200, # 12 horas max (7:00 a 19:00)
                False, 
                "Tiempo"
            )

            # C. GESTIÓN DE CAJAS LLENAS (Dirty Load)
            # Capacidad = 1.
            # Cambio/Retirada suman 1. Vertedero resta 1.
            # ESTO OBLIGA A: Cambio (+1) -> Camión lleno (1/1) -> Solo puede ir a Vertedero (-1).
            def demand_full_callback(from_index):
                return nodos[manager.IndexToNode(from_index)]['demand_full']

            full_callback_index = routing.RegisterUnaryTransitCallback(demand_full_callback)
            routing.AddDimensionWithVehicleCapacity(
                full_callback_index,
                0, # Slack
                [1] * num_vehiculos, # CAPACIDAD MÁXIMA DE SUCIAS = 1
                True, # Empezar a 0
                "CargaSucia"
            )

            # D. GESTIÓN DE CAJAS VACÍAS (Clean Stack)
            # Capacidad = 5.
            # Depósito/Cambio consumen 1.
            def demand_empty_callback(from_index):
                return nodos[manager.IndexToNode(from_index)]['demand_empty']

            empty_callback_index = routing.RegisterUnaryTransitCallback(demand_empty_callback)
            routing.AddDimensionWithVehicleCapacity(
                empty_callback_index,
                0,
                [5] * num_vehiculos, # CAPACIDAD MÁXIMA VACÍAS = 5
                False, # Permitir empezar con carga
                "CajasVacias"
            )
            
            # Permitir salir de la base (Valdemingómez) con entre 0 y 5 cajas vacías
            # El algoritmo decidirá el número óptimo
            empty_dim = routing.GetDimensionOrDie("CajasVacias")
            for v in range(num_vehiculos):
                empty_dim.CumulVar(routing.Start(v)).SetRange(0, 5)

            # E. Disjunctions (Opcionalidad) para Vertederos
            # Los vertederos son opcionales: solo se visitan si hace falta descargar.
            # Los clientes son obligatorios (penalización alta si se saltan).
            for i in range(1, len(nodos)):
                idx = manager.NodeToIndex(i)
                if nodos[i]['tipo'] == 'VERTEDERO':
                    routing.AddDisjunction([idx], 0) # Coste 0 por no visitarlo (es opcional)
                else:
                    routing.AddDisjunction([idx], 1000000) # Coste alto por no visitar cliente

            # 5. Resolver
            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 45

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, nodos)
            else:
                st.error("❌ No se encontró solución. Verifica si hay 'Cambios' imposibles sin vertedero cerca.")
                return {}

        except Exception as e:
            st.error(f"Error crítico: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        """Traduce la operativa Cintia a números (+1/-1)"""
        def analizar(row):
            texto = (str(row.get('Concepto', '')) + " " + str(row.get('Material', ''))).upper()
            
            tipo = 'RETIRADA'
            d_full = 0 # ¿Genera caja sucia? (+1)
            d_empty = 0 # ¿Gasta caja limpia? (+1 en OR-Tools logic es consumo si capacity es max)
            
            # NOTA: En OR-Tools 'Capacity' con 'UnaryTransitCallback' positivo acumula uso.
            # Capacidad 5. Depósito consume 1 hueco? No, Depósito baja el inventario.
            # Vamos a modelarlo como: Capacidad = 5. Inicio con 5. Depósito demanda 1.
            
            if 'SUMINISTRO' in texto or 'ARIDO' in texto:
                tipo = 'SUMINISTRO'
                d_full = 0
                d_empty = -1 # Genera una vacía (recupera inventario)
            elif 'CAMBIO' in texto:
                tipo = 'CAMBIO'
                d_full = 1   # Genera sucia (STOP -> Vertedero)
                d_empty = 1  # Gasta limpia
            elif 'DEPOSITO' in texto or 'ENTREGA' in texto:
                tipo = 'DEPOSITO'
                d_full = 0
                d_empty = 1  # Gasta limpia
            elif 'RETIRADA' in texto:
                tipo = 'RETIRADA'
                d_full = 1   # Genera sucia (STOP -> Vertedero)
                d_empty = 0  # No gasta limpia (se la lleva)
            
            return pd.Series([tipo, d_full, d_empty])

        df[['tipo_servicio', 'demand_full', 'demand_empty']] = df.apply(analizar, axis=1)
        return df

    def _crear_matrices(self, nodos):
        size = len(nodos)
        coords = [n['coords'] for n in nodos]
        
        matriz_dist = np.zeros((size, size))
        matriz_tiempo = np.zeros((size, size))
        
        # Cálculo optimizado con numpy (evitar bucles lentos)
        # Para 135 servicios + vertederos es pesado, usamos aproximación rápida primero
        for i in range(size):
            for j in range(size):
                if i != j:
                    try:
                        d = geodesic(coords[i], coords[j]).meters
                        matriz_dist[i][j] = int(d)
                        matriz_tiempo[i][j] = int(d / 11.1) # 40 km/h
                    except:
                        matriz_dist[i][j] = 1000000
                        matriz_tiempo[i][j] = 1000000
                        
        return matriz_dist, matriz_tiempo

    def _procesar_solucion(self, manager, routing, solution, nodos):
        rutas = {}
        empty_dim = routing.GetDimensionOrDie('CajasVacias')
        time_dim = routing.GetDimensionOrDie('Tiempo')
        
        for vehicle_id in range(routing.vehicles()):
            index = routing.Start(vehicle_id)
            ruta = []
            
            # Cajas iniciales
            cajas_inicio = solution.Value(empty_dim.CumulVar(index))
            
            # Saltar rutas vacías
            if routing.IsEnd(solution.Value(routing.NextVar(index))): continue
            
            # Inicio Jornada
            ruta.append({
                'Tipo': 'INICIO', 
                'Direccion': f'Salida Valdemingómez (Carga: {cajas_inicio} vacías)', 
                'Concepto': 'INICIO JORNADA', 
                'Hora Pide': '07:00', 
                'Material': '-'
            })
            
            hora_actual = datetime.strptime("07:00", "%H:%M")
            
            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                nodo = nodos[node_idx]
                
                # Obtener tiempo acumulado (en segundos)
                tiempo_seg = solution.Value(time_dim.CumulVar(index))
                hora_estimada = (datetime.strptime("07:00", "%H:%M") + timedelta(seconds=tiempo_seg)).strftime("%H:%M")
                
                if nodo['tipo'] == 'CLIENTE':
                    ruta.append({
                        'Cliente': nodo['nombre'],
                        'Direccion': nodo['direccion'],
                        'Tipo': nodo['tipo_servicio'],
                        'Concepto': nodo['concepto'],
                        'Material': nodo['material'],
                        'Hora Pide': nodo['hora_pide'], # Hora solicitada
                        'Hora Estimada': hora_estimada, # Hora calculada
                        'lat': nodo['coords'][0], 'lon': nodo['coords'][1]
                    })
                elif nodo['tipo'] == 'VERTEDERO':
                    ruta.append({
                        'Cliente': f"VERTEDERO {nodo['nombre']}", 
                        'Tipo': 'VERTIDO', 
                        'Direccion': 'BASCULAR', 
                        'Concepto': 'IR A VERTEDERO', 
                        'Hora Pide': '-',
                        'Hora Estimada': hora_estimada,
                        'Material': '-'
                    })
                
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