"""Painel de faturamento."""

from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from faturamento.calculo import aplicar_filtros, somar_faturamento
from faturamento.comparacao import (
    CAMINHO_ECONOMIAS,
    CAMINHO_META,
    FontesComparacao,
    carregar_fontes_comparacao,
    construir_comparacoes,
    validar_upload_economias,
    validar_upload_meta,
    validar_comparacao,
)
from faturamento.componentes import aviso, injetar_css
from faturamento.constantes import CAMINHO_PADRAO
from faturamento.dados import PlanilhaInvalida, carregar_arquivo, validar_upload_faturamento
from faturamento.formato import brl, inteiro
from faturamento.paginas.cidades import pagina_cidades
from faturamento.paginas.comparativo import mostrar_comparacao
from faturamento.paginas.grupos import pagina_grupos
from faturamento.paginas.rubricas import pagina_rubricas
from faturamento.paginas.visao import pagina_visao
from faturamento.validacao import fechar_recorte, tudo_ok, validar_base
from faturamento.persistencia import (
    BASES,
    ErroPersistencia,
    ErroValidacaoUpload,
    Persistencia,
    criar_persistencia,
    sha256,
)

ABAS = ("Visão geral", "Cidades", "COD_GRUPO", "Rubricas")


@st.cache_data(show_spinner=False)
def _cache_caminho(caminho: str, alteracao: float):
    return carregar_arquivo(caminho)


@st.cache_data(show_spinner=False)
def _cache_upload(conteudo: bytes, nome: str):
    import io

    return carregar_arquivo(io.BytesIO(conteudo), nome=nome)


@st.cache_data(show_spinner=False)
def _cache_fontes_comparacao(meta_bytes: bytes, economias_bytes: bytes):
    return carregar_fontes_comparacao(io.BytesIO(meta_bytes), io.BytesIO(economias_bytes))


@st.cache_resource(show_spinner=False)
def _persistencia() -> Persistencia:
    return criar_persistencia()


def _validar_bytes(tipo: str, conteudo: bytes, nome: str | None = None) -> dict:
    if tipo == "faturamento":
        return validar_upload_faturamento(conteudo, nome or "faturamento.xlsx")
    if tipo == "meta":
        return validar_upload_meta(conteudo)
    if tipo == "economias":
        return validar_upload_economias(conteudo)
    raise ValueError("Tipo de base inválido.")


@st.cache_data(show_spinner=False)
def _cache_persistido(_storage: Persistencia, tipo: str, versao_id: str, hash_completo: str):
    return _storage.load_current(tipo, lambda conteudo: _validar_bytes(tipo, conteudo))


@st.dialog("Confirmação dupla: remover base atual")
def _confirmar_remocao(storage: Persistencia, tipo: str) -> None:
    rotulos = {"faturamento": "Faturamento Líquido", "meta": "Meta", "economias": "Economias Faturadas"}
    st.warning(f"A base {rotulos[tipo]} deixará de ser usada. A versão atual será preservada no histórico.")
    confirmacao = st.checkbox("Confirmo que quero remover a base atual", key=f"confirmar_remocao_{tipo}")
    if st.button("Remover base atual", disabled=not confirmacao, key=f"remover_confirmado_{tipo}"):
        try:
            storage.remove_current(tipo)
        except ErroPersistencia as exc:
            st.error(str(exc))
        else:
            st.session_state.storage_flash = {"tipo": tipo, "status": "removida"}
            st.rerun()


def _autor_atual() -> str | None:
    autor = st.session_state.get("user")
    if isinstance(autor, dict):
        return autor.get("email") or autor.get("name")
    return os.getenv("STORAGE_AUTHOR") or None


