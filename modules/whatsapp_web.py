"""
Generador de enlaces para WhatsApp Web - Versión Detallada
"""
import urllib.parse
from datetime import datetime
from typing import Dict, Any

class WhatsAppLinkGenerator:
    
    def generar_mensaje_ruta(self, vehiculo: str, ruta: Dict[str, Any]) -> str:
        servicios = ruta.get('servicios', [])
        
        # Cabecera
        mensaje = [
            f"🚛 *RUTA {vehiculo} - {datetime.now().strftime('%d/%m')}*",
            f"📦 Total Servicios: {len(servicios)-1}",
            "--------------------------------"
        ]
        
        # Paradas
        for i, servicio in enumerate(servicios):
            if i == 0: # Inicio
                mensaje.append(f"🏁 *{servicio['Direccion']}*")
                mensaje.append("--------------------------------")
                continue
                
            # Iconos según tipo
            tipo = str(servicio.get('Tipo', '')).upper()
            icono = "🔹"
            if "SUMINISTRO" in tipo: icono = "🏗️"
            elif "CAMBIO" in tipo: icono = "🔄"
            elif "DEPOSITO" in tipo: icono = "⬇️"
            elif "RETIRADA" in tipo: icono = "⬆️"
            elif "VERTIDO" in tipo: icono = "🚮"

            # Cuerpo del servicio DETALLADO
            mensaje.append(f"{i}. {icono} *{servicio.get('Concepto', 'SERVICIO')}*")
            
            # Si hay material específico
            material = servicio.get('Material', '')
            if material:
                mensaje.append(f"   📦 {material}")
            
            mensaje.append(f"   🏠 {servicio.get('Direccion', 'Ubicación')}")
            
            # HORA DESTACADA
            hora = servicio.get('Hora Pide', 'Flexible')
            if hora and hora != 'Flexible':
                mensaje.append(f"   ⏰ *HORA: {hora}*")
            else:
                mensaje.append(f"   ⏰ Flexible")
                
            mensaje.append("") # Espacio
        
        mensaje.append("✅ Confirma con OK")
        return "\n".join(mensaje)
    
    def generar_enlace_whatsapp(self, mensaje: str, telefono: str = "") -> str:
        mensaje_codificado = urllib.parse.quote(mensaje)
        if telefono:
            telefono = ''.join(filter(str.isdigit, str(telefono)))
            return f"https://web.whatsapp.com/send?phone={telefono}&text={mensaje_codificado}"
        else:
            return f"https://web.whatsapp.com/send?text={mensaje_codificado}"
