"""
Algoritmo VRP Experto - LOGÍSTICA DE OBRA REAL
- Solución Anti-Fail: Soft Time Windows (Fases de Mañana)
- 0 Esperas: Límite de slack (espera) a 15 min. No hay camiones parados.
- Inventario Físico y Chasis: (Sucia + Árido <= 1).
- Priorización Comercial (Cliente 2).
"""

import pandas as pd
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.distance import geodesic
import streamlit as st
from datetime import datetime, timedelta
import re

class OptimizadorVRP:
    def __init__(self):
        self.parametros = {}
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
            nombres_conductores = self.parametros.get('nombres_conductores')
            if not nombres_conductores or len(nombres_conductores) != num_vehiculos:
                nombres_conductores = [f"Conductor {i+1}" for i in range(num_vehiculos)]
            
            nodos = []
            nodos.append({'tipo': 'BASE', 'coords': self.base['coords'], 'nombre': 'Base', 'demand_full': 0, 'demand_empty': 0, 'demand_arido': 0, 'vertedero_req': 'CUALQUIERA', 'hora_pide': ''})
            
            for idx, row in df_clientes.iterrows():
                nodos.append({
                    'tipo': 'CLIENTE',
                    'coords': (row['lat'], row['lon']),
                    'nombre': str(row.get('nombre_albaran', 'Sin Nombre')),
                    'comercial': str(row.get('comercial', '')),
                    'direccion': str(row.get('Direccion', '')).replace('nan', ''),
                    'concepto': str(row.get('Concepto', '')).replace('nan', ''),
                    'tipo_servicio': row['tipo_servicio'],
                    'hora_pide': str(row.get('Hora Pide', 'Flexible')).replace('nan', 'Flexible'),
                    'material': str(row.get('Material', '')).replace('nan', ''),
                    'demand_full': int(row['demand_full']),   
                    'demand_empty': int(row['demand_empty']), 
                    'demand_arido': int(row['demand_arido']),
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
                    'tipo': 'VERTEDERO', 'vertedero_id': v_key, 'coords': v_data['coords'],
                    'nombre': v_data['nombre'], 'demand_full': -1, 'demand_empty': 0,
                    'demand_arido': 0, 'vertedero_req': 'CUALQUIERA', 'hora_pide': ''
                })

            for i in range(num_copias):
                nodos.append({
                    'tipo': 'RECARGA_ARIDO', 'vertedero_id': 'BASE', 'coords': self.base['coords'],
                    'nombre': 'Planta Áridos', 'demand_full': 0, 'demand_empty': 0,
                    'demand_arido': 1, 'vertedero_req': 'CUALQUIERA', 'hora_pide': ''
                })

            # =========================================================
            # MATRICES BLINDADAS
            # =========================================================
            size = len(nodos)
            matriz_dist = [[0 for _ in range(size)] for _ in range(size)]
            matriz_tiempo = [[0 for _ in range(size)] for _ in range(size)]
            
            for i in range(size):
                for j in range(size):
                    if i != j:
                        try:
                            d = geodesic(nodos[i]['coords'], nodos[j]['coords']).meters
                            dist_val = int(d)
                            # Tiempo viaje + 15 min servicio en obra
                            tiempo_val = int(d / 11.1) + 900 
                        except:
                            dist_val = 1000000; tiempo_val = 1000000
                            
                        if nodos[i]['tipo'] == 'CLIENTE' and nodos[j]['tipo'] == 'VERTEDERO':
                            req = nodos[i].get('vertedero_req', 'CUALQUIERA')
                            if req != 'CUALQUIERA' and nodos[j].get('vertedero_id') != req:
                                dist_val += 1000000 
                                
                        matriz_dist[i][j] = dist_val
                        matriz_tiempo[i][j] = tiempo_val

            array_demand_full = [int(n.get('demand_full', 0)) for n in nodos]
            array_demand_empty = [int(n.get('demand_empty', 0)) for n in nodos]
            array_demand_arido = [int(n.get('demand_arido', 0)) for n in nodos]
            array_is_client = [1 if n['tipo'] == 'CLIENTE' else 0 for n in nodos]

            manager = pywrapcp.RoutingIndexManager(size, num_vehiculos, 0)
            routing = pywrapcp.RoutingModel(manager)

            def distance_callback(from_index, to_index):
                return matriz_dist[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            def time_callback(from_index, to_index):
                return matriz_tiempo[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)]
            time_callback_index = routing.RegisterTransitCallback(time_callback)
            
            # SLACK = 900s (El camión NO PUEDE esperar más de 15 minutos en ninguna parte)
            routing.AddDimension(time_callback_index, 900, 18000, False, "Tiempo")
            time_dim = routing.GetDimensionOrDie("Tiempo")

            # =========================================================
            # REGLAS DE TIEMPO BLANDAS (Evitan el CP Solver Fail)
            # =========================================================
            for i in range(1, size):
                if nodos[i]['tipo'] == 'CLIENTE':
                    idx = manager.NodeToIndex(i)
                    hora_str = str(nodos[i]['hora_pide']).lower()
                    
                    h = 7 # Por defecto
                    match = re.search(r'(\d{1,2})[:\.](\d{2})', hora_str)
                    if match: h = int(match.group(1))
                    
                    if 'flex' in hora_str or hora_str == 'nan' or hora_str == '':
                        h = 8 # Los flexibles se empujan a partir de las 8:00
                        
                    if h < 8:
                        # Fase 1: Antes de las 8 (Empieza pronto, penalizamos si se hace tarde)
                        time_dim.SetCumulVarSoftUpperBound(idx, 3600, 10) # 08:00
                    elif h == 8:
                        # Fase 2: A partir de las 8 (No debe llegar antes)
                        # Penalización brutal (100) si llega antes de las 8:00 (3600s)
                        time_dim.SetCumulVarSoftLowerBound(idx, 3600, 100)
                    else:
                        # Fase 3: A partir de las 9 (No debe llegar antes, no importa si tarde)
                        # Penalización brutal (100) si llega antes de las 9:00 (7200s)
                        time_dim.SetCumulVarSoftLowerBound(idx, 7200, 100)

            def count_client_callback(from_index):
                return array_is_client[manager.IndexToNode(from_index)]
            client_count_index = routing.RegisterUnaryTransitCallback(count_client_callback)
            routing.AddDimension(client_count_index, 0, 3, True, "MaxServicios")

            def demand_full_callback(from_index):
                return array_demand_full[manager.IndexToNode(from_index)]
            routing.AddDimension(routing.RegisterUnaryTransitCallback(demand_full_callback), 0, 1, True, "CargaSucia")

            def demand_arido_callback(from_index):
                return array_demand_arido[manager.IndexToNode(from_index)]
            routing.AddDimension(routing.RegisterUnaryTransitCallback(demand_arido_callback), 0, 1, False, "CargaArido")

            def demand_empty_callback(from_index):
                return array_demand_empty[manager.IndexToNode(from_index)]
            routing.AddDimension(routing.RegisterUnaryTransitCallback(demand_empty_callback), 0, 5, False, "CajasVacias")
            
            # RESTRICCIÓN DE CHASIS: Sucia + Árido NUNCA > 1
            solver = routing.solver()
            sucia_dim = routing.GetDimensionOrDie("CargaSucia")
            arido_dim = routing.GetDimensionOrDie("CargaArido")
            empty_dim = routing.GetDimensionOrDie("CajasVacias")
            
            for i in range(size):
                idx = manager.NodeToIndex(i)
                solver.Add(sucia_dim.CumulVar(idx) + arido_dim.CumulVar(idx) <= 1)

            # INVENTARIO INICIAL
            for v in range(num_vehiculos):
                empty_dim.CumulVar(routing.Start(v)).SetRange(0, 5)
                arido_dim.CumulVar(routing.Start(v)).SetRange(0, 1) # Puede salir cargado con Árido a las 7:00

            for i in range(1, size):
                idx = manager.NodeToIndex(i)
                if nodos[i]['tipo'] in ['VERTEDERO', 'RECARGA_ARIDO']:
                    routing.AddDisjunction([idx], 0) 
                else:
                    routing.AddDisjunction([idx], 1000000)

            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 30 

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, nodos, nombres_conductores)
            else:
                st.error("❌ No hay solución. O las distancias son inabarcables, o faltan vertederos cerca para descargar.")
                return {}

        except Exception as e:
            st.error(f"Error principal: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        def analizar(row):
            c1 = str(row.get('Cliente 1', row.get('Cliente', ''))).strip().upper()
            c2 = str(row.get('Cliente 2', '')).strip().upper()
            
            if c1 == 'NAN': c1 = ''
            if c2 == 'NAN': c2 = ''
            
            nombre_albaran = c2 if c2 else c1
            if not nombre_albaran: nombre_albaran = 'SIN NOMBRE'
                
            comercial = c1 if c2 else ""
            cliente_contexto = c1 + " " + c2
            
            vertedero_req = 'CUALQUIERA'
            if any(c in cliente_contexto for c in ['LICUAS', 'FCC', 'SANYAL', 'ACCIONA', 'TRADIVEL']):
                vertedero_req = 'VALDEMINGOMEZ'
            elif 'TRANSHELMUT' in cliente_contexto and 'TRADIVEL' not in cliente_contexto:
                vertedero_req = 'DERSA'

            lat, lon = row.get('lat', 0), row.get('lon', 0)
            zbe = "🟢 ZBE" if (40.39 < lat < 40.45 and -3.72 < lon < -3.66) else ""

            material = str(row.get('Material', '')).upper()
            concepto = str(row.get('Concepto', '')).upper()

            es_arido = any(a in material for a in ['ARIDO', 'ÁRIDO', 'RIO', 'MIGA', 'GRAVA', 'ZAHORRA'])
            es_basculado = 'BASCULADO' in material
            
            tipo = 'RETIRADA'
            d_full = 0; d_empty = 0; d_arido = 0
            
            # FÍSICA DE CARGAS
            if es_arido:
                if 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO ÁRIDO'; d_full = 0; d_empty = 1; d_arido = -1
                elif 'CAMBIO' in concepto:
                    tipo = 'CAMBIO CON ÁRIDO'; d_full = 1; d_empty = 0; d_arido = -1
                elif 'DEPOSITO' in concepto:
                    tipo = 'DEPÓSITO ÁRIDO'; d_full = 0; d_empty = 0; d_arido = -1
                elif 'RETIRADA' in concepto:
                    if es_basculado:
                        tipo = 'RETIRADA ÁRIDO BASCULADO'; d_full = 1; d_empty = 1; d_arido = -1
                    else:
                        tipo = 'RETIRADA ÁRIDO DEJA CAJA'; d_full = 1; d_empty = 0; d_arido = -1
            else:
                if 'CAMBIO' in concepto:
                    tipo = 'CAMBIO'; d_full = 1; d_empty = -1; d_arido = 0
                elif 'DEPOSITO' in concepto or 'ENTREGA' in concepto:
                    tipo = 'DEPOSITO'; d_full = 0; d_empty = -1; d_arido = 0
                elif 'RETIRADA' in concepto or 'RECOGIDA' in concepto:
                    tipo = 'RETIRADA'; d_full = 1; d_empty = 0; d_arido = 0
                elif 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO'; d_full = 0; d_empty = 1; d_arido = 0
            
            return pd.Series([tipo, d_full, d_empty, d_arido, vertedero_req, zbe, nombre_albaran, comercial])

        df[['tipo_servicio', 'demand_full', 'demand_empty', 'demand_arido', 'vertedero_req', 'zbe', 'nombre_albaran', 'comercial']] = df.apply(analizar, axis=1)
        return df

    def _procesar_solucion(self, manager, routing, solution, nodos, nombres_conductores):
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
                'Concepto': '🏁 ORIGEN DEL VIAJE', 'Hora Pide': '07:00', 'Material': '-'
            })
            
            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                nodo = nodos[node_idx]
                
                tiempo_seg = solution.Value(time_dim.CumulVar(index))
                hora_estimada = (datetime.strptime("07:00", "%H:%M") + timedelta(seconds=tiempo_seg)).strftime("%H:%M")
                
                if nodo['tipo'] == 'CLIENTE':
                    hora_m = str(nodo['hora_pide'])
                    tag_zbe = f" {nodo['zbe']}" if nodo['zbe'] else ""
                    
                    nombre_formateado = f"{nodo['nombre']} {tag_zbe}".strip()
                    nota_comercial = f" (Por: {nodo['comercial']})" if nodo.get('comercial') else ""
                    concepto_formateado = f"CLIENTE: {nombre_formateado}{nota_comercial} - {nodo['tipo_servicio']}"
                    
                    ruta.append({
                        'Cliente': nombre_formateado, 'Direccion': str(nodo['direccion']),
                        'Tipo': str(nodo['tipo_servicio']), 'Concepto': concepto_formateado,
                        'Material': str(nodo['material']), 'Hora Pide': hora_m,
                        'Hora Estimada': hora_estimada, 'lat': nodo['coords'][0], 'lon': nodo['coords'][1]
                    })
                elif nodo['tipo'] == 'VERTEDERO':
                    ruta.append({
                        'Cliente': f"VERTEDERO {nodo['nombre']}", 'Tipo': 'VERTIDO', 
                        'Direccion': 'Descargar Escombro', 'Concepto': '🏁 BASCULAR (Fin de ciclo)', 
                        'Hora Pide': '-', 'Hora Estimada': hora_estimada, 'Material': '-'
                    })
                elif nodo['tipo'] == 'RECARGA_ARIDO':
                    ruta.append({
                        'Cliente': f"PLANTA {nodo['nombre']}", 'Tipo': 'CARGA ÁRIDO', 
                        'Direccion': 'Cargar Material', 'Concepto': '🏭 PASO POR BASE (Carga Árido)', 
                        'Hora Pide': '-', 'Hora Estimada': hora_estimada, 'Material': '-'
                    })
                
                index = solution.Value(routing.NextVar(index))
            
            if len(ruta) > 1:
                nombre_c = nombres_conductores[vehicle_id] if vehicle_id < len(nombres_conductores) else f"Conductor Extra {vehicle_id}"
                rutas[f"🚚 {nombre_c}"] = {
                    'servicios': ruta,
                    'estadisticas': {
                        'distancia_total_km': 0, 'tiempo_total_min': 0, 
                        'num_servicios': sum(1 for s in ruta if s['Tipo'] not in ['INICIO', 'VERTIDO', 'CARGA ÁRIDO']), 
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