def _exibir_estado_base(tipo: str, estado: dict, fallback: bool) -> None:
    rotulos = {"faturamento": "Faturamento Líquido", "meta": "Meta", "economias": "Economias Faturadas"}
    info = estado.get("metadata") or {}
    if estado.get("status") == "Válida" and info:
        data_hora = str(info.get("data_hora", ""))[:19].replace("T", " ")
        tamanho = float(info.get("tamanho_bytes", 0)) / (1024 * 1024)
        st.caption(
            f"{rotulos[tipo]} · {info.get('nome_original', 'arquivo')} · {data_hora} · "
            f"SHA {str(info.get('sha256', ''))[:8]} · {tamanho:.2f} MB · Válida"
        )
    elif estado.get("status") in {"Com erro", "Corrompida"}:
        st.warning(f"{rotulos[tipo]} persistida: {estado['status']}. A versão anterior não foi usada.")
        if fallback:
            st.caption("Arquivo padrão local usado como alternativa.")
    elif estado.get("removida"):
        st.caption(f"{rotulos[tipo]} · Ausente (removida; histórico preservado).")
    elif fallback:
        st.caption(f"{rotulos[tipo]} · Ausente no armazenamento; arquivo padrão local em uso.")
    else:
        st.caption(f"{rotulos[tipo]} · Ausente.")


def _gerenciar_historico(storage: Persistencia, tipo: str, validar) -> None:
    historico = [versao for versao in storage.list_versions(tipo) if not versao["atual"]]
    if historico:
        por_id = {versao["id"]: versao for versao in historico}

        def rotulo(versao_id: str) -> str:
            versao = por_id[versao_id]
            return (
                f"{str(versao['data_hora'])[:19].replace('T', ' ')} · SHA {versao['sha256_curto']} · "
                f"{versao['status']}{' · arquivada' if versao['arquivada'] else ''}"
            )

        escolha_id = st.selectbox(
            "Versão para restaurar",
            list(por_id),
            format_func=rotulo,
            key=f"restaurar_versao_{tipo}",
        )
        if st.button("Restaurar versão anterior", key=f"restaurar_{tipo}"):
            try:
                resultado = storage.restore_version(tipo, escolha_id, validar, autor=_autor_atual())
            except Exception as exc:
                st.error(f"Restauração não aplicada: {exc}")
            else:
                st.session_state.storage_flash = {
                    "tipo": tipo,
                    "status": "persistida",
                    "data_hora": resultado["data_hora"],
                    "alterada": resultado["alterada"],
                }
                st.rerun()
    else:
        st.caption("Ainda não há versões anteriores para restaurar.")
    if st.button("Remover base atual", key=f"remover_{tipo}"):
        _confirmar_remocao(storage, tipo)


def _processar_upload(storage: Persistencia, tipo: str, arquivo) -> None:
    if arquivo is None:
        return
    conteudo = arquivo.getvalue()
    assinatura = (arquivo.name, len(conteudo), __import__("hashlib").sha256(conteudo).hexdigest())
    chave_assinatura = f"upload_assinatura_{tipo}"
    if st.session_state.get(chave_assinatura) == assinatura:
        return
    try:
        resultado = storage.save_upload(
            tipo,
            conteudo,
            arquivo.name,
            aba=None,
            validar=lambda dados: _validar_bytes(tipo, dados, arquivo.name),
            autor=_autor_atual(),
        )
    except Exception as exc:
        st.session_state.storage_flash = {"tipo": tipo, "status": "erro", "detalhe": str(exc)}
    else:
        st.session_state.storage_flash = {
            "tipo": tipo,
            "status": "persistida" if resultado["alterada"] else "idêntica",
            "data_hora": resultado["data_hora"],
            "alterada": resultado["alterada"],
                    "versao_anterior": resultado.get("versao_anterior", False),
        }
    st.session_state[chave_assinatura] = assinatura
    st.session_state.uploader_seq += 1
    st.session_state.fid += 1
    st.rerun()


def _opcoes(serie):
    valores = [valor for valor in serie.dropna().unique()]
    return sorted(valores, key=lambda valor: str(valor))


def _opcoes_codigo(serie):
    valores = [int(valor) for valor in serie.dropna().unique()]
    return sorted(valores)


def _textos_filtro(cidades, codigos, classes, grupos, descricoes) -> list[str]:
    textos = []
    if cidades:
        textos.append("Cidade: " + (", ".join(cidades) if len(cidades) <= 3 else f"{len(cidades)} selecionadas"))
    if codigos:
        codigos_txt = ", ".join(str(codigo) for codigo in codigos)
        textos.append("COD_GRUPO: " + (codigos_txt if len(codigos) <= 6 else f"{len(codigos)} selecionados"))
    if classes:
        textos.append("Classe: " + ", ".join(classes))
    if grupos:
        textos.append("Grupo: " + ", ".join(grupos))
    if descricoes:
        textos.append("Rubrica: " + (", ".join(descricoes) if len(descricoes) <= 2 else f"{len(descricoes)} selecionadas"))
    return textos


