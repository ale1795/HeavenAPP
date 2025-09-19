import pandas as pd
import streamlit as st

# =========================
# Configuración general
# =========================
st.set_page_config(page_title="Dashboard App Iglesia", page_icon="📊", layout="wide")

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
MESES_ES = ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"]

def leer_csv(path_or_buffer):
    """Lee CSV con autodetección de separador."""
    return pd.read_csv(path_or_buffer, sep=None, engine="python")

def cargar_y_traducir(path_or_buffer, nombre_valor):
    """
    Espera columnas 'date' (YYYY-MM-DD o similar) y 'total' (valor).
    Devuelve DataFrame con columnas: Fecha (datetime64[ns]), <nombre_valor> (float).
    """
    df = leer_csv(path_or_buffer)
    lower = {c.lower(): c for c in df.columns}
    if "date" not in lower or "total" not in lower:
        st.error(f"El archivo no tiene columnas esperadas 'date' y 'total'. Columnas encontradas: {list(df.columns)}")
        st.stop()
    df = df.rename(columns={lower["date"]: "Fecha", lower["total"]: nombre_valor})
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])
    df[nombre_valor] = pd.to_numeric(df[nombre_valor], errors="coerce").fillna(0)
    return df[["Fecha", nombre_valor]]

def agregar_campos_tiempo(df):
    """Agrega Año, MesNum, MesAbr (es), Dia, y etiquetas bonitas para cada nivel."""
    df["Año"] = df["Fecha"].dt.year
    df["MesNum"] = df["Fecha"].dt.month
    df["MesAbr"] = df["MesNum"].map(lambda m: MESES_ES[m-1])
    df["Día"] = df["Fecha"].dt.day
    # Etiquetas:
    df["Etiqueta_dia"] = df["Día"].astype(str).str.zfill(2) + " " + df["MesAbr"] + " " + df["Año"].astype(str)
    df["Etiqueta_mes"] = df["MesAbr"] + " " + df["Año"].astype(str)
    df["Etiqueta_año"] = df["Año"].astype(str)
    return df

def agregar_y_ordenar(df, by_cols, value_cols, label_col):
    """
    Agrupa por columnas de tiempo y suma valores.
    Añade la etiqueta de eje adecuada y ordena cronológicamente.
    """
    agg = df.groupby(by_cols, dropna=False)[value_cols].sum().reset_index()
    # Orden cronológico por año/mes/día si existen
    orden_cols = [c for c in ["Año", "MesNum", "Día"] if c in agg.columns]
    if orden_cols:
        agg = agg.sort_values(orden_cols)
    agg.rename(columns={label_col: "Etiqueta"}, inplace=True)
    return agg

def dibujar_chart(tipo, data_indexed):
    """Pinta gráfico según selección."""
    if tipo == "Líneas":
        st.line_chart(data_indexed)
    else:
        st.bar_chart(data_indexed)

# =========================
# Carga de datos
# =========================
st.sidebar.header("Origen de datos")
origen = st.sidebar.radio("Selecciona cómo cargar los datos", ["Archivos del repositorio", "Subir archivos CSV"])

if origen == "Archivos del repositorio":
    try:
        impresiones  = cargar_y_traducir("impressions-year.csv", "Impresiones")
        descargas    = cargar_y_traducir("app-downloads-year.csv", "Descargas")
        lanzamientos = cargar_y_traducir("app-launches-year.csv", "Lanzamientos")
    except Exception as e:
        st.error(f"No pude cargar los CSV: {e}")
        st.stop()
else:
    st.sidebar.caption("Sube los tres archivos: impresiones, descargas y lanzamientos (cada uno con 'date' y 'total').")
    up_imp = st.sidebar.file_uploader("Impresiones", type=["csv"], key="imp")
    up_dwn = st.sidebar.file_uploader("Descargas", type=["csv"], key="dwn")
    up_lnc = st.sidebar.file_uploader("Lanzamientos", type=["csv"], key="lnc")
    if not (up_imp and up_dwn and up_lnc):
        st.info("Sube los tres archivos CSV para continuar.")
        st.stop()
    impresiones  = cargar_y_traducir(up_imp, "Impresiones")
    descargas    = cargar_y_traducir(up_dwn, "Descargas")
    lanzamientos = cargar_y_traducir(up_lnc, "Lanzamientos")

# Unimos y enriquecemos
df = (
    impresiones
    .merge(descargas, on="Fecha", how="outer")
    .merge(lanzamientos, on="Fecha", how="outer")
    .fillna(0)
    .sort_values("Fecha")
)
if df.empty:
    st.warning("No hay datos disponibles.")
    st.stop()

df = agregar_campos_tiempo(df)

# =========================
# Filtros
# =========================
st.sidebar.header("Filtros")

# Rango de fechas
rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(df["Fecha"].min().date(), df["Fecha"].max().date())
)
if isinstance(rango, tuple) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df = df[(df["Fecha"] >= ini) & (df["Fecha"] <= fin)]

# Granularidad
gran = st.sidebar.radio("Granularidad", ["Día", "Mes", "Año"], horizontal=True)

# Métricas a mostrar
metricas_disp = ["Impresiones", "Descargas", "Lanzamientos"]
metricas_sel = st.sidebar.multiselect("Métricas", metricas_disp, default=metricas_disp)

# Tipo de gráfico
tipo_graf = st.sidebar.radio("Tipo de gráfico", ["Líneas", "Barras"], horizontal=True)

# =========================
# Agregación según granularidad
# =========================
if gran == "Día":
    agg = agregar_y_ordenar(df, ["Año", "MesNum", "Día", "Etiqueta_dia"], metricas_sel, "Etiqueta_dia")
elif gran == "Mes":
    agg = agregar_y_ordenar(df, ["Año", "MesNum", "Etiqueta_mes"], metricas_sel, "Etiqueta_mes")
else:  # Año
    agg = agregar_y_ordenar(df, ["Año", "Etiqueta_año"], metricas_sel, "Etiqueta_año")

# Índice para gráfico y tabla
agg_idx = agg.set_index("Etiqueta")[metricas_sel]

# =========================
# KPIs (sobre el rango filtrado)
# =========================
c1, c2, c3, c4 = st.columns(4)
c1.metric("👀 Impresiones", f"{int(df['Impresiones'].sum()):,}")
c2.metric("⬇️ Descargas",  f"{int(df['Descargas'].sum()):,}")
c3.metric("🚀 Lanzamientos", f"{int(df['Lanzamientos'].sum()):,}")

conversion = (df["Descargas"].sum() / df["Impresiones"].sum() * 100) if df["Impresiones"].sum() > 0 else 0
uso_instal = (df["Lanzamientos"].sum() / df["Descargas"].sum()) if df["Descargas"].sum() > 0 else 0
c4.metric("📈 Conversión (Descargas / Impresiones)", f"{conversion:,.2f}%")
st.caption(f"**Uso por instalación:** {uso_instal:,.2f} veces por instalación.")

st.divider()

# =========================
# Paneles
# =========================
tab1, tab2 = st.tabs(["📊 Visualización", "📋 Datos y descarga"])

with tab1:
    st.subheader(f"Evolución ({gran.lower()}) – {', '.join(metricas_sel)}")
    dibujar_chart(tipo_graf, agg_idx)

with tab2:
    st.subheader("Datos agregados según filtros")
    st.dataframe(agg, use_container_width=True)
    st.download_button(
        "📥 Descargar datos agregados (CSV)",
        agg.to_csv(index=False).encode("utf-8"),
        f"datos_{gran.lower()}_filtrados.csv",
        "text/csv"
    )

# Fin
