# app.py
import io
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ReportLab (PDF)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak)

# =========================
# Configuración general
# =========================
st.set_page_config(page_title="Dashboard Evolucion de APP Heaven", page_icon="📊", layout="wide")

# Logo e imagen del repo (usaremos la misma para portada e imagen destacada de PDF)
LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"

MESES_LARGO = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MESES_ABR   = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def fmt_fecha_es(ts, abr=True):
    if pd.isna(ts): return ""
    d = int(ts.day); m = int(ts.month); y = int(ts.year)
    mes = (MESES_ABR if abr else MESES_LARGO)[m-1]
    return f"{d:02d} {mes.capitalize()} {y}"

st.markdown("<h1 style='text-align:center'>📊 Dashboard Evolucion de APP Heaven</h1>", unsafe_allow_html=True)
st.markdown(f"<div style='text-align:center;margin-bottom:6px'><img src='{LOGO_URL}' width='120' /></div>", unsafe_allow_html=True)
st.caption("Monitoreo de Impresiones, Descargas y Lanzamientos con comparativos vs. período anterior y YoY.")
st.divider()

# =========================
# Carga y normalización
# =========================
@st.cache_data
def leer_csv(path):
    return pd.read_csv(path, sep=None, engine="python")

def cargar_metricas(path_or_buffer, nombre_metrica):
    raw = leer_csv(path_or_buffer)
    cols_lower = {c.lower(): c for c in raw.columns}
    if "date" not in cols_lower or "total" not in cols_lower:
        st.error(f"El archivo debe tener columnas 'date' y 'total'. Trae: {list(raw.columns)}")
        st.stop()

    df = raw.rename(columns={cols_lower["date"]: "Fecha", cols_lower["total"]: nombre_metrica}).copy()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])
    df[nombre_metrica] = pd.to_numeric(df[nombre_metrica], errors="coerce").fillna(0)

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

    df_total = df[["Fecha", nombre_metrica, "Año","MesNum","Semana",
                   "Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"]]

    # Plataformas opcionales
    plat_cols = [c for c in raw.columns if c not in [cols_lower["date"], cols_lower["total"]]]
    df_plat = None
    if plat_cols:
        dfp = raw[[cols_lower["date"]] + plat_cols].copy()
        dfp["Fecha"] = pd.to_datetime(dfp[cols_lower["date"]], errors="coerce")
        dfp = dfp.dropna(subset=["Fecha"]).drop(columns=[cols_lower["date"]])
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
# Origen de datos
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

