// Frontend do Narrador IA — notação húngara obrigatória (ver CLAUDE.md).

const oFormGeracao = document.getElementById("oFormGeracao");
const oBotaoGerar = document.getElementById("oBotaoGerar");

const oCampoVelocidade = document.getElementById("oVelocidade");
const oCampoTom = document.getElementById("oTom");
const oValorVelocidade = document.getElementById("oValorVelocidade");
const oValorTom = document.getElementById("oValorTom");

const oSecaoProgresso = document.getElementById("oProgresso");
const oTextoProgresso = document.getElementById("oTextoProgresso");
const oBarraPreenchimento = document.getElementById("oBarraPreenchimento");

const oSecaoResultado = document.getElementById("oResultado");
const oPlayerAudio = document.getElementById("oPlayerAudio");
const oLinkDownload = document.getElementById("oLinkDownload");

const oMensagemErro = document.getElementById("oMensagemErro");

const oSelecaoVoz = document.getElementById("oSelecaoVoz");
const oCampoVoz = document.getElementById("oVoz");
const oBotaoPrevia = document.getElementById("oBotaoPrevia");
const oPlayerPrevia = document.getElementById("oPlayerPrevia");
const oMensagemErroPrevia = document.getElementById("oMensagemErroPrevia");

let nIntervaloPolling = null;
let nIntervaloPollingPrevia = null;
let oVozesPredefinidas = {};
const sTextoPreviaPadrao = "Olá, eu serei o seu narrador.";

function fAtualizarRotulos() {
  oValorVelocidade.textContent = `${parseFloat(oCampoVelocidade.value).toFixed(2)}x`;
  oValorTom.textContent = `${oCampoTom.value} semitons`;
}

oCampoVelocidade.addEventListener("input", fAtualizarRotulos);
oCampoTom.addEventListener("input", fAtualizarRotulos);
fAtualizarRotulos();

function fMostrar(poElemento) {
  poElemento.classList.remove("oOculto");
}

function fOcultar(poElemento) {
  poElemento.classList.add("oOculto");
}

function fExibirErro(psMensagem) {
  oMensagemErro.textContent = psMensagem;
  fMostrar(oMensagemErro);
}

async function foPostGerar(poPayload) {
  const oResposta = await fetch("/api/gerar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(poPayload),
  });

  if (!oResposta.ok) {
    const oErro = await oResposta.json().catch(() => ({}));
    throw new Error(oErro.detail || "Falha ao iniciar geração.");
  }
  return oResposta.json();
}

async function foGetProgresso(psJobId) {
  const oResposta = await fetch(`/api/progresso/${psJobId}`);
  if (!oResposta.ok) {
    throw new Error("Falha ao consultar progresso.");
  }
  return oResposta.json();
}

async function foCarregarVozesPredefinidas() {
  try {
    const oResposta = await fetch("/api/vozes");
    oVozesPredefinidas = await oResposta.json();
    fAtualizarDescricaoVoz();
  } catch (oErro) {
    fExibirErro("Não foi possível carregar as vozes predefinidas.");
  }
}

function fAtualizarDescricaoVoz() {
  const sSelecao = oSelecaoVoz.value;
  if (sSelecao === "personalizada") {
    oCampoVoz.disabled = false;
    if (!oCampoVoz.value.trim()) {
      oCampoVoz.value = oVozesPredefinidas.masculina?.sDescricao || "";
    }
  } else {
    oCampoVoz.disabled = true;
    oCampoVoz.value = oVozesPredefinidas[sSelecao]?.sDescricao || "";
  }
  fOcultar(oPlayerPrevia);
  fOcultar(oMensagemErroPrevia);
}

oSelecaoVoz.addEventListener("change", fAtualizarDescricaoVoz);

async function foPostPrevia(poPayload) {
  const oResposta = await fetch("/api/previa", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(poPayload),
  });

  if (!oResposta.ok) {
    const oErro = await oResposta.json().catch(() => ({}));
    throw new Error(oErro.detail || "Falha ao gerar prévia.");
  }
  return oResposta.json();
}

