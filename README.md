# Narrador IA

> **Todos os direitos reservados.** Uso, cópia, modificação, distribuição e comercialização
> deste software são proibidos sem autorização prévia do titular dos direitos. Ver
> [LICENSE](LICENSE).

Gera narração em áudio usando [VoxCPM2](https://github.com/OpenBMB/VoxCPM) (TTS
open-source, executado localmente), com uma voz de apresentador profissional criada por
descrição de texto (*Voice Design*, sem áudio de referência). Feito para fugir dos limites
de duração das ferramentas de TTS web — narrações de vídeos longos (~10 min) são divididas
em trechos e geradas com a mesma voz/seed, depois concatenadas em um único WAV.

## Uso (via web, com GPU gratuita do Google Colab)

Geração em CPU é impraticável para narrações longas (~47s de CPU por palavra — uma
narração de 10 min pode levar quase um dia inteiro). O caminho recomendado é: o
notebook do Colab só liga o servidor (com GPU); **toda a interação real acontece na
página web** que ele expõe — escolher voz, ouvir prévia, colar o roteiro, gerar e
baixar o WAV.

[![Abrir no Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/guzsysdev/narrador/blob/prod/colab_gerar_narracao.ipynb)

1. Abra o notebook e selecione **Ambiente de execução → Alterar tipo de ambiente de
   execução → GPU (T4)**
2. **Ambiente de execução → Executar tudo** (na primeira vez, siga a célula que pede
   pra configurar o token do ngrok em Secrets — depois disso nunca mais precisa colar)
3. Aguarde a última célula imprimir uma URL e abra ela no navegador — é só isso, o
   notebook pode ficar minimizado dali em diante
4. Se a sessão do Colab cair (limite do plano grátis), volte e rode "Executar tudo"
   de novo pra gerar um novo link

Se você tiver GPU própria, dá pra rodar tudo localmente em vez do Colab (veja
"Instalação" abaixo) — o notebook existe só para suprir a falta de GPU local.

## Instalação

Requer Python ≥ 3.10 e < 3.13.

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # Linux/Mac

# 1) PyTorch — escolha a build certa para sua GPU em https://pytorch.org/get-started/locally/
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 2) Demais dependências
pip install -r requirements.txt
```

GPU recomendada: ~8 GB de VRAM (VoxCPM2, 2B parâmetros). Sem GPU CUDA disponível, o script
cai automaticamente para CPU — funciona, mas é bem mais lento para narrações longas.

## Uso via linha de comando

```bash
# Ouça uma prévia curta antes de gerar a narração completa (recomendado):
python cli.py --previa ambas   # ou --previa masculina / --previa feminina

python cli.py --texto "Bem-vindos à apresentação." --saida narracao.wav

python cli.py --arquivo-texto roteiro.txt --saida narracao.wav \
  --velocidade 1.1 --tom -1 --seed 42

# Sem GPU:
python cli.py --arquivo-texto roteiro.txt --cpu
```

Sem `--texto` nem `--arquivo-texto`, o script usa um texto de narração de exemplo.

Parâmetros principais: `--previa` (gera só uma amostra curta da voz e sai, sem rodar a
narração completa), `--voz` (descrição da voz), `--velocidade`, `--tom` (semitons),
`--seed` (mantém o timbre consistente entre trechos), `--tamanho-trecho` (caracteres por
trecho gerado), `--cpu` (força CPU).

## Uso via frontend web

```bash
uvicorn servidorWeb:oApp --reload
```

Abra `http://localhost:8000`, cole o texto da narração, ajuste voz/velocidade/tom e clique
em **Gerar narração**. A barra de progresso acompanha a geração trecho a trecho; ao final,
o áudio fica disponível para ouvir e baixar.

O servidor carrega o modelo VoxCPM2 uma única vez (na primeira geração) e processa os jobs
em fila, um por vez, para não estourar a VRAM da GPU.
