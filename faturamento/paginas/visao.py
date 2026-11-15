"""Aba de visão geral."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from faturamento.calculo import resumo_classificacao, resumo_liquidos, somar_faturamento, totais_liquidos
from faturamento.comparacao import FontesComparacao, construir_comparacoes
from faturamento.componentes import aviso, cabecalho, cartao, chips, kpis, mostrar_tabela
from faturamento.constantes import COL_PART, COL_QTD
from faturamento.formato import brl, compacto, inteiro, percentual
from faturamento.graficos import CONFIG, grafico_barras_classificacao, grafico_rosca
from faturamento.paginas.comparativo import mostrar_comparacao
from faturamento.validacao import tudo_ok


def pagina_visao(
    df: pd.DataFrame,
    meta: dict,
    checks: list[dict],
    filtros_texto: list[str],
    prefixo: str,
    *,
    fontes_comparacao: FontesComparacao | None = None,
    filtros_comparacao: dict | None = None,
) -> None:
    total = somar_faturamento(df)
    resumo = resumo_classificacao(df, total)
    resumo_grupos = resumo_liquidos(df, total)
    totais = totais_liquidos(df)
    cabecalho(
        "Visão geral",
        f"Base {meta['nome']} · {inteiro(meta['linhas_faturamento'])} lançamentos no critério de faturamento",
    )
    chips(filtros_texto)
    aviso(
        "O faturamento líquido soma contas e abatimentos de água, contas e abatimentos de esgoto, "
        "e indiretas de água e esgoto. "
        f"Fora desse critério ficam {inteiro(meta['linhas_fora'])} linhas, no valor de {brl(meta['valor_fora'])}, "
        "que não entram nos indicadores. Valores negativos são mantidos.",
        "info",
    )

    itens = [
        {
            "rotulo": "Faturamento Total Líquido",
            "valor": compacto(total),
            "detalhe": brl(total),
            "destaque": True,
            "negativo": total < 0,
        }
    ]
    for rotulo in (
        "Faturamento Líquido de Água",
        "Faturamento Líquido de Esgoto",
        "Faturamento de Indiretas",
    ):
        valor = totais[rotulo]
        itens.append(
            {
                "rotulo": rotulo,
                "valor": compacto(valor),
                "detalhe": brl(valor),
                "negativo": valor < 0,
            }
        )
    kpis(itens)

    if fontes_comparacao is not None:
        financeiro, operacional, _ = construir_comparacoes(
            df, fontes_comparacao, **(filtros_comparacao or {})
        )
        nota = (
            "Meta financeira indisponível no nível de DESCRICAO_RUBRICA; valores realizados refletem o filtro de rubrica."
            if (filtros_comparacao or {}).get("descricoes")
            else None
        )
        mostrar_comparacao(
            financeiro,
            operacional,
            prefixo=f"{prefixo}_meta",
            referencia=fontes_comparacao.referencia,
            avisos=fontes_comparacao.avisos,
            nota=nota,
        )

    esquerda, direita = st.columns(2)
    with esquerda:
        with st.container(border=True):
            cartao("Composição do faturamento", "Participação dos três totais líquidos no total do recorte")
            rosca = grafico_rosca(resumo_grupos)
            if rosca is None:
                aviso("A rosca fica oculta quando alguma classificação tem total negativo ou o recorte está zerado. Use o gráfico de barras ao lado.", "info")
            else:
                st.plotly_chart(rosca, use_container_width=True, config=CONFIG)
    with direita:
        with st.container(border=True):
            cartao("Faturamento por grupo líquido", "Passe o mouse para ver o valor exato")
            st.plotly_chart(grafico_barras_classificacao(resumo_grupos), use_container_width=True, config=CONFIG)

    with st.container(border=True):
        cartao("Memória de cálculo", "Contas, abatimentos e indiretas que compõem os totais líquidos")
        mostrar_tabela(
            resumo.drop(columns=["codigo"]),
            [
                {"campo": "Classificação", "titulo": "Classificação", "tipo": "texto"},
                {"campo": COL_QTD, "titulo": "Quantidade de registros", "tipo": "inteiro"},
                {"campo": "Faturamento", "titulo": "Faturamento", "tipo": "moeda"},
                {"campo": COL_PART, "titulo": "Participação", "tipo": "pct", "barra": True},
            ],
            prefixo=f"{prefixo}_visao",
            campos_busca=["Classificação"],
            nome_arquivo="faturamento_classificacao.csv",
            rotulo_busca="Pesquisar classificação",
        )

    with st.expander("Conferência dos cálculos", expanded=not tudo_ok(checks)):
        for item in checks:
            marca = "OK" if item["ok"] else "Falha"
            aviso(f"<b>{marca}.</b> {item['nome']}. {item['detalhe']}", "ok" if item["ok"] else "erro")
