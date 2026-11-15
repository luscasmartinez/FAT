"""Leitura e comparação das metas com faturamento e indicadores operacionais."""

from __future__ import annotations

import io
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from faturamento.formato import brl

ROOT = Path(__file__).resolve().parents[2]
CAMINHO_META = ROOT / "Meta_2026" / "meta_26-11.xlsx"
CAMINHO_ECONOMIAS = ROOT / "Economias_2026" / "26-11_Economias_Fat.xlsx"

CAMPOS_META = {
    "CIDADE",
    "DIRETORIA",
    "MACRO",
    "MICRO",
    "COD_GRUPO",
    "AGRUPADOR",
    "VALOR",
    "Referencia",
}
CAMPOS_ECONOMIAS = {
    "CIDADE",
    "COD_GRUPO",
    "REFERENCIA",
    "TIPO",
    "SUMQTD_ECONOMIAS",
    "SUMVOLUME_FATURADO",
}

META_FINANCEIRA = (
    "SERVIÇO BÁSICO",
    "DIRETAS ÁGUA",
    "DISP ESGOTO",
    "DIRETAS ESGOTO",
    "INDIRETAS ÁGUA",
    "INDIRETAS ESGOTO",
)
META_OPERACIONAL = (
    "CON. FAT. ÁGUA",
    "CON. FAT. ESGOTO",
    "ECO. FAT. ÁGUA",
    "ECO. FAT. ESGOTO",
)
TODOS_AGRUPADORES = set(META_FINANCEIRA + META_OPERACIONAL)

CLASSE_PARA_AGRUPADOR = {
    "CONTAS DE ÁGUA SB": "SERVIÇO BÁSICO",
    "CONTAS DE ÁGUA": "DIRETAS ÁGUA",
    "CONTAS DE ESGOTO SB": "DISP ESGOTO",
    "CONTAS DE ESGOTO": "DIRETAS ESGOTO",
}
GRUPO_PARA_AGRUPADOR = {
    "INDIRETAS ÁGUA": "INDIRETAS ÁGUA",
    "INDIRETAS ESGOTO": "INDIRETAS ESGOTO",
}
ABATIMENTOS = {
    "ABATIMENTO DE ÁGUA": "Água",
    "ABATIMENTO DE ESGOTO": "Esgoto",
}
TIPO_PARA_INDICADORES = {
    "ECONOMIAS FATURADAS DE ÁGUA": (
        ("CON. FAT. ÁGUA", "SUMVOLUME_FATURADO", "m³"),
        ("ECO. FAT. ÁGUA", "SUMQTD_ECONOMIAS", "economias"),
    ),
    "ECONOMIAS FATURADAS DE ESGOTO": (
        ("CON. FAT. ESGOTO", "SUMVOLUME_FATURADO", "m³"),
        ("ECO. FAT. ESGOTO", "SUMQTD_ECONOMIAS", "economias"),
    ),
}

GRUPOS_FINANCEIROS = {
    "Água": ("SERVIÇO BÁSICO", "DIRETAS ÁGUA"),
    "Esgoto": ("DISP ESGOTO", "DIRETAS ESGOTO"),
    "Indiretas": ("INDIRETAS ÁGUA", "INDIRETAS ESGOTO"),
}
META_POR_GRUPO_RUBRICA = {
    "DIRETAS ÁGUA": {"SERVIÇO BÁSICO", "DIRETAS ÁGUA"},
    "DIRETAS ESGOTO": {"DISP ESGOTO", "DIRETAS ESGOTO"},
    "INDIRETAS ÁGUA": {"INDIRETAS ÁGUA"},
    "INDIRETAS ESGOTO": {"INDIRETAS ESGOTO"},
}
NOMES_INDICADORES = {
    "Água": "Faturamento Líquido de Água",
    "Esgoto": "Faturamento Líquido de Esgoto",
    "Indiretas": "Faturamento de Indiretas",
    "Total": "Faturamento Total Líquido",
    "CON. FAT. ÁGUA": "Volume faturado de água",
    "CON. FAT. ESGOTO": "Volume faturado de esgoto",
    "ECO. FAT. ÁGUA": "Economias faturadas de água",
    "ECO. FAT. ESGOTO": "Economias faturadas de esgoto",
}

CHAVES = ["CIDADE_NORM", "COD_GRUPO", "Referencia", "AGRUPADOR"]


@dataclass(frozen=True)
class FontesComparacao:
    metas: pd.DataFrame
    economias: pd.DataFrame
    referencia: pd.Timestamp
    duplicidades_meta: int
    avisos: tuple[str, ...]


def normalizar_cidade(valor) -> str:
    if pd.isna(valor):
        return ""
    texto = unicodedata.normalize("NFKD", str(valor))
    sem_acentos = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    return re.sub(r"\s+", " ", sem_acentos).strip().upper()


def _normalizar_colunas(df: pd.DataFrame, *, maiusculas: bool = False) -> pd.DataFrame:
    dados = df.copy()
    nomes = [str(coluna).strip() for coluna in dados.columns]
    if maiusculas:
        nomes = [nome.upper() for nome in nomes]
    if len(nomes) != len(set(nomes)):
        raise ValueError("A planilha contém nomes de coluna duplicados após remover espaços.")
    dados.columns = nomes
    return dados


