# ==========================================
                #  NUEVA SECCIÓN DE CONSUMO ENERGÉTICO PERSISTENTE
                # ==========================================
                # Funciones auxiliares para interactuar con la tabla de acumulados
                def obtener_acumulados(nodo):
                    try:
                        res = supabase.table("acumulados_nodos").select("*").eq("nodo_id", nodo).execute()
                        if res.data:
                            return res.data[0]
                    except:
                        pass
                    return {"kwh_historico_total": 0.0, "costo_historico_total": 0.0, "kwh_desde_reset": 0.0, "costo_desde_reset": 0.0}

                def ejecutar_reset_nube(nodo):
                    try:
                        supabase.table("acumulados_nodos").update({
                            "kwh_desde_reset": 0.0,
                            "costo_desde_reset": 0.0,
                            "ultimo_reset_at": "now()"
                        }).eq("nodo_id", nodo).execute()
                        st.success("🔄 Contador de ensayo reiniciado en la nube.")
                    except Exception as e:
                        st.error(f"Error al resetear: {e}")

                # Cargar contadores persistentes desde Supabase
                datos_acumulados = obtener_acumulados(nodo)
                pwm_promedio = df_cronologico_base['duty_cycle'].mean()
                ultimas_lecturas = df_cronologico_base.iloc[-1] 
                current_pwm = int(ultimas_lecturas['duty_cycle'])

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

                # --- FILA 2: MÉTRICAS ENERGÉTICAS (ACTUALIZADAS) ---
                st.subheader("Eficiencia y Consumo Eléctrico")
                cole1, cole2, cole3, cole4 = st.columns(4)
                with cole1:
                    st.metric(label="Salida MOSFET Actual", value=f"{current_pwm} %")
                with cole2:
                    # Muestra el acumulado de este ensayo específico
                    st.metric(label="Consumo Ensayo Actual", value=f"{float(datos_acumulados['kwh_desde_reset']):.5f} kWh")
                with cole3:
                    # Muestra el costo estimado de este ensayo específico
                    st.metric(label="Costo Ensayo Actual", value=f"${float(datos_acumulados['costo_desde_reset']):.2f} CLP")
                with cole4:
                    st.metric(label="Carga Promedio de la Manta", value=f"{pwm_promedio:.1f} %")

                # --- NUEVA FILA 2.5: HISTÓRICO GLOBAL Y BOTÓN DE ACCIÓN ---
                col_hist1, col_hist2, col_btn = st.columns([2, 2, 1])
                with col_hist1:
                    st.caption(f"🌍 **Acumulado Histórico Total del Nodo:** {float(datos_acumulados['kwh_historico_total']):.5f} kWh")
                with col_hist2:
                    st.caption(f"💰 **Costo Histórico Total:** ${float(datos_historico:=datos_acumulados['costo_historico_total']):.2f} CLP")
                with col_btn:
                    # Botón físico para reiniciar la cuenta del ensayo actual
                    if st.button("⚠️ Resetear Cuenta Ensayo", use_container_width=True, help="Limpia la cuenta del ensayo actual pero conserva el acumulador histórico global."):
                        ejecutar_reset_nube(nodo)
                        cargar_datos.clear()
                        st.rerun()

                st.markdown("---")
