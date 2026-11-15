"""Página compartilhada de cidade e COD_GRUPO."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from faturamento.calculo import agregar_entidade, extremos_positivos, somar_faturamento
from faturamento.comparacao import FontesComparacao, construir_comparacoes
from faturamento.componentes import aviso, cabecalho, cartao, chips, kpis, mostrar_tabela
from faturamento.constantes import COL_PART, COL_TOTAL, ORDEM_CLASSIFICACAO, ROTULOS
from faturamento.formato import brl, codigo, compacto, inteiro
from faturamento.graficos import CONFIG, grafico_barras_classificacao, grafico_composicao, grafico_ranking
from faturamento.calculo import resumo_classificacao
from faturamento.paginas.comparativo import mostrar_comparacao


def pagina_dimensao(
    df: pd.DataFrame,
    *,
    coluna: str,
    titulo: str,
    subtitulo: str,
    nome_total: str,
    nome_quantidade: str,
    detalhe_quantidade: str,
    nome_maior: str,
    nome_menor: str,
    titulo_ranking: str,
    titulo_composicao: str,
    prefixo: str,
    filtros_texto: list[str],
    lado_a_lado: bool,
    nome_arquivo: str,
    fontes_comparacao: FontesComparacao | None = None,
    filtros_comparacao: dict | None = None,
) -> None:
    cabecalho(titulo, subtitulo)
    chips(filtros_texto)
    if df.empty:
        aviso("Nenhum lançamento de faturamento no recorte dos filtros.", "info")
        return

    total_geral = somar_faturamento(df)
    tabela = agregar_entidade(df, coluna, total_geral)
    if coluna == "COD_GRUPO":
        tabela[coluna] = tabela[coluna].map(codigo)
    quantidade = int(tabela[coluna].nunique()) if not tabela.empty else 0
    maior, menor = extremos_positivos(tabela, coluna)

    def detalhe_extremo(linha) -> str:
        if linha is None:
            return "Nenhum valor positivo neste recorte."
        return f"{linha[coluna]} · {brl(float(linha[COL_TOTAL]))}"

    kpis(
        [
            {
                "rotulo": nome_total,
                "valor": compacto(total_geral),
                "detalhe": brl(total_geral),
                "destaque": True,
                "negativo": total_geral < 0,
            },
            {
                "rotulo": nome_quantidade,
                "valor": inteiro(quantidade),
                "detalhe": detalhe_quantidade,
            },
            {
                "rotulo": nome_maior,
                "valor": compacto(float(maior[COL_TOTAL])) if maior is not None else "—",
                "detalhe": detalhe_extremo(maior),
                "negativo": maior is not None and float(maior[COL_TOTAL]) < 0,
            },
            {
                "rotulo": nome_menor,
                "valor": compacto(float(menor[COL_TOTAL])) if menor is not None else "—",
                "detalhe": detalhe_extremo(menor),
            },
        ]
    )

    if fontes_comparacao is not None:
        filtros_meta = dict(filtros_comparacao or {})
        financeiro_meta, operacional_meta, _ = construir_comparacoes(
            df, fontes_comparacao, dimensao=coluna, **filtros_meta
        )
        nota = (
            "A meta não possui detalhamento por DESCRICAO_RUBRICA; os indicadores usam a granularidade disponível por cidade e COD_GRUPO."
            if filtros_meta.get("descricoes")
            else None
        )
        mostrar_comparacao(
            financeiro_meta,
            operacional_meta,
            prefixo=f"{prefixo}_meta_{coluna}",
            referencia=fontes_comparacao.referencia,
            avisos=fontes_comparacao.avisos,
            nota=nota,
        )

    unico = quantidade <= 1
    if lado_a_lado and not unico and quantidade <= 25:
        colunas = st.columns(2)
    else:
        colunas = None

    def bloco_ranking():
        with st.container(border=True):
            cartao(titulo_ranking, "Ordenado do maior para o menor faturamento. O tooltip mostra o valor exato.")
            st.plotly_chart(grafico_ranking(tabela, coluna, ""), use_container_width=True, config=CONFIG)

    def bloco_composicao():
        with st.container(border=True):
            cartao(titulo_composicao, "Oito componentes da regra de faturamento")
            if unico:
                resumo = resumo_classificacao(df, total_geral)
                st.plotly_chart(grafico_barras_classificacao(resumo), use_container_width=True, config=CONFIG)
            else:
                st.plotly_chart(grafico_composicao(tabela, coluna), use_container_width=True, config=CONFIG)

    if colunas:
        with colunas[0]:
            bloco_ranking()
        with colunas[1]:
            bloco_composicao()
    else:
        bloco_ranking()
        bloco_composicao()

    nomes = [ROTULOS[codigo] for codigo in ORDEM_CLASSIFICACAO]
    especificacao = [{"campo": coluna, "titulo": coluna if coluna != "CIDADE" else "Cidade", "tipo": "texto" if coluna == "CIDADE" else "codigo"}]
    especificacao += [{"campo": nome, "titulo": nome, "tipo": "moeda"} for nome in nomes]
    especificacao += [
        {"campo": COL_TOTAL, "titulo": "Faturamento total", "tipo": "moeda"},
        {"campo": COL_PART, "titulo": "Participação no faturamento geral", "tipo": "pct", "barra": True},
    ]
    with st.container(border=True):
        cartao(
            "Tabela detalhada",
            "A participação usa o faturamento do recorte aplicado pelos filtros gerais.",
        )
        mostrar_tabela(
            tabela,
            especificacao,
            prefixo=f"{prefixo}_tab",
            nome_arquivo=nome_arquivo,
        )
