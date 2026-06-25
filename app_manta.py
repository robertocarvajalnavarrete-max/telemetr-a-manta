import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client
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

potencia_manta = st.sidebar.number_input("Potencia Manta (Watts):", value=13, step=50)
costo_kwh = st.sidebar.number_input("Costo CLP/kWh:", value=120.0, step=1.0)

st.sidebar.header("📅 Rango de Consulta")
dias = st.sidebar.number_input("Días hacia atrás:", min_value=1, value=7)
fecha_inicio = datetime.now() - timedelta(days=dias)

# --- LÓGICA DE DATOS ---
datos = supabase.table("telemetria_mantas")\
    .select("*")\
    .eq("nodo_id", nodo_sel)\
    .gte("created_at", fecha_inicio.isoformat())\
    .order("created_at", desc=True)\
    .limit(5000)\
    .execute()

df = pd.DataFrame(datos.data)

if not df.empty:
    df = df.sort_values('created_at', ascending=True)
    
    # 1. Conversión exacta a zona horaria de Magallanes
    df['created_at'] = pd.to_datetime(df['created_at'], utc=True).dt.tz_convert('America/Punta_Arenas')
    
    # 2. Creamos una columna legible para mostrar (sin zona horaria)
    df['hora formateada'] = df['created_at'].dt.strftime('%d/%m %H:%M:%S')
    
    df['consumo_kwh'] = (potencia_manta * (df['duty_cycle'].fillna(0)/100) * (10/3600)) / 1000
    df['costo_clp'] = df['consumo_kwh'] * costo_kwh

# --- DASHBOARD ---
st.title(f"Centro de Control: {nodo_sel}")

if not df.empty:
    # Indicador de flujo
    es_flujo = df['flujo_detectado'].iloc[-1]
    if es_flujo:
        st.warning("⚠️ ¡Flujo de agua detectado! Manta en reposo.")
    else:
        st.success("✅ Sin flujo de agua. Control térmico activo.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df['temp_agua'].iloc[-1]:.1f}°C")
    c2.metric("Consumo Acumulado", f"{df['consumo_kwh'].sum():.2f} kWh")
    c3.metric("Costo Acumulado", f"${df['costo_clp'].sum():,.0f} CLP")
    c4.metric("Potencia PWM", f"{df['duty_cycle'].iloc[-1]}%")
    
    st.subheader("📊 Gráfico de Rendimiento")
    # Usamos 'hora_formateada' en el gráfico para asegurar la visualización horaria correcta
    df_melted = df.melt(id_vars=['hora_formateada'], value_vars=['temp_agua', 'temp_ambiente', 'setpoint'], 
                        var_name='Variable', value_name='Valor')
    fig = px.line(df_melted, x='hora_formateada', y='Valor', color='Variable')
    fig.update_yaxes(autorange=True) 
    st.plotly_chart(fig, use_container_width=True)
    
    st.subheader("📋 Tabla de Telemetría")
    # Mostramos la columna creada para la hora
    columnas_ordenadas = ['hora_formateada', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle', 'flujo_detectado', 'consumo_kwh']
    st.dataframe(df.sort_values('created_at', ascending=False)[columnas_ordenadas], use_container_width=True)
else:
    st.warning("No hay registros. Verifica el script de la Raspberry.")

if st.button("🔄 Recargar"): st.rerun()
