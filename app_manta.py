import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, timedelta
import io
import plotly.graph_objects as go

st.set_page_config(page_title="Telemetría Mantas Calefactoras", layout="wide")

# ==========================================
#  CONTROL DE ACCESOS (SISTEMA DE SEGURIDAD)
# ==========================================
CONTRASENA_CORRECTA = "Manta2026!" 

def verificar_password():
    """Devuelve True si el usuario ingresó la credencial correcta."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    if st.session_state.autenticado:
        return True

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("https://cdn-icons-png.flaticon.com/512/3064/3064155.png", width=80)
        st.title("🔒 Acceso Restringido")
        st.subheader("Proyecto Manta - Panel de Telemetría")
        
        password_ingresada = st.text_input("Introduce la clave de acceso para continuar:", type="password")
        
        if st.button("Ingresar al Sistema", use_container_width=True):
            if password_ingresada == CONTRASENA_CORRECTA:
                st.session_state.autenticado = True
                st.success("🔑 Acceso concedido con éxito.")
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")
                
    return False

if verificar_password():

    # ==========================================
    #  CÓDIGO DE LA APLICACIÓN (SÓLO SI ESTÁ LOGUEADO)
    # ==========================================
    SUPABASE_URL = "https://pkpcbvobkgnrvqkpamun.supabase.co"
    SUPABASE_KEY = "sb_publishable_8eE8fYlKG_Nl5864tYukKA_Cm9Fh2aV"

    @st.cache_resource
    def init_connection():
        return create_client(SUPABASE_URL, SUPABASE_KEY)

    supabase = init_connection()

    st.sidebar.title("Sesión Activa")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("Panel de Monitoreo Centralizado Proyecto Manta")
    st.subheader("Monitoreo térmico en tiempo real para nodos en terreno")

    # --- FUNCIONES DE BASE DE DATOS ---
    def obtener_setpoint_nube(nodo):
        try:
            res = supabase.table("configuracion_nodos").select("limite_minimo").eq("nodo_id", nodo).execute()
            if res.data:
                return float(res.data[0]["limite_minimo"])
        except Exception as e:
            st.sidebar.error(f"Error de conexión al obtener setpoint: {e}")
        return 4.5

    def actualizar_setpoint_nube(nodo, nuevo_sp):
        try:
            supabase.table("configuracion_nodos").update({
                "limite_minimo": nuevo_sp, 
                "updated_at": "now()"
            }).eq("nodo_id", nodo).execute()
        except Exception as e:
            st.sidebar.error(f"No se pudo actualizar la nube: {e}")

    @st.cache_data(ttl=60, show_spinner=False)
    def cargar_datos():
        try:
            respuesta = supabase.table("telemetria_mantas").select("*").order("created_at", desc=True).limit(1000).execute()
            df = pd.DataFrame(respuesta.data)
            if not df.empty:
                df['created_at'] = pd.to_datetime(df['created_at'])
            return df
        except Exception as e:
            st.error(f"Error al traer datos de telemetría: {e}")
            return pd.DataFrame()

    df_inicial = cargar_datos()

    if df_inicial.empty:
        st.warning("Esperando conexión o datos iniciales desde la tabla de Supabase...")
    else:
        nodos_disponibles = df_inicial['nodo_id'].unique()
        nodo_seleccionado = st.sidebar.selectbox("Seleccionar Nodo a Monitorear:", nodos_disponibles)
        
        # Inicialización controlada
        if "nodo_actual" not in st.session_state or st.session_state.nodo_actual != nodo_seleccionado:
            st.session_state.nodo_actual = nodo_seleccionado
            st.session_state.sp_local = obtener_setpoint_nube(nodo_seleccionado)
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("Configuración de Banda Térmica")
        
        nuevo_sp = st.sidebar.slider(
            "Setpoint Objetivo Precision (°C):", 
            min_value=3.0, 
            max_value=6.0, 
            value=st.session_state.sp_local, 
            step=0.1
        )
        
        # --- IF DE DETECCIÓN DE CAMBIO (SIMULA EL REFRESH AUTOMÁTICAMENTE) ---
        if nuevo_sp != st.session_state.sp_local:
            actualizar_setpoint_nube(nodo_seleccionado, nuevo_sp)
            st.session_state.sp_local = nuevo_sp  # Forzamos el valor en memoria local inmediatamente
            cargar_datos.clear()                  # Limpiamos el caché de la telemetría por completo
            st.rerun()                            # Ejecutamos el refresh nativo por software

        @st.fragment(run_every=60)
        def renderizar_datos_dinamicos(nodo):
            df_dinamico = cargar_datos()
            df_filtrado = df_dinamico[df_dinamico['nodo_id'] == nodo].copy()
            
            if not df_filtrado.empty:
                if df_filtrado['created_at'].dt.tz is not None:
                    df_filtrado['created_at'] = df_filtrado['created_at'].dt.tz_convert('America/Punta_Arenas').dt.tz_localize(None)
                else:
                    df_filtrado['created_at'] = df_filtrado['created_at'].dt.tz_localize(None)

                # Rellenar nulos en duty_cycle por si existen registros antiguos sin la columna
                if 'duty_cycle' in df_filtrado.columns:
                    df_filtrado['duty_cycle'] = df_filtrado['duty_cycle'].fillna(0).astype(float)
                else:
                    df_filtrado['duty_cycle'] = 0.0

                # --- ORDEN CRONOLÓGICO BASE PARA INTEGRACIÓN NUMÉRICA ---
                df_cronologico_base = df_filtrado.sort_values('created_at', ascending=True).reset_index(drop=True)

                # ==========================================
                #  ALGORITMO DE CONSUMO ENERGÉTICO (PWM)
                # ==========================================
                # Parámetros físicos suministrados: 12V * 1.068A = 12.816 Watts
                POTENCIA_MANTA_W = 12.0 * 1.068 
                COSTO_KWH_MAGALLANES = 150.0  # Valor promedio de referencia CLP por kWh

                # Delta de tiempo en horas entre registros consecutivos
                df_cronologico_base['dt_horas'] = df_cronologico_base['created_at'].diff().dt.total_seconds() / 3600.0
                df_cronologico_base['dt_horas'] = df_cronologico_base['dt_horas'].fillna(0.0)

                # Energía consumida en el intervalo (Wh) transformada a kWh
                # Fórmula: (Watts * Fracción_PWM * Horas) / 1000
                df_cronologico_base['kwh_intervalo'] = (POTENCIA_MANTA_W * (df_cronologico_base['duty_cycle'] / 100.0) * df_cronologico_base['dt_horas']) / 1000.0
                
                consumo_total_kwh = df_cronologico_base['kwh_intervalo'].sum()
                costo_estimado = consumo_total_kwh * COSTO_KWH_MAGALLANES
                pwm_promedio = df_cronologico_base['duty_cycle'].mean()

                # --- MUESTREO PARA GRÁFICOS (1 MINUTO + CAMBIOS INSTANTÁNEOS) ---
                df_cronologico_base['minuto_floor'] = df_cronologico_base['created_at'].dt.floor('min')
                df_1min = df_cronologico_base.drop_duplicates(subset=['minuto_floor'], keep='last')

                mask_cambio_sp = df_cronologico_base['setpoint'] != df_cronologico_base['setpoint'].shift(1)
                df_cambios_sp = df_cronologico_base[mask_cambio_sp]

                df_procesado_cronologico = pd.concat([df_1min, df_cambios_sp]).drop_duplicates(subset=['id']).sort_values('created_at', ascending=True)
                df_procesado_cronologico = df_procesado_cronologico.drop(columns=['minuto_floor'])

                ultimas_lecturas = df_cronologico_base.iloc[-1] 
                current_pwm = int(ultimas_lecturas['duty_cycle'])

                # --- FILA 1: MÉTRICAS TÉRMICAS ---
                st.subheader("🌡️ Monitoreo de Variables Térmicas")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(label="Estado del Nodo", value="🟢 ONLINE")
                with col2:
                    st.metric(label="Temp. Agua", value=f"{ultimas_lecturas['temp_agua']} °C")
                with col3:
                    st.metric(label="Temp. Ambiente", value=f"{ultimas_lecturas['temp_ambiente']} °C")
                with col4:
                    st.metric(label="Setpoint Objetivo", value=f"{st.session_state.sp_local} °C")

                # --- FILA 2: MÉTRICAS ENERGÉTICAS (NUEVA) ---
                st.subheader("⚡ Eficiencia y Consumo Eléctrico")
                cole1, cole2, cole3, cole4 = st.columns(4)
                with cole1:
                    st.metric(label="Salida MOSFET Actual", value=f"{current_pwm} %")
                with cole2:
                    st.metric(label="Consumo Total Acumulado", value=f"{consumo_total_kwh:.5f} kWh")
                with cole3:
                    st.metric(label="Costo Energético Estimado", value=f"${costo_estimado:.2f} CLP")
                with cole4:
                    st.metric(label="Carga Promedio de la Manta", value=f"{pwm_promedio:.1f} %")

                st.markdown("---")

                # --- GRÁFICOS ---
                ultima_estampa = df_procesado_cronologico['created_at'].max()
                limite_hace_2_horas = ultima_estampa - timedelta(hours=2)
                df_ventana_grafico = df_procesado_cronologico[df_procesado_cronologico['created_at'] >= limite_hace_2_horas]

                st.subheader(f"📈 Curva Térmica e Historial PWM - {nodo}")
                
                if not df_ventana_grafico.empty:
                    fig = go.Figure()
                    
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['setpoint'],
                        mode='lines+markers', name='Historial Setpoint', line=dict(color='#1f77b4', width=2, dash='dash')
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['temp_agua'],
                        mode='lines+markers', name='Temperatura en Agua', line=dict(color='#ff7f0e', width=2)
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['temp_ambiente'],
                        mode='lines', name='Temperatura Ambiente', line=dict(color='#2ca02c', width=1.5)
                    ))
                    # Añadir línea de ciclo de trabajo en el mismo gráfico o escala secundaria si lo prefieres
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['duty_cycle'],
                        mode='lines', name='Esfuerzo Manta (PWM %)', line=dict(color='#9467bd', width=1, dash='dot')
                    ))

                    fig.update_layout(
                        template="plotly_dark",
                        margin=dict(l=50, r=40, t=20, b=50),
                        height=450,
                        hovermode="x unified",
                        xaxis=dict(
                            title="Estampa de Tiempo (Local)",
                            type='date',
                            tickformat='%H:%M:%S\n%d %b'
                        ),
                        yaxis=dict(title="Temperatura (°C) / Carga (%)"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )

                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
                else:
                    st.info("Alineando estampas de tiempo...")

                # --- EXPORTAR EXCEL ---
                st.subheader("📊 Descarga de Datos")
                
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                    df_excel = df_procesado_cronologico[['created_at', 'nodo_id', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle']].copy()
                    df_excel.columns = ['Fecha y Hora', 'ID Nodo', 'Temp Agua (°C)', 'Temp Ambiente (°C)', 'Setpoint (°C)', 'Esfuerzo PWM (%)']
                    df_excel.to_excel(writer, index=False, sheet_name='Datos Telemetría')
                    
                    worksheet = writer.sheets['Datos Telemetría']
                    worksheet.freeze_panes = 'A2'
                    for col in worksheet.columns:
                        max_len = max(len(str(cell.value or '')) for cell in col)
                        col_letter = col[0].column_letter
                        worksheet.column_dimensions[col_letter].width = max(max_len + 3, 12)
                
                buffer_excel.seek(0)

                st.download_button(
                    label="📥 Exportar Historial a Excel (.xlsx)",
                    data=buffer_excel,
                    file_name=f"telemetria_manta_{nodo}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                st.markdown("---")
                
                # --- TABLA DE REGISTROS RECIENTES ---
                st.subheader("📋 Registro de Datos Recientes")
                df_tabla_visual = df_procesado_cronologico.sort_values('created_at', ascending=False).copy()
                df_tabla_visual.index = range(len(df_tabla_visual) - 1, -1, -1)
                
                st.dataframe(
                    df_tabla_visual[['id', 'created_at', 'nodo_id', 'temp_agua', 'temp_ambiente', 'setpoint', 'duty_cycle']], 
                    use_container_width=True
                )

        renderizar_datos_dinamicos(nodo_seleccionado)

    # --- BOTÓN MANUAL AL FINAL DE LA PÁGINA ---
    if st.button("🔄"):
        if 'sp_local' in st.session_state:
            del st.session_state.sp_local
        if 'nodo_actual' in st.session_state:
            del st.session_state.nodo_actual
        cargar_datos.clear()
        st.rerun()
