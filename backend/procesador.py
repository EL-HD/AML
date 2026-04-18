import pandas as pd
import numpy as np

def validar_columnas(df):
    """
    Valida que el DataFrame contenga las columnas requeridas.
    Retorna (True, None) si es válido, (False, listado_faltantes) si faltan columnas.
    """
    columnas_requeridas = ["Cliente", "Monto", "Perfil", "Fecha", "TipoOperacion"]
    faltantes = [c for c in columnas_requeridas if c not in df.columns]
    
    if faltantes:
        return False, faltantes
    return True, None

def _detectar_columnas_pep_cpe(df):
    """
    Detecta si existen columnas de PEP/CPE en el DataFrame.
    Prioriza los nombres exactos: EsPep, EsCpe.
    """
    cols = df.columns.tolist()
    columns_lower = {c.lower(): c for c in cols}
    
    result = {
        "pep_col": None,
        "cpe_col": None,
        "has_pep": False,
        "has_cpe": False
    }
    
    # 1. Buscar nombres exactos sugeridos por el usuario
    if "EsPep" in cols:
        result["pep_col"] = "EsPep"
        result["has_pep"] = True
    elif "espep" in columns_lower:
        result["pep_col"] = columns_lower["espep"]
        result["has_pep"] = True
        
    if "EsCpe" in cols:
        result["cpe_col"] = "EsCpe"
        result["has_cpe"] = True
    elif "escpe" in columns_lower:
        result["cpe_col"] = columns_lower["escpe"]
        result["has_cpe"] = True
        
    return result


def _convertir_a_bool(valor):
    """Convierte diversos valores a booleano para PEP/CPE."""
    if pd.isna(valor):
        return False
    val_str = str(valor).strip().lower()
    return val_str in ["si", "sí", "s", "yes", "y", "true", "1", "pep", "persona expuesta", "x", "checked", "on"]

# ═══════════════════════════════════════════════════════════════════════════════
# MOTOR DE SCORING IMPERATOR — Modelo ISO 31000 / GAFI / RBA
# Score_Final = 0.40·S_T + 0.25·S_C + 0.20·S_B + 0.15·S_N  (escala 0–10)
# ═══════════════════════════════════════════════════════════════════════════════

def _calcular_st(df, cfg):
    """
    S_T = Riesgo Transaccional (normalizado 0–10)
    Pesos: monto_alto=2.0, acumulado=1.5, exceso_perfil=2.0,
           frecuencia=1.0, smurfing=2.5, pico=1.5  → máx=10.5
    """
    r_monto   = df["Alerta_Absoluto"].astype(float)  * 2.0
    r_acum    = df["Alerta_Acumulado"].astype(float)  * 1.5
    r_perfil  = df["Alerta_15"].astype(float)         * 2.0
    r_frec    = df["Alerta_Frecuencia"].astype(float) * 1.0
    r_smurf   = df["Smurfing"].astype(float)          * 2.5
    r_pico    = df["Pico"].astype(float)              * 1.5
    S_T_raw   = r_monto + r_acum + r_perfil + r_frec + r_smurf + r_pico
    S_T_max   = 10.5
    return (S_T_raw / S_T_max) * 10.0


def _calcular_sc(df):
    """
    S_C = Riesgo Contextual (normalizado 0–10)
    PEP peso=4, CPE peso=2, Geo peso_max=1 (0.2 bajo, 0.5 medio, 1.0 alto)
    S_C_max = 4 + 2 + 1 = 7
    """
    pep = df["EsPEP"].astype(float)  * 4.0
    cpe = df["EsCPE"].astype(float)  * 2.0
    # Ubicación de riesgo se mapea a 1.0 si riesgo alto, 0 si no
    geo = df["Ubicacion_Riesgo"].astype(float) * 1.0
    S_C_raw = pep + cpe + geo
    S_C_max = 7.0
    return (S_C_raw / S_C_max) * 10.0


def _calcular_sb(df):
    """
    S_B = Riesgo Conductual (normalizado 0–10)
    S_B = log(1 + |Monto - Perfil| / Perfil)
    S_B_norm = min(S_B * 5, 10)
    """
    perfil_safe = df["Perfil"].replace(0, 1)  # evitar div/0
    desviacion  = (df["Monto"] - perfil_safe).abs() / perfil_safe
    S_B_log     = np.log1p(desviacion)
    return (S_B_log * 5.0).clip(upper=10.0)


