# calculos.py

import math

# Lista estándar de secciones comerciales en mm² Cu
SECCIONES_COMERCIALES = [1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240]

# Tabla simplificada de intensidades admisibles (Iz) a 40°C para conductores de Cobre
# Según UNE 20460 / ITC-BT-19 (Valores de referencia aproximados para 3 conductores cargados)
TABLA_IZ = {
    "B1 (Tubo en pared de obra)": {1.5: 14.5, 2.5: 19.5, 4: 26, 6: 34, 10: 46, 16: 61, 25: 80, 35: 99, 50: 119, 70: 151, 95: 182, 120: 210, 150: 240, 185: 273, 240: 321},
    "B2 (Tubo sobre pared / canal)": {1.5: 13.5, 2.5: 18, 4: 24, 6: 31, 10: 42, 16: 56, 25: 73, 35: 89, 50: 108, 70: 136, 95: 164, 120: 188, 150: 216, 185: 245, 240: 286},
    "C (Bandeja no perforada / aire)": {1.5: 17.5, 2.5: 24, 4: 32, 6: 41, 10: 57, 16: 76, 25: 96, 35: 119, 50: 144, 70: 184, 95: 223, 120: 259, 150: 299, 185: 341, 240: 403},
    "E (Bandeja perforada)": {1.5: 18.5, 2.5: 25, 4: 34, 6: 43, 10: 60, 16: 80, 25: 101, 35: 126, 50: 153, 70: 196, 95: 238, 120: 276, 150: 319, 185: 364, 240: 430},
    "D (Enterrado bajo tubo)": {1.5: 18, 2.5: 24, 4: 31, 6: 39, 10: 52, 16: 67, 25: 86, 35: 103, 50: 122, 70: 151, 95: 179, 120: 203, 150: 230, 185: 258, 240: 297}
}

def calcular_intensidad_empleo(potencia_kw: float, tension_str: str, cos_phi: float = 0.85, rendimiento: float = 1.0) -> float:
    """Calcula la corriente de empleo Ib en Amperios."""
    potencia_w = potencia_kw * 1000
    if "400V" in tension_str:
        # Trifásico
        v = 400
        ib = potencia_w / (math.sqrt(3) * v * cos_phi * rendimiento)
    else:
        # Monofásico 230V
        v = 230
        ib = potencia_w / (v * cos_phi * rendimiento)
    return round(ib, 2)

def calcular_caida_tension(potencia_kw: float, longitud_m: float, seccion_mm2: float, tension_str: str, cos_phi: float = 0.85, conductividad_cu: float = 56.0) -> tuple[float, float]:
    """Calcula la caída de tensión en voltios (dU_v) y en porcentaje (dU_pct)."""
    potencia_w = potencia_kw * 1000
    if "400V" in tension_str:
        v = 400
        # Formula trifásica: dU = (P * L) / (gamma * S * V)
        dv_v = (potencia_w * longitud_m) / (conductividad_cu * seccion_mm2 * v)
    else:
        v = 230
        # Formula monofásica: dU = (2 * P * L) / (gamma * S * V)
        dv_v = (2 * potencia_w * longitud_m) / (conductividad_cu * seccion_mm2 * v)
        
    dv_pct = (dv_v / v) * 100
    return round(dv_v, 2), round(dv_pct, 2)

def obtener_iz_tabulada(seccion_mm2: float, metodo_inst: str) -> float:
    """Obtiene la corriente admisible Iz del conductor según la tabla de instalación."""
    tabla_metodo = TABLA_IZ.get(metodo_inst, TABLA_IZ["B1 (Tubo en pared de obra)"])
    return tabla_metodo.get(seccion_mm2, 10.0)

def recomendar_seccion_correctora(potencia_kw: float, longitud_m: float, tension_str: str, cos_phi: float, rendimiento: float, metodo_inst: str, limite_pct: float = 5.0) -> tuple[float, float, float]:
    """
    Busca e identifica la sección comercial mínima de cobre que satisface:
    1. Iz >= Ib (Capacidad térmica)
    2. dU% <= límite normativo (Límite de caída de tensión)
    Retorna: (seccion_recomendada, iz_resultante, dv_pct_resultante)
    """
    ib = calcular_intensidad_empleo(potencia_kw, tension_str, cos_phi, rendimiento)
    
    for s in SECCIONES_COMERCIALES:
        iz = obtener_iz_tabulada(s, metodo_inst)
        _, dv_pct = calcular_caida_tension(potencia_kw, longitud_m, s, tension_str, cos_phi)
        
        if iz >= ib and dv_pct <= limite_pct:
            return s, iz, dv_pct
            
    return None, None, None
