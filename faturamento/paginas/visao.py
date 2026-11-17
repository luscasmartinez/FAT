"""Aba de visão geral."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from faturamento.calculo import resumo_classificacao, resumo_liquidos, somar_faturamento, totais_liquidos
from faturamento.comparacao import FontesComparacao, construir_comparacoes, normalizar_cidade
from faturamento.componentes import aviso, cabecalho, cartao, chips, kpis, mostrar_tabela
from faturamento.constantes import COL_PART, COL_QTD
from faturamento.formato import brl, compacto, decimal, inteiro, percentual
from faturamento.graficos import (
    CONFIG,
    grafico_barras_classificacao,
    grafico_grupos_faturamento,
    grafico_rosca,
)
from faturamento.paginas.comparativo import mostrar_comparacao
from faturamento.validacao import tudo_ok


def _somar_coluna(dados: pd.DataFrame, coluna: str) -> float | None:
    if dados.empty or coluna not in dados.columns:
        return None
    valores = pd.to_numeric(dados[coluna], errors="coerce").dropna()
    return float(valores.sum()) if not valores.empty else None


def _dividir(numerador: float | None, denominador: float | None) -> float | None:
    if numerador is None or denominador is None or denominador == 0:
        return None
    return numerador / denominador


def _filtrar_fontes_operacionais(
    dados: pd.DataFrame, filtros: dict | None
) -> pd.DataFrame:
    recorte = dados
    filtros = filtros or {}
    cidades = filtros.get("cidades") or ()
    if cidades and "CIDADE_NORM" in recorte.columns:
        cidades_normalizadas = {normalizar_cidade(cidade) for cidade in cidades}
        recorte = recorte.loc[recorte["CIDADE_NORM"].isin(cidades_normalizadas)]
    codigos = filtros.get("codigos") or ()
    if codigos and "COD_GRUPO" in recorte.columns:
        recorte = recorte.loc[recorte["COD_GRUPO"].isin(codigos)]
    return recorte


def _calcular_indicadores_comerciais(
    faturamento: pd.DataFrame,
    fontes: FontesComparacao | None,
    filtros: dict | None,
) -> dict:
    dados = {
        "volume_agua": None,
        "volume_esgoto": None,
        "volume_medido_agua": None,
        "economias_agua": None,
        "economias_esgoto": None,
        "meta_volume_agua": None,
        "meta_volume_esgoto": None,
        "meta_economias_agua": None,
        "meta_economias_esgoto": None,
        "economias_sb_agua": None,
    }

    if fontes is not None:
        economias = _filtrar_fontes_operacionais(fontes.economias, filtros)
        metas = _filtrar_fontes_operacionais(fontes.metas, filtros)
        por_tipo = {
            "agua": economias.loc[economias["TIPO"].eq("ECONOMIAS FATURADAS DE ÁGUA")],
            "esgoto": economias.loc[economias["TIPO"].eq("ECONOMIAS FATURADAS DE ESGOTO")],
        }
        dados["volume_agua"] = _somar_coluna(por_tipo["agua"], "SUMVOLUME_FATURADO")
        dados["volume_esgoto"] = _somar_coluna(por_tipo["esgoto"], "SUMVOLUME_FATURADO")
        dados["volume_medido_agua"] = _somar_coluna(por_tipo["agua"], "SUMVOLUME_FATURADO_CORSAN")
        dados["economias_agua"] = _somar_coluna(por_tipo["agua"], "SUMQTD_ECONOMIAS")
        dados["economias_esgoto"] = _somar_coluna(por_tipo["esgoto"], "SUMQTD_ECONOMIAS")

        por_meta = {
            "volume_agua": "CON. FAT. ÁGUA",
            "volume_esgoto": "CON. FAT. ESGOTO",
            "economias_agua": "ECO. FAT. ÁGUA",
            "economias_esgoto": "ECO. FAT. ESGOTO",
        }
        for campo, agrupador in por_meta.items():
            dados[f"meta_{campo}"] = _somar_coluna(
                metas.loc[metas["AGRUPADOR"].eq(agrupador)], "VALOR"
            )

        if "NUM_LIGACAO" in faturamento.columns and "NUM_LIGACAO" in por_tipo["agua"].columns:
            ligacoes_sb = faturamento.loc[
                faturamento["CLASSE_RUBRICA"].eq("CONTAS DE ÁGUA SB"),
                ["CIDADE", "COD_GRUPO", "NUM_LIGACAO"],
            ].copy()
            ligacoes_sb["CIDADE_NORM"] = ligacoes_sb["CIDADE"].map(normalizar_cidade)
            ligacoes_sb["COD_GRUPO"] = pd.to_numeric(
                ligacoes_sb["COD_GRUPO"], errors="coerce"
            ).astype("Int64")
            ligacoes_sb["NUM_LIGACAO"] = pd.to_numeric(
                ligacoes_sb["NUM_LIGACAO"], errors="coerce"
            ).astype("Int64")
            chaves_sb = ligacoes_sb[["CIDADE_NORM", "COD_GRUPO", "NUM_LIGACAO"]].drop_duplicates()
            economias_agua = por_tipo["agua"].copy()
            economias_agua["NUM_LIGACAO"] = pd.to_numeric(
                economias_agua["NUM_LIGACAO"], errors="coerce"
            ).astype("Int64")
            ligacoes_sb = chaves_sb.merge(
                economias_agua[["CIDADE_NORM", "COD_GRUPO", "NUM_LIGACAO", "SUMQTD_ECONOMIAS"]],
                on=["CIDADE_NORM", "COD_GRUPO", "NUM_LIGACAO"],
                how="inner",
                validate="one_to_one",
            )
            dados["economias_sb_agua"] = _somar_coluna(ligacoes_sb, "SUMQTD_ECONOMIAS")

    valores_faturados = pd.to_numeric(faturamento["SumVALOR"], errors="coerce")
    dados["contas_agua"] = _somar_coluna(
        faturamento.loc[faturamento["CLASSE_RUBRICA"].eq("CONTAS DE ÁGUA")], "SumVALOR"
    )
    dados["contas_esgoto"] = _somar_coluna(
        faturamento.loc[faturamento["CLASSE_RUBRICA"].eq("CONTAS DE ESGOTO")], "SumVALOR"
    )
    dados["contas_agua_sb"] = _somar_coluna(
        faturamento.loc[faturamento["CLASSE_RUBRICA"].eq("CONTAS DE ÁGUA SB")], "SumVALOR"
    )
    motivos = (
        faturamento["MOTIVO_CANCELAMENTO"].astype("string").str.strip()
        if "MOTIVO_CANCELAMENTO" in faturamento.columns
        else pd.Series("", index=faturamento.index, dtype="string")
    )
    canceladas = motivos.notna() & motivos.ne("")
    dados["cancelamentos_quantidade"] = int(canceladas.sum())
    # TODO: substituir os zeros quando a base não disponibilizar dados de cancelamento.
    dados["cancelamentos_valor"] = (
        float(valores_faturados.loc[canceladas].sum()) if canceladas.any() else 0.0
    )
    return dados


def _formatar_medida(valor: float | None, casas: int = 2) -> str:
    return "—" if valor is None or pd.isna(valor) else decimal(valor, casas)


def _formatar_delta(realizado: float | None, orcado: float | None) -> tuple[str, str]:
    if realizado is None or orcado is None or orcado == 0:
        return "—", "neutro"
    delta = (realizado - orcado) / orcado
    return percentual(delta), "positivo" if delta >= 0 else "negativo"


def _card_comercial(
    icone: str,
    titulo: str,
    valor: str,
    descricao: str,
    rodape: str,
    *,
    detalhes: str = "",
    classe: str = "",
) -> str:
    return (
        f'<article class="oic-card {classe}">'
        f'<div class="oic-label"><span class="oic-icon">{html.escape(icone)}</span>{html.escape(titulo)}</div>'
        f'<div class="oic-value">{html.escape(valor)}</div>'
        f'<div class="oic-description">{descricao}</div>'
        f'<div class="oic-details">{detalhes}</div>'
        f'<div class="oic-footer">{rodape}</div>'
        "</article>"
    )


def _secao_indicadores_comerciais(
    faturamento: pd.DataFrame,
    total: float,
    fontes: FontesComparacao | None,
    filtros: dict | None,
) -> None:
    valores = _calcular_indicadores_comerciais(faturamento, fontes, filtros)
    if fontes is not None:
        referencia = fontes.referencia.strftime("%Y-%m")
    else:
        referencia = "Sem referência"

    delta_agua, cor_delta_agua = _formatar_delta(
        valores["volume_agua"], valores["meta_volume_agua"]
    )
    delta_esgoto, cor_delta_esgoto = _formatar_delta(
        valores["volume_esgoto"], valores["meta_volume_esgoto"]
    )

    media_agua = _dividir(valores["volume_agua"], valores["economias_agua"])
    media_esgoto = _dividir(valores["volume_esgoto"], valores["economias_esgoto"])
    meta_media_agua = _dividir(
        valores["meta_volume_agua"], valores["meta_economias_agua"]
    )
    meta_media_esgoto = _dividir(
        valores["meta_volume_esgoto"], valores["meta_economias_esgoto"]
    )
    tarifa_agua = _dividir(valores["contas_agua"], valores["volume_agua"])
    tarifa_esgoto = _dividir(valores["contas_esgoto"], valores["volume_esgoto"])
    tarifa_sb = _dividir(valores["contas_agua_sb"], valores["economias_sb_agua"])

    volume_agua = _formatar_medida(valores["volume_agua"], 0)
    volume_esgoto = _formatar_medida(valores["volume_esgoto"], 0)
    meta_volume_agua = _formatar_medida(valores["meta_volume_agua"], 0)
    meta_volume_esgoto = _formatar_medida(valores["meta_volume_esgoto"], 0)
    meta_economias_agua = inteiro(valores["meta_economias_agua"]) if valores["meta_economias_agua"] is not None else "—"
    meta_economias_esgoto = inteiro(valores["meta_economias_esgoto"]) if valores["meta_economias_esgoto"] is not None else "—"
    economias_agua = inteiro(valores["economias_agua"]) if valores["economias_agua"] is not None else "—"
    economias_esgoto = inteiro(valores["economias_esgoto"]) if valores["economias_esgoto"] is not None else "—"
    volume_medido = _formatar_medida(valores["volume_medido_agua"], 0)
    cancelamentos = brl(valores["cancelamentos_valor"])
    total_formatado = brl(total)

    delta_agua_html = (
        f'<span class="oic-delta {cor_delta_agua}">Δ {html.escape(delta_agua)}</span>'
    )
    delta_esgoto_html = (
        f'<span class="oic-delta {cor_delta_esgoto}">Δ {html.escape(delta_esgoto)}</span>'
    )
    detalhes_agua = (
        '<div><span>Volume médio</span><strong>'
        f'{_formatar_medida(media_agua)} m³</strong></div>'
        '<div><span>Meta Vol Médio A</span><strong>'
        f'{_formatar_medida(meta_media_agua)} m³</strong></div>'
    )
    detalhes_esgoto = (
        '<div><span>Volume médio</span><strong>'
        f'{_formatar_medida(media_esgoto)} m³</strong></div>'
        '<div><span>Meta Vol Médio E</span><strong>'
        f'{_formatar_medida(meta_media_esgoto)} m³</strong></div>'
    )
    cancelamentos_html = (
        '<span class="oic-alert oic-alert-red"><i></i>'
        f'Cancelamentos: {html.escape(cancelamentos)} · {inteiro(valores["cancelamentos_quantidade"])} registros'
        "</span>"
    )
    # TODO: substituir os valores simulados quando existir uma fonte de outliers comerciais.
    outliers_html = '<span class="oic-alert oic-alert-amber"><i></i>Outliers: R$ 0,00 · 0 este mês</span>'

    cards_linha_1 = "".join(
        [
            _card_comercial(
                "💧",
                "VOLUME FATURADO DE ÁGUA",
                f"{volume_agua} m³",
                f'Orçado {meta_volume_agua} m³ {delta_agua_html}',
                f"Volume medido {volume_medido} m³",
            ),
            _card_comercial(
                "🚽",
                "VOLUME FATURADO DE ESGOTO",
                f"{volume_esgoto} m³",
                f'Orçado {meta_volume_esgoto} m³ {delta_esgoto_html}',
                "Total realizado no período",
            ),
            _card_comercial(
                "🏠",
                "ECONOMIAS ÁGUA",
                economias_agua,
                f"{meta_economias_agua} meta",
                "Total realizado no período",
                detalhes=detalhes_agua,
            ),
            _card_comercial(
                "🏠",
                "ECONOMIAS ESGOTO",
                economias_esgoto,
                f"{meta_economias_esgoto} meta",
                "Total realizado no período",
                detalhes=detalhes_esgoto,
            ),
        ]
    )
    cards_linha_2 = "".join(
        [
            _card_comercial(
                "💧",
                "TARIFA MÉDIA ÁGUA",
                brl(tarifa_agua),
                "",
                "por m³ faturado",
                classe="oic-tarifa",
            ),
            _card_comercial(
                "🚽",
                "TARIFA MÉDIA ESGOTO",
                brl(tarifa_esgoto),
                "",
                "por m³ faturado",
                classe="oic-tarifa",
            ),
            _card_comercial(
                "💧",
                "TARIFA MÉDIA SB",
                brl(tarifa_sb),
                "",
                "por economia",
                classe="oic-tarifa",
            ),
        ]
    )

    st.markdown(
        f"""
        <style>
        .oic-section {{ background:#0F172A; color:#F8FAFC; border:1px solid #263449; border-radius:16px; padding:18px; margin:18px 0; }}
        .oic-alerts {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px 24px; background:#1E293B; border:1px solid #334155; border-radius:11px; padding:11px 14px; color:#CBD5E1; font-size:12px; font-weight:600; }}
        .oic-alert {{ display:inline-flex; align-items:center; gap:7px; }}
        .oic-alert i {{ display:inline-block; width:7px; height:7px; border-radius:50%; background:#22C55E; }}
        .oic-alert-red i {{ background:#F87171; }}
        .oic-alert-amber i {{ background:#FBBF24; }}
        .oic-alert-total {{ color:#FFFFFF; }}
        .oic-heading {{ display:flex; justify-content:space-between; align-items:center; gap:16px; border-bottom:1px solid #263449; padding:20px 0 16px; margin-bottom:16px; }}
        .oic-title {{ color:#FFFFFF; font-size:23px; font-weight:750; line-height:1.2; }}
        .oic-subtitle {{ color:#94A3B8; font-size:12px; margin-top:5px; }}
        .oic-reference {{ flex:none; background:#1E293B; border:1px solid #334155; border-radius:24px; color:#E2E8F0; padding:9px 14px; font-size:12px; font-weight:700; }}
        .oic-grid {{ display:grid; gap:12px; }}
        .oic-grid-four {{ grid-template-columns:repeat(4,minmax(0,1fr)); }}
        .oic-grid-three {{ grid-template-columns:repeat(3,minmax(0,1fr)); margin-top:12px; }}
        .oic-card {{ min-width:0; display:flex; flex-direction:column; background:#1E293B; border:1px solid #334155; border-radius:14px; padding:16px; }}
        .oic-label {{ display:flex; align-items:center; gap:7px; color:#AFC3DE; font-size:10px; font-weight:700; letter-spacing:.055em; line-height:1.4; }}
        .oic-icon {{ font-size:13px; }}
        .oic-value {{ color:#F8FAFC; font-size:25px; font-weight:750; letter-spacing:-.025em; margin:11px 0 5px; white-space:nowrap; }}
        .oic-description {{ min-height:20px; color:#E2E8F0; font-size:11px; font-weight:600; }}
        .oic-delta {{ margin-left:5px; font-weight:750; }}
        .oic-delta.positivo {{ color:#4ADE80; }}
        .oic-delta.negativo {{ color:#F87171; }}
        .oic-delta.neutro {{ color:#94A3B8; }}
        .oic-details {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; border-top:1px solid #334155; margin-top:10px; padding-top:10px; }}
        .oic-details div {{ display:flex; flex-direction:column; gap:3px; }}
        .oic-details span {{ color:#94A3B8; font-size:10px; }}
        .oic-details strong {{ color:#67E8F9; font-size:12px; }}
        .oic-footer {{ color:#AAB7CA; font-size:10px; font-weight:600; margin-top:auto; padding-top:10px; }}
        .oic-tarifa {{ align-items:center; text-align:center; background:linear-gradient(135deg,#1E293B,#203A5C); padding:20px; }}
        .oic-tarifa .oic-label {{ flex-direction:column; gap:8px; }}
        .oic-tarifa .oic-icon {{ font-size:24px; }}
        .oic-tarifa .oic-value {{ font-size:22px; margin:8px 0 0; }}
        .oic-tarifa .oic-footer {{ color:#AFC3DE; font-size:10px; padding-top:5px; }}
        @media (max-width:1000px) {{ .oic-grid-four {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
        @media (max-width:620px) {{ .oic-section {{ padding:12px; }} .oic-grid-four,.oic-grid-three {{ grid-template-columns:1fr; }} .oic-heading {{ align-items:flex-start; }} .oic-title {{ font-size:19px; }} }}
        </style>
        <section class="oic-section">
          <div class="oic-alerts">
            <span class="oic-alert oic-alert-total"><i></i>Valor Total: {html.escape(total_formatado)}</span>
            {cancelamentos_html}
            {outliers_html}
          </div>
          <header class="oic-heading">
            <div>
              <div class="oic-title">Oeste Indicadores Comerciais</div>
              <div class="oic-subtitle">Faturamento • Água • Esgoto • Serviço Básico</div>
            </div>
            <span class="oic-reference">▦ {html.escape(referencia)}</span>
          </header>
          <div class="oic-grid oic-grid-four">{cards_linha_1}</div>
          <div class="oic-grid oic-grid-three">{cards_linha_2}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


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
    _secao_indicadores_comerciais(
        df,
        total,
        fontes_comparacao,
        filtros_comparacao,
    )

    if fontes_comparacao is not None:
        financeiro, operacional, _ = construir_comparacoes(
            df, fontes_comparacao, **(filtros_comparacao or {})
        )
        financeiro_grupos, _, _ = construir_comparacoes(
            df,
            fontes_comparacao,
            **(filtros_comparacao or {}),
            dimensao="COD_GRUPO",
        )
        nota = (
            "Meta financeira indisponível no nível de DESCRICAO_RUBRICA; valores realizados refletem o filtro de rubrica."
            if (filtros_comparacao or {}).get("descricoes")
            else None
        )
        with st.container(border=True):
            st.plotly_chart(
                grafico_grupos_faturamento(financeiro_grupos, fontes_comparacao.referencia),
                use_container_width=True,
                config=CONFIG,
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
            nome_arquivo="faturamento_classificacao.csv",
        )

    with st.expander("Conferência dos cálculos", expanded=not tudo_ok(checks)):
        for item in checks:
            marca = "OK" if item["ok"] else "Falha"
            aviso(f"<b>{marca}.</b> {item['nome']}. {item['detalhe']}", "ok" if item["ok"] else "erro")
