import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import math
from frontend.mod_utils import render_html_table

try:
    import networkx as nx
    _NX_DISPONIBLE = True
except ImportError:
    _NX_DISPONIBLE = False


def _color_por_score(score, score_max=10.0):
    """Retorna color hex según score normalizado."""
    ratio = min(score / max(score_max, 1), 1.0)
    if ratio >= 0.8:   return "#ef4444"   # Crítico
    elif ratio >= 0.5: return "#f97316"   # Alto
    elif ratio >= 0.3: return "#eab308"   # Medio
    return "#22c55e"                      # Bajo


def _layout_circular(nodos, radio=1.0):
    """Genera coordenadas circulares para los nodos."""
    n = len(nodos)
    pos = {}
    for i, nodo in enumerate(nodos):
        angulo = 2 * math.pi * i / n
        pos[nodo] = (radio * math.cos(angulo), radio * math.sin(angulo))
    return pos


def _normalizar_cliente(valor):
    """Normaliza nombres de cliente para evitar nodos duplicados por espacios."""
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _nodos_en_hops(G, foco, profundidad):
    """Obtiene la vecindad alrededor del cliente foco en un número de hops."""
    if foco not in G:
        return {foco}
    return set(nx.single_source_shortest_path_length(G.to_undirected(), foco, cutoff=profundidad).keys())


