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

# =========================
# Configuración base
# =========================
st.set_page_config(page_title="Dashboard Evolucion de APP Heaven", page_icon="📊", layout="wide")

LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"

MESES_LARGO = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MESES_ABR_ES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def fmt_fecha_es(ts, abreviado=True):
    if pd.isna(ts): return ""
    d = int(ts.day); m = int(ts.month); y = int(ts.year)
    mes = MESES_ABR_ES[m-1].capitalize() if abreviado else MESES_LARGO[m-1]
    return f"{d:02d} {mes} {y}"

st.markdown(
    f"""<div style="text-align:center; margin-bottom:16px;">
          <img src="{LOGO_URL}" width="160" alt="Logo Iglesia">
        </div>""",
    unsafe_allow_html=True
)
st.title("📊 Dashboard Evolucion de APP Heaven")
st.caption("Analítica de impresiones, descargas y lanzamientos para líderes – con filtros claros, exportación y reportes profesionales.")

# =========================
# Utilidades de datos
# =========================
@st.cache_data
def leer_csv(path_or_buffer):
    return pd.read_csv(path_or_buffer, sep=None, engine="python")

def cargar_metric_con_plataformas(path_or_buffer, nombre_total):
    raw = leer_csv(path_or_buffer)
    lower = {c.lower(): c for c in raw.columns}
    if "date" not in lower or "total" not in lower:
        st.error(f"Esperaba columnas 'date' y 'total'. Encontré: {list(raw.columns)}"); st.stop()

    df_total = raw.rename(columns={lower["date"]:"Fecha", lower["total"]: nombre_total})
    df_total["Fecha"] = pd.to_datetime(df_total["Fecha"], errors="coerce")
    df_total = df_total.dropna(subset=["Fecha"])
    df_total[nombre_total] = pd.to_numeric(df_total[nombre_total], errors="coerce").fillna(0)
    df_total = df_total[["Fecha", nombre_total]]

    # Detectar columnas de plataformas (opcionales)
    plat_cols = [c for c in raw.columns if c not in [lower["date"], lower["total"]]]
    df_plat = None
    if plat_cols:
        df_plat = raw.rename(columns={lower["date"]:"Fecha"}).copy()
        df_plat["Fecha"] = pd.to_datetime(df_plat["Fecha"], errors="coerce")
        df_plat = df_plat.dropna(subset=["Fecha"])
        # Nombre “bonito”
        def prettify(c):
            base = c.replace("_"," ").title()
            mapping = {"Ios":"iOS","Ipad":"iPad","Iphone":"iPhone","Roku":"Roku","Web":"Web","Android":"Android","Apple Tv":"Apple TV","Tv":"TV"}
            return mapping.get(base, base)
        df_plat = df_plat[["Fecha"] + plat_cols].rename(columns={c:prettify(c) for c in plat_cols})
        for c in df_plat.columns:
            if c != "Fecha":
                df_plat[c] = pd.to_numeric(df_plat[c], errors="coerce").fillna(0)
    return df_total, df_plat

def enriquecer_tiempo(df):
    df["Año"]     = df["Fecha"].dt.year
    df["MesNum"]  = df["Fecha"].dt.month
    df["Mes"]     = df["MesNum"].map(lambda m: MESES_LARGO[m-1])
    df["Día"]     = df["Fecha"].dt.day
    df["Semana"]  = df["Fecha"].dt.isocalendar().week.astype(int)
    # Rango de semana (lunes a domingo)
    df["Sem_ini"] = df["Fecha"] - pd.to_timedelta(df["Fecha"].dt.weekday, unit="D")
    df["Sem_fin"] = df["Sem_ini"] + pd.Timedelta(days=6)
    # Etiquetas legibles
    df["Etiqueta_dia"] = df["Fecha"].apply(lambda x: fmt_fecha_es(x, True))
    df["Etiqueta_mes"] = df["Mes"] + " " + df["Año"].astype(str)
    df["Etiqueta_año"] = df["Año"].astype(str)
    df["Etiqueta_sem"] = ("Sem " + df["Semana"].astype(str) + " (" +
                          df["Sem_ini"].apply(lambda x: fmt_fecha_es(x, True)) + " – " +
                          df["Sem_fin"].apply(lambda x: fmt_fecha_es(x, True)) + ")")
    return df

