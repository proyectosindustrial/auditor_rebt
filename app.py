# app.py

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

from calculos import (
    calcular_intensidad_empleo, 
    calcular_caida_tension, 
    calcular_iz_corregida,
    calcular_seccion_pe_minima,
    recomendar_seccion_correctora
)
from database import init_db, guardar_auditoria, obtener_historial, obtener_auditoria_por_id

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
    elemento_afectado: str = Field(description="Ej: Sección Cable, Magnetotérmico, Caída de Tensión, PE/Neutro")
    articulo_itc_aplicable: str = Field(description="Ej: ITC-BT-19, ITC-BT-22, Art. 18")
    estado: EstadoCumplimiento
    dato_provocador: str = Field(description="El dato que origina el hallazgo")
    requisito_normativo: str = Field(description="Lo que exige la norma exactamente")
    justificacion_tecnica: str = Field(description="Explicación detallada del cálculo o incoherencia")

class InformeAuditoria(BaseModel):
    resumen_ejecutivo: str = Field(description="Resumen de 2-3 frases del estado general de la instalación")
    hallazgos: list[HallazgoNormativo]
    datos_faltantes_criticos: list[str] = Field(description="Lista de datos no proporcionados imprescindibles")

SYSTEM_INSTRUCTION = """
Eres un Ingeniero Inspector Industrial de Alta Calificación, especialista en el REBT (Real Decreto 842/2002) de España e ITCs.

Tu objetivo es auditar los datos proporcionados y generar un informe técnico estructurado e inflexible.

IMPORTANTE: Se te proporcionan cálculos deterministas ya ejecutados con factores de corrección por temperatura, agrupamiento y material. UTILIZA ESTOS VALORES CALCULADOS PARA TU EVALUACIÓN.

Reglas estrictas de auditoría:
1. Coordinación de Protecciones (ITC-BT-19 / ITC-BT-22): Ib <= In <= Iz.
2. Caída de Tensión (ITC-BT-19): Verificar límites (3% alumbrado, 5% otros).
3. Protección Diferencial y Puesta a Tierra (ITC-BT-18 / ITC-BT-24): En TT, Ra * IΔn <= 50V (o 24V locales húmedos/obras).
4. Sección del Conductor PE y Neutro (ITC-BT-18 / ITC-BT-19): Verificar Spe >= Sfase si Sfase <= 16mm² y Spe >= Sfase/2 si Sfase > 16mm².
5. Inflexibilidad Técnica: Si falta un dato crítico, marcar REQUIERE ACLARACIÓN.

Responde EXCLUSIVAMENTE en el formato JSON estructurado requerido.
"""

