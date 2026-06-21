import streamlit as st
import io
import datetime
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors as rl_colors

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image as RLImage, KeepTogether
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import re as _re

TIPOS_REPORTE = {
    "INDIVIDUAL": "Ficha de Investigación por Cliente",
    "EJECUTIVO":  "Informe Ejecutivo General",
    "RTS":        "Reporte de Transacción Sospechosa (Art. 30 Ley 6593)",
    "RTE":        "Reporte de Transacción en Efectivo (Art. 31 Ley 6593)",
}

# ── Paleta y helpers (SOVEREIGN AML + IMPERATOR) ─────────────────────
C_BG        = rl_colors.HexColor("#0f141b")
C_PANEL     = rl_colors.HexColor("#171c23")
C_BORDER    = rl_colors.HexColor("#534434")
C_AMBER     = rl_colors.HexColor("#f59e0b")
C_BLUE      = rl_colors.HexColor("#3b82f6")
C_RED       = rl_colors.HexColor("#ef4444")
C_ORANGE    = rl_colors.HexColor("#f97316")
C_YELLOW    = rl_colors.HexColor("#eab308")
C_GREEN     = rl_colors.HexColor("#10b981")
C_TEXT      = rl_colors.HexColor("#111827")
C_MUTED     = rl_colors.HexColor("#5b6472")
C_MUTED_LT  = rl_colors.HexColor("#d8c3ad")
C_WHITE     = rl_colors.HexColor("#ffffff")
C_HEADER_BG = rl_colors.HexColor("#1b2027")
C_TABLE_BG  = rl_colors.HexColor("#ffffff")
C_ROW_EVEN  = rl_colors.HexColor("#f8fafc")
C_ROW_ALT   = rl_colors.HexColor("#eef2f7")
C_TABLE_GRID= rl_colors.HexColor("#d7dee8")

def nivel_color_rl(nivel: str):
    if "Crítico" in nivel: return C_RED
    if "Alto"    in nivel: return C_ORANGE
    if "Medio"   in nivel: return C_YELLOW
    return C_GREEN

def nivel_label(nivel: str) -> str:
    return _re.sub(r'[^\u0000-\u024F\s]', '', nivel).strip()

def fig_to_image(fig, width_inch=6.5, height_inch=2.8, dpi=140):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return RLImage(buf, width=width_inch * inch, height=height_inch * inch)

def dark_fig(w=9, h=3):
    fig, ax = plt.subplots(figsize=(w, h))
    fig.patch.set_facecolor("#0f141b")
    ax.set_facecolor("#171c23")
    ax.tick_params(colors="#a08e7a", labelsize=8)
    for sp in ax.spines.values(): sp.set_color("#534434")
    ax.grid(color="#534434", linewidth=0.4, linestyle="--", alpha=0.3)
    ax.xaxis.label.set_color("#dee2ed")
    ax.yaxis.label.set_color("#dee2ed")
    return fig, ax

# ── Estilos ReportLab ─────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()
    S = {}
    S["cover_title"] = ParagraphStyle("cover_title",
        fontSize=26, textColor=C_WHITE, fontName="Helvetica-Bold",
        alignment=TA_CENTER, spaceAfter=6)
    S["cover_sub"] = ParagraphStyle("cover_sub",
        fontSize=11, textColor=C_AMBER, fontName="Helvetica",
        alignment=TA_CENTER, spaceAfter=4)
    S["cover_meta"] = ParagraphStyle("cover_meta",
        fontSize=9, textColor=C_MUTED_LT, fontName="Helvetica",
        alignment=TA_CENTER, spaceAfter=2)
    S["section"] = ParagraphStyle("section",
        fontSize=13, textColor=C_AMBER, fontName="Helvetica-Bold",
        spaceBefore=14, spaceAfter=6)
    S["subsection"] = ParagraphStyle("subsection",
        fontSize=10, textColor=C_BLUE, fontName="Helvetica-Bold",
        spaceBefore=8, spaceAfter=4)
    S["body"] = ParagraphStyle("body",
        fontSize=9, textColor=C_TEXT, fontName="Helvetica",
        leading=14, spaceAfter=4, alignment=TA_JUSTIFY)
    S["body_small"] = ParagraphStyle("body_small",
        fontSize=8, textColor=C_MUTED, fontName="Helvetica",
        leading=12, spaceAfter=2)
    S["label"] = ParagraphStyle("label",
        fontSize=8, textColor=C_MUTED_LT, fontName="Helvetica",
        alignment=TA_CENTER)
    S["value"] = ParagraphStyle("value",
        fontSize=18, textColor=C_WHITE, fontName="Helvetica-Bold",
        alignment=TA_CENTER)
    S["footer_txt"] = ParagraphStyle("footer_txt",
        fontSize=7, textColor=C_MUTED, fontName="Helvetica",
        alignment=TA_CENTER)
    S["alert_ok"]  = ParagraphStyle("alert_ok",  fontSize=8, textColor=C_GREEN,  fontName="Helvetica-Bold")
    S["alert_bad"] = ParagraphStyle("alert_bad", fontSize=8, textColor=C_RED,    fontName="Helvetica-Bold")
    S["tbl_head"]  = ParagraphStyle("tbl_head",  fontSize=8, textColor=C_WHITE,  fontName="Helvetica-Bold", alignment=TA_CENTER)
    S["tbl_cell"]  = ParagraphStyle("tbl_cell",  fontSize=8, textColor=C_TEXT, fontName="Helvetica", alignment=TA_CENTER)
    S["tbl_cell_l"]= ParagraphStyle("tbl_cell_l",fontSize=8, textColor=C_TEXT, fontName="Helvetica", alignment=TA_LEFT)
    return S

def header_band(title: str, subtitle: str = "") -> Table:
    rows = [[Paragraph(title, ParagraphStyle("hb_t", fontSize=12,
                textColor=C_AMBER, fontName="Helvetica-Bold"))]]
    if subtitle:
        rows.append([Paragraph(subtitle, ParagraphStyle("hb_s", fontSize=8,
                textColor=C_MUTED_LT, fontName="Helvetica"))])
    t = Table(rows, colWidths=[7.0 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), C_PANEL),
        ("LEFTPADDING",  (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING",   (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 8),
        ("LINEBELOW",   (0, -1), (-1, -1), 1.5, C_AMBER),
    ]))
    return t

def kpi_row(items: list) -> Table:
    S = make_styles()
    n = len(items)
    w = 7.0 / n
    data = [[
        Table([
            [Paragraph(v, ParagraphStyle("kv", fontSize=20, textColor=c,
                fontName="Helvetica-Bold", alignment=TA_CENTER))],
            [Paragraph(l, S["label"])],
        ], colWidths=[w * inch - 8],
        style=TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), C_PANEL),
            ("BOX", (0,0),(-1,-1), 0.5, C_BORDER),
            ("TOPPADDING",(0,0),(-1,-1),10),
            ("BOTTOMPADDING",(0,0),(-1,-1),10),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
        ]))
        for l, v, c in items
    ]]
    t = Table(data, colWidths=[w * inch] * n)
    t.setStyle(TableStyle([
        ("LEFTPADDING",  (0,0),(-1,-1), 3),
        ("RIGHTPADDING", (0,0),(-1,-1), 3),
        ("TOPPADDING",   (0,0),(-1,-1), 0),
        ("BOTTOMPADDING",(0,0),(-1,-1), 0),
    ]))
    return t

def df_to_table(df_t: pd.DataFrame, col_widths=None, zebra=True) -> Table:
    S = make_styles()
    headers = [Paragraph(c, S["tbl_head"]) for c in df_t.columns]
    rows = [headers]
    for _, row in df_t.iterrows():
        rows.append([Paragraph(str(v), S["tbl_cell"]) for v in row])
    if col_widths is None:
        col_widths = [7.0 / len(df_t.columns) * inch] * len(df_t.columns)
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND",    (0,0), (-1,0), C_HEADER_BG),
        ("ROWBACKGROUNDS",(0,1), (-1,-1), [C_ROW_EVEN, C_ROW_ALT] if zebra else [C_TABLE_BG]),
        ("GRID",          (0,0), (-1,-1), 0.4, C_TABLE_GRID),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t

def page_header_footer(canvas_obj, doc, report_title, fecha_str):
    canvas_obj.saveState()
    W, H = A4

    def draw_tricolor_band(y, height):
        colors = [C_AMBER, C_BLUE, C_ORANGE]
        segment_w = W / 6.0
        x = 0
        idx = 0
        while x < W:
            canvas_obj.setFillColor(colors[idx % len(colors)])
            width = min(segment_w, W - x)
            canvas_obj.rect(x, y, width, height, fill=1, stroke=0)
            x += width
            idx += 1

    canvas_obj.setFillColor(C_BG)
    canvas_obj.rect(0, H - 36, W, 36, fill=1, stroke=0)
    draw_tricolor_band(H - 39, 2.4)
    canvas_obj.setFont("Helvetica-Bold", 9)
    canvas_obj.setFillColor(C_WHITE)
    canvas_obj.drawString(1.0 * inch, H - 21, "SOVEREIGN AML")
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.setFillColor(C_MUTED_LT)
    canvas_obj.drawString(1.0 * inch, H - 30, "Powered by IMPERATOR")
    canvas_obj.drawRightString(W - 1.0 * inch, H - 24, report_title)
    
    canvas_obj.setFillColor(C_BG)
    canvas_obj.rect(0, 0, W, 28, fill=1, stroke=0)
    canvas_obj.setFillColor(C_BORDER)
    canvas_obj.rect(0, 28, W, 0.5, fill=1, stroke=0)
    draw_tricolor_band(28, 2.2)
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.setFillColor(C_MUTED_LT)
    canvas_obj.drawString(1.0 * inch, 10, f"Confidencial \u00b7 Uso interno \u00b7 {fecha_str}")
    canvas_obj.drawCentredString(W / 2, 10, "Powered by IMPERATOR \u00b7 Ing. Hob\u00e9d D\u00edaz, Msc. M.A.F.I")
    canvas_obj.drawRightString(W - 1.0 * inch, 10, f"P\u00e1gina {doc.page}")
    canvas_obj.restoreState()