function fIniciarPollingPrevia(psJobId) {
  nIntervaloPollingPrevia = setInterval(async () => {
    try {
      const oStatus = await foGetProgresso(psJobId);

      if (oStatus.sStatus === "concluido") {
        clearInterval(nIntervaloPollingPrevia);
        oPlayerPrevia.src = `/api/download/${psJobId}`;
        fMostrar(oPlayerPrevia);
        oPlayerPrevia.play();
        oBotaoPrevia.disabled = false;
        oBotaoPrevia.textContent = "▶ Ouvir prévia desta voz";
      } else if (oStatus.sStatus === "erro") {
        clearInterval(nIntervaloPollingPrevia);
        oMensagemErroPrevia.textContent = oStatus.sErro || "Erro ao gerar prévia.";
        fMostrar(oMensagemErroPrevia);
        oBotaoPrevia.disabled = false;
        oBotaoPrevia.textContent = "▶ Ouvir prévia desta voz";
      }
    } catch (oErro) {
      clearInterval(nIntervaloPollingPrevia);
      oMensagemErroPrevia.textContent = oErro.message;
      fMostrar(oMensagemErroPrevia);
      oBotaoPrevia.disabled = false;
      oBotaoPrevia.textContent = "▶ Ouvir prévia desta voz";
    }
  }, 1500);
}

oBotaoPrevia.addEventListener("click", async () => {
  fOcultar(oMensagemErroPrevia);
  fOcultar(oPlayerPrevia);
  oBotaoPrevia.disabled = true;
  oBotaoPrevia.textContent = "Gerando prévia...";

  const sSelecao = oSelecaoVoz.value;
  const sTextoPrevia = oVozesPredefinidas[sSelecao]?.sTextoPrevia || sTextoPreviaPadrao;

  try {
    const oResposta = await foPostPrevia({
      sDescricaoVoz: oCampoVoz.value,
      sTextoPrevia,
    });
    fIniciarPollingPrevia(oResposta.sJobId);
  } catch (oErro) {
    oMensagemErroPrevia.textContent = oErro.message;
    fMostrar(oMensagemErroPrevia);
    oBotaoPrevia.disabled = false;
    oBotaoPrevia.textContent = "▶ Ouvir prévia desta voz";
  }
});

foCarregarVozesPredefinidas();

function fIniciarPolling(psJobId) {
  nIntervaloPolling = setInterval(async () => {
    try {
      const oStatus = await foGetProgresso(psJobId);

      if (oStatus.sStatus === "na_fila") {
        oTextoProgresso.textContent = "Na fila, aguardando modelo carregar...";
      } else if (oStatus.sStatus === "processando") {
        const iAtual = oStatus.iTrechoAtual;
        const iTotal = oStatus.iTotalTrechos || 1;
        const nPercentual = Math.round((iAtual / iTotal) * 100);
        oBarraPreenchimento.style.width = `${nPercentual}%`;
        oTextoProgresso.textContent = `Gerando trecho ${iAtual}/${iTotal} (${nPercentual}%)`;
      } else if (oStatus.sStatus === "concluido") {
        clearInterval(nIntervaloPolling);
        oBarraPreenchimento.style.width = "100%";
        oTextoProgresso.textContent = "Concluído!";

        const sUrlDownload = `/api/download/${psJobId}`;
        oPlayerAudio.src = sUrlDownload;
        oLinkDownload.href = sUrlDownload;

        fMostrar(oSecaoResultado);
        oBotaoGerar.disabled = false;
      } else if (oStatus.sStatus === "erro") {
        clearInterval(nIntervaloPolling);
        fExibirErro(oStatus.sErro || "Erro desconhecido na geração.");
        oBotaoGerar.disabled = false;
      }
    } catch (oErro) {
      clearInterval(nIntervaloPolling);
      fExibirErro(oErro.message);
      oBotaoGerar.disabled = false;
    }
  }, 1500);
}

oFormGeracao.addEventListener("submit", async (oEvento) => {
  oEvento.preventDefault();

  fOcultar(oMensagemErro);
  fOcultar(oSecaoResultado);
  fMostrar(oSecaoProgresso);
  oBarraPreenchimento.style.width = "0%";
  oTextoProgresso.textContent = "Enviando...";
  oBotaoGerar.disabled = true;

  const oPayload = {
    sTexto: document.getElementById("oTexto").value,
    sNomeArquivo: document.getElementById("oNomeArquivo").value || "narracao.wav",
    sVoz: document.getElementById("oVoz").value,
    nVelocidade: parseFloat(oCampoVelocidade.value),
    nTom: parseFloat(oCampoTom.value),
    nSeed: parseInt(document.getElementById("oSeed").value, 10),
  };

  try {
    const oResposta = await foPostGerar(oPayload);
    fIniciarPolling(oResposta.sJobId);
  } catch (oErro) {
    fExibirErro(oErro.message);
    oBotaoGerar.disabled = false;
    fOcultar(oSecaoProgresso);
  }
});
