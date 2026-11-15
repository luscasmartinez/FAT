"""Componentes visuais compartilhados para comparação com metas."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from faturamento.componentes import aviso, cartao, mostrar_tabela
from faturamento.graficos import CONFIG, grafico_atingimento


def mostrar_comparacao(
    financeiro: pd.DataFrame,
    operacional: pd.DataFrame,
    *,
    prefixo: str,
    referencia: pd.Timestamp,
    avisos: tuple[str, ...] = (),
    nota: str | None = None,
) -> None:
    with st.container(border=True):
        cartao(
            "Comparação com a meta",
            f"Referência {referencia:%d/%m/%Y} · realizado comparado por CIDADE e COD_GRUPO",
        )
        if nota:
            st.caption(nota)
        for texto in avisos:
            aviso(texto, "info")

        financeiro_visao = financeiro.copy()
        rotulo_dimensao = None
        if "Dimensão" in financeiro_visao.columns:
            rotulo_dimensao = "Cidade" if not pd.api.types.is_numeric_dtype(financeiro_visao["Dimensão"]) else "COD_GRUPO"
            financeiro_visao = financeiro_visao.rename(columns={"Dimensão": rotulo_dimensao})
        if not financeiro_visao.empty:
            st.markdown("#### Faturamento (R$)")
            if rotulo_dimensao:
                grafico = grafico_atingimento(financeiro, "Dimensão")
                if grafico is not None:
                    st.plotly_chart(grafico, use_container_width=True, config=CONFIG)
            campos = [
                {"campo": "Indicador", "titulo": "Indicador", "tipo": "texto"},
                {"campo": "Realizado bruto", "titulo": "Realizado bruto", "tipo": "moeda"},
                {"campo": "Abatimentos realizados", "titulo": "Abatimentos", "tipo": "moeda"},
                {"campo": "Realizado líquido", "titulo": "Realizado líquido", "tipo": "moeda"},
                {"campo": "Meta", "titulo": "Meta", "tipo": "moeda"},
                {"campo": "Diferença", "titulo": "Diferença", "tipo": "moeda"},
                {"campo": "Atingimento", "titulo": "% atingimento", "tipo": "pct"},
                {"campo": "Status", "titulo": "Status", "tipo": "texto"},
                {"campo": "Reconciliação", "titulo": "Reconciliação", "tipo": "texto"},
            ]
            if rotulo_dimensao:
                campos.insert(0, {"campo": rotulo_dimensao, "titulo": rotulo_dimensao, "tipo": "texto"})
            mostrar_tabela(
                financeiro_visao,
                campos,
                prefixo=f"{prefixo}_financeiro",
                nome_arquivo="comparacao_meta_faturamento.csv",
                totalizador=False,
            )

        for unidade, titulo, tipo_valor, nome_arquivo in (
            ("m³", "Volume faturado (m³)", "numero", "comparacao_meta_volume.csv"),
            ("economias", "Economias faturadas", "inteiro", "comparacao_meta_economias.csv"),
        ):
            dados = operacional.loc[operacional["Unidade"].eq(unidade)].copy()
            if dados.empty:
                continue
            dimensao_coluna = None
            if "Dimensão" in dados.columns:
                dimensao_coluna = rotulo_dimensao or "Dimensão"
                dados = dados.rename(columns={"Dimensão": dimensao_coluna})
            st.markdown(f"#### {titulo}")
            campos = [
                {"campo": "Indicador", "titulo": "Indicador", "tipo": "texto"},
                {"campo": "Realizado", "titulo": "Realizado", "tipo": tipo_valor},
                {"campo": "Meta", "titulo": "Meta", "tipo": tipo_valor},
                {"campo": "Diferença", "titulo": "Diferença", "tipo": tipo_valor},
                {"campo": "Atingimento", "titulo": "% atingimento", "tipo": "pct"},
                {"campo": "Status", "titulo": "Status", "tipo": "texto"},
                {"campo": "Detalhe", "titulo": "Detalhe", "tipo": "texto"},
            ]
            if dimensao_coluna:
                campos.insert(0, {"campo": dimensao_coluna, "titulo": dimensao_coluna, "tipo": "texto"})
            mostrar_tabela(
                dados,
                campos,
                prefixo=f"{prefixo}_{unidade.replace('³', '3')}",
                nome_arquivo=nome_arquivo,
                totalizador=False,
            )