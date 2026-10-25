"""Mapas coropléticos (plotly) por município e por UF."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

import geo
import ui

SEM = "Sem apuração"
COR_SEM = "#8a8f98"
PALETA_EXTRA = px.colors.qualitative.Bold + px.colors.qualitative.Safe


def _rotulo(nome: str, partido: str) -> str:
    return f"{nome} ({partido})"


def _rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _distante(c: str, usadas: list[str], minimo: float = 90) -> bool:
    r = _rgb(c)
    return all(sum((a - b) ** 2 for a, b in zip(r, _rgb(u))) ** 0.5 >= minimo for u in usadas)


def cores_candidatos(rotulos: list[tuple[str, str]], maximo_distintos: int = 10) -> dict:
    """Cor do partido; se ficar parecida demais com a de um candidato mais votado (vários partidos
    usam azul), troca por uma cor bem distinta da paleta extra."""
    usadas, mapa = [], {}
    extra = [c for c in PALETA_EXTRA if c.startswith("#")] + ["#e599f7", "#ffd43b", "#63e6be", "#ff8787"]
    for i, (nome, partido) in enumerate(rotulos):
        cor = ui.cor_partido(partido)
        if i < maximo_distintos and not _distante(cor, usadas):
            cor = next((c for c in extra if _distante(c, usadas)), cor)
        usadas.append(cor)
        mapa[_rotulo(nome, partido)] = cor
    mapa[SEM] = COR_SEM
    return mapa


def resumo_vencedor(longo: pd.DataFrame, chave: str = "cd_ibge") -> pd.DataFrame:
    """1 linha por área: líder, 2º, margem, % seções."""
    if longo.empty:
        return pd.DataFrame()
    d = longo.sort_values([chave, "votos"], ascending=[True, False])
    g = d.groupby(chave, sort=False)
    p1 = g.nth(0).set_index(chave)
    p2 = g.nth(1).set_index(chave)
    cols = [c for c in ["municipio", "uf", "candidato", "partido", "pct", "votos", "pct_secoes", "validos"]
            if c in p1.columns]
    out = p1[cols].copy()
    out["segundo"] = (p2["candidato"] + " (" + p2["partido"] + ")").reindex(out.index)
    out["pct2"] = p2["pct"].reindex(out.index)
    out["margem"] = out["pct"] - out["pct2"].fillna(0)
    out["lider"] = [_rotulo(c, p) for c, p in zip(out["candidato"], out["partido"])]
    out.loc[out["votos"] <= 0, "lider"] = SEM
    return out.reset_index()


BRASIL_LON, BRASIL_LAT = (-74.2, -34.6), (-33.9, 5.4)


def _layout(fig, altura: int, legenda: bool = True, brasil: bool = False):
    fig.update_geos(fitbounds="locations", projection_type="mercator", visible=False, bgcolor="rgba(0,0,0,0)")
    dados = [tr for tr in fig.data if tr.hoverinfo != "skip"]  # o contorno das UFs mantém a linha grossa
    muitos = sum(len(tr.locations) if tr.locations is not None else 0 for tr in dados) > 60
    for tr in dados:
        tr.marker.line.width = 0.15 if muitos else 0.9
        tr.marker.line.color = "rgba(255,255,255,0.35)" if muitos else "rgba(255,255,255,0.85)"
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="top", y=0.0, x=0, title=None, font=dict(size=12)),
                      showlegend=legenda)
    return fig


def _contorno_ufs(fig, ufs: list[str] | None = None):
    """Sobrepõe as fronteiras estaduais (sem preenchimento) para dar leitura ao mapa municipal."""
    g = geo.ufs()
    if ufs:
        g = {"type": "FeatureCollection", "features": [f for f in g["features"] if f["properties"]["uf"] in ufs]}
    ids = [f["properties"]["codarea"] for f in g["features"]]
    fig.add_trace(go.Choropleth(geojson=g, locations=ids, z=[0] * len(ids), featureidkey="properties.codarea",
                                colorscale=[[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]], showscale=False,
                                marker_line_color="rgba(255,255,255,0.9)", marker_line_width=1.3, zmin=0, zmax=1,
                                hoverinfo="skip"))
    return fig


def vencedor(resumo: pd.DataFrame, geojson: dict, chave: str, altura: int, cores: dict,
             contorno_ufs: list[str] | None | bool = None, hover_nome: str = "municipio", brasil: bool = False) -> go.Figure:
    hover = {c: True for c in ["pct", "segundo", "pct2", "pct_secoes"] if c in resumo}
    hover |= {chave: False}
    fig = px.choropleth(resumo, geojson=geojson, locations=chave, featureidkey="properties.codarea",
                        color="lider", color_discrete_map=cores, hover_name=hover_nome if hover_nome in resumo else None,
                        hover_data=hover, labels={"pct": "% líder", "pct2": "% 2º", "segundo": "2º",
                                                  "pct_secoes": "% seções", "lider": "líder"},
                        category_orders={"lider": [k for k in cores if k in set(resumo["lider"])]})
    if contorno_ufs is not False and contorno_ufs is not None:
        _contorno_ufs(fig, contorno_ufs or None)
    return _layout(fig, altura, brasil=brasil)


def percentual(longo: pd.DataFrame, geojson: dict, chave: str, rotulo: str, altura: int,
               contorno_ufs=None, hover_nome="municipio", brasil: bool = False) -> go.Figure:
    nome, partido = rotulo.rsplit(" (", 1)
    partido = partido.rstrip(")")
    d = longo[(longo["candidato"] == nome) & (longo["partido"] == partido)]
    cor = ui.cor_partido(partido)
    fig = px.choropleth(d, geojson=geojson, locations=chave, featureidkey="properties.codarea", color="pct",
                        color_continuous_scale=[[0, "#f1f3f5"], [1, cor]], range_color=(0, max(60, d["pct"].max())),
                        hover_name=hover_nome if hover_nome in d else None,
                        hover_data={"pct": ":.2f", "votos": ":,", chave: False}, labels={"pct": "% válidos"})
    fig.update_layout(coloraxis_colorbar=dict(title="%", len=0.6))
    if contorno_ufs is not None and contorno_ufs is not False:
        _contorno_ufs(fig, contorno_ufs or None)
    return _layout(fig, altura, legenda=False, brasil=brasil)


def margem(longo: pd.DataFrame, geojson: dict, chave: str, a: str, b: str, altura: int,
           contorno_ufs=None, hover_nome="municipio", brasil: bool = False) -> go.Figure:
    def serie(rot):
        n, p = rot.rsplit(" (", 1)
        p = p.rstrip(")")
        return longo[(longo["candidato"] == n) & (longo["partido"] == p)].set_index(chave)["pct"], ui.cor_partido(p)

    sa, ca = serie(a)
    sb, cb = serie(b)
    base = longo.drop_duplicates(chave).set_index(chave)
    d = pd.DataFrame({"margem": sa.sub(sb, fill_value=0), a: sa, b: sb})
    if hover_nome in base:
        d[hover_nome] = base[hover_nome]
    d = d.reset_index()
    lim = max(10, float(d["margem"].abs().quantile(0.98) if len(d) else 10))
    if cb == ca:
        cb = "#868e96"
    fig = px.choropleth(d, geojson=geojson, locations=chave, featureidkey="properties.codarea", color="margem",
                        color_continuous_scale=[[0, cb], [0.5, "#f1f3f5"], [1, ca]], range_color=(-lim, lim),
                        hover_name=hover_nome if hover_nome in d else None,
                        hover_data={a: ":.2f", b: ":.2f", "margem": ":.2f", chave: False})
    fig.update_layout(coloraxis_colorbar=dict(title=f"pp<br>{a.split(' (')[0]} −<br>{b.split(' (')[0]}", len=0.6))
    if contorno_ufs is not None and contorno_ufs is not False:
        _contorno_ufs(fig, contorno_ufs or None)
    return _layout(fig, altura, legenda=False, brasil=brasil)


def cores_partidos(partidos: list[str]) -> dict:
    """Cores de partido garantindo contraste entre os mais frequentes (ordem = prioridade)."""
    c = cores_candidatos([(p, p) for p in partidos])
    return {k.split(" (")[0]: v for k, v in c.items() if k != SEM}
