"""Identidade visual: brasão, bandeiras, logos de partidos, fotos e cartões de candidato."""
from __future__ import annotations

import base64
import html
import unicodedata
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"

CORES = {
    "PT": "#c4122d", "PL": "#1f3c88", "UNIAO": "#22b8cf", "PSD": "#e09f00", "MDB": "#2e8b57",
    "PP": "#9775fa", "REPUBLICANOS": "#94d82d", "PSB": "#e8590c", "PDT": "#d9480f", "PSDB": "#1c7ed6",
    "PSOL": "#e6b800", "NOVO": "#f76707", "PODE": "#20c997", "AVANTE": "#ae3ec9", "SOLIDARIEDADE": "#f59f00",
    "CIDADANIA": "#e64980", "PCDOB": "#a61e4d", "REDE": "#12b886", "PV": "#2f9e44", "PRD": "#1b998b",
    "MOBILIZA": "#6b2c91", "AGIR": "#1864ab", "DC": "#1971c2", "PRTB": "#5c940d", "PSTU": "#c92a2a",
    "PCO": "#c92a2a", "PCB": "#a51111", "UP": "#212529", "PMB": "#5f3dc4", "MISSAO": "#111111",
}


def chave_partido(sigla: str) -> str:
    """'UNIÃO' -> 'UNIAO', 'PC do B' -> 'PCDOB'."""
    s = unicodedata.normalize("NFD", (sigla or "").upper())
    return "".join(c for c in s if c.isalnum() and not unicodedata.combining(c))


def cor_partido(sigla: str) -> str:
    return CORES.get(chave_partido(sigla), "#64748b")


def mapa_cores(siglas) -> dict:
    return {s: cor_partido(s) for s in siglas}


@lru_cache(maxsize=256)
def _data_uri(caminho: str) -> str:
    p = Path(caminho)
    if not p.exists():
        return ""
    mime = {".png": "image/png", ".svg": "image/svg+xml", ".jpg": "image/jpeg"}[p.suffix.lower()]
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def logo_partido(sigla: str, quadrado: bool = False) -> str:
    """quadrado=True: versão com margem para colunas de imagem do st.dataframe (que recortam)."""
    pasta = "partidos_q" if quadrado else "partidos"
    return _data_uri(str(ASSETS / pasta / f"{chave_partido(sigla)}.png"))


def bandeira(uf: str) -> str:
    if uf.upper() == "BR":
        return _data_uri(str(ASSETS / "br.svg"))
    return _data_uri(str(ASSETS / "bandeiras" / f"{uf.upper()}.png"))


def brasao() -> str:
    return _data_uri(str(ASSETS / "brasao.png"))


def _iniciais(nome: str) -> str:
    partes = nome.split() or ["?"]
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()


CSS = """
<style>
.block-container {padding: 3.2rem 1.6rem 2rem 1.6rem; max-width: 100% !important;}
.hdr {display:flex; align-items:center; gap:18px; padding:14px 22px; border-radius:14px;
      background:linear-gradient(90deg,#0b2a5b 0%,#123d7a 70%,#0f5132 100%); color:#fff; margin-bottom:14px;}
.hdr img.brasao {height:68px;}
.hdr .t1 {font-size:1.65rem; font-weight:800; letter-spacing:.3px; line-height:1.1;}
.hdr .t2 {font-size:.92rem; opacity:.85; margin-top:4px;}
.hdr .sp {flex:1;}
.hdr img.flag {height:44px; border-radius:4px; box-shadow:0 0 0 2px rgba(255,255,255,.35);}
.selo {display:inline-block; padding:3px 10px; border-radius:999px; background:rgba(255,255,255,.14);
       font-size:.72rem; margin-left:8px; vertical-align:middle; border:1px solid rgba(255,255,255,.3);}
.sec {display:flex; align-items:center; gap:10px; margin:10px 0 6px;}
.sec img {height:26px; border-radius:3px; box-shadow:0 0 0 1px rgba(0,0,0,.12);}
.sec span {font-size:1.35rem; font-weight:700;}
.cards {display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:12px; margin:6px 0 14px;}
.card {border:1px solid rgba(128,128,128,.25); border-radius:14px; padding:12px 14px; position:relative;
       background:rgba(128,128,128,.04);}
.card.lider {border:2px solid var(--cor); background:rgba(128,128,128,.07);}
.card .top {display:flex; gap:12px; align-items:center;}
.av {width:64px; height:64px; border-radius:50%; position:relative; flex:none; overflow:hidden;
     background:var(--cor); color:#fff; display:flex; align-items:center; justify-content:center;
     font-weight:800; font-size:1.3rem; box-shadow:0 0 0 3px var(--cor);}
.av .ph {position:absolute; inset:0; background-size:cover; background-position:center 28%;}
.nm {font-weight:700; font-size:1.02rem; line-height:1.15;}
.pt {display:flex; flex-wrap:wrap; align-items:center; gap:6px; font-size:.8rem; opacity:.85; margin-top:3px;}
.pt img {height:20px; max-width:56px; object-fit:contain; background:#fff; border-radius:3px; padding:1px;}
.num {font-size:.75rem; opacity:.6;}
.pc {font-size:1.6rem; font-weight:800; margin-top:8px;}
.vt {font-size:.82rem; opacity:.75;}
.bar {height:7px; border-radius:6px; background:rgba(128,128,128,.2); margin-top:6px; overflow:hidden;}
.bar div {height:100%; background:var(--cor);}
.tag {position:absolute; top:10px; right:10px; font-size:.68rem; font-weight:700; padding:2px 8px;
      border-radius:999px; background:#2f9e44; color:#fff;}
.tag.t2 {background:#f08c00;}
.tag.ld {background:var(--cor);}
.rodape {font-size:.78rem; opacity:.65; margin-top:18px;}
</style>
"""


