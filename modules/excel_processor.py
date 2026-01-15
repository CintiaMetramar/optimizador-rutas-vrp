def _inferir_tipo_servicio(self, fila) -> str:
        """Inferir tipo de servicio con lógica de CAMBIO mejorada"""
        material = str(fila.get('Material', '')).lower()
        concepto = str(fila.get('Concepto', '')).lower()
        texto_completo = material + " " + concepto

        # 1. Detección explícita de CAMBIO
        if 'cambio' in texto_completo:
            return 'CAMBIO'
        
        # 2. Detección por columnas de cajas (Si marca SÍ en ambas)
        caja_depos = str(fila.get('Caja Depos', '')).upper()
        caja_retir = str(fila.get('Caja Retir', '')).upper()
        
        if caja_depos in ['SÍ', 'SI', '1', 'TRUE'] and caja_retir in ['SÍ', 'SI', '1', 'TRUE']:
            return 'CAMBIO'
            
        # 3. Resto de tipos
        if 'retirada' in texto_completo or 'recogida' in texto_completo:
            return 'RETIRADA'
        elif 'deposito' in texto_completo or 'depósito' in texto_completo or 'entrega' in texto_completo:
            return 'DEPOSITO'
        else:
            # Por defecto, si no se sabe, asumimos Retirada (es lo más común)
            return 'RETIRADA'
