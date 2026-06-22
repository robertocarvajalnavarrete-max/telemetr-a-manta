import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
from supabase import create_client, Client

# ===========================================================
# 1. CONFIGURACIÓN DE PLATAFORMA Y CONEXIÓN NUBE
# ===========================================================
st.set_page_config(
    page_title="Panel Centralizado - Proyecto Manta",
    page_icon="📈",
    layout="wide"
)

SUPABASE_URL = "https://pkpcbvobkgnrvqkpamun.supabase.co"
SUPABASE_KEY = "sb_publishable_8eE8fYlKG_Nl5864tYukKA_Cm9Fh2aV"

if 'supabase' not in st.session_state:
    st.session_state.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase = st.session_state.supabase


# ===========================================================
# 2. CONTROL DE ACCESO (SISTEMA DE AUTENTICACIÓN)
# ===========================================================
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align: center;'>Proyecto Manta - Control de Acceso</h2>", unsafe_allow_html=True)
    col_login_1, col_login_2, col_login_3 = st.columns([1, 2, 1])
    
    with col_login_2:
        with st.form("formulario_login"):
            usuario = st.text_input("Usuario de Red:", key="usuario_ingresado")
            clave = st.text_input("Contraseña Operador:", type="password", key="clave_ingresada")
            boton_ingresar = st.form_submit_button("Ingresar al Panel", use_container_width=True)
            
            if boton_ingresar:
                if usuario == "admin" and clave == "manta2026":
                    st.session_state.autenticado = True
                    st.success("Acceso concedido.")
                    time.sleep(0.4)
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas. Intente nuevamente.")
    st.stop()


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
        df_trabajo = df_trabajo[df_trabajo['created_at'] >= desde_fecha]
        
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
    # Valores base por defecto
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
        
        # Consumo Persistente del Ensayo (Desde el reset en la nube)
        if fecha_ultimo_reset is not None:
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
    """
    try:
        # Convertir estampa de tiempo a formato ISO string para la base de datos
        iso_timestamp = estampa_tiempo.isoformat()
        supabase.table("acumulados_nodos").update({
            "kwh_desde_reset": 0.0,
            "costo_desde_reset": 0.0,
            "ultimo_reset_at": iso_timestamp
        }).eq("nodo_id", nodo).execute()
    except Exception as e:
        st.error(f"Error crítico al guardar reset en Supabase: {e}")


def cargar_datos_telemetria(nodo):
    try:
        res = supabase.table("telemetria_mantas")\
            .select("*")\
            .eq("nodo_id", nodo)\
            .order("created_at", desc=True)\
            .limit(1000)\
            .execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
            
            try:
                df['created_at'] = df['created_at'].dt.tz_convert('America/Punta_Arenas')
            except Exception:
                df['created_at'] = df['created_at'].dt.tz_localize(None) - timedelta(hours=3)

            df = df.sort_values('created_at').reset_index(drop=True)
            return df
    except Exception as e:
        st.error(f"Error descargando datos de telemetría: {e}")
    return pd.DataFrame()


# ===========================================================
# 4. INTERFAZ DE USUARIO (DASHBOARD PRINCIPAL)
# ===========================================================
col_title, col_refresh = st.columns([4, 1])

with col_title:
    st.title("Panel de Monitoreo Centralizado Proyecto Manta")
    st.caption("Monitoreo térmico en tiempo real para nodos en terreno")

with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True) 
    if st.button("🔄 Actualizar Datos", use_container_width=True):
        st.toast("Telemetría recalculada con éxito.", icon="📥")
        time.sleep(0.3)
        st.rerun()

st.markdown("---")

# --- BARRA LATERAL DE CONTROL ---
with st.sidebar:
    st.header("Sesión Activa")
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.autenticado = False
        st.info("Sesión cerrada correctamente.")
        time.sleep(0.5)
        st.rerun()
    
    st.markdown("---")
    nodo = st.selectbox("Seleccionar Nodo a Monitorear:", ["pi_lab_manta"], index=0)
    
    st.markdown("---")
    st.header("Configuración de Banda Térmica")
    
    if 'sp_local' not in st.session_state:
        st.session_state.sp_local = 4.5
        
    try:
        res_sp = supabase.table("configuracion_nodos").select("setpoint_config").eq("nodo_id", nodo).execute()
        if res_sp.data:
            st.session_state.sp_local = float(res_sp.data[0]["setpoint_config"])
    except:
        pass

    nuevo_sp = st.slider(
        "Setpoint Objetivo Precision (°C):",
        min_value=3.0,
        max_value=6.0,
        value=st.session_state.sp_local,
        step=0.1
    )
    
    if nuevo_sp != st.session_state.sp_local:
        try:
            supabase.table("configuracion_nodos").update({"setpoint_config": nuevo_sp}).eq("nodo_id", nodo).execute()
            st.session_state.sp_local = nuevo_sp
            st.success(f"🎯 Setpoint actualizado a {nuevo_sp} °C")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Error al guardar setpoint: {e}")

# --- DESPLIEGUE DE MÉTRICAS PRINCIPALES ---
if nodo:
    df_cronologico = cargar_datos_telemetria(nodo)
    
    if not df_cronologico.empty:
        ultimas_lecturas = df_cronologico.iloc[-1] 
        pwm_promedio = df_cronologico['duty_cycle'].mean() if 'duty_cycle' in df_cronologico.columns else df_cronologico['duty_cycle_mean'].mean()
        current_pwm = int(ultimas_lecturas.get('duty_cycle', 0))
        
        # Recuperar la información histórica y de reset persistente desde Supabase
        datos_acumulados = obtener_acumulados_y_metadata(nodo, df_cronologico)

        # --- FILA 1: VARIABLES TÉRMICAS ---
        st.subheader("Monitoreo de Variables Térmicas")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(label="Estado del Nodo", value="🟢 ONLINE")
        with col2:
            st.metric(label="Temp. Agua", value=f"{ultimas_lecturas['temp_agua']} °C")
        with col3:
            st.metric(label="Temp. Ambiente", value=f"{ultimas_lecturas['temp_ambiente']} °C")
        with col4:
            st.metric(label="Setpoint Objetivo", value=f"{st.session_state.sp_local} °C")

        st.markdown("---")

        # --- FILA 2: VARIABLES ENERGÉTIAS CON RESET REAL ---
        st.subheader("Eficiencia y Consumo Eléctrico")
        cole1, col_ens1, col_ens2, cole4 = st.columns(4)
        with cole1:
            st.metric(label="Salida MOSFET Actual", value=f"{current_pwm} %")
        with col_ens1:
            st.metric(label="Consumo Ensayo Actual", value=f"{datos_acumulados['kwh_desde_reset']:.5f} kWh")
        with col_ens2:
            st.metric(label="Costo Ensayo Actual", value=f"${datos_acumulados['costo_desde_reset']:.2f} CLP")
        with cole4:
            st.metric(label="Carga Promedio de la Manta", value=f"{pwm_promedio:.1f} %")

        # --- FILA 2.5: PIE DE PÁGINA METADATA GLOBAL ---
        col_hist1, col_hist2, col_btn = st.columns([2, 2, 1])
        with col_hist1:
            st.caption(f"🌍 **Acumulado Histórico Total del Nodo:** {datos_acumulados['kwh_historico_total']:.5f} kWh")
        with col_hist2:
            if datos_acumulados['ultimo_reset_at']:
                st.caption(f"⏱️ **Último reinicio de ensayo:** {datos_acumulados['ultimo_reset_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.caption("⏱️ **Último reinicio de ensayo:** Sin registros previos")
        with col_btn:
            if st.button("⚠️ Resetear Cuenta Ensayo", use_container_width=True):
                # 1. Obtener el punto en el tiempo del último registro de telemetría disponible
                instante_corte = df_cronologico['created_at'].max()
                # 2. Impactar de forma persistente en Supabase la fecha del reset
                ejecutar_reset_nube(nodo, instante_corte)
                st.toast("Hito de reset guardado de manera permanente en la nube.", icon="🔄")
                time.sleep(0.6)
                st.rerun()

        st.markdown("---")

        # --- FILA 3: GRÁFICO DE TENDENCIAS EN TIEMPO REAL ---
        st.subheader(f"📈 Curva Térmica e Historial PWM - {nodo} (Últimas 24 Horas)")
        
        ultima_estampa = df_cronologico['created_at'].max()
        limite_hace_24_horas = ultima_estampa - timedelta(hours=24)
        df_ventana_grafico = df_cronologico[df_cronologico['created_at'] >= limite_hace_24_horas].copy()
        
        df_ventana_grafico['created_at_visual'] = df_ventana_grafico['created_at'].dt.tz_localize(None)
        df_ventana_grafico['minuto'] = df_ventana_grafico['created_at_visual'].dt.floor('min')
        df_grafico_render = df_ventana_grafico.groupby('minuto').mean(numeric_only=True).reset_index()

        st.line_chart(
            data=df_grafico_render,
            x='minuto',
            y=['setpoint', 'temp_agua', 'temp_ambiente'],
            color=["#0055ff", "#ff7700", "#00aa00"]
        )

        st.markdown("---")

        # --- FILA 4: REGISTRO RECIENTE ---
        st.subheader("📋 Registro de Datos Recientes (Telemetría Histórica)")
        df_tabla_visible = df_cronologico.sort_values('created_at', ascending=False).copy()
        df_tabla_visible['created_at'] = df_tabla_visible['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        columnas_ordenadas = ['created_at', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle', 'nodo_id']
        df_tabla_visible = df_tabla_visible[[col for col in columnas_ordenadas if col in df_tabla_visible.columns]]
        st.dataframe(df_tabla_visible, use_container_width=True, hide_index=True)

        # --- FILA 5: EXPORTACIÓN ---
        st.subheader("Descarga de Datos")
        csv_data = df_tabla_visible.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Exportar Historial a CSV",
            data=csv_data,
            file_name=f"telemetria_{nodo}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("⚠️ No se encontraron registros de telemetría para este nodo.")
