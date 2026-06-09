<div align="center">

<img src="https://i.imgur.com/placeholder.png" width="80" alt="Gwen AI Logo">

# Gwen AI ✦

**Agente de produtividade com IA — funciona no terminal e na web**

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/Groq-LLaMA_3.3-orange)](https://console.groq.com)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/Licença-MIT-purple)](LICENSE)

</div>

---

## O que é a Gwen?

A Gwen é uma parceira de IA focada em **produtividade real** — não apenas responde perguntas, mas ajuda você a planejar projetos, organizar etapas e acompanhar o progresso ao longo do tempo.

Roda tanto no **terminal** (com interface rica via Rich) quanto na **web** (interface SaaS moderna via FastAPI + HTML).

---

## Funcionalidades

- 💬 **Chat inteligente** com contexto e memória de sessão
- 📌 **Gestão de projetos** — cria, rastreia e avança etapas automaticamente
- 🔄 **Check-in diário** — Gwen lembra do seu progresso e sugere o próximo passo
- 📅 **Weekly review** — resumo semanal com foco sugerido
- 🎭 **Personalidades** — produtividade, programador, professor, criativo
- 🔒 **Segurança** — proteção contra jailbreak, sanitização de inputs, audit log
- 🌐 **Interface web** — UI premium com design SaaS moderno

---

## Instalação rápida

### 1. Clone o repositório

```bash
git clone https://github.com/aleegxvs/gwen.git
cd gwen
```

### 2. Instale as dependências

```bash
pip install -r requirements.txt
```

### 3. Configure a chave de API

```bash
cp .env.example .env
# Edite .env e insira sua GROQ_API_KEY
# Obtenha em: https://console.groq.com/keys
```

### 4. Execute

**Terminal:**
```bash
python gwen.py
```

**Web (interface no navegador):**
```bash
python server.py
# Acesse: http://localhost:8000
```

---

## Uso no terminal

```
❯ /ajuda          — mostra todos os comandos
❯ /projetos       — lista projetos
❯ /projeto <nome> — ativa projeto
❯ /etapa <n>      — marca etapa como concluída
❯ /checkin        — check-in: Gwen pergunta seu progresso
❯ /semana         — weekly review
❯ /personalidade  — troca modo de resposta
❯ /salvar [nome]  — salva conversa (cifrada)
❯ /carregar <nome>— carrega conversa
❯ /limpar         — reseta memória
❯ /sair           — encerra
```

---

## API Web (endpoints)

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Interface web |
| GET | `/api/startup` | Mensagem de boas-vindas/check-in |
| POST | `/api/chat` | Enviar mensagem: `{"message": "texto"}` |
| GET | `/api/projects` | Listar projetos |
| POST | `/api/projects/{name}/activate` | Ativar projeto |
| DELETE | `/api/projects/{name}` | Deletar projeto |
| POST | `/api/projects/step/complete` | Concluir etapa: `{"index": 1}` |
| POST | `/api/projects/step/uncomplete` | Desmarcar etapa |
| POST | `/api/projects/note` | Adicionar nota: `{"text": "..."}` |
| POST | `/api/checkin` | Check-in do projeto ativo |
| POST | `/api/semana` | Weekly review |
| GET | `/api/personalities` | Listar personalidades |
| POST | `/api/personalities/{name}` | Trocar personalidade |
| GET | `/api/memory/stats` | Estatísticas de memória |
| POST | `/api/memory/clear` | Limpar memória |
| GET | `/health` | Healthcheck |

---

## Estrutura do projeto

```
gwen/
├── gwen.py              # Agente de IA (terminal + núcleo)
├── server.py            # Servidor web (FastAPI)
├── requirements.txt     # Dependências
├── .env.example         # Template de variáveis de ambiente
├── frontend/
│   └── index.html       # Interface web (standalone, sem build)
├── conversas/           # Conversas salvas (cifradas, ignoradas pelo git)
├── logs/                # Logs de auditoria (ignorados pelo git)
└── .keys/               # Chaves de criptografia (ignoradas pelo git)
```

---

## Segurança

- Inputs sanitizados contra XSS, SQL injection, path traversal e command injection
- Detecção de tentativas de jailbreak e prompt injection
- Conversas salvas com criptografia Fernet (AES-128)
- Rate limiting: 20 requests/min, burst de 5/2s
- Audit log de todas as ações sensíveis

---

## Tecnologias

- **Python 3.10+** — linguagem principal
- **Groq + LLaMA 3.3 70B** — modelo de linguagem
- **FastAPI + Uvicorn** — servidor web
- **Rich** — UI de terminal
- **Cryptography** — criptografia de conversas

---

<div align="center">
Feito com ✦ por <a href="https://github.com/aleegxvs">aleegxvs</a>
</div>
