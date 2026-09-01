import streamlit as st
import json
import io
from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# Librerías para generación de PDF
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuración de la página web
st.set_page_config(page_title="Preauditor Industrial REBT", page_icon="⚡", layout="wide")

# 1. ESQUEMA DE DATOS ESTRICTO (Pydantic)
class NivelSeveridad(str, Enum):
    CONFORME = "🟢 CONFORME"
    INFORMACION_FALTANTE = "🟠 FALTA_INFORMACION"
    NO_CONFORMIDAD = "🔴 NO_CONFORMIDAD"
    REVISION_REQUERIDA = "🔵 REVISION_PROFESIONAL"

class HallazgoNormativo(BaseModel):
    elemento_afectado: str = Field(description="Componente o sección auditada")
    estado: NivelSeveridad
    articulo_itc_aplicable: str = Field(description="ITC-BT o Artículo exacto del REBT")
    dato_provocador: str = Field(description="El valor o dato que genera esta evaluación")
    requisito_normativo: str = Field(description="Cita o resumen exacto de la exigencia del REBT")
    justificacion_tecnica: str = Field(description="Análisis de ingeniería")

class InformeAuditoria(BaseModel):
    resumen_ejecutivo: str
    hallazgos: List[HallazgoNormativo]
    datos_faltantes_criticos: Optional[List[str]] = Field(default=[], description="Información que impide auditar con precisión")

# PROMPT DEL SISTEMA
SYSTEM_INSTRUCTION = """
Eres un Ingeniero Industrial Colegiado, Auditor Experto en el REBT de España y sus ITC-BT.
Tu tarea es auditar instalaciones eléctricas industriales con rigor técnico absoluto.
REGLAS:
1. NO INVENTES NORMATIVA. Cita la ITC-BT exacta.
2. FALSOS POSITIVOS: Si una desviación está permitida por excepción (ej. ITC-BT-19 en transitorios de arranque), marca CONFORME.
3. DATOS FALTANTES: Si faltan datos críticos para un cálculo (ej. R_A de tierra, factor de agrupamiento), marca FALTA_INFORMACION.
4. Para sobrecargas, verifica estrictamente: Ib <= In <= Iz.
"""

# Función para generar el PDF en memoria con maquetación corregida
def generar_pdf(informe: InformeAuditoria, datos_txt: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    styles = getSampleStyleSheet()
    story = []

    # Estilos de texto personalizados
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=16, textColor=colors.HexColor('#1E3A8A'))
    cell_style = ParagraphStyle('CellStyle', parent=styles['Normal'], fontSize=8, leading=10)
    cell_header_style = ParagraphStyle('HeaderStyle', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.whitesmoke, fontName='Helvetica-Bold')

    # Título
    story.append(Paragraph("INFORME TÉCNICO DE PREAUDITORÍA ELECTROTÉCNICA (REBT)", title_style))
    story.append(Spacer(1, 10))

    # Resumen Ejecutivo
    story.append(Paragraph("<b>Resumen Ejecutivo:</b>", styles['Heading2']))
    story.append(Paragraph(informe.resumen_ejecutivo, styles['Normal']))
    story.append(Spacer(1, 10))

    # Datos Faltantes
    if informe.datos_faltantes_criticos:
        story.append(Paragraph("<b>Datos Faltantes Críticos:</b>", styles['Heading2']))
        for df in informe.datos_faltantes_criticos:
            story.append(Paragraph(f"• {df}", styles['Normal']))
        story.append(Spacer(1, 10))

    # Tabla de Hallazgos
    story.append(Paragraph("<b>Matriz de Hallazgos Normativos:</b>", styles['Heading2']))
    story.append(Spacer(1, 5))
    
    data = [[
        Paragraph("Estado", cell_header_style), 
        Paragraph("Elemento", cell_header_style), 
        Paragraph("ITC/Artículo", cell_header_style), 
        Paragraph("Análisis Técnico", cell_header_style)
    ]]
    
    for h in informe.hallazgos:
        data.append([
            Paragraph(f"<b>{h.estado.value}</b>", cell_style),
            Paragraph(h.elemento_afectado, cell_style),
            Paragraph(h.articulo_itc_aplicable, cell_style),
            Paragraph(h.justificacion_tecnica, cell_style)
        ])

    # Anchos ajustados para evitar solapamientos
    table = Table(data, colWidths=[120, 110, 80, 240])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# Interfaz Streamlit
st.title("⚡ Preauditor Normativo Electrotécnico (REBT)")
st.caption("Ficha técnica de entrada estructurada para auditoría industrial")

st.sidebar.header("Configuración")
api_key = st.sidebar.text_input("Introduce tu Gemini API Key:", type="password")

