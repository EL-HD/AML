import plotly.graph_objects as go
from html import escape

def apply_dark_style(fig, ax):
    """Aplica el tema oscuro consistente a todas las gráficas (Matplotlib)."""
    fig.patch.set_facecolor('#0f141b')
    ax.set_facecolor('#171c23')
    ax.tick_params(colors='#8b949e', labelsize=9)
    ax.xaxis.label.set_color('#dee2ed')
    ax.yaxis.label.set_color('#dee2ed')
    for spine in ax.spines.values():
        spine.set_color('#534434')
    ax.grid(color='#534434', linewidth=0.5, linestyle='--', alpha=0.3)
    return fig, ax

def plotly_dark_layout(**kwargs):
    """Devuelve un dict de layout Plotly con el tema 'Sovereign Intelligence'."""
    base = dict(
        paper_bgcolor='#0f141b',
        plot_bgcolor='#171c23',
        font=dict(family='IBM Plex Sans, sans-serif', color='#dee2ed', size=12),
        xaxis=dict(
            gridcolor='rgba(83, 68, 52, 0.2)', 
            linecolor='#534434', 
            tickfont=dict(color='#d8c3ad'),
            zeroline=False
        ),
        yaxis=dict(
            gridcolor='rgba(83, 68, 52, 0.2)', 
            linecolor='#534434', 
            tickfont=dict(color='#d8c3ad'),
            zeroline=False
        ),
        margin=dict(l=40, r=20, t=30, b=40),
        hoverlabel=dict(
            bgcolor='#1b2027', 
            bordercolor='#f59e0b',
            font=dict(family='IBM Plex Mono, monospace', color='#dee2ed', size=12)
        ),
        legend=dict(
            bgcolor='rgba(15, 20, 27, 0.8)', 
            bordercolor='#534434', 
            font=dict(color='#dee2ed')
        ),
    )
    base.update(kwargs)
    return base


def render_html_table(df, max_height=420, table_id=None):
    """
    Renderiza una tabla HTML estática y nítida con la paleta de Sovereign AML.
    Útil para evitar el blur que puede aparecer con st.dataframe en columnas.
    """
    css = """
        <style>
            .sovereign-table-wrap {
                width: 100%;
                overflow: auto;
                border: 1px solid #30353d;
                border-top: 3px solid #f59e0b;
                background: #171c23;
                box-shadow: inset 0 1px 0 rgba(245, 158, 11, 0.12);
                -webkit-font-smoothing: antialiased;
                text-rendering: geometricPrecision;
            }
            .sovereign-table {
                width: 100%;
                min-width: 760px;
                border-collapse: collapse;
                table-layout: auto;
                color: #1f2937;
                font-family: Manrope, Arial, sans-serif;
                font-size: 14px;
                line-height: 1.35;
                background: #ffffff;
            }
            .sovereign-table th,
            .sovereign-table td {
                padding: 13px 16px;
                text-align: left;
                border-right: 1px solid #e5e7eb;
                border-bottom: 1px solid #e5e7eb;
                white-space: nowrap;
                vertical-align: middle;
            }
            .sovereign-table th {
                position: sticky;
                top: 0;
                z-index: 2;
                background: #fff7ed;
                color: #5f3b0a;
                font-weight: 800;
            }
            .sovereign-table td {
                color: #1f2937;
                font-weight: 600;
            }
            .sovereign-table tbody tr:nth-child(even) td {
                background: #f9fafb;
            }
            .sovereign-table tbody tr:hover td {
                background: #fffbeb;
            }
            .sovereign-table th:last-child,
            .sovereign-table td:last-child {
                border-right: none;
            }
            .sovereign-table tbody tr:last-child td {
                border-bottom: none;
            }
        </style>
    """

    attrs = f' id="{escape(str(table_id))}"' if table_id else ""
    headers = "".join(f"<th>{escape(str(col))}</th>" for col in df.columns)
    rows = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in row)
        rows.append(f"<tr>{cells}</tr>")

    return f"""
    {css}
    <div class="sovereign-table-wrap" style="max-height:{int(max_height)}px;">
        <table class="sovereign-table"{attrs}>
            <thead><tr>{headers}</tr></thead>
            <tbody>{''.join(rows)}</tbody>
        </table>
    </div>
    """
