import io
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ReportLab (PDF profesional)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak)

# =========================
# Configuración base
# =========================
st.set_page_config(page_title="Dashboard Evolucion de APP Heaven", page_icon="📊", layout="wide")

LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"
MESES_LARGO = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MESES_ABR   = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def fmt_fecha_es(ts, abr=True):
    if pd.isna(ts): return ""
    d = int(ts.day); m = int(ts.month); y = int(ts.year)
    mes = (MESES_ABR if abr else MESES_LARGO)[m-1]
    return f"{d:02d} {mes.capitalize()} {y}"

# ---- Título principal ----
st.markdown(
    """
    <h1 style='text-align: center;'>
        📊 Dashboard Evolucion de APP Heaven
    </h1>
    """,
    unsafe_allow_html=True
)
st.markdown(
    f"""<div style="text-align:center; margin-bottom:16px;">
          <img src="{LOGO_URL}" width="140" alt="Logo Iglesia">
        </div>""",
    unsafe_allow_html=True
)
st.caption("Monitoreo de Impresiones, Descargas y Lanzamientos — filtros claros, exportación y reportes profesionales.")
st.divider()

# =========================
# Carga & normalización
# =========================
@st.cache_data
def leer_csv(path):
    return pd.read_csv(path, sep=None, engine="python")

def cargar_metricas(path_or_buffer, nombre_metrica):
    """Lee CSV con columnas: date, total, (opcionales) plataformas.
       Devuelve:
       - df_total: Fecha, <Métrica>, Año, MesNum, Semana, etiquetas (día/semana/mes/año)
       - df_plat: desglose por plataforma (si existe)
    """
    raw = leer_csv(path_or_buffer)
    cols_lower = {c.lower(): c for c in raw.columns}
    if "date" not in cols_lower or "total" not in cols_lower:
        st.error(f"El archivo debe tener columnas 'date' y 'total'. Trae: {list(raw.columns)}")
        st.stop()

    df = raw.rename(columns={cols_lower["date"]: "Fecha", cols_lower["total"]: nombre_metrica}).copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])
    df[nombre_metrica] = pd.to_numeric(df[nombre_metrica], errors="coerce").fillna(0)

    # Campos de tiempo + etiquetas (ES)
    df["Año"]    = df["Fecha"].dt.year
    df["MesNum"] = df["Fecha"].dt.month
    df["Semana"] = df["Fecha"].dt.isocalendar().week.astype(int)
    df["Sem_ini"] = df["Fecha"] - pd.to_timedelta(df["Fecha"].dt.weekday, unit="D")
    df["Sem_fin"] = df["Sem_ini"] + pd.Timedelta(days=6)

    df["Etiqueta_dia"] = df["Fecha"].apply(lambda x: fmt_fecha_es(x, True))
    df["Etiqueta_mes"] = df["MesNum"].map(lambda m: MESES_LARGO[m-1]) + " " + df["Año"].astype(str)
    df["Etiqueta_año"] = df["Año"].astype(str)
    df["Etiqueta_sem"] = ("Sem " + df["Semana"].astype(str) + " (" +
                          df["Sem_ini"].apply(lambda x: fmt_fecha_es(x, True)) + " – " +
                          df["Sem_fin"].apply(lambda x: fmt_fecha_es(x, True)) + ")")

    df_total = df[["Fecha", nombre_metrica, "Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"]]

    # Plataformas (todas menos 'date'/'Fecha' y 'total' y la métrica)
    plat_cols = [c for c in raw.columns if c not in [cols_lower["date"], cols_lower["total"]]]
    df_plat = None
    if plat_cols:
        dfp = raw[[cols_lower["date"]] + plat_cols].copy()
        dfp["Fecha"] = pd.to_datetime(dfp[cols_lower["date"]], errors="coerce")
        dfp = dfp.dropna(subset=["Fecha"]).drop(columns=[cols_lower["date"]])

        # nombres de plataformas bonitos
        def pretty(c):
            m = {"ios":"iOS","android":"Android","apple_tv":"Apple TV","roku":"Roku","fire_tv":"Fire TV",
                 "google_tv":"Google TV","car_play":"CarPlay","android_auto":"Android Auto"}
            key = c.strip().lower()
            return m.get(key, c.replace("_"," ").title())

        dfp = dfp.rename(columns={c: pretty(c) for c in plat_cols})
        for c in dfp.columns:
            if c != "Fecha":
                dfp[c] = pd.to_numeric(dfp[c], errors="coerce").fillna(0)
        df_plat = dfp

    return df_total, df_plat