def main() -> None:
    st.set_page_config(
        page_title="Faturamento",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    injetar_css()
    if "fid" not in st.session_state:
        st.session_state.fid = 0
    if "aba" not in st.session_state:
        st.session_state.aba = ABAS[0]
    if "uploader_seq" not in st.session_state:
        st.session_state.uploader_seq = 0

    caminhos_padrao = {
        "faturamento": CAMINHO_PADRAO,
        "meta": CAMINHO_META,
        "economias": CAMINHO_ECONOMIAS,
    }
    nomes_bases = {
        "faturamento": "Faturamento Líquido",
        "meta": "Meta",
        "economias": "Economias Faturadas",
    }
    storage = None
    erro_storage = None
    try:
        storage = _persistencia()
    except ErroPersistencia as exc:
        erro_storage = str(exc)

    with st.sidebar:
        st.markdown(
            "<p class='eyebrow'>Análise gerencial</p><span class='marca-b'>Faturamento</span><div class='regua'></div>",
            unsafe_allow_html=True,
        )
        st.caption("Substituir uma base não soma arquivos; cada envio é validado e versionado separadamente.")
        if storage is None:
            st.error(f"Armazenamento indisponível: {erro_storage}")
        else:
            validadores = {
                "faturamento": lambda conteudo: _validar_bytes("faturamento", conteudo, "faturamento.xlsx"),
                "meta": lambda conteudo: _validar_bytes("meta", conteudo),
                "economias": lambda conteudo: _validar_bytes("economias", conteudo),
            }
            for tipo in BASES:
                with st.form(f"form_upload_{tipo}_{st.session_state.uploader_seq}", clear_on_submit=True):
                    arquivo = st.file_uploader(
                        f"Substituir base: {nomes_bases[tipo]}",
                        type=["xlsx"],
                        key=f"upload_{tipo}_{st.session_state.uploader_seq}",
                    )
                    enviar = st.form_submit_button("Validar e persistir")
                if enviar and arquivo is not None:
                    _processar_upload(storage, tipo, arquivo)

            flash = st.session_state.pop("storage_flash", None)
            if flash:
                if flash["status"] == "erro":
                    st.error(f"Upload não aplicado: {flash.get('detalhe', 'falha de validação')}")
                elif flash["status"] == "idêntica":
                    st.success("Reupload sem alteração; o histórico não foi duplicado.")
                elif flash["status"] == "removida":
                    st.success("Base removida da carga atual; o histórico foi preservado.")
                else:
                    data_hora = str(flash.get("data_hora", ""))[:19].replace("T", " ")
                    anterior = " Versão anterior mantida no histórico." if flash.get("versao_anterior") else ""
                    st.success(f"Base persistida com sucesso em {data_hora}.{anterior}")

            if st.button("Voltar às bases padrão 26-11", use_container_width=True):
                erros = []
                for tipo, caminho in caminhos_padrao.items():
                    if not caminho.exists():
                        continue
                    try:
                        storage.save_upload(
                            tipo,
                            caminho.read_bytes(),
                            caminho.name,
                            aba=None,
                            validar=validadores[tipo],
                            autor=_autor_atual(),
                            acao="restauração do padrão",
                        )
                    except Exception as exc:
                        erros.append(f"{nomes_bases[tipo]}: {exc}")
                if erros:
                    st.error("Algumas bases padrão não foram aplicadas: " + "; ".join(erros))
                else:
                    st.session_state.storage_flash = {
                        "tipo": "todas",
                        "status": "persistida",
                        "data_hora": "agora",
                        "alterada": True,
                    }
                    st.rerun()

    estados = {}
    conteudos = {}
    nomes_ativos = {}
    fallback = {}
    for tipo in BASES:
        info = storage.current_info(tipo) if storage else {"status": "Ausente", "removida": False}
        estado = {**info, "conteudo": None}
        if storage and info.get("versao_id"):
            try:
                carregada = _cache_persistido(
                    storage, tipo, info["versao_id"], info.get("hash_curto", "")
                )
                estado["status"] = carregada["status"]
                estado["metadata"] = carregada.get("metadata")
                estado["erro"] = carregada.get("erro")
                if carregada["status"] == "Válida":
                    estado["conteudo"] = carregada["conteudo"]
                    conteudos[tipo] = carregada["conteudo"]
                    nomes_ativos[tipo] = (carregada.get("metadata") or {}).get("nome_original") or caminhos_padrao[tipo].name
            except Exception as exc:
                estado["status"] = "Com erro"
                estado["erro"] = str(exc)
        if tipo not in conteudos and not info.get("removida") and caminhos_padrao[tipo].exists():
            try:
                conteudos[tipo] = caminhos_padrao[tipo].read_bytes()
                nomes_ativos[tipo] = caminhos_padrao[tipo].name
                fallback[tipo] = True
            except OSError:
                pass
        estados[tipo] = estado

    with st.sidebar:
        for tipo in BASES:
            _exibir_estado_base(tipo, estados[tipo], bool(fallback.get(tipo)))
            if storage:
                with st.expander(f"Histórico e ações: {nomes_bases[tipo]}"):
                    _gerenciar_historico(storage, tipo, lambda conteudo, t=tipo: _validar_bytes(t, conteudo))

        if storage:
            configuracao = storage.configuration_status()
            if configuracao["backend"] == "local":
                diretorio = os.getenv("STORAGE_DIR", "./storage")
                if Path(diretorio).is_absolute():
                    diretorio = "diretório configurado"
            else:
                diretorio = configuracao["localizacao"]
            st.caption(
                f"Backend: {configuracao['backend']} — Diretório/bucket: {diretorio} — "
                f"Versões mantidas: {configuracao['max_versoes']}"
            )
            if configuracao["aviso_efemero"]:
                st.warning("Armazenamento local sem volume explicitamente configurado. Em disco efêmero, os arquivos podem ser perdidos em reinícios; use S3 ou monte um volume persistente.")
        st.info("Sem autenticação configurada: qualquer pessoa com acesso ao app pode substituir as bases. Restrinja o acesso ou habilite autenticação antes de publicar.")

    financeiro_bytes = conteudos.get("faturamento")
    bruto = None
    faturamento = None
    meta_base = None
    if financeiro_bytes is not None:
        try:
            with st.spinner("Carregando faturamento validado..."):
                bruto, faturamento, meta_base = _cache_upload(financeiro_bytes, nomes_ativos["faturamento"])
        except PlanilhaInvalida as exc:
            estados["faturamento"]["status"] = "Com erro"
            estados["faturamento"]["erro"] = str(exc)

    fontes_comparacao: FontesComparacao | None = None
    erro_comparacao = None
    meta_bytes = conteudos.get("meta")
    economias_bytes = conteudos.get("economias")
    if meta_bytes is not None and economias_bytes is not None:
        try:
            fontes_comparacao = _cache_fontes_comparacao(meta_bytes, economias_bytes)
        except ValueError as exc:
            erro_comparacao = str(exc)
    else:
        ausentes = [nomes_bases[tipo] for tipo, dados in (("meta", meta_bytes), ("economias", economias_bytes)) if dados is None]
        erro_comparacao = "Bases ausentes: " + ", ".join(ausentes)

    if faturamento is None or meta_base is None or bruto is None:
        aviso("Base de faturamento ausente ou inválida. Os indicadores financeiros estão indisponíveis e não foram preenchidos com zero.", "erro")
        if fontes_comparacao is not None:
            _financeiro, operacional, _junção = construir_comparacoes(pd.DataFrame(), fontes_comparacao)
            mostrar_comparacao(
                pd.DataFrame(),
                operacional,
                prefixo="sem_faturamento_meta",
                referencia=fontes_comparacao.referencia,
                avisos=fontes_comparacao.avisos,
            )
        st.stop()

    assinatura_bases = "|".join(
        f"{tipo}:{estados[tipo].get('versao_id') or sha256(conteudos.get(tipo, b''))}"
        for tipo in BASES
    )
    token = f"{meta_base['nome']}|{meta_base['linhas_arquivo']}|{meta_base['valor_faturamento']:.2f}|{assinatura_bases}"
    if st.session_state.get("val_token") != token:
        checks = validar_base(bruto, faturamento, meta_base)
        if fontes_comparacao is not None:
            checks.extend(validar_comparacao(faturamento, fontes_comparacao))
        else:
            checks.append({"nome": "Fontes de meta e economias disponíveis", "ok": False, "detalhe": erro_comparacao or "Comparação não carregada."})
        st.session_state.val_checks = checks
        st.session_state.val_token = token
    checks = st.session_state.val_checks

    fid = st.session_state.fid
    with st.sidebar:
        st.markdown(
            f"**{meta_base['nome']}**<br>Planilha: {inteiro(meta_base['linhas_arquivo'])} linhas<br>"
            f"No faturamento: {inteiro(meta_base['linhas_faturamento'])}<br>"
            f"Total: {brl(meta_base['valor_faturamento'])}",
            unsafe_allow_html=True,
        )
        if tudo_ok(checks):
            st.success("Cálculos conferidos")
        else:
            st.error("Há divergência na conferência")
        if fontes_comparacao is not None:
            st.caption(f"Referência da meta: {fontes_comparacao.referencia:%d/%m/%Y}")
        elif erro_comparacao:
            st.caption(f"Comparação indisponível: {erro_comparacao}")

        st.markdown("### Filtros")
        st.caption("Em branco, o filtro considera todos os valores.")
        cidades = st.multiselect("Cidade", _opcoes(faturamento["CIDADE"]), key=f"cid_{fid}", placeholder="Todas")
        codigos = st.multiselect("COD_GRUPO", _opcoes_codigo(faturamento["COD_GRUPO"]), key=f"grp_{fid}", placeholder="Todos")
        classes = st.multiselect("CLASSE_RUBRICA", _opcoes(faturamento["CLASSE_RUBRICA"]), key=f"cla_{fid}", placeholder="Todas")
        grupos = st.multiselect("GRUPO_RUBRICA", _opcoes(faturamento["GRUPO_RUBRICA"]), key=f"gru_{fid}", placeholder="Todos")
        descricoes = st.multiselect("DESCRICAO_RUBRICA", _opcoes(faturamento["DESCRICAO_RUBRICA"]), key=f"des_{fid}", placeholder="Todas")
        if st.button("Limpar filtros", use_container_width=True):
            st.session_state.fid += 1
            st.rerun()

    recorte = aplicar_filtros(
        faturamento,
        cidades=cidades,
        codigos_grupo=codigos,
        classes=classes,
        grupos=grupos,
        descricoes=descricoes,
    )
    filtros_texto = _textos_filtro(cidades, codigos, classes, grupos, descricoes)
    ok_recorte, texto_recorte = fechar_recorte(recorte)
    filtros_comparacao = {
        "cidades": cidades,
        "codigos": codigos,
        "classes": classes,
        "grupos": grupos,
        "descricoes": descricoes,
        "todas_classes": _opcoes(faturamento["CLASSE_RUBRICA"]),
        "todos_grupos": _opcoes(faturamento["GRUPO_RUBRICA"]),
    }

    colunas = st.columns(len(ABAS))
    for coluna, nome in zip(colunas, ABAS):
        ativo = st.session_state.aba == nome
        if coluna.button(nome, key=f"aba_{nome}", use_container_width=True, type="primary" if ativo else "secondary"):
            st.session_state.aba = nome
            st.rerun()

    if not ok_recorte:
        aviso(texto_recorte, "erro")
    if erro_comparacao:
        aviso(f"Comparação com a meta indisponível: {erro_comparacao}", "erro")

    prefixo = f"{fid}_{token}"
    aba = st.session_state.aba
    if aba == "Visão geral":
        pagina_visao(recorte, meta_base, checks, filtros_texto, prefixo, fontes_comparacao=fontes_comparacao, filtros_comparacao=filtros_comparacao)
    elif aba == "Cidades":
        pagina_cidades(recorte, filtros_texto, prefixo, fontes_comparacao=fontes_comparacao, filtros_comparacao=filtros_comparacao)
    elif aba == "COD_GRUPO":
        pagina_grupos(recorte, filtros_texto, prefixo, fontes_comparacao=fontes_comparacao, filtros_comparacao=filtros_comparacao)
    else:
        pagina_rubricas(recorte, filtros_texto, prefixo, fontes_comparacao=fontes_comparacao, filtros_comparacao=filtros_comparacao)


if __name__ == "__main__":
    main()
