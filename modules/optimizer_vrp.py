"""
Algoritmo VRP Avanzado para Portacontenedores de Cadenas (Skip Loaders)
Lógica específica: 
- Gestión de flujos: Suministro -> Genera Vacío -> Permite Depósito
- Vertederos específicos (Valdemingómez vs Laguna)
- Capacidad de apilamiento
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
        # Vertederos con sus coordenadas reales
        self.vertederos = {
            'LAGUNA': {'coords': (40.3460, -3.7007), 'nombre': 'Laguna del Marquesado'},
            'VALDEMINGOMEZ': {'coords': (40.3186, -3.6017), 'nombre': 'Valdemingómez'}
        }
        self.base = {'coords': (40.4168, -3.7038), 'nombre': 'Base'} 

    def configurar(self, **kwargs):
        self.parametros = kwargs

    def optimizar(self, df_input):
        try:
            # 1. Preparar datos y detectar lógica de negocio
            df = df_input.copy()
            df = self._procesar_logica_negocio(df)
            
            # Filtrar válidos
            df = df[df['geocodificado'] == True].reset_index(drop=True)
            if len(df) == 0: return {}

            # 2. Crear matriz de distancias
            # La matriz incluirá: [Base, Cliente 1...N, Vertedero Laguna, Vertedero Vald]
            matriz, localizaciones, nodos_vertedero = self._crear_matriz_avanzada(df)
            
            # 3. Datos para OR-Tools
            data = self._preparar_modelo_datos(df, matriz, nodos_vertedero)
            
            # 4. Configurar Routing
            manager = pywrapcp.RoutingIndexManager(len(matriz), data['num_vehicles'], data['depot'])
            routing = pywrapcp.RoutingModel(manager)

            # Callback de Coste (Distancia + Penalizaciones por Vertedero incorrecto)
            def cost_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                coste = matriz[from_node][to_node]
                
                # --- LÓGICA EXPERTA: Restricción de Vertedero ---
                # Si venimos de un cliente (from_node <= len(df)) que requiere Valdemingómez
                # y vamos a un vertedero que NO es Valdemingómez -> Penalización brutal
                if 0 < from_node <= len(df):
                    cliente = df.iloc[from_node - 1]
                    destino_es_vertedero = to_node in nodos_vertedero.values()
                    
                    if cliente['tipo_servicio'] in ['RETIRADA', 'CAMBIO'] and destino_es_vertedero:
                        pref_vertedero = cliente.get('vertedero_preferido', 'CUALQUIERA')
                        
                        # Si cliente exige Valdemingómez y vamos a Laguna
                        if pref_vertedero == 'VALDEMINGOMEZ' and to_node == nodos_vertedero['LAGUNA']:
                             return coste + 100000 # Penalización prohibitiva
                        
                        # Si cliente exige Laguna y vamos a Valdemingómez
                        if pref_vertedero == 'LAGUNA' and to_node == nodos_vertedero['VALDEMINGOMEZ']:
                             return coste + 100000

                return coste

            transit_callback_index = routing.RegisterTransitCallback(cost_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # --- DIMENSIÓN DE CAPACIDAD (Cajas Vacías) ---
            # Suministro: -1 (Genera vacío) | Depósito: +1 (Gasta vacío) | Cambio: 0
            def demand_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return data['demands'][from_node]

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
            
            # Capacidad de 5 cajas vacías apiladas
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index,
                0,  # Null capacity slack
                data['vehicle_capacities'],
                True,  # Start cumul to zero
                'CapacidadCajas'
            )

            # Búsqueda
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            search_parameters.time_limit.seconds = 15

            solution = routing.SolveWithParameters(search_parameters)

            if solution:
                return self._procesar_solucion(manager, routing, solution, df, localizaciones)
            else:
                return {}

        except Exception as e:
            st.error(f"Error en optimización: {str(e)}")
            return {}

    def _procesar_logica_negocio(self, df):
        """Interpreta la operativa real de Cadenas"""
        def analizar_fila(row):
            texto = (str(row.get('Concepto', '')) + " " + str(row.get('Material', '')) + " " + str(row.get('Direccion', ''))).upper()
            
            # 1. Detectar Vertedero Preferido
            vertedero = 'CUALQUIERA'
            if 'VALDEMINGOMEZ' in texto or 'VALDEMINGÓMEZ' in texto:
                vertedero = 'VALDEMINGOMEZ'
            elif 'LAGUNA' in texto or 'MARQUESADO' in texto:
                vertedero = 'LAGUNA'
            
            # 2. Detectar Tipo y Demanda de Cajas Vacías
            # Demanda positiva = Gasta cajas vacías
            # Demanda negativa = Genera cajas vacías (o libera hueco)
            
            tipo = 'RETIRADA'
            demanda = 0 # Cambio por defecto
            
            if 'SUMINISTRO' in texto or 'ARIDO' in texto:
                tipo = 'SUMINISTRO'
                demanda = -1 # Al descargar árido, genero 1 caja vacía disponible
            elif 'CAMBIO' in texto:
                tipo = 'CAMBIO'
                demanda = 0 # Dejo 1, cojo 1
            elif 'DEPOSITO' in texto or 'ENTREGA' in texto:
                tipo = 'DEPOSITO'
                demanda = 1 # Gasto 1 caja vacía
            elif 'RETIRADA' in texto or 'RECOGIDA' in texto:
                tipo = 'RETIRADA'
                demanda = 0 # No gasta 'caja vacía' per se, ocupa el camión entero (gestionado por otra restricción o simple flujo)
            
            return pd.Series([tipo, demanda, vertedero])

        df[['tipo_servicio', 'demanda_cajas', 'vertedero_preferido']] = df.apply(analizar_fila, axis=1)
        return df

    def _crear_matriz_avanzada(self, df):
        """Crea matriz incluyendo los vertederos como nodos visitables"""
        puntos = [self.base['coords']]
        
        # Clientes
        for _, row in df.iterrows():
            puntos.append((row['lat'], row['lon']))
            
        # Añadir Vertederos al final de la lista de nodos
        idx_base = len(puntos)
        nodos_vertedero = {}
        
        puntos.append(self.vertederos['LAGUNA']['coords'])
        nodos_vertedero['LAGUNA'] = idx_base
        
        puntos.append(self.vertederos['VALDEMINGOMEZ']['coords'])
        nodos_vertedero['VALDEMINGOMEZ'] = idx_base + 1
        
        # Calcular distancias
        size = len(puntos)
        matriz = [[0 for _ in range(size)] for _ in range(size)]
        
        for i in range(size):
            for j in range(size):
                if i != j:
                    try:
                        dist = geodesic(puntos[i], puntos[j]).meters
                        matriz[i][j] = int(dist)
                    except:
                        matriz[i][j] = 100000 # Penalizar errores
                        
        return matriz, puntos, nodos_vertedero

    def _preparar_modelo_datos(self, df, matriz, nodos_vertedero):
        # Demanda de cajas:
        # Base = 0
        # Clientes = columna 'demanda_cajas'
        # Vertederos = 0 (Son puntos de paso/descarga)
        
        demands = [0] # Base
        demands.extend(df['demanda_cajas'].tolist())
        demands.extend([0, 0]) # Los 2 vertederos tienen demanda 0 de cajas
        
        num_vehiculos = int(self.parametros.get('vehiculos_c', 5))
        
        return {
            'distance_matrix': matriz,
            'demands': demands,
            'vehicle_capacities': [5] * num_vehiculos, # 5 huecos de capacidad
            'num_vehicles': num_vehiculos,
            'depot': 0
        }

    def _procesar_solucion(self, manager, routing, solution, df, localizaciones):
        rutas = {}
        
        # Indices de los vertederos en la lista total
        idx_laguna = len(df) + 1
        idx_valde = len(df) + 2
        
        for vehicle_id in range(routing.vehicles()):
            index = routing.Start(vehicle_id)
            ruta_actual = []
            distancia_ruta = 0
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                
                # Identificar qué es este nodo
                info_nodo = {}
                
                if node_index == 0:
                    pass # Base
                elif node_index <= len(df):
                    # Es un Cliente
                    row = df.iloc[node_index - 1]
                    info_nodo = {
                        'Cliente': row['Cliente'],
                        'Direccion': row['Direccion'],
                        'Tipo': row['tipo_servicio'],
                        'Concepto': row.get('Concepto', ''),
                        'lat': row['lat'], 'lon': row['lon']
                    }
                elif node_index == idx_laguna:
                    info_nodo = {'Cliente': 'VERTEDERO LAGUNA', 'Tipo': 'VERTIDO', 'Direccion': 'Laguna del Marquesado', 'lat': 40.3460, 'lon': -3.7007}
                elif node_index == idx_valde:
                    info_nodo = {'Cliente': 'VERTEDERO VALDEMINGOMEZ', 'Tipo': 'VERTIDO', 'Direccion': 'Valdemingómez', 'lat': 40.3186, 'lon': -3.6017}
                
                if info_nodo:
                    ruta_actual.append(info_nodo)
                
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                distancia_ruta += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

            if ruta_actual:
                rutas[f"Vehículo {vehicle_id + 1}"] = {
                    'servicios': ruta_actual,
                    'estadisticas': {
                        'distancia_total_km': distancia_ruta / 1000,
                        'tiempo_total_min': (distancia_ruta / 1000 / 30) * 60,
                        'num_servicios': len(ruta_actual),
                        'combustible_estimado_l': (distancia_ruta / 1000) * 0.35,
                        'combos_detectados': 0
                    }
                }
                
        return rutas
    
    # ... (Mantenemos exportar_excel y kml igual que antes)
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
        return b"" # Simplificado por espacio