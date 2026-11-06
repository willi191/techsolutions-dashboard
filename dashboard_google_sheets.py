import streamlit as st
import plotly.express as px

from procesar_google_sheets import conectar_google_sheets, leer_ventas

st.set_page_config(
    page_title="TechSolutions S.A.S. - BI",
    page_icon="📊",
    layout="wide",
)

st.title("Dashboard de ventas")
st.subheader("TechSolutions S.A.S.")
st.caption("Los datos se leen directamente desde Google Sheets")

@st.cache_data(ttl=60)
def cargar_datos():
    documento = conectar_google_sheets()
    return leer_ventas(documento)

try:
    df = cargar_datos()
except Exception as error:
    st.error("No se pudieron cargar los datos desde Google Sheets.")
    st.code(str(error))
    st.info(
        "Verifica que hayas configurado GOOGLE_SERVICE_ACCOUNT_FILE y "
        "GOOGLE_SHEET_URL en la misma terminal donde ejecutaste Streamlit."
    )
    st.stop()

st.sidebar.header("Filtros del dashboard")
ciudades = st.sidebar.multiselect(
    "Ciudad",
    options=sorted(df["Ciudad"].dropna().unique()),
    default=sorted(df["Ciudad"].dropna().unique()),
)
categorias = st.sidebar.multiselect(
    "Categoría",
    options=sorted(df["Categoría"].dropna().unique()),
    default=sorted(df["Categoría"].dropna().unique()),
)

filtrado = df[
    df["Ciudad"].isin(ciudades) & df["Categoría"].isin(categorias)
].copy()

if filtrado.empty:
    st.warning("No hay registros para los filtros seleccionados.")
    st.stop()

# Indicadores KPI
productos = filtrado["Producto"].nunique()
ingresos = filtrado["Total de ventas"].sum()
unidades = filtrado["Unidades"].sum()
promedio_producto = filtrado.groupby("Producto")["Total de ventas"].sum().mean()

k1, k2, k3, k4 = st.columns(4)
k1.metric("Ingresos totales", f"${ingresos:,.0f}")
k2.metric("Unidades vendidas", f"{unidades:,.0f}")
k3.metric("Productos diferentes", f"{productos}")
k4.metric("Promedio por producto", f"${promedio_producto:,.0f}")

por_categoria = (
    filtrado.groupby("Categoría", as_index=False)["Total de ventas"]
    .sum()
    .sort_values("Total de ventas", ascending=False)
)
por_producto = (
    filtrado.groupby("Producto", as_index=False)["Total de ventas"]
    .sum()
    .sort_values("Total de ventas", ascending=False)
)
por_ciudad = (
    filtrado.groupby("Ciudad", as_index=False)["Total de ventas"]
    .sum()
    .sort_values("Total de ventas", ascending=False)
)
por_vendedor = (
    filtrado.groupby("Vendedor", as_index=False)
    .agg(
        Ingresos=("Total de ventas", "sum"),
        Unidades=("Unidades", "sum"),
        Transacciones=("ID", "count"),
    )
    .sort_values("Ingresos", ascending=False)
)

columna1, columna2 = st.columns(2)
with columna1:
    figura = px.bar(
        por_categoria,
        x="Categoría",
        y="Total de ventas",
        title="Ventas por categoría",
        text_auto=",")
    figura.update_layout(yaxis_title="Ingresos ($)")
    st.plotly_chart(figura, use_container_width=True)

with columna2:
    figura = px.pie(
        por_producto,
        names="Producto",
        values="Total de ventas",
        title="Participación de ventas por producto",
    )
    st.plotly_chart(figura, use_container_width=True)

columna3, columna4 = st.columns(2)
with columna3:
    figura = px.bar(
        por_ciudad,
        x="Ciudad",
        y="Total de ventas",
        title="Ventas por ciudad",
        text_auto=",")
    figura.update_layout(yaxis_title="Ingresos ($)")
    st.plotly_chart(figura, use_container_width=True)

with columna4:
    st.subheader("Desempeño de los vendedores")
    tabla_vendedores = por_vendedor.rename(columns={"Ingresos": "Ingresos ($)"})
    st.dataframe(tabla_vendedores, hide_index=True, use_container_width=True)

st.subheader("Registros utilizados")
st.dataframe(filtrado, hide_index=True, use_container_width=True)

st.download_button(
    "Descargar datos filtrados",
    filtrado.to_csv(index=False).encode("utf-8-sig"),
    file_name="ventas_filtradas.csv",
    mime="text/csv",
)
