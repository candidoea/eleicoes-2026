"""Acesso HTTP ao TSE com limitador de taxa, cache em disco e cache negativo.

O cache em disco (pasta dados/cache) é o ponto de encontro entre o coletor e o app:
o coletor mantém os arquivos frescos; o app lê do disco e só vai à rede se o arquivo
estiver mais velho que o limite pedido.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

RAIZ = Path(os.getenv("APURACAO_DADOS", Path(__file__).parent / "dados")) / "cache"
NEG_TTL = 300  # s sem tentar de novo um arquivo que deu 403/404 (o TSE bloqueia IP por excesso de 404)


class NaoDisponivel(Exception):
    pass


class Limitador:
    """Token bucket thread-safe (requisições por segundo neste processo)."""

    def __init__(self, rps: float):
        self.rps, self.tokens, self.t = rps, rps, time.monotonic()
        self.lock = threading.Lock()

    def esperar(self):
        while True:
            with self.lock:
                agora = time.monotonic()
                self.tokens = min(self.rps, self.tokens + (agora - self.t) * self.rps)
                self.t = agora
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                falta = (1 - self.tokens) / self.rps
            time.sleep(falta)


limitador = Limitador(float(os.getenv("APURACAO_RPS", "20")))
_local = threading.local()


def _sessao() -> requests.Session:
    if not hasattr(_local, "s"):
        s = requests.Session()
        s.headers.update({"User-Agent": "ifrn-especializacao-apuracao/2.0"})
        _local.s = s
    return _local.s


def caminho(url: str) -> Path:
    u = urlparse(url)
    return RAIZ / u.netloc / u.path.lstrip("/")


def _gravar_atomico(p: Path, dados: bytes):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_bytes(dados)
    for i in range(10):  # no Windows o replace falha se outro processo estiver lendo
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    tmp.unlink(missing_ok=True)


def _ler(p: Path):
    for i in range(5):
        try:
            return json.loads(p.read_bytes())
        except (PermissionError, json.JSONDecodeError):
            time.sleep(0.05 * (i + 1))
    return json.loads(p.read_bytes())


def idade(url: str) -> float | None:
    p = caminho(url)
    return time.time() - p.stat().st_mtime if p.exists() else None


def obter(url: str, max_idade: float = 0, rede: bool = True, timeout: int = 20) -> dict:
    """Devolve o JSON da URL. Usa o disco se o arquivo tiver menos de `max_idade` s.
    rede=False: só disco (NaoDisponivel se não houver)."""
    p = caminho(url)
    neg = p.with_suffix(p.suffix + ".neg")
    meta = p.with_suffix(p.suffix + ".meta")
    if p.exists() and (not rede or time.time() - p.stat().st_mtime < max_idade):
        return _ler(p)
    if not rede:
        raise NaoDisponivel(f"sem cache local: {url}")
    if neg.exists() and time.time() - neg.stat().st_mtime < NEG_TTL:
        if p.exists():
            return _ler(p)
        raise NaoDisponivel(f"indisponível (cache negativo): {url}")

    headers = {}
    if p.exists() and meta.exists():
        try:
            m = json.loads(meta.read_text())
            if m.get("etag"):
                headers["If-None-Match"] = m["etag"]
            if m.get("lm"):
                headers["If-Modified-Since"] = m["lm"]
        except Exception:
            pass
    erro = None
    for tentativa in range(3):
        limitador.esperar()
        try:
            r = _sessao().get(url, headers=headers, timeout=timeout)
        except requests.RequestException as exc:
            erro = exc
            time.sleep(1.0 * (tentativa + 1))
            continue
        if r.status_code == 304 and p.exists():
            os.utime(p)
            return _ler(p)
        if r.status_code in (403, 404):
            neg.parent.mkdir(parents=True, exist_ok=True)
            neg.touch()
            if p.exists():
                return _ler(p)
            raise NaoDisponivel(f"{r.status_code} {url}")
        if r.status_code == 429 or r.status_code >= 500:
            erro = RuntimeError(f"HTTP {r.status_code}")
            time.sleep(2.0 * (tentativa + 1))
            continue
        r.raise_for_status()
        dados = r.json()
        _gravar_atomico(p, r.content)
        neg.unlink(missing_ok=True)
        try:
            meta.write_text(json.dumps({"etag": r.headers.get("ETag"), "lm": r.headers.get("Last-Modified")}))
        except OSError:
            pass
        return dados
    if p.exists():  # rede falhou: devolve o último conhecido
        return _ler(p)
    raise RuntimeError(f"Falha ao baixar {url}: {erro}")
