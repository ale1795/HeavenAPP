import io
import requests
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import cm

# =========================
# Config
# =========================
st.set_page_config(page_title="Dashboard Evolucion de APP Heaven", page_icon="📊", layout="wide")

LOGO_URL = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"

MESES_LARGO = ["Enero","Febrero","Marzo","Abril","Mayo","Junio","Julio","Agosto","Septiembre","Octubre","Noviembre","Diciembre"]
MESES_ABR_ES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]
DIAS_ABR_ES  = ["lun","mar","mié","jue","vie","sáb","dom"]
PLAT_NAMES = {"ios":"iOS","android":"Android","apple_tv":"Apple TV","roku":"Roku","web":"Web",
              "ipad":"iPad","iphone":"iPhone","tv":"TV","other":"Otros"}

def fmt_fecha_es(ts, abreviado=True):
    """Devuelve '01 Ene 2024' o '01 Enero 2024' sin depender del locale."""
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

st.markdown("""
### ℹ️ Definiciones
- **👀 Impresiones:** Veces que la app fue **vista** en la tienda (visibilidad).
- **⬇️ Descargas:** Veces que la app fue **instalada** (interés).
- **🚀 Lanzamientos:** Veces que los usuarios **abrieron** la app (uso/engagement).
""")
st.divider()

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
        st.error(f"Esperaba columnas 'date' y 'total'. Encontré: {list(raw.columns)}")
        st.stop()

    df_total = raw.rename(columns={lower["date"]:"Fecha", lower["total"]: nombre_total})
    df_total["Fecha"] = pd.to_datetime(df_total["Fecha"], errors="coerce")
    df_total = df_total.dropna(subset=["Fecha"])
    df_total[nombre_total] = pd.to_numeric(df_total[nombre_total], errors="coerce").fillna(0)
    df_total = df_total[["Fecha", nombre_total]]

    plat_cols = [c for c in raw.columns if c not in [lower["date"], lower["total"]]]
    df_plat = None
    if plat_cols:
        df_plat = raw.rename(columns={lower["date"]:"Fecha"}).copy()
        df_plat["Fecha"] = pd.to_datetime(df_plat["Fecha"], errors="coerce")
        df_plat = df_plat.dropna(subset=["Fecha"])
        rename_map = {}
        for c in plat_cols:
            key = c.strip().lower()
            rename_map[c] = PLAT_NAMES.get(key, c.replace("_"," ").title())
        df_plat = df_plat[["Fecha"] + plat_cols].rename(columns=rename_map)
        for c in df_plat.columns:
            if c != "Fecha":
                df_plat[c] = pd.to_numeric(df_plat[c], errors="coerce").fillna(0)
    return df_total, df_plat

def enriquecer_tiempo(df):
    df["Año"] = df["Fecha"].dt.year
    df["MesNum"] = df["Fecha"].dt.month
    df["Mes"] = df["MesNum"].map(lambda m: MESES_LARGO[m-1])
    df["MesAbr"] = df["MesNum"].map(lambda m: MESES_ABR_ES[m-1])
    df["Día"] = df["Fecha"].dt.day
    df["Semana"] = df["Fecha"].dt.isocalendar().week.astype(int)
    # Rango de semana (lun-dom)
    df["Semana_inicio"] = df["Fecha"] - pd.to_timedelta(df["Fecha"].dt.weekday, unit="D")
    df["Semana_fin"] = df["Semana_inicio"] + pd.Timedelta(days=6)
    # Etiquetas en ESPAÑOL (sin locale)
    df["Etiqueta_dia"] = df["Fecha"].apply(lambda x: fmt_fecha_es(x, True))
    df["Etiqueta_sem"] = (
        "Sem " + df["Semana"].astype(str) + " (" +
        df["Semana_inicio"].apply(lambda x: fmt_fecha_es(x, True)) + " – " +
        df["Semana_fin"].apply(lambda x: fmt_fecha_es(x, True)) + ")"
    )
    df["Etiqueta_mes"] = df["Mes"] + " " + df["Año"].astype(str)
    df["Etiqueta_año"] = df["Año"].astype(str)
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
    if b is None or np.isnan(b) or b == 0: 
        return np.nan
    if a is None or np.isnan(a): 
        return np.nan
    return (a-b)/b*100.0

def safe_pct_label(v):
    return f"{v:+.1f}%" if v==v else "s/d"

