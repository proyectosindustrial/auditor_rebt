# calculos.py

import math

# Lista estándar de secciones comerciales en mm² Cu
SECCIONES_COMERCIALES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240]

# Tabla simplificada de intensidades admisibles (Iz) a 40°C para conductores de Cobre
TABLA_IZ = {
    "B1 (Tubo en pared de obra)": {1.5: 14.5, 2.5: 19.5, 4: 26, 6: 34, 10: 46, 16: 61, 25: 80, 35: 99, 50: 119, 70: 151, 95: 182, 120: 210, 150: 240, 185: 273, 240: 321},
    "B2 (Tubo sobre pared / canal)": {1.5: 13.5, 2.5: 18, 4: 24, 6: 31, 10: 42, 16: 56, 25: 73, 35: 89, 50: 108, 70: 136, 95: 164, 120: 188, 150: 216, 185: 245, 240: 286},
    "C (Bandeja no perforada / aire)": {1.5: 17.5, 2.5: 24, 4: 32, 6: 41, 10: 57, 16: 76, 25: 96, 35: 119, 50: 144, 70: 184, 95: 223, 120: 259, 150: 299, 185: 341, 240: 403},
    "E (Bandeja perforada)": {1.5: 18.5, 2.5: 25, 4: 34, 6: 43, 10: 60, 16: 80, 25: 101, 35: 126, 50: 153, 70: 196, 95: 238, 120: 276, 150: 319, 185: 364, 240: 430},
    "D (Enterrado bajo tubo)": {1.5: 18, 2.5: 24, 4: 31, 6: 39, 10: 52, 16: 67, 25: 86, 35: 103, 50: 122, 70: 151, 95: 179, 120: 203, 150: 230, 185: 258, 240: 297}
}

# Factores de corrección por temperatura ambiente (f1)
FACTORES_TEMP_XLPE = {25: 1.14, 30: 1.10, 35: 1.05, 40: 1.00, 45: 0.95, 50: 0.89, 55: 0.84, 60: 0.77}
FACTORES_TEMP_PVC = {25: 1.18, 30: 1.12, 35: 1.06, 40: 1.00, 45: 0.94, 50: 0.87, 55: 0.79, 60: 0.71}

# Factores de corrección por agrupamiento de circuitos (f2)
FACTORES_AGRUPAMIENTO = {1: 1.00, 2: 0.80, 3: 0.70, 4: 0.65, 5: 0.60, 6: 0.57, 7: 0.54, 8: 0.52, 9: 0.50}

def calcular_intensidad_empleo(potencia_kw: float, tension_str: str, cos_phi: float = 0.85, rendimiento: float = 1.0) -> float:
    """Calcula la corriente de empleo Ib en Amperios."""
    potencia_w = potencia_kw * 1000
    if "400V" in tension_str:
        v = 400
        ib = potencia_w / (math.sqrt(3) * v * cos_phi * rendimiento)
    else:
        v = 230
        ib = potencia_w / (v * cos_phi * rendimiento)
    return round(ib, 2)

def calcular_caida_tension(potencia_kw: float, longitud_m: float, seccion_mm2: float, tension_str: str, cos_phi: float = 0.85, conductividad_cu: float = 56.0) -> tuple[float, float]:
    """Calcula la caída de tensión en voltios (dU_v) y en porcentaje (dU_pct)."""
    potencia_w = potencia_kw * 1000
    if "400V" in tension_str:
        v = 400
        dv_v = (potencia_w * longitud_m) / (conductividad_cu * seccion_mm2 * v)
    else:
        v = 230
        dv_v = (2 * potencia_w * longitud_m) / (conductividad_cu * seccion_mm2 * v)
        
    dv_pct = (dv_v / v) * 100
    return round(dv_v, 2), round(dv_pct, 2)

def obtener_iz_tabulada(seccion_mm2: float, metodo_inst: str) -> float:
    """Obtiene la corriente admisible base de la tabla."""
    tabla_metodo = TABLA_IZ.get(metodo_inst, TABLA_IZ["B1 (Tubo en pared de obra)"])
    return tabla_metodo.get(seccion_mm2, 10.0)

def calcular_iz_corregida(seccion_mm2: float, metodo_inst: str, temp_amb: int = 40, tipo_aislamiento: str = "XLPE / EPR (90 °C)", num_circuitos: int = 1) -> float:
    """Calcula Iz aplicando coeficientes de temperatura (f1) y agrupamiento (f2)."""
    iz_tabulada = obtener_iz_tabulada(seccion_mm2, metodo_inst)
    
    tabla_temp = FACTORES_TEMP_XLPE if "XLPE" in tipo_aislamiento else FACTORES_TEMP_PVC
    f1 = tabla_temp.get(temp_amb, 1.00)
    f2 = FACTORES_AGRUPAMIENTO.get(min(num_circuitos, 9), 0.50)
    
    return round(iz_tabulada * f1 * f2, 2)

def recomendar_seccion_correctora(potencia_kw: float, longitud_m: float, tension_str: str, cos_phi: float, rendimiento: float, metodo_inst: str, temp_amb: int, aislamiento: str, num_circuitos: int, limite_pct: float = 5.0) -> tuple[float, float, float]:
    """Busca e identifica la sección comercial mínima aplicando coeficientes de corrección."""
    ib = calcular_intensidad_empleo(potencia_kw, tension_str, cos_phi, rendimiento)
    
    for s in SECCIONES_COMERCIALES:
        iz = calcular_iz_corregida(s, metodo_inst, temp_amb, aislamiento, num_circuitos)
        _, dv_pct = calcular_caida_tension(potencia_kw, longitud_m, s, tension_str, cos_phi)
        
        if iz >= ib and dv_pct <= limite_pct:
            return s, iz, dv_pct
            
    return None, None, None
