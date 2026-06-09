#!/usr/bin/env python3
"""
Gwen Web Server v2.2.0 — FastAPI layer sobre o GwenAgent.
Expõe o agente de IA via HTTP sem modificar gwen.py.

Uso:
    python server.py
    # ou
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import importlib.util, subprocess, sys

_WEB_DEPS = {"fastapi": "fastapi", "uvicorn": "uvicorn"}

def _install_web() -> None:
    missing = [pkg for pkg, mod in _WEB_DEPS.items()
               if importlib.util.find_spec(mod) is None]
    if missing:
        print(f"Instalando dependências web: {', '.join(missing)}...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            *missing, "uvicorn[standard]"
        ])

_install_web()

import logging
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── importa o núcleo do agente ────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gwen import (
    AuditLogger,
    GwenAgent,
    Memory,
    ProjectTracker,
    PromptBuilder,
    SecretsManager,
    Settings,
    InputSanitizer,
    APP_VERSION,
    BASE_DIR,
)

# ── UI nula — substitui a UI de terminal por versão silenciosa ────────────────
class NullUI:
    """Substitui a rich UI do terminal por uma versão no-op para uso via API."""

    class _Console:
        def print(self, *a, **kw): pass
        def input(self, *a, **kw): return ""
        def status(self, *a, **kw):
            from contextlib import nullcontext
            return nullcontext()

    console = _Console()

    def header(self, *a, **kw):             pass
    def help(self, *a, **kw):               pass
    def assistant(self, *a, **kw):          pass
    def ok(self, *a, **kw):                 pass
    def warn(self, *a, **kw):               pass
    def error(self, *a, **kw):              pass
    def status(self, *a, **kw):             pass
    def threat(self, *a, **kw):             pass
    def section(self, *a, **kw):            pass
    def confirm(self, *a, **kw):            return True
    def prompt(self, *a, **kw):             return ""
    def active_project_bar(self, *a, **kw): pass


# ── inicializa o agente uma vez, compartilhado entre requests ─────────────────
_sec   = SecretsManager()
_audit = AuditLogger()
_ui    = NullUI()

try:
    _settings = Settings.load(_ui.console, _sec)
except SystemExit as e:
    print(f"\n[ERRO] Chave de API não encontrada: {e}")
    print("Crie um arquivo .env com:\n  GROQ_API_KEY=gsk_...\n")
    sys.exit(1)

_agent = GwenAgent(_settings, _ui, _audit, _sec)

# ── app ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Gwen AI",
    version=APP_VERSION,
    description="API do agente de IA Gwen",
    docs_url=None,
    redoc_url=None,
)

# CORS — permite frontend local durante desenvolvimento
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND = Path(__file__).resolve().parent / "frontend"
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")


# ── schemas ───────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str

class StepRequest(BaseModel):
    index: int

class ProjectRequest(BaseModel):
    name: str

class NoteRequest(BaseModel):
    text: str

class PersonalityRequest(BaseModel):
    name: str


# ── rotas ─────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    """Serve o frontend."""
    index = FRONTEND / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"status": "Gwen API running", "version": APP_VERSION})


@app.get("/health")
def health():
    """Healthcheck."""
    return {"status": "ok", "version": APP_VERSION}


@app.get("/api/startup")
def startup() -> dict:
    """
    Retorna mensagem de boas-vindas ou check-in de projeto.
    Chamado pelo frontend ao carregar a página.
    """
    projects = _agent.tracker.all()

    if not projects:
        return {
            "reply": (
                "Olá! Sou a Gwen, sua parceira de produtividade. 🎯\n\n"
                "Meu foco é te ajudar a sair da ideia e chegar à execução.\n\n"
                "**O que você quer realizar hoje?**"
            ),
            "project": None,
        }

    days = _agent.tracker.days_since_checkin()
    p    = _agent.tracker.active
    name = _agent.tracker.active_name

    if not p:
        return {"reply": "Bem-vindo de volta! Qual projeto quer retomar?", "project": None}

    done  = sum(1 for s in p["steps"] if s["done"])
    total = len(p["steps"])

    if done == total:
        msg = (
            f"Bem-vindo de volta! 🎉\n\n"
            f"O projeto **{name}** está **100% concluído**.\n\n"
            f"Quer criar um novo objetivo ou revisar o que foi feito?"
        )
    elif days and days >= 1:
        nxt = _agent.tracker.next_pending_step()
        idx, desc = nxt if nxt else (0, "")
        msg = (
            f"Bem-vindo de volta! ✦\n\n"
            f"Projeto ativo: **{name}** — {done}/{total} etapas concluídas.\n\n"
            f"Próxima etapa: **{idx}. {desc}**\n\n"
            f"Conseguiu avançar nisso? Me conta como está."
        )
    else:
        msg = (
            f"Olá! Projeto ativo: **{name}** — {done}/{total} etapas. "
            f"O que quer fazer hoje?"
        )

    return {"reply": msg, "project": _project_state()}


@app.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    """Envia uma mensagem ao agente e retorna a resposta."""
    msg = req.message.strip()
    if not msg:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")
    reply = _agent.ask(msg)
    return {
        "reply":   reply or "Não consegui processar sua mensagem.",
        "project": _project_state(),
    }


# ── projetos ──────────────────────────────────────────────────────────────────

@app.get("/api/projects")
def get_projects() -> dict:
    """Lista todos os projetos."""
    return {
        "projects": _agent.tracker.all(),
        "active":   _agent.tracker.active_name,
    }


@app.post("/api/projects/{name}/activate")
def activate_project(name: str) -> dict:
    """Ativa um projeto pelo nome."""
    if not _agent.tracker.set_active(name):
        raise HTTPException(404, f"Projeto '{name}' não encontrado.")
    return {"ok": True, "project": _project_state()}


@app.delete("/api/projects/{name}")
def delete_project(name: str) -> dict:
    """Remove um projeto."""
    if not _agent.tracker.delete(name):
        raise HTTPException(404, f"Projeto '{name}' não encontrado.")
    return {"ok": True}


@app.post("/api/projects/step/complete")
def complete_step(req: StepRequest) -> dict:
    """Marca uma etapa como concluída (índice 1-based)."""
    if not _agent.tracker.complete_step(req.index):
        raise HTTPException(400, "Etapa inválida ou não existe projeto ativo.")
    return {"ok": True, "project": _project_state()}


@app.post("/api/projects/step/uncomplete")
def uncomplete_step(req: StepRequest) -> dict:
    """Desmarca uma etapa."""
    if not _agent.tracker.uncomplete_step(req.index):
        raise HTTPException(400, "Etapa inválida ou não existe projeto ativo.")
    return {"ok": True, "project": _project_state()}


@app.post("/api/projects/note")
def add_note(req: NoteRequest) -> dict:
    """Adiciona uma nota ao projeto ativo."""
    if not _agent.tracker.active:
        raise HTTPException(400, "Nenhum projeto ativo.")
    _agent.tracker.add_note(req.text)
    return {"ok": True}


# ── check-in e review ─────────────────────────────────────────────────────────

@app.post("/api/checkin")
def checkin() -> dict:
    """Inicia um check-in do projeto ativo com resposta da Gwen."""
    p    = _agent.tracker.active
    name = _agent.tracker.active_name
    if not p:
        raise HTTPException(400, "Nenhum projeto ativo.")

    done    = sum(1 for s in p["steps"] if s["done"])
    total   = len(p["steps"])
    pending = [f"{i}. {s['desc']}" for i, s in enumerate(p["steps"], 1) if not s["done"]]

    prompt_text = (
        f"O usuário está fazendo um check-in do projeto '{name}'.\n"
        f"Progresso atual: {done}/{total} etapas concluídas.\n"
        f"Etapas pendentes: {', '.join(pending[:4]) if pending else 'nenhuma'}.\n\n"
        "Faça UMA pergunta direta sobre o progresso mais recente "
        "e sugira o próximo passo concreto."
    )
    reply = _agent.ask(prompt_text)
    if reply:
        _agent.tracker.checkin()
    return {"reply": reply or "", "project": _project_state()}


@app.post("/api/semana")
def semana() -> dict:
    """Weekly review: o que avançou, o que está parado, foco sugerido."""
    summary = _agent.tracker.weekly_summary()
    if not summary:
        return {
            "reply": "Nenhum projeto ainda. Comece definindo um objetivo!",
            "project": None,
        }

    lines = ["Resumo semanal dos projetos:\n"]
    for name, info in summary.items():
        status = (
            "✦ ativo" if info["is_active"]
            else ("movimentado" if info["active_recently"] else "parado")
        )
        lines.append(f"- **{name}**: {info['done']}/{info['total']} etapas | {status}")
        if info["goal"]:
            lines.append(f"  Objetivo: {info['goal'][:80]}")

    prompt_text = (
        "\n".join(lines) +
        "\n\nCom base nesse resumo:\n"
        "1. Destaque o que avançou.\n"
        "2. Sinalize o que está parado e por quê pode estar travado.\n"
        "3. Sugira UM foco prioritário para essa semana com próximo passo concreto."
    )
    reply = _agent.ask(prompt_text)
    return {"reply": reply or "", "project": _project_state()}


# ── personalidade ─────────────────────────────────────────────────────────────

@app.get("/api/personalities")
def get_personalities() -> dict:
    """Lista personalidades disponíveis."""
    return {
        "current":   _agent.prompt.current,
        "available": list(PromptBuilder.PERSONALITIES.keys()),
    }


@app.post("/api/personalities/{name}")
def set_personality(name: str) -> dict:
    """Altera a personalidade do agente."""
    if not _agent.prompt.set(name):
        raise HTTPException(404, f"Personalidade '{name}' não encontrada.")
    return {"ok": True, "current": name}


# ── memória ───────────────────────────────────────────────────────────────────

@app.get("/api/memory/stats")
def memory_stats() -> dict:
    """Retorna estatísticas de memória da sessão atual."""
    m = _agent.memory
    u = sum(1 for msg in m.messages if msg["role"] == "user")
    a = sum(1 for msg in m.messages if msg["role"] == "assistant")
    return {
        "user_messages":      u,
        "assistant_messages": a,
        "token_estimate":     m.token_estimate(),
        "has_summary":        bool(m.summary),
        "rate_remaining":     _agent.rate.remaining,
        "model":              _settings.model,
        "personality":        _agent.prompt.current,
    }


@app.post("/api/memory/clear")
def clear_memory() -> dict:
    """Limpa toda a memória da sessão (não afeta arquivos em disco)."""
    _agent.memory.reset()
    _audit.log("MEMORY_CLEARED", {"source": "web"})
    return {"ok": True}


# ── helpers ───────────────────────────────────────────────────────────────────

def _project_state() -> dict | None:
    """Serializa o estado do projeto ativo para JSON."""
    p    = _agent.tracker.active
    name = _agent.tracker.active_name
    if not p:
        return None
    done = sum(1 for s in p["steps"] if s["done"])
    return {
        "name":  name,
        "goal":  p.get("goal", ""),
        "steps": p.get("steps", []),
        "done":  done,
        "total": len(p["steps"]),
        "notes": p.get("notes", ""),
        "last_checkin": p.get("last_checkin"),
    }


# ── entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n  ✦ Gwen AI v{APP_VERSION} — Interface Web")
    print(f"  → http://localhost:8000\n")
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="warning",
    )
