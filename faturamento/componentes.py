"""Componentes visuais no idioma do Book Comercial."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from faturamento.formato import brl, codigo, decimal, inteiro, percentual

CSS = """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"] { font-family: "Inter", "Segoe UI", sans-serif; }
.stApp { background: #E2E5F0; }
section[data-testid="stSidebar"] {
  background: #111799;
  border-right: 0;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] small,
section[data-testid="stSidebar"] li {
  color: #E8ECFF;
}
section[data-testid="stSidebar"] .eyebrow {
  color: #9DEEE7;
  font-size: 10.5px;
  letter-spacing: .16em;
  text-transform: uppercase;
  font-weight: 700;
  margin: 0;
}
section[data-testid="stSidebar"] .marca-b {
  color: #fff;
  font-size: 20px;
  font-weight: 800;
  letter-spacing: -.01em;
  display: block;
  margin-top: 2px;
}
section[data-testid="stSidebar"] .regua {
  width: 56px; height: 3px; background: #17E3CB; border-radius: 2px; margin: 8px 0 12px;
}
div[data-testid="stVerticalBlockBorderWrapper"] {
  background: #fff;
  border: 1px solid #D3D7E6 !important;
  border-radius: 14px !important;
  padding: 8px 12px 12px !important;
}
.cabec-h1 { margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -.02em; color: #111799; }
.cabec-sub { margin: 4px 0 0; font-size: 12.5px; color: #44495C; }
.regua-pag { width: 80px; height: 4px; background: #17E3CB; margin: 8px 0 14px; border-radius: 2px; }
.kpis { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 14px; margin: 4px 0 16px; }
.kpi { background: #fff; border: 1px solid #D3D7E6; border-radius: 14px; padding: 14px 16px; min-width: 0; }
.kpi .rot { font-size: 10.5px; letter-spacing: .12em; text-transform: uppercase; color: #44495C; font-weight: 700; }
.kpi .val { font-size: 24px; font-weight: 800; letter-spacing: -.03em; margin-top: 6px; line-height: 1.05; color: #191B23; }
.kpi .pe { font-size: 12px; color: #44495C; margin-top: 6px; line-height: 1.4; }
.kpi.destaque { background: #111799; border-color: #111799; }
.kpi.destaque .rot { color: #9DEEE7; }
.kpi.destaque .val, .kpi.destaque .pe { color: #fff; }
.kpi .val.neg { color: #E0383D; }
.kpi.destaque .val.neg { color: #FFB4B6; }
.aviso { border-radius: 10px; padding: 10px 13px; font-size: 12.5px; line-height: 1.5; margin: 0 0 14px; }
.aviso.info { background: #EAF0FF; border: 1px solid #C5D1F8; color: #111799; }
.aviso.ok { background: #E8FBF9; border: 1px solid #9DEEE7; color: #0A6E63; }
.aviso.erro { background: #FFE5E6; border: 1px solid #FFC2C4; color: #A8202A; }
.card-tit { margin: 0; font-size: 15px; font-weight: 700; color: #111799; }
.card-sub { margin: 2px 0 8px; font-size: 12px; color: #44495C; }
.book-tabela { max-height: 560px; overflow: auto; border-radius: 10px; border: 1px solid #D3D7E6; background: #fff; }
.book-tabela table { width: 100%; border-collapse: collapse; font-size: 12.8px; }
.book-tabela th, .book-tabela td { padding: 8px 10px; border-bottom: 1px solid #D3D7E6; white-space: nowrap; }
.book-tabela th {
  position: sticky; top: 0; z-index: 1;
  background: #111799; color: #fff;
  font-size: 10.5px; letter-spacing: .06em; text-transform: uppercase; font-weight: 700;
  text-align: right;
}
.book-tabela th:first-child, .book-tabela td:first-child { text-align: left; }
.book-tabela td { text-align: right; color: #191B23; background: #fff; }
.book-tabela tbody tr:hover td { background: #F7F9FD; }
.book-tabela td.neg { color: #E0383D; font-weight: 700; }
.book-tabela tfoot td {
  font-weight: 800; color: #111799; background: #F7F9FD;
  border-top: 1.5px solid #111799; position: sticky; bottom: 0;
}
.mini-barra { display: inline-block; height: 7px; border-radius: 4px; margin-left: 8px; vertical-align: middle; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; margin: 0 0 12px; }
.chip { font-size: 11.5px; background: #DCE3FA; color: #111799; border-radius: 20px; padding: 3px 10px; font-weight: 600; }
</style>
"""


def injetar_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def cabecalho(titulo: str, subtitulo: str) -> None:
    st.markdown(
        (
            f'<div class="cabec-h1">{html.escape(titulo)}</div>'
            f'<p class="cabec-sub">{html.escape(subtitulo)}</p>'
            '<div class="regua-pag"></div>'
        ),
        unsafe_allow_html=True,
    )


def aviso(texto: str, tipo: str = "info") -> None:
    st.markdown(f'<div class="aviso {tipo}">{texto}</div>', unsafe_allow_html=True)


def cartao(titulo: str, subtitulo: str = "") -> None:
    sub = f'<p class="card-sub">{html.escape(subtitulo)}</p>' if subtitulo else '<div style="height:8px"></div>'
    st.markdown(f'<div class="card-tit">{html.escape(titulo)}</div>{sub}', unsafe_allow_html=True)


def kpis(itens: list[dict]) -> None:
    blocos = []
    for item in itens:
        classes = "kpi destaque" if item.get("destaque") else "kpi"
        valor_classe = "val neg" if item.get("negativo") else "val"
        blocos.append(
            "<article class='{classes}'>"
            "<div class='rot'>{rotulo}</div>"
            "<div class='{valor_classe}'>{valor}</div>"
            "<div class='pe'>{detalhe}</div>"
            "</article>".format(
                classes=classes,
                valor_classe=valor_classe,
                rotulo=html.escape(str(item.get("rotulo", ""))),
                valor=html.escape(str(item.get("valor", "—"))),
                detalhe=html.escape(str(item.get("detalhe", ""))),
            )
        )
    st.markdown(f'<div class="kpis">{"".join(blocos)}</div>', unsafe_allow_html=True)


def chips(textos: list[str]) -> None:
    if not textos:
        return
    conteudo = "".join(f'<span class="chip">{html.escape(texto)}</span>' for texto in textos)
    st.markdown(f'<div class="chips">{conteudo}</div>', unsafe_allow_html=True)


def _formatar(valor, tipo: str) -> str:
    try:
        if pd.isna(valor):
            return "—"
    except (TypeError, ValueError):
        pass
    if tipo == "moeda":
        return brl(float(valor))
    if tipo == "pct":
        return percentual(float(valor))
    if tipo == "numero":
        return decimal(float(valor))
    if tipo == "inteiro":
        return inteiro(valor)
    if tipo == "codigo":
        return codigo(valor)
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "—"
    return str(valor)


def mostrar_tabela(
    df: pd.DataFrame,
    colunas: list[dict],
    *,
    prefixo: str,
    nome_arquivo: str,
    totalizador: bool = True,
) -> pd.DataFrame:
    """Tabela com ordenação padrão e exportação CSV, sem filtros locais."""
    visao = df.copy()
    campo_ordem = next(
        (coluna["campo"] for coluna in colunas if coluna["campo"] in ("Faturamento", "Faturamento Total")),
        colunas[0]["campo"],
    )
    if campo_ordem in visao.columns and not visao.empty:
        visao = visao.sort_values(campo_ordem, ascending=False, kind="mergesort")

    exportar = visao.copy()
    csv = exportar.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button(
        "Exportar CSV",
        data=csv,
        file_name=nome_arquivo,
        mime="text/csv",
        key=f"{prefixo}_csv",
    )

    if visao.empty:
        aviso("Nenhum registro no recorte atual.", "info")
        return visao

    pico_part = 1.0
    for coluna in colunas:
        if coluna.get("barra") and coluna["campo"] in visao.columns and not visao.empty:
            pico_part = max(pico_part, float(visao[coluna["campo"]].abs().max() or 1))

    cabecalho_html = "".join(f"<th>{html.escape(coluna['titulo'])}</th>" for coluna in colunas)
    linhas = []
    limite = 800
    for _, registro in visao.head(limite).iterrows():
        celulas = []
        for coluna in colunas:
            valor = registro[coluna["campo"]]
            texto = html.escape(_formatar(valor, coluna["tipo"]))
            classe = ""
            extra = ""
            if coluna["tipo"] == "moeda" and pd.notna(valor) and float(valor) < 0:
                classe = " class='neg'"
            if coluna.get("barra") and pd.notna(valor):
                largura = min(72, abs(float(valor)) / pico_part * 72)
                cor = "#E0383D" if float(valor) < 0 else "#17E3CB"
                extra = f"<span class='mini-barra' style='width:{largura:.0f}px;background:{cor}'></span>"
            celulas.append(f"<td{classe}>{texto}{extra}</td>")
        linhas.append("<tr>" + "".join(celulas) + "</tr>")

    rodape = ""
    if totalizador and len(visao) > 1:
        totais = []
        for indice, coluna in enumerate(colunas):
            campo = coluna["campo"]
            if indice == 0:
                totais.append("<td>Total do recorte</td>")
            elif coluna["tipo"] == "moeda":
                totais.append(f"<td>{html.escape(brl(float(visao[campo].sum())))}</td>")
            elif coluna["tipo"] == "inteiro":
                totais.append(f"<td>{html.escape(inteiro(visao[campo].sum()))}</td>")
            elif coluna["tipo"] == "pct":
                totais.append(f"<td>{html.escape(percentual(float(visao[campo].sum())))}</td>")
            else:
                totais.append("<td></td>")
        rodape = "<tfoot><tr>" + "".join(totais) + "</tr></tfoot>"

    st.markdown(
        (
            '<div class="book-tabela"><table><thead><tr>'
            + cabecalho_html
            + "</tr></thead><tbody>"
            + "".join(linhas)
            + "</tbody>"
            + rodape
            + "</table></div>"
        ),
        unsafe_allow_html=True,
    )
    if len(visao) > limite:
        aviso(f"A tabela mostra os primeiros {limite} registros. O CSV contém a lista inteira deste recorte.", "info")
    return visao
