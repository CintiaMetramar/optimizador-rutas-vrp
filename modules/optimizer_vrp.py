"""
Algoritmo VRP Experto (Planificación Tarde -> Ejecución 7:00 a 10:00 AM)
- Ventana de tiempo estricta matutina.
- Máximo 3 servicios por conductor.
- Lógica avanzada de Áridos y ZBE.
- Vertederos específicos (Dersa, Valdemingómez).
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
        # Coordenadas reales (Ajusta Dersa si es necesario)
        self.vertederos_reales = {
            'LAGUNA': {'coords': (40.3460, -3.7007), 'nombre': 'Laguna del Marquesado'},
            'VALDEMINGOMEZ': {'coords': (40.3186, -3.6017), 'nombre': 'Valdemingómez'},
            'DERSA': {'coords': (40.4330, -3.5000), 'nombre': 'Dersa (San Fernando)'} 
        }
        self.base = {'coords': (40.3186, -3.6017), 'nombre': 'Base Valdemingómez'} 

    def configurar(self, **kwargs):
        self.parametros = kwargs

    def optimizar(self, df_input):
        try:
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            df_clientes = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df_clientes) == 0: 
                st.warning("⚠️ No hay direcciones válidas.")
                return {}

            num_vehiculos = int(self.parametros.get('vehiculos_c', 20))
            
            nodos = []
            nodos.append({'tipo': 'BASE', 'coords': self.base['coords'], 'nombre': 'Base', 'demand_full': 0, 'demand_empty': 0, 'vertedero_req': 'CUALQUIERA'})
            
            for idx, row in df_clientes.iterrows():
                nodos.append({
                    'tipo': 'CLIENTE',
                    'coords': (row['lat'], row['lon']),
                    'nombre': row['Cliente'],
                    'direccion': row['Direccion'],
                    'concepto': row['Concepto'],
                    'tipo_servicio': row['tipo_servicio'],
                    'hora_pide': row.get('Hora Pide', '07:00'),
                    'material': row.get('Material', ''),
                    'demand_full': row['demand_full'],   
                    'demand_empty': row['demand_empty'], 
                    'vertedero_req': row['vertedero_req'],
                    'zbe': row['zbe'],
                    'id_original': idx
                })
            
            num_copias = max(len(df_clientes), num_vehiculos * 3)
            vertederos_keys = list(self.vertederos_reales.keys())
            
            for i in range(num_copias):
                v_key = vertederos_keys[i % len(vertederos_keys)]
                v_data = self.vertederos_reales[v_key]
                
                nodos.append({
                    'tipo': 'VERTEDERO',
                    'vertedero_id': v_key,
                    'coords': v_data['coords'],
                    'nombre': v_data['nombre'],
                    'demand_full': -1, 
                    'demand_empty': 0,
                    'vertedero_req': 'CUALQUIERA'
                })

            matriz_dist, matriz_tiempo = self._crear_matrices(nodos)
            
            manager = pywrapcp.RoutingIndexManager(len(nodos), num_vehiculos, 0)
            routing = pywrapcp.RoutingModel(manager)

            # A. Coste Distancia + RESTRICCIÓN DE VERTEDERO POR CLIENTE
            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                coste = matriz_dist[from_node][to_node]
                
                if nodos[from_node]['tipo'] == 'CLIENTE' and nodos[to_node]['tipo'] == 'VERTEDERO':
                    req = nodos[from_node]['vertedero_req']
                    if req != 'CUALQUIERA' and nodos[to_node]['vertedero_id'] != req:
                        return coste + 1000000 
                return coste

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # B. LÍMITE DE 3 SERVICIOS MÁXIMO
            def count_client_callback(from_index):
                if nodos[manager.IndexToNode(from_index)]['tipo'] == 'CLIENTE':
                    return 1
                return 0
            
            client_count_index = routing.RegisterUnaryTransitCallback(count_client_callback)
            routing.AddDimension(
                client_count_index,
                0,
                3, # MÁXIMO 3 SERVICIOS POR CAMIÓN
                True,
                "MaxServicios"
            )

            # C. TIEMPO MATUTINO ESTRICTO (7:00 a 10:00/11:00)
            def time_callback(from_index, to_index):
                # Viaje + 20 min servicio (1200 seg)
                return matriz_tiempo[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)] + 1200
            
            time_callback_index = routing.RegisterTransitCallback(time_callback)
            routing.AddDimension(
                time_callback_index, 
                1800, # Slack: Permitir hasta 30 mins de espera si llega muy pronto
                14400, # Max jornada: 4 horas (14400 seg). De 7:00 a 11:00 tope absoluto.
                False, 
                "Tiempo"
            )

            # D. GESTIÓN DE CAJAS LLENAS (Capacidad = 1)
            def demand_full_callback(from_index):
                return nodos[manager.IndexToNode(from_index)]['demand_full']

            full_callback_index = routing.RegisterUnaryTransitCallback(demand_full_callback)
            routing.AddDimensionWithVehicleCapacity(full_callback_index, 0, [1]*num_vehiculos, True, "CargaSucia")

            # E. GESTIÓN DE CAJAS VACÍAS (Capacidad = 5)
            def demand_empty_callback(from_index):
                return nodos[manager.IndexToNode(from_index)]['demand_empty']

            empty_callback_index = routing.RegisterUnaryTransitCallback(demand_empty_callback)
            routing.AddDimensionWithVehicleCapacity(empty_callback_index, 0, [5]*num_vehiculos, False, "CajasVacias")
            
            empty_dim = routing.GetDimensionOrDie("CajasVacias")
            for v in range(num_vehiculos):
                empty_dim.CumulVar(routing.Start(v)).SetRange(0, 5)

            # F. Opcionalidad de Vertederos y Obligación de Clientes
            for i in range(1, len(nodos)):
                idx = manager.NodeToIndex(i)
                if nodos[i]['tipo'] == 'VERTEDERO':
                    routing.AddDisjunction([idx], 0) 
                else:
                    routing.AddDisjunction([idx], 1000000)

            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 45

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, nodos)
            else:
                st.error("❌ No se encontró solución. Es posible que 3 servicios en la franja de 7:00 a 10:00 sean inviables por distancia. Intenta subir los vehículos.")
                return {}

        except Exception as e:
            st.error(f"Error crítico: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        """Traduce la operativa de Áridos y Reglas de Clientes"""
        def analizar(row):
            cliente = str(row.get('Cliente', '')).upper()
            material = str(row.get('Material', '')).upper()
            concepto = str(row.get('Concepto', '')).upper()
            lat, lon = row.get('lat', 0), row.get('lon', 0)
            
            # Reglas de Vertedero por Cliente
            vertedero_req = 'CUALQUIERA'
            if any(c in cliente for c in ['LICUAS', 'FCC', 'SANYAL', 'ACCIONA', 'TRADIVEL']):
                vertedero_req = 'VALDEMINGOMEZ'
            elif 'TRANSHELMUT' in cliente and 'TRADIVEL' not in cliente:
                vertedero_req = 'DERSA'

            # Detección de ZBE (Madrid Central)
            zbe = "🟢 ZBE" if (40.39 < lat < 40.45 and -3.72 < lon < -3.66) else ""

            # Lógica de Áridos y Cajas
            es_arido = any(a in material for a in ['ARIDO', 'ÁRIDO', 'RIO', 'MIGA', 'GRAVA', 'ZAHORRA'])
            es_basculado = 'BASCULADO' in material
            
            tipo = 'RETIRADA'
            d_full = 0 
            d_empty = 0 
            
            if es_arido:
                if 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO ÁRIDO'
                    d_full = 0
                    d_empty = -1 
                elif 'CAMBIO' in concepto:
                    tipo = 'CAMBIO CON ÁRIDO'
                    d_full = 1   
                    d_empty = 1  
                elif 'DEPOSITO' in concepto:
                    tipo = 'DEPÓSITO ÁRIDO'
                    d_full = 0
                    d_empty = 1  
                elif 'RETIRADA' in concepto:
                    if es_basculado:
                        tipo = 'RETIRADA ÁRIDO (BASCULADO)'
                        d_full = 1   
                        d_empty = -1 
                    else:
                        tipo = 'RETIRADA ÁRIDO (DEJA CAJA)'
                        d_full = 1   
                        d_empty = 1  
            else:
                if 'CAMBIO' in concepto:
                    tipo = 'CAMBIO'
                    d_full = 1; d_empty = 1
                elif 'DEPOSITO' in concepto or 'ENTREGA' in concepto:
                    tipo = 'DEPOSITO'
                    d_full = 0; d_empty = 1
                elif 'RETIRADA' in concepto or 'RECOGIDA' in concepto:
                    tipo = 'RETIRADA'
                    d_full = 1; d_empty = 0
                elif 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO'
                    d_full = 0; d_empty = -1
            
            return pd.Series([tipo, d_full, d_empty, vertedero_req, zbe])

        df[['tipo_servicio', 'demand_full', 'demand_empty', 'vertedero_req', 'zbe']] = df.apply(analizar, axis=1)
        return df

    def _crear_matrices(self, nodos):
        size = len(nodos)
        coords = [n['coords'] for n in nodos]
        matriz_dist = np.zeros((size, size))
        matriz_tiempo = np.zeros((size, size))
        
        for i in range(size):
            for j in range(size):
                if i != j:
                    try:
                        d = geodesic(coords[i], coords[j]).meters
                        matriz_dist[i][j] = int(d)
                        # Cálculo a 40 km/h para simular el tráfico madrileño real de la mañana
                        matriz_tiempo[i][j] = int(d / 11.1) 
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
            
            cajas_inicio = solution.Value(empty_dim.CumulVar(index))
            if routing.IsEnd(solution.Value(routing.NextVar(index))): continue
            
            ruta.append({
                'Tipo': 'INICIO', 
                'Direccion': f'Base Valdemingómez (Sale con {cajas_inicio} vacías)', 
                'Concepto': 'INICIO 07:00', 
                'Hora Pide': '07:00', 
                'Material': '-'
            })
            
            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                nodo = nodos[node_idx]
                
                tiempo_seg = solution.Value(time_dim.CumulVar(index))
                hora_estimada = (datetime.strptime("07:00", "%H:%M") + timedelta(seconds=tiempo_seg)).strftime("%H:%M")
                
                if nodo['tipo'] == 'CLIENTE':
                    hora_m = nodo['hora_pide']
                    if len(ruta) == 1 and (hora_m == 'Flexible' or hora_m == ''):
                        hora_m = '07:00'
                        
                    tag_zbe = f" {nodo['zbe']}" if nodo['zbe'] else ""
                    
                    ruta.append({
                        'Cliente': nodo['nombre'] + tag_zbe,
                        'Direccion': nodo['direccion'],
                        'Tipo': nodo['tipo_servicio'],
                        'Concepto': nodo['concepto'],
                        'Material': nodo['material'],
                        'Hora Pide': hora_m,
                        'Hora Estimada': hora_estimada,
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
                        'num_servicios': sum(1 for s in ruta if s['Tipo'] not in ['INICIO', 'VERTIDO']), 
                        'combustible_estimado_l': 0
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