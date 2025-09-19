import pandas as pd
import streamlit as st

# ---------- Configuración básica ----------
st.set_page_config(page_title="Dashboard App Iglesia", page_icon="📊", layout="wide")

# ---------- Mostrar logo arriba ----------
logo_url = "https://raw.githubusercontent.com/ale1795/HeavenAPP/main/HVN%20central%20blanco.png"
st.markdown(
    f"""
    <div style="text-align:center; margin-bottom:20px;">
        <img src="{logo_url}" width="200" alt="Logo Iglesia">
    </div>
    """,
    unsafe_allow_html=True
)

# ---------- Título ----------
st.title("📊 Dashboard App Iglesia")

# ---------- Definiciones visibles ----------
st.markdown("""
### ℹ️ ¿Qué significa cada métrica?
- **👀 Impresiones (App Impressions):** Veces que la app fue **vista en la tienda** (App Store / Google Play). Mide visibilidad.
- **⬇️ Descargas (App Downloads):** Veces que la app fue **instalada** en un dispositivo. Mide interés real.
- **🚀 Lanzamientos (App Launches):** Veces que los usuarios **abrieron la app** después de instalada. Mide uso/engagement.
""")

st.divider()

# ---------- Utilidades ----------
def leer_csv(path_or_buffer):
    """
    Lee CSV con autodetección del separador (, ; \t).
    Retorna DataFrame.
    """
    return pd.read_csv(path_or_buffer, sep=None, engine="python")

def cargar_y_traducir(path_or_buffer, nombre_valor):
    """
    Espera columnas: 'date' (fecha) y 'total' (valor).
    Renombra a español: Fecha, <nombre_valor>.
    """
    df = leer_csv(path_or_buffer)
    lower_map = {c.lower(): c for c in df.columns}
    if "date" not in lower_map or "total" not in lower_map:
        st.error(f"El archivo no tiene columnas esperadas 'date' y 'total'. Columnas: {list(df.columns)}")
        st.stop()

    df = df.rename(columns={
        lower_map["date"]: "Fecha",
        lower_map["total"]: nombre_valor
    })
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])
    df[nombre_valor] = pd.to_numeric(df[nombre_valor], errors="coerce").fillna(0)
    return df[["Fecha", nombre_valor]]

# ---------- Entrada de datos (repo o subida manual) ----------
st.sidebar.header("Origen de datos")
origen = st.sidebar.radio(
    "Selecciona cómo cargar los datos",
    ["Archivos del repositorio", "Subir archivos CSV"],
)

if origen == "Archivos del repositorio":
    imp_path = "impressions-year.csv"
    dwn_path = "app-downloads-year.csv"
    lnc_path = "app-launches-year.csv"

    try:
        impresiones  = cargar_y_traducir(imp_path, "Impresiones")
        descargas    = cargar_y_traducir(dwn_path, "Descargas")
        lanzamientos = cargar_y_traducir(lnc_path, "Lanzamientos")
    except Exception as e:
        st.error(f"No pude cargar los CSV del repositorio: {e}")
        st.stop()
else:
    st.sidebar.caption("Sube los tres archivos: impresiones, descargas y lanzamientos (cada uno con columnas 'date' y 'total').")
    up_imp = st.sidebar.file_uploader("Impresiones (impressions-year.csv)", type=["csv"], key="imp")
    up_dwn = st.sidebar.file_uploader("Descargas (app-downloads-year.csv)", type=["csv"], key="dwn")
    up_lnc = st.sidebar.file_uploader("Lanzamientos (app-launches-year.csv)", type=["csv"], key="lnc")

    if not (up_imp and up_dwn and up_lnc):
        st.info("Sube los tres CSV para continuar.")
        st.stop()

    try:
        impresiones  = cargar_y_traducir(up_imp, "Impresiones")
        descargas    = cargar_y_traducir(up_dwn, "Descargas")
        lanzamientos = cargar_y_traducir(up_lnc, "Lanzamientos")
    except Exception as e:
        st.error(f"No pude procesar los archivos subidos: {e}")
        st.stop()

# ---------- Unir datasets ----------
df = (
    impresiones
    .merge(descargas, on="Fecha", how="outer")
    .merge(lanzamientos, on="Fecha", how="outer")
    .sort_values("Fecha")
    .fillna(0)
)

if df.empty:
    st.warning("No hay datos para mostrar después de combinar los archivos.")
    st.stop()

# ---------- Filtros ----------
st.sidebar.header("Filtros")
rango = st.sidebar.date_input(
    "Rango de fechas",
    value=(df["Fecha"].min().date(), df["Fecha"].max().date())
)
if isinstance(rango, tuple) and len(rango) == 2:
    ini, fin = pd.to_datetime(rango[0]), pd.to_datetime(rango[1])
    df = df[(df["Fecha"] >= ini) & (df["Fecha"] <= fin)]

# ---------- KPIs ----------
c1, c2, c3, c4 = st.columns(4)
c1.metric("👀 Impresiones", f"{int(df['Impresiones'].sum()):,}")
c2.metric("⬇️ Descargas",  f"{int(df['Descargas'].sum()):,}")
c3.metric("🚀 Lanzamientos", f"{int(df['Lanzamientos'].sum()):,}")

conversion = (df["Descargas"].sum() / df["Impresiones"].sum() * 100) if df["Impresiones"].sum() > 0 else 0
uso_por_instal = (df["Lanzamientos"].sum() / df["Descargas"].sum()) if df["Descargas"].sum() > 0 else 0
c4.metric("📈 Conversion (Descargas / Impresiones)", f"{conversion:,.2f}%")

st.caption(f"**Uso por instalación** (Lanzamientos ÷ Descargas): {uso_por_instal:,.2f} veces por instalación.")

st.divider()

# ---------- Gráficos ----------
tab1, tab2, tab3, tab4 = st.tabs(["📈 Impresiones", "📉 Descargas", "🚀 Lanzamientos", "📊 Comparativo"])

with tab1:
    st.subheader("Evolución de Impresiones")
    st.line_chart(df.set_index("Fecha")[["Impresiones"]])

with tab2:
    st.subheader("Evolución de Descargas")
    st.line_chart(df.set_index("Fecha")[["Descargas"]])

with tab3:
    st.subheader("Evolución de Lanzamientos")
    st.line_chart(df.set_index("Fecha")[["Lanzamientos"]])

with tab4:
    st.subheader("Comparativo de Métricas")
    st.line_chart(df.set_index("Fecha")[["Impresiones", "Descargas", "Lanzamientos"]])

# ---------- Tabla y descarga ----------
with st.expander("📋 Ver tabla de datos"):
    st.dataframe(df, use_container_width=True)

st.download_button(
    "⬇️ Descargar datos filtrados (CSV)",
    df.to_csv(index=False).encode("utf-8"),
    "datos_combinados_filtrados.csv",
    "text/csv"
)