def _calcular_sn(df, casos):
    """
    S_N = Riesgo de Red (normalizado 0–10)
    Basado en: riesgo promedio vecinos, volumen de la red, frecuencia de interacción.
    
    Si existe columna Cliente_Destino: construye grafo y calcula vecinos.
    Si no existe: usa volumen relativo como proxy simple.
    """
    # Intentar grafo real si hay columna Cliente_Destino
    has_destino = "Cliente_Destino" in df.columns and df["Cliente_Destino"].notna().any()
    
    if has_destino:
        # Riesgo promedio de los vecinos (basado en score transaccional)
        # Mapa cliente → score_total_max provisional
        score_map = casos.set_index("Cliente")["Score_Provisional"].to_dict() if "Score_Provisional" in casos.columns else {}
        
        # Para cada fila, obtener el score del destino
        dest_risk = df["Cliente_Destino"].map(score_map).fillna(0.0)
        
        # Volumen de red por cliente (suma de montos enviados/recibidos)
        vol_enviado  = df.groupby("Cliente")["Monto"].sum()
        vol_recibido = df.groupby("Cliente_Destino")["Monto"].sum() if has_destino else pd.Series(dtype=float)
        vol_red = (vol_enviado.add(vol_recibido, fill_value=0)).reindex(df["Cliente"]).values
        vol_max = max(vol_red.max() if len(vol_red) > 0 else 1, 1)
        
        # Frecuencia de interacción (transacciones como origen o destino)
        frec_red_map = df.groupby("Cliente").size().to_dict()
        frec_envio = df["Cliente"].map(frec_red_map).fillna(0)
        frec_max   = max(frec_envio.max(), 1)
        
        S_N_raw = (0.5 * (dest_risk / 10.0) * 10.0 +
                   0.3 * (vol_red / vol_max) * 10.0 +
                   0.2 * (frec_envio / frec_max) * 10.0)
        
        # Boost: conexión a nodo crítico (+2 puntos)
        nodos_criticos = set(casos[casos.get("Nivel_Provisional", casos.index) if False else
                                   casos["Score_Provisional"] >= 8]["Cliente"].tolist()) if "Score_Provisional" in casos.columns else set()
        conexion_critica = df["Cliente_Destino"].isin(nodos_criticos).astype(float) * 2.0
        S_N_raw = (S_N_raw + conexion_critica).clip(upper=10.0)
    else:
        # Proxy: volumen relativo del cliente respecto al total
        vol_cliente = df.groupby("Cliente")["Monto"].sum()
        vol_max     = max(vol_cliente.max(), 1)
        # Asignar a cada fila el vol de su cliente
        S_N_raw = df["Cliente"].map(vol_cliente / vol_max * 8.0).fillna(0.0)
    
    return S_N_raw.clip(upper=10.0)


