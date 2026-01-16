def panel_exportacion(self):
        """Panel de exportación de resultados"""
        st.header("💾 EXPORTAR RESULTADOS")
        
        if st.session_state.rutas_optimizadas is None:
            st.warning("⚠️ No hay rutas optimizadas para exportar")
            return
        
        # Ahora usamos 4 columnas
        col1, col2, col3, col4 = st.columns(4)
        
        # ... (col1 Excel, col2 KML, col3 Informe - MANTENLOS IGUAL) ...
        
        # NUEVA COLUMNA PARA MY MAPS
        with col4:
            if st.button("🗺️ CSV My Maps", use_container_width=True):
                # Generar CSV para Google My Maps
                csv_data = "Name,Description,Latitude,Longitude\n"
                
                for vehiculo, ruta in st.session_state.rutas_optimizadas.items():
                    for i, s in enumerate(ruta['servicios']):
                        nombre = f"{vehiculo} - {i}. {s.get('Concepto', 'Punto')}"
                        desc = f"{s.get('Material', '')} - {s.get('Direccion', '')} - {s.get('Hora Pide', '')}"
                        lat = s.get('lat', 0)
                        lon = s.get('lon', 0)
                        
                        if lat != 0 and lon != 0:
                            # Limpiar comas para no romper el CSV
                            nombre = nombre.replace(',', ' ')
                            desc = desc.replace(',', ' ')
                            csv_data += f"{nombre},{desc},{lat},{lon}\n"
                
                st.download_button(
                    label="📥 Bajar CSV Maps",
                    data=csv_data,
                    file_name="importar_en_mymaps.csv",
                    mime="text/csv",
                    use_container_width=True
                )