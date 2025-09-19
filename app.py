import io
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ReportLab (PDF pro)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, PageBreak)
from reportlab.lib.utils import ImageReader

# ============== Config básica ==============
st.set_page_config(page_title="Dashboard App Iglesia", page_icon="📊", layout="wide")

LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"
MESES_LARGO = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MESES_ABR   = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def fmt_fecha_es(ts, abr=True):
    if pd.isna(ts): return ""
    d = int(ts.day); m = int(ts.month); y = int(ts.year)
    mes = (MESES_ABR if abr else MESES_LARGO)[m-1]
    return f"{d:02d} {mes.capitalize()} {y}"

st.markdown(
    f"""<div style="text-align:center; margin-bottom:16px;">
          <img src="{LOGO_URL}" width="160" alt="Logo Iglesia">
        </div>""",
    unsafe_allow_html=True
)
st.title("📊 Dashboard App Iglesia")
st.caption("Analítica de impresiones, descargas y lanzamientos — filtros claros, exportación y reportes profesionales.")

# ============== Carga & normalización ==============
@st.cache_data
def leer_csv(path):
    return pd.read_csv(path, sep=None, engine="python")

def cargar_metricas(path, nombre_metrica):
    """Lee tus CSV (date, total, ios, android, …) y devuelve:
       - df_total con columnas: Fecha, <Métrica>, Año, MesNum, Semana, etiquetas
       - df_plat (opcional) con desglose por plataforma
    """
    raw = leer_csv(path)
    if "date" not in raw.columns or "total" not in raw.columns:
        st.error(f"{path} debe tener columnas 'date' y 'total'. Trae: {list(raw.columns)}"); st.stop()

    # Total
    df = raw.copy()
    df["Fecha"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["Fecha"])
    df = df.rename(columns={"total": nombre_metrica})
    df[nombre_metrica] = pd.to_numeric(df[nombre_metrica], errors="coerce").fillna(0)

    # Campos de tiempo
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

    # Plataformas (todas menos date y total)
    plat_cols = [c for c in raw.columns if c not in ["date", "total"]]
    df_plat = None
    if plat_cols:
        dfp = raw[["date"] + plat_cols].copy()
        dfp["Fecha"] = pd.to_datetime(dfp["date"], errors="coerce")
        dfp = dfp.dropna(subset=["Fecha"]).drop(columns=["date"])
        # nombres bonitos
        def pretty(c):
            m = {"ios":"iOS","android":"Android","apple_tv":"Apple TV","roku":"Roku","fire_tv":"Fire TV",
                 "google_tv":"Google TV","car_play":"CarPlay","android_auto":"Android Auto"}
            return m.get(c, c.replace("_"," ").title())
        dfp = dfp.rename(columns={c: pretty(c) for c in plat_cols})
        for c in dfp.columns:
            if c != "Fecha":
                dfp[c] = pd.to_numeric(dfp[c], errors="coerce").fillna(0)
        df_plat = dfp

    return df_total, df_plat

# ============== Filtros de fecha inteligentes ==============
def rango_por_atajo(opcion, hoy, mes_especifico=None, anio_especifico=None, hasta_hoy=True):
    if opcion == "Últimos 7 días":
        return hoy - pd.Timedelta(days=6), hoy
    if opcion == "Últimos 30 días":
        return hoy - pd.Timedelta(days=29), hoy
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

# ============== Cargar datos (repo o uploader) ==============
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