def validar_upload_meta(conteudo: bytes) -> dict:
    arquivo = io.BytesIO(conteudo)
    try:
        livro = pd.ExcelFile(arquivo)
        if "Sheet1" not in livro.sheet_names:
            raise ValueError("A planilha de meta deve conter a aba Sheet1.")
        arquivo.seek(0)
        dados = _normalizar_colunas(pd.read_excel(arquivo, sheet_name="Sheet1"))
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Não foi possível ler a planilha de meta.") from exc
    faltantes = sorted(CAMPOS_META - set(dados.columns))
    if faltantes:
        raise ValueError("Colunas obrigatórias ausentes na meta: " + ", ".join(faltantes))
    valores = pd.to_numeric(dados["VALOR"], errors="coerce")
    if valores.isna().any() or not valores.map(math.isfinite).all():
        raise ValueError("VALOR contém campos vazios, não numéricos ou não finitos.")
    referencias = pd.to_datetime(dados["Referencia"], errors="coerce")
    if referencias.isna().any():
        raise ValueError("Referencia contém datas vazias ou inválidas.")
    if dados["CIDADE"].astype("string").str.strip().eq("").any():
        raise ValueError("CIDADE contém valores vazios.")
    if pd.to_numeric(dados["COD_GRUPO"], errors="coerce").isna().any():
        raise ValueError("COD_GRUPO contém valores vazios ou não numéricos.")
    return {"aba": "Sheet1", "linhas": int(len(dados)), "referencias": int(referencias.dt.normalize().nunique())}


def validar_upload_economias(conteudo: bytes) -> dict:
    arquivo = io.BytesIO(conteudo)
    try:
        livro = pd.ExcelFile(arquivo)
        if not livro.sheet_names:
            raise ValueError("A planilha de economias não contém abas.")
        aba = livro.sheet_names[0]
        arquivo.seek(0)
        dados = _normalizar_colunas(pd.read_excel(arquivo, sheet_name=aba), maiusculas=True)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Não foi possível ler a planilha de economias.") from exc
    faltantes = sorted(CAMPOS_ECONOMIAS - set(dados.columns))
    if faltantes:
        raise ValueError("Colunas obrigatórias ausentes nas economias: " + ", ".join(faltantes))
    if dados["CIDADE"].astype("string").str.strip().eq("").any():
        raise ValueError("CIDADE contém valores vazios.")
    if dados["TIPO"].astype("string").str.strip().eq("").any():
        raise ValueError("TIPO contém valores vazios.")
    if pd.to_datetime(dados["REFERENCIA"], errors="coerce").isna().any():
        raise ValueError("REFERENCIA contém datas vazias ou inválidas.")
    if pd.to_numeric(dados["COD_GRUPO"], errors="coerce").isna().any():
        raise ValueError("COD_GRUPO contém valores vazios ou não numéricos.")
    faltantes_valores = {}
    for coluna in ("SUMQTD_ECONOMIAS", "SUMVOLUME_FATURADO"):
        convertido = pd.to_numeric(dados[coluna], errors="coerce")
        malformados = dados[coluna].notna() & convertido.isna()
        if malformados.any():
            raise ValueError(f"{coluna} contém valores não numéricos.")
        faltantes_valores[coluna] = int(convertido.isna().sum())
    return {"aba": aba, "linhas": int(len(dados)), "valores_ausentes": faltantes_valores}


def _parse_total(serie: pd.Series) -> pd.Series:
    if serie.dtype == bool:
        return serie.fillna(False)
    texto = serie.astype("string").str.strip().str.lower()
    return texto.isin(["true", "1", "verdadeiro", "sim"])