# =========================
# Filtros de fecha (atajos robustos)
# =========================
def rango_por_atajo(opcion, hoy, mes_especifico=None, anio_especifico=None, hasta_hoy=True):
    if opcion == "Últimos 7 días":
        return (hoy - pd.Timedelta(days=6)), hoy
    if opcion == "Últimos 30 días":
        return (hoy - pd.Timedelta(days=29)), hoy
    if opcion == "Este mes":
        return pd.Timestamp(hoy.year, hoy.month, 1), hoy
    if opcion == "Mes pasado":
        first_this = pd.Timestamp(hoy.year, hoy.month, 1)
        last_prev  = first_this - pd.Timedelta(days=1)
        return pd.Timestamp(last_prev.year, last_prev.month, 1), last_prev
    if opcion == "Este año":
        return pd.Timestamp(hoy.year, 1, 1), hoy
    if opcion == "Año pasado":
        return pd.Timestamp(hoy.year-1, 1, 1), pd.Timestamp(hoy.year-1, 12, 31)
    if opcion == "Mes específico…":
        if mes_especifico is None or anio_especifico is None:
            return None, None
        ini = pd.Timestamp(anio_especifico, mes_especifico, 1)
        fin = hoy if (hasta_hoy and anio_especifico==hoy.year and mes_especifico==hoy.month) else (ini + pd.offsets.MonthEnd(1))
        return ini, fin
    return None, None

# =========================
# Carga de datos (repo o upload)
# =========================
st.sidebar.header("Origen de datos")
origen = st.sidebar.radio("Selecciona cómo cargar los datos", ["Archivos del repositorio", "Subir archivos CSV"])

if origen == "Archivos del repositorio":
    imp_tot, imp_plat = cargar_metricas("impressions-year.csv", "Impresiones")
    dwn_tot, dwn_plat = cargar_metricas("app-downloads-year.csv", "Descargas")
    lnc_tot, lnc_plat = cargar_metricas("app-launches-year.csv", "Lanzamientos")
else:
    st.sidebar.caption("Sube los tres CSV (con columnas `date` y `total`):")
    up_imp = st.sidebar.file_uploader("Impresiones", type=["csv"])
    up_dwn = st.sidebar.file_uploader("Descargas",  type=["csv"])
    up_lnc = st.sidebar.file_uploader("Lanzamientos", type=["csv"])
    if not (up_imp and up_dwn and up_lnc):
        st.info("Sube los tres CSV para continuar."); st.stop()
    imp_tot, imp_plat = cargar_metricas(up_imp, "Impresiones")
    dwn_tot, dwn_plat = cargar_metricas(up_dwn, "Descargas")
    lnc_tot, lnc_plat = cargar_metricas(up_lnc, "Lanzamientos")