def insights(df):
    out = []
    tot_imp = df["Impresiones"].sum(); tot_dwn = df["Descargas"].sum(); tot_lnc = df["Lanzamientos"].sum()
    conv = (tot_dwn/tot_imp*100) if tot_imp>0 else 0
    uso  = (tot_lnc/tot_dwn) if tot_dwn>0 else 0
    out.append(f"• Conversión: **{conv:,.2f}%**. Uso por instalación: **{uso:,.2f}**.")

    # Variación diaria (último vs anterior)
    tmp = df.set_index("Fecha")[["Impresiones","Descargas","Lanzamientos"]].resample("D").sum()
    if len(tmp) >= 2:
        a, p = tmp.iloc[-1], tmp.iloc[-2]
        out.append(
            "• Variación día a día (último vs previo): "
            f"Impresiones **{safe_pct_label(variacion_pct(a['Impresiones'], p['Impresiones']))}**, "
            f"Descargas **{safe_pct_label(variacion_pct(a['Descargas'], p['Descargas']))}**, "
            f"Lanzamientos **{safe_pct_label(variacion_pct(a['Lanzamientos'], p['Lanzamientos']))}**."
        )
    else:
        out.append("• Variación día a día: **s/d** (no hay datos suficientes).")

    # Variación mensual
    tmpm = df.set_index("Fecha")[["Impresiones","Descargas","Lanzamientos"]].resample("MS").sum()
    if len(tmpm) >= 2:
        a, p = tmpm.iloc[-1], tmpm.iloc[-2]
        out.append(
            "• Variación mensual: "
            f"Impresiones **{safe_pct_label(variacion_pct(a['Impresiones'], p['Impresiones']))}**, "
            f"Descargas **{safe_pct_label(variacion_pct(a['Descargas'], p['Descargas']))}**, "
            f"Lanzamientos **{safe_pct_label(variacion_pct(a['Lanzamientos'], p['Lanzamientos']))}**."
        )
    else:
        out.append("• Variación mensual: **s/d** (no hay datos suficientes).")
    return out

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
    st.sidebar.caption("Sube impresiones, descargas y lanzamientos (con 'date' y 'total', y opcionalmente columnas de plataformas).")
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
# Por defecto: últimos 12 meses
def_fecha_ini = max(df["Fecha"].max() - pd.DateOffset(months=12), df["Fecha"].min())
rango = st.sidebar.date_input("Rango de fechas", value=(def_fecha_ini.date(), df["Fecha"].max().date()))
if isinstance(rango, tuple) and len(rango)==2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df = df[(df["Fecha"] >= ini) & (df["Fecha"] <= fin)]

gran = st.sidebar.radio("Granularidad", ["Día","Semana","Mes","Año"])
metricas = ["Impresiones","Descargas","Lanzamientos"]
metricas_sel = st.sidebar.multiselect("Métricas", metricas, default=metricas)
tipo_graf = st.sidebar.radio("Tipo de gráfico", ["Líneas","Barras"], horizontal=True)

st.sidebar.header("Metas (OKRs)")
meta_conv = st.sidebar.number_input("Meta de Conversión % (Desc/Imp)", value=1.0, step=0.1)
meta_uso  = st.sidebar.number_input("Meta de Uso por instalación (Lan/Desc)", value=12.0, step=0.5)
umbral_alerta = st.sidebar.slider("Alerta si baja más de (%) vs período anterior", 5, 80, 20)

# =========================
# Agregación y KPIs
# =========================
agg = agregar(df, gran, metricas_sel)

# Mostrar periodo seleccionado arriba (en español)
periodo_txt = f"**📅 Período:** {fmt_fecha_es(df['Fecha'].min())} – {fmt_fecha_es(df['Fecha'].max())}  |  **Granularidad:** {gran}"
st.markdown(periodo_txt)

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

st.markdown("#### 🧠 Insights")
for linea in insights(df): st.markdown(linea)
st.divider()

# =========================
# Pestañas
# =========================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Visualización", "🧩 Por plataforma", "📄 Reporte (Excel)", "🖨️ Reporte PDF"])

