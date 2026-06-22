import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import datetime, timedelta
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Control Manta - Centro de Ingeniería", layout="wide")
SUPABASE_URL = "https://pkpcbvobkgnrvqkpamun.supabase.co"
SUPABASE_KEY = "sb_publishable_8eE8fYlKG_Nl5864tYukKA_Cm9Fh2aV"
COSTO_KWH = 0.15 # Ajusta según tu tarifa en CLP
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

# --- LÓGICA PRINCIPAL ---
st.title("🛰️ Centro de Control - Proyecto Manta")

# 1. Autodescubrimiento de Nodos
nodos_raw = supabase.table("configuracion_nodos").select("nodo_id").execute()
nodos_lista = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Seleccionar Nodo:", nodos_lista)

# 2. Obtener datos y configs
datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).order("created_at", desc=True).limit(5000).execute()
df = pd.DataFrame(datos.data)
if not df.empty: df['created_at'] = pd.to_datetime(df['created_at'])

cfg = supabase.table("configuracion_nodos").select("*").eq("nodo_id", nodo_sel).single().execute().data

# 3. Panel de Control y Métricas
col1, col2, col3, col4 = st.columns(4)
col1.metric("Temp. Agua", f"{df.iloc[0]['temp_agua']}°C" if not df.empty else "N/A")
col2.metric("Temp. Amb.", f"{df.iloc[0]['temp_ambiente']}°C" if not df.empty else "N/A")
# Cálculo de salud
last_update = df.iloc[0]['created_at'] if not df.empty else datetime.now()
col3.metric("Última señal", f"Hace {int((datetime.now(last_update.tzinfo) - last_update).total_seconds()/60)} min")

# 4. Acciones de Ingeniería
with st.sidebar:
    st.subheader("Configuración")
    nuevo_sp = st.slider("Setpoint (°C)", 2.0, 8.0, float(cfg['setpoint']), 0.1)
    if st.button("Actualizar Setpoint"):
        supabase.table("configuracion_nodos").update({"setpoint": nuevo_sp}).eq("nodo_id", nodo_sel).execute()
        st.rerun()
        
    modo = st.radio("Modo Manual:", ["Auto", "ON", "OFF"], index=0 if cfg['modo_manual'] is None else (1 if cfg['modo_manual']=='ON' else 2))
    if st.button("Aplicar Modo"):
        val = None if modo == "Auto" else modo
        supabase.table("configuracion_nodos").update({"modo_manual": val}).eq("nodo_id", nodo_sel).execute()
        st.rerun()

# 5. Visualización y Datos
tab1, tab2 = st.tabs(["📊 Gráficos", "📋 Tabla Cruda"])
with tab1:
    st.line_chart(df.set_index('created_at')[['temp_agua', 'temp_ambiente']])
with tab2:
    st.dataframe(df, use_container_width=True)
    
    # Exportación Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")

if st.button("🔄 Refrescar"): st.rerun()
