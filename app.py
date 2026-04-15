import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

st.set_page_config(page_title="AML Dashboard", layout="wide")

st.title("🔍 Sistema AML - Dashboard Profesional")

archivo = st.file_uploader("Sube tu archivo Excel", type=["xlsx"])

if archivo:
    df = pd.read_excel(archivo)

    columnas = ["Cliente", "Monto", "Perfil", "Fecha"]

    if not all(col in df.columns for col in columnas):
        st.error("Faltan columnas obligatorias")
        st.stop()

    df["Fecha"] = pd.to_datetime(df["Fecha"])

    # =========================
    # CONFIG
    # =========================
    porcentaje = st.sidebar.slider("Tolerancia (%)", 0, 50, 15)
    umbral = st.sidebar.number_input("Umbral absoluto", value=20000)
    mult = st.sidebar.slider("Multiplicador", 1.0, 5.0, 2.0)

    # =========================
    # REGLAS
    # =========================
    df["Alerta_15"] = df["Monto"] > df["Perfil"] * (1 + porcentaje/100)
    df["Alerta_Absoluto"] = df["Monto"] > umbral

    total = df.groupby("Cliente")["Monto"].sum().reset_index()
    total.columns = ["Cliente", "Total_Mensual"]
    df = df.merge(total)

    df["Alerta_Acumulado"] = df["Total_Mensual"] > df["Perfil"] * mult

    freq = df.groupby("Cliente").size().reset_index(name="Transacciones")
    df = df.merge(freq)

    df["Alerta_Frecuencia"] = df["Transacciones"] > 5

    # =========================
    # SMURFING
    # =========================
    df["Fecha_dia"] = df["Fecha"].dt.date
    smurf = df.groupby(["Cliente", "Fecha_dia"]).size().reset_index(name="Count")
    smurf["Smurfing"] = smurf["Count"] >= 5
    df = df.merge(smurf, on=["Cliente", "Fecha_dia"])

    # =========================
    # PICOS
    # =========================
    stats = df.groupby("Cliente")["Monto"].agg(["mean", "std"]).reset_index()
    stats.columns = ["Cliente", "Media", "Std"]
    df = df.merge(stats)

    df["Pico"] = df["Monto"] > (df["Media"] + 2 * df["Std"])

    # =========================
    # SCORE
    # =========================
    df["Score"] = (
        df["Alerta_15"].astype(int) +
        df["Alerta_Absoluto"].astype(int)*3 +
        df["Alerta_Acumulado"].astype(int)*2 +
        df["Alerta_Frecuencia"].astype(int) +
        df["Smurfing"].astype(int)*3 +
        df["Pico"].astype(int)*2
    )

    # =========================
    # CASOS
    # =========================
    casos = df.groupby("Cliente").agg({
        "Monto":"sum",
        "Score":"max",
        "Transacciones":"max"
    }).reset_index()

    casos.columns = ["Cliente","Total_Mensual","Score","Transacciones"]

    # =========================
    # MATRIZ CLIENTE
    # =========================
    def riesgo_cliente(row):
        if row["Score"] >= 8 or row["Total_Mensual"] > 30000:
            return "🔴 Crítico"
        elif row["Score"] >= 5:
            return "🟠 Alto"
        elif row["Score"] >= 3:
            return "🟡 Medio"
        return "🟢 Bajo"

    casos["Riesgo_Cliente"] = casos.apply(riesgo_cliente, axis=1)

    # =========================
    # MATRIZ ALERTAS (REAL)
    # =========================
    matriz_alertas = pd.DataFrame({
        "Tipo_Alerta": [
            "Monto Alto (Absoluto)",
            "Acumulado Mensual",
            "Exceso sobre Perfil",
            "Frecuencia Alta",
            "Smurfing",
            "Pico Anómalo"
        ],
        "Cantidad": [
            df["Alerta_Absoluto"].sum(),
            df["Alerta_Acumulado"].sum(),
            df["Alerta_15"].sum(),
            df["Alerta_Frecuencia"].sum(),
            df["Smurfing"].sum(),
            df["Pico"].sum()
        ],
        "Impacto": [
            "🔴 Alto",
            "🟠 Medio-Alto",
            "🟡 Medio",
            "🟡 Medio",
            "🔴 Alto",
            "🟠 Medio-Alto"
        ],
        "Descripcion": [
            "Transacciones individuales altas",
            "Supera capacidad mensual",
            "Ligero exceso sobre perfil",
            "Muchas operaciones",
            "Fragmentación de dinero",
            "Comportamiento atípico"
        ]
    })

    # =========================
    # NAV
    # =========================
    vista = st.sidebar.radio("Vista",[
        "Resumen","Casos","Transacciones","Análisis por Cliente","Matriz"
    ])

    # =========================
    # ANALISIS CLIENTE
    # =========================
    if vista == "Análisis por Cliente":

        cliente = st.selectbox("Cliente", df["Cliente"].unique())
        datos = df[df["Cliente"] == cliente].sort_values("Fecha")
        datos["Fecha_str"] = datos["Fecha"].dt.strftime("%Y-%m-%d")

        st.subheader("📈 Tendencia")
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(datos["Fecha_str"], datos["Monto"], marker='o')
        ax.axhline(y=datos["Perfil"].iloc[0], linestyle='--')
        plt.xticks(rotation=45)
        st.pyplot(fig)

        st.subheader("🚨 Picos")
        fig, ax = plt.subplots(figsize=(10,4))
        ax.plot(datos["Fecha_str"], datos["Monto"], marker='o')
        picos = datos[datos["Pico"] == True]
        ax.scatter(picos["Fecha_str"], picos["Monto"])
        plt.xticks(rotation=45)
        st.pyplot(fig)

        st.subheader("🔁 Frecuencia")
        freq = datos.groupby("Fecha_str").size()
        fig, ax = plt.subplots(figsize=(10,4))
        ax.bar(freq.index, freq.values)
        plt.xticks(rotation=45)
        st.pyplot(fig)

        st.subheader("🟠 Smurfing")
        sm = datos.groupby("Fecha_str")["Smurfing"].max()
        fig, ax = plt.subplots(figsize=(10,4))
        ax.bar(sm.index, sm.values)
        plt.xticks(rotation=45)
        st.pyplot(fig)

    # =========================
    # MATRIZ
    # =========================
    elif vista == "Matriz":

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("🧠 Riesgo por Cliente")
            st.dataframe(casos)

        with col2:
            st.subheader("📊 Tipos de Alerta")
            st.dataframe(matriz_alertas)

    elif vista=="Resumen":
        st.metric("Clientes",len(casos))
        st.metric("Alertas",len(df[df["Score"]>0]))

    elif vista=="Casos":
        st.dataframe(casos)

    elif vista=="Transacciones":
        st.dataframe(df)

# =========================
# FIRMA
# =========================
st.markdown("---")
st.markdown(
"<center><small>Diseñado por el Ing. Hobéd Díaz, Msc. M.A.F.I</small></center>",
unsafe_allow_html=True
)
