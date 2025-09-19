import io, smtplib
from email.message import EmailMessage
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

# =========================
# Configuración general
# =========================
st.set_page_config(page_title="Dashboard Evolucion App Heaven", page_icon="📊", layout="wide")

# Logo arriba (del repo)
LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"
st.markdown(
    f"""
    <div style="text-align:center; margin-bottom:16px;">
        <img src="{LOGO_URL}" width="160" alt="Logo Iglesia">
    </div>
    """,
    unsafe_allow_html=True
)

st.title("📊 Dashboard App Iglesia")

st.markdown("""
### ℹ️ ¿Qué significa cada métrica?
- **👀 Impresiones:** Veces que la app fue **vista en la tienda** (App Store / Google Play). Mide **visibilidad**.
- **⬇️ Descargas:** Veces que la app fue **instalada**. Mide **interés**.
- **🚀 Lanzamientos:** Veces que los usuarios **abrieron la app**. Mide **uso / engagement**.
""")
st.divider()

# =========================
# Utilidades
# =========================
MESES_ABR_ES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
DIAS_ABR_ES  = ["lun","mar","mié","jue","vie","sáb","dom"]
PLAT_NAMES = {  # renombrar plataformas a español bonito
    "ios":"iOS","android":"Android","apple_tv":"Apple TV","roku":"Roku","web":"Web",
    "ipad":"iPad","iphone":"iPhone","tv":"TV","other":"Otros"
}

def leer_csv(path_or_buffer):
    """Lee CSV con autodetección de separador."""
    return pd.read_csv(path_or_buffer, sep=None, engine="python")

def cargar_metric_con_plataformas(path_or_buffer, nombre_total):
    """
    Devuelve:
    - df_total: Fecha, <nombre_total>
    - df_plat:  Fecha, columnas por plataforma (si existen)
    """
    raw = leer_csv(path_or_buffer)
    lower = {c.lower(): c for c in raw.columns}
    if "date" not in lower or "total" not in lower:
        st.error(f"El archivo no tiene columnas esperadas 'date' y 'total'. Columnas: {list(raw.columns)}")
        st.stop()

    # Total
    df_total = raw.rename(columns={lower["date"]:"Fecha", lower["total"]: nombre_total})
    df_total["Fecha"] = pd.to_datetime(df_total["Fecha"], errors="coerce")
    df_total = df_total.dropna(subset=["Fecha"])
    df_total[nombre_total] = pd.to_numeric(df_total[nombre_total], errors="coerce").fillna(0)
    df_total = df_total[["Fecha", nombre_total]]

    # Plataformas (todas excepto date/total)
    plat_cols = [c for c in raw.columns if c not in [lower["date"], lower["total"]]]
    df_plat = None
    if plat_cols:
        df_plat = raw.rename(columns={lower["date"]:"Fecha"})
        df_plat["Fecha"] = pd.to_datetime(df_plat["Fecha"], errors="coerce")
        df_plat = df_plat.dropna(subset=["Fecha"])
        # normalizar nombres y tipos
        rename_map = {}
        for c in plat_cols:
            name = c.strip().lower()
            rename_map[c] = PLAT_NAMES.get(name, c.replace("_"," ").title())
        df_plat = df_plat[["Fecha"] + plat_cols].rename(columns=rename_map)
        for c in df_plat.columns:
            if c != "Fecha":
                df_plat[c] = pd.to_numeric(df_plat[c], errors="coerce").fillna(0)

    return df_total, df_plat

def enriquecer_tiempo(df):
    df["Año"] = df["Fecha"].dt.year
    df["MesNum"] = df["Fecha"].dt.month
    df["MesAbr"] = df["MesNum"].map(lambda m: MESES_ABR_ES[m-1])
    df["Día"] = df["Fecha"].dt.day
    df["Semana"] = df["Fecha"].dt.isocalendar().week.astype(int)
    df["DiaSemana"] = df["Fecha"].dt.weekday
    df["DiaSemanaAbr"] = df["DiaSemana"].map(lambda d: DIAS_ABR_ES[d])
    df["Etiqueta_dia"]  = df["Día"].astype(str).str.zfill(2) + " " + df["MesAbr"] + " " + df["Año"].astype(str)
    df["Etiqueta_mes"]  = df["MesAbr"] + " " + df["Año"].astype(str)
    df["Etiqueta_año"]  = df["Año"].astype(str)
    df["Etiqueta_sem"]  = "Sem " + df["Semana"].astype(str) + " " + df["Año"].astype(str)
    return df

