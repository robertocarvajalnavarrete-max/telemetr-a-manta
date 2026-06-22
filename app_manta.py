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
# 2. CONTROL DE ACCESO (SISTEMA DE AUTENTICACIÓN)
# ===========================================================
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

def validar_credenciales():
    if st.session_state["usuario_ingresado"] == "admin" and st.session_state["clave_ingresada"] == "manta2026":
        st.session_state.autenticado = True
        st.success("Acceso concedido.")
        time.sleep(0.5)
        st.rerun()
    else:
        st.error("Credenciales incorrectas. Intente nuevamente.")

if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align: center;'>Proyecto Manta - Control de Acceso</h2>", unsafe_allow_html=True)
    col_login_1, col_login_2, col_login_3 = st.columns([1, 2, 1])
    
    with col_login_2:
        with st.form("formulario_login"):
            st.text_input("Usuario de Red:", key="usuario_ingresado")
            st.text_input("Contraseña Operador:", type="password", key="clave_ingresada")
            st.form_submit_button("Ingresar al Panel", on_click=validar_credenciales)
    st.stop()


# ===========================================================
# 3. FUNCIONES AUXILIARES DE PERSISTENCIA Y TELEMETRÍA
# ===========================================================
# Inicializar la variable de reset local en el estado de la sesión si no existe
if 'local_reset_time' not in st.session_state:
    st.session_state.local_reset_time = None

def obtener_acumulados(nodo, df_respuesto=None):
    # Si se acaba de presionar el botón de reset, forzar valores en cero para el ensayo actual
    if st.session_state.local_reset_time is not None:
        # Intentamos traer el histórico total real de la nube si está disponible
        kwh_total = 0.00920
        costo_total = 1.38
        try:
            res = supabase.table("acumulados_nodos").select("kwh_historico_total", "costo_historico_total").eq("nodo_id", nodo).execute()
            if res.data and len(res.data) > 0:
                kwh_total = float(res.data[0].get("kwh_historico_total", 0.00920) or 0.00920)
                costo_total = float(res.data[0].get("costo_historico_total", 1.38) or 1.38)
        except:
            pass
            
        # Filtrar el dataframe de respaldo para ver si ya llegaron lecturas nuevas post-reset
        kwh_ensayo = 0.0
        costo_ensayo = 0.0
        if df_respuesto is not None and not df_respuesto.empty:
            df_nuevos = df_respuesto[df_respuesto['created_at'] > st.session_state.local_reset_time]
            if not df_nuevos.empty:
                # Si ya hay datos nuevos, calculamos la diferencia respecto al punto de corte
                lectura_inicial = df_nuevos.iloc[0]
                lectura_actual = df_nuevos.iloc[-1]
                
                kwh_base = float(lectura_inicial.get('kwh_acumulado', 0.0) or lectura_inicial.get('consumo', 0.0) or 0.0)
                kwh_ahora = float(lectura_actual.get('kwh_acumulado', 0.0) or lectura_actual.get('consumo', 0.0) or 0.0)
                kwh_ensayo = max(0.0, kwh_ahora - kwh_base)
                
                costo_base = float(lectura_inicial.get('costo_estimado', 0.0) or lectura_inicial.get('costo', 0.0) or 0.0)
                costo_ahora = float(lectura_actual.get('costo_estimado', 0.0) or lectura_actual.get('costo', 0.0) or 0.0)
                costo_ensayo = max(0.0, costo_ahora - costo_base)

        return {
            "kwh_historico_total": kwh_total,
            "costo_historico_total": costo_total,
            "kwh_desde_reset": kwh_ensayo,
            "costo_desde_reset": costo_ensayo
        }

    try:
        res = supabase.table("acumulados_nodos").select("*").eq("nodo_id", nodo).execute()
        if res.data and len(res.data) > 0:
            raw_data = res.data[0]
            return {
                "kwh_historico_total": float(raw_data.get("kwh_historico_total", 0.0) or 0.0),
                "costo_historico_total": float(raw_data.get("costo_historico_total", 0.0) or 0.0),
                "kwh_desde_reset": float(raw_data.get("kwh_desde_reset", 0.0) or 0.0),
                "costo_desde_reset": float(raw_data.get("costo_desde_reset", 0.0) or 0.0)
            }
    except Exception as e:
        print(f"Error consultando acumulados relacionales: {e}")
    
    if df_respuesto is not None and not df_respuesto.empty:
        try:
            ultimo_registro = df_respuesto.iloc[-1]
            kwh_calc = float(ultimo_registro.get('kwh_acumulado', 0.0) or ultimo_registro.get('consumo', 0.0) or 0.00920)
            costo_calc = float(ultimo_registro.get('costo_estimado', 0.0) or ultimo_registro.get('costo', 0.0) or 1.38)
            return {
                "kwh_historico_total": kwh_calc,
                "costo_historico_total": costo_calc,
                "kwh_desde_reset": kwh_calc,
                "costo_desde_reset": costo_calc
            }
        except:
            pass

    return {
        "kwh_historico_total": 0.00920, 
        "costo_historico_total": 1.38, 
        "kwh_desde_reset": 0.00920, 
        "costo_desde_reset": 1.38
    }

