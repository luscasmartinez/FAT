"""Conferências matemáticas da regra de faturamento."""

from __future__ import annotations

import math

import pandas as pd

from faturamento.calculo import (
    agregar_entidade,
    agregar_rubricas,
    aplicar_filtros,
    preparar_faturamento,
    resumo_classificacao,
    somar_faturamento,
    somar_series,
    totais_liquidos,
)
from faturamento.constantes import (
    CLASSES_ELEGIVEIS,
    COL_TOTAL,
    GRUPOS_INDIRETAS,
    GRUPOS_LIQUIDOS,
    ORDEM_CLASSIFICACAO,
)
from faturamento.formato import brl, inteiro

TOLERANCIA = 0.05

REFERENCIA_26_11 = {
    "linhas_arquivo": 285151,
    "total": 18926653.87,
    "CONTAS DE ÁGUA": 11183036.34,
    "CONTAS DE ÁGUA SB": 6264609.70,
    "ABATIMENTO DE ÁGUA": -1030526.89,
    "CONTAS DE ESGOTO": 1919336.62,
    "CONTAS DE ESGOTO SB": 176843.60,
    "ABATIMENTO DE ESGOTO": -68408.65,
    "INDIRETAS ÁGUA": 316898.20,
    "INDIRETAS ESGOTO": 164864.95,
    "negativos_n": 42531,
    "negativos_valor": -2270476.83,
    "cidades": 61,
    "grupos": 18,
}


def _perto(a: float, b: float, tolerancia: float = TOLERANCIA) -> bool:
    return abs(float(a) - float(b)) <= tolerancia


def _item(nome: str, ok: bool, detalhe: str) -> dict:
    return {"nome": nome, "ok": bool(ok), "detalhe": detalhe}


def fechar_particoes(df: pd.DataFrame) -> list[dict]:
    """Confere se cidade, grupo, rubrica e classificação repartem o mesmo total."""
    total = somar_faturamento(df)
    resumo = resumo_classificacao(df, total)
    soma_classes = somar_series(resumo["Faturamento"])
    cidades = agregar_entidade(df, "CIDADE", total)
    grupos = agregar_entidade(df, "COD_GRUPO", total)
    rubricas = agregar_rubricas(df, total)
    soma_cidades = somar_series(cidades[COL_TOTAL]) if not cidades.empty else 0.0
    soma_grupos = somar_series(grupos[COL_TOTAL]) if not grupos.empty else 0.0
    soma_rubricas = somar_series(rubricas["Faturamento"]) if not rubricas.empty else 0.0
    totais = totais_liquidos(df)
    checks = [
        _item(
            "Total igual à soma das oito classificações",
            _perto(total, soma_classes),
            f"Total {brl(total)} · classificações {brl(soma_classes)}",
        ),
        _item(
            "Soma das cidades igual ao total",
            _perto(total, soma_cidades),
            f"Cidades {brl(soma_cidades)} · total {brl(total)}",
        ),
        _item(
            "Soma dos COD_GRUPO igual ao total",
            _perto(total, soma_grupos),
            f"COD_GRUPO {brl(soma_grupos)} · total {brl(total)}",
        ),
        _item(
            "Soma das rubricas igual ao total",
            _perto(total, soma_rubricas),
            f"Rubricas {brl(soma_rubricas)} · total {brl(total)}",
        ),
    ]
    for nome, componentes in GRUPOS_LIQUIDOS.items():
        valor_componentes = somar_series(
            df.loc[df["CLASSIFICACAO"].isin(componentes), "SumVALOR"] if not df.empty else []
        )
        checks.append(
            _item(
                f"{nome} igual à soma dos componentes",
                _perto(totais[nome], valor_componentes),
                f"Agregado {brl(totais[nome])} · componentes {brl(valor_componentes)}",
            )
        )
    checks.append(
        _item(
            "Total líquido igual à soma dos três grupos",
            _perto(total, totais["Faturamento Total Líquido"]),
            f"Total {brl(total)} · grupos {brl(totais['Faturamento Total Líquido'])}",
        )
    )
    return checks


