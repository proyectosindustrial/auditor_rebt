# Factores de corrección por temperatura ambiente (para cables de PVC y XLPE)
FACTORES_TEMP_XLPE = {
    25: 1.14, 30: 1.10, 35: 1.05, 40: 1.00, 45: 0.95, 50: 0.89, 55: 0.84, 60: 0.77
}

FACTORES_TEMP_PVC = {
    25: 1.18, 30: 1.12, 35: 1.06, 40: 1.00, 45: 0.94, 50: 0.87, 55: 0.79, 60: 0.71
}

# Factores de corrección por agrupamiento de varios circuitos (Bandejas / Tubos)
FACTORES_AGRUPAMIENTO = {
    1: 1.00, 2: 0.80, 3: 0.70, 4: 0.65, 5: 0.60, 6: 0.57, 7: 0.54, 8: 0.52, 9: 0.50
}

def calcular_iz_corregida(seccion_mm2: float, metodo_inst: str, temp_amb: int = 40, tipo_aislamiento: str = "XLPE / EPR (90 °C)", num_circuitos: int = 1) -> float:
    """Calcula Iz aplicando los coeficientes f1 (temperatura) y f2 (agrupamiento)."""
    iz_tabulada = obtener_iz_tabulada(seccion_mm2, metodo_inst)
    
    # Coeficiente por Temperatura (f1)
    tabla_temp = FACTORES_TEMP_XLPE if "XLPE" in tipo_aislamiento else FACTORES_TEMP_PVC
    f1 = tabla_temp.get(temp_amb, 1.00)
    
    # Coeficiente por Agrupamiento (f2)
    f2 = FACTORES_AGRUPAMIENTO.get(min(num_circuitos, 9), 0.50)
    
    iz_corregida = iz_tabulada * f1 * f2
    return round(iz_corregida, 2)
