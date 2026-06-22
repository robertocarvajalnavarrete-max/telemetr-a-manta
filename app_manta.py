import streamlit as st
import pandas as pd
from supabase import create_client
import io

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Control Manta", layout="wide")
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

# --- INTERFAZ ---
nodos_raw = supabase.table("configuracion_nodos").select("nodo_id").execute()
nodos_lista = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Seleccionar Nodo:", nodos_lista)

datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).order("created_at", desc=True).limit(5000).execute()
df = pd.DataFrame(datos.data)
if not df.empty: df['created_at'] = pd.to_datetime(df['created_at'])

# --- EXPORTACIÓN CORREGIDA ---
df_reporte = df.copy()
for col in df_reporte.select_dtypes(['datetimetz']).columns:
    df_reporte[col] = df_reporte[col].dt.tz_localize(None)

buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
    df_reporte.to_excel(writer, index=False, sheet_name='Reporte')

st.title(f"Centro de Control: {nodo_sel}")
tab1, tab2 = st.tabs(["📊 Gráficos", "📋 Tabla Cruda"])
with tab1:
    st.line_chart(df.set_index('created_at')[['temp_agua', 'duty_cycle']])
with tab2:
    st.dataframe(df_reporte, use_container_width=True)
    st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")
