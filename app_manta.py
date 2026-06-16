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
CONTRASENA_CORRECTA = "Manta2026!"  # <--- CAMBIA TU CONTRASEÑA AQUÍ

def verificar_password():
    """Devuelve True si el usuario ingresó la credencial correcta."""
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False

    # Si ya está autenticado, no mostrar el formulario
    if st.session_state.autenticado:
        return True

    # Pantalla de bloqueo centralizada
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.image("https://cdn-icons-png.flaticon.com/512/3064/3064155.png", width=80) # Ícono de candado visual
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

# Ejecutar la verificación antes de cargar cualquier dato o componente de la UI
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

    # Barra lateral con botón de cierre de sesión
    st.sidebar.title("🔐 Sesión Activa")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("🌡️ Panel de Monitoreo Centralizado - Proyecto Manta")
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

    @st.cache_data(ttl=0, show_spinner=False)
    def cargar_datos():
        try:
            respuesta = supabase.table("telemetria_mantas").select("*").order("created_at", desc=True).limit(300).execute()
            df = pd.DataFrame(respuesta.data)
            if not df.empty:
                df['created_at'] = pd.to_datetime(df['created_at'])
            return df
        except Exception as e:
            st.error(f"Error al traer datos de telemetría: {e}")
            return pd.DataFrame()

    # --- CARGA INICIAL DE NODOS ---
    df_inicial = cargar_datos()

    if df_inicial.empty:
        st.warning("Esperando conexión o datos iniciales desde la tabla de Supabase...")
    else:
        nodos_disponibles = df_inicial['nodo_id'].unique()
        nodo_seleccionado = st.sidebar.selectbox("Seleccionar Nodo a Monitorear:", nodos_disponibles)
        
        # --- CONTROL DE SETPOINT EN LA BARRA LATERAL ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("🎛️ Configuración de Banda Térmica")
        
        if "sp_local" not in st.session_state:
            st.session_state.sp_local = obtener_setpoint_nube(nodo_seleccionado)
        
        nuevo_sp = st.sidebar.slider(
            "Setpoint Objetivo Precision (°C):", 
            min_value=3.0, 
            max_value=6.0, 
            value=st.session_state.sp_local, 
            step=0.1
        )
        
        if nuevo_sp != st.session_state.sp_local:
            actualizar_setpoint_nube(nodo_seleccionado, nuevo_sp)
            st.session_state.sp_local = nuevo_sp
            st.sidebar.success(f"🔄 Nube actualizada: {nuevo_sp} °C")
            st.rerun()

        # --- FRAGMENTO DE REFRESCO AUTOMÁTICO CADA 5 SEGUNDOS ---
        @st.fragment(run_every=5)
        def renderizar_datos_dinamicos(nodo):
            df_dinamico = cargar_datos()
            df_filtrado = df_dinamico[df_dinamico['nodo_id'] == nodo].copy()
            
            if not df_filtrado.empty:
                # Asegurar la conversión limpia a tiempo plano (naive) para evitar desfases con Plotly
                if df_filtrado['created_at'].dt.tz is not None:
                    df_filtrado['created_at'] = df_filtrado['created_at'].dt.tz_convert('America/Punta_Arenas').dt.tz_localize(None)
                else:
                    df_filtrado['created_at'] = df_filtrado['created_at'].dt.tz_localize(None)

                ultimas_lecturas = df_filtrado.iloc[0] 

                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric(label="Estado del Nodo", value="🟢 ONLINE")
                with col2:
                    st.metric(label="Temp. Agua", value=f"{ultimas_lecturas['temp_agua']} °C")
                with col3:
                    st.metric(label="Temp. Ambiente", value=f"{ultimas_lecturas['temp_ambiente']} °C")
                with col4:
                    st.metric(label="Setpoint Objetivo", value=f"{ultimas_lecturas['setpoint']} °C")

                st.markdown("---")

                # --- PROCESAMIENTO CRONOLÓGICO PARA EL GRÁFICO ---
                df_cronologico = df_filtrado.sort_values('created_at', ascending=True)
                
                # Definir la ventana de las últimas 2 horas basándonos en la estampa más reciente registrada
                ultima_estampa = df_cronologico['created_at'].max()
                limite_hace_2_horas = ultima_estampa - timedelta(hours=2)
                df_ventana_grafico = df_cronologico[df_cronologico['created_at'] >= limite_hace_2_horas]

                st.subheader(f"📈 Curva Térmica Histórica en Tiempo Real - {nodo}")
                
                if not df_ventana_grafico.empty:
                    fig = go.Figure()
                    
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['setpoint'],
                        mode='lines', name='Setpoint Objetivo', line=dict(color='#1f77b4', width=2, dash='dash')
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['temp_agua'],
                        mode='lines+markers', name='Temperatura en Agua', line=dict(color='#ff7f0e', width=2.5)
                    ))
                    fig.add_trace(go.Scatter(
                        x=df_ventana_grafico['created_at'], y=df_ventana_grafico['temp_ambiente'],
                        mode='lines', name='Temperatura Ambiente', line=dict(color='#2ca02c', width=2)
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
                        yaxis=dict(title="Temperatura (°C)"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                    )

                    st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': True})
                else:
                    st.info("Alineando estampas de tiempo...")

                # --- EXPORTACIÓN A EXCEL AUTOMATIZADA ---
                st.subheader("📊 Gestión y Descarga de Datos")
                
                buffer_excel = io.BytesIO()
                with pd.ExcelWriter(buffer_excel, engine='openpyxl') as writer:
                    df_excel = df_cronologico[['created_at', 'nodo_id', 'temp_agua', 'temp_ambiente', 'setpoint']].copy()
                    df_excel.columns = ['Fecha y Hora', 'ID Nodo', 'Temp Agua (°C)', 'Temp Ambiente (°C)', 'Setpoint (°C)']
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
                st.subheader("📋 Registro de Datos Recientes")
                st.dataframe(df_filtrado[['id', 'created_at', 'nodo_id', 'temp_agua', 'temp_ambiente', 'setpoint']], use_container_width=True)

        renderizar_datos_dinamicos(nodo_seleccionado)

    if st.button("🔄 Forzar Sincronización Completa"):
        if 'sp_local' in st.session_state:
            del st.session_state.sp_local
        st.rerun()