def generar_auditoria_local(ib: float, iz: float, dv_pct: float, limite_du: float, in_pia: float, r_tierra: float, sens_diff_ma: float, seccion_mm2: float, seccion_pe: float, seccion_n: float, sec_rec: float, material: str) -> InformeAuditoria:
    hallazgos = []
    faltantes = []

    # 1. Capacidad térmica del conductor
    if ib <= iz:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado=f"Sección de Conductor Fase ({material})",
            articulo_itc_aplicable="ITC-BT-19",
            estado=EstadoCumplimiento.CUMPLE,
            dato_provocador=f"Ib = {ib} A <= Iz corregida = {iz} A",
            requisito_normativo="La intensidad admisible corregida (Iz) debe ser superior o igual a la intensidad de empleo (Ib).",
            justificacion_tecnica="El conductor seleccionado soportará la carga aplicando coeficientes de agrupamiento, temperatura y material."
        ))
    else:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado=f"Sección de Conductor Fase ({material})",
            articulo_itc_aplicable="ITC-BT-19",
            estado=EstadoCumplimiento.NO_CUMPLE,
            dato_provocador=f"Ib = {ib} A > Iz corregida = {iz} A",
            requisito_normativo="La corriente admisible corregida del cable (Iz) debe ser mayor o igual que la corriente de servicio (Ib).",
            justificacion_tecnica=f"Riesgo térmico grave. Aumentar sección a mínimo {sec_rec} mm²."
        ))

    # 2. Coordinación de protección frente a sobrecargas
    if ib <= in_pia <= iz:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Coordinación de Magnetotérmico (Ib <= In <= Iz)",
            articulo_itc_aplicable="ITC-BT-22 / ITC-BT-19",
            estado=EstadoCumplimiento.CUMPLE,
            dato_provocador=f"Ib ({ib} A) <= In ({in_pia} A) <= Iz ({iz} A)",
            requisito_normativo="In debe cumplir estrictamente Ib <= In <= Iz.",
            justificacion_tecnica="El calibre nominal del PIA garantiza la protección sin disparos intempestivos."
        ))
    else:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Coordinación de Magnetotérmico (Ib <= In <= Iz)",
            articulo_itc_aplicable="ITC-BT-22 / ITC-BT-19",
            estado=EstadoCumplimiento.NO_CUMPLE,
            dato_provocador=f"In = {in_pia} A fuera de rango Ib = {ib} A / Iz = {iz} A",
            requisito_normativo="In debe cumplir estrictamente Ib <= In <= Iz.",
            justificacion_tecnica="Si In > Iz el cable no está protegido contra sobrecargas. Si In < Ib la protección disparará en servicio regular."
        ))

    # 3. Caída de Tensión
    if dv_pct <= limite_du:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Caída de Tensión (dU%)",
            articulo_itc_aplicable="ITC-BT-19",
            estado=EstadoCumplimiento.CUMPLE,
            dato_provocador=f"dU = {dv_pct}% <= {limite_du}%",
            requisito_normativo=f"La caída de tensión no debe superar el {limite_du}%.",
            justificacion_tecnica="El voltaje en el receptor se mantiene dentro de los márgenes admisibles."
        ))
    else:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Caída de Tensión (dU%)",
            articulo_itc_aplicable="ITC-BT-19",
            estado=EstadoCumplimiento.NO_CUMPLE,
            dato_provocador=f"dU = {dv_pct}% > {limite_du}%",
            requisito_normativo=f"La caída de tensión no debe superar el {limite_du}%.",
            justificacion_tecnica=f"Exceso de caída de tensión. Redimensionar a mínimo {sec_rec} mm²."
        ))

    # 4. Dimensionamiento de PE y Neutro
    pe_min = calcular_seccion_pe_minima(seccion_mm2)
    if seccion_pe >= pe_min:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Sección Conductor Proteccion (PE)",
            articulo_itc_aplicable="ITC-BT-18 / Tabla 2",
            estado=EstadoCumplimiento.CUMPLE,
            dato_provocador=f"SPE = {seccion_pe} mm² >= SPE_mín = {pe_min} mm²",
            requisito_normativo=f"Para Sfase = {seccion_mm2} mm², SPE debe ser de al menos {pe_min} mm².",
            justificacion_tecnica="El conductor de protección garantiza la evacuación de corrientes de defecto sin sobrecalentamiento."
        ))
    else:
        hallazgos.append(HallazgoNormativo(
            elemento_afectado="Sección Conductor Proteccion (PE)",
            articulo_itc_aplicable="ITC-BT-18 / Tabla 2",
            estado=EstadoCumplimiento.NO_CUMPLE,
            dato_provocador=f"SPE = {seccion_pe} mm² < SPE_mín = {pe_min} mm²",
            requisito_normativo=f"Para Sfase = {seccion_mm2} mm², SPE debe ser de al menos {pe_min} mm².",
            justificacion_tecnica="Sección de protección insuficiente según la norma. Aumentar el conductor de tierra a mínimo la sección requerida."
        ))

    # 5. Protección contra contactos indirectos (Esquema TT)
    if r_tierra > 0:
        v_contacto = r_tierra * (sens_diff_ma / 1000.0)
        if v_contacto <= 50.0:
            hallazgos.append(HallazgoNormativo(
                elemento_afectado="Protección Diferencial y Tierra",
                articulo_itc_aplicable="ITC-BT-18 / ITC-BT-24",
                estado=EstadoCumplimiento.CUMPLE,
                dato_provocador=f"Ra * IΔn = {r_tierra} Ω * {sens_diff_ma} mA = {round(v_contacto, 2)} V <= 50 V",
                requisito_normativo="La tensión de defecto no debe superar 50 V.",
                justificacion_tecnica="El diferencial desconectará el circuito antes de alcanzar tensiones peligrosas."
            ))
        else:
            hallazgos.append(HallazgoNormativo(
                elemento_afectado="Protección Diferencial y Tierra",
                articulo_itc_aplicable="ITC-BT-18 / ITC-BT-24",
                estado=EstadoCumplimiento.NO_CUMPLE,
                dato_provocador=f"Ra * IΔn = {round(v_contacto, 2)} V > 50 V",
                requisito_normativo="Tensión de contacto máxima admisible en instalaciones generales = 50 V.",
                justificacion_tecnica="Resistencia de tierra excesivamente alta para la sensibilidad del diferencial."
            ))
    else:
        faltantes.append("Resistencia de la toma de tierra (Ra) no especificada. Imposible validar contactos indirectos (ITC-BT-18).")

    resumen = "Auditoría ejecutada mediante motor determinista local. " + (
        "La instalación cumple con los preceptos fundamentales del REBT." if all(h.estado == EstadoCumplimiento.CUMPLE for h in hallazgos)
        else "Se han detectado incumplimientos normativos críticos que requieren corrección de diseño."
    )

    return InformeAuditoria(
        resumen_ejecutivo=resumen,
        hallazgos=hallazgos,
        datos_faltantes_criticos=faltantes
    )