def validar_base(bruto: pd.DataFrame, faturamento: pd.DataFrame, meta: dict) -> list[dict]:
    elegivel = bruto["CLASSE_RUBRICA"].isin(CLASSES_ELEGIVEIS) | bruto["GRUPO_RUBRICA"].isin(GRUPOS_INDIRETAS)
    fora = bruto.loc[~elegivel]
    no_criterio = bruto.loc[elegivel]
    recalculado = preparar_faturamento(bruto)
    total = somar_faturamento(faturamento)
    total_regra = somar_series(no_criterio["SumVALOR"])
    linhas_ok = len(recalculado) == len(faturamento) == int(elegivel.sum())
    classificacao_ok = set(faturamento["CLASSIFICACAO"].dropna().unique()).issubset(set(ORDEM_CLASSIFICACAO))
    uma_classe = int(faturamento.groupby(level=0).size().max() or 0) <= 1 if len(faturamento) else True

    checks = [
        _item(
            "Linhas elegíveis entram uma única vez",
            linhas_ok and classificacao_ok and uma_classe and _perto(total, total_regra),
            (
                f"{inteiro(len(faturamento))} linhas no faturamento, "
                f"{inteiro(len(fora))} fora do critério. "
                f"Total da regra {brl(total_regra)}."
            ),
        ),
        _item(
            "Registros fora do critério não entram no total",
            not fora.index.isin(faturamento.index).any(),
            f"Fora do critério: {inteiro(len(fora))} linhas, {brl(somar_series(fora['SumVALOR']) if len(fora) else 0)}.",
        ),
    ]
    checks.extend(fechar_particoes(faturamento))

    cidade = sorted(faturamento["CIDADE"].dropna().unique())[0]
    recorte_cidade = aplicar_filtros(faturamento, cidades=[cidade])
    manual_cidade = faturamento.loc[faturamento["CIDADE"].eq(cidade)]
    recorte_vazio = aplicar_filtros(faturamento, cidades=[])
    classe = "CONTAS DE ÁGUA"
    grupo = "DIRETAS ÁGUA"
    recorte_cruzado = aplicar_filtros(faturamento, classes=[classe], grupos=[grupo])
    manual_cruzado = faturamento.loc[
        faturamento["CLASSE_RUBRICA"].eq(classe) & faturamento["GRUPO_RUBRICA"].eq(grupo)
    ]
    checks.append(
        _item(
            "Filtros não alteram o valor das linhas selecionadas",
            len(recorte_vazio) == len(faturamento)
            and len(recorte_cidade) == len(manual_cidade)
            and _perto(somar_faturamento(recorte_cidade), somar_series(manual_cidade["SumVALOR"]))
            and len(recorte_cruzado) == len(manual_cruzado)
            and _perto(somar_faturamento(recorte_cruzado), somar_series(manual_cruzado["SumVALOR"])),
            f"Cidade de prova {cidade}: {brl(somar_faturamento(recorte_cidade))}.",
        )
    )

    negativos = faturamento.loc[faturamento["SumVALOR"] < 0, "SumVALOR"]
    negativos_origem = no_criterio.loc[no_criterio["SumVALOR"] < 0, "SumVALOR"]
    preservados = True
    if len(negativos_origem):
        preservados = (
            len(negativos) == len(negativos_origem)
            and _perto(somar_series(negativos), somar_series(negativos_origem))
            and float(negativos.max()) < 0
        )
    checks.append(
        _item(
            "Valores negativos preservados",
            preservados,
            (
                f"{inteiro(len(negativos))} lançamentos negativos, soma {brl(somar_series(negativos) if len(negativos) else 0)}."
            ),
        )
    )

    if meta.get("linhas_arquivo") == REFERENCIA_26_11["linhas_arquivo"] and str(meta.get("nome", "")).startswith("26-11"):
        resumo = resumo_classificacao(faturamento, total)
        por_codigo = dict(zip(resumo["codigo"], resumo["Faturamento"]))
        referencia_ok = _perto(total, REFERENCIA_26_11["total"])
        for codigo, esperado in REFERENCIA_26_11.items():
            if codigo in ORDEM_CLASSIFICACAO:
                referencia_ok = referencia_ok and _perto(por_codigo.get(codigo, 0.0), esperado)
        referencia_ok = referencia_ok and meta["linhas_negativas"] == REFERENCIA_26_11["negativos_n"]
        referencia_ok = referencia_ok and _perto(meta["valor_negativo"], REFERENCIA_26_11["negativos_valor"])
        referencia_ok = referencia_ok and faturamento["CIDADE"].nunique() == REFERENCIA_26_11["cidades"]
        referencia_ok = referencia_ok and faturamento["COD_GRUPO"].nunique() == REFERENCIA_26_11["grupos"]
        referencia_ok = referencia_ok and _perto(meta["valor_arquivo"], meta["valor_faturamento"], tolerancia=1)
        checks.append(
            _item(
                "Base 26-11 confere com a apuração de controle",
                referencia_ok,
                f"Esperado {brl(REFERENCIA_26_11['total'])} · calculado {brl(total)}.",
            )
        )

    checks.append(
        {
            "nome": "Linhas idênticas",
            "ok": True,
            "detalhe": (
                f"{inteiro(meta.get('duplicadas_identicas', 0))} linhas idênticas foram preservadas. "
                "A regra de não duplicar impede contar duas vezes a mesma linha quando ela atende "
                "mais de um critério; não remove lançamentos repetidos da origem."
            ),
        }
    )
    return checks


def tudo_ok(checks: list[dict]) -> bool:
    return all(item["ok"] for item in checks)


def fechar_recorte(df: pd.DataFrame) -> tuple[bool, str]:
    itens = fechar_particoes(df)
    ok = all(item["ok"] for item in itens)
    total = somar_faturamento(df)
    if ok:
        return True, f"Recorte conferido: classificações, cidades, COD_GRUPO e rubricas fecham em {brl(total)}."
    falhas = "; ".join(item["nome"] for item in itens if not item["ok"])
    return False, f"Divergência no recorte ({brl(total)}): {falhas}."


def main() -> int:
    from faturamento.dados import carregar_padrao
    from faturamento.comparacao import carregar_fontes_comparacao, validar_comparacao

    _bruto, faturamento, meta = carregar_padrao()
    fontes = carregar_fontes_comparacao()
    checks = validar_base(_bruto, faturamento, meta)
    checks.extend(validar_comparacao(faturamento, fontes))
    print(f"Base: {meta['nome']}")
    print(f"Referência da meta: {fontes.referencia:%d/%m/%Y}")
    print(f"Linhas no arquivo: {meta['linhas_arquivo']} | no faturamento: {meta['linhas_faturamento']}")
    print(f"Faturamento: {brl(meta['valor_faturamento'])}")
    print(f"Fora do critério: {brl(meta['valor_fora'])} ({meta['linhas_fora']} linhas)")
    print(f"Negativos: {meta['linhas_negativas']} | {brl(meta['valor_negativo'])}")
    for texto in fontes.avisos:
        print(f"Aviso: {texto}")
    print("-" * 72)
    falhas = 0
    for item in checks:
        marca = "OK" if item["ok"] else "FALHA"
        if not item["ok"]:
            falhas += 1
        print(f"[{marca}] {item['nome']}")
        print(f"       {item['detalhe']}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
