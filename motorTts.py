"""
Motor de geração de narração de vídeo usando VoxCPM2 (TTS open-source).

Repositório: https://github.com/OpenBMB/VoxCPM
Checkpoint:  openbmb/VoxCPM2 (pacote pip: voxcpm)

Notação húngara obrigatória em todos os identificadores (ver CLAUDE.md).
"""

from __future__ import annotations

import logging
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

sLoggerNome = "narrador.motor"
oLogger = logging.getLogger(sLoggerNome)

# Descrições de voz padrão (Voice Design, sem áudio de referência), usadas
# quando nenhuma outra é informada e nas prévias de escolha de voz.
sVozPadrao = (
    "homem, 40-50 anos, voz autoritária e confiante, tom profissional e "
    "envolvente, ideal para apresentação corporativa"
)
sVozPadraoMasculina = sVozPadrao
sVozPadraoFeminina = (
    "mulher, 30-40 anos, voz confiante e envolvente, tom profissional e "
    "caloroso, ideal para apresentação corporativa"
)

# Frases curtas usadas para gerar uma prévia de voz antes de rodar a narração completa.
sTextoPreviaMasculina = "Olá, eu serei o seu narrador."
sTextoPreviaFeminina = "Olá, eu serei a sua narradora."


def fConfigurarLogging(pnNivel: int = logging.INFO) -> None:
    """Configura o formato padrão de logging do projeto."""
    logging.basicConfig(
        level=pnNivel,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def fFixarSeed(piSeed: int) -> None:
    """Fixa a seed do RNG global (torch/numpy/random).

    O VoxCPM2 não expõe um parâmetro "seed" em generate() — a geração é
    estocástica (diffusion). Para manter o mesmo timbre de voz entre trechos,
    fixamos a seed global antes de cada chamada em vez de passá-la ao modelo.
    """
    import random

    import numpy as np
    import torch

    random.seed(piSeed)
    np.random.seed(piSeed)
    torch.manual_seed(piSeed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(piSeed)


def fsDetectarDispositivo(plForcarCpu: bool = False) -> str:
    """Detecta se há GPU CUDA disponível; caso contrário, faz fallback para CPU."""
    if plForcarCpu:
        oLogger.warning("Uso de CPU forçado — a geração será significativamente mais lenta.")
        return "cpu"

    try:
        import torch
    except ImportError as oErro:
        raise RuntimeError(
            "PyTorch não está instalado. Rode: pip install -r requirements.txt"
        ) from oErro

    if torch.cuda.is_available():
        sNomeGpu = torch.cuda.get_device_name(0)
        oLogger.info("GPU CUDA detectada: %s", sNomeGpu)
        return "cuda"

    oLogger.warning(
        "Nenhuma GPU CUDA detectada — usando CPU. Para narrações longas "
        "(vídeos de vários minutos) isso pode ser bastante lento."
    )
    return "cpu"


def faDividirTexto(psTexto: str, piTamanhoMaximo: int = 350) -> list[str]:
    """Divide o texto da narração em trechos, um por linha do roteiro.

    Necessário porque o VoxCPM2 é pensado para gerar frase/parágrafo por vez;
    gerar 10 minutos de narração em uma única chamada tende a degradar
    qualidade e estabilidade. Cada linha do roteiro normalmente já representa
    um "beat" da narração (uma ação de tela em um passo a passo), então é
    tratada como um trecho próprio — isso preserva o ritmo/pausas que o autor
    do roteiro já pensou, em vez de reagrupar por contagem de caracteres e
    misturar beats diferentes num mesmo trecho. Uma linha só é subdividida por
    sentença (via _faDividirPorSentenca) se ela sozinha ultrapassar
    piTamanhoMaximo caracteres. Cada trecho é depois gerado com a mesma
    descrição de voz e a mesma seed para manter o timbre consistente.
    """
    aLinhas = [sLinha.strip() for sLinha in psTexto.splitlines() if sLinha.strip()]
    aTrechos: list[str] = []

    for sLinha in aLinhas:
        if len(sLinha) <= piTamanhoMaximo:
            aTrechos.append(sLinha)
        else:
            aTrechos.extend(_faDividirPorSentenca(sLinha, piTamanhoMaximo))

    return aTrechos


def _faDividirPorSentenca(psTexto: str, piTamanhoMaximo: int) -> list[str]:
    """Fallback: divide uma linha longa demais por sentença, agrupando
    sentenças consecutivas até o tamanho máximo permitido."""
    aSentencas = re.split(r"(?<=[.!?])\s+", psTexto.strip())
    aTrechos: list[str] = []
    sTrechoAtual = ""

    for sSentenca in aSentencas:
        sSentenca = sSentenca.strip()
        if not sSentenca:
            continue
        if len(sTrechoAtual) + len(sSentenca) + 1 <= piTamanhoMaximo:
            sTrechoAtual = f"{sTrechoAtual} {sSentenca}".strip()
        else:
            if sTrechoAtual:
                aTrechos.append(sTrechoAtual)
            sTrechoAtual = sSentenca

    if sTrechoAtual:
        aTrechos.append(sTrechoAtual)

    return aTrechos


def faAplicarVelocidadeTom(paAudio, pnTaxaAmostragem: int, pnVelocidade: float, pnTom: float):
    """Ajusta velocidade (time-stretch) e tom (pitch-shift) do áudio gerado.

    Aplicado como pós-processamento porque a chamada de geração do VoxCPM2
    não expõe controles diretos de velocidade/tom — apenas texto, descrição
    de voz e seed.
    """
    aAudioProcessado = paAudio

    if pnVelocidade and pnVelocidade != 1.0:
        import librosa

        aAudioProcessado = librosa.effects.time_stretch(aAudioProcessado, rate=pnVelocidade)

    if pnTom and pnTom != 0.0:
        import librosa

        aAudioProcessado = librosa.effects.pitch_shift(
            aAudioProcessado, sr=pnTaxaAmostragem, n_steps=pnTom
        )

    return aAudioProcessado


def fSalvarWav(paAudio, pnTaxaAmostragem: int, psCaminho: str) -> None:
    """Salva um array de áudio em WAV 16-bit PCM."""
    import soundfile as sf

    sf.write(psCaminho, paAudio, pnTaxaAmostragem, subtype="PCM_16")


def fConcatenarWavs(
    paCaminhos: list[Path], poCaminhoSaida: Path, pnSilencioEntreTrechos: float = 0.35
) -> None:
    """Concatena vários WAVs (mesmo formato) em um único arquivo final.

    Insere um pequeno silêncio entre trechos: evita cortes secos/cliques na
    junção e dá uma pausa natural entre os "beats" da narração (cada trecho
    corresponde a uma linha do roteiro, ex.: uma ação de tela).
    """
    with wave.open(str(paCaminhos[0]), "rb") as oPrimeiro:
        oParametros = oPrimeiro.getparams()

    iAmostrasSilencio = int(oParametros.framerate * pnSilencioEntreTrechos)
    bSilencio = b"\x00" * (iAmostrasSilencio * oParametros.sampwidth * oParametros.nchannels)

    with wave.open(str(poCaminhoSaida), "wb") as oSaida:
        oSaida.setparams(oParametros)
        for iIndice, oCaminho in enumerate(paCaminhos):
            with wave.open(str(oCaminho), "rb") as oEntrada:
                oSaida.writeframes(oEntrada.readframes(oEntrada.getnframes()))
            if iIndice < len(paCaminhos) - 1:
                oSaida.writeframes(bSilencio)


@dataclass
class ConfiguracaoVoz:
    """Parâmetros ajustáveis de geração de voz."""

    sDescricaoVoz: str = sVozPadrao
    nVelocidade: float = 1.0  # 1.0 = velocidade normal
    nTom: float = 0.0  # semitons de ajuste de pitch (0 = tom original)
    nSeed: int = 42  # mesma seed em todos os trechos -> timbre consistente


class MotorNarracao:
    """Encapsula o carregamento do VoxCPM2 e a geração de narração completa."""

    def __init__(self, psDispositivo: Optional[str] = None, plForcarCpu: bool = False) -> None:
        self.sDispositivo = psDispositivo or fsDetectarDispositivo(plForcarCpu)
        self.oModel = None  # carregado sob demanda em fCarregarModelo()
        self.nTaxaAmostragem = 48000

    def fCarregarModelo(self, psCheckpoint: str = "openbmb/VoxCPM2") -> None:
        """Carrega o modelo VoxCPM2 de forma otimizada para o dispositivo detectado."""
        try:
            from voxcpm import VoxCPM
        except ImportError as oErro:
            raise RuntimeError(
                "Pacote 'voxcpm' não instalado. Rode: pip install voxcpm"
            ) from oErro

        oLogger.info("Carregando modelo %s em '%s'...", psCheckpoint, self.sDispositivo)
        self.oModel = VoxCPM.from_pretrained(psCheckpoint, load_denoiser=False)
        oLogger.info("Modelo carregado com sucesso.")

    def fGerarPrevia(
        self, psDescricaoVoz: str, psTextoPrevia: str, psCaminhoSaida: str, piSeed: int = 42
    ) -> str:
        """Gera um clipe curto de prévia para uma descrição de voz (sem
        chunking nem clonagem) — usado para escolher a voz antes de rodar a
        narração completa, que é bem mais lenta."""
        if self.oModel is None:
            raise RuntimeError("Modelo não carregado. Chame fCarregarModelo() antes.")

        fFixarSeed(piSeed)
        sTextoGeracao = f"({psDescricaoVoz}){psTextoPrevia}"
        aAudio = self.oModel.generate(text=sTextoGeracao, cfg_value=2.0)
        fSalvarWav(aAudio, self.nTaxaAmostragem, psCaminhoSaida)
        return psCaminhoSaida

    def _fGerarESalvarTrecho(
        self,
        psTexto: str,
        poConfigVoz: ConfiguracaoVoz,
        poCaminhoSaida: Path,
        psCaminhoVozReferencia: Optional[str] = None,
    ):
        """Gera um único trecho, aplica velocidade/tom e salva em WAV.

        Retorna o áudio bruto (antes de velocidade/tom) gerado — usado pelo
        chamador para criar o clipe de referência de voz quando psCaminhoVozReferencia
        for None (primeiro trecho).
        """
        if self.oModel is None:
            raise RuntimeError("Modelo não carregado. Chame fCarregarModelo() antes.")

        # Fixar a seed do RNG global não garante reprodutibilidade exata em GPU
        # (kernels CUDA não são 100% determinísticos), então "mesma seed" sozinha
        # não é suficiente para manter o mesmo timbre entre trechos. Em vez disso:
        # o primeiro trecho cria a voz do zero via Voice Design (descrição
        # textual); os demais clonam essa voz (reference_wav_path), garantindo o
        # mesmo timbre por construção, não por sorte de reprodutibilidade.
        fFixarSeed(poConfigVoz.nSeed)
        if psCaminhoVozReferencia is None:
            sTextoGeracao = f"({poConfigVoz.sDescricaoVoz}){psTexto}"
            aAudio = self.oModel.generate(text=sTextoGeracao, cfg_value=2.0)
        else:
            aAudio = self.oModel.generate(
                text=psTexto, cfg_value=2.0, reference_wav_path=psCaminhoVozReferencia
            )

        aAudioProcessado = faAplicarVelocidadeTom(
            aAudio, self.nTaxaAmostragem, poConfigVoz.nVelocidade, poConfigVoz.nTom
        )
        fSalvarWav(aAudioProcessado, self.nTaxaAmostragem, str(poCaminhoSaida))
        return aAudio

    def fGerarNarracaoCompleta(
        self,
        psTexto: str,
        poConfigVoz: ConfiguracaoVoz,
        psCaminhoSaida: str,
        pfCallbackProgresso: Optional[Callable[[int, int], None]] = None,
        piTamanhoMaximoTrecho: int = 350,
        psCaminhoVozReferencia: Optional[str] = None,
    ) -> str:
        """Gera a narração completa: divide o texto em trechos, aplica
        velocidade/tom e concatena tudo no WAV final.

        Se psCaminhoVozReferencia for informado (ex.: uma opção de voz já
        escolhida pelo usuário na prévia), todos os trechos — incluindo o
        primeiro — clonam essa voz. Caso contrário, o primeiro trecho cria a
        voz via Voice Design e os demais clonam essa mesma voz.
        """
        aTrechos = faDividirTexto(psTexto, piTamanhoMaximoTrecho)
        iTotalTrechos = len(aTrechos)
        if iTotalTrechos == 0:
            raise ValueError("Texto de narração vazio.")

        oLogger.info("Narração dividida em %d trecho(s).", iTotalTrechos)

        oCaminhoSaida = Path(psCaminhoSaida)
        oDirTemp = oCaminhoSaida.parent / f".{oCaminhoSaida.stem}_trechos"
        oDirTemp.mkdir(parents=True, exist_ok=True)
        aCaminhosTrechos: list[Path] = []
        oCaminhoVozReferenciaInterna = oDirTemp / "voz_referencia.wav"

        try:
            sCaminhoVozReferencia = psCaminhoVozReferencia
            for iIndice, sTrecho in enumerate(aTrechos, start=1):
                oCaminhoTrecho = oDirTemp / f"trecho_{iIndice:04d}.wav"
                aAudioBruto = self._fGerarESalvarTrecho(
                    sTrecho, poConfigVoz, oCaminhoTrecho, sCaminhoVozReferencia
                )
                aCaminhosTrechos.append(oCaminhoTrecho)

                if sCaminhoVozReferencia is None:
                    fSalvarWav(aAudioBruto, self.nTaxaAmostragem, str(oCaminhoVozReferenciaInterna))
                    sCaminhoVozReferencia = str(oCaminhoVozReferenciaInterna)

                if pfCallbackProgresso:
                    pfCallbackProgresso(iIndice, iTotalTrechos)
                oLogger.info("Trecho %d/%d gerado.", iIndice, iTotalTrechos)

            fConcatenarWavs(aCaminhosTrechos, oCaminhoSaida)
        finally:
            for oCaminho in aCaminhosTrechos:
                oCaminho.unlink(missing_ok=True)
            oCaminhoVozReferenciaInterna.unlink(missing_ok=True)
            oDirTemp.rmdir()

        oLogger.info("Narração completa salva em: %s", oCaminhoSaida)
        return str(oCaminhoSaida)