def agregar(df, nivel, cols_valor):
    if nivel == "Día":
        by, label = ["Año","MesNum","Día","Etiqueta_dia"], "Etiqueta_dia"
    elif nivel == "Semana":
        by, label = ["Año","Semana","Etiqueta_sem"], "Etiqueta_sem"
    elif nivel == "Mes":
        by, label = ["Año","MesNum","Etiqueta_mes"], "Etiqueta_mes"
    else:
        by, label = ["Año","Etiqueta_año"], "Etiqueta_año"
    g = df.groupby(by, dropna=False)[cols_valor].sum().reset_index()
    orden = [c for c in ["Año","MesNum","Semana","Día"] if c in g.columns]
    if orden: g = g.sort_values(orden)
    g = g.rename(columns={label: "Etiqueta"})
    return g

def dibujar(tipo, df_indexed):
    if tipo == "Líneas": st.line_chart(df_indexed)
    else:                st.bar_chart(df_indexed)

def variacion_pct(a, b):
    if b == 0: return np.nan
    return (a - b) / b * 100.0

def tendencia(actual, previo):
    if previo is None or np.isnan(previo): return "↔"
    if actual > previo: return "↑"
    if actual < previo: return "↓"
    return "↔"

def color_semaforo(valor, meta, tolerancia_pct=10):
    """
    Verde: >= meta
    Amarillo: >= (meta - tolerancia)
    Rojo: < (meta - tolerancia)
    """
    if meta is None: return "🔵"  # sin meta
    tolerancia = meta * (tolerancia_pct/100)
    if valor >= meta: return "🟢"
    if valor >= meta - tolerancia: return "🟡"
    return "🔴"

# --- Figuras Matplotlib (para PDF y avanzados) ---
def fig_linea(x, y_series, titulo):
    fig, ax = plt.subplots(figsize=(9,4))
    for nombre, serie in y_series.items():
        ax.plot(x, serie, label=nombre)
    ax.set_title(titulo); ax.grid(True, alpha=.3); ax.legend(); fig.tight_layout(); return fig

def fig_barras_apiladas(x, df_plat, titulo):
    fig, ax = plt.subplots(figsize=(9,4))
    df_plat.plot(kind="bar", stacked=True, ax=ax)
    ax.set_xticklabels(x, rotation=45, ha="right")
    ax.set_title(titulo); ax.grid(axis="y", alpha=.3); fig.tight_layout(); return fig

def fig_embudo(tot_imp, tot_dwn, tot_lnc):
    etapas = ["Impresiones","Descargas","Lanzamientos"]; vals = [tot_imp, tot_dwn, tot_lnc]
    fig, ax = plt.subplots(figsize=(6,4)); ax.barh(etapas, vals)
    ax.set_title("Embudo de conversión"); 
    for i,v in enumerate(vals): ax.text(v, i, f" {int(v):,}", va="center")
    fig.tight_layout(); return fig

def fig_heatmap_uso(df):
    df2 = df.copy()
    tabla = df2.groupby(["DiaSemanaAbr","MesAbr"])["Lanzamientos"].sum().unstack(fill_value=0).reindex(DIAS_ABR_ES)
    fig, ax = plt.subplots(figsize=(9,4))
    im = ax.imshow(tabla.values, aspect="auto")
    ax.set_yticks(range(len(tabla.index)), labels=tabla.index)
    ax.set_xticks(range(len(tabla.columns)), labels=tabla.columns)
    ax.set_title("Heatmap de lanzamientos por día semana vs mes")
    fig.colorbar(im, ax=ax); fig.tight_layout(); return fig