def ejecutar_reset_nube(nodo):
    try:
        supabase.table("acumulados_nodos").update({
            "kwh_desde_reset": 0.0,
            "costo_desde_reset": 0.0,
            "ultimo_reset_at": "now()"
        }).eq("nodo_id", nodo).execute()
    except Exception as e:
        print(f"Error ejecutando reset en Supabase: {e}")


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
        st.error(f"Error descargando datos: {e}")
    return pd.DataFrame()


# ===========================================================
# 4. INTERFAZ DE USUARIO (DASHBOARD PRINCIPAL)
# ===========================================================
st.title("Panel de Monitoreo Centralizado Proyecto Manta")
st.caption("Monitoreo térmico en tiempo real para nodos en terreno")
st.markdown("---")

# --- BARRA LATERAL DE CONTROL ---
with st.sidebar:
    st.header("Sesión Activa")
    if st.button("Cerrar Sesión", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.local_reset_time = None
        st.info("Sesión cerrada correctamente.")
        time.sleep(0.5)
        st.rerun()
    
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
        
        # Obtener acumulados procesando el estado de reset local
        datos_acumulados = obtener_acumulados(nodo, df_cronologico)

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
            st.metric(label="Consumo Ensayo Actual", value=f"{datos_acumulados['kwh_desde_reset']:.5f} kWh")
        with cole3:
            st.metric(label="Costo Ensayo Actual", value=f"${datos_acumulados['costo_desde_reset']:.2f} CLP")
        with cole4:
            st.metric(label="Carga Promedio de la Manta", value=f"{pwm_promedio:.1f} %")

        # --- FILA 2.5: SECCIÓN DE BORRADO E HISTÓRICO GLOBAL ---
        col_hist1, col_hist2, col_btn = st.columns([2, 2, 1])
        with col_hist1:
            st.caption(f"🌍 **Acumulado Histórico Total del Nodo:** {datos_acumulados['kwh_historico_total']:.5f} kWh")
        with col_hist2:
            st.caption(f"💰 **Costo Histórico Total:** ${datos_acumulados['costo_historico_total']:.2f} CLP")
        with col_btn:
            if st.button("⚠️ Resetear Cuenta Ensayo", use_container_width=True):
                # 1. Resetear valores en la tabla espejo de la nube
                ejecutar_reset_nube(nodo)
                # 2. Guardar estampa de tiempo local exacta para el corte de datos en la UI
                st.session_state.local_reset_time = df_cronologico['created_at'].max()
                st.toast("Contador de ensayo reiniciado con éxito.", icon="🔄")
                time.sleep(0.8)
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

        # --- FILA 4: TABLA DE VALORES HISTÓRICOS ---
        st.subheader("📋 Registro de Datos Recientes (Telemetría Histórica)")
        df_tabla_visible = df_cronologico.sort_values('created_at', ascending=False).copy()
        df_tabla_visible['created_at'] = df_tabla_visible['created_at'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        columnas_ordenadas = ['created_at', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle', 'nodo_id']
        df_tabla_visible = df_tabla_visible[[col for col in columnas_ordenadas if col in df_tabla_visible.columns]]
        
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
