"""Conecta Python con Google Sheets, procesa las ventas y escribe los resultados.

Configuración recomendada mediante variables de entorno:
  GOOGLE_SERVICE_ACCOUNT_FILE=/ruta/a/credenciales.json
  GOOGLE_SHEET_URL=https://docs.google.com/spreadsheets/d/...

La hoja de entrada debe llamarse "Ventas" y contener:
ID, Producto, Categoría, Ciudad, Vendedor, Unidades, Precio
"""

import os
import unicodedata
from pathlib import Path

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]
COLUMNAS_REQUERIDAS = [
    "ID", "Producto", "Categoría", "Ciudad", "Vendedor", "Unidades", "Precio"
]


def normalizar_encabezado(texto):
    """Permite encabezados con o sin tildes, por ejemplo Categoria/Categoría."""
    texto = str(texto).strip()
    sin_tildes = "".join(
        caracter for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )
    equivalencias = {
        "categoria": "Categoría",
        "producto": "Producto",
        "ciudad": "Ciudad",
        "vendedor": "Vendedor",
        "unidades": "Unidades",
        "precio": "Precio",
        "id": "ID",
        "total de ventas": "Total de ventas",
    }
    return equivalencias.get(sin_tildes.lower(), texto)


def conectar_google_sheets():
    archivo_credenciales = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    url_hoja = os.getenv("GOOGLE_SHEET_URL")

    # En Streamlit Community Cloud se usan st.secrets en lugar de un archivo local.
    try:
        import streamlit as st
        secretos = st.secrets
    except Exception:
        secretos = None

    if secretos is not None and "gcp_service_account" in secretos:
        datos_cuenta = dict(secretos["gcp_service_account"])
        url_hoja = secretos.get("google_sheet_url", url_hoja)
        if not url_hoja:
            url_hoja = datos_cuenta.get("google_sheet_url")
        if not url_hoja:
            raise RuntimeError("Falta google_sheet_url en los secretos de Streamlit.")
        credenciales = Credentials.from_service_account_info(
            datos_cuenta, scopes=SCOPES
        )
        cliente = gspread.authorize(credenciales)
        return cliente.open_by_url(url_hoja)

    if not archivo_credenciales:
        raise RuntimeError(
            "Falta GOOGLE_SERVICE_ACCOUNT_FILE. Define la ruta del archivo JSON "
            "descargado desde Google Cloud."
        )
    if not url_hoja:
        raise RuntimeError(
            "Falta GOOGLE_SHEET_URL. Define la URL de tu documento de Google Sheets."
        )
    if not Path(archivo_credenciales).exists():
        raise FileNotFoundError(f"No existe el archivo de credenciales: {archivo_credenciales}")

    credenciales = Credentials.from_service_account_file(
        archivo_credenciales, scopes=SCOPES
    )
    cliente = gspread.authorize(credenciales)
    return cliente.open_by_url(url_hoja)


def leer_ventas(documento):
    try:
        hoja = documento.worksheet("Ventas")
    except gspread.WorksheetNotFound as error:
        raise RuntimeError("Crea una pestaña llamada 'Ventas' en Google Sheets.") from error

    df = pd.DataFrame(hoja.get_all_records())
    df.columns = [normalizar_encabezado(columna) for columna in df.columns]
    faltantes = [col for col in COLUMNAS_REQUERIDAS if col not in df.columns]
    if faltantes:
        raise ValueError("Faltan columnas en la hoja Ventas: " + ", ".join(faltantes))
    if df.empty:
        raise ValueError("La hoja Ventas no contiene registros.")

    for columna in ["Unidades", "Precio"]:
        df[columna] = pd.to_numeric(df[columna], errors="coerce")
    if df[["Unidades", "Precio"]].isna().any().any():
        raise ValueError("Unidades y Precio deben ser valores numéricos.")

    # Se recalcula para evitar errores manuales, aunque la hoja ya tenga la columna.
    df["Total de ventas"] = df["Unidades"] * df["Precio"]
    return df


def resumenes(df):
    return {
        "Por producto": df.groupby("Producto", as_index=False).agg(
            Ingresos=("Total de ventas", "sum"), Unidades=("Unidades", "sum")
        ).sort_values("Ingresos", ascending=False),
        "Por categoría": df.groupby("Categoría", as_index=False).agg(
            Ingresos=("Total de ventas", "sum"), Unidades=("Unidades", "sum")
        ).sort_values("Ingresos", ascending=False),
        "Por ciudad": df.groupby("Ciudad", as_index=False).agg(
            Ingresos=("Total de ventas", "sum"), Unidades=("Unidades", "sum")
        ).sort_values("Ingresos", ascending=False),
        "Por vendedor": df.groupby("Vendedor", as_index=False).agg(
            Ingresos=("Total de ventas", "sum"),
            Unidades=("Unidades", "sum"),
            Transacciones=("ID", "count"),
        ).sort_values("Ingresos", ascending=False),
    }


def escribir_hoja(documento, nombre, df):
    """Crea o reemplaza una pestaña y sube el DataFrame a Google Sheets."""
    try:
        hoja = documento.worksheet(nombre)
        hoja.clear()
    except gspread.WorksheetNotFound:
        hoja = documento.add_worksheet(title=nombre, rows=100, cols=20)

    datos = [df.columns.tolist()] + df.fillna("").astype(object).values.tolist()
    hoja.resize(rows=max(len(datos), 1), cols=max(len(df.columns), 1))
    hoja.update(datos, "A1")
    hoja.freeze(rows=1)
    hoja.format("1:1", {"backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
                          "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}}})


def procesar():
    documento = conectar_google_sheets()
    df = leer_ventas(documento)

    kpi = pd.DataFrame({
        "Indicador": [
            "Total de ingresos por ventas",
            "Cantidad total de unidades",
            "Número de productos diferentes",
            "Promedio de ventas por producto",
        ],
        "Valor": [
            df["Total de ventas"].sum(),
            df["Unidades"].sum(),
            df["Producto"].nunique(),
            df.groupby("Producto")["Total de ventas"].sum().mean(),
        ],
    })

    escribir_hoja(documento, "Ventas procesadas", df)
    escribir_hoja(documento, "KPI", kpi)
    for nombre, tabla in resumenes(df).items():
        escribir_hoja(documento, nombre, tabla)

    print("Proceso terminado correctamente en Google Sheets.")
    print(f"Ingresos totales: ${df['Total de ventas'].sum():,.0f}")
    print(f"Unidades vendidas: {df['Unidades'].sum():,.0f}")
    print(f"Producto líder: {df.groupby('Producto')['Total de ventas'].sum().idxmax()}")
    print(f"Categoría líder: {df.groupby('Categoría')['Total de ventas'].sum().idxmax()}")
    print(f"Ciudad líder: {df.groupby('Ciudad')['Total de ventas'].sum().idxmax()}")
    print(f"Vendedor líder: {df.groupby('Vendedor')['Total de ventas'].sum().idxmax()}")


if __name__ == "__main__":
    procesar()
