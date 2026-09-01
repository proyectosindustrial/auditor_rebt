import streamlit as st
import time
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from enum import Enum
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from calculos import calcular_intensidad_empleo, calcular_caida_tension, obtener_iz_tabulada
from database import init_db, guardar_auditoria, obtener_historial, obtener_auditoria_por_id

# Inicializar Base de Datos al arrancar
init_db()

st.set_page_config(
    page_title="Auditor Técnico REBT",
    page_icon="⚡",
    layout="centered"
)

class EstadoCumplimiento(str, Enum):
    CUMPLE = "CUMPLE"
    NO_CUMPLE = "NO CUMPLE"
    REQUIERE_ACLARACION = "REQUIERE ACLARACIÓN"

class HallazgoNormativo(BaseModel):
    elemento_afectado: str = Field(description="Ej: Sección Cable, Magnetotérmico, Caída de Tensión")
    articulo_itc_aplicable: str = Field(description="Ej: ITC-BT-19, ITC-BT-22, Art. 18")
    estado: EstadoCumplimiento
    dato_provocador: str = Field(description="El dato que origina el hallazgo, ej: Ib = 45A > Iz = 32A")
    requisito_normativo: str = Field(description="Lo que exige la norma exactamente")
    justificacion_tecnica: str = Field(description="Explicación detallada del cálculo o incoherencia")

class InformeAuditoria(BaseModel):
    resumen_ejecutivo: str = Field(description="Resumen de 2-3 frases del estado general de la instalación")
    hallazgos: list[HallazgoNormativo]
    datos_faltantes_criticos: list[str] = Field(description="Lista de datos no proporcionados que son imprescindibles para validar completamente la instalación")

SYSTEM_INSTRUCTION = """
Eres un Ingeniero Inspector Industrial de Alta Calificación, especialista en el Reglamento Electrotécnico para Baja Tensión (REBT - Real Decreto 842/2002) de España y sus Instrucciones Técnicas Complementarias (ITCs).

Tu objetivo es auditar los datos de la instalación eléctrica proporcionados y generar un informe técnico estructurado e inflexible respecto al cumplimiento normativo.

IMPORTANTE: Se te proporcionan cálculos deterministas ya ejecutados (Intensidad de empleo Ib, Caída de tensión dU%, e Intensidad Admisible Iz). UTILIZA ESTOS VALORES CALCULADOS PARA TU EVALUACIÓN.

Reglas estrictas de auditoría:
1. Coordinación de Protecciones (ITC-BT-19 / ITC-BT-22): Verifica strictly la condición de protección frente a sobrecargas: Ib <= In <= Iz.
2. Caída de Tensión (ITC-BT-19): Verifica que dU% no supere los límites normativos (4% para distribución interior general, 3% para alumbrado, 5% para otros usos/fuerza salvo especificación).
3. Protección Diferencial y Puesta a Tierra (ITC-BT-18 / ITC-BT-24): En esquema TT, verifica Ra * IΔn <= 50V (o 24V en locales húmedos/obras).
4. Sección del Conductor Neutro y Protección (ITC-BT-19): Verifica si la sección del neutro cumple con los mínimos requeridos según la sección de los conductores de fase.
5. Inflexibilidad Técnica: Si un dato imprescindible falta (ej: no se da la Ra de tierra), márcalo como REQUIERE ACLARACIÓN y añádelo a 'datos_faltantes_criticos'.

Responde EXCLUSIVAMENTE en el formato JSON estructurado requerido.
"""

