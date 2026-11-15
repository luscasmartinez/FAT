"""Aba de análise por COD_GRUPO."""

from __future__ import annotations

import pandas as pd

from faturamento.comparacao import FontesComparacao
from faturamento.paginas.entidade import pagina_dimensao


def pagina_grupos(
    df: pd.DataFrame,
    filtros_texto: list[str],
    prefixo: str,
    *,
    fontes_comparacao: FontesComparacao | None = None,
    filtros_comparacao: dict | None = None,
) -> None:
    pagina_dimensao(
        df,
        coluna="COD_GRUPO",
        titulo="Análise por COD_GRUPO",
        subtitulo="Código de grupo da ligação. Não é o COD_GRUPO_RUBRICA.",
        nome_total="Faturamento total",
        nome_quantidade="Quantidade de códigos de grupo",
        detalhe_quantidade="Códigos com lançamento no recorte",
        nome_maior="Código com maior faturamento",
        nome_menor="Código com menor faturamento positivo",
        titulo_ranking="Ranking por código de grupo",
        titulo_composicao="Composição por código de grupo",
        prefixo=prefixo,
        filtros_texto=filtros_texto,
        lado_a_lado=True,
        nome_arquivo="faturamento_cod_grupo.csv",
        fontes_comparacao=fontes_comparacao,
        filtros_comparacao=filtros_comparacao,
    )
