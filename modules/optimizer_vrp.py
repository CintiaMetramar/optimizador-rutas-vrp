"""
Algoritmo VRP Experto para Cadenas (Skip Loaders)
Lógica: Inventario de Cajas Vacías
- El camión optimiza su carga inicial (0-5 cajas).
- Suministro: Genera caja vacía (+1).
- Depósito/Cambio: Gasta caja vacía (-1).
- Prioriza Vertederos según columna Concepto/Dirección.
"""

import pandas as pd
import numpy as np
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
from geopy.distance import geodesic
import streamlit as st

class OptimizadorVRP:
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
        try:
            # 1. Interpretar Operativa (Depósito, Cambio, Suministro...)
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            # Filtrar solo válidos
            df = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df) == 0: return {}

            # 2. Matriz de Distancias (Incluyendo Vertederos como nodos de paso)
            matriz, puntos, nodos_vertederos = self._crear_matriz(df)
            
            # 3. Configurar OR-Tools
            manager = pywrapcp.RoutingIndexManager(len(matriz), 
                                                 int(self.parametros.get('vehiculos_c', 5)), 
                                                 0) # 0 es el Depósito/Base
            routing = pywrapcp.RoutingModel(manager)

            # --- CALLBACK DE COSTE (Distancia + Penalizaciones) ---
            def cost_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                coste = matriz[from_node][to_node]
                
                # Penalización: Si el cliente pide un vertedero específico
                if 0 < from_node <= len(df):
                    cliente = df.iloc[from_node - 1]
                    target_vertedero = cliente.get('vertedero_target')
                    
                    # Si va a un vertedero incorrecto -> Penalización gigante
                    if target_vertedero == 'VALDEMINGOMEZ' and to_node == nodos_vertederos['LAGUNA']:
                        return coste + 1000000
                    if target_vertedero == 'LAGUNA' and to_node == nodos_vertederos['VALDEMINGOMEZ']:
                        return coste + 1000000
                        
                return coste

            transit_callback_index = routing.RegisterTransitCallback(cost_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # --- DIMENSIÓN DE INVENTARIO (Cajas Vacías) ---
            # Modelamos el flujo de cajas:
            # DEPOSITO: -1 (Dejas una caja)
            # CAMBIO: -1 (Dejas una caja vacía para llevarte la llena)
            # SUMINISTRO: +1 (Al descargar árido, te queda la caja vacía disponible)
            # RETIRADA: 0 (No afecta al stock de vacías, pero requiere viaje a vertedero)
            
            demands = [0] # Base
            demands.extend(df['delta_cajas'].tolist())
            demands.extend([0, 0]) # Vertederos (no cambian stock, solo descargan)

            def demand_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return demands[from_node]

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)

            # Creamos la dimensión con "slack" para permitir que el camión salga con cajas
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index,
                0,  # null capacity slack
                [5] * manager.GetNumberOfVehicles(), # Capacidad máxima de 5 cajas
                False, # <--- IMPORTANTE: False para permitir empezar con >0 cajas
                'InventarioCajas'
            )
            
            # Restricción: El inventario nunca puede ser negativo (no puedes dejar caja si no tienes)
            inventory_dimension = routing.GetDimensionOrDie('InventarioCajas')
            for vehicle_id in range(manager.GetNumberOfVehicles()):
                # Permitimos que la base (inicio) tenga entre 0 y 5 cajas
                index = routing.Start(vehicle_id)
                inventory_dimension.CumulVar(index).SetRange(0, 5)

            # 4. Resolver
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_parameters.time_limit.seconds = 10

            solution = routing.SolveWithParameters(search_parameters)

            if solution:
                return self._procesar_solucion(manager, routing, solution, df, nodos_vertederos)
            else:
                return {}

        except Exception as e:
            st.error(f"Error optimización: {e}")
            return {}

    def _procesar_conceptos(self, df):
        """Traduce 'Concepto' a lógica de cajas (+1 / -1)"""
        def analizar(row):
            texto = (str(row.get('Concepto', '')) + " " + str(row.get('Material', '')) + " " + str(row.get('Direccion', ''))).upper()
            
            # 1. Detectar Vertedero Obligatorio
            vertedero = None
            if 'VALDEMINGOMEZ' in texto or 'VALDEMINGÓMEZ' in texto:
                vertedero = 'VALDEMINGOMEZ'
            elif 'LAGUNA' in texto or 'MARQUESADO' in texto:
                vertedero = 'LAGUNA'

            # 2. Detectar Delta de Cajas (Inventario)
            tipo = 'RETIRADA'
            delta = 0 
            
            if 'SUMINISTRO' in texto or 'ARIDO' in texto:
                tipo = 'SUMINISTRO'
                delta = 1 # Genera +1 caja vacía disponible
            elif 'CAMBIO' in texto:
                tipo = 'CAMBIO'
                delta = -1 # Gasta -1 caja vacía
            elif 'DEPOSITO' in texto or 'ENTREGA' in texto:
                tipo = 'DEPOSITO'
                delta = -1 # Gasta -1 caja vacía
            elif 'RETIRADA' in texto or 'RECOGIDA' in texto:
                tipo = 'RETIRADA'
                delta = 0 # Neutro para vacías (pero ocupa el camión con llena)
            
            return pd.Series([tipo, delta, vertedero])

        df[['tipo_servicio', 'delta_cajas', 'vertedero_target']] = df.apply(analizar, axis=1)
        return df

    def _crear_matriz(self, df):
        puntos = [self.base['coords']] + [(r['lat'], r['lon']) for _, r in df.iterrows()]
        
        # Añadir Vertederos
        idx_base = len(puntos)
        nodos = {}
        
        puntos.append(self.vertederos['LAGUNA']['coords'])
        nodos['LAGUNA'] = idx_base
        
        puntos.append(self.vertederos['VALDEMINGOMEZ']['coords'])
        nodos['VALDEMINGOMEZ'] = idx_base + 1
        
        size = len(puntos)
        matriz = [[0]*size for _ in range(size)]
        
        for i in range(size):
            for j in range(size):
                if i != j:
                    try:
                        matriz[i][j] = int(geodesic(puntos[i], puntos[j]).meters)
                    except:
                        matriz[i][j] = 100000
                        
        return matriz, puntos, nodos

    def _procesar_solucion(self, manager, routing, solution, df, nodos_vertederos):
        rutas = {}
        inv_dim = routing.GetDimensionOrDie('InventarioCajas')
        
        # Mapeo inverso de nodos de vertedero
        vertedero_idx_to_name = {v: k for k, v in nodos_vertederos.items()}
        
        for vehicle_id in range(routing.vehicles()):
            index = routing.Start(vehicle_id)
            ruta = []
            dist = 0
            
            # Ver con cuántas cajas sale
            cajas_inicio = solution.Value(inv_dim.CumulVar(index))
            if routing.IsEnd(solution.Value(routing.NextVar(index))) and cajas_inicio == 0:
                continue # Ruta vacía
                
            ruta.append({'Tipo': 'INICIO', 'Direccion': f'Base - Sale con {cajas_inicio} cajas vacías'})
            
            while not routing.IsEnd(index):
                node = manager.IndexToNode(index)
                
                if 0 < node <= len(df): # Cliente
                    row = df.iloc[node - 1]
                    ruta.append({
                        'Cliente': row['Cliente'],
                        'Direccion': row['Direccion'],
                        'Tipo': row['tipo_servicio'],
                        'Concepto': row.get('Concepto', ''),
                        'lat': row['lat'], 'lon': row['lon']
                    })
                elif node in vertedero_idx_to_name: # Vertedero
                    nombre = vertedero_idx_to_name[node]
                    ruta.append({'Cliente': f'VERTEDERO {nombre}', 'Tipo': 'VERTIDO', 'Direccion': 'Descarga'})
                
                prev = index
                index = solution.Value(routing.NextVar(index))
                dist += routing.GetArcCostForVehicle(prev, index, vehicle_id)
            
            if len(ruta) > 1:
                rutas[f"Vehículo {vehicle_id + 1}"] = {
                    'servicios': ruta,
                    'estadisticas': {
                        'distancia_total_km': dist / 1000,
                        'tiempo_total_min': (dist / 1000 / 30) * 60,
                        'num_servicios': len(ruta) - 1, # Restar inicio
                        'combustible_estimado_l': (dist / 1000) * 0.35,
                        'combos_detectados': cajas_inicio
                    }
                }
        return rutas
    
    # ... (Mantén aquí las funciones exportar_excel y exportar_kml del código anterior)
    def exportar_excel(self, rutas, df_original):
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            detalle = []
            for vehiculo, datos in rutas.items():
                for orden, serv in enumerate(datos['servicios'], 1):
                    s = serv.copy()
                    s['Vehículo'] = vehiculo
                    s['Orden'] = orden
                    detalle.append(s)
            pd.DataFrame(detalle).to_excel(writer, sheet_name='Detalle Rutas', index=False)
        return output.getvalue()

    def exportar_kml(self, rutas):
        return b""