def carregar_fontes_comparacao(
    caminho_meta: str | Path = CAMINHO_META,
    caminho_economias: str | Path = CAMINHO_ECONOMIAS,
) -> FontesComparacao:
    """Lê a referência mais recente compartilhada e exclui chaves de meta duplicadas."""
    try:
        metas = _normalizar_colunas(pd.read_excel(caminho_meta, sheet_name="Sheet1"))
        economias = _normalizar_colunas(pd.read_excel(caminho_economias), maiusculas=True)
    except Exception as exc:
        raise ValueError(f"Não foi possível ler os arquivos de meta/economias: {exc}") from exc

    faltantes_meta = sorted(CAMPOS_META - set(metas.columns))
    faltantes_economias = sorted(CAMPOS_ECONOMIAS - set(economias.columns))
    if faltantes_meta or faltantes_economias:
        faltantes = []
        if faltantes_meta:
            faltantes.append("meta: " + ", ".join(faltantes_meta))
        if faltantes_economias:
            faltantes.append("economias: " + ", ".join(faltantes_economias))
        raise ValueError("Colunas obrigatórias ausentes: " + "; ".join(faltantes))

    metas["Referencia"] = pd.to_datetime(metas["Referencia"], errors="coerce").dt.normalize()
    economias["REFERENCIA"] = pd.to_datetime(economias["REFERENCIA"], errors="coerce").dt.normalize()
    referencias = sorted(set(metas["Referencia"].dropna()) & set(economias["REFERENCIA"].dropna()))
    if not referencias:
        raise ValueError("Meta e economias não possuem uma Referencia em comum.")
    referencia = pd.Timestamp(referencias[-1])
    metas = metas.loc[metas["Referencia"].eq(referencia)].copy()
    economias = economias.loc[economias["REFERENCIA"].eq(referencia)].copy()

    metas["CIDADE"] = metas["CIDADE"].astype("string").str.strip()
    metas["CIDADE_NORM"] = metas["CIDADE"].map(normalizar_cidade)
    metas["COD_GRUPO"] = pd.to_numeric(metas["COD_GRUPO"], errors="coerce").astype("Int64")
    metas["AGRUPADOR"] = metas["AGRUPADOR"].astype("string").str.strip()
    metas["VALOR"] = pd.to_numeric(metas["VALOR"], errors="coerce")
    if metas["VALOR"].isna().any():
        raise ValueError("A coluna VALOR da meta contém valores vazios ou não numéricos.")

    chaves_meta = ["CIDADE_NORM", "COD_GRUPO", "AGRUPADOR", "Referencia"]
    repetidas = metas.duplicated(chaves_meta, keep=False)
    duplicidades = int(metas.loc[repetidas, chaves_meta].drop_duplicates().shape[0])
    avisos = []
    if duplicidades:
        avisos.append(
            f"{duplicidades} chaves duplicadas na meta foram excluídas da comparação; os valores não foram somados."
        )
        metas = metas.loc[~repetidas].copy()

    agrupadores_desconhecidos = sorted(set(metas["AGRUPADOR"].dropna()) - TODOS_AGRUPADORES)
    if agrupadores_desconhecidos:
        avisos.append(
            "Agrupadores não mapeados foram ignorados: " + ", ".join(agrupadores_desconhecidos)
        )
        metas = metas.loc[metas["AGRUPADOR"].isin(TODOS_AGRUPADORES)].copy()

    economias["CIDADE"] = economias["CIDADE"].astype("string").str.strip()
    economias["CIDADE_NORM"] = economias["CIDADE"].map(normalizar_cidade)
    economias["COD_GRUPO"] = pd.to_numeric(economias["COD_GRUPO"], errors="coerce").astype("Int64")
    economias["TIPO"] = economias["TIPO"].astype("string").str.strip().str.upper()
    for coluna in ("SUMQTD_ECONOMIAS", "SUMVOLUME_FATURADO"):
        economias[coluna] = pd.to_numeric(economias[coluna], errors="coerce")
        faltantes = int(economias[coluna].isna().sum())
        if faltantes:
            avisos.append(
                f"{faltantes} valores ausentes em {coluna}; a soma considera os valores numéricos disponíveis."
            )
    if "ISGRANDTOTALROWTOTAL" in economias.columns:
        economias = economias.loc[~_parse_total(economias["ISGRANDTOTALROWTOTAL"])].copy()
    tipos_desconhecidos = sorted(set(economias["TIPO"].dropna()) - set(TIPO_PARA_INDICADORES))
    if tipos_desconhecidos:
        avisos.append("Tipos de economias não mapeados foram ignorados: " + ", ".join(tipos_desconhecidos))
        economias = economias.loc[economias["TIPO"].isin(TIPO_PARA_INDICADORES)].copy()

    return FontesComparacao(
        metas=metas,
        economias=economias,
        referencia=referencia,
        duplicidades_meta=duplicidades,
        avisos=tuple(avisos),
    )


def _agregar_lancamentos(
    df: pd.DataFrame,
    mascara: pd.Series,
    agrupador: str,
    referencia: pd.Timestamp,
) -> pd.DataFrame:
    if df.empty or not bool(mascara.any()):
        return pd.DataFrame(columns=[*CHAVES, "CIDADE", "Realizado", "Unidade", "DadosIncompletos", "LinhasSemValor"])
    linhas = df.loc[mascara, ["CIDADE", "COD_GRUPO", "SumVALOR"]].copy()
    linhas["CIDADE_NORM"] = linhas["CIDADE"].map(normalizar_cidade)
    linhas["COD_GRUPO"] = pd.to_numeric(linhas["COD_GRUPO"], errors="coerce").astype("Int64")
    linhas["Referencia"] = referencia
    linhas["AGRUPADOR"] = agrupador
    linhas["Unidade"] = "R$"
    linhas["DadosIncompletos"] = False
    linhas["LinhasSemValor"] = 0
    return (
        linhas.groupby(CHAVES, dropna=False, as_index=False)
        .agg(
            CIDADE=("CIDADE", "first"),
            Realizado=("SumVALOR", "sum"),
            Unidade=("Unidade", "first"),
            DadosIncompletos=("DadosIncompletos", "any"),
            LinhasSemValor=("LinhasSemValor", "sum"),
        )
    )


def _realizados_financeiros(df: pd.DataFrame, referencia: pd.Timestamp) -> pd.DataFrame:
    colunas = [*CHAVES, "CIDADE", "Realizado", "Unidade", "DadosIncompletos", "LinhasSemValor"]
    if df.empty:
        return pd.DataFrame(columns=colunas)
    partes = []
    for classe, agrupador in CLASSE_PARA_AGRUPADOR.items():
        partes.append(_agregar_lancamentos(df, df["CLASSE_RUBRICA"].eq(classe), agrupador, referencia))
    for grupo, agrupador in GRUPO_PARA_AGRUPADOR.items():
        partes.append(_agregar_lancamentos(df, df["GRUPO_RUBRICA"].eq(grupo), agrupador, referencia))
    for classe in ABATIMENTOS:
        partes.append(_agregar_lancamentos(df, df["CLASSE_RUBRICA"].eq(classe), classe, referencia))
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=colunas)


