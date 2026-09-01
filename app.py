if btn_evaluar:
        if not api_key:
            st.error("Introduce tu Gemini API Key en el menú lateral.")
        else:
            ib_calc = calcular_intensidad_empleo(potencia_kw, tension, cos_phi, rendimiento)
            dv_v, dv_pct = calcular_caida_tension(potencia_kw, longitud_m, seccion_mm2, tension, cos_phi)
            iz_calc = obtener_iz_tabulada(seccion_mm2, metodo_inst)

            datos_consolidados = f"""
            --- CÁLCULOS FÍSICOS DETERMINISTAS EJECUTADOS POR EL MOTOR EN PYTHON ---
            * Intensidad de empleo calculada (Ib): {ib_calc} A
            * Caída de tensión calculada (dU): {dv_v} V ({dv_pct} %)
            * Intensidad admisible tabulada del conductor (Iz a 40°C): {iz_calc} A

            --- DATOS DE ENTRADA DE LA INSTALACIÓN ---
            - Nombre: {nombre_inst}
            - Entorno: {entorno}, Temp ambiente: {temp_ambiente}°C
            - Red: {tension}, Esquema: {esquema_tierra}, Ra tierra: {r_tierra if r_tierra > 0 else 'NO ESPECIFICADO'}
            - Receptor: {tipo_receptor}, Potencia: {potencia_kw} kW, cos φ: {cos_phi}, rendimiento: {rendimiento}
            - Arranque: {tipo_arranque}
            - Línea: Longitud: {longitud_m} m, Sección: {seccion_mm2} mm² Cu, PE: {seccion_pe if seccion_pe > 0 else 'NO ESPECIFICADO'}
            - Cable/Canalización: Aislamiento {aislamiento}, Método {metodo_inst}
            - Magnetotérmico: In={in_pia}A, Curva {curva_pia}
            - Diferencial: In={in_diff}A, Sensibilidad={sens_diff_ma} mA
            - Observaciones: {observaciones}
            """
            
            with st.spinner("Procesando auditoría de forma inmediata..."):
                client = genai.Client(api_key=api_key)
                
                # Lista fija y directa sin llamadas previas para listar modelos
                modelos_candidatos = ["gemini-2.5-flash", "gemini-1.5-flash"]
                
                informe = None
                raw_json = ""
                ultimo_error = ""
                modelo_exitoso = ""

                for mod in modelos_candidatos:
                    try:
                        response = client.models.generate_content(
                            model=mod,
                            contents=f"Audita la siguiente instalación:\n{datos_consolidados}",
                            config=types.GenerateContentConfig(
                                system_instruction=SYSTEM_INSTRUCTION,
                                response_mime_type="application/json",
                                response_schema=InformeAuditoria,
                                temperature=0.1,
                            ),
                        )
                        raw_json = response.text
                        informe = InformeAuditoria.model_validate_json(raw_json)
                        modelo_exitoso = mod
                        break
                    except Exception as e:
                        ultimo_error = str(e)
                        continue

                if informe:
                    st.success(f"Auditoría completada con `{modelo_exitoso}`.")
                    
                    auditoria_id = guardar_auditoria(nombre_inst, datos_consolidados, raw_json)
                    st.toast(f"Guardado en base de datos con ID #{auditoria_id}")

                    st.info(f"**Valores deterministas de línea:** $I_b = {ib_calc}\\text{{ A}}$ | $I_z = {iz_calc}\\text{{ A}}$ | $\\Delta U = {dv_pct}\\%$")

                    st.subheader("Resumen Ejecutivo")
                    st.info(informe.resumen_ejecutivo)
                    
                    if informe.datos_faltantes_criticos:
                        st.subheader("⚠️ Datos Faltantes Críticos")
                        for dato in informe.datos_faltantes_criticos:
                            st.warning(f"- {dato}")
                    
                    st.subheader("Matriz de Hallazgos Normativos")
                    for h in informe.hallazgos:
                        with st.expander(f"{h.estado.value} | {h.elemento_afectado}"):
                            st.write(f"**Artículo/ITC:** {h.articulo_itc_aplicable}")
                            st.write(f"**Dato provocador:** {h.dato_provocador}")
                            st.write(f"**Exigencia:** {h.requisito_normativo}")
                            st.write(f"**Análisis técnico:** {h.justificacion_tecnica}")

                    pdf_bytes = generar_pdf(informe, datos_consolidados)
                    st.download_button(
                        label="📄 Descargar Informe Oficial en PDF",
                        data=pdf_bytes,
                        file_name=f"Informe_Auditoria_REBT_{auditoria_id}.pdf",
                        mime="application/pdf",
                        type="secondary"
                    )
                else:
                    st.error(f"Error de ejecución: {ultimo_error}")
