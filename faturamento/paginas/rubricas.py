"""Aba de análise por rubrica."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from faturamento.calculo import agregar_rubricas, somar_faturamento, somar_series
from faturamento.comparacao import FontesComparacao, construir_comparacoes
from faturamento.componentes import aviso, cabecalho, cartao, chips, kpis, mostrar_tabela
from faturamento.constantes import COL_PART, COL_QTD
from faturamento.formato import brl, compacto, inteiro, percentual
from faturamento.graficos import CONFIG, grafico_ranking
from faturamento.paginas.comparativo import mostrar_comparacao


def pagina_rubricas(
    df: pd.DataFrame,
    filtros_texto: list[str],
    prefixo: str,
    *,
    fontes_comparacao: FontesComparacao | None = None,
    filtros_comparacao: dict | None = None,
) -> None:
    cabecalho(
        "Análise por rubrica",
        "Descrição, código, classe e grupo. Os filtros de classe e grupo ficam na barra lateral.",
    )
    chips(filtros_texto)
    if df.empty:
        aviso("Nenhum lançamento de faturamento no recorte dos filtros.", "info")
        return

    total = somar_faturamento(df)
    tabela = agregar_rubricas(df, total)
    tabela = tabela.rename(
        columns={
            "COD_RUBRICA": "Código",
            "DESCRICAO_RUBRICA": "Descrição",
            "CLASSE_RUBRICA": "Classe",
            "GRUPO_RUBRICA": "Grupo",
            "Faturamento": "Faturamento",
            COL_QTD: "Quantidade de registros",
            COL_PART: "Participação",
        }
    )

    termo_chave = f"{prefixo}_desc"
    termo = st.text_input("Pesquisar descrição da rubrica", key=termo_chave, placeholder="Digite parte da descrição")
    visao = tabela
    realizado_comparacao = df
    filtros_meta = dict(filtros_comparacao or {})
    if termo:
        corresponde = df["DESCRICAO_RUBRICA"].astype("string").str.contains(termo, case=False, na=False)
        visao = tabela.loc[tabela["Descrição"].astype("string").str.contains(termo, case=False, na=False)]
        realizado_comparacao = df.loc[corresponde]
        filtros_meta["descricoes"] = [termo]

    if fontes_comparacao is not None:
        financeiro_meta, operacional_meta, _ = construir_comparacoes(
            realizado_comparacao, fontes_comparacao, **filtros_meta
        )
        mostrar_comparacao(
            financeiro_meta,
            operacional_meta,
            prefixo=f"{prefixo}_meta_rubricas",
            referencia=fontes_comparacao.referencia,
            avisos=fontes_comparacao.avisos,
            nota=(
                "A meta existe por agrupador e COD_GRUPO, não por descrição individual; a busca de rubrica não redistribui a meta."
                if termo or filtros_meta.get("descricoes")
                else "A meta é exibida na granularidade disponível por cidade, COD_GRUPO e agrupador."
            ),
        )

    total_visao = somar_series(visao["Faturamento"]) if not visao.empty else 0.0
    if visao.empty:
        maior_nome = "—"
        maior_valor = 0.0
        maior_part = 0.0
    else:
        topo = visao.sort_values(["Faturamento", "Descrição"], ascending=[False, True]).iloc[0]
        maior_nome = str(topo["Descrição"])
        maior_valor = float(topo["Faturamento"])
        maior_part = float(topo["Participação"])

    kpis(
        [
            {
                "rotulo": "Faturamento das rubricas",
                "valor": compacto(total_visao),
                "detalhe": brl(total_visao) + (" · resultado da pesquisa" if termo else ""),
                "destaque": True,
                "negativo": total_visao < 0,
            },
            {
                "rotulo": "Quantidade de rubricas",
                "valor": inteiro(len(visao)),
                "detalhe": "Combinações de código, descrição, classe e grupo",
            },
            {
                "rotulo": "Maior rubrica",
                "valor": compacto(maior_valor) if not visao.empty else "—",
                "detalhe": f"{maior_nome} · {brl(maior_valor)}",
                "negativo": maior_valor < 0,
            },
            {
                "rotulo": "Participação da maior",
                "valor": percentual(maior_part) if not visao.empty else "—",
                "detalhe": "Sobre o faturamento do recorte, antes da pesquisa",
            },
        ]
    )

    ranking = (
        visao.groupby("Descrição", as_index=False)
        .agg(Faturamento=("Faturamento", "sum"), Participação=("Participação", "sum"))
        .sort_values("Faturamento", ascending=False)
        .head(15)
    )
    ranking = ranking.rename(columns={"Descrição": "Rubrica", "Faturamento": "Faturamento Total", "Participação": "Participação"})
    with st.container(border=True):
        cartao("Ranking das rubricas", "Até 15 descrições com maior faturamento. O tooltip mostra o valor exato.")
        if ranking.empty:
            aviso("Nenhuma rubrica encontrada para a pesquisa.", "info")
        else:
            st.plotly_chart(grafico_ranking(ranking, "Rubrica", ""), use_container_width=True, config=CONFIG)

    with st.container(border=True):
        cartao("Faturamento por rubrica", "Pesquise também na tabela. A participação é sobre o total do recorte.")
        mostrar_tabela(
            visao,
            [
                {"campo": "Descrição", "titulo": "Descrição", "tipo": "texto"},
                {"campo": "Código", "titulo": "Código", "tipo": "codigo"},
                {"campo": "Classe", "titulo": "Classe", "tipo": "texto"},
                {"campo": "Grupo", "titulo": "Grupo", "tipo": "texto"},
                {"campo": "Quantidade de registros", "titulo": "Quantidade de registros", "tipo": "inteiro"},
                {"campo": "Faturamento", "titulo": "Faturamento", "tipo": "moeda"},
                {"campo": "Participação", "titulo": "Participação", "tipo": "pct", "barra": True},
            ],
            prefixo=f"{prefixo}_rub",
            campos_busca=["Descrição", "Código", "Classe", "Grupo"],
            nome_arquivo="faturamento_rubricas.csv",
            rotulo_busca="Filtrar a tabela",
        )
