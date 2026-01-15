"""
Configuración global de la aplicación
"""

import os
from typing import Dict, Any

class Config:
    """Configuración de la aplicación"""
    
    # Configuración general
    APP_NAME = "Optimizador VRP de Rutas"
    VERSION = "1.0.0"
    
    # Rutas de archivos
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
    
    # Archivos de datos
    GEOCACHE_FILE = os.path.join(DATA_DIR, "geocache.json")
    CONDUCTORES_FILE = os.path.join(DATA_DIR, "conductores.json")
    
    # Configuración de geocodificación
    GEOCODER_CONFIG = {
        'provider': 'nominatim',
        'user_agent': 'optimizador_rutas_vrp/1.0',
        'timeout': 10,
        'rate_limit': True,
        'wait_time': 1.0  # segundos entre consultas
    }
    
    # Vertederos fijos
    VERTEDEROS = {
        'norte': {
            'nombre': 'Vertedero Norte',
            'direccion': 'C. Laguna del Marquesado, 16, 28021 Madrid',
            'coordenadas': (40.3460, -3.7007),
            'horario': '24/7'
        },
        'sur': {
            'nombre': 'Vertedero Sur',
            'direccion': 'Ctra. Vertedero Municipal Valdemingómez, 28031 Madrid',
            'coordenadas': (40.3186, -3.6017),
            'horario': '24/7'
        }
    }
    
    # Parámetros por defecto de optimización
    OPTIMIZACION_DEFAULTS = {
        'max_distancia_combo_km': 5,
        'flexibilidad_horaria_min': 60,
        'vehiculos_etiqueta_c': 10,
        'capacidad_vehiculo_contenedores': 5,
        'velocidad_promedio_kmh': 30,
        'tiempo_servicio_min': 30,
        'consumo_combustible_l_km': 0.3
    }
    
    # Zonas de Madrid
    ZONAS_MADRID = {
        'CENTRO': {
            'bounds': {
                'lat_min': 40.405,
                'lat_max': 40.435,
                'lon_min': -3.715,
                'lon_max': -3.665
            },
            'requiere_etiqueta_c': True
        },
        'NORTE': {
            'bounds': {
                'lat_min': 40.435,
                'lat_max': 40.500,
                'lon_min': -3.750,
                'lon_max': -3.650
            },
            'requiere_etiqueta_c': False
        },
        'SUR': {
            'bounds': {
                'lat_min': 40.350,
                'lat_max': 40.405,
                'lon_min': -3.750,
                'lon_max': -3.650
            },
            'requiere_etiqueta_c': False
        },
        'ESTE': {
            'bounds': {
                'lat_min': 40.380,
                'lat_max': 40.450,
                'lon_min': -3.650,
                'lon_max': -3.550
            },
            'requiere_etiqueta_c': False
        },
        'OESTE': {
            'bounds': {
                'lat_min': 40.380,
                'lat_max': 40.450,
                'lon_min': -3.750,
                'lon_max': -3.680
            },
            'requiere_etiqueta_c': False
        }
    }
    
    # Configuración de WhatsApp
    WHATSAPP_CONFIG = {
        'template_ruta': """
🚛 *RUTA ASIGNADA - {fecha}*

👤 *CONDUCTOR:* {conductor}
🚚 *VEHÍCULO:* {vehiculo}
📋 *SERVICIOS:* {num_servicios}

📍 *ITINERARIO:*
{itinerario}

📏 *DISTANCIA TOTAL:* {distancia} km
⏱️ *TIEMPO ESTIMADO:* {tiempo} horas
⛽ *COMBUSTIBLE:* {combustible} L

🔄 *INSTRUCCIONES:*
1. Seguir el orden establecido
2. Reportar incidencias
3. Confirmar cada servicio

✅ *CONFIRMAR RECEPCIÓN* con "OK"
        """,
        'url_base': 'https://web.whatsapp.com/send?phone={phone}&text={text}',
        'url_sin_telefono': 'https://web.whatsapp.com/send?text={text}'
    }
    
    # Columnas esperadas en Excel de servicios
    COLUMNAS_SERVICIOS = [
        'Fecha',
        'Conductor',
        'Cliente',
        'Cliente (2)',
        'Contacto',
        'Telefono',
        'Direccion',
        'Hora Pide',
        'Poblacion',
        'Aclaracion',
        'Concepto',
        'Material',
        'Observaciones',
        'Precio',
        'Cobrado',
        'Hora Condu',
        'Hora Llam',
        'Cliente (3)',
        'Caja Depos',
        'Cantidad',
        'Caja Retir',
        'A Cuenta',
        'Iva',
        'ObservacionesCobro'
    ]
    
    # Columnas esperadas en Excel de conductores
    COLUMNAS_CONDUCTORES = [
        'Nombre',
        'Telefono',
        'Vehiculo',
        'Etiqueta_C',
        'Capacidad_m3',
        'Activo',
        'Notas'
    ]
    
    @classmethod
    def crear_directorios(cls):
        """Crear directorios necesarios"""
        os.makedirs(cls.DATA_DIR, exist_ok=True)
        os.makedirs(cls.TEMPLATES_DIR, exist_ok=True)
    
    @classmethod
    def get_vertedero_mas_cercano(cls, lat: float, lon: float) -> Dict[str, Any]:
        """Obtener el vertedero más cercano a unas coordenadas"""
        from modules.geocoder import GeocodificadorOffline
        geocoder = GeocodificadorOffline()
        
        distancias = {}
        for nombre, datos in cls.VERTEDEROS.items():
            distancia = geocoder.calcular_distancia_km(
                (lat, lon),
                datos['coordenadas']
            )
            distancias[nombre] = distancia
        
        # Obtener el más cercano
        mas_cercano = min(distancias, key=distancias.get)
        return {
            'vertedero': mas_cercano,
            'datos': cls.VERTEDEROS[mas_cercano],
            'distancia_km': distancias[mas_cercano]
        }

# Crear directorios al importar
Config.crear_directorios()