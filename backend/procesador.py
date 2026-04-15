import pandas as pd

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

def procesar_transacciones(df, cfg):
    """
    Aplica las reglas de negocio AML al DataFrame de transacciones.
    Retorna: (df_procesado, casos, matriz_alertas, info_pep_cpe)
    
    info_pep_cpe contiene: {"has_pep": bool, "has_cpe": bool, "pep_count": int, "cpe_count": int}
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
    if pep_cpe_info["has_pep"] or pep_cpe_info["has_cpe"]: # CPE logic
        if pep_cpe_info["has_cpe"]:
            cpe_col = pep_cpe_info["cpe_col"]
            df["EsCPE"] = df[cpe_col].apply(_convertir_a_bool)
        else:
            df["EsCPE"] = False
    else:
        df["EsCPE"] = False
    
    # --- Regla: Ubicación de Riesgo ---
    df["Ubicacion_Riesgo"] = False
    
    if cfg.get("regla_ubicacion", True):
        # 1. Prioridad: Columna específica en el Excel 'UbicacionRiesgo'
        if "UbicacionRiesgo" in df.columns:
            df["Ubicacion_Riesgo"] = df["UbicacionRiesgo"].apply(_convertir_a_bool)
        
        # 2. Complemento: Lista de gestión manual de la plataforma
        manual_list = [str(loc).lower() for loc in cfg.get("ubicaciones_manuales", [])]
        if manual_list and "Ubicacion" in df.columns:
            manual_risk = df["Ubicacion"].astype(str).str.lower().isin(manual_list)
            df["Ubicacion_Riesgo"] = df["Ubicacion_Riesgo"] | manual_risk



    # Contadores para estadísticas
    pep_cpe_info["pep_count"] = int(df["EsPEP"].sum())
    pep_cpe_info["cpe_count"] = int(df["EsCPE"].sum())
    pep_cpe_info["asociados_riesgo"] = pep_cpe_info["pep_count"] + pep_cpe_info["cpe_count"]
    pep_cpe_info["ubicacion_riesgo_count"] = int(df["Ubicacion_Riesgo"].sum())

    # --- Reglas (controladas por cfg) ---
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

    # --- Score base (reglas AML) ---
    score_base = (
        df["Alerta_15"].astype(int)       * cfg["peso_perfil"]     +
        df["Alerta_Absoluto"].astype(int) * cfg["peso_absoluto"]   +
        df["Alerta_Acumulado"].astype(int)* cfg["peso_acumulado"]  +
        df["Alerta_Frecuencia"].astype(int)*cfg["peso_frecuencia"] +
        df["Smurfing"].astype(int)        * cfg["peso_smurfing"]   +
        df["Pico"].astype(int)            * cfg["peso_pico"]
    )
    
    # --- Score adicional por PEP/CPE y Ubicación ---
    peso_pep_cpe = cfg.get("peso_pep_cpe", 1)
    peso_ubicacion = cfg.get("peso_ubicacion", 2)
    
    score_extra = (
        (df["EsPEP"].astype(int) + df["EsCPE"].astype(int)) * peso_pep_cpe +
        df["Ubicacion_Riesgo"].astype(int) * peso_ubicacion
    )
    
    # Score total = score_base + score_extra
    df["Score"] = score_base + score_extra

    casos = df.groupby("Cliente").agg({
        "Monto": "sum",
        "Score": "max",
        "Transacciones": "max",
        "EsPEP": "max",
        "EsCPE": "max",
        "Ubicacion_Riesgo": "max"
    }).reset_index()
    casos.columns = ["Cliente", "Total_Mensual", "Score_Max", "Transacciones", "EsPEP", "EsCPE", "Ubicacion_Riesgo"]

    def riesgo_cliente(row):
        if row["Score_Max"] >= cfg["score_critico"] or row["Total_Mensual"] > cfg["monto_critico"]:
            return "Crítico"
        elif row["Score_Max"] >= cfg["score_alto"]:
            return "Alto"
        elif row["Score_Max"] >= cfg["score_medio"]:
            return "Medio"
        return "Bajo"

    casos["Nivel_Riesgo"] = casos.apply(riesgo_cliente, axis=1)

    matriz_alertas = pd.DataFrame({
        "Tipo de Alerta": [
            "Monto Alto (Absoluto)", "Acumulado Mensual",
            "Exceso sobre Perfil", "Frecuencia Alta",
            "Smurfing", "Pico Anómalo"
        ],
        "Cantidad": [
            int(df["Alerta_Absoluto"].sum()), int(df["Alerta_Acumulado"].sum()),
            int(df["Alerta_15"].sum()), int(df["Alerta_Frecuencia"].sum()),
            int(df["Smurfing"].sum()), int(df["Pico"].sum())
        ],
        "Nivel de Impacto": [
            "Alto", "Medio-Alto", "Medio", "Medio", "Alto", "Medio-Alto"
        ],
        "Descripción": [
            "Transacciones individuales que superan el umbral absoluto configurado",
            "El total mensual del cliente excede N veces su perfil de riesgo",
            "Monto ligeramente superior al perfil esperado del cliente",
            "El cliente realiza más de 5 operaciones en el período analizado",
            "Se detectan ≥5 transacciones el mismo día (posible fragmentación)",
            "Monto > (promedio + 2 desviaciones estándar) del cliente"
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
                "Nivel de Impacto": "Alto",
                "Descripción": "Persona Expuesta Políticamente - Relaciones políticas de alto riesgo",
                "Peso en Score": peso_pep_cpe
            })
        if pep_cpe_info["has_cpe"]:
            pep_cpe_alertas.append({
                "Tipo de Alerta": "Asociado CPE",
                "Cantidad": pep_cpe_info["cpe_count"],
                "Nivel de Impacto": "Alto",
                "Descripción": "Contratista/Proveedor relacionado a proyectos gubernamentales",
                "Peso en Score": peso_pep_cpe
            })
        if pep_cpe_info["ubicacion_riesgo_count"] > 0:
            pep_cpe_alertas.append({
                "Tipo de Alerta": "Ubicación de Riesgo",
                "Cantidad": pep_cpe_info["ubicacion_riesgo_count"],
                "Nivel de Impacto": "Alto",
                "Descripción": "Transacción originada en zona fronteriza o de alto riesgo",
                "Peso en Score": peso_ubicacion
            })
        
        if pep_cpe_alertas:
            matriz_alertas = pd.concat([matriz_alertas, pd.DataFrame(pep_cpe_alertas)], ignore_index=True)

    return df, casos, matriz_alertas, pep_cpe_info