def generar_pdf(informe: InformeAuditoria, datos_entrada: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1E3A8A"), spaceAfter=12
    )
    h2_style = ParagraphStyle(
        'SectionHeader', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor("#1E3A8A"), spaceBefore=10, spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyDark', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#111827")
    )
    header_cell_style = ParagraphStyle(
        'HeaderCell', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName="Helvetica-Bold"
    )

    story.append(Paragraph("Informe Técnico de Auditoría REBT", title_style))
    story.append(Paragraph("<b>Entorno de Inspección:</b> Evaluación de Conformidad Normativa", body_style))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Resumen Ejecutivo", h2_style))
    story.append(Paragraph(informe.resumen_ejecutivo, body_style))
    story.append(Spacer(1, 10))

    if informe.datos_faltantes_criticos:
        story.append(Paragraph("2. Datos Faltantes Críticos", h2_style))
        for df in informe.datos_faltantes_criticos:
            story.append(Paragraph(f"• {df}", body_style))
        story.append(Spacer(1, 10))

    story.append(Paragraph("3. Matriz de Hallazgos Normativos", h2_style))
    table_data = [[
        Paragraph("Elemento", header_cell_style),
        Paragraph("ITC", header_cell_style),
        Paragraph("Estado", header_cell_style),
        Paragraph("Detalle / Justificación", header_cell_style)
    ]]

    for h in informe.hallazgos:
        color_estado = "#15803D" if h.estado == EstadoCumplimiento.CUMPLE else ("#B91C1C" if h.estado == EstadoCumplimiento.NO_CUMPLE else "#B45309")
        estado_style = ParagraphStyle('EstStyle', parent=body_style, textColor=colors.HexColor(color_estado), fontName="Helvetica-Bold")
        detalle_txt = f"<b>Provocador:</b> {h.dato_provocador}<br/><b>Requisito:</b> {h.requisito_normativo}<br/><b>Análisis:</b> {h.justificacion_tecnica}"

        table_data.append([
            Paragraph(h.elemento_afectado, body_style),
            Paragraph(h.articulo_itc_aplicable, body_style),
            Paragraph(h.estado.value, estado_style),
            Paragraph(detalle_txt, body_style)
        ])

    t = Table(table_data, colWidths=[90, 65, 85, 300])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

st.title("⚡ Auditor Técnico REBT")
st.caption("Verificación de conformidad según Reglamento Electrotécnico para Baja Tensión")

with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("Gemini API Key", type="password", help="Introduce tu API Key de Google AI Studio")

tab1, tab2 = st.tabs(["🚀 Nueva Auditoría", "📂 Historial de Inspecciones"])

