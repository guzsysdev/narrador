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
import threading
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from motorTts import ConfiguracaoVoz, MotorNarracao, fConfigurarLogging, sVozPadrao

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
    lForcarCpu: bool = False


# Estado dos jobs em memória (processo único, adequado para uso local/pessoal).
oJobs: dict[str, dict] = {}
oFilaJobs: "queue.Queue[str]" = queue.Queue()
oMotor: Optional[MotorNarracao] = None
oLockMotor = threading.Lock()


def foObterMotor(plForcarCpu: bool) -> MotorNarracao:
    """Carrega o modelo uma única vez e reutiliza entre jobs (evita recarregar
    o VoxCPM2 a cada geração, o que seria lento)."""
    global oMotor
    with oLockMotor:
        if oMotor is None:
            oMotor = MotorNarracao(plForcarCpu=plForcarCpu)
            oMotor.fCarregarModelo()
    return oMotor


def fProcessarFilaJobs() -> None:
    """Worker único: processa um job por vez para não estourar VRAM com
    gerações concorrentes."""
    while True:
        sJobId = oFilaJobs.get()
        oJob = oJobs[sJobId]
        try:
            oJob["sStatus"] = "processando"
            oMotorLocal = foObterMotor(oJob["lForcarCpu"])

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
            )
            oJob["sCaminhoSaida"] = sCaminhoSaida
            oJob["sStatus"] = "concluido"
        except Exception as oErro:
            oLogger.exception("Falha ao gerar narração do job %s", sJobId)
            oJob["sStatus"] = "erro"
            oJob["sErro"] = str(oErro)
        finally:
            oFilaJobs.task_done()


oThreadWorker = threading.Thread(target=fProcessarFilaJobs, daemon=True)
oThreadWorker.start()


@oApp.post("/api/gerar")
def fPostGerar(poRequisicao: RequisicaoGeracao) -> dict:
    if not poRequisicao.sTexto.strip():
        raise HTTPException(status_code=400, detail="Texto da narração vazio.")

    sJobId = str(uuid.uuid4())
    oJobs[sJobId] = {
        "sStatus": "na_fila",
        "sTexto": poRequisicao.sTexto,
        "sNomeArquivo": poRequisicao.sNomeArquivo,
        "sVoz": poRequisicao.sVoz,
        "nVelocidade": poRequisicao.nVelocidade,
        "nTom": poRequisicao.nTom,
        "nSeed": poRequisicao.nSeed,
        "lForcarCpu": poRequisicao.lForcarCpu,
        "iTrechoAtual": 0,
        "iTotalTrechos": 0,
    }
    oFilaJobs.put(sJobId)
    oLogger.info("Job %s adicionado à fila.", sJobId)
    return {"sJobId": sJobId}


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
