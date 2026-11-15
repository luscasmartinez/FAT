"""Regra única de faturamento.

Uma linha entra no faturamento se a classe for conta de água, água SB,
esgoto ou esgoto SB, ou se o grupo for indiretas de água ou de esgoto.
A linha é contada uma única vez. Valores negativos permanecem negativos.
"""

from __future__ import annotations

import math

import pandas as pd

from faturamento.constantes import (
    CLASSES_ELEGIVEIS,
    COL_PART,
    COL_QTD,
    COL_TOTAL,
    GRUPOS_LIQUIDOS,
    GRUPOS_INDIRETAS,
    ORDEM_CLASSIFICACAO,
    ROTULOS,
)


def classificar(df: pd.DataFrame) -> pd.Series:
    """Atribui uma classificação exclusiva.

    A classe de conta tem prioridade sobre o grupo de indiretas. Na base
    26-11 os dois critérios não se cruzam; a prioridade evita dupla contagem
    se uma carga futura trouxer uma linha que atenda aos dois.
    """
    classificacao = pd.Series(pd.NA, index=df.index, dtype="string")
    por_classe = df["CLASSE_RUBRICA"].isin(CLASSES_ELEGIVEIS)
    classificacao = classificacao.mask(por_classe, df["CLASSE_RUBRICA"])
    por_grupo = classificacao.isna() & df["GRUPO_RUBRICA"].isin(GRUPOS_INDIRETAS)
    classificacao = classificacao.mask(por_grupo, df["GRUPO_RUBRICA"])
    return classificacao


def preparar_faturamento(df: pd.DataFrame) -> pd.DataFrame:
    """Recorte elegível, com a coluna CLASSIFICACAO. Não altera SumVALOR."""
    classificacao = classificar(df)
    faturamento = df.loc[classificacao.notna()].copy()
    faturamento["CLASSIFICACAO"] = classificacao.loc[faturamento.index].astype("string")
    return faturamento


def somar_series(valores) -> float:
    if valores is None:
        return 0.0
    if isinstance(valores, pd.Series):
        dados = valores.to_numpy()
    else:
        dados = list(valores)
    if len(dados) == 0:
        return 0.0
    return float(math.fsum(float(valor) for valor in dados))


def somar_faturamento(df: pd.DataFrame) -> float:
    """Soma SumVALOR apenas de linhas já classificadas pela regra de negócio."""
    if df is None or df.empty:
        return 0.0
    if "CLASSIFICACAO" not in df.columns:
        df = preparar_faturamento(df)
    if df.empty:
        return 0.0
    return somar_series(df["SumVALOR"])


def totais_liquidos(df: pd.DataFrame) -> dict[str, float]:
    """Calcula os totais de água, esgoto e indiretas, preservando abatimentos negativos."""
    if df is None or df.empty:
        classificados = pd.DataFrame(columns=["CLASSIFICACAO", "SumVALOR"])
    elif "CLASSIFICACAO" not in df.columns:
        classificados = preparar_faturamento(df)
    else:
        classificados = df

    totais = {
        nome: somar_series(
            classificados.loc[classificados["CLASSIFICACAO"].isin(componentes), "SumVALOR"]
        )
        for nome, componentes in GRUPOS_LIQUIDOS.items()
    }
    totais["Faturamento Total Líquido"] = somar_series(totais.values())
    return totais