def _realizados_operacionais(economias: pd.DataFrame) -> pd.DataFrame:
    colunas = [*CHAVES, "CIDADE", "Realizado", "Unidade", "DadosIncompletos", "LinhasSemValor"]
    partes = []
    for tipo, indicadores in TIPO_PARA_INDICADORES.items():
        linhas_tipo = economias.loc[economias["TIPO"].eq(tipo)]
        for agrupador, campo, unidade in indicadores:
            if linhas_tipo.empty:
                continue
            linhas = linhas_tipo[["CIDADE", "CIDADE_NORM", "COD_GRUPO", "REFERENCIA", campo]].copy()
            linhas = linhas.rename(columns={"REFERENCIA": "Referencia", campo: "Realizado"})
            linhas["AGRUPADOR"] = agrupador
            linhas["Unidade"] = unidade
            linhas["DadosIncompletos"] = linhas["Realizado"].isna()
            linhas["LinhasSemValor"] = linhas["DadosIncompletos"].astype(int)
            partes.append(
                linhas.groupby(CHAVES, dropna=False, as_index=False)
                .agg(
                    CIDADE=("CIDADE", "first"),
                    Realizado=("Realizado", lambda valores: valores.sum(min_count=1)),
                    Unidade=("Unidade", "first"),
                    DadosIncompletos=("DadosIncompletos", "any"),
                    LinhasSemValor=("LinhasSemValor", "sum"),
                )
            )
    return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=colunas)


def _normalizar_filtro_valores(valores, *, cidades: bool = False):
    if not valores:
        return None
    return {normalizar_cidade(valor) for valor in valores} if cidades else set(valores)


def _filtrar_chaves(df: pd.DataFrame, cidades=None, codigos=None) -> pd.DataFrame:
    recorte = df
    cidades_norm = _normalizar_filtro_valores(cidades, cidades=True)
    if cidades_norm is not None:
        recorte = recorte.loc[recorte["CIDADE_NORM"].isin(cidades_norm)]
    codigos_set = _normalizar_filtro_valores(codigos)
    if codigos_set is not None:
        recorte = recorte.loc[recorte["COD_GRUPO"].isin(codigos_set)]
    return recorte


def _agrupadores_meta_filtrados(
    classes=None,
    grupos=None,
    descricoes=None,
    todas_classes=None,
    todos_grupos=None,
) -> set[str]:
    permitidos = set(META_FINANCEIRA)
    classes_set = set(classes or ())
    grupos_set = set(grupos or ())
    if classes_set and todas_classes and classes_set == set(todas_classes):
        classes_set.clear()
    if grupos_set and todos_grupos and grupos_set == set(todos_grupos):
        grupos_set.clear()
    if descricoes:
        return set()
    if classes_set:
        permitidos &= {alvo for classe, alvo in CLASSE_PARA_AGRUPADOR.items() if classe in classes_set}
    if grupos_set:
        permitidos &= set().union(
            *(META_POR_GRUPO_RUBRICA.get(grupo, set()) for grupo in grupos_set)
        ) if grupos_set else permitidos
    return permitidos


def _juntar(meta: pd.DataFrame, realizado: pd.DataFrame) -> pd.DataFrame:
    alvos = meta[[*CHAVES, "CIDADE", "VALOR"]].rename(columns={"CIDADE": "CIDADE_META", "VALOR": "Meta"})
    valores = realizado[[*CHAVES, "CIDADE", "Realizado", "Unidade", "DadosIncompletos", "LinhasSemValor"]].rename(
        columns={"CIDADE": "CIDADE_REALIZADO"}
    )
    for quadro in (alvos, valores):
        quadro["CIDADE_NORM"] = quadro["CIDADE_NORM"].astype("string")
        quadro["COD_GRUPO"] = pd.to_numeric(quadro["COD_GRUPO"], errors="coerce").astype("Int64")
        quadro["Referencia"] = pd.to_datetime(quadro["Referencia"], errors="coerce").dt.normalize()
        quadro["AGRUPADOR"] = quadro["AGRUPADOR"].astype("string")
    combinado = alvos.merge(valores, on=CHAVES, how="outer", validate="one_to_one", indicator=True)
    combinado["CIDADE"] = combinado["CIDADE_REALIZADO"].combine_first(combinado["CIDADE_META"])
    return combinado


def _somar_mapa(combinado: pd.DataFrame, campo: str, agrupadores: set[str]) -> float | None:
    linhas = combinado.loc[combinado["AGRUPADOR"].isin(agrupadores)]
    if campo == "Realizado":
        linhas = linhas.loc[linhas["_merge"].isin(["both", "right_only"])]
    valores = linhas[campo].dropna()
    if campo == "Realizado" and linhas.empty:
        return 0.0
    if campo == "Realizado" and valores.empty:
        return None
    return math.fsum(float(valor) for valor in valores)


def _valor_meta(combinado: pd.DataFrame, agrupadores: set[str]) -> float | None:
    valores = combinado.loc[
        combinado["AGRUPADOR"].isin(agrupadores) & combinado["Meta"].notna(), "Meta"
    ]
    return None if valores.empty else math.fsum(float(valor) for valor in valores)