def agregar(df, nivel, cols):
    if nivel == "Día":
        by, label = ["Año","MesNum","Día","Etiqueta_dia"], "Etiqueta_dia"
    elif nivel == "Semana":
        by, label = ["Año","Semana","Etiqueta_sem"], "Etiqueta_sem"
    elif nivel == "Mes":
        by, label = ["Año","MesNum","Etiqueta_mes"], "Etiqueta_mes"
    else:
        by, label = ["Año","Etiqueta_año"], "Etiqueta_año"
    g = df.groupby(by, dropna=False)[cols].sum().reset_index()
    orden = [c for c in ["Año","MesNum","Semana","Día"] if c in g.columns]
    if orden: g = g.sort_values(orden)
    g = g.rename(columns={label:"Etiqueta"})
    return g

def variacion_pct(a, b):
    if b is None or pd.isna(b) or b == 0: return np.nan
    if a is None or pd.isna(a): return np.nan
    return (a-b)/b*100.0

def safe_pct_label(v):  # evita NaN en textos
    return f"{v:+.1f}%" if v==v else "s/d"

# =========================
# Filtros de fecha “inteligentes”
# =========================
def rango_por_atajo(opcion, hoy, mes_especifico=None, anio_especifico=None, hasta_hoy=True):
    if opcion == "Últimos 7 días":
        return hoy - pd.Timedelta(days=6), hoy
    if opcion == "Últimos 30 días":
        return hoy - pd.Timedelta(days=29), hoy
    if opcion == "Este mes":
        ini = pd.Timestamp(year=hoy.year, month=hoy.month, day=1)
        fin = hoy
        return ini, fin
    if opcion == "Mes pasado":
        first_this = pd.Timestamp(year=hoy.year, month=hoy.month, day=1)
        last_prev  = first_this - pd.Timedelta(days=1)
        ini_prev   = pd.Timestamp(year=last_prev.year, month=last_prev.month, day=1)
        fin_prev   = last_prev
        return ini_prev, fin_prev
    if opcion == "Este año":
        return pd.Timestamp(year=hoy.year, month=1, day=1), hoy
    if opcion == "Año pasado":
        return pd.Timestamp(year=hoy.year-1, month=1, day=1), pd.Timestamp(year=hoy.year-1, month=12, day=31)
    if opcion == "Mes específico…":
        if mes_especifico is None or anio_especifico is None:
            return None, None
        ini = pd.Timestamp(year=anio_especifico, month=mes_especifico, day=1)
        if hasta_hoy and (anio_especifico==hoy.year and mes_especifico==hoy.month):
            fin = hoy
        else:
            # fin de mes
            fin = (ini + pd.offsets.MonthEnd(1))
        return ini, fin
    return None, None

# =========================
# Carga de datos
# =========================
st.sidebar.header("Origen de datos")
origen = st.sidebar.radio("Selecciona cómo cargar los datos", ["Archivos del repositorio", "Subir archivos CSV"])

if origen == "Archivos del repositorio":
    imp_tot, imp_plat = cargar_metric_con_plataformas("impressions-year.csv", "Impresiones")
    dwn_tot, dwn_plat = cargar_metric_con_plataformas("app-downloads-year.csv", "Descargas")
    lnc_tot, lnc_plat = cargar_metric_con_plataformas("app-launches-year.csv", "Lanzamientos")
else:
    st.sidebar.caption("Sube impresiones, descargas y lanzamientos (con 'date' y 'total'; opcional: columnas por plataforma).")
    up_imp = st.sidebar.file_uploader("Impresiones", type=["csv"])
    up_dwn = st.sidebar.file_uploader("Descargas",  type=["csv"])
    up_lnc = st.sidebar.file_uploader("Lanzamientos", type=["csv"])
    if not (up_imp and up_dwn and up_lnc):
        st.info("Sube los tres CSV para continuar."); st.stop()
    imp_tot, imp_plat = cargar_metric_con_plataformas(up_imp, "Impresiones")
    dwn_tot, dwn_plat = cargar_metric_con_plataformas(up_dwn, "Descargas")
    lnc_tot, lnc_plat = cargar_metric_con_plataformas(up_lnc, "Lanzamientos")

