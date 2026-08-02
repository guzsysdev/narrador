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
const oBotaoOpcoesVoz = document.getElementById("oBotaoOpcoesVoz");
const oStatusVozEscolhida = document.getElementById("oStatusVozEscolhida");
const oListaOpcoesVoz = document.getElementById("oListaOpcoesVoz");
const oMensagemErroPrevia = document.getElementById("oMensagemErroPrevia");

let nIntervaloPolling = null;
let nIntervaloPollingOpcoesVoz = null;
let oVozesPredefinidas = {};
const sTextoPreviaPadrao = "Olá, eu serei o seu narrador.";
const iQuantidadeOpcoesVoz = 4;

// Estado da opção de voz escolhida pelo usuário (usada como referência de
// clonagem na geração final, em vez de recriar a voz do zero).
let sJobIdVozEscolhida = null;
let iIndiceVozEscolhida = null;
let aIndicesRenderizados = [];

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

function fLimparEscolhaVoz() {
  sJobIdVozEscolhida = null;
  iIndiceVozEscolhida = null;
  aIndicesRenderizados = [];
  oListaOpcoesVoz.innerHTML = "";
  fOcultar(oStatusVozEscolhida);
  fOcultar(oMensagemErroPrevia);
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
  fLimparEscolhaVoz();
}

oSelecaoVoz.addEventListener("change", fAtualizarDescricaoVoz);

async function foPostOpcoesVoz(poPayload) {
  const oResposta = await fetch("/api/opcoes-voz", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(poPayload),
  });

  if (!oResposta.ok) {
    const oErro = await oResposta.json().catch(() => ({}));
    throw new Error(oErro.detail || "Falha ao gerar opções de voz.");
  }
  return oResposta.json();
}

async function foGetOpcoesVoz(psJobId) {
  const oResposta = await fetch(`/api/opcoes-voz/${psJobId}`);
  if (!oResposta.ok) {
    throw new Error("Falha ao consultar opções de voz.");
  }
  return oResposta.json();
}

function fEscolherVoz(psJobId, piIndice, poCard) {
  sJobIdVozEscolhida = psJobId;
  iIndiceVozEscolhida = piIndice;

  document.querySelectorAll(".oOpcaoVoz").forEach((oEl) => oEl.classList.remove("oOpcaoVozEscolhida"));
  poCard.classList.add("oOpcaoVozEscolhida");

  oStatusVozEscolhida.textContent = `✓ Voz selecionada: opção ${piIndice + 1}`;
  fMostrar(oStatusVozEscolhida);
}

function fAdicionarCardOpcaoVoz(psJobId, piIndice) {
  const oCard = document.createElement("div");
  oCard.className = "oOpcaoVoz";

  const oRotulo = document.createElement("span");
  oRotulo.textContent = `Opção ${piIndice + 1}`;

  const oAudio = document.createElement("audio");
  oAudio.controls = true;
  oAudio.src = `/api/opcoes-voz/${psJobId}/${piIndice}`;

  const oBotaoUsar = document.createElement("button");
  oBotaoUsar.type = "button";
  oBotaoUsar.textContent = "Usar esta voz";
  oBotaoUsar.addEventListener("click", () => fEscolherVoz(psJobId, piIndice, oCard));

  oCard.append(oRotulo, oAudio, oBotaoUsar);
  oListaOpcoesVoz.appendChild(oCard);
}

function fPararGeracaoOpcoesVoz() {
  clearInterval(nIntervaloPollingOpcoesVoz);
  oBotaoOpcoesVoz.disabled = false;
  oBotaoOpcoesVoz.textContent = "🎲 Gerar opções de voz";
}

function fIniciarPollingOpcoesVoz(psJobId) {
  nIntervaloPollingOpcoesVoz = setInterval(async () => {
    try {
      const oStatus = await foGetOpcoesVoz(psJobId);

      for (const iIndice of oStatus.aIndicesProntos) {
        if (!aIndicesRenderizados.includes(iIndice)) {
          aIndicesRenderizados.push(iIndice);
          fAdicionarCardOpcaoVoz(psJobId, iIndice);
        }
      }

      if (oStatus.sStatus === "processando" || oStatus.sStatus === "na_fila") {
        oBotaoOpcoesVoz.textContent = `Gerando opções... ${oStatus.iTrechoAtual}/${oStatus.iTotalTrechos}`;
      } else if (oStatus.sStatus === "concluido") {
        fPararGeracaoOpcoesVoz();
      } else if (oStatus.sStatus === "erro") {
        fPararGeracaoOpcoesVoz();
        oMensagemErroPrevia.textContent = oStatus.sErro || "Erro ao gerar opções de voz.";
        fMostrar(oMensagemErroPrevia);
      }
    } catch (oErro) {
      fPararGeracaoOpcoesVoz();
      oMensagemErroPrevia.textContent = oErro.message;
      fMostrar(oMensagemErroPrevia);
    }
  }, 1500);
}

oBotaoOpcoesVoz.addEventListener("click", async () => {
  fLimparEscolhaVoz();
  oBotaoOpcoesVoz.disabled = true;
  oBotaoOpcoesVoz.textContent = "Gerando opções... 0/" + iQuantidadeOpcoesVoz;

  const sSelecao = oSelecaoVoz.value;
  const sTextoPrevia = oVozesPredefinidas[sSelecao]?.sTextoPrevia || sTextoPreviaPadrao;

  try {
    const oResposta = await foPostOpcoesVoz({
      sDescricaoVoz: oCampoVoz.value,
      sTextoPrevia,
      iQuantidade: iQuantidadeOpcoesVoz,
    });
    fIniciarPollingOpcoesVoz(oResposta.sJobId);
  } catch (oErro) {
    fPararGeracaoOpcoesVoz();
    oMensagemErroPrevia.textContent = oErro.message;
    fMostrar(oMensagemErroPrevia);
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
    sJobIdVozEscolhida,
    iIndiceVozEscolhida,
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
