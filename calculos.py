# calculos.py (Extracto actualizado)

# Resistividades a 20 °C (Ohm * mm² / m) y coeficientes térmicos (alpha)
PROPIEDADES_MATERIAL = {
    "Cobre (Cu)": {"rho_20": 1 / 56.0, "alpha": 0.00393},
    "Aluminio (Al)": {"rho_20": 1 / 35.0, "alpha": 0.00403}
}

def obtener_temperatura_servicio(aislamiento: str) -> float:
    """Retorna la temperatura máxima de servicio del conductor según el aislamiento."""
    return 90.0 if "XLPE" in aislamiento or "EPR" in aislamiento else 70.0

def calcular_conductividad_temperatura(material: str, temp_servicio: float) -> float:
    """Calcula la conductividad real (gamma_T) a la temperatura de servicio del conductor."""
    props = PROPIEDADES_MATERIAL.get(material, PROPIEDADES_MATERIAL["Cobre (Cu)"])
    rho_20 = props["rho_20"]
    alpha = props["alpha"]
    
    # Resistividad a la temperatura de servicio T
    rho_t = rho_20 * (1 + alpha * (temp_servicio - 20.0))
    gamma_t = 1.0 / rho_t
    return gamma_t

def calcular_caida_tension(
    potencia_kw: float, 
    longitud_m: float, 
    seccion_mm2: float, 
    tension_str: str, 
    cos_phi: float = 0.85, 
    material_conductor: str = "Cobre (Cu)",
    aislamiento: str = "XLPE / EPR (90 °C)"
) -> tuple[float, float]:
    """Calcula la caída de tensión exacta considerando la temperatura de servicio del conductor."""
    potencia_w = potencia_kw * 1000
    temp_servicio = obtener_temperatura_servicio(aislamiento)
    gamma_t = calcular_conductividad_temperatura(material_conductor, temp_servicio)
    
    if "400V" in tension_str:
        v = 400.0
        dv_v = (potencia_w * longitud_m) / (gamma_t * seccion_mm2 * v)
    else:
        v = 230.0
        dv_v = (2.0 * potencia_w * longitud_m) / (gamma_t * seccion_mm2 * v)
        
    dv_pct = (dv_v / v) * 100.0
    return round(dv_v, 2), round(dv_pct, 2)