def _status(realizado: float | None, meta: float | None, completo: bool) -> tuple[str, float | None, float | None]:
    if meta is None or pd.isna(meta) or meta == 0:
        return "Sem meta", None, None
    if realizado is None or pd.isna(realizado):
        return "N/A", None, None
    diferenca = realizado - meta
    if not completo:
        return "N/A", diferenca, None
    atingimento = realizado / meta
    if atingimento >= 1:
        status = "Atingido"
    elif atingimento >= 0.9:
        status = "Em atenção"
    else:
        status = "Abaixo"
    return status, diferenca, atingimento


def _chaves_esperadas(
    fontes: FontesComparacao,
    metas_escopo: pd.DataFrame,
    realizados_escopo: pd.DataFrame,
    dimensao: str | None,
) -> pd.DataFrame:
    colunas = ["CIDADE_NORM", "COD_GRUPO", "CIDADE"]
    todas = pd.concat(
        [metas_escopo[colunas], realizados_escopo[colunas]], ignore_index=True
    ).drop_duplicates(["CIDADE_NORM", "COD_GRUPO"])
    if dimensao == "CIDADE":
        exibicao = (
            realizados_escopo.groupby("CIDADE_NORM", dropna=False)["CIDADE"].first()
            .combine_first(metas_escopo.groupby("CIDADE_NORM", dropna=False)["CIDADE"].first())
        )
        todas["DIMENSAO"] = todas["CIDADE_NORM"].map(exibicao)
    elif dimensao == "COD_GRUPO":
        todas["DIMENSAO"] = todas["COD_GRUPO"]
    else:
        todas["DIMENSAO"] = "Total do recorte"
    return todas


def _agregados_financeiros(
    combinado: pd.DataFrame,
    chaves_escopo: pd.DataFrame,
    metas_escopo: pd.DataFrame,
    agrupadores_ativos: set[str],
    dimensao: str | None,
) -> pd.DataFrame:
    linhas = []
    metas_com_dimensao = metas_escopo.merge(
        chaves_escopo[["CIDADE_NORM", "COD_GRUPO", "DIMENSAO"]],
        on=["CIDADE_NORM", "COD_GRUPO"],
        how="left",
        validate="many_to_one",
    )
    for dimensao_valor, dados in combinado.groupby("DIMENSAO", dropna=False, sort=False):
        linhas_chaves = chaves_escopo.loc[chaves_escopo["DIMENSAO"].eq(dimensao_valor)]
        ids = set(zip(linhas_chaves["CIDADE_NORM"], linhas_chaves["COD_GRUPO"]))
        metas_dados = metas_com_dimensao.loc[metas_com_dimensao["DIMENSAO"].eq(dimensao_valor)]

        def realizado(agrupadores: set[str]) -> float:
            valor = _somar_mapa(dados, "Realizado", agrupadores)
            return 0.0 if valor is None else float(valor)

        def meta(agrupadores: set[str]) -> float | None:
            return _valor_meta(dados, agrupadores)

        def completo(agrupadores: set[str]) -> bool:
            if not agrupadores:
                return False
            chaves_base = set(zip(metas_dados["CIDADE_NORM"], metas_dados["COD_GRUPO"]))
            for agrupador in agrupadores:
                presentes = set(
                    zip(
                        metas_dados.loc[metas_dados["AGRUPADOR"].eq(agrupador), "CIDADE_NORM"],
                        metas_dados.loc[metas_dados["AGRUPADOR"].eq(agrupador), "COD_GRUPO"],
                    )
                )
                linhas_realizadas = dados.loc[
                    dados["AGRUPADOR"].eq(agrupador) & dados["_merge"].isin(["both", "right_only"])
                ]
                chaves_realizadas = set(zip(linhas_realizadas["CIDADE_NORM"], linhas_realizadas["COD_GRUPO"]))
                esperadas = chaves_base | chaves_realizadas
                if esperadas - presentes:
                    return False
            return True

        def reconcilia(agrupadores: set[str], abatimentos: float = 0.0) -> str:
            avisos = []
            if abatimentos:
                avisos.append("Abatimentos compõem o líquido e não possuem agrupador de meta.")
            sem_meta = dados.loc[
                dados["AGRUPADOR"].isin(agrupadores) & dados["Realizado"].notna() & dados["Meta"].isna()
            ]
            if not sem_meta.empty:
                valor = _somar_mapa(sem_meta, "Realizado", set(sem_meta["AGRUPADOR"]))
                avisos.append(f"{brl(float(valor))} de realizado sem meta na chave cidade/COD_GRUPO.")
            return " ".join(avisos)

        agua_aggs = agrupadores_ativos & set(GRUPOS_FINANCEIROS["Água"])
        esgoto_aggs = agrupadores_ativos & set(GRUPOS_FINANCEIROS["Esgoto"])
        indiretas_aggs = agrupadores_ativos & set(GRUPOS_FINANCEIROS["Indiretas"])
        todos_aggs = agua_aggs | esgoto_aggs | indiretas_aggs

        agua_bruta = realizado({"SERVIÇO BÁSICO", "DIRETAS ÁGUA"})
        agua_abatimentos = realizado({"ABATIMENTO DE ÁGUA"})
        agua_liquida = agua_bruta + agua_abatimentos
        esgoto_bruto = realizado({"DISP ESGOTO", "DIRETAS ESGOTO"})
        esgoto_abatimentos = realizado({"ABATIMENTO DE ESGOTO"})
        esgoto_liquido = esgoto_bruto + esgoto_abatimentos
        indiretas = realizado({"INDIRETAS ÁGUA", "INDIRETAS ESGOTO"})
        linhas_financeiras = [
            ("Faturamento Líquido de Água", agua_bruta, agua_abatimentos, agua_liquida, agua_aggs),
            ("Faturamento Líquido de Esgoto", esgoto_bruto, esgoto_abatimentos, esgoto_liquido, esgoto_aggs),
            ("Faturamento de Indiretas", indiretas, 0.0, indiretas, indiretas_aggs),
            (
                "Faturamento Total Líquido",
                agua_bruta + esgoto_bruto + indiretas,
                agua_abatimentos + esgoto_abatimentos,
                agua_liquida + esgoto_liquido + indiretas,
                todos_aggs,
            ),
        ]
        for nome, bruto, abatimentos, liquido, metas_grupo in linhas_financeiras:
            alvo = meta(metas_grupo)
            status, diferenca, atingimento = _status(liquido, alvo, completo(metas_grupo))
            linhas.append(
                {
                    "Dimensão": dimensao_valor,
                    "Indicador": nome,
                    "Realizado bruto": bruto,
                    "Abatimentos realizados": abatimentos,
                    "Realizado líquido": liquido,
                    "Meta": alvo,
                    "Diferença": diferenca,
                    "Atingimento": atingimento,
                    "Status": status,
                    "Reconciliação": reconcilia(metas_grupo, abatimentos),
                }
            )
    resultado = pd.DataFrame(linhas)
    if dimensao is None and not resultado.empty:
        resultado = resultado.drop(columns=["Dimensão"])
    return resultado


