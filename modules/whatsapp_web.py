"""
Generador de enlaces para WhatsApp Web
"""

import urllib.parse
from datetime import datetime
from typing import Dict, List, Optional
import streamlit as st

class WhatsAppLinkGenerator:
    """Genera enlaces directos a WhatsApp Web con mensajes predefinidos"""
    
    def __init__(self):
        self.templates = {
            'ruta_completa': self._template_ruta_completa,
            'ruta_simple': self._template_ruta_simple,
            'actualizacion': self._template_actualizacion,
            'incidencia': self._template_incidencia
        }
    
    def _template_ruta_completa(self, **kwargs) -> str:
        """Plantilla para ruta completa"""
        return f"""🚛 *RUTA ASIGNADA - {kwargs.get('fecha', '')}*

👤 *CONDUCTOR:* {kwargs.get('conductor', '')}
🚚 *VEHÍCULO:* {kwargs.get('vehiculo', '')}
📋 *SERVICIOS:* {kwargs.get('num_servicios', 0)}

📍 *ITINERARIO:*
{kwargs.get('itinerario', '')}

📏 *DISTANCIA TOTAL:* {kwargs.get('distancia', 0)} km
⏱️ *TIEMPO ESTIMADO:* {kwargs.get('tiempo', 0)} horas
⛽ *COMBUSTIBLE:* {kwargs.get('combustible', 0)} L

🔄 *INSTRUCCIONES:*
1. Seguir el orden establecido
2. Reportar incidencias al +34XXX XXX XXX
3. Confirmar cada servicio completado
4. Informar retrasos mayores a 15 minutos

✅ *CONFIRMAR RECEPCIÓN* con "OK"

#Ruta{kwargs.get('vehiculo_num', '')} #{kwargs.get('fecha_codigo', '')}"""
    
    def _template_ruta_simple(self, **kwargs) -> str:
        """Plantilla para ruta simplificada"""
        return f"""🚛 Ruta asignada: {kwargs.get('vehiculo', '')}
👤 Conductor: {kwargs.get('conductor', '')}
📍 {kwargs.get('num_servicios', 0)} servicios
📏 {kwargs.get('distancia', 0)} km
⏱️ {kwargs.get('tiempo', 0)} h

Confirmar recepción con OK"""
    
    def _template_actualizacion(self, **kwargs) -> str:
        """Plantilla para actualización de ruta"""
        return f"""🔄 *ACTUALIZACIÓN DE RUTA*

Ruta: {kwargs.get('vehiculo', '')}
Cambios: {kwargs.get('cambios', '')}
Nuevos servicios: {kwargs.get('nuevos_servicios', 0)}

Confirmar recepción"""
    
    def _template_incidencia(self, **kwargs) -> str:
        """Plantilla para reporte de incidencia"""
        return f"""⚠️ *INCIDENCIA REPORTADA*

Ruta: {kwargs.get('vehiculo', '')}
Conductor: {kwargs.get('conductor', '')}
Incidencia: {kwargs.get('incidencia', '')}
Hora: {kwargs.get('hora', '')}

Acciones tomadas: {kwargs.get('acciones', '')}"""
    
    def generar_mensaje_ruta(self, vehiculo: str, ruta_data: Dict, 
                           template: str = 'ruta_completa') -> str:
        """
        Generar mensaje de WhatsApp para una ruta
        
        Args:
            vehiculo: Nombre del vehículo
            ruta_data: Diccionario con datos de la ruta
            template: Nombre del template a usar
        
        Returns:
            Mensaje formateado para WhatsApp
        """
        
        # Extraer datos de la ruta
        conductor = ruta_data.get('conductor', 'Por asignar')
        servicios = ruta_data.get('servicios', [])
        estadisticas = ruta_data.get('estadisticas', {})
        
        # Generar itinerario
        itinerario = ""
        for i, servicio in enumerate(servicios, 1):
            cliente = servicio.get('Cliente', f'Cliente {i}')
            direccion = servicio.get('Direccion', 'Sin dirección')
            hora = servicio.get('Hora Pide', '--:--')
            tipo = servicio.get('tipo_servicio', servicio.get('Material', 'Servicio'))
            
            # Acortar dirección si es muy larga
            if len(direccion) > 40:
                direccion = direccion[:37] + "..."
            
            # Determinar emoji según tipo
            emoji = "📦"
            if 'retirada' in str(tipo).lower():
                emoji = "🔄"
            elif 'deposito' in str(tipo).lower():
                emoji = "📤"
            
            itinerario += f"\n{i}. {emoji} *{cliente}*"
            itinerario += f"\n   📍 {direccion}"
            itinerario += f"\n   ⏰ {hora} | {tipo}"
            
            # Añadir notas si existen y no son demasiado largas
            observaciones = servicio.get('Observaciones', '')
            if observaciones and len(str(observaciones)) < 50:
                itinerario += f"\n   📝 {observaciones}"
            
            itinerario += "\n"
        
        # Preparar parámetros para el template
        fecha_actual = datetime.now()
        params = {
            'fecha': fecha_actual.strftime("%d/%m/%Y %H:%M"),
            'fecha_codigo': fecha_actual.strftime("%d%m"),
            'conductor': conductor,
            'vehiculo': vehiculo,
            'vehiculo_num': ''.join(filter(str.isdigit, vehiculo)) or 'X',
            'num_servicios': len(servicios),
            'itinerario': itinerario,
            'distancia': f"{estadisticas.get('distancia_total_km', 0):.1f}",
            'tiempo': f"{estadisticas.get('tiempo_total_min', 0)/60:.1f}",
            'combustible': f"{estadisticas.get('combustible_estimado_l', 0):.1f}"
        }
        
        # Seleccionar y aplicar template
        if template in self.templates:
            mensaje = self.templates[template](**params)
        else:
            mensaje = self.templates['ruta_completa'](**params)
        
        return mensaje
    
    def generar_enlace_whatsapp(self, mensaje: str, telefono: str = None) -> str:
        """
        Generar enlace para WhatsApp Web
        
        Args:
            mensaje: Mensaje a enviar
            telefono: Número de teléfono (opcional)
        
        Returns:
            Enlace de WhatsApp Web
        """
        
        # Codificar mensaje para URL
        mensaje_codificado = urllib.parse.quote(mensaje)
        
        if telefono:
            # Limpiar y formatear número de teléfono
            telefono_limpio = self._limpiar_telefono(telefono)
            
            if telefono_limpio:
                # Enlace directo al chat
                enlace = f"https://web.whatsapp.com/send?phone={telefono_limpio}&text={mensaje_codificado}"
            else:
                # Enlace sin teléfono si el número no es válido
                enlace = f"https://web.whatsapp.com/send?text={mensaje_codificado}"
        else:
            # Enlace para elegir contacto manualmente
            enlace = f"https://web.whatsapp.com/send?text={mensaje_codificado}"
        
        return enlace
    
    def _limpiar_telefono(self, telefono: str) -> str:
        """Limpiar y validar número de teléfono"""
        if not telefono:
            return ""
        
        # Eliminar espacios y caracteres no numéricos
        numeros = ''.join(filter(str.isdigit, str(telefono)))
        
        # Si empieza con 34 (España), mantenerlo
        if numeros.startswith('34') and len(numeros) == 11:
            return f"34{numeros[2:]}"
        
        # Si tiene 9 dígitos, asumir que es español sin prefijo
        elif len(numeros) == 9:
            return f"34{numeros}"
        
        # Si tiene otros formatos, devolver tal cual
        elif len(numeros) >= 9:
            return numeros
        
        return ""
    
    def generar_enlace_por_conductor(self, rutas_optimizadas: Dict, 
                                   telefonos_conductores: Dict) -> Dict:
        """
        Generar enlaces WhatsApp para cada conductor
        
        Args:
            rutas_optimizadas: Diccionario de rutas por vehículo
            telefonos_conductores: Diccionario {nombre_conductor: telefono}
        
        Returns:
            Diccionario con enlaces por vehículo
        """
        
        enlaces = {}
        
        for vehiculo, ruta in rutas_optimizadas.items():
            conductor = ruta.get('conductor', '')
            
            if conductor in telefonos_conductores:
                telefono = telefonos_conductores[conductor]
                
                # Generar mensaje
                mensaje = self.generar_mensaje_ruta(vehiculo, ruta)
                
                # Generar enlace
                enlace = self.generar_enlace_whatsapp(mensaje, telefono)
                
                enlaces[vehiculo] = {
                    'conductor': conductor,
                    'telefono': telefono,
                    'enlace': enlace,
                    'mensaje_preview': mensaje[:150] + "..." if len(mensaje) > 150 else mensaje
                }
            else:
                # Sin teléfono, generar enlace genérico
                mensaje = self.generar_mensaje_ruta(vehiculo, ruta)
                enlace = self.generar_enlace_whatsapp(mensaje)
                
                enlaces[vehiculo] = {
                    'conductor': conductor,
                    'telefono': None,
                    'enlace': enlace,
                    'mensaje_preview': mensaje[:150] + "..." if len(mensaje) > 150 else mensaje,
                    'nota': 'Sin teléfono - elegir contacto manualmente'
                }
        
        return enlaces
    
    def generar_codigo_qr(self, enlace: str, tamaño: int = 300) -> str:
        """
        Generar URL para código QR (útil para móviles)
        
        Args:
            enlace: Enlace de WhatsApp
            tamaño: Tamaño del QR en píxeles
        
        Returns:
            URL de imagen QR
        """
        enlace_codificado = urllib.parse.quote(enlace)
        return f"https://api.qrserver.com/v1/create-qr-code/?size={tamaño}x{tamaño}&data={enlace_codificado}"
    
    def crear_panel_envio_masivo(self, rutas_optimizadas: Dict, 
                                telefonos_conductores: Dict = None):
        """
        Crear panel de Streamlit para envío masivo
        
        Args:
            rutas_optimizadas: Rutas a enviar
            telefonos_conductores: Teléfonos de conductores
        """
        
        st.subheader("📱 ENVÍO MASIVO POR WHATSAPP")
        
        # Generar todos los enlaces
        enlaces = self.generar_enlace_por_conductor(rutas_optimizadas, telefonos_conductores or {})
        
        # Mostrar tabla de enlaces
        datos_tabla = []
        for vehiculo, datos in enlaces.items():
            datos_tabla.append({
                'Vehículo': vehiculo,
                'Conductor': datos['conductor'],
                'Teléfono': datos['telefono'] or 'No especificado',
                'Acción': 'Disponible'
            })
        
        if datos_tabla:
            import pandas as pd
            df_enlaces = pd.DataFrame(datos_tabla)
            st.dataframe(df_enlaces, use_container_width=True)
        
        # Botones de acción
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📤 Enviar Todos", type="primary", use_container_width=True):
                st.info("Se abrirán varias pestañas de WhatsApp Web...")
                
                import webbrowser
                for vehiculo, datos in enlaces.items():
                    webbrowser.open_new_tab(datos['enlace'])
                    import time
                    time.sleep(1)  # Pequeña pausa entre aperturas
                
                st.success(f"✅ {len(enlaces)} enlaces abiertos en WhatsApp Web")
        
        with col2:
            # Exportar todos los mensajes
            todos_mensajes = []
            for vehiculo, datos in enlaces.items():
                # Reconstruir mensaje completo (necesitaríamos guardarlo)
                ruta = rutas_optimizadas[vehiculo]
                mensaje = self.generar_mensaje_ruta(vehiculo, ruta)
                todos_mensajes.append(f"=== {vehiculo} ===\