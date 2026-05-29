# Morning Call Digest — contexto para Claude

## O que o projeto faz

Automação Windows que roda seg–sex às 10h30 via Task Scheduler. Para cada um dos 4 canais (BTG, Genial, Investing, XP), busca o morning call do dia no YouTube, baixa a transcrição e gera um digest em 3–4 parágrafos com Gemini, enviado por email via Gmail SMTP.

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
| `emailer.py` | Construção e envio de todos os tipos de email |
| `run.ps1` | Carrega `secrets.env`, roda `main.py`, suspende PC após 30s |
| `setup_task.ps1` | Registra `MorningCallDigest_Wake` (10:25) e `_Run` (10:30) no Task Scheduler |
| `config.json` | Lista de destinatários do email |
| `secrets.env` | Credenciais locais (gitignored) |
| `logs/YYYY-MM-DD.log` | Log de cada execução |

## Decisões de arquitetura

**Por que rodar local e não GitHub Actions / Colab?**
O YouTube bloqueia IPs de datacenter. IP residencial é necessário para o `youtube-transcript-api` funcionar sem autenticação.

**Por que consultar a data de cada vídeo individualmente?**
O `yt-dlp --flat-playlist` não retorna datas. É preciso fazer um request por vídeo para obter `release_date` / `upload_date`. Isso está comprovado como a única abordagem confiável — não tente mandar 20 vídeos de uma vez para a IA compensar.

**Por que `max_output_tokens=512` na seleção de vídeo?**
Nesse ponto a IA recebe apenas 1–2 vídeos do dia (já filtrados por data), não 20. Com 512 tokens o JSON de resposta cabe com folga. Aumentar esse valor não resolve nada e só aumenta custo.

**Por que `WakeToRun` só no `_Wake` e não no `_Run`?**
Ter `WakeToRun` na tarefa `_Run` cria um wake timer interno no Windows que acorda o PC ~2h após a execução, causando dupla execução. A tarefa `_Wake` às 10:25 já garante que o PC estará acordado quando `_Run` disparar às 10:30.

**Guard de dupla execução em `run.ps1`**
Se o log do dia já contiver `"Script finalizado"`, o `run.ps1` aborta imediatamente e volta a suspender o PC. Isso cobre qualquer cenário de re-disparo inesperado do Task Scheduler.

## Comportamento esperado por execução

1. Verifica IP (se bloqueado, envia email de aviso e encerra)
2. Para cada canal: flat-playlist → data por vídeo → filtra dia → IA seleciona → baixa transcrição (até 3 tentativas com 10min de espera)
3. Gemini gera resumo consolidado
4. Email enviado; log finalizado; PC suspende em 30s

## Restrições importantes

- Não usar `yt-dlp` para download de vídeo — só para `--flat-playlist` e `--print` de metadados
- Não remover os delays `_sleep_humano` entre requests — eles simulam comportamento humano e evitam bloqueio
- O modelo atual é `gemini-3.1-flash-lite` — suficiente para seleção e resumo neste contexto
- `secrets.env` nunca deve ser commitado
