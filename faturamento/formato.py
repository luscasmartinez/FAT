"""Formatação monetária e numérica em padrão brasileiro."""

from __future__ import annotations

import math


def _numero(valor: float, casas: int) -> str:
    texto = f"{abs(float(valor)):,.{casas}f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


def brl(valor: float) -> str:
    """Valor monetário completo, com sinal e centavos. Ex.: -R$ 1.234,56."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {_numero(valor, 2)}"


def compacto(valor: float) -> str:
    """Valor abreviado para cards. O valor exato continua disponível no detalhe e no tooltip."""
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    absoluto = abs(float(valor))
    sinal = "-" if valor < 0 else ""
    if absoluto >= 1_000_000_000:
        corpo = f"{absoluto / 1_000_000_000:.2f} bi"
    elif absoluto >= 1_000_000:
        corpo = f"{absoluto / 1_000_000:.2f} mi"
    elif absoluto >= 1_000:
        corpo = f"{absoluto / 1_000:.1f} mil"
    else:
        return brl(valor)
    return f"{sinal}R$ {corpo.replace('.', ',')}"


def percentual(valor: float) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    sinal = "-" if valor < 0 else ""
    return f"{sinal}{_numero(valor * 100, 2)}%"


def decimal(valor: float, casas: int = 2) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    numero = float(valor)
    sinal = "-" if numero < 0 else ""
    return sinal + _numero(numero, casas)


def inteiro(valor: float) -> str:
    if valor is None or (isinstance(valor, float) and math.isnan(valor)):
        return "—"
    sinal = "-" if valor < 0 else ""
    return sinal + f"{int(round(abs(valor))):,}".replace(",", ".")


def codigo(valor) -> str:
    if valor is None:
        return "—"
    try:
        if isinstance(valor, float) and math.isnan(valor):
            return "—"
    except TypeError:
        pass
    try:
        if valor != valor:
            return "—"
    except Exception:
        return "—"
    try:
        return str(int(valor))
    except (TypeError, ValueError):
        return str(valor)


def escala_eixo(valores) -> tuple[float, str]:
    pico = 0.0
    for valor in valores:
        if valor is None:
            continue
        pico = max(pico, abs(float(valor)))
    if pico >= 1_000_000:
        return 1_000_000.0, "milhões de R$"
    if pico >= 1_000:
        return 1_000.0, "mil R$"
    return 1.0, "R$"