# --- Visualización principal ---
with tab1:
    st.subheader(f"Evolución por {gran.lower()} – {', '.join(metricas_sel)}")
    if tipo_graf == "Líneas":
        fig = px.line(agg, x="Etiqueta", y=metricas_sel, markers=True)
    else:
        fig = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group")
    fig.update_layout(xaxis_title="", legend_title="", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

# --- Segmentación por plataforma ---
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
        plat_cols = [c for c in agg_plat.columns if c not in ["Año","MesNum","Semana","Día","Etiqueta","Fecha","Semana_inicio","Semana_fin","Mes","MesAbr"]]
        agg_plat = agg_plat.sort_values([c for c in ["Año","MesNum","Semana","Día"] if c in agg_plat.columns])

        fig_stack = px.bar(agg_plat, x="Etiqueta", y=plat_cols, barmode="stack", title=f"{met_seg} por {gran.lower()} (apilado)")
        fig_stack.update_layout(xaxis_title="", legend_title="")
        st.plotly_chart(fig_stack, use_container_width=True)

        if len(agg_plat) > 0:
            ultimo = agg_plat.iloc[-1][plat_cols]
            fig_pie = px.pie(values=ultimo.values, names=ultimo.index, title="Participación (último período)")
            st.plotly_chart(fig_pie, use_container_width=True)

# --- Reporte Excel ---
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

# --- Reporte PDF con logo y gráficos ---
def fig_to_png_bytes(fig, width=1100, height=500, scale=2):
    """Convierte figura Plotly a PNG (bytes) usando kaleido."""
    return fig.to_image(format="png", width=width, height=height, scale=scale)

def generar_pdf_con_logo(logo_url, kpis, texto_periodo, figuras_png_bytes, tabla_df):
    """Genera un PDF A4 con logo, KPIs, imágenes de gráficos y tabla resumida."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    # Portada
    y = H - 2*cm
    try:
        img = ImageReader(io.BytesIO(requests.get(logo_url, timeout=10).content))
        c.drawImage(img, (W-4*cm)/2, y-3*cm, width=4*cm, height=3*cm, mask='auto')
    except Exception:
        pass
    c.setFont("Helvetica-Bold", 18); c.drawCentredString(W/2, y-3.8*cm, "Dashboard Evolucion de APP Heaven – Reporte")
    c.setFont("Helvetica", 11); c.drawCentredString(W/2, y-4.5*cm, texto_periodo)

    # KPIs
    c.setFont("Helvetica", 12)
    yk = y-6.0*cm
    c.drawString(2*cm, yk,       f"👀 Impresiones: {kpis['imp']:,}")
    c.drawString(2*cm, yk-0.7*cm, f"⬇️ Descargas:  {kpis['dwn']:,}")
    c.drawString(2*cm, yk-1.4*cm, f"🚀 Lanzamientos: {kpis['lnc']:,}")
    c.drawString(2*cm, yk-2.1*cm, f"📈 Conversión:  {kpis['conv']:,.2f}%")
    c.drawString(2*cm, yk-2.8*cm, f"🧭 Uso por instalación: {kpis['uso']:,.2f}")
    c.showPage()

    # Gráficos (1 por página)
    for i, png in enumerate(figuras_png_bytes):
        img = ImageReader(io.BytesIO(png))
        c.drawImage(img, 1.5*cm, 4*cm, width=W-3*cm, height=H-7*cm)
        c.showPage()

    # Tabla resumida (primeros 30 renglones)
    c.setFont("Helvetica-Bold", 12); c.drawString(2*cm, H-2.5*cm, "Datos agregados")
    c.setFont("Helvetica", 9)
    ytab = H-3.2*cm
    lines = tabla_df.head(30).to_string(index=False).splitlines()
    for line in lines:
        c.drawString(2*cm, ytab, line)
        ytab -= 0.45*cm
        if ytab < 2*cm:
            c.showPage(); ytab = H-2.5*cm
    c.save()
    return buf.getvalue()

with tab4:
    st.subheader("Generar Reporte PDF con logo y gráficos")
    periodo_pdf = st.selectbox("Periodo de tabla PDF", ["Diario","Semanal","Mensual"], key="pdfp")
    tabla_pdf = agregar(df, {"Diario":"Día","Semanal":"Semana","Mensual":"Mes"}[periodo_pdf], metricas)

    # 2 gráficos para el PDF: evolución + barras comparativas
    if tipo_graf == "Líneas":
        fig_main = px.line(agg, x="Etiqueta", y=metricas_sel, markers=True, title=f"Evolución por {gran.lower()}")
    else:
        fig_main = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title=f"Evolución por {gran.lower()}")
    fig_main.update_layout(xaxis_title="", legend_title="")

    fig_comp = px.bar(agg, x="Etiqueta", y=metricas_sel, barmode="group", title="Comparativa")
    fig_comp.update_layout(xaxis_title="", legend_title="")

    pngs = [fig_to_png_bytes(fig_main), fig_to_png_bytes(fig_comp)]

    kpis = {"imp": tot_imp, "dwn": tot_dwn, "lnc": tot_lnc, "conv": conv, "uso": uso}
    texto_periodo = f"Rango: {fmt_fecha_es(df['Fecha'].min())} a {fmt_fecha_es(df['Fecha'].max())}  •  Granularidad: {gran}"

    if st.button("🖨️ Generar PDF"):
        pdf_bytes = generar_pdf_con_logo(LOGO_URL, kpis, texto_periodo, pngs, tabla_pdf)
        st.download_button("📥 Descargar PDF", data=pdf_bytes,
                           file_name=f"reporte_{periodo_pdf.lower()}.pdf", mime="application/pdf")