df = (imp_tot.merge(dwn_tot, on="Fecha", how="outer")
             .merge(lnc_tot, on="Fecha", how="outer")
             .fillna(0).sort_values("Fecha"))
if df.empty:
    st.warning("No hay datos."); st.stop()

df = enriquecer_tiempo(df)

# =========================
# Filtros & Metas
# =========================
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
    # fallback: últimos 12 meses
    ini_r = max(df["Fecha"].max() - pd.DateOffset(months=12), df["Fecha"].min())
    fin_r = df["Fecha"].max()

# Opción de ajuste manual (si quieren)
ini_r, fin_r = st.sidebar.date_input("Rango (puedes ajustar)", value=(ini_r.date(), fin_r.date()))

gran = st.sidebar.radio("Granularidad", ["Día","Semana","Mes","Año"])
metricas = ["Impresiones","Descargas","Lanzamientos"]
metricas_sel = st.sidebar.multiselect("Métricas", metricas, default=metricas)
tipo_graf = st.sidebar.radio("Tipo de gráfico", ["Líneas","Barras"], horizontal=True)

st.sidebar.header("Metas (OKRs)")
umbral_alerta = st.sidebar.slider("Alerta si baja más de (%) vs período anterior", 5, 80, 20)

# Aplicar rango
ini_ts = pd.to_datetime(ini_r); fin_ts = pd.to_datetime(fin_r)
df = df[(df["Fecha"] >= ini_ts) & (df["Fecha"] <= fin_ts)]

# =========================
# KPIs / Alertas / Insights
# =========================
agg = agregar(df, gran, metricas_sel)
st.markdown(f"**📅 Período:** {fmt_fecha_es(df['Fecha'].min())} – {fmt_fecha_es(df['Fecha'].max())}  |  **Granularidad:** {gran}")

c1,c2,c3,c4 = st.columns(4)
tot_imp = int(df["Impresiones"].sum()); tot_dwn = int(df["Descargas"].sum()); tot_lnc = int(df["Lanzamientos"].sum())
conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0
c1.metric("👀 Impresiones (período)", f"{tot_imp:,}")
c2.metric("⬇️ Descargas (período)",  f"{tot_dwn:,}")
c3.metric("🚀 Lanzamientos (período)", f"{tot_lnc:,}")
c4.metric("📈 Conversión (Desc/Imp)", f"{conv:,.2f}%")
st.caption(f"**Uso por instalación (Lan/Desc):** {uso:,.2f}")

alertas = []
if len(agg) >= 2:
    a, p = agg.iloc[-1], agg.iloc[-2]
    for m in metricas_sel:
        if p[m] > 0:
            cambio = variacion_pct(a[m], p[m])
            if not np.isnan(cambio) and cambio <= -umbral_alerta:
                alertas.append(f"🔴 **{m}** cayó **{cambio:.1f}%** (últ. {gran.lower()}: {a['Etiqueta']} vs prev.: {p['Etiqueta']})")
if alertas: st.error(" \n".join(alertas))
else:       st.success("✅ Sin alertas críticas en el período seleccionado.")

# Insights
def insights(df):
    out = []
    tot_imp = df["Impresiones"].sum(); tot_dwn = df["Descargas"].sum(); tot_lnc = df["Lanzamientos"].sum()
    conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
    uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0
    out.append(f"• Conversión: **{conv:,.2f}%**. Uso por instalación: **{uso:,.2f}**.")
    # diaria
    tmp = df.set_index("Fecha")[["Impresiones","Descargas","Lanzamientos"]].resample("D").sum()
    if len(tmp) >= 2:
        a, p = tmp.iloc[-1], tmp.iloc[-2]
        out.append("• Variación día a día (último vs previo): " +
                   f"Impresiones **{safe_pct_label(variacion_pct(a['Impresiones'], p['Impresiones']))}**, " +
                   f"Descargas **{safe_pct_label(variacion_pct(a['Descargas'], p['Descargas']))}**, " +
                   f"Lanzamientos **{safe_pct_label(variacion_pct(a['Lanzamientos'], p['Lanzamientos']))}**.")
    else:
        out.append("• Variación día a día: **s/d** (no hay datos suficientes).")
    # mensual
    tmpm = df.set_index("Fecha")[["Impresiones","Descargas","Lanzamientos"]].resample("MS").sum()
    if len(tmpm) >= 2:
        a, p = tmpm.iloc[-1], tmpm.iloc[-2]
        out.append("• Variación mensual: " +
                   f"Impresiones **{safe_pct_label(variacion_pct(a['Impresiones'], p['Impresiones']))}**, " +
                   f"Descargas **{safe_pct_label(variacion_pct(a['Descargas'], p['Descargas']))}**, " +
                   f"Lanzamientos **{safe_pct_label(variacion_pct(a['Lanzamientos'], p['Lanzamientos']))}**.")
    else:
        out.append("• Variación mensual: **s/d** (no hay datos suficientes).")
    return out