def generar_pdf(logo_url, periodo_txt, kpis, figuras, tabla):
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Portada KPIs
        fig, ax = plt.subplots(figsize=(8.27,11.69)); ax.axis("off")
        ax.text(0.5, 0.93, "Dashboard App Iglesia – Reporte", ha="center", fontsize=20, weight="bold")
        ax.text(0.5, 0.88, periodo_txt, ha="center", fontsize=12)
        ax.text(0.1, 0.80, f"👀 Impresiones: {kpis['imp']:,}", fontsize=14)
        ax.text(0.1, 0.74, f"⬇️ Descargas: {kpis['dwn']:,}", fontsize=14)
        ax.text(0.1, 0.68, f"🚀 Lanzamientos: {kpis['lnc']:,}", fontsize=14)
        ax.text(0.1, 0.62, f"📈 Conversión: {kpis['conv']:,.2f}%", fontsize=14)
        ax.text(0.1, 0.56, f"🧭 Uso por instalación: {kpis['uso']:,.2f}", fontsize=14)
        pdf.savefig(fig); plt.close(fig)
        # Gráficos
        for f in figuras: pdf.savefig(f); plt.close(f)
        # Tabla agregada
        fig, ax = plt.subplots(figsize=(8.27,11.69)); ax.axis("off"); ax.set_title("Datos agregados", loc="left")
        max_rows = 35; start = 0
        while start < len(tabla):
            end = min(start+max_rows, len(tabla))
            sub = tabla.iloc[start:end]
            ax.text(0.02, 0.95, sub.to_string(index=False), family="monospace", va="top")
            pdf.savefig(fig); ax.cla(); ax.axis("off"); ax.set_title("Datos agregados", loc="left"); start = end
        plt.close(fig)
    buf.seek(0); return buf.getvalue()

def enviar_email_pdf(to_email, subject, body_md, pdf_bytes, filename="reporte.pdf"):
    cfg = st.secrets.get("smtp", {})
    host = cfg.get("host"); port = int(cfg.get("port", 587))
    user = cfg.get("user"); password = cfg.get("password"); sender = cfg.get("sender", user)
    if not all([host, port, user, password, sender]):
        st.error("Config SMTP incompleta en st.secrets['smtp']."); return False
    msg = EmailMessage()
    msg["From"] = sender; msg["To"] = to_email; msg["Subject"] = subject
    msg.set_content(body_md)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    with smtplib.SMTP(host, port) as server:
        server.starttls(); server.login(user, password); server.send_message(msg)
    return True

# =========================
# Carga de datos
# =========================
st.sidebar.header("Origen de datos")
origen = st.sidebar.radio("Selecciona cómo cargar los datos", ["Archivos del repositorio", "Subir archivos CSV"])

if origen == "Archivos del repositorio":
    try:
        imp_tot, imp_plat = cargar_metric_con_plataformas("impressions-year.csv", "Impresiones")
        dwn_tot, dwn_plat = cargar_metric_con_plataformas("app-downloads-year.csv", "Descargas")
        lnc_tot, lnc_plat = cargar_metric_con_plataformas("app-launches-year.csv", "Lanzamientos")
    except Exception as e:
        st.error(f"No pude cargar los CSV: {e}"); st.stop()
else:
    st.sidebar.caption("Sube: impresiones, descargas y lanzamientos (con 'date', 'total' y/o plataformas).")
    up_imp = st.sidebar.file_uploader("Impresiones", type=["csv"], key="imp")
    up_dwn = st.sidebar.file_uploader("Descargas", type=["csv"], key="dwn")
    up_lnc = st.sidebar.file_uploader("Lanzamientos", type=["csv"], key="lnc")
    if not (up_imp and up_dwn and up_lnc):
        st.info("Sube los tres CSV para continuar."); st.stop()
    imp_tot, imp_plat = cargar_metric_con_plataformas(up_imp, "Impresiones")
    dwn_tot, dwn_plat = cargar_metric_con_plataformas(up_dwn, "Descargas")
    lnc_tot, lnc_plat = cargar_metric_con_plataformas(up_lnc, "Lanzamientos")

# Unir totales
df = (
    imp_tot.merge(dwn_tot, on="Fecha", how="outer")
           .merge(lnc_tot, on="Fecha", how="outer")
           .fillna(0).sort_values("Fecha")
)
if df.empty: st.warning("No hay datos disponibles."); st.stop()

df = enriquecer_tiempo(df)

# =========================
# Filtros y Metas (OKRs)
# =========================
st.sidebar.header("Filtros")
rango = st.sidebar.date_input("Rango de fechas", value=(df["Fecha"].min().date(), df["Fecha"].max().date()))
if isinstance(rango, tuple) and len(rango)==2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df = df[(df["Fecha"] >= ini) & (df["Fecha"] <= fin)]

gran = st.sidebar.radio("Granularidad", ["Día","Semana","Mes","Año"], horizontal=False)
metricas_disp = ["Impresiones","Descargas","Lanzamientos"]
metricas_sel  = st.sidebar.multiselect("Métricas", metricas_disp, default=metricas_disp)
tipo_graf     = st.sidebar.radio("Tipo de gráfico", ["Líneas","Barras"], horizontal=True)

