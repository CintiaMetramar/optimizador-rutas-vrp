"""
Generador de enlaces para WhatsApp Web
"""
import urllib.parse
from datetime import datetime
from typing import Dict, Any

class WhatsAppLinkGenerator:
    """Genera enlaces directos a WhatsApp Web con mensajes predefinidos"""
    
    def __init__(self):
        # Plantillas base
        pass
    
    def generar_mensaje_ruta(self, vehiculo: str, ruta: Dict[str, Any]) -> str:
        """
        Genera el mensaje de texto formateado para el conductor.
        """
        stats = ruta.get('estadisticas', {})
        servicios = ruta.get('servicios', [])
        
        # Construir cabecera
        mensaje = [
            f"🚛 *RUTA ASIGNADA - {datetime.now().strftime('%d/%m/%Y')}*",
            f"👤 *VEHÍCULO:* {vehiculo}",
            f"📦 *SERVICIOS:* {stats.get('num_servicios', len(servicios))}",
            "",
            "📍 *ITINERARIO DETALLADO:*"
        ]
        
        # Añadir paradas
        for i, servicio in enumerate(servicios, 1):
            direccion = servicio.get('Direccion', 'Sin dirección')
            cliente = servicio.get('Cliente', 'Cliente')
            hora = servicio.get('Hora Pide', 'Flexible')
            material = servicio.get('Material', '')
            
            # Icono según tipo
            icono = "🛑" if "retirada" in str(material).lower() else "🔹"
            
            parada = f"{i}. {icono} *{cliente}*\n   🏠 {direccion}\n   ⏰ {hora}"
            if material:
                parada += f"\n   📋 {material}"
            
            mensaje.append(parada)
            mensaje.append("")  # Espacio entre paradas
        
        # Añadir pie de página con resumen
        mensaje.extend([
            "📊 *RESUMEN:*",
            f"📏 Distancia est.: {stats.get('distancia_total_km', 0):.1f} km",
            f"⏱️ Tiempo est.: {stats.get('tiempo_total_min', 0):.0f} min",
            "",
            "✅ Por favor, confirma recepción con un 👍"
        ])
        
        return "\n".join(mensaje)
    
    def generar_enlace_whatsapp(self, mensaje: str, telefono: str = "") -> str:
        """
        Crea el enlace clicable para abrir WhatsApp Web.
        Si hay teléfono, abre el chat directo. Si no, abre ventana para elegir contacto.
        """
        mensaje_codificado = urllib.parse.quote(mensaje)
        
        if telefono:
            # Limpiar teléfono
            telefono = ''.join(filter(str.isdigit, str(telefono)))
            return f"https://web.whatsapp.com/send?phone={telefono}&text={mensaje_codificado}"
        else:
            return f"https://web.whatsapp.com/send?text={mensaje_codificado}"
