# Morning Call Digest

Automação que coleta os morning calls de 4 canais financeiros do YouTube, gera um resumo executivo com IA (Gemini) e envia por email todo dia útil às 9h30.

**Canais monitorados:** BTG Pactual · Genial Investimentos · Investing.com BR · XP Oficial

---

## Como funciona

```
11h55 → Windows acorda o PC automaticamente (se estiver suspenso)
12h00 → Task Scheduler executa run.ps1
        ├── yt-dlp lista vídeos de cada canal
        ├── Gemini identifica qual é o morning call do dia
        ├── youtube-transcript-api baixa as transcrições
        ├── Gemini gera resumo executivo em 3-4 parágrafos
        └── Email HTML enviado via Gmail SMTP
~12h10 → Script termina, email na caixa de entrada
```

> **Por que meio-dia?** Os morning calls são transmitidos ao vivo entre 9h e 10h30. O YouTube leva 2–4h para processar as legendas automáticas do VOD. Rodar ao meio-dia garante que todos os canais já têm transcrição disponível.

---

## Pré-requisitos

- Python 3.10+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) instalado e no PATH
- Conta Google com [Gemini API Key](https://aistudio.google.com/app/apikey)
- Conta Gmail com [Senha de App](https://myaccount.google.com/apppasswords) gerada

---

## Instalação

### 1. Clone e instale dependências

```powershell
git clone <url-do-repo>
cd morning-call-digest
pip install -r requirements.txt
```

### 2. Configure os segredos

Copie o arquivo de exemplo e preencha com suas credenciais:

```powershell
Copy-Item secrets.env.example secrets.env
notepad secrets.env
```

Conteúdo do `secrets.env`:
```
GEMINI_API_KEY=sua_chave_gemini_aqui
EMAIL_REMETENTE=seu_email@gmail.com
EMAIL_SENHA_APP=xxxx xxxx xxxx xxxx   # senha de app do Gmail (16 caracteres)
```

> `secrets.env` está no `.gitignore` e nunca será commitado.

### 3. Configure os destinatários

Edite [config.json](config.json) com os emails que devem receber o digest:

```json
{
  "destinatarios": [
    "voce@gmail.com",
    "outro@email.com"
  ]
}
```

### 4. Teste manualmente

```powershell
.\run.ps1
```

---

## Agendamento automático (Windows Task Scheduler)

O script roda localmente para evitar bloqueios de IP que afetam ambientes de CI/CD.

### Configurar as tarefas

Execute **como Administrador**:

```powershell
.\setup_task.ps1
```

Isso cria duas tarefas no Windows:

| Tarefa | Horário | Função |
|--------|---------|--------|
| `MorningCallDigest_Wake` | 11:55 seg–sex | Acorda o PC do modo de suspensão |
| `MorningCallDigest_Run`  | 12:00 seg–sex | Executa o script e envia o email |

### Requisitos para o wake funcionar

- Notebook **plugado na tomada** (não na bateria)
- Suspensão **S3** (suspensão normal), não hibernação (`S4`) nem desligado
- Wake timers habilitados no plano de energia:

```powershell
# Verificar se wake timers estão ativos
powercfg /query SCHEME_CURRENT SUB_SLEEP RTCWAKE
```

Se o valor for `000`, habilite via Painel de Controle:
> Opções de Energia → Alterar configurações do plano → Alterar configurações de energia avançadas → Suspender → Permitir temporizadores de ativação → **Habilitar**

### Cookies do YouTube (recomendado)

O yt-dlp precisa de cookies para acessar metadados de vídeos individuais sem ser bloqueado pelo YouTube. Existem duas formas:

**Opção A — Arquivo de cookies (mais confiável)**

1. Instale a extensão [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) no Edge ou Chrome
2. Acesse [youtube.com](https://youtube.com) logado na sua conta
3. Clique no ícone da extensão e exporte para `youtube_cookies.txt`
4. Coloque o arquivo na pasta do projeto

O script detecta o arquivo automaticamente e usa os cookies. Renove o arquivo a cada 1–2 anos quando os cookies expirarem.

**Opção B — Cookies do browser (automático, mas requer browser fechado)**

Se `youtube_cookies.txt` não existir, o script tenta ler os cookies direto do Edge/Chrome. Funciona apenas se o browser estiver **fechado** no momento da execução — o que deve ser o caso às 12h00 se o PC acordou do modo de suspensão.

### Remover as tarefas

```powershell
Unregister-ScheduledTask -TaskName "MorningCallDigest_Wake" -Confirm:$false
Unregister-ScheduledTask -TaskName "MorningCallDigest_Run"  -Confirm:$false
```

---

## Estrutura do projeto

```
morning-call-digest/
├── main.py              # pipeline principal
├── run.ps1              # wrapper local (carrega secrets e roda main.py)
├── setup_task.ps1       # cria as tarefas no Task Scheduler (rodar como Admin)
├── config.json          # lista de destinatários do email
├── secrets.env          # credenciais locais (não commitado)
├── secrets.env.example  # template de credenciais
├── requirements.txt     # dependências Python
└── .github/workflows/
    └── digest.yml       # workflow GitHub Actions (alternativa via CI/CD)
```

---

## Variáveis de ambiente / segredos

| Variável | Onde obter |
|----------|-----------|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `EMAIL_REMETENTE` | Seu endereço Gmail |
| `EMAIL_SENHA_APP` | [Senhas de app do Google](https://myaccount.google.com/apppasswords) — requer 2FA ativo |
