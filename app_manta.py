import streamlit as st
import pandas as pd
from supabase import create_client
import io
from datetime import datetime

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

# --- LÓGICA DE DATOS ---
nodos_raw = supabase.table("configuracion_nodos").select("nodo_id").execute()
nodos_lista = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Seleccionar Nodo:", nodos_lista)

datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).order("created_at", desc=True).limit(500).execute()
df = pd.DataFrame(datos.data)
cfg = supabase.table("configuracion_nodos").select("*").eq("nodo_id", nodo_sel).single().execute().data

# --- LAYOUT SUPERIOR: KPIs ---
st.title(f"Centro de Control: {nodo_sel}")
if not df.empty:
    df['created_at'] = pd.to_datetime(df['created_at'])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df.iloc[0]['temp_agua']} °C")
    c2.metric("Setpoint", f"{cfg['setpoint']} °C")
    c3.metric("Potencia PID", f"{df.iloc[0]['duty_cycle']} %")
    c4.metric("Estado Manta", "Manual" if cfg['modo_manual'] else "Auto")

# --- SIDEBAR: CONTROLES ---
with st.sidebar:
    st.header("⚙️ Configuración")
    nuevo_sp = st.slider("Ajustar Setpoint (°C)", 2.0, 10.0, float(cfg['setpoint']), 0.5)
    if st.button("Actualizar Setpoint"):
        supabase.table("configuracion_nodos").update({"setpoint": nuevo_sp}).eq("nodo_id", nodo_sel).execute()
        st.rerun()
    
    st.divider()
    modo = st.radio("Modo Manual:", ["Auto", "ON", "OFF"], index=0 if cfg['modo_manual'] is None else (1 if cfg['modo_manual']=='ON' else 2))
    if st.button("Aplicar Modo"):
        val = None if modo == "Auto" else modo
        supabase.table("configuracion_nodos").update({"modo_manual": val}).eq("nodo_id", nodo_sel).execute()
        st.rerun()

# --- CUERPO: GRÁFICOS Y DATOS ---
tab1, tab2 = st.tabs(["📊 Gráfico de Rendimiento", "📋 Tabla de Telemetría"])
with tab1:
    if not df.empty:
        st.line_chart(df.set_index('created_at')[['temp_agua', 'duty_cycle']])
    else:
        st.warning("No hay datos suficientes para graficar.")

with tab2:
    if not df.empty:
        df_reporte = df.copy()
        for col in df_reporte.select_dtypes(['datetimetz']).columns:
            df_reporte[col] = df_reporte[col].dt.tz_localize(None)
        st.dataframe(df_reporte, use_container_width=True)
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            df_reporte.to_excel(writer, index=False, sheet_name='Reporte')
        st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")
    else:
        st.info("Sin registros en la base de datos.")

if st.button("🔄 Recargar"): st.rerun()