with st.form("formulario_instalacion"):
    st.subheader("1. Datos Generales y Entorno")
    col1, col2, col3 = st.columns(3)
    with col1:
        entorno = st.selectbox("Entorno / Tipo de local", ["Taller Industrial (Seco)", "Local Húmedo / Mojado", "Local con Riesgo de Incendio/Explosión (ATEX)", "Pública Concurrencia"])
        temp_ambiente = st.number_input("Temperatura ambiente (°C)", value=30)
    with col2:
        tension = st.selectbox("Tensión de suministro", ["Trifásico 400V (3P+N)", "Monofásico 230V"])
        esquema_tierra = st.selectbox("Esquema de distribución", ["TT", "TN-S", "TN-C", "IT"])
    with col3:
        r_tierra = st.text_input("Resistencia de tierra Ra (Ω)", placeholder="Ej: 25 (Dejar en blanco si no se midió)")

    st.subheader("2. Datos del Receptor / Carga")
    col4, col5, col6 = st.columns(3)
    with col4:
        potencia_kw = st.number_input("Potencia nominal (kW)", value=22.0, step=0.5)
        cos_phi = st.number_input("Factor de potencia (cos φ)", value=0.85, min_value=0.1, max_value=1.0)
    with col5:
        rendimiento = st.number_input("Rendimiento (η)", value=0.88, min_value=0.1, max_value=1.0)
        tipo_receptor = st.text_input("Tipo de receptor", value="Compresor de pistón")
    with col6:
        tipo_arranque = st.selectbox("Tipo de arranque", ["Directo (Ia = 6xIn)", "Estrella-Triángulo (Ia = 2.5xIn)", "Arrancador Suave", "Variador de Frecuencia"])

    st.subheader("3. Canalización y Conductores")
    col7, col8, col9 = st.columns(3)
    with col7:
        longitud_m = st.number_input("Longitud de línea (m)", value=65.0, step=1.0)
        seccion_mm2 = st.selectbox("Sección proyectada (mm² Cu)", [10, 2.5, 4, 6, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240])
    with col8:
        aislamiento = st.selectbox("Tipo de aislamiento", ["XLPE (90°C)", "PVC (70°C)", "EPR (90°C)"])
        metodo_inst = st.selectbox("Método de instalación (UNE 20460 / ITC-BT-19)", ["B2 (Bajo tubo en pared aislante)", "B1 (Bajo tubo sobre pared)", "C (Cables unipo/multipolares sobre pared)", "D (Bajo tubo subterráneo)", "E (Al aire en bandejas)"])
    with col9:
        seccion_pe = st.text_input("Sección Conductor Protección PE (mm²)", placeholder="Ej: 10 (Dejar en blanco si no se indica)")

    st.subheader("4. Protecciones en CGMP")
    col10, col11 = st.columns(2)
    with col10:
        in_pia = st.number_input("Intensidad nominal Magnetotérmico In (A)", value=50)
        curva_pia = st.selectbox("Curva magnetotérmico", ["C", "D", "B", "K"])
    with col11:
        in_diff = st.number_input("Intensidad nominal Diferencial (A)", value=63)
        sens_diff_ma = st.selectbox("Sensibilidad Diferencial (mA)", [30, 300, 500, 1000])

    st.subheader("5. Observaciones adicionales")
    observaciones = st.text_area("Cualquier otro dato técnico relevante:", placeholder="Ej: Agrupamiento con otras líneas, tipo de guardamotor instalado...")

    btn_evaluar = st.form_submit_button("🚀 Ejecutar Auditoría Estructurada", type="primary")

if btn_evaluar:
    if not api_key:
        st.error("Introduce tu Gemini API Key en el menú lateral.")
    else:
        datos_consolidados = f"""
        - Entorno: {entorno}, Temp ambiente: {temp_ambiente}°C
        - Red: {tension}, Esquema: {esquema_tierra}, Ra tierra: {r_tierra if r_tierra else 'NO ESPECIFICADO'}
        - Receptor: {tipo_receptor}, Potencia: {potencia_kw} kW, cos φ: {cos_phi}, rendimiento: {rendimiento}
        - Arranque: {tipo_arranque}
        - Línea: Longitud: {longitud_m} m, Sección: {seccion_mm2} mm² Cu, PE: {seccion_pe if seccion_pe else 'NO ESPECIFICADO'}
        - Cable/Canalización: Aislamiento {aislamiento}, Método {metodo_inst}
        - Magnetotérmico: In={in_pia}A, Curva {curva_pia}
        - Diferencial: In={in_diff}A, Sensibilidad={sens_diff_ma} mA
        - Observaciones: {observaciones}
        """
        
        with st.spinner("Analizando normas UNE y articulado del REBT..."):
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=f"Audita la siguiente instalación:\n{datos_consolidados}",
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        response_mime_type="application/json",
                        response_schema=InformeAuditoria,
                        temperature=0.1,
                    ),
                )
                informe = InformeAuditoria.model_validate_json(response.text)
                
                st.success("Auditoría completada exitosamente.")
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

                # Botón de descarga en PDF
                pdf_bytes = generar_pdf(informe, datos_consolidados)
                st.download_button(
                    label="📄 Descargar Informe Oficial en PDF",
                    data=pdf_bytes,
                    file_name="Informe_Auditoria_REBT.pdf",
                    mime="application/pdf",
                    type="secondary"
                )

            except Exception as e:
                st.error(f"Error en la ejecución: {str(e)}")