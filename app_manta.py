import streamlit as st
import pandas as pd
from supabase import create_client
import io
from datetime import datetime, timedelta

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Control Manta - Centro de Ingeniería", layout="wide")
SUPABASE_URL = "https://pkpcbvobkgnrvqkpamun.supabase.co"
SUPABASE_KEY = "sb_publishable_8eE8fYlKG_Nl5864tYukKA_Cm9Fh2aV"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- LOGIN ---
if "autenticado" not in st.session_state: st.session_state.autenticado = False
if not st.session_state.autenticado:
    password = st.text_input("Clave de Acceso:", type="password")
    if st.button("Ingresar"):
        if password == "Manta2026!":
            st.session_state.autenticado = True
            st.rerun()
    st.stop()

# --- SIDEBAR: CONTROLES Y FILTROS ---
st.sidebar.header("⚙️ Configuración")
nodos_raw = supabase.table("configuracion_nodos").select("nodo_id").execute()
nodos_lista = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Seleccionar Nodo:", nodos_lista)

st.sidebar.header("📅 Rango de Consulta")
dias = st.sidebar.slider("Días hacia atrás:", 1, 30, 1)
fecha_inicio = datetime.now() - timedelta(days=dias)

# --- LÓGICA DE DATOS Y CORRECCIÓN HORARIA ---
datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).gte("created_at", fecha_inicio.isoformat()).execute()
df = pd.DataFrame(datos.data)

if not df.empty:
    # 1. Convertir a datetime y restar 3 horas (UTC-3 Punta Arenas)
    df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
    
    # 2. Crear una columna de hora como string para el gráfico (evita desfases del navegador)
    df['hora_str'] = df['created_at'].dt.strftime('%H:%M:%S')
    
    # 3. Establecer el índice para la tabla
    df = df.set_index('created_at')

# --- DASHBOARD ---
st.title(f"Centro de Control: {nodo_sel}")

if not df.empty:
    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df['temp_agua'].iloc[-1]}°C")
    c2.metric("Temp. Amb.", f"{df['temp_ambiente'].iloc[-1]}°C")
    
    cfg = supabase.table("configuracion_nodos").select("*").eq("nodo_id", nodo_sel).single().execute().data
    c3.metric("Setpoint", f"{cfg['setpoint']}°C")
    c4.metric("Potencia PID", f"{df['duty_cycle'].iloc[-1]}%")
    
    # Gráfico Corregido: Usamos 'hora_str' como índice para el eje X
    st.subheader("📊 Gráfico de Rendimiento")
    df_grafico = df.set_index('hora_str')[['temp_agua', 'temp_ambiente', 'setpoint']]
    st.line_chart(df_grafico)
else:
    st.warning("No hay datos disponibles para el nodo y rango seleccionados.")

# --- TABLA Y EXPORTACIÓN ---
if not df.empty:
    st.subheader("📋 Tabla de Telemetría")
    
    # Limpiar zona horaria para Excel (evita error ValueError)
    df_reporte = df.reset_index()
    if df_reporte['created_at'].dt.tz is not None:
        df_reporte['created_at'] = df_reporte['created_at'].dt.tz_localize(None)
    
    st.dataframe(df_reporte, use_container_width=True)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_reporte.to_excel(writer, index=False, sheet_name='Reporte')
    st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")

if st.button("🔄 Recargar"): st.rerun()
