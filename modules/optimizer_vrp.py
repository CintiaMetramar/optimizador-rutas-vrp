"""
Algoritmo VRP Experto - VERSIÓN DEFINITIVA ÁRIDOS Y HORARIOS
- Respeta estrictamente "Hora Pide" (Límite inferior bloqueado).
- Restricción física de chasis: CargaSucia + CargaArido <= 1.
- Nodos automáticos de "Base" para recarga de áridos.
- Formato visual limpio con el Nombre del Cliente destacado.
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
        # Coordenadas reales 
        self.vertederos_reales = {
            'LAGUNA': {'coords': (40.3460, -3.7007), 'nombre': 'Laguna del Marquesado'},
            'VALDEMINGOMEZ': {'coords': (40.3186, -3.6017), 'nombre': 'Valdemingómez'},
            'DERSA': {'coords': (40.4330, -3.5000), 'nombre': 'Dersa (San Fernando)'} 
        }
        self.base = {'coords': (40.3186, -3.6017), 'nombre': 'Base Valdemingómez'} 

    def configurar(self, **kwargs):
        self.parametros = kwargs

    def parse_time_window(self, hora_str):
        """Convierte la hora de texto en un rango estricto de segundos desde las 7:00"""
        if not hora_str or 'flex' in str(hora_str).lower() or 'nan' in str(hora_str).lower() or '-' in str(hora_str):
            return 0, 18000 # Flexible: De 7:00 a 12:00
        
        match = re.search(r'(\d{1,2})[:\.](\d{2})', str(hora_str))
        if match:
            h, m = int(match.group(1)), int(match.group(2))
            if h < 7: h = 7 
            if h > 12: h = 12 
            
            # Segundos exactos desde las 07:00
            segundos_desde_7 = (h - 7) * 3600 + m * 60
            
            # REGLA ESTRICTA: min_sec es la hora exacta (no se puede llegar antes)
            min_sec = segundos_desde_7
            # Damos 1 hora de margen hacia adelante para que tenga viabilidad
            max_sec = min(18000, segundos_desde_7 + 3600) 
            return min_sec, max_sec
            
        return 0, 18000

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
            # 0. BASE DE INICIO
            nodos.append({'tipo': 'BASE', 'coords': self.base['coords'], 'nombre': 'Base', 'demand_full': 0, 'demand_empty': 0, 'demand_arido': 0, 'vertedero_req': 'CUALQUIERA', 'hora_pide': ''})
            
            # 1. CLIENTES
            for idx, row in df_clientes.iterrows():
                nombre_cliente = str(row.get('Cliente', '')).replace('nan', 'Sin Nombre')
                direccion_cliente = str(row.get('Direccion', '')).replace('nan', '')
                concepto_cliente = str(row.get('Concepto', '')).replace('nan', '')
                material_cliente = str(row.get('Material', '')).replace('nan', '')
                hora_pide_cliente = str(row.get('Hora Pide', 'Flexible')).replace('nan', 'Flexible')

                nodos.append({
                    'tipo': 'CLIENTE',
                    'coords': (row['lat'], row['lon']),
                    'nombre': nombre_cliente,
                    'direccion': direccion_cliente,
                    'concepto': concepto_cliente,
                    'tipo_servicio': row['tipo_servicio'],
                    'hora_pide': hora_pide_cliente,
                    'material': material_cliente,
                    'demand_full': int(row['demand_full']),   
                    'demand_empty': int(row['demand_empty']), 
                    'demand_arido': int(row['demand_arido']),
                    'vertedero_req': row['vertedero_req'],
                    'zbe': row['zbe'],
                    'id_original': idx
                })
            
            num_copias = max(len(df_clientes), num_vehiculos * 3)
            vertederos_keys = list(self.vertederos_reales.keys())
            
            # 2. VERTEDEROS VIRTUALES (Para descargar escombro)
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
                    'demand_arido': 0,
                    'vertedero_req': 'CUALQUIERA',
                    'hora_pide': ''
                })

            # 3. BASES VIRTUALES DE RECARGA (Para ir a por Árido)
            for i in range(num_copias):
                nodos.append({
                    'tipo': 'RECARGA_ARIDO',
                    'vertedero_id': 'BASE',
                    'coords': self.base['coords'],
                    'nombre': 'Planta Áridos',
                    'demand_full': 0, 
                    'demand_empty': 0,
                    'demand_arido': 1, # AQUÍ GANA LA CARGA DE ÁRIDO
                    'vertedero_req': 'CUALQUIERA',
                    'hora_pide': ''
                })

            # =========================================================
            # MATRICES
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
                            tiempo_val = int(d / 11.1) + 1200 # +20 min servicio
                        except Exception:
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
            routing.AddDimension(time_callback_index, 3600, 18000, False, "Tiempo")
            time_dim = routing.GetDimensionOrDie("Tiempo")

            # APLICAR HORAS ESTRICTAS
            for i in range(1, size):
                if nodos[i]['tipo'] == 'CLIENTE':
                    idx = manager.NodeToIndex(i)
                    min_s, max_s = self.parse_time_window(nodos[i]['hora_pide'])
                    time_dim.CumulVar(idx).SetRange(int(min_s), int(max_s))

            def count_client_callback(from_index):
                return array_is_client[manager.IndexToNode(from_index)]
            client_count_index = routing.RegisterUnaryTransitCallback(count_client_callback)
            routing.AddDimension(client_count_index, 0, 3, True, "MaxServicios")

            # GESTIÓN FÍSICA DE CARGAS
            def demand_full_callback(from_index):
                return array_demand_full[manager.IndexToNode(from_index)]
            full_idx = routing.RegisterUnaryTransitCallback(demand_full_callback)
            routing.AddDimension(full_idx, 0, 1, True, "CargaSucia")

            def demand_arido_callback(from_index):
                return array_demand_arido[manager.IndexToNode(from_index)]
            arido_idx = routing.RegisterUnaryTransitCallback(demand_arido_callback)
            routing.AddDimension(arido_idx, 0, 1, False, "CargaArido")

            def demand_empty_callback(from_index):
                return array_demand_empty[manager.IndexToNode(from_index)]
            empty_idx = routing.RegisterUnaryTransitCallback(demand_empty_callback)
            routing.AddDimension(empty_idx, 0, 5, False, "CajasVacias")
            
            # REGLA DE CHASIS: Sucia + Árido NUNCA puede ser > 1
            solver = routing.solver()
            sucia_dim = routing.GetDimensionOrDie("CargaSucia")
            arido_dim = routing.GetDimensionOrDie("CargaArido")
            empty_dim = routing.GetDimensionOrDie("CajasVacias")
            
            for i in range(size):
                idx = manager.NodeToIndex(i)
                solver.Add(sucia_dim.CumulVar(idx) + arido_dim.CumulVar(idx) <= 1)

            for v in range(num_vehiculos):
                empty_dim.CumulVar(routing.Start(v)).SetRange(0, 5)
                # Permitimos que salgan de la base ya cargados con árido a las 7:00
                arido_dim.CumulVar(routing.Start(v)).SetRange(0, 1)

            for i in range(1, size):
                idx = manager.NodeToIndex(i)
                if nodos[i]['tipo'] in ['VERTEDERO', 'RECARGA_ARIDO']:
                    routing.AddDisjunction([idx], 0) 
                else:
                    routing.AddDisjunction([idx], 1000000)

            search_params = pywrapcp.DefaultRoutingSearchParameters()
            search_params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
            search_params.time_limit.seconds = 35 

            solution = routing.SolveWithParameters(search_params)

            if solution:
                return self._procesar_solucion(manager, routing, solution, nodos, nombres_conductores)
            else:
                st.error("❌ No hay solución. O las horas son incompatibles físicamente, o no hay vertederos cerca para descargar el escombro antes de cargar el árido.")
                return {}

        except Exception as e:
            st.error(f"Error principal: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        def analizar(row):
            cliente = str(row.get('Cliente', '')).upper()
            material = str(row.get('Material', '')).upper()
            concepto = str(row.get('Concepto', '')).upper()
            lat, lon = row.get('lat', 0), row.get('lon', 0)
            
            vertedero_req = 'CUALQUIERA'
            if any(c in cliente for c in ['LICUAS', 'FCC', 'SANYAL', 'ACCIONA', 'TRADIVEL']):
                vertedero_req = 'VALDEMINGOMEZ'
            elif 'TRANSHELMUT' in cliente and 'TRADIVEL' not in cliente:
                vertedero_req = 'DERSA'

            zbe = "🟢 ZBE" if (40.39 < lat < 40.45 and -3.72 < lon < -3.66) else ""

            es_arido = any(a in material for a in ['ARIDO', 'ÁRIDO', 'RIO', 'MIGA', 'GRAVA', 'ZAHORRA'])
            es_basculado = 'BASCULADO' in material
            
            tipo = 'RETIRADA'
            d_full = 0; d_empty = 0; d_arido = 0
            
            if es_arido:
                if 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO ÁRIDO'
                    d_full = 0; d_empty = -1; d_arido = -1
                elif 'CAMBIO' in concepto:
                    tipo = 'CAMBIO CON ÁRIDO'
                    d_full = 1; d_empty = 0; d_arido = -1
                elif 'DEPOSITO' in concepto:
                    tipo = 'DEPÓSITO ÁRIDO'
                    d_full = 0; d_empty = 0; d_arido = -1
                elif 'RETIRADA' in concepto:
                    if es_basculado:
                        tipo = 'RETIRADA ÁRIDO BASCULADO'
                        d_full = 1; d_empty = -1; d_arido = -1
                    else:
                        tipo = 'RETIRADA ÁRIDO DEJA CAJA'
                        d_full = 1; d_empty = 0; d_arido = -1
            else:
                if 'CAMBIO' in concepto:
                    tipo = 'CAMBIO'
                    d_full = 1; d_empty = 1; d_arido = 0
                elif 'DEPOSITO' in concepto or 'ENTREGA' in concepto:
                    tipo = 'DEPOSITO'
                    d_full = 0; d_empty = 1; d_arido = 0
                elif 'RETIRADA' in concepto or 'RECOGIDA' in concepto:
                    tipo = 'RETIRADA'
                    d_full = 1; d_empty = 0; d_arido = 0
                elif 'SUMINISTRO' in concepto:
                    tipo = 'SUMINISTRO'
                    d_full = 0; d_empty = -1; d_arido = 0
            
            return pd.Series([tipo, d_full, d_empty, d_arido, vertedero_req, zbe])

        df[['tipo_servicio', 'demand_full', 'demand_empty', 'demand_arido', 'vertedero_req', 'zbe']] = df.apply(analizar, axis=1)
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
                'Concepto': '🏁 ORIGEN DEL VIAJE', 
                'Hora Pide': '07:00', 
                'Material': '-'
            })
            
            while not routing.IsEnd(index):
                node_idx = manager.IndexToNode(index)
                nodo = nodos[node_idx]
                
                tiempo_seg = solution.Value(time_dim.CumulVar(index))
                hora_estimada = (datetime.strptime("07:00", "%H:%M") + timedelta(seconds=tiempo_seg)).strftime("%H:%M")
                
                if nodo['tipo'] == 'CLIENTE':
                    hora_m = str(nodo['hora_pide'])
                    tag_zbe = f" {nodo['zbe']}" if nodo['zbe'] else ""
                    
                    # AQUÍ SE ARREGLA EL FORMATO DEL WHATSAPP Y EXCEL
                    nombre_formateado = f"{nodo['nombre']} {tag_zbe}".strip()
                    concepto_formateado = f"CLIENTE: {nombre_formateado} - {nodo['tipo_servicio']}"
                    
                    ruta.append({
                        'Cliente': nombre_formateado,
                        'Direccion': str(nodo['direccion']),
                        'Tipo': str(nodo['tipo_servicio']),
                        'Concepto': concepto_formateado, # Esto sale destacado en WhatsApp
                        'Material': str(nodo['material']),
                        'Hora Pide': hora_m,
                        'Hora Estimada': hora_estimada,
                        'lat': nodo['coords'][0], 'lon': nodo['coords'][1]
                    })
                elif nodo['tipo'] == 'VERTEDERO':
                    ruta.append({
                        'Cliente': f"VERTEDERO {nodo['nombre']}", 
                        'Tipo': 'VERTIDO', 
                        'Direccion': 'Descargar Escombro', 
                        'Concepto': '🏁 BASCULAR (Fin de ciclo)', 
                        'Hora Pide': '-',
                        'Hora Estimada': hora_estimada,
                        'Material': '-'
                    })
                elif nodo['tipo'] == 'RECARGA_ARIDO':
                    ruta.append({
                        'Cliente': f"PLANTA {nodo['nombre']}", 
                        'Tipo': 'CARGA ÁRIDO', 
                        'Direccion': 'Cargar Material', 
                        'Concepto': '🏭 PASO POR BASE (Carga Árido)', 
                        'Hora Pide': '-',
                        'Hora Estimada': hora_estimada,
                        'Material': '-'
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