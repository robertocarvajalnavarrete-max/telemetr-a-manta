# ===========================================================
# 3. FUNCIONES AUXILIARES DE PERSISTENCIA Y TELEMETRÍA
# ===========================================================
def calcular_consumo_dinamico(df_datos, desde_fecha=None):
    """
    Calcula el consumo eléctrico acumulado integrando los puntos de telemetría.
    Si se pasa 'desde_fecha', solo acumula los registros posteriores a ese hito.
    """
    if df_datos.empty:
        return 0.0, 0.0
        
    df_trabajo = df_datos.copy()
    
    # Filtrar cronológicamente si existe un reset registrado
    if desde_fecha is not None:
        # Asegurar compatibilidad de zonas horarias (Mismo timezone que los datos)
        if df_trabajo['created_at'].dt.tz is not None and desde_fecha.tzinfo is None:
            desde_fecha = desde_fecha.replace(tzinfo=df_trabajo['created_at'].dt.tz)
        
        # Aplicamos el filtro estricto posterior al hito de reset
        df_trabajo = df_trabajo[df_trabajo['created_at'] > desde_fecha]
        
    # Si no hay suficientes puntos tras el reset, el consumo del ensayo es legítimamente 0
    if df_trabajo.shape[0] < 2:
        return 0.0, 0.0
        
    df_trabajo = df_trabajo.sort_values('created_at')
    
    POTENCIA_MANTA_KW = 0.060  # 60 Watts nominales
    COSTO_KWH_CLP = 150.0      # Costo promedio energía
    
    kwh_acumulado = 0.0
    
    for i in range(1, len(df_trabajo)):
        t1 = df_trabajo.iloc[i-1]['created_at']
        t2 = df_trabajo.iloc[i]['created_at']
        delta_horas = (t2 - t1).total_seconds() / 3600.0
        
        # Ignorar vacíos temporales huérfanos por desconexión
        if delta_horas > 0.16:
            delta_horas = 0.016  
            
        pwm = float(df_trabajo.iloc[i]['duty_cycle'] or 0.0) / 100.0
        kwh_acumulado += (POTENCIA_MANTA_KW * pwm) * delta_horas
        
    costo_clp = kwh_acumulado * COSTO_KWH_CLP
    return kwh_acumulado, costo_clp


def obtener_acumulados_y_metadata(nodo, df_telemetria):
    """
    Consulta la metadata del nodo en Supabase para obtener la fecha del último reset
    y calcula de forma robusta los consumos absolutos y del ensayo actual.
    """
    kwh_total, costo_total = 0.0, 0.0
    kwh_ensayo, costo_ensayo = 0.0, 0.0
    fecha_ultimo_reset = None

    # 1. Obtener la estampa de tiempo del último reset real guardado en la nube
    try:
        res = supabase.table("acumulados_nodos").select("ultimo_reset_at").eq("nodo_id", nodo).execute()
        if res.data and len(res.data) > 0:
            raw_reset = res.data[0].get("ultimo_reset_at")
            if raw_reset:
                fecha_ultimo_reset = pd.to_datetime(raw_reset)
    except Exception as e:
        print(f"Error al recuperar fecha de reset: {e}")

    # 2. Calcular consumos basados en el dataframe de telemetría cargado
    if not df_telemetria.empty:
        # Consumo Histórico Completo
        kwh_total, costo_total = calcular_consumo_dinamico(df_telemetria)
        
        # Consumo Persistente del Ensayo
        if fecha_ultimo_reset is not None:
            # Forzar limpieza inmediata si el reset es igual o posterior al último dato descargado
            ultimo_dato_time = df_telemetria['created_at'].max()
            if fecha_ultimo_reset >= ultimo_dato_time:
                kwh_ensayo, costo_ensayo = 0.0, 0.0
            else:
                kwh_ensayo, costo_ensayo = calcular_consumo_dinamico(df_telemetria, desde_fecha=fecha_ultimo_reset)
        else:
            kwh_ensayo, costo_ensayo = kwh_total, costo_total

    return {
        "kwh_historico_total": kwh_total,
        "costo_historico_total": costo_total,
        "kwh_desde_reset": kwh_ensayo,
        "costo_desde_reset": costo_ensayo,
        "ultimo_reset_at": fecha_ultimo_reset
    }


def ejecutar_reset_nube(nodo, estampa_tiempo):
    """
    Guarda de manera definitiva el instante exacto del reset en la base de datos relacional.
    Adiciona un segundo de holgura para evitar solapamientos con el registro actual.
    """
    try:
        # Añadir una holgura de 1 segundo para asegurar que el filtro excluya el bloque histórico anterior
        estampa_con_holgura = estampa_tiempo + timedelta(seconds=1)
        iso_timestamp = estampa_con_holgura.isoformat()
        
        supabase.table("acumulados_nodos").update({
            "kwh_desde_reset": 0.0,
            "costo_desde_reset": 0.0,
            "ultimo_reset_at": iso_timestamp
        }).eq("nodo_id", nodo).execute()
    except Exception as e:
        st.error(f"Error crítico al guardar reset en Supabase: {e}")