st.sidebar.header("Metas (OKRs)")
meta_conv = st.sidebar.number_input("Meta de Conversión % (Descargas/Impresiones)", value=1.0, step=0.1)
meta_uso  = st.sidebar.number_input("Meta de Uso por instalación (Lanzamientos/Descargas)", value=12.0, step=0.5)
umbral_alerta = st.sidebar.slider("Alerta si baja más de (%) vs período anterior", 5, 80, 20)

# =========================
# Agregación para gráficas
# =========================
agg = agregar(df, gran, metricas_sel)
agg_idx = agg.set_index("Etiqueta")[metricas_sel]

# =========================
# KPIs + Semáforo + Tendencia
# =========================
c1, c2, c3, c4 = st.columns(4)
tot_imp = int(df["Impresiones"].sum()); tot_dwn = int(df["Descargas"].sum()); tot_lnc = int(df["Lanzamientos"].sum())
conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
uso_instal = (tot_lnc/tot_dwn) if tot_dwn>0 else 0

# Tendencia: último punto vs anterior en la granularidad seleccionada
trend_prev_imp = trend_prev_dwn = trend_prev_lnc = None
if len(agg_idx) >= 2:
    trend_prev_imp = agg_idx["Impresiones"].iloc[-2] if "Impresiones" in agg_idx else None
    trend_prev_dwn = agg_idx["Descargas"].iloc[-2]   if "Descargas"   in agg_idx else None
    trend_prev_lnc = agg_idx["Lanzamientos"].iloc[-2]if "Lanzamientos" in agg_idx else None

c1.metric(f"{color_semaforo(conv, meta_conv)} Conversión", f"{conv:,.2f}%", delta=f"{variacion_pct(conv, trend_prev_dwn/tot_imp*100 if (trend_prev_dwn and tot_imp>0) else np.nan):+.1f}%" if trend_prev_dwn else None)
c2.metric(f"{color_semaforo(uso_instal, meta_uso)} Uso por instalación", f"{uso_instal:,.2f}", delta=None)
c3.metric("👀 Impresiones", f"{tot_imp:,}", delta=tendencia(agg_idx.iloc[-1]["Impresiones"] if "Impresiones" in agg_idx else None, trend_prev_imp))
c4.metric("⬇️ Descargas", f"{tot_dwn:,}", delta=tendencia(agg_idx.iloc[-1]["Descargas"] if "Descargas" in agg_idx else None, trend_prev_dwn))

st.divider()

# =========================
# Alertas automáticas
# =========================
alertas = []
def add_alerta(nombre, actual, previo):
    if previo and previo>0:
        cambio = variacion_pct(actual, previo)
        if not np.isnan(cambio) and cambio <= -umbral_alerta:
            alertas.append(f"🚨 **{nombre}** cayó **{cambio:.1f}%** vs el período anterior.")

if len(agg_idx) >= 2:
    a, p = agg_idx.iloc[-1], agg_idx.iloc[-2]
    for m in metricas_disp:
        if m in agg_idx:
            add_alerta(m, a[m], p[m])

if alertas:
    st.error(" \n".join(alertas))
else:
    st.success("✅ Sin alertas críticas en el período seleccionado.")

# =========================
# Tabs principales
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualización", "🧩 Segmentación por plataforma", "🔥 Análisis avanzado", "📄 Reportes"])

with tab1:
    st.subheader(f"Evolución por {gran.lower()} – {', '.join(metricas_sel)}")
    dibujar(tipo_graf, agg_idx)