# DF maestro
df = (imp_tot.merge(dwn_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
             .merge(lnc_tot, on=["Fecha","Año","MesNum","Semana","Etiqueta_dia","Etiqueta_mes","Etiqueta_año","Etiqueta_sem"], how="outer")
             .fillna(0).sort_values("Fecha"))

# Asegurar numéricos
for c in ["Impresiones","Descargas","Lanzamientos"]:
    df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

if df.empty:
    st.warning("No hay datos."); st.stop()

# ============== Filtros (atajos + mes específico) ==============
st.sidebar.header("Filtros")
hoy = pd.to_datetime("today").normalize()
atajo = st.sidebar.selectbox("Atajo de fechas",
    ["Últimos 30 días","Últimos 7 días","Este mes","Mes pasado","Este año","Año pasado","Mes específico…"], index=2)

mes_espec = None; anio_espec = None; hasta_hoy = True
if atajo == "Mes específico…":
    colm, coly = st.sidebar.columns(2)
    mes_espec  = colm.selectbox("Mes", list(range(1,13)), format_func=lambda m: MESES_LARGO[m-1], index=max(0, hoy.month-1))
    anio_espec = coly.number_input("Año", value=int(hoy.year), step=1)
    hasta_hoy  = st.sidebar.checkbox("Hasta hoy (si es el mes actual)", value=True)

ini_r, fin_r = rango_por_atajo(atajo, hoy, mes_espec, anio_espec, hasta_hoy)
if ini_r is None:
    ini_r = max(df["Fecha"].max() - pd.DateOffset(months=12), df["Fecha"].min())
    fin_r = df["Fecha"].max()

ini_r, fin_r = st.sidebar.date_input("Rango (puedes ajustar)", value=(ini_r.date(), fin_r.date()))
ini_ts, fin_ts = pd.to_datetime(ini_r), pd.to_datetime(fin_r)
df = df[(df["Fecha"] >= ini_ts) & (df["Fecha"] <= fin_ts)]
if df.empty:
    st.warning("No hay datos en el rango seleccionado."); st.stop()

gran = st.sidebar.radio("Granularidad", ["Día","Semana","Mes","Año"])
metricas = ["Impresiones","Descargas","Lanzamientos"]
metricas_sel = st.sidebar.multiselect("Métricas", metricas, default=metricas)
tipo_graf = st.sidebar.radio("Tipo de gráfico", ["Líneas","Barras"], horizontal=True)
umbral_alerta = st.sidebar.slider("Alerta si baja más de (%) vs período anterior", 5, 80, 20)

# ============== Agregación ==============
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

# ============== KPIs & alertas ==============
c1,c2,c3,c4 = st.columns(4)
tot_imp = int(df["Impresiones"].sum()); tot_dwn = int(df["Descargas"].sum()); tot_lnc = int(df["Lanzamientos"].sum())
conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0
c1.metric("👀 Impresiones (período)", f"{tot_imp:,}")
c2.metric("⬇️ Descargas (período)",  f"{tot_dwn:,}")
c3.metric("🚀 Lanzamientos (período)", f"{tot_lnc:,}")
c4.metric("📈 Conversión (Desc/Imp)", f"{conv:,.2f}%")
st.caption(f"**📅 Período:** {fmt_fecha_es(df['Fecha'].min())} – {fmt_fecha_es(df['Fecha'].max())}  |  **Granularidad:** {gran}  |  **Uso por instalación:** {uso:,.2f}")

def variacion_pct(a,b):
    if b in (0,np.nan) or pd.isna(b): return np.nan
    return (a-b)/b*100.0

alertas=[]
if len(agg)>=2:
    a,p = agg.iloc[-1], agg.iloc[-2]
    for m in metricas_sel:
        if p[m]>0:
            ch = variacion_pct(a[m], p[m])
            if ch==ch and ch<=-umbral_alerta:
                alertas.append(f"🔴 **{m}** cayó **{ch:.1f}%** (últ. {gran.lower()}: {a['Etiqueta']} vs prev.: {p['Etiqueta']})")
if alertas: st.error(" \n".join(alertas))
else: st.success("✅ Sin alertas críticas en el período.")

# ============== Tabs ==============
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
        st.info("Tus CSV no traen columnas por plataforma.")
    else:
        # Alinear al rango y granularidad
        dfp = dfp.merge(df[["Fecha"]], on="Fecha", how="inner")
        dfp["Año"] = dfp["Fecha"].dt.year; dfp["MesNum"]=dfp["Fecha"].dt.month; dfp["Semana"]=dfp["Fecha"].dt.isocalendar().week.astype(int)
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
        fig_stack = px.bar(agg_plat, x="Etiqueta", y=num_cols, barmode="stack", title=f"{met_seg} por {gran.lower()} (apilado)")
        fig_stack.update_layout(xaxis_title="", legend_title="")
        st.plotly_chart(fig_stack, use_container_width=True)
        if len(agg_plat)>0:
            ultimo = agg_plat.iloc[-1][num_cols]
            st.plotly_chart(px.pie(values=ultimo.values, names=ultimo.index, title="Participación (último período)"),
                            use_container_width=True)

with tab3:
    st.subheader("Descargar datos agregados")
    periodo = st.selectbox("Periodo de tabla", ["Diario","Semanal","Mensual"])
    tabla = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo], metricas)
    st.dataframe(tabla, use_container_width=True)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        tabla.to_excel(writer, index=False, sheet_name="Datos")
    st.download_button("📥 Descargar Excel", data=out.getvalue(),
                       file_name=f"datos_{periodo.lower()}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ===== PDF profesional (kaleido + reportlab) =====
def plot_to_png(fig, w=1100, h=500, scale=2):
    return fig.to_image(format="png", width=w, height=h, scale=scale)

def build_pdf(logo_url, titulo, subtitulo, kpis, figuras_png, tabla_df):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    W, H = A4
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="h1", parent=styles["Heading1"], alignment=1, fontSize=18, spaceAfter=12))
    styles.add(ParagraphStyle(name="h2", parent=styles["Heading2"], alignment=1, fontSize=11, textColor=colors.grey, spaceAfter=12))
    styles.add(ParagraphStyle(name="kpi", parent=styles["Normal"], alignment=1, fontSize=12))

    story = []
    # Portada
    try:
        logo_bytes = requests.get(logo_url, timeout=10).content
        story.append(Spacer(1, 0.3*cm))
        story.append(Image(io.BytesIO(logo_bytes), width=4*cm, height=3*cm))
    except Exception:
        story.append(Spacer(1, 3.5*cm))
    story.append(Paragraph(titulo, styles["h1"]))
    story.append(Paragraph(subtitulo, styles["h2"]))
    story.append(Spacer(1, 0.4*cm))

    # KPIs
    data_kpi = [
        [Paragraph("👀 Impresiones",styles["kpi"]), Paragraph(f"{kpis['imp']:,}",styles["kpi"])],
        [Paragraph("⬇️ Descargas", styles["kpi"]), Paragraph(f"{kpis['dwn']:,}",styles["kpi"])],
        [Paragraph("🚀 Lanzamientos",styles["kpi"]), Paragraph(f"{kpis['lnc']:,}",styles["kpi"])],
        [Paragraph("📈 Conversión", styles["kpi"]), Paragraph(f"{kpis['conv']:,.2f}%",styles["kpi"])],
        [Paragraph("🧭 Uso por instalación",styles["kpi"]), Paragraph(f"{kpis['uso']:,.2f}",styles["kpi"])],
    ]
    kpi_tbl = Table(data_kpi, colWidths=[7*cm, 7*cm])
    kpi_tbl.setStyle(TableStyle([
        ('BOX',(0,0),(-1,-1), 0.5, colors.grey),
        ('INNERGRID',(0,0),(-1,-1), 0.25, colors.lightgrey),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('FONT',(0,0),(-1,-1),'Helvetica'),
        ('BACKGROUND',(0,0),(-1,0), colors.whitesmoke)
    ]))
    story.append(kpi_tbl); story.append(PageBreak())

    # Gráficos (1 por página)
    for png in figuras_png:
        story.append(Image(io.BytesIO(png), width=W-3*cm, height=H-5*cm))
        story.append(PageBreak())

    # Tabla
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

    # Pie de página con numeración
    def on_page(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(W-1.2*cm, 1*cm, f"Página {doc.page}")

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()

with tab4:
    st.subheader("Generar Reporte PDF profesional")
    periodo_pdf = st.selectbox("Periodo de tabla PDF", ["Diario","Semanal","Mensual"])
    tabla_pdf = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo_pdf], metricas)

    # Gráficos para el PDF
    if tipo_graf=="Líneas":
        fig1 = px.line(agg, x="Etiqueta", y=metricas_sel, markers=True, title=f"Evolución por {gran.lower()}")
    else:
        fig1 = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title=f"Evolución por {gran.lower()}")
    fig1.update_layout(xaxis_title="", legend_title="")

    fig2 = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title="Comparativa")
    fig2.update_layout(xaxis_title="", legend_title="")

    pngs = [plot_to_png(fig1), plot_to_png(fig2)]

    kpis = {"imp": tot_imp, "dwn": tot_dwn, "lnc": tot_lnc, "conv": conv, "uso": uso}
    subtitulo = f"Rango: {fmt_fecha_es(df['Fecha'].min())} a {fmt_fecha_es(df['Fecha'].max())}  •  Granularidad: {gran}"

    if st.button("🖨️ Generar PDF"):
        pdf_bytes = build_pdf(LOGO_URL, "Dashboard App Iglesia – Reporte", subtitulo, kpis, pngs, tabla_pdf)
        st.download_button("📥 Descargar PDF", data=pdf_bytes,
                           file_name=f"reporte_{periodo_pdf.lower()}.pdf", mime="application/pdf")
