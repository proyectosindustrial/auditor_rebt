with st.spinner("Procesando auditoría..."):
    client = genai.Client(api_key=api_key)
    
    # 1. Obtener dinámicamente los modelos que soporten generateContent en tu cuenta
    try:
        modelos_remotos = client.models.list()
        # Filtramos los nombres oficiales disponibles (ej. 'gemini-2.5-flash', 'gemini-3.1-pro-preview', etc.)
        modelos_candidatos = [
            m.name.replace("models/", "") 
            for m in modelos_remotos 
            if "generateContent" in getattr(m, "supported_generation_methods", [])
        ]
    except Exception:
        # Respaldo con lo que sugiere tu propio mensaje de error
        modelos_candidatos = ["gemini-3.1-pro-preview", "gemini-2.5-flash"]

    informe = None
    raw_json = ""
    ultimo_error = ""
    modelo_exitoso = ""

    # 2. Iterar sobre los modelos reales disponibles
    for mod in modelos_candidatos:
        for intento in range(3):
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
                if "503" in ultimo_error or "UNAVAILABLE" in ultimo_error:
                    time.sleep(1.5 ** intento)
                    continue
                break # Si el error es 404 u otro, pasa de inmediato al siguiente modelo
        if informe:
            break