df_all = (imp_tot.merge(dwn_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
                 .merge(lnc_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
                 .fillna(0).sort_values("Fecha"))
for c in ["Impresiones","Descargas","Lanzamientos"]:
    df_all[c] = pd.to_numeric(df_all[c], errors="coerce").fillna(0)
if df_all.empty:
    st.warning("No hay datos."); st.stop()

data_min = df_all["Fecha"].min().date()
data_max = df_all["Fecha"].max().date()
st.info(f"📅 Datos disponibles: **{data_min}** → **{data_max}**")

# =========================
# Filtros superiores (rango inteligente)
# =========================
hoy = pd.Timestamp(data_max)

col_gran, col_anio, col_mes, col_sem, col_dia = st.columns([1.2, 1, 1, 1, 1.3], vertical_alignment="bottom")
with col_gran:
    gran = st.radio("Granularidad", ["Día","Semana","Mes","Año"], horizontal=True)
with col_anio:
    años = sorted(df_all["Año"].unique())
    anio_sel = st.selectbox("Año", años, index=len(años)-1)
with col_mes:
    mes_opc = ["Todos"] + MESES_LARGO
    mes_sel = st.selectbox("Mes", mes_opc, index=0)
with col_sem:
    sem_disp = sorted(df_all[df_all["Año"]==anio_sel]["Semana"].unique())
    sem_sel = st.selectbox("Semana (opcional)", ["Todas"] + list(map(int, sem_disp)), index=0)
with col_dia:
    dias_anio = df_all[df_all["Año"]==anio_sel]["Fecha"].dt.date.unique()
    dia_sel = st.selectbox("Día (opcional)", ["Ninguno"] + sorted(map(str, dias_anio)), index=0)

# Sidebar: modo guía y comparación YoY
st.sidebar.markdown("---")
modo_guia = st.sidebar.toggle("🧭 Modo guía", value=False, help="Muestra consejos y explicación paso a paso.")
cmp_yoy   = st.sidebar.toggle("📊 Comparar YoY (mismo período año anterior)", value=False)

# Rango INTELIGENTE (prioridad: Día > Semana > Mes > Año)
if dia_sel != "Ninguno":
    ini_r = fin_r = pd.to_datetime(dia_sel).date()
elif sem_sel != "Todas":
    sem_ini = pd.to_datetime(f"{anio_sel}-W{int(sem_sel):02d}-1")
    sem_fin = sem_ini + pd.Timedelta(days=6)
    ini_r, fin_r = sem_ini.date(), sem_fin.date()
elif mes_sel != "Todos":
    mes_num = MESES_LARGO.index(mes_sel) + 1
    ini_r = pd.Timestamp(anio_sel, mes_num, 1).date()
    fin_r = (pd.Timestamp(anio_sel, mes_num, 1) + pd.offsets.MonthEnd(1)).date()
else:
    ini_r = pd.Timestamp(anio_sel, 1, 1).date()
    fin_r = pd.Timestamp(anio_sel, 12, 31).date()

# Limitar al rango real de datos
ini_r = max(ini_r, data_min)
fin_r = min(fin_r, data_max)
st.caption(f"**Rango de fechas:** {ini_r} – {fin_r}")

df = df_all[(df_all["Fecha"] >= pd.to_datetime(ini_r)) & (df_all["Fecha"] <= pd.to_datetime(fin_r))]
if df.empty:
    st.warning("No hay datos en el rango seleccionado."); st.stop()

# =========================
# Glosario simple
# =========================
with st.expander("ℹ️ ¿Qué significan estas métricas?"):
    st.markdown("""
**👀 Impresiones**: Veces que la app fue mostrada (tienda o notificaciones).  
**📥 Descargas**: Instalaciones de la app.  
**🚀 Lanzamientos**: Aperturas de la app por los usuarios.  
**📈 Conversión**: Descargas ÷ Impresiones × 100.  
**🧭 Uso por instalación**: Lanzamientos ÷ Descargas (aperturas promedio por instalación).
""")

# =========================
# Agregación
# =========================
def agregar(df_local, nivel, cols):
    if nivel == "Día":
        by, lab = ["Año","MesNum","Fecha","Etiqueta_dia"], "Etiqueta_dia"
    elif nivel == "Semana":
        by, lab = ["Año","Semana","Etiqueta_sem"], "Etiqueta_sem"
    elif nivel == "Mes":
        by, lab = ["Año","MesNum","Etiqueta_mes"], "Etiqueta_mes"
    else:
        by, lab = ["Año","Etiqueta_año"], "Etiqueta_año"
    g = df_local.groupby(by, dropna=False)[cols].sum().reset_index().rename(columns={lab:"Etiqueta"})
    g = g.sort_values([c for c in ["Año","MesNum","Semana","Fecha"] if c in g.columns])
    g["Etiqueta"] = g["Etiqueta"].astype(str)
    return g

metricas = ["Impresiones","Descargas","Lanzamientos"]
agg = agregar(df, gran, metricas)

# =========================
# Helpers comparativas
# =========================
def periodo_anterior(ini: pd.Timestamp, fin: pd.Timestamp, gran: str):
    if gran == "Año":
        return pd.Timestamp(ini.year-1, 1, 1), pd.Timestamp(ini.year-1, 12, 31)
    if gran == "Mes":
        ini_prev = (pd.Timestamp(ini.year, ini.month, 1) - pd.offsets.MonthBegin(1))
        fin_prev = ini_prev + pd.offsets.MonthEnd(1)
        return ini_prev, fin_prev
    if gran == "Semana":
        dur = fin - ini
        return ini - pd.Timedelta(weeks=1), (ini - pd.Timedelta(weeks=1)) + dur
    dur = fin - ini
    return ini - dur - pd.Timedelta(days=1), fin - dur - pd.Timedelta(days=1)

def periodo_yoy(ini: pd.Timestamp, fin: pd.Timestamp):
    return pd.Timestamp(ini.year-1, ini.month, ini.day), pd.Timestamp(fin.year-1, fin.month, fin.day)

def pct(a,b):
    if b in (0, np.nan) or pd.isna(b): return np.nan
    return (a - b) / b * 100.0

def sumar_rango(df_base, ini, fin):
    d = df_base[(df_base["Fecha"]>=pd.to_datetime(ini)) & (df_base["Fecha"]<=pd.to_datetime(fin))]
    if d.empty: 
        return {"Impresiones":0, "Descargas":0, "Lanzamientos":0}, np.nan, np.nan
    imp = int(d["Impresiones"].sum()); dwn = int(d["Descargas"].sum()); lnc = int(d["Lanzamientos"].sum())
    conv = (dwn/imp*100) if imp>0 else np.nan
    uso  = (lnc/dwn) if dwn>0 else np.nan
    return {"Impresiones":imp, "Descargas":dwn, "Lanzamientos":lnc}, conv, uso

# Período actual
tot_imp = int(df["Impresiones"].sum())
tot_dwn = int(df["Descargas"].sum())
tot_lnc = int(df["Lanzamientos"].sum())
conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0

# Período anterior
ini_prev, fin_prev = periodo_anterior(pd.to_datetime(ini_r), pd.to_datetime(fin_r), gran)
ini_prev = max(ini_prev.date(), data_min); fin_prev = min(fin_prev.date(), data_max)
sum_prev, conv_prev, uso_prev = sumar_rango(df_all, ini_prev, fin_prev)

delta_imp = pct(tot_imp, sum_prev["Impresiones"])
delta_dwn = pct(tot_dwn, sum_prev["Descargas"])
delta_lnc = pct(tot_lnc, sum_prev["Lanzamientos"])
delta_conv = pct(conv, conv_prev) if pd.notna(conv_prev) else np.nan
delta_uso  = pct(uso,  uso_prev)  if pd.notna(uso_prev)  else np.nan

# Período YoY (opcional) — armado general para PDF
yoy_block = None
if cmp_yoy:
    ini_yoy, fin_yoy = periodo_yoy(pd.to_datetime(ini_r), pd.to_datetime(fin_r))
    ini_yoy = max(ini_yoy.date(), data_min); fin_yoy = min(fin_yoy.date(), data_max)
    sum_yoy, conv_yoy, uso_yoy = sumar_rango(df_all, ini_yoy, fin_yoy)

    delta_imp_yoy = pct(tot_imp, sum_yoy["Impresiones"])
    delta_dwn_yoy = pct(tot_dwn, sum_yoy["Descargas"])
    delta_lnc_yoy = pct(tot_lnc, sum_yoy["Lanzamientos"])
    delta_conv_yoy = pct(conv, conv_yoy) if pd.notna(conv_yoy) else np.nan
    delta_uso_yoy  = pct(uso,  uso_yoy)  if pd.notna(uso_yoy)  else np.nan

    yoy_block = {
        "RangoYoY": (ini_yoy, fin_yoy),
        "Filas": [
            ("Impresiones",        tot_imp, sum_yoy["Impresiones"], delta_imp_yoy),
            ("Descargas",          tot_dwn, sum_yoy["Descargas"],   delta_dwn_yoy),
            ("Lanzamientos",       tot_lnc, sum_yoy["Lanzamientos"],delta_lnc_yoy),
            ("Conversión (%)",     conv,    conv_yoy if pd.notna(conv_yoy) else 0, delta_conv_yoy),
            ("Uso/instalación",    uso,     uso_yoy if pd.notna(uso_yoy) else 0,   delta_uso_yoy),
        ]
    }

# =========================
# KPIs + resumen
# =========================
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("👀 Impresiones (período)", f"{tot_imp:,}", delta=f"{delta_imp:+.1f}%" if pd.notna(delta_imp) else "–", help="Oportunidades de instalación")
c2.metric("📥 Descargas (período)",  f"{tot_dwn:,}", delta=f"{delta_dwn:+.1f}%" if pd.notna(delta_dwn) else "–", help="Instalaciones")
c3.metric("🚀 Lanzamientos (per.)",  f"{tot_lnc:,}", delta=f"{delta_lnc:+.1f}%" if pd.notna(delta_lnc) else "–", help="Aperturas de app")
c4.metric("📈 Conversión",           f"{conv:,.2f}%", delta=f"{delta_conv:+.1f}%" if pd.notna(delta_conv) else "–", help="Descargas ÷ Impresiones × 100")
c5.metric("🧭 Uso por instalación",  f"{uso:,.2f}",  delta=f"{delta_uso:+.1f}%"  if pd.notna(delta_uso)  else "–", help="Lanzamientos ÷ Descargas")

def chip(valor):
    if pd.isna(valor): return "—"
    return ("🟢 +" if valor >= 0 else "🔴 ") + f"{valor:.1f}%"

resumen = (
    f"**Resumen:** Impresiones {chip(delta_imp)}, Descargas {chip(delta_dwn)}, "
    f"Lanzamientos {chip(delta_lnc)}, Conversión {chip(delta_conv)}, Uso/instalación {chip(delta_uso)} "
    f"vs. período anterior ({fmt_fecha_es(pd.to_datetime(ini_prev))} – {fmt_fecha_es(pd.to_datetime(fin_prev))})."
)
if cmp_yoy:
    ini_yoy, fin_yoy = yoy_block["RangoYoY"]
    # extraemos del bloque para describir
    di = yoy_block["Filas"][0][3]; dd = yoy_block["Filas"][1][3]; dl = yoy_block["Filas"][2][3]
    dc = yoy_block["Filas"][3][3]; du = yoy_block["Filas"][4][3]
    resumen += (
        f"  |  **YoY:** Imp {chip(di)}, Desc {chip(dd)}, Lanz {chip(dl)}, "
        f"Conv {chip(dc)}, Uso {chip(du)} vs. {fmt_fecha_es(pd.to_datetime(ini_yoy))} – {fmt_fecha_es(pd.to_datetime(fin_yoy))}."
    )
st.info(resumen)

st.caption(
    f"**Período:** {fmt_fecha_es(df['Fecha'].min())} – {fmt_fecha_es(df['Fecha'].max())} | "
    f"**Granularidad:** {gran}"
)

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualización", "🧩 Por plataforma", "📄 Reporte (Excel)", "🖨️ Reporte PDF"])

with tab1:
    st.subheader(f"Evolución por {gran.lower()}")
    if gran in ["Día","Semana"]:
        fig = px.line(agg, x="Etiqueta", y=metricas, markers=True)
    else:
        fig = px.bar(agg, x="Etiqueta", y=metricas, barmode="group")
    fig.update_xaxes(type="category")
    fig.update_layout(xaxis_title="", legend_title="", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    if modo_guia:
        with st.expander("Cómo leer este gráfico"):
            st.markdown(f"""
- El eje **X** muestra períodos por **{gran.lower()}** (cámbialo arriba).
- Las series comparan **Impresiones**, **Descargas** y **Lanzamientos**.
- Revisa los **KPIs**: variación vs. período anterior y (si activas) **YoY**.
- Para ver un mes o semana específica, usa los selectores de arriba.
""")
        st.success("Consejo: en **Por plataforma** ves si el cambio viene de iOS, Android u otra plataforma.")

with tab2:
    st.subheader("Segmentación por plataforma")
    met_seg = st.selectbox("Métrica para segmentar", metricas, index=1)
    plat_map = {"Impresiones": imp_plat, "Descargas": dwn_plat, "Lanzamientos": lnc_plat}
    dfp = plat_map.get(met_seg)
    if dfp is None:
        st.info("Tus CSV no traen columnas por plataforma.")
    else:
        dfp = dfp.merge(df[["Fecha"]], on="Fecha", how="inner")
        dfp["Año"]=dfp["Fecha"].dt.year; dfp["MesNum"]=dfp["Fecha"].dt.month
        dfp["Semana"]=dfp["Fecha"].dt.isocalendar().week.astype(int)
        dfp["Sem_ini"]=dfp["Fecha"]-pd.to_timedelta(dfp["Fecha"].dt.weekday, unit="D")
        dfp["Sem_fin"]=dfp["Sem_ini"]+pd.Timedelta(days=6)
        dfp["Etiqueta_dia"]=dfp["Fecha"].apply(lambda x: fmt_fecha_es(x, True))
        dfp["Etiqueta_mes"]=dfp["MesNum"].map(lambda m: MESES_LARGO[m-1])+" "+dfp["Año"].astype(str)
        dfp["Etiqueta_año"]=dfp["Año"].astype(str)
        dfp["Etiqueta_sem"]=("Sem "+dfp["Semana"].astype(str)+" ("+
                             dfp["Sem_ini"].apply(lambda x: fmt_fecha_es(x, True))+" – "+
                             dfp["Sem_fin"].apply(lambda x: fmt_fecha_es(x, True))+")")
        by_map={"Día":["Año","MesNum","Fecha","Etiqueta_dia"],"Semana":["Año","Semana","Etiqueta_sem"],
                "Mes":["Año","MesNum","Etiqueta_mes"],"Año":["Año","Etiqueta_año"]}
        etiqueta = by_map[gran][-1]
        agg_plat = dfp.groupby(by_map[gran], dropna=False).sum(numeric_only=True).reset_index().rename(columns={etiqueta:"Etiqueta"})
        num_cols = [c for c in agg_plat.columns if c not in by_map[gran]+["Etiqueta","Sem_ini","Sem_fin","Fecha","MesNum","Año","Semana"]]
        agg_plat = agg_plat.sort_values([c for c in ["Año","MesNum","Semana","Fecha"] if c in agg_plat.columns])
        agg_plat["Etiqueta"]=agg_plat["Etiqueta"].astype(str)

        fig_stack = px.bar(agg_plat, x="Etiqueta", y=num_cols, barmode="stack", title=f"{met_seg} por {gran.lower()} (apilado)")
        fig_stack.update_xaxes(type="category")
        fig_stack.update_layout(xaxis_title="", legend_title="")
        st.plotly_chart(fig_stack, use_container_width=True)

        if len(agg_plat)>0:
            ultimo = agg_plat.iloc[-1][num_cols]
            st.plotly_chart(px.pie(values=ultimo.values, names=ultimo.index, title="Participación (último período)"),
                            use_container_width=True)

with tab3:
    st.subheader("Descargar datos agregados")
    periodo = st.selectbox("Periodo de tabla", ["Diario","Semanal","Mensual","Anual"])
    def agregar_tabla(df_local, p):
        mapa = {"Diario":"Día", "Semanal":"Semana", "Mensual":"Mes", "Anual":"Año"}
        t = agregar(df_local, mapa[p], metricas); t["Etiqueta"]=t["Etiqueta"].astype(str); return t
    tabla = agregar_tabla(df, periodo)
    st.dataframe(tabla, use_container_width=True)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        tabla.to_excel(writer, index=False, sheet_name="Datos")
    st.download_button("📥 Descargar Excel", data=out.getvalue(),
                       file_name=f"datos_{periodo.lower()}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# =========================
# PDF profesional (incluye imagen del repo y tabla YoY)
# =========================
def build_pdf(logo_url, titulo, subtitulo, kpis, figuras_png, tabla_df, extra_image_bytes=None, yoy_block=None):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    W, H = A4
    styles = getSampleStyleSheet()
    if "TituloReporte" not in styles.byName:
        styles.add(ParagraphStyle(name="TituloReporte", parent=styles["Heading1"], alignment=1, fontSize=18, spaceAfter=12))
    if "SubtituloReporte" not in styles.byName:
        styles.add(ParagraphStyle(name="SubtituloReporte", parent=styles["Heading2"], alignment=1, fontSize=11, textColor=colors.grey, spaceAfter=12))
    if "KPITexto" not in styles.byName:
        styles.add(ParagraphStyle(name="KPITexto", parent=styles["Normal"], alignment=1, fontSize=12))

    story=[]
    # Portada con logo
    try:
        logo_bytes = requests.get(logo_url, timeout=10).content
        story.append(Spacer(1, 0.3*cm))
        story.append(Image(io.BytesIO(logo_bytes), width=4*cm, height=3*cm))
    except Exception:
        story.append(Spacer(1, 3.5*cm))
    story.append(Paragraph(titulo, styles["TituloReporte"]))
    story.append(Paragraph(subtitulo, styles["SubtituloReporte"]))
    story.append(Spacer(1, 0.4*cm))

    # Imagen destacada (usaremos la del repo si no se provee otra)
    if extra_image_bytes:
        story.append(Paragraph("Imagen destacada", styles["Heading2"]))
        story.append(Image(io.BytesIO(extra_image_bytes), width=W-3*cm, height=H/2))
        story.append(PageBreak())

    # Descripción de métricas
    story.append(Paragraph("Descripción de métricas", styles["Heading2"]))
    for d in [
        "📊 Impresiones: veces que la app fue mostrada (alcance).",
        "📥 Descargas: instalaciones de la app.",
        "🚀 Lanzamientos: aperturas de la app.",
        "📈 Conversión: Descargas ÷ Impresiones.",
        "🧭 Uso por instalación: Lanzamientos ÷ Descargas."
    ]:
        story.append(Paragraph(d, styles["Normal"]))
    story.append(Spacer(1, 0.4*cm))

    # KPIs
    data_kpi = [
        [Paragraph("👀 Impresiones",styles["KPITexto"]), Paragraph(f"{kpis['imp']:,}",styles["KPITexto"])],
        [Paragraph("📥 Descargas", styles["KPITexto"]), Paragraph(f"{kpis['dwn']:,}",styles["KPITexto"])],
        [Paragraph("🚀 Lanzamientos",styles["KPITexto"]), Paragraph(f"{kpis['lnc']:,}",styles["KPITexto"])],
        [Paragraph("📈 Conversión", styles["KPITexto"]), Paragraph(f"{kpis['conv']:,.2f}%",styles["KPITexto"])],
        [Paragraph("🧭 Uso por instalación",styles["KPITexto"]), Paragraph(f"{kpis['uso']:,.2f}",styles["KPITexto"])],
    ]
    kpi_tbl = Table(data_kpi, colWidths=[7*cm, 7*cm])
    kpi_tbl.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1), 0.5, colors.grey),
        ('INNERGRID',(0,0),(-1,-1), 0.25, colors.lightgrey),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
    ]))
    story.append(kpi_tbl); story.append(PageBreak())

    # Gráficos
    for png in figuras_png:
        story.append(Image(io.BytesIO(png), width=W-3*cm, height=H-5*cm))
        story.append(PageBreak())

    # Tabla YoY (si aplica)
    if yoy_block:
        ini_y, fin_y = yoy_block["RangoYoY"]
        story.append(Paragraph(
            f"Comparativo YoY (mismo período del año anterior): "
            f"{fmt_fecha_es(pd.to_datetime(ini_y))} – {fmt_fecha_es(pd.to_datetime(fin_y))}",
            styles["Heading2"])
        )
        filas = [["Métrica", "Actual", "YoY", "Δ%"]]
        for nombre, actual, yoy, delta in yoy_block["Filas"]:
            filas.append([nombre,
                          f"{actual:,.2f}" if isinstance(actual, float) else f"{actual:,}",
                          f"{yoy:,.2f}"    if isinstance(yoy, float)    else f"{yoy:,}",
                          f"{delta:+.1f}%" if pd.notna(delta) else "–"])
        tbl_yoy = Table(filas, repeatRows=1, colWidths=[6*cm, 3*cm, 3*cm, 3*cm])
        tbl_yoy.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0), colors.Color(0.12,0.12,0.12)),
            ('TEXTCOLOR',(0,0),(-1,0), colors.white),
            ('GRID',(0,0),(-1,-1), 0.25, colors.lightgrey),
            ('ALIGN',(1,1),(-1,-1),'CENTER'),
            ('FONT',(0,0),(-1,0),'Helvetica-Bold'),
        ]))
        story.append(tbl_yoy)
        story.append(PageBreak())

    # Tabla de datos (primeros 30)
    story.append(Paragraph("Datos agregados (primeros 30 registros)", styles["Heading2"]))
    head = list(tabla_df.columns)
    rows = [head] + tabla_df.head(30).astype(str).values.tolist()
    tbl = Table(rows, repeatRows=1)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.Color(0.12,0.12,0.12)),
        ('TEXTCOLOR',(0,0),(-1,0), colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1), 0.25, colors.lightgrey),
        ('FONT',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONT',(0,1),(-1,-1),'Helvetica'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.whitesmoke, colors.lightgrey]),
    ]))
    story.append(tbl)

    def on_page(canvas, doc):
        W,H = A4
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(W-1.2*cm, 1*cm, f"Página {doc.page}")

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()

