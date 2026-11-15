"""Colunas, critérios e identidade visual do painel."""

from pathlib import Path

CAMINHO_PADRAO = (
    Path(__file__).resolve().parents[2]
    / "Faturamento_Liquido_2026"
    / "26-11.xlsx"
)

COLUNAS_OBRIGATORIAS = (
    "CIDADE",
    "CLASSE_RUBRICA",
    "GRUPO_RUBRICA",
    "COD_RUBRICA",
    "DESCRICAO_RUBRICA",
    "COD_GRUPO",
    "SumVALOR",
)

CLASSES_CONTA = (
    "CONTAS DE ÁGUA",
    "CONTAS DE ÁGUA SB",
    "CONTAS DE ESGOTO",
    "CONTAS DE ESGOTO SB",
)

CLASSES_ABATIMENTO = (
    "ABATIMENTO DE ÁGUA",
    "ABATIMENTO DE ESGOTO",
)

CLASSES_ELEGIVEIS = CLASSES_CONTA + CLASSES_ABATIMENTO

GRUPOS_INDIRETAS = (
    "INDIRETAS ÁGUA",
    "INDIRETAS ESGOTO",
)

ORDEM_CLASSIFICACAO = (
    "CONTAS DE ÁGUA",
    "CONTAS DE ÁGUA SB",
    "ABATIMENTO DE ÁGUA",
    "CONTAS DE ESGOTO",
    "CONTAS DE ESGOTO SB",
    "ABATIMENTO DE ESGOTO",
    *GRUPOS_INDIRETAS,
)

ROTULOS = {
    "CONTAS DE ÁGUA": "CONTAS DE ÁGUA",
    "CONTAS DE ÁGUA SB": "CONTAS DE ÁGUA SB",
    "ABATIMENTO DE ÁGUA": "ABATIMENTO DE ÁGUA",
    "CONTAS DE ESGOTO": "CONTAS DE ESGOTO",
    "CONTAS DE ESGOTO SB": "CONTAS DE ESGOTO SB",
    "ABATIMENTO DE ESGOTO": "ABATIMENTO DE ESGOTO",
    "INDIRETAS ÁGUA": "INDIRETAS ÁGUA",
    "INDIRETAS ESGOTO": "INDIRETAS ESGOTO",
}

GRUPOS_LIQUIDOS = {
    "Faturamento Líquido de Água": (
        "CONTAS DE ÁGUA",
        "CONTAS DE ÁGUA SB",
        "ABATIMENTO DE ÁGUA",
    ),
    "Faturamento Líquido de Esgoto": (
        "CONTAS DE ESGOTO",
        "CONTAS DE ESGOTO SB",
        "ABATIMENTO DE ESGOTO",
    ),
    "Faturamento de Indiretas": GRUPOS_INDIRETAS,
}

CORES = {
    "Faturamento Líquido de Água": "#111799",
    "Faturamento Líquido de Esgoto": "#0A8F80",
    "Faturamento de Indiretas": "#FE952B",
    "CONTAS DE ÁGUA": "#111799",
    "CONTAS DE ÁGUA SB": "#4F5BD5",
    "ABATIMENTO DE ÁGUA": "#E0383D",
    "CONTAS DE ESGOTO": "#17E3CB",
    "CONTAS DE ESGOTO SB": "#0A8F80",
    "ABATIMENTO DE ESGOTO": "#E0383D",
    "INDIRETAS ÁGUA": "#191B23",
    "INDIRETAS ESGOTO": "#FE952B",
}

COL_TOTAL = "Faturamento Total"
COL_PART = "Participação"
COL_QTD = "Registros"

COR_AZUL = "#111799"
COR_TURQUESA = "#17E3CB"
COR_FUNDO = "#E2E5F0"
COR_LINHA = "#D3D7E6"
COR_GRAFITE = "#191B23"
COR_POSITIVO = "#0A8F80"
COR_NEGATIVO = "#E0383D"
COR_MUTED = "#44495C"
COR_AZUL_SUAVE = "#DCE3FA"
