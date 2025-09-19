import pandas as pd
import streamlit as st

st.set_page_config(page_title="Dashboard mínimo", page_icon="📊", layout="wide")
st.title("📊 Dashboard mínimo (prueba)")

st.markdown("Sube **uno o hasta tres** CSV. Deben tener columnas `date` y `total`.")
col1, col2, col3 = st.columns(3)

files = {}
files["Impresiones"] = col1.file_uploader("Impresiones (impressions-year.csv)", type=["csv"])
files["Descargas"]   = col2.file_uploader("Descargas (app-downloads-year.csv)", type=["csv"])
files["Lanzamientos"]= col3.file_uploader("Lanzamientos (app-launches-year.csv)", type=["csv"])

dfs = []
for nombre, f in files.items():
    if f:
        df = pd.read_csv(f, sep=None, engine="python")
        df = df.rename(columns={c:"date" for c in df.columns if c.lower()=="date"})
        df = df.rename(columns={c:"total" for c in df.columns if c.lower()=="total"})
        if "date" in df.columns and "total" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df = df.dropna(subset=["date"])
            df = df[["date","total"]].rename(columns={"date":"Fecha","total":nombre})
            dfs.append(df)
        else:
            st.error(f"El archivo de **{nombre}** no tiene columnas `date` y `total`.")

if not dfs:
    st.info("👆 Sube al menos un CSV para ver datos.")
    st.stop()

# Combinar y mostrar
from functools import reduce
df_all = reduce(lambda a,b: pd.merge(a,b,on="Fecha",how="outer"), dfs).sort_values("Fecha").fillna(0)

st.subheader("Gráfico")
metrica = st.radio("Métrica", [c for c in df_all.columns if c!="Fecha"], horizontal=True)
st.line_chart(df_all.set_index("Fecha")[[metrica]])

with st.expander("📋 Ver tabla"):
    st.dataframe(df_all, use_container_width=True)
