"""Leitura, validação de colunas e tipagem da planilha.

A carga sempre substitui a anterior. Não há concatenação entre arquivos.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from faturamento.constantes import CAMINHO_PADRAO, COLUNAS_OBRIGATORIAS

COLUNA_TOTAL_POWER_BI = "IsGrandTotalRowTotal"


class PlanilhaInvalida(ValueError):
    """A planilha não atende o contrato mínimo do painel."""


def _ler_excel(origem) -> pd.DataFrame:
    ultimo_erro = None
    for motor in ("calamine", "openpyxl"):
        try:
            if hasattr(origem, "seek"):
                origem.seek(0)
            return pd.read_excel(origem, engine=motor)
        except Exception as exc:
            ultimo_erro = exc
    raise PlanilhaInvalida(f"Não foi possível ler o arquivo Excel. {ultimo_erro}")


def _linha_de_total(serie: pd.Series) -> pd.Series:
    if serie.dtype == bool:
        return serie.fillna(False)
    texto = serie.astype("string").str.strip().str.lower()
    return texto.isin(["true", "1", "verdadeiro", "sim"])


def tratar_planilha(origem) -> tuple[pd.DataFrame, dict]:
    """Devolve a base tipada, sem a linha de total do Power BI, e metadados da leitura."""
    bruto = _ler_excel(origem)
    bruto.columns = [str(coluna).strip() for coluna in bruto.columns]
    faltantes = [coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in bruto.columns]
    if faltantes:
        lista = ", ".join(faltantes)
        raise PlanilhaInvalida(
            "Colunas obrigatórias ausentes: "
            f"{lista}. A importação não foi aplicada."
        )

    colunas_opcionais = ("NUM_LIGACAO", "MOTIVO_CANCELAMENTO")
    manter = list(COLUNAS_OBRIGATORIAS) + [
        coluna for coluna in colunas_opcionais if coluna in bruto.columns
    ]
    if COLUNA_TOTAL_POWER_BI in bruto.columns:
        manter.append(COLUNA_TOTAL_POWER_BI)
    dados = bruto[manter].copy()

    linhas_grand = 0
    if COLUNA_TOTAL_POWER_BI in dados.columns:
        totais = _linha_de_total(dados[COLUNA_TOTAL_POWER_BI])
        linhas_grand = int(totais.sum())
        dados = dados.loc[~totais].drop(columns=[COLUNA_TOTAL_POWER_BI])

    dados["SumVALOR"] = pd.to_numeric(dados["SumVALOR"], errors="coerce")
    invalidos = int(dados["SumVALOR"].isna().sum())
    if invalidos:
        raise PlanilhaInvalida(
            f"A coluna SumVALOR possui {invalidos} valor(es) vazio(s) ou não numérico(s). "
            "A importação não foi aplicada."
        )

    for coluna in ("CIDADE", "CLASSE_RUBRICA", "GRUPO_RUBRICA", "DESCRICAO_RUBRICA"):
        dados[coluna] = dados[coluna].astype("string").str.strip()
        dados[coluna] = dados[coluna].fillna("(não informado)")

    for coluna in ("COD_GRUPO", "COD_RUBRICA"):
        dados[coluna] = pd.to_numeric(dados[coluna], errors="coerce").astype("Int64")
    if "NUM_LIGACAO" in dados.columns:
        dados["NUM_LIGACAO"] = pd.to_numeric(
            dados["NUM_LIGACAO"], errors="coerce"
        ).astype("Int64")
    if "MOTIVO_CANCELAMENTO" in dados.columns:
        dados["MOTIVO_CANCELAMENTO"] = (
            dados["MOTIVO_CANCELAMENTO"].astype("string").str.strip()
        )

    if bool(dados["SumVALOR"].isna().any()):
        raise PlanilhaInvalida("SumVALOR ficou vazio depois da leitura.")

    info = {
        "linhas_grand": linhas_grand,
        "linhas_arquivo": int(len(dados)),
        "duplicadas_identicas": int(dados.duplicated().sum()),
    }
    return dados, info


def carregar_arquivo(origem, nome: str | None = None):
    """Lê a planilha e devolve bruto, faturamento elegível e metadados."""
    from faturamento.calculo import preparar_faturamento, somar_series

    dados, info = tratar_planilha(origem)
    faturamento = preparar_faturamento(dados)
    if nome is None:
        nome = Path(origem).name if isinstance(origem, (str, Path)) else "planilha.xlsx"

    valor_arquivo = somar_series(dados["SumVALOR"])
    valor_faturamento = somar_series(faturamento["SumVALOR"])
    negativos = faturamento["SumVALOR"] < 0
    meta = {
        "nome": nome,
        "linhas_grand": info["linhas_grand"],
        "linhas_arquivo": info["linhas_arquivo"],
        "linhas_faturamento": int(len(faturamento)),
        "linhas_fora": int(len(dados) - len(faturamento)),
        "duplicadas_identicas": info["duplicadas_identicas"],
        "valor_arquivo": valor_arquivo,
        "valor_faturamento": valor_faturamento,
        "valor_fora": valor_arquivo - valor_faturamento,
        "linhas_negativas": int(negativos.sum()),
        "valor_negativo": somar_series(faturamento.loc[negativos, "SumVALOR"]) if negativos.any() else 0.0,
    }
    if math.isnan(meta["valor_faturamento"]):
        raise PlanilhaInvalida("Não foi possível totalizar SumVALOR.")
    return dados, faturamento, meta


def carregar_padrao():
    if not CAMINHO_PADRAO.exists():
        raise PlanilhaInvalida(f"Base padrão não encontrada: {CAMINHO_PADRAO}")
    return carregar_arquivo(CAMINHO_PADRAO, CAMINHO_PADRAO.name)


def validar_upload_faturamento(conteudo: bytes, nome: str) -> dict:
    """Valida um upload sem gravá-lo e executa as conferências financeiras existentes."""
    import io

    try:
        livro = pd.ExcelFile(io.BytesIO(conteudo))
        if not livro.sheet_names:
            raise PlanilhaInvalida("O arquivo não contém abas.")
        aba = livro.sheet_names[0]
        bruto, faturamento, meta = carregar_arquivo(io.BytesIO(conteudo), nome=nome)
    except PlanilhaInvalida:
        raise
    except Exception as exc:
        raise PlanilhaInvalida("O arquivo Excel não pôde ser validado.") from exc

    if faturamento.empty:
        raise PlanilhaInvalida("A planilha não contém lançamentos elegíveis para faturamento.")

    from faturamento.validacao import tudo_ok, validar_base

    falhas = [item["nome"] for item in validar_base(bruto, faturamento, meta) if not item["ok"]]
    if falhas:
        raise PlanilhaInvalida("A base não passou nas conferências: " + "; ".join(falhas))
    return {
        "aba": aba,
        "linhas": meta["linhas_arquivo"],
        "linhas_faturamento": meta["linhas_faturamento"],
        "total": meta["valor_faturamento"],
    }
