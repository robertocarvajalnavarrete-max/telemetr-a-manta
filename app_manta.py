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
nodos_raw = supabase.table("configuracion_nodos").select("*").execute()
nodo_nombres = [n['nodo_id'] for n in nodos_raw.data]
nodo_sel = st.sidebar.selectbox("Nodo:", nodo_nombres)

# Obtener configuración actual
cfg = next(n for n in nodos_raw.data if n['nodo_id'] == nodo_sel)

# Controles de Parámetros
nuevo_sp = st.sidebar.number_input("Setpoint (°C):", value=float(cfg['setpoint']), step=0.1)
potencia_manta = st.sidebar.number_input("Potencia Manta (Watts):", value=500, step=50)
costo_kwh = st.sidebar.number_input("Costo CLP/kWh:", value=150.0, step=1.0)

if st.sidebar.button("Guardar Configuración"):
    supabase.table("configuracion_nodos").update({"setpoint": nuevo_sp}).eq("nodo_id", nodo_sel).execute()
    st.sidebar.success("Setpoint guardado")
    st.rerun()

st.sidebar.header("📅 Rango de Consulta")
dias = st.sidebar.number_input("Ver días hacia atrás:", min_value=1, max_value=365, value=7)
fecha_inicio = datetime.now() - timedelta(days=dias)

# --- LÓGICA DE DATOS ---
datos = supabase.table("telemetria_mantas").select("*").eq("nodo_id", nodo_sel).gte("created_at", fecha_inicio.isoformat()).execute()
df = pd.DataFrame(datos.data)

if not df.empty:
    # 1. Corrección Horaria (UTC-3 Punta Arenas)
    df['created_at'] = pd.to_datetime(df['created_at']) - timedelta(hours=3)
    
    # 2. Cálculo de consumo (kWh) y costo
    # Asumiendo muestreo de 10 segundos = 0.00277 horas
    df['consumo_kwh'] = (potencia_manta * (df['duty_cycle']/100) * (10/3600)) / 1000
    df['costo_clp'] = df['consumo_kwh'] * costo_kwh
    
    # 3. Índice para gráfico como string para evitar desfases
    df['hora_str'] = df['created_at'].dt.strftime('%d/%m %H:%M:%S')
    df_idx = df.set_index('created_at')

# --- DASHBOARD ---
st.title(f"Centro de Control: {nodo_sel}")

if not df.empty:
    # KPIs Superiores
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Temp. Agua", f"{df['temp_agua'].iloc[-1]}°C")
    c2.metric("Consumo Acumulado", f"{df['consumo_kwh'].sum():.2f} kWh")
    c3.metric("Costo Acumulado", f"${df['costo_clp'].sum():,.0f} CLP")
    c4.metric("Potencia PID", f"{df['duty_cycle'].iloc[-1]}%")
    
    # Gráfico
    st.subheader("📊 Gráfico de Rendimiento")
    st.line_chart(df.set_index('hora_str')[['temp_agua', 'temp_ambiente', 'setpoint']])
    
    # Tabla
    st.subheader("📋 Tabla de Telemetría")
    df_reporte = df.reset_index()
    if df_reporte['created_at'].dt.tz is not None:
        df_reporte['created_at'] = df_reporte['created_at'].dt.tz_localize(None)
    st.dataframe(df_reporte, use_container_width=True)
    
    # Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df_reporte.to_excel(writer, index=False, sheet_name='Reporte')
    st.download_button("📥 Descargar Excel", data=buffer, file_name=f"reporte_{nodo_sel}.xlsx")
else:
    st.warning("No hay registros en el rango seleccionado.")

if st.button("🔄 Recargar"): st.rerun()