def resumo_liquidos(df: pd.DataFrame, total_referencia: float | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        classificados = pd.DataFrame(columns=["CLASSIFICACAO", "SumVALOR"])
    elif "CLASSIFICACAO" not in df.columns:
        classificados = preparar_faturamento(df)
    else:
        classificados = df
    total = somar_faturamento(classificados) if total_referencia is None else float(total_referencia)
    totais = totais_liquidos(classificados)
    linhas = []
    for codigo, componentes in GRUPOS_LIQUIDOS.items():
        valor = totais[codigo]
        linhas.append(
            {
                "codigo": codigo,
                "Classificação": codigo,
                COL_QTD: int(classificados["CLASSIFICACAO"].isin(componentes).sum()),
                "Faturamento": valor,
                COL_PART: valor / total if total else 0.0,
            }
        )
    return pd.DataFrame(linhas)


def aplicar_filtros(
    df: pd.DataFrame,
    *,
    cidades=None,
    codigos_grupo=None,
    classes=None,
    grupos=None,
    descricoes=None,
) -> pd.DataFrame:
    """Filtros são interseção. Lista vazia ou None significa 'todos'."""
    recorte = df
    if cidades:
        recorte = recorte.loc[recorte["CIDADE"].isin(cidades)]
    if codigos_grupo:
        recorte = recorte.loc[recorte["COD_GRUPO"].isin(list(codigos_grupo))]
    if classes:
        recorte = recorte.loc[recorte["CLASSE_RUBRICA"].isin(classes)]
    if grupos:
        recorte = recorte.loc[recorte["GRUPO_RUBRICA"].isin(grupos)]
    if descricoes:
        recorte = recorte.loc[recorte["DESCRICAO_RUBRICA"].isin(descricoes)]
    return recorte


def resumo_classificacao(df: pd.DataFrame, total_referencia: float | None = None) -> pd.DataFrame:
    total = somar_faturamento(df) if total_referencia is None else float(total_referencia)
    if df.empty:
        valores = {}
        quantidades = {}
    else:
        valores = df.groupby("CLASSIFICACAO", dropna=False)["SumVALOR"].apply(somar_series).to_dict()
        quantidades = df.groupby("CLASSIFICACAO", dropna=False).size().to_dict()
    linhas = []
    for codigo in ORDEM_CLASSIFICACAO:
        valor = float(valores.get(codigo, 0.0))
        linhas.append(
            {
                "codigo": codigo,
                "Classificação": ROTULOS[codigo],
                COL_QTD: int(quantidades.get(codigo, 0)),
                "Faturamento": valor,
                COL_PART: (valor / total) if total else 0.0,
            }
        )
    return pd.DataFrame(linhas)


def agregar_entidade(
    df: pd.DataFrame,
    coluna: str,
    total_referencia: float | None = None,
) -> pd.DataFrame:
    nomes = [ROTULOS[codigo] for codigo in ORDEM_CLASSIFICACAO]
    if df.empty:
        return pd.DataFrame(columns=[coluna, *nomes, COL_TOTAL, COL_PART])

    tabela = df.pivot_table(
        index=coluna,
        columns="CLASSIFICACAO",
        values="SumVALOR",
        aggfunc=somar_series,
        fill_value=0.0,
        dropna=False,
    )
    for codigo in ORDEM_CLASSIFICACAO:
        if codigo not in tabela.columns:
            tabela[codigo] = 0.0
    tabela = tabela[list(ORDEM_CLASSIFICACAO)].rename(columns=ROTULOS)
    tabela[COL_TOTAL] = tabela[nomes].sum(axis=1)
    base = somar_faturamento(df) if total_referencia is None else float(total_referencia)
    tabela[COL_PART] = tabela[COL_TOTAL] / base if base else 0.0
    tabela = tabela.reset_index()
    return tabela


def agregar_rubricas(df: pd.DataFrame, total_referencia: float | None = None) -> pd.DataFrame:
    chaves = ["COD_RUBRICA", "DESCRICAO_RUBRICA", "CLASSE_RUBRICA", "GRUPO_RUBRICA"]
    colunas = chaves + ["Faturamento", COL_QTD, COL_PART]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    tabela = (
        df.groupby(chaves, dropna=False)
        .agg(Faturamento=("SumVALOR", somar_series), Registros=("SumVALOR", "size"))
        .reset_index()
    )
    base = somar_faturamento(df) if total_referencia is None else float(total_referencia)
    tabela[COL_PART] = tabela["Faturamento"] / base if base else 0.0
    return tabela


def extremos_positivos(tabela: pd.DataFrame, coluna: str):
    """Maior valor e menor valor estritamente positivo da coluna de total."""
    if tabela.empty:
        return None, None
    ordenada = tabela.sort_values([COL_TOTAL, coluna], ascending=[False, True])
    maior = ordenada.iloc[0]
    positivos = ordenada.loc[ordenada[COL_TOTAL] > 0].sort_values(
        [COL_TOTAL, coluna], ascending=[True, True]
    )
    menor = None if positivos.empty else positivos.iloc[0]
    return maior, menor
