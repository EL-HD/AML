import plotly.graph_objects as go

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
