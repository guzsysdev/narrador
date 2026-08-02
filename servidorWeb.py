"""
Servidor web (FastAPI) para gerar narração via VoxCPM2 com acompanhamento de
progresso em tempo real e download do WAV final.

Executar:
    uvicorn servidorWeb:oApp --reload

Depois abrir http://localhost:8000 no navegador.
"""

from __future__ import annotations

import logging
import queue
import random
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

fConfigurarLogging()
oLogger = logging.getLogger("narrador.servidor")

oApp = FastAPI(title="Narrador IA")

oDirBase = Path(__file__).parent
oDirSaidas = oDirBase / "saidas"
oDirSaidas.mkdir(exist_ok=True)

oApp.mount("/estatico", StaticFiles(directory=str(oDirBase / "static")), name="estatico")


class RequisicaoGeracao(BaseModel):
    """Corpo da requisição POST /api/gerar."""

    sTexto: str
    sNomeArquivo: str = "narracao.wav"
    sVoz: str = sVozPadrao
    nVelocidade: float = 1.0
    nTom: float = 0.0
    nSeed: int = 42
    # Se preenchidos, usa a opção de voz escolhida em /api/opcoes-voz como
    # referência de clonagem em vez de gerar a voz do zero por Voice Design.
    sJobIdVozEscolhida: Optional[str] = None
    iIndiceVozEscolhida: Optional[int] = None


class RequisicaoOpcoesVoz(BaseModel):
    """Corpo da requisição POST /api/opcoes-voz."""

    sDescricaoVoz: str
    sTextoPrevia: str = sTextoPreviaMasculina
    iQuantidade: int = 4


# Vozes pré-definidas oferecidas na interface (nome -> descrição + frase de prévia).
oVozesPredefinidas = {
    "masculina": {"sDescricao": sVozPadraoMasculina, "sTextoPrevia": sTextoPreviaMasculina},
    "feminina": {"sDescricao": sVozPadraoFeminina, "sTextoPrevia": sTextoPreviaFeminina},
}


# Estado dos jobs em memória (processo único, adequado para uso local/pessoal).
oJobs: dict[str, dict] = {}
oFilaJobs: "queue.Queue[str]" = queue.Queue()
oMotor: Optional[MotorNarracao] = None
oEventoMotorPronto = threading.Event()


def fCarregarMotorNaInicializacao() -> None:
    """Carrega o modelo VoxCPM2 assim que o servidor sobe, em vez de esperar a
    primeira geração pedida — assim, quando o link é divulgado, já está tudo
    pronto para uso imediato (sem o usuário esperar minutos na primeira prévia)."""
    global oMotor
    oLogger.info("Carregando modelo VoxCPM2 na inicialização do servidor...")
    oMotor = MotorNarracao()
    oMotor.fCarregarModelo()
    oEventoMotorPronto.set()
    oLogger.info("Modelo pronto — servidor aceitando gerações.")


@oApp.on_event("startup")
def fAoIniciarServidor() -> None:
    threading.Thread(target=fCarregarMotorNaInicializacao, daemon=True).start()


def foObterMotor() -> MotorNarracao:
    """Aguarda o carregamento (feito na inicialização) terminar, se ainda não tiver."""
    oEventoMotorPronto.wait()
    return oMotor