st.markdown("#### 🧠 Insights")
for linea in insights(df): st.markdown(linea)
st.divider()

# =========================
# Tabs
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualización", "🧩 Por plataforma", "📄 Reporte (Excel)", "🖨️ Reporte PDF"])

with tab1:
    st.subheader(f"Evolución por {gran.lower()} – {', '.join(metricas_sel)}")
    if tipo_graf == "Líneas":
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
        st.info("Tus CSV no traen columnas por plataforma. Si las agregas, aquí verás barras apiladas y participación.")
    else:
        dfp = dfp.merge(df[["Fecha"]], on="Fecha", how="inner")
        dfp = enriquecer_tiempo(dfp)
        by = {"Día":["Año","MesNum","Día","Etiqueta_dia"],
              "Semana":["Año","Semana","Etiqueta_sem"],
              "Mes":["Año","MesNum","Etiqueta_mes"],
              "Año":["Año","Etiqueta_año"]}[gran]
        etiqueta = by[-1]
        agg_plat = dfp.groupby(by, dropna=False).sum(numeric_only=True).reset_index().rename(columns={etiqueta:"Etiqueta"})
        plat_cols = [c for c in agg_plat.columns if c not in ["Año","MesNum","Semana","Día","Etiqueta","Fecha","Sem_ini","Sem_fin","Mes"]]
        agg_plat = agg_plat.sort_values([c for c in ["Año","MesNum","Semana","Día"] if c in agg_plat.columns])

        fig_stack = px.bar(agg_plat, x="Etiqueta", y=plat_cols, barmode="stack", title=f"{met_seg} por {gran.lower()} (apilado)")
        fig_stack.update_layout(xaxis_title="", legend_title="")
        st.plotly_chart(fig_stack, use_container_width=True)

        if len(agg_plat) > 0:
            ultimo = agg_plat.iloc[-1][plat_cols]
            fig_pie = px.pie(values=ultimo.values, names=ultimo.index, title="Participación (último período)")
            st.plotly_chart(fig_pie, use_container_width=True)