def _agregados_operacionais(
    combinado: pd.DataFrame,
    chaves_escopo: pd.DataFrame,
    metas_escopo: pd.DataFrame,
    dimensao: str | None,
) -> pd.DataFrame:
    linhas = []
    metas_com_dimensao = metas_escopo.merge(
        chaves_escopo[["CIDADE_NORM", "COD_GRUPO", "DIMENSAO"]],
        on=["CIDADE_NORM", "COD_GRUPO"],
        how="left",
        validate="many_to_one",
    )
    for dimensao_valor, dados in combinado.groupby("DIMENSAO", dropna=False, sort=False):
        linhas_chaves = chaves_escopo.loc[chaves_escopo["DIMENSAO"].eq(dimensao_valor)]
        ids = set(zip(linhas_chaves["CIDADE_NORM"], linhas_chaves["COD_GRUPO"]))
        metas_dados = metas_com_dimensao.loc[metas_com_dimensao["DIMENSAO"].eq(dimensao_valor)]
        for agrupador in META_OPERACIONAL:
            meta = _valor_meta(dados, {agrupador})
            dados_indicador = dados.loc[dados["AGRUPADOR"].eq(agrupador)]
            faltantes = int(pd.to_numeric(dados_indicador["LinhasSemValor"], errors="coerce").sum())
            linhas_realizadas = dados_indicador.loc[
                dados_indicador["_merge"].isin(["both", "right_only"])
            ]
            valores_disponiveis = linhas_realizadas["Realizado"].dropna()
            if valores_disponiveis.empty and linhas_realizadas.empty:
                realizado = 0.0 if meta is not None else None
            elif valores_disponiveis.empty:
                realizado = None
            else:
                realizado = _somar_mapa(dados, "Realizado", {agrupador})
            chaves_meta = set(
                zip(
                    metas_dados.loc[metas_dados["AGRUPADOR"].eq(agrupador), "CIDADE_NORM"],
                    metas_dados.loc[metas_dados["AGRUPADOR"].eq(agrupador), "COD_GRUPO"],
                )
            )
            chaves_base = set(zip(metas_dados["CIDADE_NORM"], metas_dados["COD_GRUPO"]))
            linhas_realizadas = dados.loc[
                dados["AGRUPADOR"].eq(agrupador) & dados["_merge"].isin(["both", "right_only"])
            ]
            chaves_realizadas = set(zip(linhas_realizadas["CIDADE_NORM"], linhas_realizadas["COD_GRUPO"]))
            completo = bool(chaves_base) and (chaves_base | chaves_realizadas).issubset(chaves_meta)
            status, diferenca, atingimento = _status(realizado, meta, completo)
            unidade = "m³" if agrupador.startswith("CON.") else "economias"
            linhas.append(
                {
                    "Dimensão": dimensao_valor,
                    "Indicador": NOMES_INDICADORES[agrupador],
                    "Unidade": unidade,
                    "Realizado": realizado,
                    "Meta": meta,
                    "Diferença": diferenca,
                    "Atingimento": atingimento,
                    "Status": status,
                    "Detalhe": (
                        f"{faltantes} registros sem valor; realizado soma os valores numéricos disponíveis."
                        if faltantes
                        else ""
                    ),
                }
            )
    resultado = pd.DataFrame(linhas)
    if dimensao is None and not resultado.empty:
        resultado = resultado.drop(columns=["Dimensão"])
    return resultado


