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

# --- SIDEBAR: CONFIGURACIÓN Y FILTROS ---
st.sidebar.header("⚙️ Configuración")
nodos_raw = supabase.table("configuracion_nodos").select("nodo_id").execute()
nodos_lista = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Seleccionar Nodo:", nodos_lista)

# Recuperar configuración actual
cfg = supabase.table("configuracion_nodos").select("*").eq("nodo_id", nodo_sel).single().execute().data

# Control Setpoint
nuevo_sp = st.sidebar.number_input("Ajustar Setpoint (°C):", min_value=0.0, max_value=20.0, value=float(cfg['setpoint']), step=0.1)
if st.sidebar.button("Guardar Setpoint"):
    supabase.table("configuracion_nodos").update({"setpoint": nuevo_sp}).eq("nodo_id", nodo_sel).execute()
    st.sidebar.success("Setpoint actualizado")
    st.rerun()

# Control de fechas
st.sidebar.header("📅 Rango de Consulta")
dias = st.sidebar.number_input("Ver días hacia atrás:", min_value=1, max_value=365, value=7)
fecha_inicio = datetime.now() - timedelta(days=dias)

# --- LÓGICA DE DATOS ---
datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).gte("created_at", fecha_inicio.isoformat()).execute()
df = pd.DataFrame(datos.data)

if not df.empty:
    # Corrección horaria Punta Arenas
    df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
    df['hora_str'] = df['created_at'].dt.strftime('%d/%m %H:%M:%S')
    df = df.set_index('created_at')

# --- DASHBOARD ---
st.title(f"Centro de Control: {nodo_sel}")

if not df.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df['temp_agua'].iloc[-1]}°C")
    c2.metric("Temp. Amb.", f"{df['temp_ambiente'].iloc[-1]}°C")
    c3.metric("Setpoint Act.", f"{cfg['setpoint']}°C")
    c4.metric("Potencia PID", f"{df['duty_cycle'].iloc[-1]}%")
    
    st.subheader("📊 Gráfico de Rendimiento")
    # El gráfico usa el índice 'hora_str' que es texto, evitando desfases temporales
    st.line_chart(df.set_index('hora_str')[['temp_agua', 'temp_ambiente', 'setpoint']])
else:
    st.warning("No hay datos en el rango seleccionado.")

# --- TABLA Y EXPORTACIÓN ---
if not df.empty:
    st.subheader("📋 Tabla de Telemetría")
    df_reporte = df.reset_index()
    if df_reporte['created_at'].dt.tz is not None:
        df_reporte['created_at'] = df_reporte['created_at'].dt.tz_localize(None)
    st.dataframe(df_reporte, use_container_width=True)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_reporte.to_excel(writer, index=False, sheet_name='Reporte')
    st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")

if st.button("🔄 Recargar"): st.rerun()