with tab4:
    st.subheader("Generar Reporte PDF profesional")
    periodo_pdf = st.selectbox("Periodo de tabla PDF", ["Diario","Semanal","Mensual","Anual"])

    def tabla_por_periodo(df_local, p):
        mapa = {"Diario":"Día","Semanal":"Semana","Mensual":"Mes","Anual":"Año"}
        t = agregar(df_local, mapa[p], metricas); t["Etiqueta"]=t["Etiqueta"].astype(str); return t

    tabla_pdf = tabla_por_periodo(df, periodo_pdf)

    # Figuras base (evolución del período actual)
    if gran in ["Día","Semana"]:
        fig1 = px.line(agg, x="Etiqueta", y=metricas, markers=True, title=f"Evolución por {gran.lower()}")
    else:
        fig1 = px.bar(agg, x="Etiqueta", y=metricas, barmode="group", title=f"Evolución por {gran.lower()}")
    fig1.update_xaxes(type="category"); fig1.update_layout(xaxis_title="", legend_title="")

    # Gráficos YoY por métrica (si está activo)
    figs_yoy = []
    if cmp_yoy:
        ini_yoy, fin_yoy = periodo_yoy(pd.to_datetime(ini_r), pd.to_datetime(fin_r))
        df_yoy = df_all[(df_all["Fecha"]>=pd.to_datetime(ini_yoy))&(df_all["Fecha"]<=pd.to_datetime(fin_yoy))]
        agg_yoy = agregar(df_yoy, gran, metricas)

        for m in metricas:
            comb = pd.DataFrame({"Etiqueta": agg["Etiqueta"], "Actual": agg[m]})
            if len(agg_yoy) == len(agg):
                comb["YoY"] = agg_yoy[m].values
            else:
                comb["YoY"] = np.nan
            figm = px.bar(comb, x="Etiqueta", y=["Actual","YoY"], barmode="group", title=f"Comparativo YoY • {m}")
            figm.update_xaxes(type="category"); figm.update_layout(xaxis_title="", legend_title="")
            figs_yoy.append(figm)
    else:
        fig2 = px.bar(agg, x="Etiqueta", y=metricas, barmode="group", title="Comparativa")
        fig2.update_xaxes(type="category"); fig2.update_layout(xaxis_title="", legend_title="")

    # Exportar figuras a PNG (kaleido)
    def plot_to_png(fig, w=1100, h=500, scale=2): 
        return fig.to_image(format="png", width=w, height=h, scale=scale)

    pngs = [plot_to_png(fig1)]
    if cmp_yoy:
        pngs.extend([plot_to_png(f) for f in figs_yoy])  # un gráfico por métrica
    else:
        pngs.append(plot_to_png(fig2))

    # Imagen destacada: usamos la MISMA del repo por defecto
    try:
        extra_image_bytes = requests.get(LOGO_URL, timeout=10).content
    except Exception:
        extra_image_bytes = None

    kpis = {"imp": tot_imp, "dwn": tot_dwn, "lnc": tot_lnc, "conv": conv, "uso": uso}
    subtitulo = f"Rango: {fmt_fecha_es(df['Fecha'].min())} a {fmt_fecha_es(df['Fecha'].max())} • Granularidad: {gran}"

    if st.button("🖨️ Generar PDF"):
        pdf_bytes = build_pdf(
            LOGO_URL,
            "📊 Dashboard Evolucion de APP Heaven",
            subtitulo,
            kpis,
            pngs,
            tabla_pdf,
            extra_image_bytes=extra_image_bytes,  # <- imagen del repo
            yoy_block=yoy_block                    # <- tabla YoY
        )
        st.download_button("📥 Descargar PDF", data=pdf_bytes,
                           file_name=f"reporte_{periodo_pdf.lower()}.pdf", mime="application/pdf")
