# Log de alterações — Gwen AI Agent

---

## v1.0.0 — 2025-06-07

**O que foi alterado:** Criação inicial do agente
**Por que:** Primeira implementação da Gwen

- Agente conversacional via terminal usando SDK `anthropic`
- Histórico persistido em `history.json`
- Comandos `sair` e `limpar`
- Modelo: `claude-opus-4-20250514`

---

## v1.1.0 — 2025-06-07

**O que foi alterado:** Migração de `anthropic` para `groq`; criação de `.env` e `requirements.txt`
**Por que:** Troca de provedor de API para Groq conforme solicitado

- Cliente trocado para `groq.Groq()`, modelo `llama-3.3-70b-versatile`
- API key carregada via `.env` com `python-dotenv`
- Output renderizado com `rich` (Markdown + Prompt colorido)
- Criado `.env` com `GROQ_API_KEY`
- Criado `requirements.txt` com `groq>=0.9.0`, `python-dotenv>=1.0.0`, `rich>=13.7.0`

---

## v1.2.0 — 2025-06-07

**O que foi alterado:** Criação de `setup.bat`
**Por que:** Corrigir `ModuleNotFoundError: No module named 'groq'` em Windows

- O erro ocorria porque as dependências não estavam instaladas
- `setup.bat` executa `pip install -r requirements.txt` e em seguida `python gwen.py`
- O código `gwen.py` estava correto; apenas faltava instalação das libs

**Como rodar (Windows):**
```
Duplo clique em setup.bat
```
ou manualmente:
```bash
pip install -r requirements.txt
python gwen.py
```

---

## v1.3.0 — 2025-06-08

**O que foi alterado:** Reescrita de `setup.bat`; criação de `run.bat`
**Por que:** `setup.bat` anterior não resolvia o erro quando o usuário executava `python gwen.py` diretamente no PowerShell sem ter instalado as dependências. O problema real: `pip install` do bat anterior usava o `pip` do PATH, que pode apontar para outro Python que não o do sistema. A correção usa `python -m pip`, garantindo que as libs sejam instaladas no mesmo Python que executa o script.

**Mudanças em `setup.bat`:**
- Substituído `pip install -r requirements.txt` por `python -m pip install groq python-dotenv rich`
- Adicionada verificação de Python no PATH com mensagem de erro clara
- Adicionado upgrade do pip antes da instalação
- Adicionado feedback visual de cada etapa

**Criado `run.bat`:**
- Atalho simples para execuções após o setup já ter sido feito

**Como rodar:**
```
1ª vez: duplo clique em setup.bat (instala tudo e inicia)
Próximas vezes: duplo clique em run.bat
```

---

## v1.4.0 — 2025-06-08

**O que foi alterado:** Auto-instalação de dependências dentro do `gwen.py`
**Por que:** Usuário não conseguia instalar as dependências sem usar os arquivos `.bat`

- Adicionado bloco `_install()` no topo do `gwen.py`, antes dos imports de terceiros
- Usa `importlib.util.find_spec()` para checar se cada lib já está instalada
- Só instala o que falta — não reinstala desnecessariamente
- Usa `sys.executable` para garantir que o `pip` é do mesmo Python que está rodando o script
- Libs verificadas: `groq`, `python-dotenv` (módulo `dotenv`), `rich`

**Como rodar (sem bat, sem setup):**
```bash
python gwen.py
```
Na primeira execução, instala as dependências automaticamente e inicia.

---

## v1.5.0 — 2025-06-08

**O que foi alterado:** `encoding="utf-8"` em `read_text()` e `write_text()`
**Por que:** `UnicodeEncodeError` no Windows — o codec padrão `cp1252` não suporta emojis (ex: 🤖). O histórico salvo pela Gwen contém emojis nas respostas, causando falha ao gravar `history.json`.

---

## v2.0.0 — 2025-06-08

**O que foi alterado:** Substituição completa do `gwen.py` pelo código novo; atualização do `requirements.txt`
**Por que:** Usuário optou por usar a versão com segurança avançada (código do documento enviado)

**Problemas corrigidos no código original:**
- `cryptography` e `keyring` não estavam no `requirements.txt` — adicionados
- Aprovação por token CSRF para `/salvar` e `/limpar` substituída por confirmação simples `s/N` — o mecanismo original era inviável para uso pessoal no terminal
- Classe `JWTHandler` removida — era usada só para assinar o audit log, complexidade desnecessária; audit log continua funcional sem JWT
- `SessionManager` removido junto com o CSRF de token — dependia do `JWTHandler`
- Auto-install (`_install()`) adicionado ao topo — mantém a correção do v1.4.0
- Encoding `utf-8` mantido em todas as operações de arquivo — correção do v1.5.0
- Código reduzido de ~900 para 450 linhas sem perder nenhuma funcionalidade relevante