def fProcessarFilaJobs() -> None:
    """Worker único: processa um job por vez (narração completa ou opções de
    voz) para não estourar VRAM com gerações concorrentes."""
    while True:
        sJobId = oFilaJobs.get()
        oJob = oJobs[sJobId]
        try:
            oJob["sStatus"] = "processando"
            oMotorLocal = foObterMotor()

            if oJob["sTipo"] == "opcoes_voz":
                iQuantidade = oJob["iQuantidade"]
                for iIndice in range(iQuantidade):
                    # Seed aleatória (não fixa) em cada opção: o Voice Design é
                    # estocástico, então descrições iguais com seeds diferentes
                    # produzem vozes distintas dentro do que a descrição pede —
                    # é assim que oferecemos várias vozes reais para escolher,
                    # em vez de uma única amostra fixa que pode não soar bem.
                    nSeedAleatoria = random.randint(1, 2_000_000_000)
                    sCaminhoOpcao = str(oDirSaidas / f"{sJobId}_opcao{iIndice}.wav")
                    oMotorLocal.fGerarPrevia(
                        psDescricaoVoz=oJob["sVoz"],
                        psTextoPrevia=oJob["sTexto"],
                        psCaminhoSaida=sCaminhoOpcao,
                        piSeed=nSeedAleatoria,
                    )
                    oJob["aOpcoes"].append(
                        {"iIndice": iIndice, "nSeed": nSeedAleatoria, "sCaminho": sCaminhoOpcao}
                    )
                    oJob["iTrechoAtual"] = iIndice + 1
            else:

                def fCallback(piAtual: int, piTotal: int) -> None:
                    oJob["iTrechoAtual"] = piAtual
                    oJob["iTotalTrechos"] = piTotal

                poConfigVoz = ConfiguracaoVoz(
                    sDescricaoVoz=oJob["sVoz"],
                    nVelocidade=oJob["nVelocidade"],
                    nTom=oJob["nTom"],
                    nSeed=oJob["nSeed"],
                )
                sCaminhoSaida = str(oDirSaidas / f"{sJobId}.wav")
                oMotorLocal.fGerarNarracaoCompleta(
                    psTexto=oJob["sTexto"],
                    poConfigVoz=poConfigVoz,
                    psCaminhoSaida=sCaminhoSaida,
                    pfCallbackProgresso=fCallback,
                    psCaminhoVozReferencia=oJob.get("sCaminhoVozReferencia"),
                )
                oJob["sCaminhoSaida"] = sCaminhoSaida

            oJob["sStatus"] = "concluido"
        except Exception as oErro:
            oLogger.exception("Falha ao processar job %s", sJobId)
            oJob["sStatus"] = "erro"
            oJob["sErro"] = str(oErro)
        finally:
            oFilaJobs.task_done()


oThreadWorker = threading.Thread(target=fProcessarFilaJobs, daemon=True)
oThreadWorker.start()


@oApp.get("/api/saude")
def fGetSaude() -> dict:
    """Usado pelo notebook do Colab para só divulgar o link depois que o
    modelo terminar de carregar."""
    return {"lPronto": oEventoMotorPronto.is_set()}


@oApp.get("/api/vozes")
def fGetVozes() -> dict:
    """Vozes predefinidas (descrição + frase de prévia) para a interface."""
    return oVozesPredefinidas


@oApp.post("/api/gerar")
def fPostGerar(poRequisicao: RequisicaoGeracao) -> dict:
    if not poRequisicao.sTexto.strip():
        raise HTTPException(status_code=400, detail="Texto da narração vazio.")

    sCaminhoVozReferencia = None
    if poRequisicao.sJobIdVozEscolhida is not None and poRequisicao.iIndiceVozEscolhida is not None:
        oJobVoz = oJobs.get(poRequisicao.sJobIdVozEscolhida)
        if oJobVoz is None:
            raise HTTPException(status_code=400, detail="Job de opções de voz não encontrado.")
        aOpcoes = oJobVoz.get("aOpcoes", [])
        if not (0 <= poRequisicao.iIndiceVozEscolhida < len(aOpcoes)):
            raise HTTPException(status_code=400, detail="Índice de opção de voz inválido.")
        sCaminhoVozReferencia = aOpcoes[poRequisicao.iIndiceVozEscolhida]["sCaminho"]

    sJobId = str(uuid.uuid4())
    oJobs[sJobId] = {
        "sTipo": "narracao",
        "sStatus": "na_fila",
        "sTexto": poRequisicao.sTexto,
        "sNomeArquivo": poRequisicao.sNomeArquivo,
        "sVoz": poRequisicao.sVoz,
        "nVelocidade": poRequisicao.nVelocidade,
        "nTom": poRequisicao.nTom,
        "nSeed": poRequisicao.nSeed,
        "sCaminhoVozReferencia": sCaminhoVozReferencia,
        "iTrechoAtual": 0,
        "iTotalTrechos": 0,
    }
    oFilaJobs.put(sJobId)
    oLogger.info("Job %s (narração) adicionado à fila.", sJobId)
    return {"sJobId": sJobId}


