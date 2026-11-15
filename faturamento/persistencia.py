"""Persistência versionada das três bases do dashboard."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

BASES = ("economias", "faturamento", "meta")
EXTENSAO_BASE = {"economias": ".xlsx", "faturamento": ".xlsx", "meta": ".xlsx"}
LOGGER = logging.getLogger(__name__)


class ErroPersistencia(RuntimeError):
    """Falha de configuração, integridade ou concorrência no armazenamento."""


class ErroValidacaoUpload(ValueError):
    """O arquivo enviado não passou pelo validador específico da base."""


def _configuracao(nome: str, padrao: str | None = None) -> str | None:
    """Prioriza Streamlit Secrets; usa ambiente como fallback no desenvolvimento local."""
    try:
        import streamlit as st

        valor = st.secrets.get(nome)
    except Exception:
        valor = None
    if valor is not None and str(valor).strip():
        return str(valor).strip()
    valor_ambiente = os.getenv(nome)
    if valor_ambiente is not None and valor_ambiente.strip():
        return valor_ambiente.strip()
    return padrao


def _inteiro_configurado(nome: str, padrao: int) -> int:
    valor = _configuracao(nome, str(padrao))
    try:
        return max(1, int(valor))
    except (TypeError, ValueError) as exc:
        raise ErroPersistencia(f"{nome} deve ser um número inteiro positivo.") from exc


def sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def nome_seguro(nome: str, tipo: str) -> str:
    nome = Path(str(nome).replace("\\", "/")).name
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", nome).strip("._")
    if not nome:
        nome = f"{tipo}{EXTENSAO_BASE[tipo]}"
    if not Path(nome).suffix:
        nome += EXTENSAO_BASE[tipo]
    return nome[:120]


class Persistencia:
    def __init__(self) -> None:
        backend = (_configuracao("STORAGE_BACKEND", "local") or "local").lower()
        if backend not in {"local", "s3"}:
            raise ErroPersistencia("STORAGE_BACKEND deve ser local ou s3.")
        self.backend = backend
        self.max_versoes = _inteiro_configurado("MAX_VERSOES", 5)
        self.max_upload_bytes = _inteiro_configurado("MAX_UPLOAD_MB", 50) * 1024 * 1024
        self.root = Path(_configuracao("STORAGE_DIR", "./storage") or "./storage").expanduser().resolve()
        self.bucket = ""
        self.prefix = ""
        self.s3 = None
        if backend == "s3":
            self._configurar_s3()
        else:
            self._criar_diretorios()

    @property
    def local_temporal(self) -> bool:
        return self.backend == "local" and _configuracao("STORAGE_DIR") is None

    @property
    def localizacao(self) -> str:
        if self.backend == "local":
            return str(self.root)
        sufixo = f"/{self.prefix}" if self.prefix else ""
        return f"s3://{self.bucket}{sufixo}"

    def _configurar_s3(self) -> None:
        configuracao = {
            "S3_ENDPOINT": _configuracao("S3_ENDPOINT"),
            "S3_BUCKET": _configuracao("S3_BUCKET"),
            "S3_ACCESS_KEY": _configuracao("S3_ACCESS_KEY"),
            "S3_SECRET_KEY": _configuracao("S3_SECRET_KEY"),
            "S3_REGION": _configuracao("S3_REGION", "auto"),
            "S3_PREFIX": _configuracao("S3_PREFIX", "") or "",
        }
        obrigatorias = ("S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY")
        ausentes = [nome for nome in obrigatorias if not configuracao[nome]]
        if ausentes:
            raise ErroPersistencia(
                "STORAGE_BACKEND=s3 requer S3_ENDPOINT, S3_BUCKET, S3_ACCESS_KEY e S3_SECRET_KEY em st.secrets ou no ambiente local."
            )
        try:
            import boto3
            from botocore.config import Config
            from botocore.exceptions import ClientError
        except ImportError as exc:
            LOGGER.exception("Dependência boto3/botocore ausente para STORAGE_BACKEND=s3.")
            raise ErroPersistencia("STORAGE_BACKEND=s3 requer as dependências boto3 e botocore.") from exc

        try:
            endpoint = urlsplit(configuracao["S3_ENDPOINT"])
            bucket = configuracao["S3_BUCKET"]
            if endpoint.scheme != "https" or not endpoint.netloc:
                raise ErroPersistencia("S3_ENDPOINT deve ser uma URL válida com https://.")
            caminho = endpoint.path.rstrip("/")
            if caminho:
                partes_caminho = caminho.strip("/").split("/")
                if partes_caminho[-1] == bucket:
                    caminho = "/".join(partes_caminho[:-1])
                    caminho = f"/{caminho}" if caminho else ""
                else:
                    raise ErroPersistencia(
                        "S3_ENDPOINT deve apontar ao endpoint base do serviço; não inclua um caminho que não seja o bucket configurado."
                    )
            endpoint_url = urlunsplit((endpoint.scheme, endpoint.netloc, caminho, "", ""))
            config_boto = Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
            self.s3 = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=configuracao["S3_ACCESS_KEY"],
                aws_secret_access_key=configuracao["S3_SECRET_KEY"],
                region_name=configuracao["S3_REGION"] or "auto",
                config=config_boto,
            )
            self.bucket = bucket
            self.prefix = configuracao["S3_PREFIX"].strip("/")
            self.s3.head_bucket(Bucket=self.bucket)
        except ErroPersistencia:
            raise
        except ClientError as exc:
            erro = exc.response.get("Error", {})
            metadata = exc.response.get("ResponseMetadata", {})
            codigo = str(erro.get("Code", "ClientError"))
            mensagem = str(erro.get("Message", "sem detalhes do serviço"))
            request_id = str(metadata.get("RequestId", "indisponível"))
            LOGGER.error(
                "Falha ClientError ao inicializar S3/R2: código=%s mensagem=%s request_id=%s",
                codigo,
                mensagem,
                request_id,
            )
            raise ErroPersistencia(
                f"Não foi possível inicializar o armazenamento S3: {codigo}: {mensagem} (request_id={request_id})."
            ) from exc
        except Exception as exc:
            LOGGER.exception("Falha ao inicializar cliente S3/R2 (%s).", type(exc).__name__)
            raise ErroPersistencia(
                f"Não foi possível inicializar o armazenamento S3: {type(exc).__name__}: {exc}"
            ) from exc

    def _criar_diretorios(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "relatorios").mkdir(exist_ok=True)
        for tipo in BASES:
            base = self.root / tipo
            (base / "atual").mkdir(parents=True, exist_ok=True)
            (base / "historico" / "arquivadas").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validar_tipo(tipo: str) -> None:
        if tipo not in BASES:
            raise ValueError(f"Tipo de base inválido: {tipo}")

    def _s3_key(self, chave: str) -> str:
        limpa = PurePosixPath(chave)
        if limpa.is_absolute() or ".." in limpa.parts:
            raise ErroPersistencia("Chave de armazenamento inválida.")
        caminho = limpa.as_posix()
        return f"{self.prefix}/{caminho}" if self.prefix else caminho

    def _local_path(self, chave: str) -> Path:
        limpa = PurePosixPath(chave)
        if limpa.is_absolute() or ".." in limpa.parts:
            raise ErroPersistencia("Caminho de armazenamento inválido.")
        destino = (self.root / Path(*limpa.parts)).resolve()
        if self.root not in destino.parents and destino != self.root:
            raise ErroPersistencia("Caminho fora do diretório de armazenamento.")
        return destino

    def _read(self, chave: str) -> tuple[bytes | None, str | None]:
        if self.backend == "local":
            caminho = self._local_path(chave)
            if not caminho.is_file():
                return None, None
            return caminho.read_bytes(), None
        try:
            resposta = self.s3.get_object(Bucket=self.bucket, Key=self._s3_key(chave))
            return resposta["Body"].read(), resposta.get("ETag")
        except Exception as exc:
            codigo = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if codigo in {"NoSuchKey", "404", "NotFound"}:
                return None, None
            raise ErroPersistencia(f"Falha ao ler objeto do armazenamento ({type(exc).__name__}).") from exc

    def _write_atomic(
        self,
        chave: str,
        conteudo: bytes,
        *,
        if_match: str | None = None,
        if_none_match: bool = False,
    ) -> str | None:
        if self.backend == "local":
            destino = self._local_path(chave)
            destino.parent.mkdir(parents=True, exist_ok=True)
            temporario = destino.with_name(f".{destino.name}.{uuid.uuid4().hex}.tmp")
            try:
                with temporario.open("wb") as arquivo:
                    arquivo.write(conteudo)
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
                os.replace(temporario, destino)
            finally:
                temporario.unlink(missing_ok=True)
            return None

        parametros = {"Bucket": self.bucket, "Key": self._s3_key(chave), "Body": conteudo}
        if if_match:
            parametros["IfMatch"] = if_match
        elif if_none_match:
            parametros["IfNoneMatch"] = "*"
        try:
            resposta = self.s3.put_object(**parametros)
            return resposta.get("ETag")
        except Exception as exc:
            codigo = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if codigo in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
                raise ErroPersistencia("Outra sessão alterou esta base. Recarregue e tente novamente.") from exc
            raise ErroPersistencia(f"Falha ao gravar objeto no armazenamento ({type(exc).__name__}).") from exc

    def _delete(self, chave: str, *, if_match: str | None = None) -> None:
        if self.backend == "local":
            self._local_path(chave).unlink(missing_ok=True)
            return
        parametros = {"Bucket": self.bucket, "Key": self._s3_key(chave)}
        if if_match:
            parametros["IfMatch"] = if_match
        try:
            self.s3.delete_object(**parametros)
        except Exception as exc:
            raise ErroPersistencia(f"Falha ao remover objeto do armazenamento ({type(exc).__name__}).") from exc

    def _copy(self, origem: str, destino: str, *, if_match: str | None = None) -> None:
        if self.backend == "local":
            fonte = self._local_path(origem)
            alvo = self._local_path(destino)
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(fonte, alvo)
            return
        argumentos = {
            "Bucket": self.bucket,
            "Key": self._s3_key(destino),
            "CopySource": {"Bucket": self.bucket, "Key": self._s3_key(origem)},
        }
        if if_match:
            argumentos["CopySourceIfMatch"] = if_match
        try:
            self.s3.copy_object(**argumentos)
        except Exception as exc:
            raise ErroPersistencia(f"Falha ao versionar objeto no armazenamento ({type(exc).__name__}).") from exc

    def _key_atual(self, tipo: str) -> str:
        return f"{tipo}/atual/{tipo}{EXTENSAO_BASE[tipo]}"

    def _key_metadata(self, tipo: str) -> str:
        return f"{tipo}/metadata.json"

    def _get_metadata(self, tipo: str) -> tuple[dict, str | None]:
        conteudo, etag = self._read(self._key_metadata(tipo))
        if conteudo is None:
            return {"tipo": tipo, "atual": None, "versoes": [], "eventos": []}, None
        try:
            dados = json.loads(conteudo.decode("utf-8"))
            dados.setdefault("versoes", [])
            dados.setdefault("eventos", [])
            return dados, etag
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ErroPersistencia("O metadata.json da base está corrompido.") from exc

    def _save_metadata(self, tipo: str, dados: dict, etag: str | None) -> str | None:
        conteudo = json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8")
        return self._write_atomic(
            self._key_metadata(tipo),
            conteudo,
            if_match=etag if self.backend == "s3" else None,
            if_none_match=self.backend == "s3" and etag is None,
        )

    def _set_validation_status(self, tipo: str, metadata: dict, etag: str | None, status: str) -> None:
        atual = metadata.get("atual")
        if not atual or atual.get("status_validacao") == status:
            return
        atual["status_validacao"] = status
        for versao in metadata.get("versoes", []):
            if versao.get("id") == atual.get("id"):
                versao["status_validacao"] = status
                break
        metadata["eventos"].append(
            {"data_hora": agora_iso(), "evento": "revalidação", "version_id": atual.get("id"), "status": status}
        )
        metadata["eventos"] = metadata["eventos"][-100:]
        self._save_metadata(tipo, metadata, etag)

    @contextmanager
    def _lock(self, tipo: str):
        if self.backend == "s3":
            yield
            return
        try:
            from filelock import FileLock

            with FileLock(str(self.root / tipo / ".lock"), timeout=30):
                yield
        except ImportError as exc:
            raise ErroPersistencia("Dependência filelock ausente; instale requirements.txt.") from exc

    def _gravar_relatorio(self, tipo: str, hash_arquivo: str, status: str, detalhe: str) -> None:
        momento = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        nome = f"relatorios/{tipo}/{momento}_{hash_arquivo[:8]}"
        registro = {
            "tipo": tipo,
            "data_hora": agora_iso(),
            "hash_curto": hash_arquivo[:8],
            "status": status,
            "detalhe": detalhe[:1000],
        }
        self._write_atomic(f"{nome}.json", json.dumps(registro, ensure_ascii=False, indent=2).encode("utf-8"))
        buffer = io.StringIO(newline="")
        escritor = csv.DictWriter(buffer, fieldnames=list(registro))
        escritor.writeheader()
        escritor.writerow(registro)
        self._write_atomic(f"{nome}.csv", buffer.getvalue().encode("utf-8-sig"))

    def _version_key(self, tipo: str, versao_id: str, nome: str) -> str:
        return f"{tipo}/historico/{versao_id}/{nome}"

    def _local_commit(self, tipo: str, nome: str, conteudo: bytes, metadata: dict, metadata_etag: str | None) -> None:
        atual_dir = f"{tipo}/atual"
        staging_dir = f"{tipo}/.staging-{uuid.uuid4().hex}"
        backup_dir = f"{tipo}/.rollback-{uuid.uuid4().hex}"
        stage_file = f"{staging_dir}/{tipo}{EXTENSAO_BASE[tipo]}"
        actual_file = self._key_atual(tipo)
        stage_path = self._local_path(stage_file)
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        stage_path.write_bytes(conteudo)
        actual_path = self._local_path(actual_file)
        backup_path = self._local_path(backup_dir)
        stage_dir_path = self._local_path(staging_dir)
        atual_dir_path = self._local_path(atual_dir)
        try:
            if atual_dir_path.exists():
                os.replace(atual_dir_path, backup_path)
            os.replace(stage_dir_path, atual_dir_path)
            self._save_metadata(tipo, metadata, metadata_etag)
        except Exception:
            if atual_dir_path.exists():
                shutil.rmtree(atual_dir_path, ignore_errors=True)
            if backup_path.exists():
                os.replace(backup_path, atual_dir_path)
            raise
        finally:
            shutil.rmtree(stage_dir_path, ignore_errors=True)
            shutil.rmtree(backup_path, ignore_errors=True)

    def _archive_excess(self, tipo: str, metadata: dict, metadata_etag: str | None) -> None:
        antigas = [v for v in metadata["versoes"] if not v.get("arquivada") and v.get("id") != (metadata.get("atual") or {}).get("id")]
        antigas.sort(key=lambda version: version.get("data_hora", ""), reverse=True)
        atual = metadata.get("atual") is not None
        max_historicas = max(0, self.max_versoes - int(atual))
        for version in antigas[max_historicas:]:
            if self.backend == "local":
                origem = self._local_path(version["storage_key"])
                destino_key = f"{tipo}/historico/arquivadas/{version['id']}/{version['nome_seguro']}"
                destino = self._local_path(destino_key)
                destino.parent.mkdir(parents=True, exist_ok=True)
                if origem.exists():
                    os.replace(origem, destino)
                version["storage_key"] = destino_key
            else:
                destino_key = f"{tipo}/historico/arquivadas/{version['id']}/{version['nome_seguro']}"
                self._copy(version["storage_key"], destino_key)
                version["storage_key"] = destino_key
                self._delete(f"{tipo}/historico/{version['id']}/{version['nome_seguro']}")
            version["arquivada"] = True
        self._save_metadata(tipo, metadata, metadata_etag)

    def save_upload(
        self,
        tipo: str,
        conteudo: bytes,
        nome_original: str,
        *,
        aba: str | None,
        validar: Callable[[bytes], dict],
        autor: str | None = None,
        acao: str = "upload",
        origem_versao: str | None = None,
    ) -> dict:
        self._validar_tipo(tipo)
        assinatura = sha256(conteudo)
        nome = nome_seguro(nome_original, tipo)
        if len(conteudo) > self.max_upload_bytes:
            detalhe = f"Arquivo excede o limite configurado de {self.max_upload_bytes // (1024 * 1024)} MB."
            self._gravar_relatorio(tipo, assinatura, "inválida", detalhe)
            raise ErroValidacaoUpload(detalhe)
        try:
            resultado_validacao = validar(conteudo)
        except Exception as exc:
            detalhe = str(exc) or type(exc).__name__
            self._gravar_relatorio(tipo, assinatura, "inválida", detalhe)
            raise ErroValidacaoUpload(detalhe) from exc

        with self._lock(tipo):
            metadata, metadata_etag = self._get_metadata(tipo)
            atual = metadata.get("atual")
            atual_bytes, atual_etag = self._read(self._key_atual(tipo))
            if atual and atual.get("sha256") == assinatura and atual_bytes is not None and sha256(atual_bytes) == assinatura:
                agora = agora_iso()
                atual["ultimo_reupload"] = agora
                atual["quantidade_reuploads"] = int(atual.get("quantidade_reuploads", 0)) + 1
                atual["status_validacao"] = "Válida"
                metadata["eventos"].append({"data_hora": agora, "evento": "reupload sem alteração", "sha256_curto": assinatura[:8]})
                metadata["eventos"] = metadata["eventos"][-100:]
                self._save_metadata(tipo, metadata, metadata_etag)
                self._gravar_relatorio(tipo, assinatura, "válida", "Reupload sem alteração; histórico não duplicado.")
                return {
                    "alterada": False,
                    "versao_anterior": False,
                    "data_hora": agora,
                    "sha256": assinatura,
                    "validacao": resultado_validacao,
                }

            agora = agora_iso()
            momento = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            version_id = f"{momento}_{assinatura}"
            storage_key = self._version_key(tipo, version_id, nome)
            if self.backend == "local":
                self._write_atomic(storage_key, conteudo, if_none_match=True)
            else:
                self._write_atomic(storage_key, conteudo, if_none_match=True)

            versao = {
                "id": version_id,
                "nome_original": nome_original[:240],
                "nome_seguro": nome,
                "aba": aba or resultado_validacao.get("aba"),
                "data_hora": agora,
                "sha256": assinatura,
                "tamanho_bytes": len(conteudo),
                "autor": autor,
                "status_validacao": "Válida",
                "arquivada": False,
                "storage_key": storage_key,
                "acao": acao,
                "origem_versao": origem_versao,
            }
            metadata["versoes"].append(versao)
            metadata["atual"] = {**versao, "actual_key": self._key_atual(tipo)}
            metadata["eventos"].append(
                {"data_hora": agora, "evento": acao, "version_id": version_id, "sha256_curto": assinatura[:8]}
            )
            metadata["eventos"] = metadata["eventos"][-100:]

            if self.backend == "local":
                self._local_commit(tipo, nome, conteudo, metadata, metadata_etag)
            else:
                old_etag = (atual or {}).get("actual_etag")
                new_etag = self._write_atomic(
                    self._key_atual(tipo),
                    conteudo,
                    if_match=old_etag,
                    if_none_match=old_etag is None,
                )
                metadata["atual"]["actual_etag"] = new_etag
                try:
                    metadata_etag = self._save_metadata(tipo, metadata, metadata_etag)
                except Exception:
                    try:
                        if atual_bytes is None:
                            self._delete(self._key_atual(tipo), if_match=new_etag)
                        else:
                            self._write_atomic(self._key_atual(tipo), atual_bytes, if_match=new_etag)
                    except Exception:
                        pass
                    raise

            self._gravar_relatorio(tipo, assinatura, "válida", "Upload validado e persistido.")
            metadata_etag, = (self._read(self._key_metadata(tipo))[1],)
            self._archive_excess(tipo, metadata, metadata_etag)
            return {
                "alterada": True,
                "versao_anterior": atual is not None,
                "data_hora": agora,
                "sha256": assinatura,
                "validacao": resultado_validacao,
            }

    def load_current(self, tipo: str, validar: Callable[[bytes], dict]) -> dict:
        self._validar_tipo(tipo)
        with self._lock(tipo):
            metadata, metadata_etag = self._get_metadata(tipo)
            atual = metadata.get("atual")
            if not atual:
                return {"status": "Ausente", "conteudo": None, "metadata": metadata}
            conteudo, _ = self._read(self._key_atual(tipo))
            if conteudo is None or sha256(conteudo) != atual.get("sha256"):
                self._set_validation_status(tipo, metadata, metadata_etag, "Corrompida")
                self._gravar_relatorio(tipo, str(atual.get("sha256", "")), "corrompida", "Arquivo ausente ou hash divergente do metadata.")
                return {"status": "Corrompida", "conteudo": None, "metadata": atual}
            try:
                resultado = validar(conteudo)
            except Exception as exc:
                self._set_validation_status(tipo, metadata, metadata_etag, "Com erro")
                self._gravar_relatorio(tipo, str(atual.get("sha256", "")), "com erro", str(exc))
                return {"status": "Com erro", "conteudo": None, "metadata": atual, "erro": str(exc)[:1000]}
            self._set_validation_status(tipo, metadata, metadata_etag, "Válida")
            return {"status": "Válida", "conteudo": conteudo, "metadata": atual, "validacao": resultado}

    def current_info(self, tipo: str) -> dict:
        """Retorna metadados seguros para a interface, sem conteúdo ou hash completo."""
        self._validar_tipo(tipo)
        metadata, _ = self._get_metadata(tipo)
        atual = metadata.get("atual")
        if not atual:
            ultimo_evento = (metadata.get("eventos") or [{}])[-1]
            removida = ultimo_evento.get("evento") == "remoção"
            return {"status": "Ausente", "removida": removida, "versao_id": None}
        return {
            "status": atual.get("status_validacao", "Válida"),
            "removida": False,
            "versao_id": atual.get("id"),
            "nome_original": atual.get("nome_original", ""),
            "data_hora": atual.get("data_hora"),
            "hash_curto": str(atual.get("sha256", ""))[:8],
            "tamanho_bytes": int(atual.get("tamanho_bytes", 0)),
            "aba": atual.get("aba"),
        }

    def list_versions(self, tipo: str) -> list[dict]:
        self._validar_tipo(tipo)
        metadata, _ = self._get_metadata(tipo)
        atual_id = (metadata.get("atual") or {}).get("id")
        versoes = []
        for versao in metadata.get("versoes", []):
            versoes.append(
                {
                    "id": versao["id"],
                    "data_hora": versao.get("data_hora"),
                    "sha256_curto": str(versao.get("sha256", ""))[:8],
                    "status": "Removida" if versao.get("status") == "removida" else versao.get("status_validacao", "Com erro"),
                    "atual": versao["id"] == atual_id,
                    "arquivada": bool(versao.get("arquivada")),
                    "removida": versao.get("status") == "removida",
                    "nome_original": versao.get("nome_original", ""),
                }
            )
        return sorted(versoes, key=lambda version: version.get("data_hora") or "", reverse=True)

    def restore_version(self, tipo: str, version_id: str, validar: Callable[[bytes], dict], autor: str | None = None) -> dict:
        self._validar_tipo(tipo)
        metadata, _ = self._get_metadata(tipo)
        versao = next((v for v in metadata.get("versoes", []) if v.get("id") == version_id), None)
        if not versao:
            raise ErroPersistencia("A versão selecionada não foi encontrada no histórico.")
        conteudo, _ = self._read(versao["storage_key"])
        if conteudo is None or sha256(conteudo) != versao.get("sha256"):
            raise ErroPersistencia("A versão do histórico está ausente ou corrompida.")
        return self.save_upload(
            tipo,
            conteudo,
            versao.get("nome_original") or versao["nome_seguro"],
            aba=versao.get("aba"),
            validar=validar,
            autor=autor,
            acao="restauração",
            origem_versao=version_id,
        )

    def remove_current(self, tipo: str) -> None:
        self._validar_tipo(tipo)
        with self._lock(tipo):
            metadata, metadata_etag = self._get_metadata(tipo)
            atual = metadata.get("atual")
            if not atual:
                return
            conteudo, atual_etag = self._read(self._key_atual(tipo))
            if conteudo is not None:
                version_id = f"{atual['id']}_removida"
                chave_removida = self._version_key(tipo, version_id, atual["nome_seguro"])
                if self.backend == "local":
                    origem = self._local_path(self._key_atual(tipo))
                    destino = self._local_path(chave_removida)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(origem, destino)
                else:
                    self._copy(self._key_atual(tipo), chave_removida, if_match=atual_etag)
                removida = {**atual, "id": version_id, "storage_key": chave_removida, "status": "removida", "arquivada": False}
                metadata["versoes"].append(removida)
            metadata["atual"] = None
            metadata["eventos"].append({"data_hora": agora_iso(), "evento": "remoção", "version_id": atual.get("id")})
            metadata_etag = self._save_metadata(tipo, metadata, metadata_etag)
            if self.backend == "local":
                shutil.rmtree(self._local_path(f"{tipo}/atual"), ignore_errors=True)
                (self._local_path(f"{tipo}/atual")).mkdir(parents=True, exist_ok=True)
            else:
                self._delete(self._key_atual(tipo), if_match=atual_etag)
            self._archive_excess(tipo, metadata, metadata_etag)

    def configuration_status(self) -> dict:
        return {
            "backend": self.backend,
            "localizacao": self.localizacao,
            "max_versoes": self.max_versoes,
            "max_upload_mb": self.max_upload_bytes // (1024 * 1024),
            "aviso_efemero": self.local_temporal,
        }


def criar_persistencia() -> Persistencia:
    return Persistencia()