def generar_pdf(informe: InformeAuditoria, datos_entrada: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    story = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=18, leading=22, textColor=colors.HexColor("#1E3A8A"), spaceAfter=12)
    h2_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=13, leading=16, textColor=colors.HexColor("#1E3A8A"), spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle('BodyDark', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#111827"))
    header_cell_style = ParagraphStyle('HeaderCell', parent=styles['Normal'], fontSize=9, leading=11, textColor=colors.white, fontName="Helvetica-Bold")

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
        temp_ambiente = st.select_slider("Temperatura ambiente (°C)", options=[25, 30, 35, 40, 45, 50, 55, 60], value=40)
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
        material_conductor = st.selectbox("Material del conductor", ["Cobre (Cu)", "Aluminio (Al)"])
        longitud_m = st.number_input("Longitud de la línea (m)", value=45.0, step=1.0)
        seccion_mm2 = st.selectbox("Sección fase (mm²)", [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240], index=3)
        seccion_neutro = st.selectbox("Sección neutro (mm²)", [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240], index=3)
        seccion_pe = st.selectbox("Sección de protección PE (mm²)", [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240], index=3)

    with col4:
        aislamiento = st.selectbox("Tipo de aislamiento", ["XLPE / EPR (90 °C)", "PVC (70 °C)"])
        metodo_inst = st.selectbox("Método de instalación (UNE 20460)", ["B1 (Tubo en pared de obra)", "B2 (Tubo sobre pared / canal)", "C (Bandeja no perforada / aire)", "E (Bandeja perforada)", "D (Enterrado bajo tubo)"])
        num_circuitos = st.number_input("Número de circuitos agrupados en canalización", value=1, min_value=1, max_value=9)

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
        ib_calc = calcular_intensidad_empleo(potencia_kw, tension, cos_phi, rendimiento)
        dv_v, dv_pct = calcular_caida_tension(potencia_kw, longitud_m, seccion_mm2, tension, cos_phi, material_conductor)
        iz_calc = calcular_iz_corregida(seccion_mm2, metodo_inst, temp_ambiente, aislamiento, num_circuitos, material_conductor)
        limite_du_norma = 3.0 if "Alumbrado" in tipo_receptor else 5.0

        st.info(f"**Valores deterministas corregidos ({material_conductor}):** $I_b = {ib_calc}\\text{{ A}}$ | $I_z (corregida) = {iz_calc}\\text{{ A}}$ | $\\Delta U = {dv_pct}\\%$")

        sec_rec, iz_rec, dv_rec = recomendar_seccion_correctora(
            potencia_kw, longitud_m, tension, cos_phi, rendimiento, metodo_inst, temp_ambiente, aislamiento, num_circuitos, material_conductor, limite_pct=limite_du_norma
        )

        if ib_calc > iz_calc or dv_pct > limite_du_norma:
            if sec_rec:
                st.warning(
                    f"💡 **Recomendación Correctora Directa (Cálculo Determinista):**\n\n"
                    f"La sección introducida ({seccion_mm2} mm² {material_conductor}) no es apta. Aumenta la sección a **{sec_rec} mm²**.\n"
                    f"- Nueva Intensidad Admisible Corregida ($I_z$): **{iz_rec} A** (suficiente para $I_b = {ib_calc} A$)\n"
                    f"- Nueva Caída de Tensión ($\\Delta U$): **{dv_rec}%** (cumple límite de {limite_du_norma}%)"
                )

        datos_consolidados = f"""
        --- CÁLCULOS FÍSICOS DETERMINISTAS (CON FACTORES DE CORRECCIÓN) ---
        * Material Conductor: {material_conductor}
        * Intensidad de empleo calculada (Ib): {ib_calc} A
        * Caída de tensión calculada (dU): {dv_v} V ({dv_pct} %)
        * Intensidad admisible corregida (Iz con f1={temp_ambiente}°C y f2={num_circuitos} circ): {iz_calc} A

        --- DATOS DE ENTRADA DE LA INSTALACIÓN ---
        - Nombre: {nombre_inst}
        - Entorno: {entorno}, Temp ambiente: {temp_ambiente}°C
        - Red: {tension}, Esquema: {esquema_tierra}, Ra tierra: {r_tierra if r_tierra > 0 else 'NO ESPECIFICADO'}
        - Receptor: {tipo_receptor}, Potencia: {potencia_kw} kW, cos φ: {cos_phi}, rendimiento: {rendimiento}
        - Arranque: {tipo_arranque}
        - Línea: Longitud: {longitud_m} m, Material: {material_conductor}, Sección Fase: {seccion_mm2} mm², Neutro: {seccion_neutro} mm², PE: {seccion_pe} mm²
        - Cable/Canalización: Aislamiento {aislamiento}, Método {metodo_inst}, Agrupamiento: {num_circuitos} circuitos
        - Magnetotérmico: In={in_pia}A, Curva {curva_pia}
        - Diferencial: In={in_diff}A, Sensibilidad={sens_diff_ma} mA
        - Observaciones: {observaciones}
        """

        informe = None
        raw_json = ""

        if api_key:
            with st.spinner("Procesando auditoría con IA..."):
                client = genai.Client(api_key=api_key)
                modelo_objetivo = "gemini-3.6-flash"
                for intento in range(2):
                    try:
                        response = client.models.generate_content(
                            model=modelo_objetivo,
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
                        break
                    except Exception:
                        time.sleep(1)
                        continue

        if not informe:
            st.info("ℹ️ **Modo de Auditoría Local Activo:** Generando informe regulatorio completo mediante reglas de ingeniería en Python.")
            informe = generar_auditoria_local(ib_calc, iz_calc, dv_pct, limite_du_norma, in_pia, r_tierra, sens_diff_ma, seccion_mm2, seccion_pe, seccion_neutro, sec_rec, material_conductor)
            raw_json = informe.model_dump_json()

        auditoria_id = guardar_auditoria(nombre_inst, datos_consolidados, raw_json)
        st.toast(f"Guardado en base de datos con ID #{auditoria_id}")

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
            type="primary"
        )

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