def procesar_transacciones(df, cfg):
    """
    Aplica las reglas de negocio AML al DataFrame de transacciones.
    Implementa el modelo de scoring IMPERATOR basado en ISO 31000.
    
    Retorna: (df_procesado, casos, matriz_alertas, info_pep_cpe)
    info_pep_cpe: {has_pep, has_cpe, pep_count, cpe_count, asociados_riesgo, ubicacion_riesgo_count}
    """
    
    # Asegurar el formato de fecha
    df["Fecha"] = pd.to_datetime(df["Fecha"])

    # --- Detectar columnas PEP/CPE y Ubicación ---
    pep_cpe_info = _detectar_columnas_pep_cpe(df)
    
    # Procesar columnas PEP si existen
    if pep_cpe_info["has_pep"]:
        pep_col = pep_cpe_info["pep_col"]
        df["EsPEP"] = df[pep_col].apply(_convertir_a_bool)
    else:
        df["EsPEP"] = False
    
    # Procesar columnas CPE si existen
    if pep_cpe_info["has_cpe"]:
        cpe_col = pep_cpe_info["cpe_col"]
        df["EsCPE"] = df[cpe_col].apply(_convertir_a_bool)
    else:
        df["EsCPE"] = False
    
    # --- Regla: Ubicación de Riesgo ---
    df["Ubicacion_Riesgo"] = False
    
    if cfg.get("regla_ubicacion", True):
        if "UbicacionRiesgo" in df.columns:
            df["Ubicacion_Riesgo"] = df["UbicacionRiesgo"].apply(_convertir_a_bool)
        
        manual_list = [str(loc).lower() for loc in cfg.get("ubicaciones_manuales", [])]
        if manual_list and "Ubicacion" in df.columns:
            manual_risk = df["Ubicacion"].astype(str).str.lower().isin(manual_list)
            df["Ubicacion_Riesgo"] = df["Ubicacion_Riesgo"] | manual_risk

    # Contadores PEP/CPE
    pep_cpe_info["pep_count"]             = int(df["EsPEP"].sum())
    pep_cpe_info["cpe_count"]             = int(df["EsCPE"].sum())
    pep_cpe_info["asociados_riesgo"]      = pep_cpe_info["pep_count"] + pep_cpe_info["cpe_count"]
    pep_cpe_info["ubicacion_riesgo_count"] = int(df["Ubicacion_Riesgo"].sum())

    # ── REGLAS DE DETECCIÓN (controladas por cfg) ──────────────────────────
    df["Alerta_15"]       = (df["Monto"] > df["Perfil"] * (1 + cfg["tolerancia_perfil"] / 100)) & cfg["regla_perfil"]
    df["Alerta_Absoluto"] = (df["Monto"] > cfg["umbral_absoluto"]) & cfg["regla_absoluto"]

    total = df.groupby("Cliente")["Monto"].sum().reset_index()
    total.columns = ["Cliente", "Total_Mensual"]
    df = df.merge(total)
    df["Alerta_Acumulado"] = (df["Total_Mensual"] > df["Perfil"] * cfg["mult_acumulado"]) & cfg["regla_acumulado"]

    freq = df.groupby("Cliente").size().reset_index(name="Transacciones")
    df = df.merge(freq)
    df["Alerta_Frecuencia"] = (df["Transacciones"] > cfg["umbral_frecuencia"]) & cfg["regla_frecuencia"]

    df["Fecha_dia"] = df["Fecha"].dt.date
    smurf = df.groupby(["Cliente", "Fecha_dia"]).size().reset_index(name="Count")
    smurf["Smurfing"] = (smurf["Count"] >= cfg["umbral_smurfing"]) & cfg["regla_smurfing"]
    df = df.merge(smurf, on=["Cliente", "Fecha_dia"])

    stats = df.groupby("Cliente")["Monto"].agg(["mean", "std"]).reset_index()
    stats.columns = ["Cliente", "Media", "Std"]
    df = df.merge(stats)
    df["Pico"] = (df["Monto"] > (df["Media"] + cfg["mult_std_pico"] * df["Std"])) & cfg["regla_pico"]

    # ── MODELO IMPERATOR — 4 COMPONENTES (ISO 31000) ────────────────────────
    # Paso 1: calcular S_T, S_C, S_B (S_N requiere casos parciales)
    df["_ST"] = _calcular_st(df, cfg)
    df["_SC"] = _calcular_sc(df)
    df["_SB"] = _calcular_sb(df)

    # Paso 2: Score provisional (sin S_N) para calcular S_N en base a vecinos
    w1, w2, w3, w4 = cfg["w_st"], cfg["w_sc"], cfg["w_sb"], cfg["w_sn"]
    df["Score_Provisional"] = w1 * df["_ST"] + w2 * df["_SC"] + w3 * df["_SB"]

    # Construir casos provisionales para S_N
    casos_prov = df.groupby("Cliente").agg(Score_Provisional=("Score_Provisional", "max")).reset_index()

    # Paso 3: S_N usando riesgo de vecinos
    df["_SN"] = _calcular_sn(df, casos_prov)

    # ── Paso 4: Score total antes de ajustes ──────────────────────────────
    df["Score_Total"] = w1 * df["_ST"] + w2 * df["_SC"] + w3 * df["_SB"] + w4 * df["_SN"]

    # ── Paso 5: Factor de mitigación (riesgo residual) ─────────────────────
    # Control_eff ∈ [0, 0.5] — se puede ampliar en cfg en el futuro
    control_eff = cfg.get("control_efectividad", 0.0)  # default 0 = sin reducción
    df["Score_Residual"] = df["Score_Total"] * (1.0 - control_eff)

    # ── Paso 6: Boost por sinergia (factores agravantes) ───────────────────
    # γ = 1.0, PEP+Smurfing → +2, Geo_alto+Pico → +1
    gamma = 1.0
    boost_pep_smurf = (df["EsPEP"].astype(float) * df["Smurfing"].astype(float)) * 2.0
    boost_geo_pico  = (df["Ubicacion_Riesgo"].astype(float) * df["Pico"].astype(float)) * 1.0
    df["Boost"]     = gamma * (boost_pep_smurf + boost_geo_pico)

    # ── Paso 7: Score Final ─────────────────────────────────────────────────
    df["Score"] = (df["Score_Residual"] + df["Boost"]).clip(upper=10.0)

    # ── CASOS POR CLIENTE ───────────────────────────────────────────────────
    casos = df.groupby("Cliente").agg(
        Total_Mensual    = ("Monto", "sum"),
        Score_Max        = ("Score", "max"),
        ST_Max           = ("_ST", "max"),
        SC_Max           = ("_SC", "max"),
        SB_Max           = ("_SB", "max"),
        SN_Max           = ("_SN", "max"),
        Transacciones    = ("Transacciones", "max"),
        EsPEP            = ("EsPEP", "max"),
        EsCPE            = ("EsCPE", "max"),
        Ubicacion_Riesgo = ("Ubicacion_Riesgo", "max"),
        Smurfing_Count   = ("Smurfing", "sum"),
        Pico_Count       = ("Pico", "sum"),
    ).reset_index()

    # ── CLASIFICACIÓN DE RIESGO (escala 0–10) ──────────────────────────────
    def riesgo_cliente(row):
        s = row["Score_Max"]
        if s >= 8.0 or row["Total_Mensual"] > cfg["monto_critico"]:
            return "Crítico"
        elif s >= 5.0:
            return "Alto"
        elif s >= 3.0:
            return "Medio"
        return "Bajo"

    casos["Nivel_Riesgo"] = casos.apply(riesgo_cliente, axis=1)

    # ── MATRIZ DE ALERTAS ───────────────────────────────────────────────────
    matriz_alertas = pd.DataFrame({
        "Tipo de Alerta": [
            "Monto Alto (Absoluto)", "Acumulado Mensual",
            "Exceso sobre Perfil", "Frecuencia Alta",
            "Smurfing", "Pico Anómalo"
        ],
        "Cantidad": [
            int(df["Alerta_Absoluto"].sum()), int(df["Alerta_Acumulado"].sum()),
            int(df["Alerta_15"].sum()),       int(df["Alerta_Frecuencia"].sum()),
            int(df["Smurfing"].sum()),         int(df["Pico"].sum())
        ],
        "Nivel de Impacto": [
            "Alto", "Medio-Alto", "Medio", "Medio", "Alto", "Medio-Alto"
        ],
        "Descripción": [
            "Transacciones individuales que superan el umbral absoluto configurado",
            "El total mensual del cliente excede N veces su perfil de riesgo",
            "Monto ligeramente superior al perfil esperado del cliente",
            "El cliente realiza más transacciones de las permitidas en el período",
            "Se detectan transacciones múltiples en el mismo día (posible fragmentación)",
            "Monto > (promedio + N desviaciones estándar) del cliente"
        ],
        "Peso en Score": [
            cfg["peso_absoluto"], cfg["peso_acumulado"], cfg["peso_perfil"],
            cfg["peso_frecuencia"], cfg["peso_smurfing"], cfg["peso_pico"]
        ]
    })
    
    # Agregar info de PEP/CPE y Ubicación a la matriz si existen
    if pep_cpe_info["has_pep"] or pep_cpe_info["has_cpe"] or pep_cpe_info["ubicacion_riesgo_count"] > 0:
        pep_cpe_alertas = []
        if pep_cpe_info["has_pep"]:
            pep_cpe_alertas.append({
                "Tipo de Alerta": "Asociado PEP",
                "Cantidad": pep_cpe_info["pep_count"],
                "Nivel de Impacto": "Crítico",
                "Descripción": "Persona Expuesta Políticamente — Relaciones políticas de alto riesgo (GAFI)",
                "Peso en Score": cfg.get("peso_pep_cpe", 2)
            })
        if pep_cpe_info["has_cpe"]:
            pep_cpe_alertas.append({
                "Tipo de Alerta": "Asociado CPE",
                "Cantidad": pep_cpe_info["cpe_count"],
                "Nivel de Impacto": "Alto",
                "Descripción": "Contratista/Proveedor relacionado a proyectos gubernamentales",
                "Peso en Score": cfg.get("peso_pep_cpe", 2)
            })
        if pep_cpe_info["ubicacion_riesgo_count"] > 0:
            pep_cpe_alertas.append({
                "Tipo de Alerta": "Ubicación de Riesgo",
                "Cantidad": pep_cpe_info["ubicacion_riesgo_count"],
                "Nivel de Impacto": "Alto",
                "Descripción": "Transacción originada en zona fronteriza o de alto riesgo",
                "Peso en Score": cfg.get("peso_ubicacion", 2)
            })
        
        if pep_cpe_alertas:
            matriz_alertas = pd.concat([matriz_alertas, pd.DataFrame(pep_cpe_alertas)], ignore_index=True)

    return df, casos, matriz_alertas, pep_cpe_info