def mostrar(df, casos):
    st.markdown("""
    <div class="info-box">
        <strong>RED TRANSACCIONAL</strong> — Grafo dirigido de flujos entre clientes.
        Nodo = Cliente · Arista = Transacción (Origen → Destino).
        Detecta rutas multi-hop y clústeres de riesgo interconectados.
        Requiere la columna <code style="color:#f59e0b;">Cliente_Destino</code> en el Excel.
    </div>
    """, unsafe_allow_html=True)

    if not _NX_DISPONIBLE:
        st.error("""**networkx no está instalado.**
Ejecuta en tu terminal:
```
pip install networkx
```
Luego reinicia la aplicación.""")
        return

    # ── Verificar columna Cliente_Destino ─────────────────────────────────
    if "Cliente_Destino" not in df.columns or df["Cliente_Destino"].isna().all():
        st.warning("""**Columna `Cliente_Destino` no encontrada.**

Para utilizar este módulo, agrega la columna **`Cliente_Destino`** en tu archivo Excel con el cliente receptor de cada transacción.

| Cliente (Origen) | Cliente_Destino | Monto | Fecha |
|-----------------|-----------------|-------|-------|
| Juan Pérez      | María López     | 5,000 | 2024-01-15 |
| María López      | Carlos García   | 4,800 | 2024-01-16 |

Las filas sin destino (transferencias propias o sin contraparte) pueden dejarse en blanco.""")
        return

    # ── Preparación de datos ───────────────────────────────────────────────
    df_red = df.dropna(subset=["Cliente_Destino"]).copy()
    df_red["Cliente"] = df_red["Cliente"].apply(_normalizar_cliente)
    df_red["Cliente_Destino"] = df_red["Cliente_Destino"].apply(_normalizar_cliente)
    df_red["Monto"] = pd.to_numeric(df_red["Monto"], errors="coerce").fillna(0)
    df_red = df_red.dropna(subset=["Cliente", "Cliente_Destino"])

    # ── Filtros de visualización ───────────────────────────────────────────
    st.markdown("""
    <div class="info-box" style="border-left-color: #3b82f6;">
        <strong>GUÍA SENCILLA DE NAVEGACIÓN:</strong><br>
        • <b>Enfoque (Cliente Foco):</b> Elige a una persona específica para ver solo sus movimientos y contactos directos.<br>
        • <b>Niveles (Hops/Saltos):</b> Controla qué tan lejos quieres ver en la red (1 = contactos directos, 2 o más = conocidos de sus conocidos).<br>
        • <b>Frecuencia (Mínimo Txs):</b> Limpia el mapa ocultando relaciones ocasionales para concentrarse en clientes frecuentes.<br>
        • <b>Claridad (Relaciones Visibles):</b> Ajusta qué tan "cargado" se ve el gráfico, mostrando siempre los flujos de dinero más importantes.<br><br>
        <i><strong>Consejo:</strong> Si tienes muchos datos, elige un "Cliente Foco" y usa "1 o 2 Saltos" para que el mapa sea más fácil de leer.</i>
    </div>
    """, unsafe_allow_html=True)

    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        cliente_foco = st.selectbox(
            "Enfoque (Cliente Foco)",
            ["Todos"] + sorted(pd.unique(pd.concat([df_red["Cliente"], df_red["Cliente_Destino"]])).tolist())
        )
    with col_f2:
        nivel_filtro = st.multiselect(
            "Nivel de riesgo de nodos",
            ["Crítico", "Alto", "Medio", "Bajo"],
            default=["Crítico", "Alto", "Medio", "Bajo"]
        )
    with col_f3:
        monto_min = st.number_input(
            "Monto mínimo de arista (Q)",
            min_value=0, value=0, step=1000,
            help="Solo mostrar transacciones ≥ este monto."
        )

    col_f4, col_f5, col_f6 = st.columns(3)
    with col_f4:
        min_transacciones = st.number_input(
            "Frecuencia (Mínimo Txs)",
            min_value=1, value=1, step=1,
            help="Oculta relaciones aisladas o de muy baja recurrencia."
        )
    with col_f5:
        profundidad = st.select_slider(
            "Niveles (Hops/Saltos)",
            options=[1, 2, 3, 4],
            value=2,
            help="Si eliges un cliente foco, muestra relaciones hasta N saltos alrededor."
        )
    with col_f6:
        top_relaciones = st.select_slider(
            "Claridad (Relaciones Visibles)",
            options=[25, 50, 75, 100, 150, 300],
            value=75,
            help="Mantiene en pantalla las relaciones de mayor monto para facilitar lectura."
        )

    df_red = df_red[df_red["Monto"] >= monto_min]

    if df_red.empty:
        st.info("No hay transacciones con los filtros aplicados.")
        return

    # Mapa de scores por cliente
    score_map  = casos.set_index("Cliente")["Score_Max"].to_dict()
    nivel_map  = casos.set_index("Cliente")["Nivel_Riesgo"].to_dict()

    # Agregar aristas (agrupadas por par origen-destino)
    aristas = df_red.groupby(["Cliente", "Cliente_Destino"]).agg(
        monto_total=("Monto", "sum"),
        n_transacciones=("Monto", "count")
    ).reset_index()

    aristas["Nivel_Origen"] = aristas["Cliente"].map(nivel_map).fillna("Bajo")
    aristas["Nivel_Destino"] = aristas["Cliente_Destino"].map(nivel_map).fillna("Bajo")
    aristas = aristas[
        (aristas["Nivel_Origen"].isin(nivel_filtro)) |
        (aristas["Nivel_Destino"].isin(nivel_filtro))
    ]
    aristas = aristas[aristas["n_transacciones"] >= min_transacciones]

    if aristas.empty:
        st.info("No hay relaciones que cumplan el filtro de riesgo y recurrencia.")
        return

    if cliente_foco != "Todos":
        G_base = nx.from_pandas_edgelist(
            aristas,
            source="Cliente",
            target="Cliente_Destino",
            edge_attr=["monto_total", "n_transacciones"],
            create_using=nx.DiGraph()
        )
        nodos_focus = _nodos_en_hops(G_base, cliente_foco, profundidad)
        aristas = aristas[
            aristas["Cliente"].isin(nodos_focus) &
            aristas["Cliente_Destino"].isin(nodos_focus)
        ]

    aristas = aristas.sort_values(["monto_total", "n_transacciones"], ascending=[False, False]).head(top_relaciones)

    if aristas.empty:
        st.info("El cliente foco no tiene relaciones dentro de la profundidad seleccionada.")
        return

    G = nx.DiGraph()
    for _, row in aristas.iterrows():
        G.add_edge(
            row["Cliente"],
            row["Cliente_Destino"],
            monto=row["monto_total"],
            n_transacciones=row["n_transacciones"],
        )

    if G.number_of_nodes() == 0:
        st.info("El grafo no tiene nodos con los filtros actuales.")
        return

    # ── KPIs del grafo ────────────────────────────────────────────────────
    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    ciclos_detectados = "N/A"
    if G.number_of_nodes() <= 20 and G.number_of_edges() <= 40:
        ciclos_detectados = len(list(nx.simple_cycles(G)))

    kpi_vals = [
        (G.number_of_nodes(),  "Nodos (Clientes)",  "blue"),
        (G.number_of_edges(),  "Relaciones visibles", "amber"),
        (sum(1 for n in G.nodes if nivel_map.get(n, "Bajo") == "Crítico"), "Nodos Críticos", "red"),
        (ciclos_detectados,  "Ciclos Detectados", "green"),
    ]
    for col, (val, lbl, color) in zip([col_k1, col_k2, col_k3, col_k4], kpi_vals):
        with col:
            st.markdown(f"""
            <div class="metric-card {color}">
                <div class="metric-number">{val}</div>
                <div class="metric-label">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="info-box" style="margin-top:0;">
        <b>Vista aplicada:</b> se muestran hasta <b>{G.number_of_edges()}</b> relaciones agregadas por par origen-destino.
        {"La red está centrada en <b>" + cliente_foco + "</b> con profundidad de <b>" + str(profundidad) + " hop(s)</b>." if cliente_foco != "Todos" else "Para una trazabilidad más exacta, conviene enfocar un cliente y bajar la profundidad a 1 o 2 hops."}
    </div>
    """, unsafe_allow_html=True)

    # ── Layout de posiciones ───────────────────────────────────────────────
    nodos = list(G.nodes)
    try:
        # Intentar layout spring con networkx
        pos = nx.spring_layout(G, seed=42, k=2.5)
    except Exception:
        pos = _layout_circular(nodos)

    # ── Trazar aristas ─────────────────────────────────────────────────────
    edge_traces = []
    monto_max_arista = max((d["monto"] for _, _, d in G.edges(data=True)), default=1)

    mostrar_etiquetas = G.number_of_edges() <= 24

    for u, v, data in G.edges(data=True):
        if u not in pos or v not in pos:
            continue
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        monto_arista = data.get("monto", 0)
        n_tx_arista  = data.get("n_transacciones", 1)
        grosor = max(1, min(8, (monto_arista / monto_max_arista) * 8))
        alpha  = max(0.3, min(1.0, monto_arista / monto_max_arista))

        edge_traces.append(go.Scatter(
            x=[x0, x1, None], y=[y0, y1, None],
            mode="lines",
            line=dict(width=grosor, color=f"rgba(245,158,11,{alpha:.2f})"),
            hoverinfo="skip",
            showlegend=False,
        ))

        # Flecha indicadora de dirección (punto en mitad de la arista)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        edge_traces.append(go.Scatter(
            x=[mx], y=[my],
            mode="markers+text",
            marker=dict(symbol="arrow", size=10, color="#f59e0b",
                        angle=math.degrees(math.atan2(y1 - y0, x1 - x0))),
            text=[f"Q{monto_arista:,.0f}<br>{n_tx_arista} tx"] if mostrar_etiquetas else [""],
            textposition="top center",
            textfont=dict(color="#8b949e", size=9),
            hovertemplate=f"<b>{u} → {v}</b><br>Monto: Q{monto_arista:,.0f}<br>Transacciones: {n_tx_arista}<extra></extra>",
            showlegend=False,
        ))

    # ── Trazar nodos ────────────────────────────────────────────────────────
    node_x, node_y, node_colors, node_sizes, node_text, node_hover = [], [], [], [], [], []

    for nodo in nodos:
        if nodo not in pos:
            continue
        x, y = pos[nodo]
        score  = score_map.get(nodo, 0)
        nivel  = nivel_map.get(nodo, "Bajo")
        color  = _color_por_score(score)
        grado_entrada = G.in_degree(nodo)
        grado_salida  = G.out_degree(nodo)

        node_x.append(x)
        node_y.append(y)
        node_colors.append(color)
        node_sizes.append(max(18, min(45, 18 + score * 2.5)))
        node_text.append(nodo[:12] + "…" if len(nodo) > 12 else nodo)
        node_hover.append(
            f"<b>{nodo}</b><br>"
            f"Nivel: <b>{nivel}</b><br>"
            f"Score: <b>{score:.2f}/10</b><br>"
            f"Envía a: <b>{grado_salida}</b> nodo(s)<br>"
            f"Recibe de: <b>{grado_entrada}</b> nodo(s)"
        )

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(color="#0d1117", width=2),
        ),
        text=node_text,
        textposition="top center",
        textfont=dict(color="#c9d1d9", size=10),
        hovertemplate="%{customdata}<extra></extra>",
        customdata=node_hover,
        name="Clientes",
    )

    # ── Figura final ────────────────────────────────────────────────────────
    fig = go.Figure(data=[*edge_traces, node_trace])
    fig.update_layout(
        paper_bgcolor="#0f141b",
        plot_bgcolor="#0f141b",
        font=dict(color="#dee2ed", family="IBM Plex Mono"),
        height=620,
        margin=dict(t=30, b=20, l=20, r=20),
        showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        hoverlabel=dict(
            bgcolor="#1b2027",
            bordercolor="#f59e0b",
            font=dict(color="#dee2ed", family="IBM Plex Mono", size=12),
        ),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown('<div class="section-title">Relaciones Visibles y Trazabilidad Base</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        Esta tabla suele ser la vista más útil cuando la red ya tiene demasiados nodos: resume cada relación,
        su recurrencia, monto y el nivel de riesgo de ambos extremos.
    </div>
    """, unsafe_allow_html=True)

    df_relaciones = aristas.rename(columns={
        "Cliente": "Cliente origen",
        "Cliente_Destino": "Cliente destino",
        "monto_total": "Monto total",
        "n_transacciones": "Núm. transacciones",
        "Nivel_Origen": "Nivel origen",
        "Nivel_Destino": "Nivel destino",
    }).copy()
    df_relaciones["Monto total"] = df_relaciones["Monto total"].map(lambda v: f"Q{v:,.2f}")
    st.markdown(render_html_table(df_relaciones, max_height=520), unsafe_allow_html=True)

    # Leyenda de colores
    st.markdown("""
    <div class="info-box" style="margin-top:5px;">
        <b>Leyenda:</b>
        <span style="color:#ef4444; font-weight:700;">● Crítico</span> &nbsp;
        <span style="color:#f97316; font-weight:700;">● Alto</span> &nbsp;
        <span style="color:#eab308; font-weight:700;">● Medio</span> &nbsp;
        <span style="color:#22c55e; font-weight:700;">● Bajo</span> &nbsp; — &nbsp;
        El <b>tamaño del nodo</b> refleja el score. El <b>grosor de la arista</b> representa el monto transado.
        Las <b>flechas</b> indican la dirección del flujo (Origen → Destino).
        Las <b>etiquetas de arista</b> se ocultan automáticamente cuando la red tiene demasiadas relaciones para evitar saturación visual.
    </div>
    """, unsafe_allow_html=True)

    # ── TABLA DE RUTAS MULTI-HOP ───────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-title">Rutas Multi-Hop Detectadas</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box" style="border-left-color: #ef4444;">
        <strong>Análisis de encadenamiento:</strong> Rutas donde el dinero pasa por ≥2 clientes intermedios.
        Patrón típico de <em>layering</em> (estratificación) en esquemas de LD/FT.
    </div>
    """, unsafe_allow_html=True)

    rutas = []
    max_rutas = 200
    cutoff_rutas = max(2, profundidad + 1 if cliente_foco != "Todos" else 3)

    if G.number_of_nodes() > 25 and cliente_foco == "Todos":
        st.info("La detección de rutas multi-hop se vuelve más útil cuando eliges un cliente foco. Con la red completa puede generar demasiadas combinaciones.")
    else:
        for nodo in nodos:
            if len(rutas) >= max_rutas:
                break
            for target in nodos:
                if nodo == target or len(rutas) >= max_rutas:
                    continue
                try:
                    for path in nx.all_simple_paths(G, nodo, target, cutoff=cutoff_rutas):
                        if len(path) >= 3:  # al menos 1 intermediario
                            scores_ruta = [score_map.get(n, 0) for n in path]
                            rutas.append({
                                "Ruta": " → ".join(path),
                                "Saltos": len(path) - 1,
                                "Score máx. en ruta": f"{max(scores_ruta):.2f}",
                                "Cliente origen": path[0],
                                "Cliente destino": path[-1],
                            })
                            if len(rutas) >= max_rutas:
                                break
                except Exception:
                    pass

        if rutas:
            df_rutas = pd.DataFrame(rutas).drop_duplicates(subset=["Ruta"]).sort_values(["Saltos", "Score máx. en ruta"], ascending=[False, False])
            st.markdown(render_html_table(df_rutas, max_height=420), unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#6e7681; font-size:13px; padding:8px 0;">No se detectaron rutas multi-hop con los filtros actuales.</div>', unsafe_allow_html=True)

    # ── CENTRALIDAD DE NODOS ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown('<div class="section-title">Centralidad de Nodos (Importancia en la Red)</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        La <b>centralidad de intermediario (betweenness)</b> identifica nodos que actúan como puente en la red.
        Un valor alto indica que el cliente está en el camino de muchas rutas de flujo — señal de posible <em>cuenta puente</em>.
    </div>
    """, unsafe_allow_html=True)

    centralidad = nx.betweenness_centrality(G, normalized=True)
    df_central = pd.DataFrame([
        {
            "Cliente": n,
            "Centralidad": f"{v:.4f}",
            "Nivel Riesgo": nivel_map.get(n, "—"),
            "Score": f"{score_map.get(n, 0):.2f}",
            "Grado Entrada": G.in_degree(n),
            "Grado Salida": G.out_degree(n),
        }
        for n, v in sorted(centralidad.items(), key=lambda x: -x[1])
    ])
    st.markdown(render_html_table(df_central, max_height=420), unsafe_allow_html=True)