with tab3:
    st.subheader("Descargar datos agregados")
    periodo = st.selectbox("Periodo de tabla", ["Diario","Semanal","Mensual"])
    tabla_rep = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo], metricas)
    st.dataframe(tabla_rep, use_container_width=True)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter") as writer:
        tabla_rep.to_excel(writer, index=False, sheet_name="Datos")
    st.download_button("📥 Descargar Excel", data=out.getvalue(),
                       file_name=f"datos_{periodo.lower()}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---------- PDF PRO: portada, KPIs, gráficos y tabla formateada ----------
def plot_to_png(fig, w=1100, h=500, scale=2):
    # Requiere kaleido en requirements
    return fig.to_image(format="png", width=w, height=h, scale=scale)

def build_pdf(logo_url, titulo, subtitulo, kpi_dict, figuras_png, tabla_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=1.5*cm, rightMargin=1.5*cm)
    W, H = A4
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="h1", parent=styles["Heading1"], alignment=1, fontSize=18, spaceAfter=12))
    styles.add(ParagraphStyle(name="h2", parent=styles["Heading2"], alignment=1, fontSize=12, textColor=colors.grey, spaceAfter=12))
    styles.add(ParagraphStyle(name="kpi", parent=styles["Normal"], alignment=1, fontSize=12))
    story = []

    # Portada
    try:
        logo_bytes = requests.get(logo_url, timeout=10).content
        img = Image(io.BytesIO(logo_bytes), width=4*cm, height=3*cm)
        story.append(Spacer(1, 1*cm))
        story.append(img)
    except Exception:
        story.append(Spacer(1, 4*cm))
    story.append(Paragraph(titulo, styles["h1"]))
    story.append(Paragraph(subtitulo, styles["h2"]))
    story.append(Spacer(1, 0.5*cm))

    # KPIs en una grilla 2x2
    data_kpi = [
        [Paragraph("👀 Impresiones", styles["kpi"]), Paragraph(f"{kpi_dict['imp']:,}", styles["kpi"])],
        [Paragraph("⬇️ Descargas",  styles["kpi"]), Paragraph(f"{kpi_dict['dwn']:,}", styles["kpi"])],
        [Paragraph("🚀 Lanzamientos",styles["kpi"]), Paragraph(f"{kpi_dict['lnc']:,}", styles["kpi"])],
        [Paragraph("📈 Conversión", styles["kpi"]), Paragraph(f"{kpi_dict['conv']:,.2f}%", styles["kpi"])],
        [Paragraph("🧭 Uso por instalación", styles["kpi"]), Paragraph(f"{kpi_dict['uso']:,.2f}", styles["kpi"])]
    ]
    t = Table(data_kpi, colWidths=[7*cm, 7*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.whitesmoke),
        ('BOX',(0,0),(-1,-1), colors.grey),
        ('INNERGRID',(0,0),(-1,-1), colors.lightgrey),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('FONT',(0,0),(-1,-1),'Helvetica')
    ]))
    story.append(t)
    story.append(Spacer(1, 0.6*cm))
    story.append(PageBreak())

    # Gráficos (1 por página)
    for png in figuras_png:
        story.append(Image(io.BytesIO(png), width=W-3*cm, height=H-5*cm))
        story.append(PageBreak())

    # Tabla resumida y con estilo
    story.append(Paragraph("Datos agregados (primeros 30 registros)", styles["Heading2"]))
    head = list(tabla_df.columns)
    rows = [head] + tabla_df.head(30).astype(str).values.tolist()
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0), colors.Color(0.12,0.12,0.12)),
        ('TEXTCOLOR',(0,0),(-1,0), colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('GRID',(0,0),(-1,-1), 0.25, colors.lightgrey),
        ('FONT',(0,0),(-1,0),'Helvetica-Bold'),
        ('FONT',(0,1),(-1,-1),'Helvetica'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.whitesmoke, colors.lightgrey]),
    ]))
    story.append(table)

    # Número de página
    def on_page(canvas, doc):
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(W-1.2*cm, 1*cm, f"Página {doc.page}")

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()

with tab4:
    st.subheader("Generar Reporte PDF profesional")
    periodo_pdf = st.selectbox("Periodo de tabla PDF", ["Diario","Semanal","Mensual"])
    tabla_pdf = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo_pdf], metricas)

    # Gráficos que irán al PDF
    if tipo_graf == "Líneas":
        fig_main = px.line(agg, x="Etiqueta", y=metricas_sel, markers=True, title=f"Evolución por {gran.lower()}")
    else:
        fig_main = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title=f"Evolución por {gran.lower()}")
    fig_main.update_layout(xaxis_title="", legend_title="")

    fig_comp = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title="Comparativa")
    fig_comp.update_layout(xaxis_title="", legend_title="")

    pngs = [plot_to_png(fig_main), plot_to_png(fig_comp)]

    kpis = {"imp": tot_imp, "dwn": tot_dwn, "lnc": tot_lnc, "conv": conv, "uso": uso}
    subtitulo = f"Rango: {fmt_fecha_es(df['Fecha'].min())} a {fmt_fecha_es(df['Fecha'].max())}  •  Granularidad: {gran}"

    if st.button("🖨️ Generar PDF"):
        pdf_bytes = build_pdf(LOGO_URL, "Dashboard Evolucion de APP Heaven – Reporte", subtitulo, kpis, pngs, tabla_pdf)
        st.download_button("📥 Descargar PDF", data=pdf_bytes,
                           file_name=f"reporte_{periodo_pdf.lower()}.pdf", mime="application/pdf")
