"""
Algoritmo VRP Avanzado para Portacontenedores de Cadenas
Lógica específica: 
- Apilamiento de hasta 5 vacíos.
- Gestión de Suministros de Áridos.
- Lectura de columna 'Concepto'.
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
        # Ubicaciones fijas (esto debería venir de config, pero lo dejamos por seguridad)
        self.vertederos = {
            'norte': {'coords': (40.3460, -3.7007), 'nombre': 'Vertedero Norte'},
            'sur': {'coords': (40.3186, -3.6017), 'nombre': 'Vertedero Sur'}
        }
        self.base = {'coords': (40.4168, -3.7038), 'nombre': 'Base Central'} # Madrid centro por defecto

    def configurar(self, **kwargs):
        """Configura los parámetros desde la interfaz"""
        self.parametros = kwargs

    def optimizar(self, df_input):
        """Función principal que orquesta la optimización"""
        try:
            # 1. Preparar datos y detectar tipos de servicio por 'Concepto'
            df = df_input.copy()
            df = self._procesar_conceptos(df)
            
            # 2. Filtrar solo filas válidas geocodificadas
            df = df[df['geocodificado'] == True].reset_index(drop=True)
            
            if len(df) == 0:
                st.error("No hay direcciones geocodificadas válidas para optimizar.")
                return {}

            # 3. Crear matriz de distancias
            matriz_distancias, localizaciones = self._crear_matriz_distancias(df)
            
            # 4. Configurar modelo OR-Tools
            data = self._preparar_modelo_datos(df, matriz_distancias)
            
            # 5. Resolver
            manager = pywrapcp.RoutingIndexManager(
                len(data['distance_matrix']), 
                data['num_vehicles'], 
                data['depot']
            )
            routing = pywrapcp.RoutingModel(manager)

            # Definir callback de distancia
            def distance_callback(from_index, to_index):
                from_node = manager.IndexToNode(from_index)
                to_node = manager.IndexToNode(to_index)
                return data['distance_matrix'][from_node][to_node]

            transit_callback_index = routing.RegisterTransitCallback(distance_callback)
            routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

            # --- RESTRICCIÓN DE CAPACIDAD (Cadenas: hasta 5 vacíos) ---
            # En portacontenedores: 
            # DEPOSITO: Gasta 1 vacío (-1)
            # RETIRADA: Genera 1 lleno (pero matemáticamente ocupa espacio de carga, +1)
            # SUMINISTRO: Empieza lleno, acaba con vacío (Efecto neto en vacíos: +1 disponible)
            
            def demand_callback(from_index):
                from_node = manager.IndexToNode(from_index)
                return data['demands'][from_node]

            demand_callback_index = routing.RegisterUnaryTransitCallback(demand_callback)
            
            # Capacidad de 5 (pensando en huecos/contenedores vacíos apilables)
            routing.AddDimensionWithVehicleCapacity(
                demand_callback_index,
                0,  # null capacity slack
                data['vehicle_capacities'],
                True,  # start cumul to zero
                'Capacidad'
            )

            # Configuración de búsqueda (Heurística)
            search_parameters = pywrapcp.DefaultRoutingSearchParameters()
            search_parameters.first_solution_strategy = (
                routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
            )
            # Tiempo límite para no bloquear la app
            search_parameters.time_limit.seconds = 10 

            # Resolver
            solution = routing.SolveWithParameters(search_parameters)

            # 6. Formatear resultados
            if solution:
                return self._procesar_solucion(manager, routing, solution, df, localizaciones)
            else:
                st.warning("No se encontró una solución óptima con las restricciones actuales.")
                return {}

        except Exception as e:
            st.error(f"Error crítico en optimización: {str(e)}")
            return {}

    def _procesar_conceptos(self, df):
        """Interpreta la columna 'Concepto' según lógica de negocio"""
        def identificar_tipo(row):
            # Prioridad absoluta a la columna Concepto
            concepto = str(row.get('Concepto', '')).upper()
            material = str(row.get('Material', '')).upper()
            texto = f"{concepto} {material}"
            
            if 'SUMINISTRO' in texto or 'ARIDO' in texto or 'ÁRIDO' in texto:
                return 'SUMINISTRO' # Lleva tierra, sale con caja vacía
            elif 'CAMBIO' in texto:
                return 'CAMBIO' # Deja una, se lleva otra
            elif 'RETIRADA' in texto or 'RECOGIDA' in texto:
                return 'RETIRADA' # Se lleva una llena
            elif 'DEPOSITO' in texto or 'ENTREGA' in texto:
                return 'DEPOSITO' # Deja una vacía
            else:
                # Por defecto, si no está claro
                return 'RETIRADA'

        df['tipo_servicio'] = df.apply(identificar_tipo, axis=1)
        return df

    def _crear_matriz_distancias(self, df):
        """Calcula matriz de distancias entre todos los puntos + base + vertederos"""
        # Lista de puntos: [Base, Cliente 1, Cliente 2, ..., Vertedero N, Vertedero S]
        puntos = [self.base['coords']]
        
        # Añadir clientes
        for _, row in df.iterrows():
            puntos.append((row['lat'], row['lon']))
            
        # Añadir vertederos al final de la matriz (como nodos posibles)
        # Nota: En una implementación simple VRP, los vertederos son complejos.
        # Aquí simplificaremos asumiendo que el 'Depósito' (0) es la base.
        
        size = len(puntos)
        matriz = [[0 for _ in range(size)] for _ in range(size)]
        
        for i in range(size):
            for j in range(size):
                if i != j:
                    # Distancia en Metros (convertida a entero para OR-Tools)
                    dist = geodesic(puntos[i], puntos[j]).meters
                    matriz[i][j] = int(dist)
                    
        return matriz, puntos

    def _preparar_modelo_datos(self, df, matriz):
        """Define las demandas y capacidades"""
        
        # Lógica de Demanda para Cadenas (Gestión de Vacíos):
        # El camión tiene 'slots' para vacíos.
        # DEPOSITO: Entrega un vacío. Demanda = 1 (Gasta 1 slot de carga que llevaba)
        # RETIRADA: Recoge lleno. Demanda = 0 (En modelo simplificado de vacíos) o requiere ir a vertedero.
        # SUMINISTRO: Genera un vacío nuevo en la ruta. Demanda = -1 (Gana 1 vacío).
        
        # NOTA IMPORTANTE: Modelar Cargas (Llenos) y Vacíos simultáneamente es complejo.
        # Simplificación robusta:
        # Usaremos capacidad positiva como "Entregas pendientes" (Depósitos).
        
        demands = [0] # Base
        
        for _, row in df.iterrows():
            tipo = row['tipo_servicio']
            
            if tipo == 'DEPOSITO':
                # Necesita que el camión lleve una caja.
                demands.append(1) 
            elif tipo == 'SUMINISTRO':
                # El camión se libera de su carga y genera una caja vacía disponible.
                # Matemáticamente, recupera capacidad de llevar cosas.
                demands.append(-1)
            elif tipo == 'RETIRADA':
                # Ocupa el camión totalmente (no puede hacer más depositos hasta descargar)
                # Le damos un peso alto para forzar descarga o fin de ruta si no es complejo
                demands.append(0) # Simplificación: Asumimos que retiradas van al final o intercaladas
            elif tipo == 'CAMBIO':
                # Neutro
                demands.append(0)
            else:
                demands.append(1)

        # Capacidad de vehículos
        # Cadenas = 5 Contenedores Vacíos
        num_vehiculos = int(self.parametros.get('vehiculos_c', 5))
        capacidad = 5 # 5 Contenedores vacíos apilados
        
        return {
            'distance_matrix': matriz,
            'demands': demands,
            'vehicle_capacities': [capacidad] * num_vehiculos,
            'num_vehicles': num_vehiculos,
            'depot': 0
        }

    def _procesar_solucion(self, manager, routing, solution, df, localizaciones):
        """Convierte la solución matemática en rutas legibles"""
        rutas = {}
        
        for vehicle_id in range(routing.vehicles()):
            index = routing.Start(vehicle_id)
            ruta_actual = []
            distancia_ruta = 0
            carga_actual = 0 # Contenedores vacíos
            
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                
                # Si no es el depósito (nodo 0)
                if node_index > 0 and node_index <= len(df):
                    row = df.iloc[node_index - 1] # -1 porque 0 es base
                    
                    servicio = {
                        'Cliente': row['Cliente'],
                        'Direccion': row['Direccion'],
                        'Tipo': row['tipo_servicio'],
                        'Concepto': row.get('Concepto', ''),
                        'Hora Pide': row['Hora Pide'],
                        'lat': row['lat'],
                        'lon': row['lon']
                    }
                    ruta_actual.append(servicio)
                
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                distancia_ruta += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)

            if ruta_actual:
                # Guardar ruta
                rutas[f"Vehículo {vehicle_id + 1}"] = {
                    'servicios': ruta_actual,
                    'estadisticas': {
                        'distancia_total_km': distancia_ruta / 1000,
                        'tiempo_total_min': (distancia_ruta / 1000 / 30) * 60, # 30km/h media urbana
                        'num_servicios': len(ruta_actual),
                        'combustible_estimado_l': (distancia_ruta / 1000) * 0.35, # Consumo camión
                        'combos_detectados': sum(1 for s in ruta_actual if s['Tipo'] == 'CAMBIO')
                    }
                }
                
        return rutas

    def exportar_excel(self, rutas, df_original):
        """Genera Excel descargable"""
        import io
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # Resumen
            resumen = []
            for vehiculo, datos in rutas.items():
                resumen.append({
                    'Vehículo': vehiculo,
                    'Servicios': datos['estadisticas']['num_servicios'],
                    'Km': datos['estadisticas']['distancia_total_km']
                })
            pd.DataFrame(resumen).to_excel(writer, sheet_name='Resumen', index=False)
            
            # Detalle
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
        """Genera KML para Google Earth"""
        kml = ['<?xml version="1.0" encoding="UTF-8"?>']
        kml.append('<kml xmlns="http://www.opengis.net/kml/2.2">')
        kml.append('<Document>')
        
        colores = ['ff0000ff', 'ff00ff00', 'ffff0000', 'ff00ffff', 'ffffff00'] # ABGR
        
        i = 0
        for vehiculo, datos in rutas.items():
            color = colores[i % len(colores)]
            i += 1
            
            # Línea de ruta
            kml.append(f'<Placemark><name>{vehiculo}</name><Style><LineStyle><color>{color}</color><width>4</width></LineStyle></Style>')
            kml.append('<LineString><coordinates>')
            for serv in datos['servicios']:
                kml.append(f"{serv['lon']},{serv['lat']},0")
            kml.append('</coordinates></LineString></Placemark>')
            
        kml.append('</Document></kml>')
        return "\n".join(kml).encode('utf-8')