"""Gráficos Plotly na paleta do Book Comercial."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from faturamento.constantes import (
    COL_PART,
    COL_TOTAL,
    COR_AZUL,
    COR_GRAFITE,
    COR_NEGATIVO,
    CORES,
    ORDEM_CLASSIFICACAO,
    ROTULOS,
)
from faturamento.formato import brl, compacto, decimal, escala_eixo, percentual

CONFIG = {
    "displaylogo": False,
    "responsive": True,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
}

CLARAS = {"CONTAS DE ESGOTO", "INDIRETAS ESGOTO"}


def _base(fig: go.Figure, altura: int) -> go.Figure:
    fig.update_layout(
        height=altura,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color=COR_GRAFITE, size=12),
        margin=dict(l=8, r=16, t=8, b=8),
        legend=dict(orientation="h", yanchor="top", y=-0.12, x=0, font=dict(size=11)),
        hoverlabel=dict(
            bgcolor=COR_AZUL,
            font_size=12,
            font_color="#ffffff",
            font_family="Inter, Segoe UI, sans-serif",
        ),
        hovermode="closest",
    )
    return fig


def grafico_rosca(resumo: pd.DataFrame) -> go.Figure | None:
    valores = resumo["Faturamento"].tolist()
    if not valores or any(valor < 0 for valor in valores) or sum(valores) == 0:
        return None
    cores = [CORES[codigo] for codigo in resumo["codigo"]]
    fig = go.Figure(
        go.Pie(
            labels=resumo["Classificação"],
            values=valores,
            hole=0.62,
            sort=False,
            direction="clockwise",
            marker=dict(colors=cores, line=dict(color="#ffffff", width=2)),
            customdata=[brl(valor) for valor in valores],
            hovertemplate="<b>%{label}</b><br>%{customdata}<br>%{percent}<extra></extra>",
            textinfo="percent",
            textfont=dict(
                size=12,
                color=["#191B23" if codigo in CLARAS else "#ffffff" for codigo in resumo["codigo"]],
            ),
        )
    )
    total = float(sum(valores))
    fig.update_layout(
        annotations=[
            dict(
                text=compacto(total),
                x=0.5,
                y=0.54,
                showarrow=False,
                font=dict(size=18, color=COR_AZUL, family="Inter, Segoe UI, sans-serif"),
            ),
            dict(
                text="faturamento",
                x=0.5,
                y=0.44,
                showarrow=False,
                font=dict(size=11, color="#44495C", family="Inter, Segoe UI, sans-serif"),
            ),
        ],
        showlegend=True,
    )
    return _base(fig, 420)


def grafico_barras_classificacao(resumo: pd.DataFrame) -> go.Figure:
    valores = resumo["Faturamento"].tolist()
    fator, titulo = escala_eixo(valores)
    cores = [COR_NEGATIVO if valor < 0 else CORES[codigo] for codigo, valor in zip(resumo["codigo"], valores)]
    fig = go.Figure(
        go.Bar(
            x=resumo["Classificação"],
            y=[valor / fator for valor in valores],
            marker_color=cores,
            customdata=[f"{brl(valor)} · {percentual(part)}" for valor, part in zip(valores, resumo[COL_PART])],
            hovertemplate="<b>%{x}</b><br>%{customdata}<extra></extra>",
        )
    )
    fig.update_yaxes(title=titulo, showgrid=True, gridcolor="#E2E5F0", zerolinecolor="#D3D7E6")
    fig.update_xaxes(showgrid=False)
    return _base(fig, 420)


def grafico_grupos_faturamento(tabela: pd.DataFrame, referencia: pd.Timestamp) -> go.Figure:
    dados = tabela.loc[tabela["Indicador"].eq("Faturamento Total Líquido")].copy()
    por_grupo = {}
    for _, linha in dados.iterrows():
        grupo = linha["Dimensão"]
        rotulo = "N/A" if pd.isna(grupo) else str(int(grupo)) if _inteiro(grupo) else str(grupo)
        por_grupo[rotulo] = linha

    extras = sorted(
        (rotulo for rotulo in por_grupo if rotulo not in {str(codigo) for codigo in range(1, 18)} | {"N/A"}),
        key=lambda rotulo: (not _inteiro(rotulo), int(rotulo) if _inteiro(rotulo) else rotulo),
    )
    categorias = [str(codigo) for codigo in range(1, 18)] + extras + ["N/A"]
    metas = [float(por_grupo[grupo]["Meta"]) if grupo in por_grupo and pd.notna(por_grupo[grupo]["Meta"]) else 0.0 for grupo in categorias]
    realizados = [
        float(por_grupo[grupo]["Realizado líquido"])
        if grupo in por_grupo and pd.notna(por_grupo[grupo]["Realizado líquido"])
        else 0.0
        for grupo in categorias
    ]
    atingimentos = [
        float(por_grupo[grupo]["Realizado líquido"]) / metas[indice]
        if (
            grupo in por_grupo
            and metas[indice] != 0
            and pd.notna(por_grupo[grupo]["Realizado líquido"])
        )
        else None
        for indice, grupo in enumerate(categorias)
    ]
    rotulos_meta = [
        decimal(metas[indice] / 1_000_000, 1) if grupo in por_grupo and pd.notna(por_grupo[grupo]["Meta"]) else ""
        for indice, grupo in enumerate(categorias)
    ]
    rotulos_realizados = [
        decimal(realizados[indice] / 1_000_000, 1)
        if grupo in por_grupo and pd.notna(por_grupo[grupo]["Realizado líquido"])
        else ""
        for indice, grupo in enumerate(categorias)
    ]
    rotulos_atingimento = [f"{valor:.0%}" if valor is not None else "" for valor in atingimentos]

    mes_anterior = referencia.replace(day=1) - pd.DateOffset(months=1)
    meses = (
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    )
    subtitulo = (
        f"Valor do mês por GF • {meses[mes_anterior.month - 1]}/{mes_anterior.year} "
        "• R$ milhões • orçado RF2T26"
    )

    fig = _base(go.Figure(), 460)
    fig.add_trace(
        go.Bar(
            x=categorias,
            y=[valor / 1_000_000 for valor in metas],
            name="Orçado RF2T26",
            marker_color="#000080",
            text=rotulos_meta,
            textposition="outside",
            textfont=dict(color="#000080", size=12),
            cliponaxis=False,
            hovertemplate="<b>GF %{x}</b><br>Orçado: R$ %{y:.1f} milhões<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=categorias,
            y=[valor / 1_000_000 for valor in realizados],
            name="Realizado",
            marker_color="#17E3CB",
            text=rotulos_realizados,
            textposition="outside",
            textfont=dict(color="#00AFC4", size=12),
            cliponaxis=False,
            hovertemplate="<b>GF %{x}</b><br>Realizado: R$ %{y:.1f} milhões<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=categorias,
            y=atingimentos,
            yaxis="y2",
            name="% de atingimento",
            mode="lines+markers+text",
            line=dict(color="#FFA500", width=2),
            marker=dict(symbol="circle", size=8, color="#FFFFFF", line=dict(color="#FFA500", width=2)),
            text=rotulos_atingimento,
            textposition="top center",
            textfont=dict(color="#FFA500", size=12, family="Inter, Segoe UI, sans-serif"),
            cliponaxis=False,
            hovertemplate="<b>GF %{x}</b><br>Atingimento: %{y:.0%}<extra></extra>",
        )
    )

    maximo = max([*metas, *realizados], default=0) / 1_000_000
    minimo = min([*metas, *realizados], default=0) / 1_000_000
    fig.update_layout(
        title=dict(
            text=(
                "<b>Por grupo de faturamento</b><br>"
                f"<span style='font-size:13px;color:#44495C;font-weight:400'>{subtitulo}</span>"
            ),
            x=0,
            xanchor="left",
            y=0.98,
            yanchor="top",
            font=dict(size=18, color="#000080"),
        ),
        barmode="group",
        bargap=0.3,
        bargroupgap=0.06,
        margin=dict(l=12, r=12, t=82, b=78),
        legend=dict(orientation="h", yanchor="top", y=-0.17, x=0, font=dict(size=12)),
        hovermode="x unified",
        yaxis=dict(
            range=[min(0, minimo * 1.08), max(1, maximo / 0.65)],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            title=None,
        ),
        yaxis2=dict(
            overlaying="y",
            side="right",
            range=[0, 1.1],
            tickformat=".0%",
            showgrid=False,
            zeroline=False,
            showticklabels=False,
        ),
    )
    fig.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=categorias,
        showgrid=False,
        showline=True,
        linecolor="#D3D7E6",
        linewidth=1,
        ticks="",
    )
    return fig


def grafico_atingimento(tabela: pd.DataFrame, coluna: str) -> go.Figure | None:
    dados = tabela.loc[
        tabela["Indicador"].eq("Faturamento Total Líquido") & tabela["Atingimento"].notna()
    ].sort_values("Atingimento", ascending=True)
    if dados.empty:
        return None
    rotulos = dados[coluna].astype("string").tolist()
    valores = (dados["Atingimento"] * 100).tolist()
    cores_status = {
        "Atingido": "#0A8F80",
        "Em atenção": "#FE952B",
        "Abaixo": COR_NEGATIVO,
    }
    customdata = [
        [brl(realizado), brl(meta), str(status)]
        for realizado, meta, status in zip(
            dados["Realizado líquido"], dados["Meta"], dados["Status"]
        )
    ]
    fig = go.Figure(
        go.Bar(
            y=rotulos,
            x=valores,
            orientation="h",
            marker_color=[cores_status.get(status, COR_NEGATIVO) for status in dados["Status"]],
            customdata=customdata,
            hovertemplate=(
                "<b>%{y}</b><br>Atingimento: %{x:.2f}%<br>Realizado: %{customdata[0]}"
                "<br>Meta: %{customdata[1]}<br>%{customdata[2]}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=100, line_dash="dash", line_color=COR_GRAFITE, opacity=0.7)
    fig.update_xaxes(title="Atingimento da meta (%)", showgrid=True, gridcolor="#E2E5F0", zeroline=False)
    fig.update_yaxes(automargin=True, showgrid=False)
    return _base(fig, min(900, 110 + 26 * len(dados)))


def grafico_ranking(tabela: pd.DataFrame, coluna: str, titulo_eixo_categoria: str) -> go.Figure:
    dados = tabela.sort_values(COL_TOTAL, ascending=True)
    valores = dados[COL_TOTAL].tolist()
    fator, titulo = escala_eixo(valores)
    rotulos = dados[coluna].map(lambda v: str(int(v)) if _inteiro(v) else str(v))
    fig = go.Figure(
        go.Bar(
            y=rotulos,
            x=[valor / fator for valor in valores],
            orientation="h",
            marker_color=[COR_NEGATIVO if valor < 0 else COR_AZUL for valor in valores],
            customdata=[f"{brl(valor)} · {percentual(part)}" for valor, part in zip(valores, dados[COL_PART])],
            hovertemplate="<b>%{y}</b><br>%{customdata}<extra></extra>",
        )
    )
    fig.update_xaxes(title=titulo, showgrid=True, gridcolor="#E2E5F0", zerolinecolor="#D3D7E6")
    fig.update_yaxes(title=titulo_eixo_categoria, showgrid=False, automargin=True)
    altura = min(1600, 90 + 24 * max(len(dados), 1))
    return _base(fig, altura)


def grafico_composicao(tabela: pd.DataFrame, coluna: str) -> go.Figure:
    dados = tabela.sort_values(COL_TOTAL, ascending=True)
    rotulos = dados[coluna].map(lambda v: str(int(v)) if _inteiro(v) else str(v))
    blocos = [ROTULOS[codigo] for codigo in ORDEM_CLASSIFICACAO]
    valores_todos = []
    for nome in blocos:
        valores_todos.extend(dados[nome].tolist())
    fator, titulo = escala_eixo(valores_todos)
    fig = go.Figure()
    for codigo in ORDEM_CLASSIFICACAO:
        nome = ROTULOS[codigo]
        valores = dados[nome].tolist()
        fig.add_trace(
            go.Bar(
                y=rotulos,
                x=[valor / fator for valor in valores],
                name=nome,
                orientation="h",
                marker_color=CORES[codigo],
                customdata=[brl(valor) for valor in valores],
                hovertemplate="<b>%{y}</b><br>" + nome + ": %{customdata}<extra></extra>",
            )
        )
    fig.update_layout(barmode="relative")
    fig.update_xaxes(title=titulo, showgrid=True, gridcolor="#E2E5F0", zerolinecolor="#D3D7E6")
    fig.update_yaxes(automargin=True, showgrid=False)
    altura = min(1700, 120 + 24 * max(len(dados), 1))
    return _base(fig, altura)


def _inteiro(valor) -> bool:
    try:
        if pd.isna(valor):
            return False
        int(valor)
        return True
    except (TypeError, ValueError):
        return False
