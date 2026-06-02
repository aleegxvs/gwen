#!/usr/bin/env python3
"""
Gwen — Agente de IA Conversacional
Versão 2.0 | CLI-first, seguro, modular, profissional
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import hmac
import hashlib
import logging
import textwrap
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
#  LOGGING (arquivo, sem poluir o terminal)
# ─────────────────────────────────────────────

_log_dir = Path.home() / ".gwen" / "logs"
_log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(
            _log_dir / f"gwen_{datetime.now().strftime('%Y%m%d')}.log",
            encoding="utf-8",
        )
    ],
)
logger = logging.getLogger("gwen")


# ─────────────────────────────────────────────
#  PALETA DE CORES ANSI
# ─────────────────────────────────────────────

class Cor:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"

    BRANCO  = "\033[97m"
    CINZA   = "\033[90m"
    VERDE   = "\033[92m"
    AMARELO = "\033[93m"
    AZUL    = "\033[94m"
    ROXO    = "\033[95m"
    CIANO   = "\033[96m"
    VERMELHO= "\033[91m"
    LARANJA = "\033[38;5;208m"

    @staticmethod
    def strip(text: str) -> str:
        """Remove códigos ANSI de uma string."""
        return re.sub(r"\033\[[0-9;]*m", "", text)


def _suporte_cor() -> bool:
    """Detecta se o terminal suporta ANSI."""
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        return os.environ.get("TERM") is not None
    return True


_COR_ATIVA = _suporte_cor()


def cor(codigo: str, texto: str) -> str:
    """Aplica cor apenas se suportado."""
    if not _COR_ATIVA:
        return texto
    return f"{codigo}{texto}{Cor.RESET}"


# ─────────────────────────────────────────────
#  COMPONENTES VISUAIS CLI
# ─────────────────────────────────────────────

LARGURA = 64


def _largura_terminal() -> int:
    try:
        return min(os.get_terminal_size().columns, 80)
    except OSError:
        return LARGURA


def linha(char: str = "─", largura: int | None = None, c: str = Cor.CINZA) -> None:
    w = largura or _largura_terminal()
    print(cor(c, char * w))


def cabecalho(personalidade: str = "assistente", modelo: str = "llama-3.3-70b") -> None:
    w = _largura_terminal()
    print()
    linha("─", w, Cor.CINZA)
    esq = f"  {cor(Cor.ROXO + Cor.BOLD, 'Gwen')}"
    dir_ = cor(Cor.CINZA, f"groq / {modelo}  [{personalidade}]")
    print(f"{esq}  {dir_}")
    linha("─", w, Cor.CINZA)
    print()


def badge_ok(msg: str) -> None:
    print(f"  {cor(Cor.VERDE, '✓')} {msg}")


def badge_erro(msg: str) -> None:
    print(f"  {cor(Cor.VERMELHO, '✗')} {msg}")


def badge_aviso(msg: str) -> None:
    print(f"  {cor(Cor.AMARELO, '!')} {msg}")


def badge_info(msg: str) -> None:
    print(f"  {cor(Cor.CIANO, '·')} {msg}")


def menu_ajuda() -> None:
    cmds = [
        ("/modo <nome>",        "trocar personalidade"),
        ("/modos",              "listar personalidades disponíveis"),
        ("/salvar [arquivo]",   "salvar conversa em JSON"),
        ("/carregar <arquivo>", "carregar conversa salva"),
        ("/historico",          "ver conversa completa"),
        ("/limpar",             "resetar conversa"),
        ("/stats",              "ver estatísticas da sessão"),
        ("/ajuda",              "exibir esta lista"),
        ("/sair",               "encerrar"),
    ]
    w = _largura_terminal()
    linha("─", w)
    print(f"  {cor(Cor.CINZA, 'Comandos disponíveis:')}")
    print()
    for cmd, desc in cmds:
        print(
            f"  {cor(Cor.AMARELO, f'{cmd:<26}')}"
            f"{cor(Cor.CINZA, desc)}"
        )
    linha("─", w)
    print()


# ─────────────────────────────────────────────
#  SPINNER THREAD-SAFE
# ─────────────────────────────────────────────

class Spinner:
    """Spinner não-bloqueante para operações assíncronas."""

    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

    def __init__(self, mensagem: str = "aguardando") -> None:
        self._msg = mensagem
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Spinner":
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)
        # Limpa a linha do spinner
        print(f"\r{' ' * (_largura_terminal())}\r", end="", flush=True)

    def _run(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._FRAMES[i % len(self._FRAMES)]
            msg = cor(Cor.CINZA, f"  {frame} {self._msg}...")
            print(f"\r{msg}", end="", flush=True)
            time.sleep(0.08)
            i += 1


# ─────────────────────────────────────────────
#  RENDERIZADOR DE MARKDOWN SIMPLES PARA CLI
# ─────────────────────────────────────────────

class RenderCLI:
    """
    Converte Markdown básico em saída ANSI colorida para terminal.
    Suporta: blocos de código, negrito, itálico, listas, cabeçalhos.
    """

    _CODE_BLOCK = re.compile(r"```(\w*)\n?([\s\S]*?)```", re.MULTILINE)
    _INLINE_CODE = re.compile(r"`([^`]+)`")
    _BOLD        = re.compile(r"\*\*(.+?)\*\*")
    _ITALIC      = re.compile(r"\*(.+?)\*")
    _HEADING     = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    _LIST_ITEM   = re.compile(r"^(\s*[-*+]|\s*\d+\.)\s+", re.MULTILINE)

    @classmethod
    def render(cls, texto: str) -> str:
        # Separa blocos de código do resto para não aplicar outros formatadores neles
        partes: list[tuple[bool, str]] = []
        ultimo = 0
        for m in cls._CODE_BLOCK.finditer(texto):
            if m.start() > ultimo:
                partes.append((False, texto[ultimo:m.start()]))
            lang = m.group(1) or ""
            codigo = m.group(2).rstrip()
            partes.append((True, cls._render_bloco_codigo(codigo, lang)))
            ultimo = m.end()
        if ultimo < len(texto):
            partes.append((False, texto[ultimo:]))

        resultado = []
        for is_code, parte in partes:
            if is_code:
                resultado.append(parte)
            else:
                resultado.append(cls._render_prosa(parte))

        return "".join(resultado)

    @classmethod
    def _render_bloco_codigo(cls, codigo: str, lang: str) -> str:
        w = _largura_terminal() - 4
        barra_top = cor(Cor.CINZA, "  ┌" + ("─" * (w)) + "┐")
        barra_bot = cor(Cor.CINZA, "  └" + ("─" * (w)) + "┘")
        linhas = codigo.split("\n")
        corpo = []
        for l in linhas:
            # Trunca linhas muito longas
            if len(l) > w - 2:
                l = l[:w - 5] + "..."
            padding = " " * (w - len(l) - 1)
            corpo.append(
                cor(Cor.CINZA, "  │") +
                cor(Cor.VERDE, f" {l}{padding}") +
                cor(Cor.CINZA, "│")
            )
        label = f"  {cor(Cor.CINZA, lang)}\n" if lang else ""
        return f"\n{label}{barra_top}\n" + "\n".join(corpo) + f"\n{barra_bot}\n"

    @classmethod
    def _render_prosa(cls, texto: str) -> str:
        # Cabeçalhos
        def sub_heading(m):
            nivel = len(m.group(1))
            t = m.group(2)
            if nivel == 1:
                return cor(Cor.ROXO + Cor.BOLD, f"\n  {t}\n")
            elif nivel == 2:
                return cor(Cor.CIANO + Cor.BOLD, f"\n  {t}")
            return cor(Cor.AMARELO, f"\n  {t}")

        texto = cls._HEADING.sub(sub_heading, texto)

        # Negrito e itálico
        texto = cls._BOLD.sub(lambda m: cor(Cor.BOLD, m.group(1)), texto)
        texto = cls._ITALIC.sub(lambda m: cor(Cor.DIM, m.group(1)), texto)

        # Código inline
        texto = cls._INLINE_CODE.sub(
            lambda m: cor(Cor.VERDE, f"`{m.group(1)}`"), texto
        )

        # Itens de lista
        texto = cls._LIST_ITEM.sub(
            lambda m: m.group(0).replace(m.group(1).strip(), cor(Cor.AMARELO, "•")), texto
        )

        # Quebra de linha com wrap adequado
        linhas = texto.split("\n")
        resultado = []
        w = _largura_terminal() - 4
        for l in linhas:
            raw = Cor.strip(l)
            if len(raw) > w:
                # Quebra linhas longas preservando indentação
                indent = len(raw) - len(raw.lstrip())
                wrapped = textwrap.fill(
                    raw, width=w,
                    initial_indent="  ",
                    subsequent_indent="  " + " " * indent
                )
                resultado.append(wrapped)
            else:
                resultado.append("  " + l if l.strip() else "")
        return "\n".join(resultado)


# ─────────────────────────────────────────────
#  SEGURANÇA
# ─────────────────────────────────────────────

class Sanitizador:
    """
    Defesa contra prompt injection, path traversal e inputs maliciosos.
    OWASP A03 (Injection), A01 (Broken Access Control).
    """

    # Padrões de prompt injection conhecidos
    _INJECTION_PATTERNS = re.compile(
        r"(ignore\s+(all\s+)?previous\s+instructions?"
        r"|forget\s+(everything|all)"
        r"|you\s+are\s+now\s+(?:a\s+)?(?:dan|jailbreak|unrestricted)"
        r"|system\s*:\s*(?:override|ignore|reset)"
        r"|<\s*/?system\s*>"
        r"|###\s*(?:system|override|admin|root)"
        r"|\[INST\]|\[\/INST\]"
        r"|<\|im_start\|>|<\|im_end\|>"
        r"|do\s+anything\s+now"
        r"|pretend\s+(?:you\s+(?:are|have)\s+no\s+restrictions?)"
        r"|bypass\s+(?:all\s+)?restrictions?)",
        re.IGNORECASE,
    )

    # Limites de tamanho
    MAX_MSG_LEN = 8_000   # ~2k tokens, evita context stuffing
    MAX_FILE_SIZE = 512 * 1024  # 512 KB para arquivos carregados

    @classmethod
    def validar_mensagem(cls, texto: str) -> tuple[str, list[str]]:
        """
        Retorna (texto_sanitizado, lista_de_avisos).
        Nunca lança exceção — o chamador decide o que fazer com avisos.
        """
        avisos: list[str] = []

        if not isinstance(texto, str):
            return "", ["Tipo de entrada inválido."]

        # Trunca entradas excessivamente longas
        if len(texto) > cls.MAX_MSG_LEN:
            texto = texto[:cls.MAX_MSG_LEN]
            avisos.append(
                f"Mensagem truncada para {cls.MAX_MSG_LEN} caracteres."
            )

        # Detecta tentativa de injeção
        if cls._INJECTION_PATTERNS.search(texto):
            avisos.append("Possível tentativa de prompt injection detectada.")
            logger.warning("Prompt injection attempt: %r", texto[:200])

        # Remove caracteres de controle perigosos (exceto newline/tab)
        texto_limpo = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", texto)
        if texto_limpo != texto:
            avisos.append("Caracteres de controle removidos da entrada.")
            texto = texto_limpo

        return texto, avisos

    @classmethod
    def validar_caminho_arquivo(cls, caminho: str) -> Path:
        """
        Valida e resolve caminho de arquivo de forma segura.
        Previne path traversal (OWASP A01).
        """
        if not isinstance(caminho, str) or not caminho.strip():
            raise ValueError("Caminho de arquivo inválido.")

        # Apenas .json permitido para carregamento
        if not caminho.endswith(".json"):
            raise ValueError("Apenas arquivos .json são aceitos.")

        # Resolve path absoluto
        path = Path(caminho).resolve()

        # Restringe ao diretório atual e ~/.gwen/saves/
        allowed_dirs = [
            Path.cwd(),
            Path.home() / ".gwen" / "saves",
        ]
        if not any(path.is_relative_to(d) for d in allowed_dirs):
            raise PermissionError(
                f"Acesso negado: '{caminho}' fora dos diretórios permitidos."
            )

        return path

    @classmethod
    def validar_nome_personalidade(cls, nome: str) -> str:
        """Aceita apenas nomes alfanuméricos simples."""
        if not re.match(r"^[a-z_]{1,32}$", nome, re.IGNORECASE):
            raise ValueError(
                f"Nome de personalidade inválido: '{nome}'. "
                "Use apenas letras e underscores (máx. 32 chars)."
            )
        return nome.lower()


def _hash_api_key(key: str) -> str:
    """Gera hash seguro da chave para logging (nunca loga a chave em si)."""
    return hmac.new(b"gwen-v2", key.encode(), hashlib.sha256).hexdigest()[:12]


# ─────────────────────────────────────────────
#  GERENCIADOR DE CONTEXTO / MEMÓRIA
# ─────────────────────────────────────────────

@dataclass
class Mensagem:
    role: str
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_api(self) -> dict:
        """Formato esperado pela API Groq/OpenAI."""
        return {"role": self.role, "content": self.content}

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content, "timestamp": self.timestamp}

    @staticmethod
    def from_dict(d: dict) -> "Mensagem":
        return Mensagem(
            role=d["role"],
            content=d["content"],
            timestamp=d.get("timestamp", ""),
        )


class GerenciadorContexto:
    """
    Gerencia o histórico de conversa com limite de tokens estimado.
    Implementa sliding window para evitar overflow de contexto.
    CRÍTICO: previne vazamento de memória em sessões longas.
    """

    # llama-3.3-70b tem 128k context. Usamos 10% do limite como margem de segurança.
    # 1 token ≈ 4 chars; limite conservador: ~12k tokens = ~48k chars de histórico
    MAX_HISTORICO_CHARS = 48_000
    # Mínimo de turnos a preservar sempre (para manter coerência)
    MIN_TURNS = 4

    def __init__(self) -> None:
        self._msgs: list[Mensagem] = []

    def adicionar(self, role: str, content: str) -> None:
        self._msgs.append(Mensagem(role=role, content=content))
        self._compactar_se_necessario()

    def _compactar_se_necessario(self) -> None:
        total = sum(len(m.content) for m in self._msgs)
        while total > self.MAX_HISTORICO_CHARS and len(self._msgs) > self.MIN_TURNS * 2:
            # Remove o par mais antigo (user + assistant), preservando coerência
            self._msgs.pop(0)
            if self._msgs:
                self._msgs.pop(0)
            total = sum(len(m.content) for m in self._msgs)

    def para_api(self) -> list[dict]:
        return [m.to_api() for m in self._msgs]

    def para_exportacao(self) -> list[dict]:
        return [m.to_dict() for m in self._msgs]

    @staticmethod
    def de_importacao(dados: list[dict]) -> "GerenciadorContexto":
        gc = GerenciadorContexto()
        for d in dados:
            if isinstance(d, dict) and "role" in d and "content" in d:
                gc._msgs.append(Mensagem.from_dict(d))
        return gc

    def limpar(self) -> None:
        self._msgs.clear()

    def __len__(self) -> int:
        return len(self._msgs)

    def __iter__(self):
        return iter(self._msgs)

    @property
    def tokens_estimados(self) -> int:
        return sum(len(m.content) for m in self._msgs) // 4

    @property
    def msgs_usuario(self) -> int:
        return sum(1 for m in self._msgs if m.role == "user")

    @property
    def msgs_assistente(self) -> int:
        return sum(1 for m in self._msgs if m.role == "assistant")


# ─────────────────────────────────────────────
#  PERSONALIDADES (Strategy Pattern)
# ─────────────────────────────────────────────

@dataclass(frozen=True)
class Personalidade:
    nome: str
    descricao: str
    system_prompt: str
    temperatura: float = 0.7
    max_tokens: int = 2048
    emoji: str = "·"


class RegistroPersonalidades:
    """Registro imutável de personalidades. Extensível sem modificar código existente."""

    _CATALOGO: dict[str, Personalidade] = {
        "assistente": Personalidade(
            nome="assistente",
            descricao="Assistente geral, amigável e equilibrado",
            emoji="◆",
            temperatura=0.7,
            max_tokens=2048,
            system_prompt=(
                "Você é Gwen, uma assistente de IA inteligente e prestativa. "
                "Responda sempre em português do Brasil, de forma clara, precisa e natural. "
                "Seja direto e objetivo, sem introduções desnecessárias. "
                "Quando não souber algo com certeza, diga explicitamente. "
                "Evite repetir informações já mencionadas na conversa. "
                "Adapte o tom ao contexto: informal em bate-papo, técnico em código, didático ao ensinar."
            ),
        ),
        "programador": Personalidade(
            nome="programador",
            descricao="Especialista em código Python, JS, sistemas",
            emoji="⌘",
            temperatura=0.3,  # Mais determinístico para código
            max_tokens=4096,
            system_prompt=(
                "Você é Gwen, uma engenheira de software sênior especializada em Python, "
                "JavaScript, TypeScript, sistemas Linux e arquitetura de software. "
                "Responda em português do Brasil. "
                "Ao escrever código: use boas práticas, type hints, docstrings quando relevante. "
                "Prefira exemplos concretos e funcionais a explicações abstratas. "
                "Aponte problemas de segurança, performance e manutenibilidade quando relevantes. "
                "Seja preciso e nunca invente APIs, funções ou comportamentos que não existem. "
                "Se não tiver certeza, diga qual versão/contexto pode afetar a resposta."
            ),
        ),
        "professor": Personalidade(
            nome="professor",
            descricao="Ensino didático do simples ao complexo",
            emoji="◉",
            temperatura=0.6,
            max_tokens=3000,
            system_prompt=(
                "Você é Gwen, uma professora paciente e didática. Responda em português do Brasil. "
                "Ensine do simples ao complexo, usando analogias do cotidiano quando útil. "
                "Verifique a compreensão com perguntas breves quando o assunto for complexo. "
                "Use exemplos concretos. Nunca simplifique tanto a ponto de ser impreciso. "
                "Se detectar um equívoco na pergunta, corrija gentilmente antes de responder. "
                "Ao explicar conceitos técnicos, conecte-os ao conhecimento que o usuário já demonstrou."
            ),
        ),
        "criativo": Personalidade(
            nome="criativo",
            descricao="Escrita criativa, brainstorming, ideias",
            emoji="◈",
            temperatura=0.9,  # Mais criativo
            max_tokens=3000,
            system_prompt=(
                "Você é Gwen, uma parceira criativa imaginativa. Responda em português do Brasil. "
                "Ajude com escrita criativa, histórias, brainstorming, conceitos visuais e ideias. "
                "Seja original, evite clichês e soluções óbvias. "
                "Quando der sugestões, dê opções diversas ao invés de uma única resposta. "
                "Mantenha consistência interna em universos ficcionais. "
                "Ao colaborar em texto criativo, preserve o estilo e voz do usuário."
            ),
        ),
        "analista": Personalidade(
            nome="analista",
            descricao="Análise crítica, dados, argumentação lógica",
            emoji="◇",
            temperatura=0.4,
            max_tokens=3000,
            system_prompt=(
                "Você é Gwen, uma analista rigorosa. Responda em português do Brasil. "
                "Analise argumentos com pensamento crítico. Identifique premissas, falácias e lacunas. "
                "Ao avaliar dados: considere fontes, metodologia e possíveis vieses. "
                "Apresente múltiplos ângulos antes de concluir. "
                "Diferencie claramente fatos verificáveis de interpretações e opiniões. "
                "Seja precisa em linguagem: evite generalizações excessivas."
            ),
        ),
    }

    @classmethod
    def obter(cls, nome: str) -> Optional[Personalidade]:
        return cls._CATALOGO.get(nome)

    @classmethod
    def listar(cls) -> dict[str, Personalidade]:
        return dict(cls._CATALOGO)

    @classmethod
    def existe(cls, nome: str) -> bool:
        return nome in cls._CATALOGO


# ─────────────────────────────────────────────
#  CLIENTE DE API (Abstração + Implementação Groq)
# ─────────────────────────────────────────────

class ErroAPI(Exception):
    """Erros originados na chamada à API LLM."""
    def __init__(self, msg: str, retentavel: bool = False):
        super().__init__(msg)
        self.retentavel = retentavel


class ClienteLLM(ABC):
    """Interface abstrata para cliente LLM. Facilita mock em testes e troca de provider."""

    @abstractmethod
    def completar(
        self,
        system: str,
        historico: list[dict],
        temperatura: float,
        max_tokens: int,
    ) -> str: ...


class ClienteGroq(ClienteLLM):
    """
    Cliente Groq com retry exponencial e tratamento granular de erros.
    Nunca expõe a API key em logs ou mensagens de erro.
    """

    MODELO = "llama-3.3-70b-versatile"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # segundos

    def __init__(self, api_key: str) -> None:
        try:
            from groq import Groq, APIError, RateLimitError, APIConnectionError
            self._groq_cls_error = APIError
            self._groq_rate_error = RateLimitError
            self._groq_conn_error = APIConnectionError
            self._client = Groq(api_key=api_key)
        except ImportError:
            raise ErroAPI(
                "Biblioteca 'groq' não instalada. Execute: pip install groq"
            )

        logger.info("ClienteGroq inicializado. key_hash=%s", _hash_api_key(api_key))

    def completar(
        self,
        system: str,
        historico: list[dict],
        temperatura: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        msgs = [{"role": "system", "content": system}, *historico]

        for tentativa in range(1, self.MAX_RETRIES + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.MODELO,
                    max_tokens=max_tokens,
                    temperature=temperatura,
                    messages=msgs,
                )
                conteudo = resp.choices[0].message.content
                if not conteudo:
                    raise ErroAPI("Resposta vazia da API.", retentavel=True)
                logger.info(
                    "Completion OK. tokens_in=%s tokens_out=%s",
                    resp.usage.prompt_tokens if resp.usage else "?",
                    resp.usage.completion_tokens if resp.usage else "?",
                )
                return conteudo

            except self._groq_rate_error:
                delay = self.RETRY_BASE_DELAY * (2 ** tentativa)
                logger.warning("Rate limit atingido. Aguardando %.1fs (tentativa %d)", delay, tentativa)
                if tentativa == self.MAX_RETRIES:
                    raise ErroAPI(
                        f"Limite de requisições atingido. Aguarde {delay:.0f}s e tente novamente.",
                        retentavel=False,
                    )
                time.sleep(delay)

            except self._groq_conn_error as e:
                logger.error("Erro de conexão: %s (tentativa %d)", e, tentativa)
                if tentativa == self.MAX_RETRIES:
                    raise ErroAPI(
                        "Falha de conexão com a API. Verifique sua internet.",
                        retentavel=True,
                    )
                time.sleep(self.RETRY_BASE_DELAY * tentativa)

            except self._groq_cls_error as e:
                # Nunca inclui status_code na mensagem ao usuário para não vazar detalhes internos
                status = getattr(e, "status_code", 0)
                logger.error("APIError status=%s: %s", status, e)

                if status == 401:
                    raise ErroAPI("API key inválida ou expirada.", retentavel=False)
                elif status == 429:
                    raise ErroAPI("Cota de requisições excedida.", retentavel=False)
                elif status and status >= 500:
                    if tentativa < self.MAX_RETRIES:
                        time.sleep(self.RETRY_BASE_DELAY * tentativa)
                        continue
                    raise ErroAPI("Serviço temporariamente indisponível.", retentavel=True)
                else:
                    raise ErroAPI(f"Erro na API: {e}", retentavel=False)

            except Exception as e:
                logger.exception("Erro inesperado na API")
                raise ErroAPI(f"Erro inesperado: {type(e).__name__}", retentavel=False)

        raise ErroAPI("Máximo de tentativas atingido.", retentavel=True)


# ─────────────────────────────────────────────
#  PERSISTÊNCIA (Repository Pattern)
# ─────────────────────────────────────────────

class RepositorioConversa:
    """
    Salva/carrega conversas com validação de integridade.
    Previne path traversal e injeção via JSON malicioso.
    """

    VERSAO_SCHEMA = 2
    _SAVES_DIR = Path.home() / ".gwen" / "saves"

    def __init__(self) -> None:
        self._SAVES_DIR.mkdir(parents=True, exist_ok=True)

    def salvar(
        self,
        contexto: GerenciadorContexto,
        personalidade: str,
        nome: str | None = None,
    ) -> Path:
        if len(contexto) == 0:
            raise ValueError("Nenhuma conversa para salvar.")

        if nome is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            nome = f"gwen_{ts}.json"

        path = Sanitizador.validar_caminho_arquivo(
            str(self._SAVES_DIR / nome) if not os.sep in nome else nome
        )

        dados = {
            "_schema_version": self.VERSAO_SCHEMA,
            "timestamp": datetime.now().isoformat(),
            "personalidade": personalidade,
            "mensagens": contexto.para_exportacao(),
        }

        # Escrita atômica: escreve em temp e renomeia
        tmp = path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            tmp.rename(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

        logger.info("Conversa salva em %s (%d msgs)", path, len(contexto))
        return path

    def carregar(self, caminho: str) -> tuple[GerenciadorContexto, str]:
        path = Sanitizador.validar_caminho_arquivo(caminho)

        if not path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {path.name}")

        if path.stat().st_size > Sanitizador.MAX_FILE_SIZE:
            raise ValueError("Arquivo muito grande para carregar.")

        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)

        self._validar_schema(raw)

        mensagens_raw = raw.get("mensagens", raw.get("historico", []))
        personalidade = raw.get("personalidade", "assistente")

        # Valida cada mensagem antes de aceitar
        mensagens_validas = []
        for m in mensagens_raw:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "")
            content = m.get("content", "")
            if role not in ("user", "assistant") or not isinstance(content, str):
                logger.warning("Mensagem inválida ignorada: %r", m)
                continue
            # Sanitiza conteúdo carregado
            content_limpo, avisos = Sanitizador.validar_mensagem(content)
            for av in avisos:
                logger.warning("Arquivo carregado: %s", av)
            mensagens_validas.append({"role": role, "content": content_limpo})

        contexto = GerenciadorContexto.de_importacao(mensagens_validas)
        logger.info("Conversa carregada: %s (%d msgs)", path.name, len(contexto))
        return contexto, personalidade

    @staticmethod
    def _validar_schema(dados: dict) -> None:
        """Rejeita JSONs malformados ou de versão incompatível."""
        if not isinstance(dados, dict):
            raise ValueError("Formato de arquivo inválido.")
        # Aceita v1 (legado) e v2
        versao = dados.get("_schema_version", 1)
        if versao not in (1, 2):
            raise ValueError(f"Schema versão {versao} não suportada.")


# ─────────────────────────────────────────────
#  INICIALIZAÇÃO SEGURA DA API KEY
# ─────────────────────────────────────────────

def _obter_api_key() -> str:
    """
    Obtém a API key de forma segura.
    Ordem: variável de ambiente → arquivo ~/.gwen/key → entrada interativa.
    Nunca escreve a chave em disco em texto simples sem consentimento.
    """
    # 1. Variável de ambiente (prioritária)
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if key:
        logger.info("API key obtida via variável de ambiente.")
        return key

    # 2. Arquivo de chave do usuário (opcional, gerado pelo próprio Gwen)
    key_file = Path.home() / ".gwen" / "key"
    if key_file.exists() and key_file.stat().st_mode & 0o077 == 0:
        key = key_file.read_text().strip()
        if key:
            logger.info("API key carregada de %s", key_file)
            return key

    # 3. Entrada interativa — nunca ecoa a chave
    badge_aviso("GROQ_API_KEY não encontrada no ambiente.")
    print()

    try:
        import getpass
        chave = getpass.getpass(
            f"  {cor(Cor.CINZA, 'Cole sua chave Groq (não será exibida): ')}"
        ).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        badge_erro("Inicialização cancelada.")
        sys.exit(1)

    if not chave:
        badge_erro("Nenhuma chave fornecida.")
        sys.exit(1)

    # Validação básica de formato (gsk_ + 56 chars alfanuméricos)
    if not re.match(r"^gsk_[A-Za-z0-9]{50,}$", chave):
        badge_aviso("A chave não parece ter o formato padrão Groq (gsk_...).")
        badge_info("Continuando mesmo assim — a API confirmará se é válida.")

    # Oferecer salvar (com permissão explícita do usuário)
    try:
        resposta = input(
            f"\n  {cor(Cor.CINZA, 'Salvar chave em ~/.gwen/key para próximas sessões? [s/N] ')}"
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        resposta = "n"

    if resposta == "s":
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text(chave)
        key_file.chmod(0o600)  # Só o dono pode ler
        badge_ok(f"Chave salva em {key_file} (permissão 600).")
        print()

    return chave


# ─────────────────────────────────────────────
#  ESTATÍSTICAS DE SESSÃO
# ─────────────────────────────────────────────

@dataclass
class EstatisticasSessao:
    inicio: datetime = field(default_factory=datetime.now)
    total_requisicoes: int = 0
    erros: int = 0
    tempo_total_resposta: float = 0.0
    trocas_personalidade: int = 0

    @property
    def tempo_medio_resposta(self) -> float:
        if self.total_requisicoes == 0:
            return 0.0
        return self.tempo_total_resposta / self.total_requisicoes

    @property
    def duracao_sessao(self) -> str:
        delta = datetime.now() - self.inicio
        mins, secs = divmod(int(delta.total_seconds()), 60)
        horas, mins = divmod(mins, 60)
        if horas:
            return f"{horas}h {mins}m"
        return f"{mins}m {secs}s"


# ─────────────────────────────────────────────
#  PROCESSADOR DE COMANDOS (Command Pattern)
# ─────────────────────────────────────────────

@dataclass
class ComandoCLI:
    nome: str
    args: list[str]


class ProcessadorComandos:
    """
    Despacha comandos /cmd para handlers registrados.
    Separação clara de responsabilidades — o agente não conhece UI.
    """

    def __init__(self, agente: "GwenAgente") -> None:
        self._agente = agente
        self._handlers: dict[str, callable] = {
            "sair":         self._cmd_sair,
            "ajuda":        self._cmd_ajuda,
            "historico":    self._cmd_historico,
            "limpar":       self._cmd_limpar,
            "modos":        self._cmd_modos,
            "modo":         self._cmd_modo,
            # Compatibilidade com v1
            "personalidade":self._cmd_modo,
            "listar":       self._cmd_modos,
            "salvar":       self._cmd_salvar,
            "carregar":     self._cmd_carregar,
            "stats":        self._cmd_stats,
        }

    def processar(self, cmd: ComandoCLI) -> bool:
        """Retorna False se deve encerrar o loop principal."""
        handler = self._handlers.get(cmd.nome)
        if handler is None:
            badge_erro(f"Comando desconhecido: /{cmd.nome}  (use /ajuda)")
            print()
            return True
        return handler(cmd.args)

    # ── Handlers ──────────────────────────────

    def _cmd_sair(self, _) -> bool:
        print(f"\n  {cor(Cor.CINZA, 'Até logo.')}\n")
        logger.info("Sessão encerrada pelo usuário.")
        return False

    def _cmd_ajuda(self, _) -> bool:
        menu_ajuda()
        return True

    def _cmd_historico(self, _) -> bool:
        ctx = self._agente.contexto
        if not len(ctx):
            badge_info("Nenhuma conversa ainda.")
            print()
            return True

        w = _largura_terminal()
        print()
        linha("─", w)
        for msg in ctx:
            if msg.role == "user":
                prefixo = cor(Cor.VERDE, "  você  ")
            else:
                prefixo = cor(Cor.ROXO, "  gwen  ")

            conteudo = msg.content
            if len(conteudo) > 400:
                conteudo = conteudo[:397] + "..."

            print(f"{prefixo}{cor(Cor.DIM, msg.timestamp[:16])}")
            print(f"  {conteudo}")
            print()
        linha("─", w)
        print()
        return True

    def _cmd_limpar(self, _) -> bool:
        self._agente.contexto.limpar()
        badge_ok("Conversa reiniciada.")
        print()
        return True

    def _cmd_modos(self, _) -> bool:
        w = _largura_terminal()
        print()
        linha("─", w)
        atual = self._agente.personalidade_atual
        for nome, p in RegistroPersonalidades.listar().items():
            ativo = nome == atual
            marca = cor(Cor.VERDE, f" {p.emoji}") if ativo else cor(Cor.CINZA, f" {p.emoji}")
            nome_fmt = cor(Cor.AMARELO + Cor.BOLD, nome) if ativo else cor(Cor.BRANCO, nome)
            desc = cor(Cor.CINZA, p.descricao)
            print(f"  {marca} {nome_fmt:<20} {desc}")
        linha("─", w)
        print()
        return True

    def _cmd_modo(self, args: list[str]) -> bool:
        if not args:
            badge_aviso("uso: /modo <nome>  |  use /modos para listar")
            print()
            return True
        try:
            nome = Sanitizador.validar_nome_personalidade(args[0])
        except ValueError as e:
            badge_erro(str(e))
            print()
            return True

        if not RegistroPersonalidades.existe(nome):
            badge_erro(f"Personalidade '{nome}' não existe. Use /modos.")
            print()
            return True

        self._agente.definir_personalidade(nome)
        p = RegistroPersonalidades.obter(nome)
        badge_ok(
            f"Modo: {cor(Cor.ROXO, nome)}  {cor(Cor.CINZA, f'— {p.descricao}')}"
        )
        print()
        return True

    def _cmd_salvar(self, args: list[str]) -> bool:
        nome = args[0] if args else None
        repo = RepositorioConversa()
        try:
            path = repo.salvar(self._agente.contexto, self._agente.personalidade_atual, nome)
            badge_ok(f"Salvo em {cor(Cor.CIANO, str(path))}")
        except ValueError as e:
            badge_info(str(e))
        except Exception as e:
            badge_erro(f"Erro ao salvar: {e}")
            logger.exception("Erro ao salvar conversa")
        print()
        return True

    def _cmd_carregar(self, args: list[str]) -> bool:
        if not args:
            badge_aviso("uso: /carregar <arquivo.json>")
            print()
            return True
        repo = RepositorioConversa()
        try:
            contexto, personalidade = repo.carregar(args[0])
            self._agente.contexto = contexto
            self._agente.definir_personalidade(personalidade)
            badge_ok(
                f"{len(contexto)} mensagens carregadas  "
                f"{cor(Cor.CINZA, f'[modo: {personalidade}]')}"
            )
        except (FileNotFoundError, PermissionError, ValueError) as e:
            badge_erro(str(e))
        except Exception as e:
            badge_erro(f"Erro ao carregar: {e}")
            logger.exception("Erro ao carregar conversa")
        print()
        return True

    def _cmd_stats(self, _) -> bool:
        st = self._agente.stats
        ctx = self._agente.contexto
        w = _largura_terminal()

        def row(label: str, valor: str) -> None:
            print(f"  {cor(Cor.CINZA, f'{label:<22}')}{valor}")

        print()
        linha("─", w)
        row("modo atual",      cor(Cor.ROXO, self._agente.personalidade_atual))
        row("mensagens (você)", str(ctx.msgs_usuario))
        row("respostas (gwen)", str(ctx.msgs_assistente))
        row("tokens estimados", f"~{ctx.tokens_estimados:,}")
        row("requisições",     str(st.total_requisicoes))
        row("erros",           str(st.erros) if st.erros else cor(Cor.VERDE, "0"))
        row("tempo médio resp",f"{st.tempo_medio_resposta:.1f}s")
        row("duração sessão",  st.duracao_sessao)
        linha("─", w)
        print()
        return True


# ─────────────────────────────────────────────
#  AGENTE PRINCIPAL
# ─────────────────────────────────────────────

class GwenAgente:
    """
    Agente conversacional principal.
    Orquestra: cliente LLM, contexto, personalidades, segurança.
    """

    def __init__(self, cliente: ClienteLLM) -> None:
        self._cliente = cliente
        self.contexto = GerenciadorContexto()
        self.personalidade_atual = "assistente"
        self.stats = EstatisticasSessao()

    def definir_personalidade(self, nome: str) -> None:
        self.personalidade_atual = nome
        self.stats.trocas_personalidade += 1

    def _system_prompt(self) -> str:
        p = RegistroPersonalidades.obter(self.personalidade_atual)
        return p.system_prompt if p else RegistroPersonalidades.obter("assistente").system_prompt

    def conversar(self, mensagem: str) -> str:
        """
        Envia mensagem, obtém resposta, atualiza contexto.
        Toda a validação de segurança acontece aqui.
        """
        # Sanitização de entrada
        mensagem_limpa, avisos = Sanitizador.validar_mensagem(mensagem)
        for av in avisos:
            logger.warning("Input sanitization: %s", av)

        if not mensagem_limpa.strip():
            return ""

        p = RegistroPersonalidades.obter(self.personalidade_atual)
        temperatura = p.temperatura if p else 0.7
        max_tokens = p.max_tokens if p else 2048

        self.contexto.adicionar("user", mensagem_limpa)

        inicio = time.monotonic()
        try:
            resposta = self._cliente.completar(
                system=self._system_prompt(),
                historico=self.contexto.para_api()[:-1],  # Exclui a msg que acabou de adicionar
                temperatura=temperatura,
                max_tokens=max_tokens,
            )
            # Adiciona apenas após sucesso (evita duplicação em retry)
            self.contexto.adicionar("assistant", resposta)
            self.stats.total_requisicoes += 1
            self.stats.tempo_total_resposta += time.monotonic() - inicio
            return resposta

        except ErroAPI:
            # Remove a mensagem do usuário que acabou de adicionar se houver falha
            self.contexto._msgs.pop()
            self.stats.erros += 1
            raise


# ─────────────────────────────────────────────
#  LOOP PRINCIPAL CLI
# ─────────────────────────────────────────────

class GwenCLI:
    """Camada de apresentação CLI. Separa completamente UI de lógica de negócio."""

    def __init__(self, agente: GwenAgente) -> None:
        self._agente = agente
        self._processador = ProcessadorComandos(agente)

    def executar(self) -> None:
        p = RegistroPersonalidades.obter(self._agente.personalidade_atual)
        cabecalho(self._agente.personalidade_atual, ClienteGroq.MODELO)
        menu_ajuda()

        while True:
            try:
                entrada = self._ler_entrada()
                if entrada is None:
                    continue

                if entrada.startswith("/"):
                    partes = entrada.split()
                    cmd = ComandoCLI(
                        nome=partes[0][1:].lower(),
                        args=partes[1:],
                    )
                    continuar = self._processador.processar(cmd)
                    if not continuar:
                        break
                else:
                    self._processar_mensagem(entrada)

            except KeyboardInterrupt:
                print(f"\n\n  {cor(Cor.CINZA, 'Até logo.')}\n")
                logger.info("Sessão encerrada via Ctrl+C.")
                break
            except EOFError:
                # Pipe fechado — encerra silenciosamente
                break

    def _ler_entrada(self) -> str | None:
        try:
            print(f"{cor(Cor.VERDE, '›')} ", end="", flush=True)
            entrada = input().strip()
            return entrada if entrada else None
        except EOFError:
            raise

    def _processar_mensagem(self, mensagem: str) -> None:
        with Spinner("pensando"):
            try:
                resposta = self._agente.conversar(mensagem)
            except ErroAPI as e:
                print()
                badge_erro(str(e))
                if e.retentavel:
                    badge_info("Tente novamente ou verifique sua conexão.")
                print()
                return

        if not resposta:
            return

        w = _largura_terminal()
        print()
        linha("─", w, Cor.CINZA)
        print(f"  {cor(Cor.ROXO + Cor.BOLD, 'gwen')}")
        print()
        texto_renderizado = RenderCLI.render(resposta)
        print(texto_renderizado)
        print()
        linha("─", w, Cor.CINZA)
        print()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

def main() -> None:
    print(f"\n  {cor(Cor.CINZA, 'inicializando gwen...')}")

    api_key = _obter_api_key()

    try:
        cliente = ClienteGroq(api_key)
        print(f"  {cor(Cor.VERDE, '✓')} {cor(Cor.CINZA, 'conectado à API Groq')}\n")
    except ErroAPI as e:
        badge_erro(str(e))
        sys.exit(1)

    agente = GwenAgente(cliente)
    cli = GwenCLI(agente)
    cli.executar()


if __name__ == "__main__":
    main()