def mostrar(df, casos, matriz_alertas, cfg):

    def generar_reporte_cliente(cliente_sel: str) -> bytes:
        fecha_gen = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        S = make_styles()
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.0*inch, rightMargin=1.0*inch,
            topMargin=1.1*inch, bottomMargin=0.7*inch,
        )

        def _hf(c, d):
            page_header_footer(c, d, f"Ficha de Cliente \u00b7 {cliente_sel}", fecha_gen)

        story = []

        info_c    = casos[casos["Cliente"] == cliente_sel].iloc[0]
        datos_c   = df[df["Cliente"] == cliente_sel].sort_values("Fecha")
        nivel_c   = info_c["Nivel_Riesgo"]
        color_c   = nivel_color_rl(nivel_c)
        label_c   = nivel_label(nivel_c)
        score_c   = int(info_c["Score_Max"])
        total_c   = float(info_c["Total_Mensual"])
        tx_c      = int(info_c["Transacciones"])
        perfil_c  = float(datos_c["Perfil"].iloc[0])
        fecha_min = datos_c["Fecha"].min().strftime("%d/%m/%Y")
        fecha_max = datos_c["Fecha"].max().strftime("%d/%m/%Y")

        cover_data = [[
            Table([
                [Paragraph("FICHA DE INVESTIGACI\u00d3N \u00b7 SOVEREIGN AML", ParagraphStyle("ct",
                    fontSize=9, textColor=C_AMBER, fontName="Helvetica-Bold",
                    alignment=TA_CENTER, spaceAfter=2))],
                [Paragraph(str(cliente_sel), ParagraphStyle("cn",
                    fontSize=22, textColor=C_WHITE, fontName="Helvetica-Bold",
                    alignment=TA_CENTER, spaceAfter=4))],
                [Paragraph("Powered by IMPERATOR", ParagraphStyle("cp",
                    fontSize=10, textColor=C_BLUE, fontName="Helvetica-Bold",
                    alignment=TA_CENTER, spaceAfter=4))],
                [Paragraph(f"Per\u00edodo: {fecha_min} \u2013 {fecha_max}  \u00b7  Generado: {fecha_gen}",
                    S["cover_meta"])],
            ], colWidths=[6.5*inch],
            style=TableStyle([
                ("BACKGROUND",     (0,0),(-1,-1), C_HEADER_BG),
                ("LINEBELOW",      (0,-1),(-1,-1), 3, color_c),
                ("LINEABOVE",      (0,0),(-1,0),  3, C_AMBER),
                ("TOPPADDING",     (0,0),(-1,-1), 14),
                ("BOTTOMPADDING",  (0,0),(-1,-1), 14),
            ]))
        ]]
        story.append(Table(cover_data, colWidths=[7.0*inch]))
        story.append(Spacer(1, 14))

        score_max_teorico = sum([cfg["peso_absoluto"], cfg["peso_acumulado"],
                                 cfg["peso_perfil"], cfg["peso_frecuencia"],
                                 cfg["peso_smurfing"], cfg["peso_pico"]])
        story.append(kpi_row([
            ("Nivel de Riesgo",   label_c,                  color_c),
            ("Score IMPERATOR",   f"{score_c}/{score_max_teorico}", C_AMBER),
            ("Total Transaccionado", f"Q{total_c:,.0f}",    C_BLUE),
            ("Num. Operaciones",  str(tx_c),                C_WHITE),
        ]))
        story.append(Spacer(1, 14))

        C_ROW_EVEN = rl_colors.HexColor("#f8fafc")
        C_ROW_ALT  = rl_colors.HexColor("#eef2f7")
        C_TXT_W    = C_TEXT

        S_CELL   = ParagraphStyle("sc",  fontSize=8, textColor=C_TXT_W, fontName="Helvetica", alignment=TA_CENTER)
        S_CELL_L = ParagraphStyle("scl", fontSize=8, textColor=C_TXT_W, fontName="Helvetica", alignment=TA_LEFT)

        story.append(header_band("1. PERFIL DE ALERTAS DETECTADAS",
            "Detalle de cada regla AML y su estado para este cliente"))
        story.append(Spacer(1, 6))

        alertas_info = [
            ("Monto Alto (Absoluto)", bool(datos_c["Alerta_Absoluto"].any()),
             f"Umbral: Q{cfg['umbral_absoluto']:,}",  cfg["peso_absoluto"]),
            ("Acumulado Mensual",     bool(datos_c["Alerta_Acumulado"].any()),
             f"Multiplicador: {cfg['mult_acumulado']}x perfil", cfg["peso_acumulado"]),
            ("Exceso sobre Perfil",   bool(datos_c["Alerta_15"].any()),
             f"Tolerancia: {cfg['tolerancia_perfil']}%", cfg["peso_perfil"]),
            ("Frecuencia Alta",       bool(datos_c["Alerta_Frecuencia"].any()),
             f"Umbral: >{cfg['umbral_frecuencia']} transacciones", cfg["peso_frecuencia"]),
            ("Smurfing (fragmentacion)", bool(datos_c["Smurfing"].any()),
             f"Umbral: >={cfg['umbral_smurfing']} ops/dia", cfg["peso_smurfing"]),
            ("Pico Anomalo",          bool(datos_c["Pico"].any()),
             f"Umbral: media + {cfg['mult_std_pico']}*sigma", cfg["peso_pico"]),
        ]

        alerta_rows = [[
            Paragraph("Regla AML", S["tbl_head"]),
            Paragraph("Estado", S["tbl_head"]),
            Paragraph("Parametro", S["tbl_head"]),
             Paragraph("Peso", S["tbl_head"]),
             Paragraph("Contribucion al Score", S["tbl_head"]),
        ]]
        for nombre_a, activa_a, param_a, peso_a in alertas_info:
            contrib_a = peso_a if activa_a else 0
            estado_p  = Paragraph("ACTIVA", ParagraphStyle("ae", fontSize=8,
                            textColor=C_RED, fontName="Helvetica-Bold", alignment=TA_CENTER)) \
                        if activa_a else \
                        Paragraph("--", ParagraphStyle("ao", fontSize=8,
                            textColor=C_GREEN, fontName="Helvetica-Bold", alignment=TA_CENTER))
            alerta_rows.append([
                Paragraph(nombre_a, S_CELL_L),
                estado_p,
                Paragraph(param_a, S_CELL),
                Paragraph(str(peso_a), S_CELL),
                Paragraph(str(contrib_a), ParagraphStyle("ac", fontSize=8,
                    textColor=C_AMBER if activa_a else C_TXT_W,
                    fontName="Helvetica-Bold", alignment=TA_CENTER)),
            ])

        t_alertas = Table(alerta_rows, colWidths=[2.2*inch, 0.8*inch, 1.5*inch, 0.6*inch, 1.4*inch])
        t_alertas.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  C_HEADER_BG),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_ROW_EVEN, C_ROW_ALT]),
            ("GRID",          (0,0),(-1,-1), 0.4, C_TABLE_GRID),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        story.append(t_alertas)
        story.append(Spacer(1, 14))

        story.append(header_band("2. ESTADISTICAS DEL CLIENTE",
            "Resumen estadistico del comportamiento transaccional"))
        story.append(Spacer(1, 6))

        media_c = float(datos_c["Media"].iloc[0])
        std_c   = float(datos_c["Std"].iloc[0]) if datos_c["Std"].iloc[0] > 0 else 0
        monto_max_c = float(datos_c["Monto"].max())
        monto_min_c = float(datos_c["Monto"].min())
        picos_cnt   = int(datos_c["Pico"].sum())
        smurf_dias  = int(datos_c["Smurfing"].sum())

        stat_data = [
            [Paragraph("Indicador", S["tbl_head"]), Paragraph("Valor", S["tbl_head"]),
             Paragraph("Indicador", S["tbl_head"]), Paragraph("Valor", S["tbl_head"])],
            [Paragraph("Perfil esperado", S_CELL_L),
             Paragraph(f"Q{perfil_c:,.0f}", S_CELL),
             Paragraph("Total transaccionado", S_CELL_L),
             Paragraph(f"Q{total_c:,.0f}", S_CELL)],
            [Paragraph("Monto promedio", S_CELL_L),
             Paragraph(f"Q{media_c:,.0f}", S_CELL),
             Paragraph("Desv. estandar", S_CELL_L),
             Paragraph(f"Q{std_c:,.0f}", S_CELL)],
            [Paragraph("Monto maximo", S_CELL_L),
             Paragraph(f"Q{monto_max_c:,.0f}", S_CELL),
             Paragraph("Monto minimo", S_CELL_L),
             Paragraph(f"Q{monto_min_c:,.0f}", S_CELL)],
            [Paragraph("N. operaciones", S_CELL_L),
             Paragraph(str(tx_c), S_CELL),
             Paragraph("Picos anomalos", S_CELL_L),
             Paragraph(str(picos_cnt), ParagraphStyle("ps", fontSize=8,
                 textColor=C_RED if picos_cnt > 0 else C_GREEN,
                 fontName="Helvetica-Bold", alignment=TA_CENTER))],
            [Paragraph("Score IMPERATOR maximo", S_CELL_L),
             Paragraph(str(score_c), ParagraphStyle("ss", fontSize=8,
                 textColor=color_c, fontName="Helvetica-Bold", alignment=TA_CENTER)),
             Paragraph("Dias con smurfing", S_CELL_L),
             Paragraph(str(smurf_dias), ParagraphStyle("sd", fontSize=8,
                 textColor=C_RED if smurf_dias > 0 else C_GREEN,
                 fontName="Helvetica-Bold", alignment=TA_CENTER))],
        ]
        t_stats = Table(stat_data, colWidths=[2.0*inch, 1.5*inch, 2.0*inch, 1.5*inch])
        t_stats.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  C_HEADER_BG),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_ROW_EVEN, C_ROW_ALT]),
            ("GRID",          (0,0),(-1,-1), 0.4, C_TABLE_GRID),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        story.append(t_stats)
        story.append(Spacer(1, 14))
        
        hb_graficas = header_band("3. ANALISIS VISUAL DEL COMPORTAMIENTO",
            "Evolucion de montos, deteccion de picos y frecuencia operativa")

        datos_c["Fecha_str"] = datos_c["Fecha"].dt.strftime("%d/%m")

        fig, ax = dark_fig(9, 3)
        ax.plot(datos_c["Fecha_str"], datos_c["Monto"],
                color="#3b82f6", marker='o', markersize=4, linewidth=1.8, label="Monto")
        ax.axhline(y=perfil_c, linestyle='--', color="#f59e0b",
                   linewidth=1.3, alpha=0.9, label=f"Perfil: Q{perfil_c:,.0f}")
        above = datos_c["Monto"].values > perfil_c
        ax.fill_between(range(len(datos_c)), datos_c["Monto"].values,
                        perfil_c, where=above, alpha=0.15, color="#ef4444")
        ax.legend(facecolor='#161b22', edgecolor='#21262d',
                  labelcolor='#c9d1d9', fontsize=8)
        ax.set_title("Evolucion de Montos vs Perfil Esperado",
                     color="#c9d1d9", fontsize=9, pad=8)
        plt.xticks(rotation=40, ha='right', fontsize=7)
        plt.tight_layout()
        story.append(KeepTogether([hb_graficas, Spacer(1, 8), fig_to_image(fig, 6.5, 2.7)]))
        story.append(Spacer(1, 8))

        fig2, ax2 = dark_fig(9, 2.8)
        ax2.plot(datos_c["Fecha_str"], datos_c["Monto"],
                 color="#58a6ff", marker='o', markersize=3, linewidth=1.3, alpha=0.75)
        picos_g = datos_c[datos_c["Pico"] == True]
        if len(picos_g):
            ax2.scatter(picos_g["Fecha_str"], picos_g["Monto"],
                        color="#ef4444", s=80, zorder=5, label=f"{len(picos_g)} pico(s)")
        ax2.axhline(y=media_c, linestyle=':', color='#8b949e', linewidth=1, alpha=0.6, label='Media')
        if std_c > 0:
            ax2.axhline(y=media_c + cfg["mult_std_pico"]*std_c,
                        linestyle='--', color='#ef4444', linewidth=1, alpha=0.5,
                        label=f'Media + {cfg["mult_std_pico"]}\u03c3')
        ax2.legend(facecolor='#161b22', edgecolor='#21262d',
                   labelcolor='#c9d1d9', fontsize=8)
        ax2.set_title("Deteccion de Picos Anomalos", color="#c9d1d9", fontsize=9, pad=8)
        plt.xticks(rotation=40, ha='right', fontsize=7)
        plt.tight_layout()
        story.append(fig_to_image(fig2, 6.5, 2.5))
        story.append(Spacer(1, 8))

        fig3, ax3 = dark_fig(9, 2.5)
        freq_d = datos_c.groupby("Fecha_str").size().reset_index(name="N")
        bar_cols = ["#ef4444" if v >= cfg["umbral_smurfing"] else "#3b82f6"
                    for v in freq_d["N"]]
        ax3.bar(freq_d["Fecha_str"], freq_d["N"],
                color=bar_cols, edgecolor='#0d1117', linewidth=0.4)
        ax3.axhline(y=cfg["umbral_smurfing"], linestyle='--',
                    color='#f59e0b', linewidth=1.2, alpha=0.8,
                    label=f'Umbral smurfing ({cfg["umbral_smurfing"]})')
        ax3.legend(facecolor='#161b22', edgecolor='#21262d',
                   labelcolor='#c9d1d9', fontsize=8)
        ax3.set_title("Frecuencia Diaria de Operaciones",
                      color="#c9d1d9", fontsize=9, pad=8)
        plt.xticks(rotation=40, ha='right', fontsize=7)
        plt.tight_layout()
        story.append(fig_to_image(fig3, 6.5, 2.3))
        story.append(Spacer(1, 14))
        
        story.append(header_band("4. DETALLE DE TRANSACCIONES",
            "Registro completo de operaciones con alertas activas marcadas"))
        story.append(Spacer(1, 6))

        tx_display = datos_c[["Fecha", "Monto", "Alerta_Absoluto",
                               "Alerta_15", "Smurfing", "Pico", "Score"]].copy()
        tx_display["Fecha"]   = tx_display["Fecha"].dt.strftime("%d/%m/%Y")
        tx_display["Monto"]   = tx_display["Monto"].apply(lambda x: f"Q{x:,.0f}")
        bool_cols = ["Alerta_Absoluto", "Alerta_15", "Smurfing", "Pico"]
        for bc in bool_cols:
            tx_display[bc] = tx_display[bc].apply(lambda x: "SI" if x else "\u2014")
        tx_display.columns = ["Fecha", "Monto", "Mto.Alto", "Exc.Perfil",
                               "Smurfing", "Pico", "Score"]

        story.append(df_to_table(
            tx_display,
            col_widths=[0.9*inch, 1.1*inch, 0.85*inch, 0.85*inch, 0.85*inch, 0.7*inch, 0.75*inch]
        ))
        story.append(Spacer(1, 14))

        story.append(header_band("5. CONCLUSION Y ACCION RECOMENDADA"))
        story.append(Spacer(1, 6))

        if "Cr\u00edtico" in nivel_c:
            concl = (f"El cliente <b>{cliente_sel}</b> presenta un nivel de riesgo <b>CRITICO</b> "
                     f"con score AML de {score_c}/{score_max_teorico} y un volumen mensual de "
                     f"Q{total_c:,.0f}. Se recomienda iniciar una investigacion formal inmediata, "
                     f"documentar el expediente y evaluar la presentacion de un "
                     f"Reporte de Transaccion Sospechosa (RTS) ante la SIB (mediante la IVE).")
            accion = "ACCION INMEDIATA: Bloquear operaciones, notificar al Oficial de Cumplimiento y activar protocolo RTS."
            accion_color = C_RED
        elif "Alto" in nivel_c:
            concl = (f"El cliente <b>{cliente_sel}</b> presenta un nivel de riesgo <b>ALTO</b> "
                     f"con score AML de {score_c}/{score_max_teorico}. Se recomienda actualizar "
                     f"el perfil del cliente, solicitar documentacion de soporte para las "
                     f"transacciones marcadas y mantener monitoreo intensificado.")
            accion = "SEGUIMIENTO PRIORITARIO: Actualizar perfil KYC y revisar en los proximos 5 dias habiles."
            accion_color = C_ORANGE
        elif "Medio" in nivel_c:
            concl = (f"El cliente <b>{cliente_sel}</b> presenta alertas de nivel <b>MEDIO</b> "
                     f"con score AML de {score_c}/{score_max_teorico}. Se recomienda incluirlo "
                     f"en el ciclo de monitoreo preventivo del siguiente periodo.")
            accion = "MONITOREO PREVENTIVO: Incluir en revision mensual del siguiente periodo."
            accion_color = C_YELLOW
        else:
            concl = (f"El cliente <b>{cliente_sel}</b> no presenta alertas significativas en "
                     f"el periodo analizado. Score IMPERATOR: {score_c}/{score_max_teorico}.")
            accion = "SIN ACCION REQUERIDA: Continuar monitoreo rutinario."
            accion_color = C_GREEN

        story.append(Paragraph(concl, S["body"]))
        story.append(Spacer(1, 8))

        accion_t = Table([[Paragraph(accion, ParagraphStyle("ac_t",
            fontSize=9, textColor=accion_color, fontName="Helvetica-Bold"))]],
            colWidths=[7.0*inch])
        accion_t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C_PANEL),
            ("LINEBELOW",     (0,-1),(-1,-1), 2, accion_color),
            ("LINEABOVE",     (0,0),(-1,0),  2, accion_color),
            ("TOPPADDING",    (0,0),(-1,-1), 10),
            ("BOTTOMPADDING", (0,0),(-1,-1), 10),
            ("LEFTPADDING",   (0,0),(-1,-1), 12),
        ]))
        story.append(accion_t)
        story.append(Spacer(1, 14))

        story.append(Paragraph(
            f"Reporte generado automaticamente por SOVEREIGN AML \u00b7 Powered by IMPERATOR \u00b7 "
            f"{fecha_gen} \u00b7 Ing. Hob\u00e9d D\u00edaz, Msc. M.A.F.I",
            S["footer_txt"]
        ))

        doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
        return buf.getvalue()

    def generar_informe_general() -> bytes:
        fecha_gen = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        S = make_styles()
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.0*inch, rightMargin=1.0*inch,
            topMargin=1.1*inch, bottomMargin=0.7*inch,
        )

        def _hf(c, d):
            page_header_footer(c, d, "Informe Ejecutivo \u00b7 SOVEREIGN AML", fecha_gen)

        story = []

        story.append(Spacer(1, 20))
        portada = Table([[
            Table([
                [Paragraph("INFORME EJECUTIVO", ParagraphStyle("pt",
                    fontSize=10, textColor=C_AMBER, fontName="Helvetica-Bold",
                    alignment=TA_CENTER))],
                [Paragraph("SOVEREIGN AML", ParagraphStyle("ps",
                    fontSize=20, textColor=C_WHITE, fontName="Helvetica-Bold",
                    alignment=TA_CENTER))],
                [Paragraph("Powered by IMPERATOR", ParagraphStyle("pp",
                    fontSize=13, textColor=C_BLUE, fontName="Helvetica",
                    alignment=TA_CENTER))],
                [Spacer(1, 8)],
                [HRFlowable(width="80%", thickness=1, color=C_AMBER, spaceAfter=8)],
                [Paragraph(f"Fecha de generacion: {fecha_gen}", S["cover_meta"])],
                [Paragraph(f"Total de transacciones analizadas: {len(df):,}", S["cover_meta"])],
                [Paragraph(f"Total de clientes en el periodo: {df['Cliente'].nunique():,}", S["cover_meta"])],
                [Spacer(1, 8)],
                [Paragraph("CONFIDENCIAL \u00b7 USO INTERNO EXCLUSIVO",
                    ParagraphStyle("conf", fontSize=8, textColor=C_RED,
                    fontName="Helvetica-Bold", alignment=TA_CENTER))],
            ], colWidths=[6.5*inch],
            style=TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), C_HEADER_BG),
                ("LINEABOVE",     (0,0),(-1,0),  3, C_AMBER),
                ("LINEBELOW",     (0,-1),(-1,-1), 3, C_AMBER),
                ("TOPPADDING",    (0,0),(-1,-1), 12),
                ("BOTTOMPADDING", (0,0),(-1,-1), 12),
            ]))
        ]], colWidths=[7.0*inch])
        story.append(portada)
        story.append(Spacer(1, 20))

        story.append(header_band("1. INDICADORES CLAVE DEL PERIODO",
            "Resumen cuantitativo de la actividad transaccional analizada"))
        story.append(Spacer(1, 8))

        total_clientes   = len(casos)
        criticos_g       = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udd34 Cr\u00edtico"])
        altos_g          = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udfe7 Alto"])
        medios_g         = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udfe1 Medio"])
        bajos_g          = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udfe2 Bajo"])
        total_alertas_g  = int(df["Score"].gt(0).sum())
        monto_total_g    = df["Monto"].sum()
        clientes_alerta  = len(df[df["Score"] > 0]["Cliente"].unique())
        pct_alerta       = clientes_alerta / total_clientes * 100 if total_clientes else 0

        story.append(kpi_row([
            ("Clientes analizados",    str(total_clientes),       C_BLUE),
            ("Nivel CRITICO",          str(criticos_g),           C_RED),
            ("Nivel ALTO",             str(altos_g),              C_ORANGE),
            ("Con alguna alerta",      str(clientes_alerta),      C_YELLOW),
        ]))
        story.append(Spacer(1, 6))
        story.append(kpi_row([
            ("Total alertas generadas", f"{total_alertas_g:,}",   C_AMBER),
            ("Volumen total (Q)",        f"{monto_total_g:,.0f}", C_BLUE),
            ("% clientes con alerta",   f"{pct_alerta:.1f}%",     C_ORANGE),
            ("Nivel MEDIO / BAJO",      f"{medios_g} / {bajos_g}", C_GREEN),
        ]))
        story.append(Spacer(1, 14))

        hb_sec2 = header_band("2. DISTRIBUCION DE RIESGO POR CLIENTE",
            "Clasificacion del universo de clientes segun nivel de riesgo AML")

        riesgo_counts_g = casos["Nivel_Riesgo"].value_counts()

        def _hex(c):
            hx = "#{:02X}{:02X}{:02X}".format(
                int(c.red*255), int(c.green*255), int(c.blue*255))
            return hx

        colores_hex = [_hex(nivel_color_rl(k)) for k in riesgo_counts_g.index]
        labels_pie  = [nivel_label(k) for k in riesgo_counts_g.index]

        fig_p, ax_p = dark_fig(5, 4.5)   
        ax_p.set_aspect('equal')
        wedges, texts, autotexts = ax_p.pie(
            riesgo_counts_g.values, labels=labels_pie, colors=colores_hex,
            autopct='%1.0f%%', startangle=140, pctdistance=0.72,
            wedgeprops=dict(linewidth=2, edgecolor='#0d1117'))
        for txt in texts:    txt.set_color('#c9d1d9'); txt.set_fontsize(10)
        for atxt in autotexts: atxt.set_color('#0d1117'); atxt.set_fontweight('bold'); atxt.set_fontsize(10)
        ax_p.set_xlim(-1.4, 1.4)  
        plt.tight_layout()
        desc_pie = "<b>Interpretacion:</b> Agrupacion porcentual del total de clientes evaluados segun su categorizacion de riesgo final calculada por el motor IMPERATOR. Util para entender la exposicion general de la cartera."
        story.append(KeepTogether([hb_sec2, Spacer(1, 8), fig_to_image(fig_p, 4.0, 3.6), Spacer(1, 4), Paragraph(desc_pie, S["body"])]))  
        story.append(Spacer(1, 14))
        
        story.append(PageBreak())
        hb_sec3 = header_band("3. ALERTAS POR TIPO DE REGLA AML",
            "Frecuencia de activacion de cada regla en el periodo analizado")

        fig_b, ax_b = dark_fig(9, 3.5)
        tipos_g  = [t.replace(" (Absoluto)", "") for t in matriz_alertas["Tipo de Alerta"]]
        cnts_g   = matriz_alertas["Cantidad"].tolist()
        pesos_g  = matriz_alertas["Peso en Score"].tolist()
        bcols_g  = ["#ef4444" if p >= 3 else ("#f97316" if p == 2 else "#eab308") for p in pesos_g]
        bars_g   = ax_b.barh(tipos_g, cnts_g, color=bcols_g, edgecolor='#0d1117',
                             linewidth=0.4, height=0.5)
        max_cnt  = max(cnts_g) if max(cnts_g) > 0 else 1
        ax_b.set_xlim(0, max_cnt * 1.18)   
        for bar_g, val_g in zip(bars_g, cnts_g):
            ax_b.text(bar_g.get_width() + max_cnt * 0.02,
                      bar_g.get_y() + bar_g.get_height() / 2,
                      str(val_g), va='center', ha='left', color='#c9d1d9',
                      fontsize=9, fontweight='bold')
        ax_b.set_xlabel("Cantidad de alertas generadas", color='#8b949e')
        ax_b.tick_params(axis='y', labelsize=8.5)
        ax_b.invert_yaxis()
        plt.tight_layout()
        desc_bar = "<b>Interpretacion:</b> Frecuencia absoluta de deteccion por tipo de alerta. Permite identificar cuales reglas y comportamientos anomalos son los mas recurrentes en el periodo."
        story.append(KeepTogether([hb_sec3, Spacer(1, 8), fig_to_image(fig_b, 6.5, 3.2), Spacer(1, 4), Paragraph(desc_bar, S["body"])]))
        story.append(Spacer(1, 8))

        ma_display = matriz_alertas[["Tipo de Alerta","Cantidad","Nivel de Impacto","Peso en Score"]].copy()
        story.append(df_to_table(
            ma_display,
            col_widths=[2.5*inch, 0.9*inch, 1.5*inch, 1.1*inch]
        ))
        story.append(Spacer(1, 14))

        hb_sec4 = header_band("4. EVOLUCION DEL VOLUMEN TRANSACCIONAL",
            "Comportamiento diario del flujo de operaciones en el periodo")

        timeline_g = df.groupby("Fecha_dia")["Monto"].sum().reset_index()
        fechas_g   = [str(d) for d in timeline_g["Fecha_dia"]]
        fig_l, ax_l = dark_fig(10, 3)
        ax_l.fill_between(range(len(timeline_g)), timeline_g["Monto"],
                          alpha=0.18, color="#3b82f6")
        ax_l.plot(range(len(timeline_g)), timeline_g["Monto"],
                  color="#3b82f6", linewidth=2, marker='o', markersize=4)
        
        n_ticks = len(fechas_g)
        step = max(1, n_ticks // 15)
        ax_l.set_xticks(range(0, n_ticks, step))
        ax_l.set_xticklabels([fechas_g[i] for i in range(0, n_ticks, step)], rotation=45, ha='right', fontsize=7)
        ax_l.set_ylabel("Monto total (Q)", color='#8b949e')
        ax_l.set_title("Volumen transaccional diario", color="#c9d1d9", fontsize=9, pad=8)
        plt.tight_layout()
        desc_line = "<b>Interpretacion:</b> Serie temporal del dinero movilizado diariamente. Alteraciones abruptas o picos anomalos pueden indicar posibles ingresos atipicos o alta volatilidad transaccional."
        story.append(KeepTogether([hb_sec4, Spacer(1, 8), fig_to_image(fig_l, 6.5, 2.8), Spacer(1, 4), Paragraph(desc_line, S["body"])]))
        story.append(Spacer(1, 14))
        
        hb_sec5 = None
        if "TipoOperacion" in df.columns:
            hb_sec5 = header_band("5. DISTRIBUCION POR TIPO DE OPERACION",
                "Volumen transaccional clasificado segun su naturaleza (Efectivo, Transferencia, etc.)")
            
            flujo_t = df.groupby("TipoOperacion")["Monto"].sum().reset_index()
            fig_t, ax_t = dark_fig(10, 3)
            ax_t.bar(flujo_t["TipoOperacion"], flujo_t["Monto"], color="#f97316", edgecolor="#0d1117", alpha=0.9)
            ax_t.set_ylabel("Monto total (Q)", color='#8b949e')
            ax_t.set_title("Volumen por tipo", color="#c9d1d9", fontsize=9, pad=8)
            ax_t.tick_params(axis='x', colors='#8b949e', rotation=0)
            ax_t.tick_params(axis='y', colors='#8b949e')
            plt.tight_layout()
            
            desc_tipo = "<b>Interpretacion:</b> Agrupacion del monto total segun la via transaccional. Permite evaluar la predominancia de operaciones liquidas, transferencias o uso de efectivo pesado."
            story.append(KeepTogether([hb_sec5, Spacer(1, 8), fig_to_image(fig_t, 6.5, 2.5), Spacer(1, 4), Paragraph(desc_tipo, S["body"])]))
            story.append(Spacer(1, 14))

            # --- NUEVA SECCI\u00d3N BI EN PDF ---
            hb_sec6 = header_band("6. INTELIGENCIA ESTRATEGICA Y DE NEGOCIOS",
                "Analisis de oportunidades comerciales y proyeccion de nuevos productos")
            
            stats_c = df.groupby("TipoOperacion").agg({"Cliente": "nunique", "Monto": "sum"}).reset_index()
            stats_c.columns = ["Canal", "Clientes", "Volumen"]
            canal_vip = stats_c.loc[stats_c["Volumen"].idxmax(), "Canal"]
            canal_pop = stats_c.loc[stats_c["Clientes"].idxmax(), "Canal"]
            
            bi_text = (
                f"<b>Oportunidad VIP (Canal {canal_vip}):</b> Este canal concentra la mayor liquidez del periodo. "
                f"Se recomienda considerarlo para productos de inversion premium o seguros de transaccion protegida.<br/><br/>"
                f"<b>Potencial de Escalamiento (Canal {canal_pop}):</b> Es el canal con mayor alcance de usuarios ({int(stats_c['Clientes'].max())}). "
                f"Ideal para lanzamientos masivos de programas de lealtad o billeteras digitales integradas."
            )
            story.append(KeepTogether([hb_sec6, Spacer(1, 8), Paragraph(bi_text, S["body"])]))
            story.append(Spacer(1, 14))

            next_section_num = 7
        else:
            next_section_num = 5

        pep_casos = casos[casos["EsPEP"] == True].copy() if "EsPEP" in casos.columns else pd.DataFrame()
        cpe_casos = casos[casos["EsCPE"] == True].copy() if "EsCPE" in casos.columns else pd.DataFrame()

        if not pep_casos.empty or not cpe_casos.empty:
            hb_sec_pep_cpe = header_band(
                f"{next_section_num}. ASOCIADOS PEP Y CPE IDENTIFICADOS",
                "Clientes marcados como personas expuestas politicamente o contratistas/proveedores relacionados con sensibilidad reforzada"
            )
            next_section_num += 1

            resumen_pep_cpe = (
                f"El motor IMPERATOR identifico <b>{len(pep_casos)} asociado(s) PEP</b> y "
                f"<b>{len(cpe_casos)} asociado(s) CPE</b> en el periodo evaluado. "
                f"Estas marcas requieren validacion reforzada de origen de fondos, perfil economico, "
                f"vinculos institucionales y consistencia documental antes de cerrar el analisis de cumplimiento."
            )
            story.append(KeepTogether([hb_sec_pep_cpe, Spacer(1, 8), Paragraph(resumen_pep_cpe, S["body"])]))
            story.append(Spacer(1, 8))

            if not pep_casos.empty:
                pep_display = pep_casos[["Cliente", "Total_Mensual", "Score_Max", "Transacciones", "Nivel_Riesgo"]].copy()
                pep_display["Total_Mensual"] = pep_display["Total_Mensual"].apply(lambda x: f"Q{x:,.0f}")
                pep_display.columns = ["Cliente PEP", "Total Mensual", "Score", "Num. Ops", "Nivel Riesgo"]
                story.append(Paragraph("Listado de asociados PEP", S["subsection"]))
                story.append(df_to_table(pep_display, col_widths=[2.15*inch, 1.35*inch, 0.75*inch, 0.85*inch, 1.9*inch]))
                story.append(Spacer(1, 8))

            if not cpe_casos.empty:
                cpe_display = cpe_casos[["Cliente", "Total_Mensual", "Score_Max", "Transacciones", "Nivel_Riesgo"]].copy()
                cpe_display["Total_Mensual"] = cpe_display["Total_Mensual"].apply(lambda x: f"Q{x:,.0f}")
                cpe_display.columns = ["Cliente CPE", "Total Mensual", "Score", "Num. Ops", "Nivel Riesgo"]
                story.append(Paragraph("Listado de asociados CPE", S["subsection"]))
                story.append(df_to_table(cpe_display, col_widths=[2.15*inch, 1.35*inch, 0.75*inch, 0.85*inch, 1.9*inch]))
                story.append(Spacer(1, 14))

        if "Ubicacion_Riesgo" in df.columns and df["Ubicacion_Riesgo"].any():
            hb_sec_ubic = header_band(f"{next_section_num}. ANALISIS DE UBICACIONES CON RIESGO",
                "Monitoreo de transacciones procedentes de fronteras o zonas rojas")
            next_section_num += 1

            df_riesgo_ubic = df[df["Ubicacion_Riesgo"] == True]
            ubic_count = df_riesgo_ubic["Ubicacion"].value_counts().reset_index()
            ubic_count.columns = ["Zona de Riesgo", "Transacciones"]
            ubic_monto = df_riesgo_ubic.groupby("Ubicacion")["Monto"].sum().reset_index()
            ubic_monto.columns = ["Zona de Riesgo", "Volumen (Q)"]
            ubic_res = pd.merge(ubic_count, ubic_monto, on="Zona de Riesgo")
            ubic_res["Volumen (Q)"] = ubic_res["Volumen (Q)"].apply(lambda x: f"Q{x:,.0f}")
            
            story.append(KeepTogether([
                hb_sec_ubic, Spacer(1, 8),
                df_to_table(ubic_res, col_widths=[3.0*inch, 1.5*inch, 2.5*inch]),
                Spacer(1, 4),
                Paragraph("<b>Interpretacion:</b> El desglose muestra la exposicion a zonas geograficas de alto riesgo, requiriendo justificacion de origen/destino de fondos.", S["body"])
            ]))
            story.append(Spacer(1, 14))

        sec_casos = f"{next_section_num}. CLIENTES PRIORITARIOS PARA INVESTIGACION"
        sec_sintesis = f"{next_section_num + 1}. SINTESIS Y RECOMENDACIONES"

        hb_sec_casos = header_band(sec_casos,
            "Listado de clientes con mayor score de riesgo AML \u2014 accion requerida")

        top_casos = casos.sort_values("Score_Max", ascending=False).head(15).copy()
        top_casos["Nivel_Riesgo_txt"] = top_casos["Nivel_Riesgo"].apply(nivel_label)
        top_casos["Total_Mensual"]    = top_casos["Total_Mensual"].apply(lambda x: f"Q{x:,.0f}")

        tc_display = top_casos[["Cliente","Total_Mensual","Score_Max",
                                 "Transacciones","Nivel_Riesgo_txt"]].copy()
        tc_display.columns = ["Cliente","Total Mensual","Score","Num. Ops","Nivel Riesgo"]
        story.append(KeepTogether([
            hb_sec_casos, Spacer(1, 6),
            df_to_table(tc_display, col_widths=[1.8*inch, 1.4*inch, 0.8*inch, 0.9*inch, 2.1*inch])
        ]))
        story.append(Spacer(1, 14))
        
        hb_sec_sintesis = header_band(sec_sintesis,
            "Conclusiones del analisis automatizado del periodo")

        pct_critico = criticos_g / total_clientes * 100 if total_clientes else 0
        sintesis = (
            f"Durante el periodo analizado se procesaron <b>{len(df):,} transacciones</b> "
            f"correspondientes a <b>{total_clientes} clientes</b>, con un volumen total de "
            f"<b>Q{monto_total_g:,.0f}</b>. El motor IMPERATOR genero <b>{total_alertas_g:,} alertas</b> "
            f"distribuidas en {len(matriz_alertas)} tipos de reglas de deteccion.<br/><br/>"
            f"Se identificaron <b>{criticos_g} cliente(s) en nivel CRITICO</b> "
            f"({pct_critico:.1f}% del total), los cuales requieren atencion inmediata por parte "
            f"del equipo de cumplimiento. Adicionalmente, {altos_g} cliente(s) presentan nivel "
            f"ALTO y deben ser incluidos en el ciclo de monitoreo intensificado.<br/><br/>"
            f"La regla con mayor frecuencia de activacion fue "
            f"<b>{matriz_alertas.iloc[matriz_alertas['Cantidad'].values.argmax()]['Tipo de Alerta']}</b> "
            f"({matriz_alertas['Cantidad'].max()} activaciones), lo que sugiere revisar el umbral "
            f"configurado para esta regla si el numero de falsos positivos es elevado."
        )
        story.append(KeepTogether([hb_sec_sintesis, Spacer(1, 6), Paragraph(sintesis, S["body"])]))
        story.append(Spacer(1, 12))

        # --- C\u00c1LCULOS DE BI PARA RECOMENDACIONES ---
        conteo_t = df["TipoOperacion"].value_counts()
        canal_f  = conteo_t.index[0] if not conteo_t.empty else "N/A"
        monto_t  = df.groupby("TipoOperacion")["Monto"].sum()
        canal_v  = monto_t.idxmax() if not monto_t.empty else "N/A"
        
        es_digital_g = any(x in str(canal_f).lower() for x in ["app", "web", "transferencia", "digital"])
        es_cash_g    = any(x in str(canal_f).lower() for x in ["efectivo", "cash", "ventanilla", "caja"])

        recomendaciones = [
            f"Escalar de inmediato los {criticos_g} caso(s) CRITICO(S) al Oficial de Cumplimiento.",
            f"Iniciar expediente formal para clientes con score >= {cfg['score_critico']} o volumen > Q{cfg['monto_critico']:,}.",
            f"Revisar y actualizar el perfil KYC de los {altos_g} clientes en nivel ALTO en los proximos 5 dias habiles.",
        ]

        if es_digital_g:
            recomendaciones.append(f"OPORTUNIDAD COMERCIAL: El canal {canal_f} lidera en uso. Se sugiere incentivar productos digitales con micro-segmentacion y notificaciones preventivas.")
        elif es_cash_g:
            recomendaciones.append(f"EFICIENCIA OPERATIVA: El alto uso de {canal_f} sugiere una oportunidad para migrar usuarios a banca digital mediante bonos de adopcion tecnologica.")
            recomendaciones.append(f"SEGURIDAD: Reforzar la vigilancia y arqueos preventivos en los puntos que manejan {canal_f} debido al volumen detectado (Q{monto_t.max():,.0f}).")
        
        recomendaciones.extend([
            "Correlacionar picos de volumen detectados con fechas festivas, fin de mes o eventos externos relevantes.",
            f"ANALISIS DE VALOR: El canal {canal_v} mueve el mayor capital. Evaluar el lanzamiento de productos de inversion premium para estos usuarios.",
            "Evaluar ajuste de umbrales si la tasa de falsos positivos supera el 20% del total de alertas.",
        ])

        for i, rec in enumerate(recomendaciones, 1):
            story.append(Paragraph(f"<b>{i}.</b> {rec}", S["body"]))

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"Informe generado automaticamente por SOVEREIGN AML \u00b7 Powered by IMPERATOR \u00b7 "
            f"{fecha_gen} \u00b7 Ing. Hob\u00e9d D\u00edaz, Msc. M.A.F.I \u00b7 CONFIDENCIAL",
            S["footer_txt"]
        ))

        doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
        return buf.getvalue()

    # ── GENERADORES RTS / RTE (Arts. 30-31 Ley 6593) — Platypus SOVEREIGN AML ──

    def generar_pdf_rts_completo(caso_rts_sel: str, sujeto_info: dict) -> bytes:
        """RTS completo con identidad visual SOVEREIGN AML — Art. 30 Ley 6593 / GAFI Rec. 20."""
        fecha_gen = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        S = make_styles()
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.0*inch, rightMargin=1.0*inch,
            topMargin=1.1*inch, bottomMargin=0.7*inch,
        )

        def _hf(c, d):
            page_header_footer(c, d, "RTS — Art. 30 Ley 6593", fecha_gen)

        story = []

        fila     = casos[casos["Cliente"] == caso_rts_sel].iloc[0]
        df_cli   = df[df["Cliente"] == caso_rts_sel].copy()
        score    = int(fila.get("Score_Max", 0))
        nivel    = nivel_label(str(fila.get("Nivel_Riesgo", "—")))
        total_txs = int(fila.get("Transacciones", len(df_cli)))
        monto_cli = df_cli["Monto"].sum() if "Monto" in df_cli.columns else 0.0

        # ── Portada ──
        cover_data = [
            [Paragraph("REPORTE DE TRANSACCIÓN SOSPECHOSA", S["cover_title"])],
            [Paragraph("RTS — Intendencia de Verificación Especial (IVE) · SIB Guatemala", S["cover_sub"])],
            [Paragraph("Art. 30 Ley Integral contra LD/FT/FPADM (Ley 6593) / GAFI Rec. 20", S["cover_meta"])],
            [Paragraph(f"Cliente reportado: <b>{caso_rts_sel}</b>",
                ParagraphStyle("cov_cl", fontSize=11, textColor=C_WHITE,
                    fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4))],
            [Paragraph(f"Generado: {fecha_gen} · CONFIDENCIAL — USO EXCLUSIVO IVE/SIB", S["cover_meta"])],
        ]
        cover_tbl = Table(cover_data, colWidths=[7.0 * inch])
        cover_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), C_BG),
            ("LINEBELOW",    (0, -1), (-1, -1), 2.0, C_RED),
            ("TOPPADDING",   (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
            ("LEFTPADDING",  (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ]))
        story.append(cover_tbl)
        story.append(Spacer(1, 14))

        story.append(kpi_row([
            ("Nivel de Riesgo",   nivel,            nivel_color_rl(str(fila.get("Nivel_Riesgo", "")))),
            ("Score IMPERATOR",   str(score),        C_AMBER),
            ("Transacciones",     str(total_txs),    C_BLUE),
            ("Monto Total",       f"Q{monto_cli:,.0f}", C_ORANGE),
        ]))
        story.append(Spacer(1, 16))

        # ── I. Sujeto Obligado ──
        story.append(header_band("I. SUJETO OBLIGADO", "Institución reportante — Art. 28 Ley 6593"))
        story.append(Spacer(1, 6))
        for label, value in [
            ("Institución:",            sujeto_info.get("Institucion", "—")),
            ("Oficial de Cumplimiento:", sujeto_info.get("Oficial_Cumplimiento", "—")),
            ("NIT / Licencia:",          sujeto_info.get("NIT_DPI", "—")),
            ("Fecha del reporte:",       fecha_gen),
        ]:
            story.append(Paragraph(f"<b>{label}</b> {value}", S["body"]))
        story.append(Spacer(1, 10))

        # ── II. Marco Legal ──
        story.append(header_band("II. MARCO LEGAL Y CLASIFICACIÓN", "Base normativa del reporte"))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>Art. 30 Ley 6593 (Guatemala):</b> Todo sujeto obligado que detecte una operación sospechosa "
            "deberá reportarla a la IVE dentro de los plazos establecidos, acompañada del fundamento del "
            "examen realizado.",
            S["body"]
        ))
        story.append(Paragraph(
            "<b>GAFI Recomendación 20:</b> Los sujetos obligados deben reportar operaciones sospechosas de "
            "manera oportuna a la unidad de inteligencia financiera competente.",
            S["body"]
        ))
        story.append(Paragraph(
            "<b>Estado de la alerta:</b> Sospechosa_Confirmada — requiere envío a IVE (Art. 30 Ley 6593).",
            S["body"]
        ))
        story.append(Spacer(1, 10))

        # ── III. Datos del Reportado ──
        story.append(header_band("III. DATOS DEL REPORTADO", "Información del cliente — Ley 6593 / GAFI Rec. 10"))
        story.append(Spacer(1, 6))
        es_pep   = bool(fila.get("EsPEP",   False))
        es_cpe   = bool(fila.get("EsCPE",   False))
        es_fpadm = bool(fila.get("EsFPADM", False))
        ubo      = str(fila.get("Beneficiario_Final", "—"))
        ubo_pep  = bool(fila.get("EsPEP_UBO", False))
        porc_ubo = fila.get("Porcentaje_Participacion", None)

        reportado = [
            ("Cliente / Nombre:",  caso_rts_sel),
            ("NIT / DPI:",         sujeto_info.get("NIT_DPI", "—")),
            ("Tipo de cliente:",   str(fila.get("Tipo_Cliente", "—"))),
            ("EsPEP:",  "SÍ ⚠ (Art. 25a Ley 6593 — DDA Obligatoria)" if es_pep else "No"),
            ("EsCPE:",  "SÍ ⚠" if es_cpe else "No"),
            ("EsFPADM:", "SÍ ⚠ (GAFI Rec. 7 / Art. 2 Ley 6593 — Acción R-03)" if es_fpadm else "No"),
            ("Beneficiario Final (UBO):", ubo),
        ]
        if ubo not in ("—", "", "nan"):
            if porc_ubo is not None:
                reportado.append(("Porcentaje participación UBO:", f"{porc_ubo}%"))
            if ubo_pep:
                reportado.append(("EsPEP_UBO:", "SÍ ⚠ — DDA Obligatoria (Art. 21 / GAFI Rec. 12)"))
        for label, value in reportado:
            story.append(Paragraph(f"<b>{label}</b> {value}", S["body"]))
        story.append(Spacer(1, 10))

        # ── IV. Perfil de Alertas IMPERATOR ──
        story.append(header_band("IV. PERFIL DE ALERTAS IMPERATOR", "Detección automática de indicadores LD/FT/FPADM"))
        story.append(Spacer(1, 6))
        alerta_map = {
            "Alerta_Absoluto":   "Monto Alto",
            "Alerta_Acumulado":  "Acumulado",
            "Alerta_15":         "Desv. Perfil",
            "Alerta_Frecuencia": "Frecuencia",
            "Alerta_Smurfing":   "Smurfing",
            "Alerta_Pico":       "Pico",
            "Alerta_Ubicacion":  "Ubicación",
        }
        alert_rows = []
        for col_orig, col_name in alerta_map.items():
            if col_orig in df_cli.columns:
                n_a = int(df_cli[col_orig].astype(int).sum())
                alert_rows.append([col_name, str(n_a), "Activa" if n_a > 0 else "—"])
        if alert_rows:
            story.append(df_to_table(
                pd.DataFrame(alert_rows, columns=["Regla", "N° Alertas", "Estado"]),
                col_widths=[3.5*inch, 1.5*inch, 2.0*inch]
            ))
        story.append(Spacer(1, 8))
        st_v = fila.get("S_T", "—"); sc_v = fila.get("S_C", "—")
        sb_v = fila.get("S_B", "—"); sn_v = fila.get("S_N", "—")
        story.append(Paragraph(
            f"<b>Score IMPERATOR {score}</b> — Composición: "
            f"S_T (Transaccional): <b>{st_v}</b> · "
            f"S_C (Contextual): <b>{sc_v}</b> · "
            f"S_B (Conductual): <b>{sb_v}</b> · "
            f"S_N (Red): <b>{sn_v}</b>",
            S["body"]
        ))
        story.append(Spacer(1, 10))

        # ── V. Transacciones asociadas ──
        story.append(PageBreak())
        story.append(header_band("V. TRANSACCIONES ASOCIADAS", "Detalle de operaciones del cliente reportado"))
        story.append(Spacer(1, 6))
        tx_cols_ord = ["Fecha", "Monto", "TipoOperacion", "Tipo_Instrumento"]
        tx_present  = [c for c in tx_cols_ord if c in df_cli.columns]
        if tx_present:
            df_tx_show = df_cli[tx_present].copy()
            if "Monto" in df_tx_show.columns:
                df_tx_show["Monto"] = df_tx_show["Monto"].apply(
                    lambda x: f"Q{x:,.2f}" if pd.notna(x) else "—")
            df_tx_show = df_tx_show.rename(columns={
                "TipoOperacion": "Canal", "Tipo_Instrumento": "Instrumento"})
            story.append(df_to_table(df_tx_show))
        else:
            story.append(Paragraph("No hay columnas de detalle de transacciones disponibles.", S["body"]))
        story.append(Spacer(1, 10))

        # ── VI. Fundamento del Examen ──
        story.append(header_band("VI. FUNDAMENTO DEL EXAMEN", "Art. 29 Ley 6593 — Documentación del análisis"))
        story.append(Spacer(1, 6))
        fundamento = str(fila.get("Fundamento_Examen", ""))
        if not fundamento or fundamento in ("nan", "—", ""):
            fundamento = (
                "Sin fundamento registrado. El analista debe completar este campo en el módulo "
                "de Casos de Alerta antes de emitir el RTS formal."
            )
        story.append(Paragraph(fundamento, S["body"]))
        story.append(Spacer(1, 10))

        # ── VII. Tipología GAFI ──
        story.append(header_band("VII. TIPOLOGÍA Y PATRONES LD/FT/FPADM", "Correspondencia con tipologías GAFI"))
        story.append(Spacer(1, 6))
        tipologias = []
        if fila.get("Alerta_Smurfing", False):
            tipologias.append(
                "Smurfing / Pitufeo: Fragmentación de operaciones para evadir umbrales de reporte (GAFI Tip. 4)")
        if fila.get("Alerta_Pico", False):
            tipologias.append(
                "Pico Anómalo: Incremento estadístico atípico sobre el perfil histórico del cliente (ISO 31000)")
        if es_pep or es_cpe:
            tipologias.append(
                "PEP/CPE: Persona Expuesta Políticamente o Contratista/Proveedor del Estado — "
                "riesgo elevado (GAFI Rec. 12)")
        if es_fpadm:
            tipologias.append(
                "FPADM: Riesgo de Financiamiento de Proliferación de Armas de Destrucción Masiva "
                "(GAFI Rec. 7 / Art. 2 Ley 6593)")
        if fila.get("Alerta_Acumulado", False):
            tipologias.append(
                "Acumulación: Volumen mensual excede el perfil esperado del cliente — "
                "posible estructuración")
        if not tipologias:
            tipologias.append(
                "Patrón combinado de indicadores de riesgo — "
                "Ver sección IV para detalle de alertas activas")
        for i, tip in enumerate(tipologias, 1):
            story.append(Paragraph(f"<b>{i}.</b> {tip}", S["body"]))
        story.append(Spacer(1, 12))

        # ── VIII. Declaración y Firma ──
        story.append(header_band("VIII. DECLARACIÓN DEL SUJETO OBLIGADO", "Certificación del reporte — Art. 28 Ley 6593"))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            f"El suscrito Oficial de Cumplimiento de "
            f"<b>{sujeto_info.get('Institucion', '—')}</b> certifica que la presente operación "
            "fue analizada conforme al Manual de Prevención LD/FT/FPADM de la institución, al motor de "
            "riesgo IMPERATOR (ISO 31000 / COSO ERM) y a las disposiciones de la "
            "<b>Ley Integral contra el Lavado de Dinero u Otros Activos y el Financiamiento del "
            "Terrorismo (Ley 6593, Guatemala)</b>, y que existe mérito suficiente para su reporte "
            "formal ante la <b>Intendencia de Verificación Especial (IVE) de la SIB</b>.",
            S["body"]
        ))
        story.append(Spacer(1, 36))
        sig_table = Table(
            [
                [Paragraph("_______________________________", S["body"]),
                 Paragraph("_______________________________", S["body"])],
                [Paragraph(f"<b>{sujeto_info.get('Oficial_Cumplimiento', 'Oficial de Cumplimiento')}</b>", S["body"]),
                 Paragraph("<b>Fecha y sello</b>", S["body"])],
                [Paragraph("Oficial de Cumplimiento", S["body_small"]),
                 Paragraph(f"Generado: {fecha_gen}", S["body_small"])],
            ],
            colWidths=[3.5*inch, 3.5*inch]
        )
        sig_table.setStyle(TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(sig_table)
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"SOVEREIGN AML · Powered by IMPERATOR · {fecha_gen} · "
            "Ing. Hobéd Díaz, Msc. M.A.F.I · CONFIDENCIAL — IVE/SIB",
            S["footer_txt"]
        ))

        doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
        return buf.getvalue()

    def generar_pdf_rte_completo(sujeto_info: dict) -> bytes:
        """RTE completo con identidad visual SOVEREIGN AML — Art. 31 Ley 6593."""
        fecha_gen = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        S = make_styles()
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=1.0*inch, rightMargin=1.0*inch,
            topMargin=1.1*inch, bottomMargin=0.7*inch,
        )

        def _hf(c, d):
            page_header_footer(c, d, "RTE — Art. 31 Ley 6593", fecha_gen)

        story = []

        df_rte     = df[df["Es_RTE"] == True].copy() if "Es_RTE" in df.columns else df.iloc[0:0]
        n_rte      = len(df_rte)
        monto_rte  = df_rte["Monto"].sum() if "Monto" in df_rte.columns and n_rte > 0 else 0.0
        cli_unicos = df_rte["Cliente"].nunique() if "Cliente" in df_rte.columns and n_rte > 0 else 0

        # ── Portada ──
        cover_data = [
            [Paragraph("REPORTE DE TRANSACCIÓN EN EFECTIVO", S["cover_title"])],
            [Paragraph("RTE — Intendencia de Verificación Especial (IVE) · SIB Guatemala", S["cover_sub"])],
            [Paragraph("Art. 31 Ley Integral contra LD/FT/FPADM (Ley 6593) · Umbral: USD 10,000 o equivalente",
                S["cover_meta"])],
            [Paragraph(f"Generado: {fecha_gen} · CONFIDENCIAL — USO EXCLUSIVO IVE/SIB", S["cover_meta"])],
        ]
        cover_tbl = Table(cover_data, colWidths=[7.0 * inch])
        cover_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, -1), C_BG),
            ("LINEBELOW",    (0, -1), (-1, -1), 2.0, C_BLUE),
            ("TOPPADDING",   (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 12),
            ("LEFTPADDING",  (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ]))
        story.append(cover_tbl)
        story.append(Spacer(1, 14))

        story.append(kpi_row([
            ("Transacciones RTE",    str(n_rte),              C_RED),
            ("Clientes únicos", str(cli_unicos),          C_AMBER),
            ("Monto total efectivo", f"Q{monto_rte:,.0f}",    C_ORANGE),
            ("Umbral reportable",    "USD 10,000",             C_BLUE),
        ]))
        story.append(Spacer(1, 16))

        # ── I. Marco Legal ──
        story.append(header_band("I. MARCO LEGAL", "Base normativa del reporte RTE"))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "<b>Art. 31 Ley 6593 (Guatemala):</b> Los sujetos obligados deben reportar a la IVE toda "
            "transacción realizada en efectivo que iguale o supere el equivalente a USD 10,000, "
            "independientemente de que la operación sea o no sospechosa.",
            S["body"]
        ))
        story.append(Paragraph(
            "<b>Criterio de inclusión:</b> Tipo_Instrumento = EFECTIVO y Monto ≥ USD 10,000 "
            "(o equivalente en Quetzales).",
            S["body"]
        ))
        story.append(Spacer(1, 10))

        # ── II. Sujeto Obligado ──
        story.append(header_band("II. SUJETO OBLIGADO", "Institución reportante"))
        story.append(Spacer(1, 6))
        for label, value in [
            ("Institución:",            sujeto_info.get("Institucion", "—")),
            ("Oficial de Cumplimiento:", sujeto_info.get("Oficial_Cumplimiento", "—")),
            ("Fecha del reporte:",       fecha_gen),
        ]:
            story.append(Paragraph(f"<b>{label}</b> {value}", S["body"]))
        story.append(Spacer(1, 10))

        # ── III. Transacciones en efectivo ──
        story.append(header_band(
            "III. TRANSACCIONES EN EFECTIVO REPORTABLES",
            f"{n_rte} transacciones — Art. 31 Ley 6593"
        ))
        story.append(Spacer(1, 6))
        if n_rte == 0:
            story.append(Paragraph(
                "No se detectaron transacciones en efectivo ≥ USD 10,000.", S["body"]))
        else:
            tx_cols_ord = ["Cliente", "Fecha", "Monto", "TipoOperacion"]
            tx_present  = [c for c in tx_cols_ord if c in df_rte.columns]
            df_rte_show = df_rte[tx_present].copy()
            if "Monto" in df_rte_show.columns:
                df_rte_show["Monto"] = df_rte_show["Monto"].apply(
                    lambda x: f"Q{x:,.2f}" if pd.notna(x) else "—")
            df_rte_show = df_rte_show.rename(columns={"TipoOperacion": "Canal"})
            cw = 7.0 / len(df_rte_show.columns) * inch
            story.append(df_to_table(df_rte_show, col_widths=[cw] * len(df_rte_show.columns)))

        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=0.5, color=C_BORDER))
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f"SOVEREIGN AML · Powered by IMPERATOR · {fecha_gen} · "
            "Ing. Hobéd Díaz, Msc. M.A.F.I · CONFIDENCIAL — IVE/SIB",
            S["footer_txt"]
        ))

        doc.build(story, onFirstPage=_hf, onLaterPages=_hf)
        return buf.getvalue()

    st.markdown("""
    <div class="info-box">
        <strong>INFORMES Y REPORTES PDF</strong> — Documentación formal bajo estándares IMPERATOR.
        Genera instrumentos analíticos de alta fidelidad para procesos de auditoría y reporte regulatorio (RTS a la IVE — Art. 30 Ley 6593).
        Utilice la <strong>Ficha Individual</strong> para expedientes específicos o el <strong>Informe Ejecutivo</strong> para visión de junta directiva.
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="section-title">Tipos de Reporte IMPERATOR AML</div>
    <div class="info-box" style="margin-top:-6px;">
        Seleccione el formato de salida según su objetivo: <strong>reporte individual</strong> para expedientes de cliente o <strong>informe ejecutivo</strong> para visión consolidada de gerencia, comité o auditoría.
    </div>
    """, unsafe_allow_html=True)

    tab_ind, tab_gen, tab_rts_rte = st.tabs([
        "Reporte Individual por Cliente",
        "Informe Ejecutivo General",
        "RTS / RTE — IVE (Ley 6593)",
    ])

    with tab_ind:
        st.markdown("""
        <div class="warning-box">
            <strong>Ficha de Investigaci\u00f3n por Cliente</strong> \u2014 Genera un PDF con todas las alertas detectadas,
            estad\u00edsticas del comportamiento transaccional, gr\u00e1ficas de evoluci\u00f3n y la recomendaci\u00f3n de acci\u00f3n
            seg\u00fan el nivel de riesgo. Ideal para expedientes de cumplimiento e investigaciones formales.
        </div>
        """, unsafe_allow_html=True)

        col_sel1, col_sel2 = st.columns([3, 1])
        with col_sel1:
            cliente_pdf = st.selectbox(
                "Selecciona el cliente para generar su ficha",
                options=casos.sort_values("Score_Max", ascending=False)["Cliente"].tolist(),
                help="Los clientes aparecen ordenados de mayor a menor score de riesgo."
            )
        with col_sel2:
            st.markdown("<br>", unsafe_allow_html=True)
            generar_ind = st.button("Generar PDF", type="primary", use_container_width=True)

        if cliente_pdf:
            info_prev = casos[casos["Cliente"] == cliente_pdf].iloc[0]
            nivel_prev = info_prev["Nivel_Riesgo"]
            color_prev = {"\ud83d\udd34 Cr\u00edtico": "red", "\ud83d\udfe7 Alto": "amber",
                          "\ud83d\udfe1 Medio": "blue", "\ud83d\udfe2 Bajo": "green"}.get(nivel_prev, "blue")

            col_p1, col_p2, col_p3, col_p4 = st.columns(4)
            with col_p1:
                st.markdown(f"""<div class="metric-card {color_prev}">
                    <div class="metric-number">{nivel_prev}</div>
                    <div class="metric-label">Nivel de Riesgo</div></div>""",
                    unsafe_allow_html=True)
            with col_p2:
                st.markdown(f"""<div class="metric-card amber">
                    <div class="metric-number">{int(info_prev['Score_Max'])}</div>
                    <div class="metric-label">Score IMPERATOR</div></div>""",
                    unsafe_allow_html=True)
            with col_p3:
                st.markdown(f"""<div class="metric-card blue">
                    <div class="metric-number">Q{info_prev['Total_Mensual']:,.0f}</div>
                    <div class="metric-label">Total Mensual</div></div>""",
                    unsafe_allow_html=True)
            with col_p4:
                st.markdown(f"""<div class="metric-card green">
                    <div class="metric-number">{int(info_prev['Transacciones'])}</div>
                    <div class="metric-label">Transacciones</div></div>""",
                    unsafe_allow_html=True)

        if generar_ind:
            with st.spinner(f"Generando ficha de investigaci\u00f3n para {cliente_pdf}..."):
                try:
                    pdf_bytes = generar_reporte_cliente(cliente_pdf)
                    nombre_archivo = f"AML_Ficha_{cliente_pdf.replace(' ','_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.success(f"Reporte generado correctamente ({len(pdf_bytes)/1024:.0f} KB)")
                    st.download_button(
                        label="Descargar Ficha PDF",
                        data=pdf_bytes,
                        file_name=nombre_archivo,
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error al generar el reporte: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    with tab_gen:
        st.markdown("""
        <div class="warning-box">
            <strong>Informe Ejecutivo General</strong> \u2014 Documento de alto nivel para presentar a superiores y
            comit\u00e9s de cumplimiento. Incluye KPIs globales, distribuci\u00f3n de riesgo, frecuencia de alertas,
            evoluci\u00f3n del volumen transaccional, listado de clientes prioritarios y recomendaciones formales.
        </div>
        """, unsafe_allow_html=True)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("""
            <div class="glossary">
                <div class="glossary-title">Contenido del informe ejecutivo</div>
                <div class="glossary-item"><span class="glossary-key">Portada</span><span>Datos del per\u00edodo, instituci\u00f3n y clasificaci\u00f3n de confidencialidad.</span></div>
                <div class="glossary-item"><span class="glossary-key">KPIs Globales</span><span>8 indicadores clave: clientes, alertas, volumen y distribuci\u00f3n.</span></div>
                <div class="glossary-item"><span class="glossary-key">Distribuci\u00f3n de Riesgo</span><span>Gr\u00e1fica de pastel con la proporci\u00f3n de clientes por nivel.</span></div>
                <div class="glossary-item"><span class="glossary-key">Alertas por Tipo</span><span>Gr\u00e1fica de barras con la frecuencia de cada regla AML.</span></div>
                <div class="glossary-item"><span class="glossary-key">Evoluci\u00f3n Temporal</span><span>L\u00ednea de volumen diario transaccionado en el per\u00edodo.</span></div>
                <div class="glossary-item"><span class="glossary-key">Clientes Prioritarios</span><span>Tabla con top 15 clientes ordenados por score de riesgo.</span></div>
                <div class="glossary-item"><span class="glossary-key">Recomendaciones</span><span>6 acciones concretas generadas autom\u00e1ticamente.</span></div>
            </div>
            """, unsafe_allow_html=True)

        with col_g2:
            total_cl = len(casos)
            crit_g   = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udd34 Cr\u00edtico"])
            alto_g   = len(casos[casos["Nivel_Riesgo"] == "\ud83d\udfe7 Alto"])
            vol_g    = df["Monto"].sum()
            at_g     = int(df["Score"].gt(0).sum())

            st.markdown(f"""
            <div class="metric-card red" style="margin-bottom:10px;">
                <div style="font-size:13px; color:#c9d1d9; font-weight:600;">Vista previa del informe</div>
                <div style="font-size:11px; color:#8b949e; margin-top:6px; font-family:IBM Plex Mono,monospace; line-height:1.8;">
                    Clientes analizados: <strong style="color:#f0f6fc;">{total_cl}</strong><br>
                    Nivel cr\u00edtico: <strong style="color:#ef4444;">{crit_g}</strong> &nbsp;\u00b7&nbsp;
                    Nivel alto: <strong style="color:#f97316;">{alto_g}</strong><br>
                    Alertas totales: <strong style="color:#f59e0b;">{at_g:,}</strong><br>
                    Volumen: <strong style="color:#3b82f6;">Q{vol_g:,.0f}</strong>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        generar_gen = st.button("Generar Informe Ejecutivo PDF",
                                type="primary", use_container_width=False)

        if generar_gen:
            with st.spinner("Compilando informe ejecutivo general..."):
                try:
                    pdf_bytes_g = generar_informe_general()
                    nombre_g = f"AML_Informe_Ejecutivo_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    st.success(f"Informe generado correctamente ({len(pdf_bytes_g)/1024:.0f} KB)")
                    st.download_button(
                        label="Descargar Informe Ejecutivo PDF",
                        data=pdf_bytes_g,
                        file_name=nombre_g,
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
                except Exception as e:
                    st.error(f"Error al generar el informe: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    with tab_rts_rte:
        st.markdown("""
        <div class="warning-box">
            <strong>Reportes Regulatorios IVE — Ley 6593</strong> —
            Genera PDFs estructurados compatibles con la Intendencia de Verificación Especial (IVE) de la SIB.
            <br>• <strong>RTS</strong>: Reporte de Transacción Sospechosa (Art. 30 Ley 6593 / GAFI Rec. 20)
            <br>• <strong>RTE</strong>: Reporte de Transacción en Efectivo ≥ USD 10,000 (Art. 31 Ley 6593)
        </div>
        """, unsafe_allow_html=True)

        sub_rts, sub_rte = st.tabs(["RTS — Sospechosa", "RTE — Efectivo"])

        with sub_rts:
            sospechosos = (
                casos[casos["Estado_Alerta"] == "Sospechosa_Confirmada"]
                if "Estado_Alerta" in casos.columns else casos.iloc[0:0]
            )
            if sospechosos.empty:
                st.info("No hay casos clasificados como Sospechosa_Confirmada. "
                        "Clasifique casos en el módulo de Alertas.")
            else:
                caso_rts = st.selectbox(
                    "Seleccionar caso sospechoso para generar RTS",
                    sospechosos.sort_values("Score_Max", ascending=False)["Cliente"].tolist(),
                    key="sel_caso_rts"
                )

                if caso_rts:
                    fila_prev = sospechosos[sospechosos["Cliente"] == caso_rts].iloc[0]
                    nivel_p   = fila_prev.get("Nivel_Riesgo", "")
                    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                    color_p = {"🔴 Crítico": "red", "🟧 Alto": "amber",
                               "🟡 Medio": "blue", "🟢 Bajo": "green"}.get(nivel_p, "red")
                    with col_p1:
                        st.markdown(
                            f'<div class="metric-card {color_p}">'
                            f'<div class="metric-number">{nivel_label(str(nivel_p))}</div>'
                            f'<div class="metric-label">Nivel de Riesgo</div></div>',
                            unsafe_allow_html=True)
                    with col_p2:
                        st.markdown(
                            f'<div class="metric-card amber">'
                            f'<div class="metric-number">{int(fila_prev.get("Score_Max", 0))}</div>'
                            f'<div class="metric-label">Score IMPERATOR</div></div>',
                            unsafe_allow_html=True)
                    with col_p3:
                        monto_p = df[df["Cliente"] == caso_rts]["Monto"].sum() if "Monto" in df.columns else 0
                        st.markdown(
                            f'<div class="metric-card blue">'
                            f'<div class="metric-number">Q{monto_p:,.0f}</div>'
                            f'<div class="metric-label">Monto Total</div></div>',
                            unsafe_allow_html=True)
                    with col_p4:
                        fund = str(fila_prev.get("Fundamento_Examen", ""))
                        estado_fund = "Registrado" if fund and fund not in ("nan", "—", "") else "Pendiente"
                        color_fund  = "green" if estado_fund == "Registrado" else "red"
                        st.markdown(
                            f'<div class="metric-card {color_fund}">'
                            f'<div class="metric-number">{estado_fund}</div>'
                            f'<div class="metric-label">Fundamento Examen</div></div>',
                            unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                col_i1, col_i2 = st.columns(2)
                with col_i1:
                    inst    = st.text_input("Institución", value="SOVEREIGN AML", key="rts_inst")
                    oficial = st.text_input("Oficial de Cumplimiento", key="rts_oficial")
                with col_i2:
                    nit = st.text_input("NIT / Licencia de la institución", key="rts_nit")

                if st.button("Generar PDF RTS — Identidad SOVEREIGN AML", type="primary", key="btn_rts"):
                    with st.spinner(f"Generando RTS para {caso_rts}..."):
                        try:
                            sujeto_info = {
                                "Institucion":            inst,
                                "Oficial_Cumplimiento":   oficial,
                                "NIT_DPI":                nit,
                            }
                            pdf_rts = generar_pdf_rts_completo(caso_rts, sujeto_info)
                            nombre_rts = (
                                f"RTS_{caso_rts.replace(' ','_')}_"
                                f"{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                            )
                            st.success(f"RTS generado correctamente ({len(pdf_rts)/1024:.0f} KB)")
                            st.download_button(
                                label="Descargar RTS PDF",
                                data=pdf_rts,
                                file_name=nombre_rts,
                                mime="application/pdf",
                                use_container_width=True,
                                type="primary"
                            )
                        except Exception as e:
                            st.error(f"Error al generar RTS: {e}")
                            import traceback
                            st.code(traceback.format_exc())

        with sub_rte:
            if "Es_RTE" not in df.columns:
                st.info("No se detectaron transacciones en efectivo. "
                        "Asegúrese de que la columna 'Tipo_Instrumento' esté presente.")
            else:
                df_rte_prev = df[df["Es_RTE"] == True]
                n_rte_prev  = len(df_rte_prev)
                if n_rte_prev == 0:
                    st.info("No hay transacciones en efectivo ≥ USD 10,000 en el período analizado.")
                else:
                    col_r1, col_r2, col_r3 = st.columns(3)
                    with col_r1:
                        st.markdown(
                            f'<div class="metric-card red">'
                            f'<div class="metric-number">{n_rte_prev}</div>'
                            f'<div class="metric-label">Transacciones RTE</div></div>',
                            unsafe_allow_html=True)
                    with col_r2:
                        cli_u = df_rte_prev["Cliente"].nunique() if "Cliente" in df_rte_prev.columns else 0
                        st.markdown(
                            f'<div class="metric-card amber">'
                            f'<div class="metric-number">{cli_u}</div>'
                            f'<div class="metric-label">Clientes únicos</div></div>',
                            unsafe_allow_html=True)
                    with col_r3:
                        monto_rte_prev = df_rte_prev["Monto"].sum() if "Monto" in df_rte_prev.columns else 0
                        st.markdown(
                            f'<div class="metric-card orange">'
                            f'<div class="metric-number">Q{monto_rte_prev:,.0f}</div>'
                            f'<div class="metric-label">Monto total efectivo</div></div>',
                            unsafe_allow_html=True)

                    st.warning(
                        f"⚠️ {n_rte_prev} transacción(es) requieren RTE ante la IVE (Art. 31 Ley 6593)")
                    st.markdown("<br>", unsafe_allow_html=True)
                    col_rte1, col_rte2 = st.columns(2)
                    with col_rte1:
                        inst_rte    = st.text_input("Institución", value="SOVEREIGN AML", key="rte_inst")
                    with col_rte2:
                        oficial_rte = st.text_input("Oficial de Cumplimiento", key="rte_oficial")

                    if st.button("Generar PDF RTE — Identidad SOVEREIGN AML", type="primary", key="btn_rte"):
                        with st.spinner("Generando RTE..."):
                            try:
                                sujeto_rte = {
                                    "Institucion":          inst_rte,
                                    "Oficial_Cumplimiento": oficial_rte,
                                }
                                pdf_rte    = generar_pdf_rte_completo(sujeto_rte)
                                nombre_rte = f"RTE_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                                st.success(f"RTE generado correctamente ({len(pdf_rte)/1024:.0f} KB)")
                                st.download_button(
                                    label="Descargar RTE PDF",
                                    data=pdf_rte,
                                    file_name=nombre_rte,
                                    mime="application/pdf",
                                    use_container_width=True,
                                    type="primary"
                                )
                            except Exception as e:
                                st.error(f"Error al generar RTE: {e}")
                                import traceback
                                st.code(traceback.format_exc())
