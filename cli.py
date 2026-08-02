"""
Interface de linha de comando para gerar narração de vídeo com VoxCPM2.

Exemplo de uso:
    python cli.py --texto "Bem-vindos à apresentação." --saida narracao.wav
    python cli.py --arquivo-texto roteiro.txt --saida narracao.wav --velocidade 1.1
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from motorTts import (
    ConfiguracaoVoz,
    MotorNarracao,
    fConfigurarLogging,
    sTextoPreviaFeminina,
    sTextoPreviaMasculina,
    sVozPadrao,
    sVozPadraoFeminina,
    sVozPadraoMasculina,
)

oLogger = logging.getLogger("narrador.cli")

# Texto de exemplo usado quando nenhum texto/arquivo é informado (requisito 7 do CLAUDE.md).
sTextoExemplo = (
    "Bem-vindos a esta apresentação. Hoje vamos explorar como a inteligência "
    "artificial está transformando a forma como criamos conteúdo em vídeo. "
    "Prepare-se para uma jornada de descobertas e inovação."
)


def fsLerTexto(poArgs: argparse.Namespace) -> str:
    """Resolve o texto da narração a partir dos argumentos de linha de comando."""
    if poArgs.sArquivoTexto:
        oCaminho = Path(poArgs.sArquivoTexto)
        if not oCaminho.exists():
            raise FileNotFoundError(f"Arquivo de texto não encontrado: {oCaminho}")
        return oCaminho.read_text(encoding="utf-8")

    if poArgs.sTexto:
        return poArgs.sTexto

    oLogger.info("Nenhum texto informado — usando texto de exemplo.")
    return sTextoExemplo


def fCriarParser() -> argparse.ArgumentParser:
    oParser = argparse.ArgumentParser(
        description="Gera narração em áudio usando VoxCPM2 (TTS open-source)."
    )
    oParser.add_argument("--texto", dest="sTexto", type=str, default=None, help="Texto da narração.")
    oParser.add_argument(
        "--arquivo-texto",
        dest="sArquivoTexto",
        type=str,
        default=None,
        help="Caminho de um .txt com o texto da narração.",
    )
    oParser.add_argument(
        "--saida", dest="sSaida", type=str, default="narracao.wav", help="Nome do arquivo WAV de saída."
    )
    oParser.add_argument(
        "--voz",
        dest="sVoz",
        type=str,
        default=sVozPadrao,
        help="Descrição da voz (Voice Design, sem áudio de referência).",
    )
    oParser.add_argument(
        "--velocidade", dest="nVelocidade", type=float, default=1.0, help="Fator de velocidade (1.0 = normal)."
    )
    oParser.add_argument(
        "--tom", dest="nTom", type=float, default=0.0, help="Ajuste de tom em semitons (0 = original)."
    )
    oParser.add_argument(
        "--seed", dest="nSeed", type=int, default=42, help="Seed para manter timbre consistente entre trechos."
    )
    oParser.add_argument(
        "--tamanho-trecho",
        dest="iTamanhoTrecho",
        type=int,
        default=350,
        help="Tamanho máximo (caracteres) de cada trecho gerado.",
    )
    oParser.add_argument(
        "--cpu", dest="lCpu", action="store_true", help="Força uso de CPU mesmo se houver GPU disponível."
    )
    oParser.add_argument(
        "--previa",
        dest="sPrevia",
        choices=["masculina", "feminina", "ambas"],
        default=None,
        help=(
            "Gera só uma prévia curta da(s) voz(es) padrão e sai, sem gerar a "
            "narração completa. Salva em previa_masculina.wav / previa_feminina.wav."
        ),
    )
    return oParser


def fGerarPrevias(poMotor: MotorNarracao, psPrevia: str, piSeed: int) -> None:
    """Gera clipes curtos de prévia para escolha de voz antes da narração completa."""
    aVozes = []
    if psPrevia in ("masculina", "ambas"):
        aVozes.append(("masculina", sVozPadraoMasculina, sTextoPreviaMasculina, "previa_masculina.wav"))
    if psPrevia in ("feminina", "ambas"):
        aVozes.append(("feminina", sVozPadraoFeminina, sTextoPreviaFeminina, "previa_feminina.wav"))

    for sNome, sDescricao, sTexto, sSaida in aVozes:
        oLogger.info("Gerando prévia da voz %s...", sNome)
        poMotor.fGerarPrevia(sDescricao, sTexto, sSaida, piSeed)
        oLogger.info("Prévia salva em: %s", sSaida)


def fMain() -> int:
    fConfigurarLogging()
    oParser = fCriarParser()
    oArgs = oParser.parse_args()

    try:
        oMotor = MotorNarracao(plForcarCpu=oArgs.lCpu)
        oMotor.fCarregarModelo()

        if oArgs.sPrevia:
            fGerarPrevias(oMotor, oArgs.sPrevia, oArgs.nSeed)
            return 0

        sTexto = fsLerTexto(oArgs)

        poConfigVoz = ConfiguracaoVoz(
            sDescricaoVoz=oArgs.sVoz,
            nVelocidade=oArgs.nVelocidade,
            nTom=oArgs.nTom,
            nSeed=oArgs.nSeed,
        )

        def fExibirProgresso(piAtual: int, piTotal: int) -> None:
            nPercentual = (piAtual / piTotal) * 100
            print(f"\rGerando narração: trecho {piAtual}/{piTotal} ({nPercentual:5.1f}%)", end="", flush=True)

        oMotor.fGerarNarracaoCompleta(
            psTexto=sTexto,
            poConfigVoz=poConfigVoz,
            psCaminhoSaida=oArgs.sSaida,
            pfCallbackProgresso=fExibirProgresso,
            piTamanhoMaximoTrecho=oArgs.iTamanhoTrecho,
        )
        print()
        oLogger.info("Concluído! Arquivo salvo em: %s", oArgs.sSaida)
        return 0

    except Exception as oErro:
        oLogger.error("Falha ao gerar narração: %s", oErro)
        return 1


if __name__ == "__main__":
    sys.exit(fMain())