**`requirements.txt` atualizado:**
- Adicionados `cryptography>=41.0.0` e `keyring>=24.0.0`

**Funcionalidades mantidas:**
- Detecção de jailbreak, prompt injection, exfiltração
- Criptografia da API key em disco (Fernet/AES)
- Rate limiting (burst + janela deslizante)
- Audit log append-only
- Memória com proteção contra envenenamento
- Conversas cifradas em disco
- Troca de personalidade
- Compactação automática de contexto
- UI com rich (cores, Markdown, painéis)

---

## v2.1.0 — 2025-06-08

**O que foi alterado:** Implementação da identidade real da Gwen como parceira de produtividade
**Por que:** O código anterior funcionava como chatbot genérico; não seguia a proposta original da Gwen de transformar objetivos em resultados com acompanhamento de progresso

**Adicionado — `ProjectTracker` (nova classe):**
- Persiste projetos, etapas e progresso em `projetos.json`
- Cada projeto tem: objetivo, lista de etapas (concluídas/pendentes), notas e timestamps
- Suporta múltiplos projetos simultâneos com controle de projeto ativo
- Restaura o projeto ativo automaticamente entre sessões

**Adicionado — injeção de contexto no system prompt:**
- `PromptBuilder.build()` injeta bloco `<project_context>` com projeto ativo, progresso e próximas etapas
- A Gwen considera esse contexto em toda resposta automaticamente

**Adicionado — extração automática de projetos:**
- `GwenAgent._maybe_extract_project()` detecta quando a Gwen gerou um plano com etapas numeradas
- Cria o projeto no tracker automaticamente — sem intervenção do usuário

**Adicionado — novos comandos:**
- `/projetos` — lista todos os projetos com progresso visual
- `/projeto <nome>` — ativa um projeto
- `/etapa <n>` — marca etapa como concluída
- `/desetapa <n>` — desmarca etapa
- `/nota <texto>` — adiciona nota ao projeto ativo
- `/deletar <nome>` — remove projeto

**Adicionado — barra de progresso visual:**
- `UI.active_project_bar()` exibe nome do projeto + barra `█░` + contador de etapas
- Aparece no startup e após cada mudança de projeto/etapa

**Alterado — system prompt:**
- Substituído por prompt completo com missão, comportamento e estilo da Gwen
- Personalidade padrão trocada de "assistente" para "produtividade"
- Inclui instruções de como pensar ao receber um objetivo (os 6 passos originais)

**Alterado — personalidades:**
- "assistente" → "produtividade" (novo padrão, focado em planos e execução)

---

## v2.2.0 — 2025-06-08

**O que foi alterado:** MVP de melhorias de produtividade
**Por que:** O agente ainda não seguia o ciclo completo da Gwen — faltavam onboarding, check-in de retorno, weekly review e feedback automático de progresso

**Adicionado — onboarding (`_startup_message`):**
- Primeira sessão sem projetos: Gwen se apresenta e faz a pergunta principal ("O que você quer realizar hoje?")
- Sessões seguintes com projeto parado 1+ dias: Gwen retoma com check-in automático, mostrando progresso e próxima etapa pendente
- Projeto 100% concluído: Gwen celebra e sugere criar novo objetivo

**Adicionado — `/checkin`:**
- Check-in manual a qualquer momento
- Gwen consulta o progresso atual do projeto, faz uma pergunta direta sobre o avanço e sugere o próximo passo concreto
- Registra timestamp do check-in em `last_checkin` no projeto

**Adicionado — `/semana` (Weekly Review):**
- Consolida todos os projetos: o que avançou, o que está parado
- Gwen analisa o resumo e sugere UM foco prioritário para a semana com próximo passo

**Adicionado — hint automático após `/etapa`:**
- Ao concluir uma etapa, a Gwen mostra imediatamente a próxima etapa pendente
- Se todas as etapas foram concluídas, exibe mensagem de conclusão e sugere `/semana`

**Adicionado — `ProjectTracker` novos métodos:**
- `checkin()` — registra `last_checkin`
- `days_since_checkin()` — retorna dias desde o último check-in
- `next_pending_step()` — retorna a próxima etapa não concluída
- `weekly_summary()` — consolida todos os projetos para o review semanal
