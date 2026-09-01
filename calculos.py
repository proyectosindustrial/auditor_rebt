import math

# Tabla de intensidades admisibles (Iz) en Cu a 40°C (UNE 20460 / ITC-BT-19)
TABLA_IZ_CU_40C = {
    1.5:  {"B1": 14.5, "B2": 13.5, "C": 17.5, "E": 18.5, "D": 18.0},
    2.5:  {"B1": 19.5, "B2": 18.0, "C": 24.0, "E": 25.0, "D": 24.0},
    4:    {"B1": 26.0, "B2": 24.0, "C": 32.0, "E": 34.0, "D": 31.0},
    6:    {"B1": 34.0, "B2": 31.0, "C": 41.0, "E": 44.0, "D": 39.0},
    10:   {"B1": 46.0, "B2": 42.0, "C": 57.0, "E": 61.0, "D": 52.0},
    16:   {"B1": 61.0, "B2": 56.0, "C": 76.0, "E": 82.0, "D": 67.0},
    25:   {"B1": 80.0, "B2": 73.0, "C": 101.0, "E": 109.0, "D": 86.0},
    35:   {"B1": 99.0, "B2": 89.0, "C": 125.0, "E": 137.0, "D": 103.0},
    50:   {"B1": 119.0, "B2": 108.0, "C": 151.0, "E": 167.0, "D": 122.0},
    70:   {"B1": 151.0, "B2": 136.0, "C": 192.0, "E": 216.0, "D": 151.0},
    95:   {"B1": 182.0, "B2": 164.0, "C": 234.0, "E": 264.0, "D": 179.0},
    120:  {"B1": 210.0, "B2": 188.0, "C": 270.0, "E": 308.0, "D": 204.0},
    150:  {"B1": 240.0, "B2": 215.0, "C": 310.0, "E": 356.0, "D": 230.0},
    185:  {"B1": 273.0, "B2": 245.0, "C": 355.0, "E": 409.0, "D": 259.0},
    240:  {"B1": 321.0, "B2": 286.0, "C": 421.0, "E": 487.0, "D": 300.0},
}

def calcular_intensidad_empleo(potencia_kw: float, tension_str: str, cos_phi: float, rendimiento: float = 1.0) -> float:
    """Calcula la intensidad de empleo Ib (A)"""
    potencia_w = potencia_kw * 1000
    if "230V" in tension_str:
        ib = potencia_w / (230 * cos_phi * rendimiento)
    else:
        ib = potencia_w / (math.sqrt(3) * 400 * cos_phi * rendimiento)
    return round(ib, 2)

def calcular_caida_tension(potencia_kw: float, longitud_m: float, seccion_mm2: float, tension_str: str, cos_phi: float) -> tuple[float, float]:
    """Calcula la caída de tensión en voltios (dV) y en porcentaje (dV%)"""
    potencia_w = potencia_kw * 1000
    gamma_cu = 44.0  # Conductividad Cu a 90°C
    
    if "230V" in tension_str:
        v_nom = 230.0
        dv_volts = (2 * longitud_m * potencia_w) / (gamma_cu * seccion_mm2 * v_nom)
    else:
        v_nom = 400.0
        dv_volts = (longitud_m * potencia_w) / (gamma_cu * seccion_mm2 * v_nom)
        
    dv_porcentaje = (dv_volts / v_nom) * 100
    return round(dv_volts, 2), round(dv_porcentaje, 2)

def obtener_iz_tabulada(seccion_mm2: float, metodo_inst_str: str) -> float:
    """Obtiene Iz admisible tabulada según sección y método"""
    metodo_clave = metodo_inst_str.split()[0]
    sec_data = TABLA_IZ_CU_40C.get(seccion_mm2, {})
    return sec_data.get(metodo_clave, 0.0)
