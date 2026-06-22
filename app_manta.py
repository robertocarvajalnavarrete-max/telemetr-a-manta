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

# Inicializar cliente de la nube de forma segura
if 'supabase' not in st.session_state:
    st.session_state.supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
supabase = st.session_state.supabase


# ===========================================================
# 2. FUNCIONES AUXILIARES DE PERSISTENCIA
# ===========================================================
def obtener_acumulados(nodo):
    try:
        # Se fuerza el refresco evitando almacenamiento en caché local de Streamlit
        res = supabase.table("acumulados_nodos").select("*").eq("nodo_id", nodo).execute()
        if res.data:
            return res.data[0]
    except Exception as e:
        print(f"Error consultando acumulados: {e}")
    return {
        "kwh_historico_total": 0.0, 
        "costo_historico_total": 0.0, 
        "kwh_desde_reset": 0.0, 
        "costo_desde_reset": 0.0
    }

def ejecutar_reset_nube(nodo):
    try:
        supabase.table("acumulados_nodos").update({
            "kwh_desde_reset": 0.0,
            "costo_desde_reset": 0.0,
            "ultimo_reset_at": "now()"
        }).eq("nodo_id", nodo).execute()
    except Exception as e:
        print(f"Error ejecutando reset: {e}")


def cargar_datos_telemetria(nodo):
    try:
        # Eliminamos @st.cache_data para que la lectura de la última fila 
        # del MOSFET y consumo no se queden congeladas en cero
        res = supabase.table("telemetria_mantas")\
            .select("*")\
            .eq("nodo_id", nodo)\
            .order("created_at", desc=True)\
            .limit(1000)\
            .execute()
        
        if res.data:
            df = pd.DataFrame(res.data)
            df['created_at'] = pd.to_datetime(df['created_at'])
            return df
    except Exception as e:
        st.error(f"Error descargando datos: {e}")
    return pd.DataFrame()


# ===========================================================
# 3. INTERFAZ DE USUARIO (DASHBOARD PRINCIPAL)
# ===========================================================
st.title("Panel de Monitoreo Centralizado Proyecto Manta")
st.caption("Monitoreo térmico en tiempo real para nodos en terreno")
st.markdown("---")

# --- BARRA LATERAL DE CONTROL ---
with st.sidebar:
    st.header("Sesión Activa")
    if st.button("Cerrar Sesión"):
        st.info("Sesión finalizada.")
    
    st.markdown("---")
    nodo = st.selectbox(
        "Seleccionar Nodo a Monitorear:",
        ["pi_lab_manta"],
        index=0
    )
    
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
        "Setpoint Objetivo Precisión (°C):",
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
    df_telemetria = cargar_datos_telemetria(nodo)
    
    if not df_telemetria.empty:
        # Ordenamos una copia cronológicamente para cálculos y gráficos de líneas
        df_cronologico = df_telemetria.sort_values('created_at').reset_index(drop=True)
        
        # Cargar contadores persistentes en tiempo real
        datos_acumulados = obtener_acumulados(nodo)
        
        pwm_promedio = df_cronologico['duty_cycle'].mean()
        ultimas_lecturas = df_cronologico.iloc[-1] 
        current_pwm = int(ultimas_lecturas['duty_cycle'])

        # --- FILA 1: MÉTRICAS TÉRMICAS ---
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

        # --- FILA 2: MÉTRICAS ENERGÉTICAS PERSISTENTES ---
        st.subheader("Eficiencia y Consumo Eléctrico")
        cole1, cole2, cole3, cole4 = st.columns(4)
        with cole1:
            st.metric(label="Salida MOSFET Actual", value=f"{current_pwm} %")
        with cole2:
            st.metric(label="Consumo Ensayo Actual", value=f"{float(datos_acumulados['kwh_desde_reset']):.5f} kWh")
        with cole3:
            st.metric(label="Costo Ensayo Actual", value=f"${float(datos_acumulados['costo_desde_reset']):.2f} CLP")
        with cole4:
            st.metric(label="Carga Promedio de la Manta", value=f"{pwm_promedio:.1f} %")

        # --- FILA 2.5: SECCIÓN DE BORRADO E HISTÓRICO GLOBAL ---
        col_hist1, col_hist2, col_btn = st.columns([2, 2, 1])
        with col_hist1:
            st.caption(f"🌍 **Acumulado Histórico Total del Nodo:** {float(datos_acumulados['kwh_historico_total']):.5f} kWh")
        with col_hist2:
            st.caption(f"💰 **Costo Histórico Total:** ${float(datos_acumulados['costo_historico_total']):.2f} CLP")
        with col_btn:
            if st.button("⚠️ Resetear Cuenta Ensayo", use_container_width=True):
                ejecutar_reset_nube(nodo)
                st.toast("Contador de ensayo reiniciado con éxito.", icon="🔄")
                time.sleep(1)
                st.rerun()

        st.markdown("---")

        # --- FILA 3: GRÁFICO DE TENDENCIAS EN TIEMPO REAL ---
        st.subheader(f"📈 Curva Térmica e Historial PWM - {nodo} (Últimas 24 Horas)")
        
        ultima_estampa = df_cronologico['created_at'].max()
        limite_hace_24_horas = ultima_estampa - timedelta(hours=24)
        df_ventana_grafico = df_cronologico[df_cronologico['created_at'] >= limite_hace_24_horas].copy()
        
        # Remuestreo por minuto para suavizar líneas y optimizar memoria de la GPU web
        df_ventana_grafico['minuto'] = df_ventana_grafico['created_at'].dt.floor('min')
        df_grafico_render = df_ventana_grafico.groupby('minuto').mean(numeric_only=True).reset_index()

        st.line_chart(
            data=df_grafico_render,
            x='minuto',
            y=['setpoint', 'temp_agua', 'temp_ambiente'],
            color=["#0055ff", "#ff7700", "#00aa00"]
        )

        st.markdown("---")

        # --- FILA 4: TABLA DE VALORES HISTÓRICOS (REINCORPORADA) ---
        st.subheader("📋 Registro de Datos Recientes (Telemetría Histórica)")
        
        # Clonamos y formateamos el DataFrame original para una lectura tabular cómoda
        df_tabla_visible = df_telemetria.copy()
        df_tabla_visible['created_at'] = df_tabla_visible['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Reordenamos las columnas para destacar las variables principales
        columnas_ordenadas = ['created_at', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle', 'nodo_id']
        df_tabla_visible = df_tabla_visible[[col for col in columnas_ordenadas if col in df_tabla_visible.columns]]
        
        # Renderizado de la tabla interactiva de Streamlit
        st.dataframe(df_tabla_visible, use_container_width=True, hide_index=True)

        # --- FILA 5: EXPORTACIÓN DE HOJAS DE DATOS ---
        st.subheader("Descarga de Datos")
        csv_data = df_tabla_visible.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Exportar Historial a CSV",
            data=csv_data,
            file_name=f"telemetria_{nodo}_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv"
        )
    else:
        st.warning("⚠️ No se encontraron registros de telemetría para este nodo en la base de datos.")