# Maestro
df = (imp_tot.merge(dwn_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
             .merge(lnc_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
             .fillna(0).sort_values("Fecha"))

for c in ["Impresiones","Descargas","Lanzamientos"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

if df.empty:
    st.warning("No hay datos."); st.stop()

# ---- Rango real disponible ----
data_min = df["Fecha"].min().date()
data_max = df["Fecha"].max().date()
st.info(f"📅 Datos disponibles: **{data_min}** → **{data_max}**")

# =========================
# Filtros & Metas
# =========================
st.sidebar.header("Filtros")
hoy = pd.Timestamp(data_max)

atajo = st.sidebar.selectbox(
    "Atajo de fechas",
    ["Últimos 30 días","Últimos 7 días","Este mes","Mes pasado","Este año","Año pasado","Mes específico…"],
    index=2
)

mes_espec = None; anio_espec = None; hasta_hoy = True
if atajo == "Mes específico…":
    c1, c2 = st.sidebar.columns(2)
    mes_espec  = c1.selectbox("Mes", list(range(1,13)), format_func=lambda m: MESES_LARGO[m-1])
    anio_espec = c2.number_input("Año", value=int(hoy.year), step=1)
    hasta_hoy  = st.sidebar.checkbox("Hasta hoy (si es el mes actual)", value=True)

ini_r, fin_r = rango_por_atajo(atajo, hoy, mes_espec, anio_espec, hasta_hoy)

# Si None (p.ej., aún no eliges mes/año), usa último mes de datos
if ini_r is None:
    ini_r = max(pd.Timestamp(data_max) - pd.DateOffset(days=30), pd.Timestamp(data_min))
    fin_r = pd.Timestamp(data_max)

# Recorta para que siempre esté dentro del rango de datos
ini_r = max(pd.Timestamp(ini_r).date(), data_min)
fin_r = min(pd.Timestamp(fin_r).date(), data_max)

# Selector manual limitado al rango real
ini_r, fin_r = st.sidebar.date_input(
    "Rango (ajustable)",
    value=(ini_r, fin_r),
    min_value=data_min,
    max_value=data_max
)

# Aplica el filtro inclusivo
ini_ts, fin_ts = pd.to_datetime(ini_r), pd.to_datetime(fin_r)
df = df[(df["Fecha"] >= ini_ts) & (df["Fecha"] <= fin_ts)]
if df.empty:
    st.warning("No hay datos en el rango seleccionado. Ajusta el filtro de fechas.")
    st.stop()

gran = st.sidebar.radio("Granularidad", ["Día","Semana","Mes","Año"])
metricas = ["Impresiones","Descargas","Lanzamientos"]
metricas_sel = st.sidebar.multiselect("Métricas", metricas, default=metricas)
tipo_graf = st.sidebar.radio("Tipo de gráfico", ["Líneas","Barras"], horizontal=True)
umbral_alerta = st.sidebar.slider("Alerta si baja más de (%) vs período anterior", 5, 80, 20)

# =========================
# Panel de definiciones (para no técnicos)
# =========================
with st.expander("ℹ️ ¿Qué significan estas métricas?"):
    st.markdown("""
**📊 Impresiones:** número de veces que la app fue mostrada en las tiendas o en notificaciones (indica alcance/visibilidad).  
**📥 Descargas:** cantidad de instalaciones de la app por usuarios.  
**🚀 Lanzamientos:** veces que los usuarios abrieron la app luego de instalarla.  
**📈 Conversión:** relación entre descargas e impresiones (Descargas ÷ Impresiones).
""")

# =========================
# Agregación
# =========================
def agregar(df, nivel, cols):
    if nivel == "Día":
        by, lab = ["Año","MesNum","Fecha","Etiqueta_dia"], "Etiqueta_dia"
    elif nivel == "Semana":
        by, lab = ["Año","Semana","Etiqueta_sem"], "Etiqueta_sem"
    elif nivel == "Mes":
        by, lab = ["Año","MesNum","Etiqueta_mes"], "Etiqueta_mes"
    else:
        by, lab = ["Año","Etiqueta_año"], "Etiqueta_año"
    g = df.groupby(by, dropna=False)[cols].sum().reset_index().rename(columns={lab:"Etiqueta"})
    g = g.sort_values([c for c in ["Año","MesNum","Semana","Fecha"] if c in g.columns])
    return g

agg = agregar(df, gran, metricas_sel)

# =========================
# KPIs & Alertas
# =========================
c1,c2,c3,c4 = st.columns(4)
tot_imp = int(df["Impresiones"].sum()); tot_dwn = int(df["Descargas"].sum()); tot_lnc = int(df["Lanzamientos"].sum())
conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0
c1.metric("👀 Impresiones (período)", f"{tot_imp:,}")
c2.metric("📥 Descargas (período)",  f"{tot_dwn:,}")
c3.metric("🚀 Lanzamientos (período)", f"{tot_lnc:,}")
c4.metric("📈 Conversión (Desc/Imp)", f"{conv:,.2f}%")

st.caption(
    f"**📅 Período:** {fmt_fecha_es(df['Fecha'].min())} – {fmt_fecha_es(df['Fecha'].max())}  |  "
    f"**Granularidad:** {gran}  |  **Uso por instalación (Lan/Desc):** {uso:,.2f}"
)

def variacion_pct(a,b):
    if b in (0, np.nan) or pd.isna(b): return np.nan
    return (a-b)/b*100.0

alertas=[]
if len(agg)>=2:
    a,p = agg.iloc[-1], agg.iloc[-2]
    for m in metricas_sel:
        if p[m]>0:
            ch = variacion_pct(a[m], p[m])
            if pd.notna(ch) and ch <= -umbral_alerta:
                alertas.append(f"🔴 **{m}** cayó **{ch:.1f}%** (últ. {gran.lower()}: {a['Etiqueta']} vs prev.: {p['Etiqueta']})")
if alertas: st.error(" \n".join(alertas))
else: st.success("✅ Sin alertas críticas en el período.")

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualización", "🧩 Por plataforma", "📄 Reporte (Excel)", "🖨️ Reporte PDF"])

with tab1:
    st.subheader(f"Evolución por {gran.lower()} – {', '.join(metricas_sel)}")
    if tipo_graf=="Líneas":
        fig = px.line(agg, x="Etiqueta", y=metricas_sel, markers=True)
    else:
        fig = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group")
    fig.update_layout(xaxis_title="", legend_title="", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("Segmentación por plataforma")
    met_seg = st.selectbox("Métrica para segmentar", metricas, index=1)
    plat_map = {"Impresiones": imp_plat, "Descargas": dwn_plat, "Lanzamientos": lnc_plat}
    dfp = plat_map.get(met_seg)
    if dfp is None:
