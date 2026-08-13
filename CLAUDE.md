# Morning Call Digest — contexto para Claude

## O que o projeto faz

Automação Windows que roda seg–sex às 10h30 via Task Scheduler. Para cada um dos 5 canais (BTG, Genial, Investing, XP e PicPay/Diário Econômico), busca o morning call do dia no YouTube, baixa a transcrição e gera um digest em 3–4 parágrafos com Gemini. O email inclui ainda um painel de preços (Ibovespa, S&P 500, BTC, ETH, ouro e petróleo Brent) com variações de 3/7/30 dias. Enviado por email via Gmail SMTP.

## Como testar

```powershell
# Roda com email apenas para o remetente (não dispara para todos os destinatários)
$env:TEST_MODE = "true"
.\run.ps1

# Ou direto com Python (requer secrets.env carregado manualmente)
py main.py
```

## Arquivos principais

| Arquivo | Função |
|---------|--------|
| `main.py` | Orquestração do pipeline — entry point |
| `config.py` | Constantes, env vars, cliente Gemini, YTDLP, CHANNELS |
| `youtube.py` | Busca de vídeos, consulta de datas, transcrições, IP check |
| `summarizer.py` | Geração do resumo com Gemini |
| `prices.py` | Busca preços e variações dos ativos (yfinance) para o painel de mercado |
| `emailer.py` | Construção e envio de todos os tipos de email (inclui o painel de preços) |
| `run.ps1` | Carrega `secrets.env`, roda `main.py`, suspende PC após 30s |
| `setup_task.ps1` | Registra `MorningCallDigest_Wake` (10:25) e `_Run` (10:30) no Task Scheduler |
| `wake_hold.ps1` | Ação da tarefa `_Wake` — segura o PC acordado até a `_Run` assumir |
| `config.json` | Lista de destinatários do email |
| `secrets.env` | Credenciais locais (gitignored) |
| `cookies.txt` | Cookies (formato Netscape) de uma conta Google dedicada, opcional, gitignored — ver decisão de robustez de IP abaixo |
| `logs/YYYY-MM-DD.log` | Log de cada execução (timestamp por linha; stderr do Python incluído) |
| `logs/YYYY-MM-DD.error.log` | Stderr completo do Python quando o processo termina com exit code != 0 |
| `logs/YYYY-MM-DD.wake.log` | Log do `wake_hold.ps1` — confirma se o hold de acordar o PC rodou |

## Decisões de arquitetura

**Por que rodar local e não GitHub Actions / Colab?**
O YouTube bloqueia IPs de datacenter. IP residencial é necessário para o `youtube-transcript-api` funcionar sem autenticação.

**Por que consultar a data de cada vídeo individualmente?**
O `yt-dlp --flat-playlist` não retorna datas. É preciso fazer um request por vídeo para obter `release_date` / `upload_date`. Isso está comprovado como a única abordagem confiável — não tente mandar 20 vídeos de uma vez para a IA compensar.

**Por que `max_output_tokens=512` na seleção de vídeo?**
Nesse ponto a IA recebe apenas 1–2 vídeos do dia (já filtrados por data), não 20. Com 512 tokens o JSON de resposta cabe com folga. Aumentar esse valor não resolve nada e só aumenta custo.

**Por que `WakeToRun` só no `_Wake` e não no `_Run`?**
Ter `WakeToRun` na tarefa `_Run` cria um wake timer interno no Windows que acorda o PC ~2h após a execução, causando dupla execução. A tarefa `_Wake` às 10:25 já garante que o PC estará acordado quando `_Run` disparar às 10:30.

**Por que `_Wake` roda `wake_hold.ps1` em vez de só `echo wake`?**
`WakeToRun` acorda o PC, mas só o mantém ligado enquanto a própria tarefa `_Wake` está rodando — como `echo wake` termina em menos de 1s, o Windows não tinha mais motivo pra continuar acordado e voltava a suspender sozinho em ~2–3min, antes da `_Run` disparar às 10:30. Isso derrubava o digest para a tarde/noite, só rodando via `StartWhenAvailable` quando alguém ligava o PC manualmente (confirmado no Visualizador de Eventos do Windows em 17/06, 25/06, 09/07, 10/07, 17/07, 22/07 e 30/07/2026 — todos com padrão idêntico: wake às 10:24:33, suspensão de novo minutos depois, e só religam via botão de energia horas mais tarde). `wake_hold.ps1` segura o PC acordado (`ES_SYSTEM_REQUIRED`) por 10min, cobrindo a lacuna até `_Run` assumir e o próprio `main.py` travar a suspensão (`_impedir_suspensao`). Isso não atrasa o desligamento no fim do dia: a suspensão forçada do `run.ps1` (`SetSuspendState`) ignora bloqueios de `ES_SYSTEM_REQUIRED`.

**Guard de dupla execução em `run.ps1`**
Se o log do dia já contiver `"Script finalizado OK"`, o `run.ps1` aborta imediatamente e volta a suspender o PC. Isso cobre qualquer cenário de re-disparo inesperado do Task Scheduler. Note que o marcador é `"...OK"`, não só `"Script finalizado"`: uma execução que termina com erro (`"Script finalizado COM ERRO (exit code N)"`) **não** ativa o guard — de propósito, para deixar uma tentativa seguinte (manual ou via `StartWhenAvailable`) rodar ainda no mesmo dia em vez de ficar travada até amanhã.