def construir_comparacoes(
    faturamento: pd.DataFrame,
    fontes: FontesComparacao,
    *,
    cidades=None,
    codigos=None,
    classes=None,
    grupos=None,
    descricoes=None,
    todas_classes=None,
    todos_grupos=None,
    dimensao: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Compara indicadores após agregar cada fonte na chave antes da junção."""
    agrupadores_financeiros = _agrupadores_meta_filtrados(
        classes, grupos, descricoes, todas_classes, todos_grupos
    )
    meta_escopo_completo = _filtrar_chaves(fontes.metas, cidades, codigos)
    realizado_financeiro = _filtrar_chaves(
        _realizados_financeiros(faturamento, fontes.referencia), cidades, codigos
    )
    realizado_operacional = _filtrar_chaves(_realizados_operacionais(fontes.economias), cidades, codigos)
    partes_realizadas = [parte for parte in (realizado_financeiro, realizado_operacional) if not parte.empty]
    realizado = (
        pd.concat(partes_realizadas, ignore_index=True)
        if partes_realizadas
        else pd.DataFrame(columns=[*CHAVES, "CIDADE", "Realizado", "Unidade", "DadosIncompletos", "LinhasSemValor"])
    )

    metas_escopo = meta_escopo_completo.loc[
        meta_escopo_completo["AGRUPADOR"].isin(agrupadores_financeiros | set(META_OPERACIONAL))
    ].copy()
    combinado = _juntar(metas_escopo, realizado)
    chaves_escopo = _chaves_esperadas(fontes, meta_escopo_completo, realizado, dimensao)
    if not combinado.empty:
        combinado = combinado.merge(
            chaves_escopo[["CIDADE_NORM", "COD_GRUPO", "DIMENSAO"]],
            on=["CIDADE_NORM", "COD_GRUPO"],
            how="left",
            validate="many_to_one",
        )
    else:
        combinado["DIMENSAO"] = pd.Series(dtype="object")
    financeiro = _agregados_financeiros(
        combinado, chaves_escopo, metas_escopo, agrupadores_financeiros, dimensao
    )
    operacional = _agregados_operacionais(combinado, chaves_escopo, metas_escopo, dimensao)
    return financeiro, operacional, combinado


def validar_comparacao(faturamento: pd.DataFrame, fontes: FontesComparacao) -> list[dict]:
    """Confere as fórmulas solicitadas e a unicidade da junção na referência carregada."""
    tolerancia = 0.05

    def perto(a: float, b: float) -> bool:
        return abs(float(a) - float(b)) <= tolerancia

    def item(nome: str, ok: bool, detalhe: str) -> dict:
        return {"nome": nome, "ok": bool(ok), "detalhe": detalhe}

    def soma_meta(agrupador: str) -> float:
        valores = fontes.metas.loc[fontes.metas["AGRUPADOR"].eq(agrupador), "VALOR"]
        return math.fsum(float(valor) for valor in valores)

    meta_agua = math.fsum([soma_meta("SERVIÇO BÁSICO"), soma_meta("DIRETAS ÁGUA")])
    meta_esgoto = math.fsum([soma_meta("DISP ESGOTO"), soma_meta("DIRETAS ESGOTO")])
    meta_indiretas = math.fsum([soma_meta("INDIRETAS ÁGUA"), soma_meta("INDIRETAS ESGOTO")])
    meta_total = math.fsum([meta_agua, meta_esgoto, meta_indiretas])

    classes = faturamento["CLASSE_RUBRICA"]
    grupos = faturamento["GRUPO_RUBRICA"]
    valores = faturamento["SumVALOR"]
    agua_bruta = math.fsum(float(v) for v in valores.loc[classes.isin(["CONTAS DE ÁGUA", "CONTAS DE ÁGUA SB"])])
    agua_abatimento = math.fsum(float(v) for v in valores.loc[classes.eq("ABATIMENTO DE ÁGUA")])
    esgoto_bruto = math.fsum(float(v) for v in valores.loc[classes.isin(["CONTAS DE ESGOTO", "CONTAS DE ESGOTO SB"])])
    esgoto_abatimento = math.fsum(float(v) for v in valores.loc[classes.eq("ABATIMENTO DE ESGOTO")])
    indiretas = math.fsum(float(v) for v in valores.loc[grupos.isin(["INDIRETAS ÁGUA", "INDIRETAS ESGOTO"])])
    agua_liquida = agua_bruta + agua_abatimento
    esgoto_liquido = esgoto_bruto + esgoto_abatimento
    total_liquido = math.fsum([agua_liquida, esgoto_liquido, indiretas])

    financeiro, operacional, combinado = construir_comparacoes(faturamento, fontes)
    linhas_financeiras = financeiro.set_index("Indicador")
    agua_painel = linhas_financeiras.loc["Faturamento Líquido de Água"]
    esgoto_painel = linhas_financeiras.loc["Faturamento Líquido de Esgoto"]
    indiretas_painel = linhas_financeiras.loc["Faturamento de Indiretas"]
    total_painel = linhas_financeiras.loc["Faturamento Total Líquido"]
    checks = [
        item(
            "Meta líquida de água usa SERVIÇO BÁSICO + DIRETAS ÁGUA",
            perto(float(agua_painel["Meta"]), meta_agua),
            f"Calculado {meta_agua:,.2f} · relatório {float(agua_painel['Meta']):,.2f}.",
        ),
        item(
            "Meta líquida de esgoto usa DISP ESGOTO + DIRETAS ESGOTO",
            perto(float(esgoto_painel["Meta"]), meta_esgoto),
            f"Calculado {meta_esgoto:,.2f} · relatório {float(esgoto_painel['Meta']):,.2f}.",
        ),
        item(
            "Meta de indiretas usa INDIRETAS ÁGUA + INDIRETAS ESGOTO",
            perto(float(indiretas_painel["Meta"]), meta_indiretas),
            f"Calculado {meta_indiretas:,.2f} · relatório {float(indiretas_painel['Meta']):,.2f}.",
        ),
        item(
            "Meta total soma as três metas financeiras",
            perto(float(total_painel["Meta"]), meta_total),
            f"Calculado {meta_total:,.2f} · relatório {float(total_painel['Meta']):,.2f}.",
        ),
        item(
            "Realizado líquido de água preserva somente o abatimento de água",
            perto(float(agua_painel["Realizado bruto"]), agua_bruta)
            and perto(float(agua_painel["Abatimentos realizados"]), agua_abatimento)
            and perto(float(agua_painel["Realizado líquido"]), agua_liquida),
            f"Bruto {agua_bruta:,.2f} + abatimento {agua_abatimento:,.2f} = líquido {agua_liquida:,.2f}.",
        ),
        item(
            "Realizado líquido de esgoto preserva somente o abatimento de esgoto",
            perto(float(esgoto_painel["Realizado bruto"]), esgoto_bruto)
            and perto(float(esgoto_painel["Abatimentos realizados"]), esgoto_abatimento)
            and perto(float(esgoto_painel["Realizado líquido"]), esgoto_liquido),
            f"Bruto {esgoto_bruto:,.2f} + abatimento {esgoto_abatimento:,.2f} = líquido {esgoto_liquido:,.2f}.",
        ),
        item(
            "Abatimentos de água e esgoto permanecem negativos e separados",
            agua_abatimento <= 0
            and esgoto_abatimento <= 0
            and perto(float(agua_painel["Abatimentos realizados"]), agua_abatimento)
            and perto(float(esgoto_painel["Abatimentos realizados"]), esgoto_abatimento),
            f"Água {agua_abatimento:,.2f} · esgoto {esgoto_abatimento:,.2f}.",
        ),
        item(
            "Total realizado soma água líquida, esgoto líquido e indiretas",
            perto(float(total_painel["Realizado líquido"]), total_liquido)
            and perto(total_liquido, math.fsum([agua_liquida, esgoto_liquido, indiretas])),
            f"Total líquido {total_liquido:,.2f}.",
        ),
    ]

    reais = pd.concat(
        [
            _realizados_financeiros(faturamento, fontes.referencia),
            _realizados_operacionais(fontes.economias),
        ],
        ignore_index=True,
    )
    chaves_meta = fontes.metas[[*CHAVES, "CIDADE", "VALOR"]]
    combinado = _juntar(chaves_meta, reais)
    sem_repeticao = not combinado.duplicated(CHAVES, keep=False).any()
    checks.extend(
        [
            item(
                "Meta sem duplicidade na chave normalizada",
                fontes.duplicidades_meta == 0,
                f"Chaves duplicadas excluídas: {fontes.duplicidades_meta}.",
            ),
            item(
                "Junção meta/realizado não duplica chaves",
                sem_repeticao,
                f"Linhas após junção: {len(combinado):,} · repetidas: {int(combinado.duplicated(CHAVES, keep=False).sum())}.",
            ),
            item(
                "Referência de meta e economias é única e comum",
                fontes.metas["Referencia"].eq(fontes.referencia).all()
                and fontes.economias["REFERENCIA"].eq(fontes.referencia).all(),
                f"Referência selecionada: {fontes.referencia:%d/%m/%Y}.",
            ),
        ]
    )
    status_limites = (
        _status(100.0, 100.0, True)[0] == "Atingido"
        and _status(90.0, 100.0, True)[0] == "Em atenção"
        and _status(89.0, 100.0, True)[0] == "Abaixo"
        and _status(10.0, 0.0, True)[0] == "Sem meta"
        and _status(None, 100.0, True)[0] == "N/A"
        and _status(10.0, 100.0, False) == ("N/A", -90.0, None)
    )
    checks.append(
        item(
            "Status respeita os limites e evita divisão por zero",
            status_limites,
            "Atingido ≥ 100%, Em atenção ≥ 90%, Abaixo < 90%; meta zero e realizado N/A não geram percentual.",
        )
    )
    volume_esgoto = operacional.loc[operacional["Indicador"].eq("Volume faturado de esgoto")].iloc[0]
    volumes_esgoto = fontes.economias.loc[
        fontes.economias["TIPO"].eq("ECONOMIAS FATURADAS DE ESGOTO"), "SUMVOLUME_FATURADO"
    ]
    volumes_ausentes = int(volumes_esgoto.isna().sum())
    volume_esgoto_disponivel = math.fsum(float(valor) for valor in volumes_esgoto.dropna())
    checks.append(
        item(
            "Volume faturado de esgoto soma valores disponíveis sem substituir vazios",
            pd.notna(volume_esgoto["Realizado"])
            and perto(float(volume_esgoto["Realizado"]), volume_esgoto_disponivel)
            and (volume_esgoto["Detalhe"].startswith(f"{volumes_ausentes} registros") if volumes_ausentes else True)
            and volume_esgoto["Status"] != "N/A",
            (
                f"Realizado {float(volume_esgoto['Realizado']):,.2f} m³; {volumes_ausentes} valores vazios informados. "
                "A coluna CORSAN não foi usada."
            ),
        )
    )
    return checks