def cabecalho_html(subtitulo: str, demo: bool) -> str:
    selo = '<span class="selo">DADOS FICTÍCIOS</span>' if demo else '<span class="selo">painel não oficial</span>'
    return f"""
<div class="hdr">
  <img class="brasao" src="{brasao()}" alt="Brasão da República"/>
  <div><div class="t1">Eleições Gerais 2026 · Apuração{selo}</div><div class="t2">{html.escape(subtitulo)}</div></div>
  <div class="sp"></div>
  <img class="flag" src="{bandeira('BR')}" alt="Bandeira do Brasil"/>
</div>"""


def secao_html(titulo: str, uf: str | None = None) -> str:
    img = f'<img src="{bandeira(uf)}"/>' if uf else ""
    return f'<div class="sec">{img}<span>{html.escape(titulo)}</span></div>'


def _fmt(n) -> str:
    return f"{int(n):,}".replace(",", ".")


# Ajuste fino de enquadramento por candidato (chave = nome de urna sem acento/espaço, maiúsculo).
# background-position vertical maior = mostra uma parte mais baixa da foto.
AJUSTE_FOTO = {
    "SAMARA": "background-position:center 75%;background-size:125%;",
}


def cards_html(df, vagas: int = 1, maximo: int = 12, apurando: bool = True) -> str:
    """Cartões de candidatos (majoritários). Foto do TSE sobreposta às iniciais: se a foto
    não carregar, as iniciais na cor do partido aparecem."""
    itens = []
    for i, c in enumerate(df.head(maximo).itertuples()):
        cor = cor_partido(c.partido)
        foto = getattr(c, "foto", "") or ""
        ajuste = AJUSTE_FOTO.get(chave_partido(c.candidato), "")
        ph = f'<div class="ph" style="background-image:url(\'{foto}\');{ajuste}"></div>' if foto else ""
        logo = logo_partido(c.partido)
        logo_img = f'<img src="{logo}"/>' if logo else ""
        sit = (c.situacao or "").lower()
        if c.eleito or sit.startswith("eleito"):
            tag = '<span class="tag">ELEITO</span>'
        elif "2º turno" in sit or "2o turno" in sit:
            tag = '<span class="tag t2">2º TURNO</span>'
        elif apurando and i < vagas and c.votos > 0:
            tag = '<span class="tag ld">LIDERA</span>' if vagas == 1 else '<span class="tag ld">NAS VAGAS</span>'
        else:
            tag = ""
        lider = " lider" if i < vagas and c.votos > 0 else ""
        pct = f"{c.pct:.2f}".replace(".", ",")
        itens.append(f"""
<div class="card{lider}" style="--cor:{cor}">{tag}
  <div class="top">
    <div class="av">{html.escape(_iniciais(c.candidato))}{ph}</div>
    <div><div class="nm">{html.escape(c.candidato)}</div>
      <div class="pt">{logo_img}<b>{html.escape(c.partido)}</b><span class="num">· {html.escape(str(c.numero))}</span></div></div>
  </div>
  <div class="pc">{pct}%</div><div class="vt">{_fmt(c.votos)} votos</div>
  <div class="bar"><div style="width:{min(c.pct, 100):.2f}%"></div></div>
</div>""")
    return f'<div class="cards">{"".join(itens)}</div>'
