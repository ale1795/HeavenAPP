import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard App Iglesia", page_icon="📱", layout="wide")
st.title("📱 Dashboard App Iglesia")

# ---- Cargar archivos CSV individuales ----
try:
    impressions = pd.read_csv("impressions-year.csv")
    downloads = pd.read_csv("app-downloads-year.csv")
    launches = pd.read_csv("app-launches-year.csv")
except Exception as e:
    st.error(f"No pude leer los CSV: {e}")
    st.stop()

# ---- Normalizar columnas ----
for df in [impressions, downloads, launches]:
    df.columns = [c.strip().capitalize() for c in df.columns]

# Asumimos que todas tienen columna Fecha
df = impressions.merge(downloads, on="Fecha", how="outer").merge(launches, on="Fecha", how="outer")
df = df.rename(columns={
    "Impressions": "Impressions",
    "Downloads": "Downloads",
    "Launches": "Launches"
})
df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
df = df.dropna(subset=["Fecha"]).sort_values("Fecha")

# ---- Filtros ----
st.sidebar.header("Filtros")
rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(df["Fecha"].min().date(), df["Fecha"].max().date())
)
if isinstance(rango, tuple) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df = df[(df["Fecha"] >= ini) & (df["Fecha"] <= fin)]

# ---- Selector de métrica ----
metrica = st.segmented_control(
    "Analytics",
    options=["App Impressions", "App Downloads", "App Launches"],
    default="App Impressions"
)

col1, col2, col3 = st.columns(3)
col1.metric("👀 Impresiones", f"{int(df['Impressions'].sum()):,}")
col2.metric("⬇️ Descargas", f"{int(df['Downloads'].sum()):,}")
col3.metric("🚀 Lanzamientos", f"{int(df['Launches'].sum()):,}")

serie = {
    "App Impressions": "Impressions",
    "App Downloads": "Downloads",
    "App Launches": "Launches"
}[metrica]

st.subheader(metrica)
st.line_chart(df.set_index("Fecha")[[serie]])

with st.expander("Ver tabla"):
    st.dataframe(df, use_container_width=True)

st.download_button(
    "⬇️ Descargar datos combinados (CSV)",
    df.to_csv(index=False).encode("utf-8"),
    "datos_combinados.csv",
    "text/csv"
)
