import streamlit as st
import pandas as pd
import plotly.express as px
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

# --- SIDEBAR ---
st.sidebar.header("⚙️ Configuración")
nodos_raw = supabase.table("configuracion_nodos").select("*").execute()
nodo_nombres = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Nodo:", nodo_nombres)
cfg = next(n for n in nodos_raw.data if n['nodo_id'] == nodo_sel)

nuevo_sp = st.sidebar.number_input("Setpoint (°C):", value=float(cfg['setpoint']), step=0.1)
potencia_manta = st.sidebar.number_input("Potencia Manta (Watts):", value=500, step=50)
costo_kwh = st.sidebar.number_input("Costo CLP/kWh:", value=150.0, step=1.0)

if st.sidebar.button("Guardar Configuración"):
    supabase.table("configuracion_nodos").update({"setpoint": nuevo_sp}).eq("nodo_id", nodo_sel).execute()
    st.sidebar.success("Actualizado")
    st.rerun()

st.sidebar.header("📅 Rango de Consulta")
dias = st.sidebar.number_input("Días hacia atrás:", min_value=1, value=7)
fecha_inicio = datetime.now() - timedelta(days=dias)

# --- LÓGICA DE DATOS ---
datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).gte("created_at", fecha_inicio.isoformat()).execute()
df = pd.DataFrame(datos.data)

if not df.empty:
    df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
    df['consumo_kwh'] = (potencia_manta * (df['duty_cycle'].fillna(0)/100) * (10/3600)) / 1000
    df['costo_clp'] = df['consumo_kwh'] * costo_kwh
    df['hora_str'] = df['created_at'].dt.strftime('%d/%m %H:%M:%S')

# --- DASHBOARD ---
st.title(f"Centro de Control: {nodo_sel}")

if not df.empty:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df['temp_agua'].iloc[-1]}°C")
    c2.metric("Consumo Acumulado", f"{df['consumo_kwh'].sum():.2f} kWh")
    c3.metric("Costo Acumulado", f"${df['costo_clp'].sum():,.0f} CLP")
    c4.metric("Potencia PID", f"{df['duty_cycle'].iloc[-1]}%")
    
    st.subheader("📊 Gráfico de Rendimiento")
    
    # Preparación para Plotly
    df_melted = df.melt(id_vars=['hora_str'], value_vars=['temp_agua', 'temp_ambiente', 'setpoint'], 
                             var_name='Variable', value_name='Valor')
    
    fig = px.line(df_melted, x='hora_str', y='Valor', color='Variable')
    # Fijamos el eje Y de 0 a 10 para evitar distorsiones al hacer zoom
    fig.update_yaxes(range=[0, 10], autorange=False) 
    
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("📋 Tabla de Telemetría")
    st.dataframe(df.reset_index(drop=True), use_container_width=True)
else:
    st.warning("No hay registros disponibles.")

if st.button("🔄 Recargar"): st.rerun()
