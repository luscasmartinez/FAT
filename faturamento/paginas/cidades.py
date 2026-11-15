"""Aba de análise por cidade."""

from __future__ import annotations

import pandas as pd

from faturamento.comparacao import FontesComparacao
from faturamento.paginas.entidade import pagina_dimensao


def pagina_cidades(
    df: pd.DataFrame,
    filtros_texto: list[str],
    prefixo: str,
    *,
    fontes_comparacao: FontesComparacao | None = None,
    filtros_comparacao: dict | None = None,
) -> None:
    pagina_dimensao(
        df,
        coluna="CIDADE",
        titulo="Análise por cidade",
        subtitulo="Faturamento do recorte aberto por município",
        nome_total="Faturamento total",
        nome_quantidade="Quantidade de cidades",
        detalhe_quantidade="Municípios com lançamento no recorte",
        nome_maior="Cidade com maior faturamento",
        nome_menor="Cidade com menor faturamento positivo",
        titulo_ranking="Ranking de faturamento por cidade",
        titulo_composicao="Composição do faturamento por cidade",
        prefixo=prefixo,
        filtros_texto=filtros_texto,
        lado_a_lado=False,
        nome_arquivo="faturamento_cidades.csv",
        fontes_comparacao=fontes_comparacao,
        filtros_comparacao=filtros_comparacao,
    )