with tab2:
    st.subheader("Segmentación por plataforma")
    # Intentar armar data de plataformas para una métrica elegida
    met_seg = st.selectbox("Métrica para segmentar", metricas_disp, index=1)
    map_plat_df = {"Impresiones": imp_plat, "Descargas": dwn_plat, "Lanzamientos": lnc_plat}
    dfp = map_plat_df.get(met_seg)
    if dfp is None:
        st.info("Este CSV no trae columnas por plataforma. Sube archivos con desglose (ios, android, etc.) para activar esta sección.")
    else:
        dfp = dfp.copy()
        dfp = dfp.merge(df[["Fecha"]], on="Fecha", how="inner")  # alinear al rango filtrado
        dfp = enriquecer_tiempo(dfp)
        by_cols = {"Día":["Año","MesNum","Día","Etiqueta_dia"],
                   "Semana":["Año","Semana","Etiqueta_sem"],
                   "Mes":["Año","MesNum","Etiqueta_mes"],
                   "Año":["Año","Etiqueta_año"]}[gran]
        etiqueta = by_cols[-1]
        agg_plat = dfp.groupby(by_cols).sum(numeric_only=True).reset_index().rename(columns={etiqueta:"Etiqueta"})
        # Preparar stacked
        plat_cols = [c for c in agg_plat.columns if c not in ["Año","MesNum","Semana","Día","Etiqueta","Fecha","DiaSemana","DiaSemanaAbr","MesAbr"]]
        agg_plat_sorted = agg_plat.sort_values([c for c in ["Año","MesNum","Semana","Día"] if c in agg_plat.columns])
        idx = agg_plat_sorted.set_index("Etiqueta")[plat_cols]
        st.markdown("**Barras apiladas por plataforma**")
        fig_stack = fig_barras_apiladas(idx.index.tolist(), idx, f"{met_seg} por {gran.lower()} (apilado)")
        st.pyplot(fig_stack, use_container_width=True)
        st.markdown("**Participación por plataforma (último período)**")
        if len(idx)>0:
            ultimo = idx.iloc[-1]
            fig, ax = plt.subplots(figsize=(6,4)); ax.pie(ultimo, labels=ultimo.index, autopct="%1.0f%%")
            ax.set_title(f"Participación en el último {gran.lower()}"); fig.tight_layout(); st.pyplot(fig, use_container_width=True)

with tab3:
    st.subheader("Análisis avanzado")
    st.markdown("**Comparativa de métricas (líneas)**")
    dibujar("Líneas", agg_idx)
    st.markdown("**Embudo de conversión (Impresiones → Descargas → Lanzamientos)**")
    fig_funnel = fig_embudo(tot_imp, tot_dwn, tot_lnc); st.pyplot(fig_funnel, use_container_width=True)
    st.markdown("**Heatmap de lanzamientos** (día de semana × mes)")
    fig_heat = fig_heatmap_uso(df); st.pyplot(fig_heat, use_container_width=True)

with tab4:
    st.subheader("Reportes profesionales y distribución")
    periodo = st.selectbox("Tipo de reporte", ["Diario","Semanal","Mensual"])
    tabla_rep = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo], metricas_disp)

    # Figuras para PDF
    x = agg["Etiqueta"].tolist()
    series = {m: agg[m].tolist() for m in metricas_sel}
    fig1 = fig_linea(x, series, f"Evolución por {gran.lower()}")
    fig2 = fig_linea(x, {k:series[k] for k in series}, "Comparativa")
    fig3 = fig_heat
    fig4 = fig_funnel

    kpis = {"imp": tot_imp, "dwn": tot_dwn, "lnc": tot_lnc, "conv": conv, "uso": uso_instal}
    periodo_txt = f"Rango: {rango[0]} a {rango[1]} – Reporte {periodo.lower()}"

    col_pdf, col_xlsx, col_mail = st.columns([1,1,1])

    with col_pdf:
        if st.button("📄 Generar PDF"):
            pdf_bytes = generar_pdf(LOGO_URL, periodo_txt, kpis, [fig1, fig2, fig3, fig4], tabla_rep)
            st.download_button("⬇️ Descargar PDF", data=pdf_bytes, file_name=f"reporte_{periodo.lower()}.pdf", mime="application/pdf")

    with col_xlsx:
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
            tabla_rep.to_excel(writer, index=False, sheet_name="Datos")
        st.download_button("📊 Descargar Excel", data=out.getvalue(), file_name=f"datos_{periodo.lower()}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with col_mail:
        destinatario = st.text_input("Enviar por email a:", placeholder="lideres@tuiglesia.org")
        if st.button("✉️ Enviar PDF por email"):
            pdf_bytes = generar_pdf(LOGO_URL, periodo_txt, kpis, [fig1, fig2, fig3, fig4], tabla_rep)
            if destinatario:
                try:
                    ok = enviar_email_pdf(destinatario, f"Reporte {periodo} – App Iglesia", 
                                          f"Adjunto reporte {periodo.lower()}.\nRango: {rango[0]} a {rango[1]}", 
                                          pdf_bytes, filename=f"reporte_{periodo.lower()}.pdf")
                    st.success("📬 Email enviado correctamente." if ok else "No se pudo enviar el email.")
                except Exception as e:
                    st.error(f"Error al enviar email: {e}")
            else:
                st.info("Escribe un correo destino para enviar el reporte.")