**Diagnóstico de crash e de wake em `run.ps1`**
Antes de rodar `main.py`, o `run.ps1` loga o horário do último boot do PC e a saída de `powercfg /lastwake` — isso já teria respondido em segundos ao diagnóstico feito manualmente em 09/08/2026 (que exigiu vasculhar o Visualizador de Eventos na mão) sempre que o horário de início for atípico. Depois, o stderr do Python é redirecionado para um arquivo (não `2>&1` — mistura no stream de sucesso e gera `NativeCommandError` no PowerShell 5.1), apensado ao log principal e ao `.error.log`, e o exit code é checado: antes disso, um crash não tratado do `main.py` (traceback indo só para o console de uma sessão S4U sem interface) terminava o log exatamente como um dia de sucesso, porque `"Script finalizado"` era escrito incondicionalmente.

**Por que o canal do PicPay (Diário Econômico) é diferente?**
O `@PodcastDiarioEconomico` não tem aba `/streams` — é publicado como vídeo em `/videos`, então a URL em `CHANNELS` aponta para `/videos`. Os episódios são curtos (~5min), abaixo do `MIN_VIDEO_SECS=300` dos demais canais; por isso o picpay tem `min_secs=120` em `CHANNELS` (cada canal tem seu mínimo). Os títulos podem voltar traduzidos para inglês ("Economic Daily"), então o prompt de seleção reconhece "Diário Econômico/Economic Daily". O filtro por data usa `upload_date` (metadado, independe do idioma do título).

**Por que o Investing quase nunca entra no digest, e por que ele não faz retry?**
Investigado em 09/08/2026: o vídeo do Investing chega a ser encontrado e selecionado, mas o YouTube demora **~13h** para finalizar o processamento da live dele (visto comparando `release_timestamp` com `timestamp` via `yt-dlp` — outros canais, como o BTG, finalizam em ~35min). Nenhum retry dentro da janela das 10:30 resolve isso, então o Investing tem `"retries": 1` em `CHANNELS` (sem espera de 10min) — insistir só atrasa o digest à toa. Além disso, desde ~24/07/2026 o canal também passou a postar com bem menos frequência no `/streams` (o `/videos` dele é conteúdo temático avulso, não serve de fallback). Ficar de fora do digest na maioria dos dias é esperado, não é bug.

**Por que os preços não passam pela IA?**
O painel de mercado é informativo e determinístico (Yahoo Finance via `yfinance`, sem API key). Passar cotações pela IA só adicionaria custo e risco de alucinação. Os preços são buscados em `prices.py` e renderizados direto na tabela do email, em paralelo ao resumo. Qualquer falha (Yahoo fora do ar, símbolo sem dado) é capturada por ativo e/ou no `main.py` — o digest sempre é enviado, no pior caso com "—" na linha do ativo.

**Robustez contra bloqueio de IP (12–13/08/2026)**
Depois de 2 bloqueios em 10 dias (04/08 e 12/08/2026), quatro mudanças:
- `verificar_ip_bloqueado()` (em `youtube.py`) capturava bloqueio via `"blocked" in msg or "bot" in msg or "ip" in msg` — um match de substring largo o bastante pra classificar qualquer erro não relacionado (timeout, DNS etc.) como bloqueio e abortar o dia à toa, sem deixar rastro da causa real no log. Passou a capturar especificamente `RequestBlocked`/`IpBlocked` (exceções tipadas da própria `youtube_transcript_api`) e logar a mensagem completa da lib — qualquer outro erro no check não é mais tratado como bloqueio.
- O check de IP agora tenta de novo (`IP_CHECK_RETRIES=2`, espera `IP_CHECK_RETRY_WAIT=5min` entre tentativas) antes de desistir do dia — bloqueio costuma ser rate-limit temporário, não ban permanente, e não temos rede alternativa (hotspot/segunda conexão) pra fallback imediato.
- `max_busca` (vídeos varridos por canal pra achar a data) caiu de 20 pra 8. O morning call sempre está entre os mais recentes; a busca de 20 gerava até ~100 chamadas de `yt-dlp` em poucos minutos, todo dia útil no mesmo horário — um padrão de tráfego bem "bot-like" que era provavelmente o principal gatilho do bloqueio.
- Suporte opcional a `cookies.txt`: se o arquivo existir (exportado de uma conta Google **dedicada**, não a pessoal — a própria lib avisa que a conta usada pode ser banida), `YTDLP` passa `--cookies cookies.txt` e a `youtube_transcript_api` usa um `requests.Session()` autenticado com esses cookies (via `http_client=`, já que a lib removeu o parâmetro de cookie_path nativo). Tráfego autenticado é tratado de forma bem menos suspeita que anônimo. Sem o arquivo, tudo roda anônimo como antes — não é obrigatório.

Se bloqueios voltarem a ser frequentes mesmo com essas mudanças: o provedor residencial usado aqui é IP dinâmico, então reiniciar o roteador antes da próxima execução costuma trocar o IP público e resetar bloqueios ligados a IP — não há automação disso ainda (dependeria de smart plug ou API de reboot do roteador), é um passo manual.

## Comportamento esperado por execução

1. Verifica IP (até 2 tentativas com 5min de espera; se seguir bloqueado, envia email de aviso e encerra)
2. Para cada canal: flat-playlist → data por vídeo → filtra dia → IA seleciona → baixa transcrição (até 3 tentativas com 10min de espera)
3. Gemini gera resumo consolidado
4. Busca preços de mercado (yfinance) para o painel — falha aqui nunca derruba o digest
5. Email enviado (resumo + painel de preços); log finalizado; PC suspende em 30s

## Restrições importantes

- Não usar `yt-dlp` para download de vídeo — só para `--flat-playlist` e `--print` de metadados
- Não remover os delays `_sleep_humano` entre requests — eles simulam comportamento humano e evitam bloqueio
- O modelo atual é `gemini-3.1-flash-lite` — suficiente para seleção e resumo neste contexto
- `secrets.env` nunca deve ser commitado