with tab1:
    st.header("Parámetros de la Instalación")
    nombre_inst = st.text_input("Nombre de la instalación / Cliente", value="Instalación Industrial Naves A-1")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("1. Entorno y Red")
        entorno = st.selectbox("Local de concurrencia / Emplazamiento", ["General / Habitual", "Pública concurrencia (ITC-BT-28)", "Local húmedo / mojado (ITC-BT-30)", "Local con riesgo de incendio/explosión (ITC-BT-29)", "Obra de construcción (ITC-BT-33)"])
        temp_ambiente = st.number_input("Temperatura ambiente (°C)", value=40, step=5)
        tension = st.selectbox("Tensión de red", ["400V Trifásico", "230V Monofásico"])
        esquema_tierra = st.selectbox("Esquema de distribución / Tierra", ["TT", "TN-S", "TN-C", "IT"])
        r_tierra = st.number_input("Resistencia de tierra Ra (Ω) [0 si no se conoce]", value=15.0, step=1.0)

    with col2:
        st.subheader("2. Receptor / Carga")
        tipo_receptor = st.selectbox("Tipo de receptor", ["Motor industrial", "Alumbrado", "Carga general / Variado", "Línea general de alimentación"])
        potencia_kw = st.number_input("Potencia activa (kW)", value=15.0, step=0.5)
        cos_phi = st.number_input("Factor de potencia (cos φ)", value=0.85, step=0.01, min_value=0.1, max_value=1.0)
        rendimiento = st.number_input("Rendimiento motor (η)", value=0.88, step=0.01, min_value=0.1, max_value=1.0)
        tipo_arranque = st.selectbox("Tipo de arranque (motores)", ["Directo", "Estrella-Triángulo", "Variador de frecuencia / Arrancador suave"])

    st.subheader("3. Canalización y Conductor")
    col3, col4 = st.columns(2)
    with col3:
        longitud_m = st.number_input("Longitud de la línea (m)", value=45.0, step=1.0)
        seccion_mm2 = st.selectbox("Sección fase (mm² Cu)", [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240])
        seccion_pe = st.selectbox("Sección de protección PE (mm² Cu)", [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240], index=4)

    with col4:
        aislamiento = st.selectbox("Tipo de aislamiento", ["XLPE / EPR (90 °C)", "PVC (70 °C)"])
        metodo_inst = st.selectbox("Método de instalación (UNE 20460)", ["B1 (Tubo en pared de obra)", "B2 (Tubo sobre pared / canal)", "C (Bandeja no perforada / aire)", "E (Bandeja perforada)", "D (Enterrado bajo tubo)"])

    st.subheader("4. Protecciones en CGMP")
    col5, col6 = st.columns(2)
    with col5:
        in_pia = st.number_input("Intensidad nominal Magnetotérmico In (A)", value=50, step=1)
        curva_pia = st.selectbox("Curva magnetotérmico", ["C", "B", "D", "MA"])
    with col6:
        in_diff = st.number_input("Intensidad nominal Diferencial (A)", value=63, step=1)
        sens_diff_ma = st.selectbox("Sensibilidad Diferencial (mA)", [30, 100, 300, 500])

    st.subheader("5. Observaciones adicionales")
    observaciones = st.text_area("Cualquier otro dato técnico relevante:", placeholder="Ej: Agrupamiento con otras líneas, tipo de guardamotor instalado...")

    btn_evaluar = st.button("🚀 Ejecutar Auditoría Estructurada", type="primary")

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
            
            with st.spinner("Analizando normas UNE y articulado del REBT..."):
                client = genai.Client(api_key=api_key)
                
                # Lista de modelos de respaldo para mitigar la saturación puntual (Error 503)
                modelos_a_probar = ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-2.0-flash']
                respuesta_correcta = False
                informe = None
                raw_json = ""
                ultimo_error = ""

                for modelo in modelos_a_probar:
                    if respuesta_correcta:
                        break
                    for intento in range(3):
                        try:
                            response = client.models.generate_content(
                                model=modelo,
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
                            respuesta_correcta = True
                            break
                        except Exception as e:
                            ultimo_error = str(e)
                            time.sleep(2)
                
                if respuesta_correcta and informe:
                    st.success("Auditoría completada exitosamente.")
                    
                    # Guardar en SQLite
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
                    st.error(f"Error al conectar con la API tras varios reintentos: {ultimo_error}")

with tab2:
    st.header("Historial de Inspecciones Guardadas")
    historial = obtener_historial()
    
    if not historial:
        st.info("No hay auditorías registradas todavía.")
    else:
        opciones = {f"#{rec[0]} | {rec[1]} | {rec[2]}": rec[0] for rec in historial}
        seleccion = st.selectbox("Selecciona una inspección previa para cargar:", list(opciones.keys()))
        
        if seleccion:
            rec_id = opciones[seleccion]
            registro = obtener_auditoria_por_id(rec_id)
            if registro:
                _, fecha, nombre, datos_in, json_raw = registro
                informe_hist = InformeAuditoria.model_validate_json(json_raw)
                
                st.markdown(f"**Fecha:** {fecha} | **Instalación:** {nombre}")
                st.subheader("Resumen Ejecutivo")
                st.info(informe_hist.resumen_ejecutivo)
                
                if informe_hist.datos_faltantes_criticos:
                    st.subheader("⚠️ Datos Faltantes Críticos")
                    for dato in informe_hist.datos_faltantes_criticos:
                        st.warning(f"- {dato}")
                
                st.subheader("Matriz de Hallazgos Normativos")
                for h in informe_hist.hallazgos:
                    with st.expander(f"{h.estado.value} | {h.elemento_afectado}"):
                        st.write(f"**Artículo/ITC:** {h.articulo_itc_aplicable}")
                        st.write(f"**Dato provocador:** {h.dato_provocador}")
                        st.write(f"**Exigencia:** {h.requisito_normativo}")
                        st.write(f"**Análisis técnico:** {h.justificacion_tecnica}")

                pdf_bytes_hist = generar_pdf(informe_hist, datos_in)
                st.download_button(
                    label="📄 Re-descargar Informe PDF",
                    data=pdf_bytes_hist,
                    file_name=f"Informe_Auditoria_REBT_{rec_id}.pdf",
                    mime="application/pdf"
                )