@oApp.post("/api/opcoes-voz")
def fPostOpcoesVoz(poRequisicao: RequisicaoOpcoesVoz) -> dict:
    if not poRequisicao.sDescricaoVoz.strip():
        raise HTTPException(status_code=400, detail="Descrição da voz vazia.")
    if not (1 <= poRequisicao.iQuantidade <= 8):
        raise HTTPException(status_code=400, detail="Quantidade de opções deve ser entre 1 e 8.")

    sJobId = str(uuid.uuid4())
    oJobs[sJobId] = {
        "sTipo": "opcoes_voz",
        "sStatus": "na_fila",
        "sTexto": poRequisicao.sTextoPrevia,
        "sVoz": poRequisicao.sDescricaoVoz,
        "iQuantidade": poRequisicao.iQuantidade,
        "aOpcoes": [],
        "iTrechoAtual": 0,
        "iTotalTrechos": poRequisicao.iQuantidade,
    }
    oFilaJobs.put(sJobId)
    oLogger.info("Job %s (opções de voz, %d) adicionado à fila.", sJobId, poRequisicao.iQuantidade)
    return {"sJobId": sJobId}


@oApp.get("/api/opcoes-voz/{sJobId}")
def fGetOpcoesVoz(sJobId: str) -> dict:
    oJob = oJobs.get(sJobId)
    if oJob is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return {
        "sStatus": oJob["sStatus"],
        "iTrechoAtual": oJob.get("iTrechoAtual", 0),
        "iTotalTrechos": oJob.get("iTotalTrechos", 0),
        "aIndicesProntos": [o["iIndice"] for o in oJob.get("aOpcoes", [])],
        "sErro": oJob.get("sErro"),
    }


@oApp.get("/api/opcoes-voz/{sJobId}/{iIndice}")
def fGetOpcaoVozAudio(sJobId: str, iIndice: int) -> FileResponse:
    oJob = oJobs.get(sJobId)
    if oJob is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    aOpcoes = oJob.get("aOpcoes", [])
    if iIndice < 0 or iIndice >= len(aOpcoes):
        raise HTTPException(status_code=404, detail="Opção de voz não encontrada.")

    return FileResponse(aOpcoes[iIndice]["sCaminho"], media_type="audio/wav")


@oApp.get("/api/progresso/{sJobId}")
def fGetProgresso(sJobId: str) -> dict:
    oJob = oJobs.get(sJobId)
    if oJob is None:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return {
        "sStatus": oJob["sStatus"],
        "iTrechoAtual": oJob.get("iTrechoAtual", 0),
        "iTotalTrechos": oJob.get("iTotalTrechos", 0),
        "sErro": oJob.get("sErro"),
    }


@oApp.get("/api/download/{sJobId}")
def fGetDownload(sJobId: str) -> FileResponse:
    oJob = oJobs.get(sJobId)
    if oJob is None or oJob["sStatus"] != "concluido":
        raise HTTPException(status_code=404, detail="Arquivo ainda não disponível.")

    return FileResponse(
        oJob["sCaminhoSaida"],
        media_type="audio/wav",
        filename=oJob["sNomeArquivo"],
    )


@oApp.get("/")
def fGetIndex() -> FileResponse:
    return FileResponse(str(oDirBase / "static" / "index.html"))
