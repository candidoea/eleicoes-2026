"""Apuração Eleições 2026 (1º e 2º turnos) - acompanhamento em tempo (quase) real via dados abertos do TSE,
com projeção do resultado do 2º turno e laboratório de validação.
Executar:  python -m streamlit run app.py      (e, em outro terminal, python coletor.py)
"""
from __future__ import annotations

import os
import time

import pandas as pd
import plotly.express as px
import streamlit as st

import geo
import mapas
import tse
import ui
from tse import CARGOS, UFS, cargo_legislativo_estadual

st.set_page_config(page_title="Apuração 2026", page_icon="🗳️", layout="wide")
CFG = {"topojsonURL": "/app/static/topojson/", "displaylogo": False, "scrollZoom": False}  # mapas sem depender do cdn.plot.ly
st.markdown(ui.CSS, unsafe_allow_html=True)


def fmt(n: int | float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def fpct(x: float) -> str:
    return f"{x:.2f}%".replace(".", ",")


# ------------------------------------------------------------------ sidebar
st.sidebar.markdown(f'<div style="text-align:center;margin:-10px 0 6px"><img src="{ui.brasao()}" '
                    f'style="width:130px"/><div style="font-weight:800;font-size:1.25rem;margin-top:6px">'
                    f'Apuração 2026</div></div>', unsafe_allow_html=True)
ambiente = st.sidebar.selectbox("Fonte", list(tse.AMBIENTES))
demo = st.sidebar.toggle("Modo demonstração (dados fictícios)", value=os.getenv("APURACAO_DEMO") == "1",
                         help="Gera dados no layout do TSE sem acessar a rede.")
TURNO2 = tse.turno(ambiente) == 2
visao = st.sidebar.radio("Visão", ["Brasil", "Estado", "Projeção e laboratório", "Painel das UFs"] if TURNO2
                         else ["Brasil", "Estado", "Partidos", "Painel das UFs"])
intervalo = st.sidebar.select_slider("Atualizar a cada (s)", [15, 30, 60, 120, 300], value=60)
auto = st.sidebar.toggle("Atualização automática", value=True)
if st.sidebar.button("Atualizar agora"):
    st.cache_data.clear()
st.sidebar.caption(
    "Rode `python coletor.py` em outro terminal: ele mantém o cache local (inclusive municípios) e grava "
    "o histórico no SQL Server. Sem o coletor, o painel busca direto no TSE (exceto o mapa municipal do Brasil)."
)
CHAVE = "demo" if demo else tse.chave(ambiente)

st.markdown(ui.cabecalho_html(f"{tse.AMBIENTES[ambiente]['rotulo']} · dados abertos de divulgação do TSE", demo),
            unsafe_allow_html=True)


# ------------------------------------------------------------------ dados (cache)
def bucket(seg: int | None = None) -> int:
    return int(time.time() // (seg or intervalo))


@st.cache_data(ttl=900, max_entries=500, show_spinner=False)
def _um(amb, cargo, abr, demo_, b, idade):
    return tse.coletar(amb, cargo, abr, demo_, max_idade=idade)


@st.cache_data(ttl=900, max_entries=500, show_spinner=False)
def _lote(amb, pedidos, demo_, b, idade):
    return tse.coletar_lote(amb, list(pedidos), demo_, max_idade=idade)


@st.cache_data(ttl=1800, max_entries=60, show_spinner=False)
def _municipal(amb, cargo, ufs, demo_, rede, b):
    if not demo_:  # camada consolidada gravada pelo coletor: 1 arquivo em vez de milhares de JSON
        cons = tse.ler_consolidado(amb, cargo, max_idade=1500)
        if cons is not None:
            d = cons[cons["uf"].isin(ufs)]
            if not d.empty:
                return d, d["cd_tse"].nunique(), 0
    return tse.coletar_municipal(amb, cargo, list(ufs), demo=demo_, rede=rede, max_idade=600, workers=12)


def um(cargo: int, abr: str):
    try:
        res = _um(ambiente, cargo, abr, demo, bucket(), intervalo)
        tse.salvar_snapshot(res, CHAVE)
        return res
    except tse.NaoDisponivel:
        st.info(f"{CARGOS[cargo][0]} / {abr.upper()}: arquivo ainda não publicado pelo TSE.")
    except Exception as exc:
        st.error(f"{CARGOS[cargo][0]} / {abr.upper()}: {exc}")
    return None


def lote(pedidos: list[tuple[int, str]]):
    ok, erros = _lote(ambiente, tuple(pedidos), demo, bucket(), intervalo)
    if erros:
        with st.expander(f"⚠️ {len(erros)} arquivo(s) indisponível(is)"):
            for k, v in erros.items():
                st.text(f"{k}: {v}")
    return ok


def municipal(cargo: int, ufs: list[str], rede: bool):
    try:
        with st.spinner("Carregando resultados por município..."):
            return _municipal(ambiente, cargo, tuple(ufs), demo, rede, bucket(max(intervalo, 120)))
    except Exception as exc:
        st.warning(f"Resultados municipais indisponíveis agora ({exc}).")
        return pd.DataFrame(), 0, 0


# ------------------------------------------------------------------ componentes
def indicadores(res: tse.Resultado):
    c = st.columns(6)
    c[0].metric("Seções totalizadas", fpct(res.pct_secoes), f"{fmt(res.secoes_tot)} de {fmt(res.secoes_total)}",
                delta_color="off")
    c[1].metric("Comparecimento", fmt(res.comparecimento), fpct(res.pct_comparecimento), delta_color="off")
    c[2].metric("Abstenção", fmt(res.abstencao), fpct(res.pct_abstencao), delta_color="off")
    c[3].metric("Votos válidos", fmt(res.validos))
    c[4].metric("Brancos", fmt(res.brancos), fpct(res.pct_brancos), delta_color="off")
    c[5].metric("Nulos", fmt(res.nulos), fpct(res.pct_nulos), delta_color="off")
    st.progress(min(res.pct_secoes / 100, 1.0),
                text=f"Atualizado pelo TSE em {res.atualizado or 'n/d'}"
                     + (" · TOTALIZAÇÃO FINAL" if res.final else ""))


def com_imagens(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d.insert(0, "legenda", d["partido"].map(lambda p: ui.logo_partido(p, True)))
    if "foto" in d.columns:
        d.insert(0, "foto", d.pop("foto"))
    return d


COLS_TABELA = {
    "foto": st.column_config.ImageColumn("", width="small"),
    "legenda": st.column_config.ImageColumn("partido", width="small"),
    "partido": st.column_config.TextColumn("sigla"),
    "votos": st.column_config.NumberColumn(format="%d"),
    "pct": st.column_config.ProgressColumn("% válidos", format="%.2f%%", min_value=0, max_value=100),
}


def tabela(df: pd.DataFrame, altura: int | None = None):
    d = com_imagens(df).drop(columns=["uf", "sqcand", "agremiacao"], errors="ignore")
    kw = {"height": altura} if altura else {}
    st.dataframe(d, hide_index=True, use_container_width=True, column_config=COLS_TABELA, row_height=48, **kw)


def grafico_candidatos(df: pd.DataFrame, top: int = 12):
    d = df.head(top).iloc[::-1]
    fig = px.bar(d, x="votos", y=d["candidato"] + " (" + d["partido"] + ")", orientation="h",
                 color="partido", color_discrete_map=ui.mapa_cores(d["partido"].unique()),
                 text=d["pct"].map(fpct))
    fig.update_layout(showlegend=False, yaxis_title=None, xaxis_title="votos", height=max(260, 34 * len(d)),
                      margin=dict(l=0, r=10, t=10, b=0))
    st.plotly_chart(fig, use_container_width=True, config=CFG)


def cards(res: tse.Resultado, maximo: int = 12):
    st.markdown(ui.cards_html(res.candidatos, vagas=max(res.vagas, 1), maximo=maximo, apurando=not res.final),
                unsafe_allow_html=True)


def detalhes(res: tse.Resultado):
    with st.expander("Gráfico e tabela completa"):
        grafico_candidatos(res.candidatos)
        tabela(res.candidatos)


def evolucao(cargo: int, abr: str):
    ev = tse.ler_evolucao(cargo, abr, CHAVE)
    if len(ev) < 2:
        return
    ev = ev.drop_duplicates("pct_secoes").sort_values("pct_secoes")
    cols = [c for c in ev.columns if "(" in c]
    if not cols:
        return
    longo = ev.melt(id_vars="pct_secoes", value_vars=cols, var_name="candidato", value_name="% válidos").dropna()
    fig = px.line(longo, x="pct_secoes", y="% válidos", color="candidato", markers=True,
                  title="Evolução durante a apuração (coletas desta máquina)")
    fig.update_layout(xaxis_title="% seções totalizadas", height=330, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True, config=CFG)


def rotulos_candidatos(res: tse.Resultado) -> list[tuple[str, str]]:
    return list(zip(res.candidatos["candidato"], res.candidatos["partido"]))


_CACHE_MAPA: dict = {}


def bloco_mapa(longo: pd.DataFrame, res: tse.Resultado, geojson: dict, altura: int, key: str,
               contorno=None, chave="cd_ibge", hover_nome="municipio", titulo_area="municípios", brasil=False,
               placar_lateral=True):
    """Seletor de modo + mapa + placar de áreas vencidas."""
    if longo.empty:
        st.info("Sem resultados por área ainda.")
        return
    rot = [f"{n} ({p})" for n, p in rotulos_candidatos(res)]
    m1, m2, m3 = st.columns([3, 2, 2])
    modo = m1.radio("Mapa", ["Vencedor", "% do candidato", "Margem entre dois"], horizontal=True, key=f"modo{key}")
    a = b = None
    if modo == "% do candidato":
        a = m2.selectbox("Candidato", rot, key=f"a{key}")
    elif modo == "Margem entre dois":
        a = m2.selectbox("Candidato A", rot, index=0, key=f"a{key}")
        b = m3.selectbox("Candidato B", rot, index=min(1, len(rot) - 1), key=f"b{key}")
    if "uf" in longo and chave == "codarea":  # DF por último: fica por cima de GO
        longo = longo.assign(_o=(longo["uf"] == "DF")).sort_values("_o").drop(columns="_o")
    ck = (key, ambiente, demo, bucket(max(intervalo, 120)), len(longo), int(longo["votos"].sum()))
    if ck not in _CACHE_MAPA:  # resumo e figuras ficam em memória: trocar o modo do mapa não recalcula
        if len(_CACHE_MAPA) > 40:
            _CACHE_MAPA.clear()
        resumo = mapas.resumo_vencedor(longo, chave)
        if "uf" in resumo and chave == "codarea":
            resumo = resumo.assign(_o=(resumo["uf"] == "DF")).sort_values("_o").drop(columns="_o")
        _CACHE_MAPA[ck] = {"resumo": resumo, "figs": {}}
    entrada = _CACHE_MAPA[ck]
    resumo = entrada["resumo"]
    cores = mapas.cores_candidatos(rotulos_candidatos(res))
    if placar_lateral:
        col_mapa, col_placar = st.columns([4, 1])
    else:
        col_mapa, col_placar = st.container(), st.container()
    with col_mapa:
        fk = (modo, a, b, tuple(sorted(cores.items())))
        fig = entrada["figs"].get(fk)
        if fig is None:
            if modo == "Vencedor":
                fig = mapas.vencedor(resumo, geojson, chave, altura, cores, contorno, hover_nome, brasil)
            elif modo == "% do candidato":
                fig = mapas.percentual(longo, geojson, chave, a, altura, contorno, hover_nome, brasil)
            else:
                fig = mapas.margem(longo, geojson, chave, a, b, altura, contorno, hover_nome, brasil)
            entrada["figs"][fk] = fig
        st.plotly_chart(fig, use_container_width=True, config=CFG, key=f"fig{key}")
    with col_placar:
        st.markdown(f"**{titulo_area.capitalize()} vencidos**")
        placar = resumo[resumo["lider"] != mapas.SEM].groupby("lider").size().sort_values(ascending=False)
        for lid, n in placar.items():
            cor = cores.get(lid, "#888")
            st.markdown(f'<div style="display:flex;justify-content:space-between;border-left:6px solid {cor};'
                        f'padding:4px 8px;margin:3px 0;background:rgba(128,128,128,.08);border-radius:4px">'
                        f'<span>{lid}</span><b>{fmt(n)}</b></div>', unsafe_allow_html=True)
        sem = int((resumo["lider"] == mapas.SEM).sum())
        st.caption(f"{fmt(len(resumo) - sem)} {titulo_area} com votos · {fmt(sem)} sem apuração")


def resumo_partidos(resultados: dict, cargo: int) -> pd.DataFrame:
    linhas = []
    for (_, uf), res in resultados.items():
        df = res.candidatos
        if df.empty:
            continue
        d = df.copy()
        d["nas_vagas"] = False
        if cargo in (1, 3, 5):
            d.loc[: max(res.vagas, 1) - 1, "nas_vagas"] = True
        linhas.append(d)
    if not linhas:
        return pd.DataFrame()
    todos = pd.concat(linhas)
    agg = todos.groupby("partido").agg(votos=("votos", "sum"), candidatos=("candidato", "count"),
                                       eleitos=("eleito", "sum"), liderando=("nas_vagas", "sum"))
    agg["% votos"] = 100 * agg["votos"] / max(agg["votos"].sum(), 1)
    agg = agg.sort_values(["eleitos", "liderando", "votos"], ascending=False).reset_index()
    agg.insert(0, "legenda", agg["partido"].map(lambda p: ui.logo_partido(p, True)))
    return agg


def tabela_partidos(part: pd.DataFrame, cargo: int, altura: int = 560):
    cols = ["legenda", "partido", "eleitos"] + (["liderando"] if cargo in (3, 5) else []) + \
           ["votos", "% votos", "candidatos"]
    st.dataframe(part[cols], hide_index=True, use_container_width=True, row_height=44, height=altura,
                 column_config={"legenda": st.column_config.ImageColumn("", width="small"),
                                "votos": st.column_config.NumberColumn(format="%d"),
                                "% votos": st.column_config.ProgressColumn(format="%.2f%%", min_value=0,
                                                                           max_value=float(part["% votos"].max() or 1))})


def mapa_ufs_partido(por_uf: dict[str, str], altura: int, titulo: str):
    """UFs coloridas pelo partido indicado (líder, mais votado etc.)."""
    d = pd.DataFrame([{"uf": uf, "codarea": str(UFS[uf][1]), "partido": p} for uf, p in por_uf.items() if p])
    if not d.empty:
        d = d.assign(_o=(d["uf"] == "DF")).sort_values("_o").drop(columns="_o")
    if d.empty:
        st.info("Sem dados para o mapa.")
        return
    fig = px.choropleth(d, geojson=geo.ufs(), locations="codarea", featureidkey="properties.codarea",
                        color="partido", color_discrete_map=mapas.cores_partidos(list(d["partido"].value_counts().index)),
                        hover_name="uf", hover_data={"codarea": False}, labels={"partido": titulo})
    fig.update_traces(marker_line_color="rgba(255,255,255,0.9)", marker_line_width=1)
    fig.update_geos(fitbounds="locations", projection_type="mercator", visible=False, bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=altura, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", y=0, title=None))
    st.plotly_chart(fig, use_container_width=True, config=CFG)



# ------------------------------------------------------------------ 2º turno: apuração x projeção lado a lado
def comparacao(cargo: int, uf: str | None, res, vertical: bool = False):
    """Cartões do TSE e cartões da projeção do modelo, na mesma ordem, para comparar de relance."""
    import projecao
    if res is None or res.candidatos.empty:
        return
    a, b = projecao.finalistas(cargo, uf if cargo == 3 else None)
    uf_modelo = uf if cargo == 3 else None
    longo, _, _ = municipal(cargo, [uf_modelo] if uf_modelo else list(UFS), rede=bool(uf_modelo))
    try:
        pj = _projetar(cargo, uf_modelo, longo, bucket(max(intervalo, 120)))
    except Exception as exc:
        st.warning(f"Projeção indisponível agora ({exc}).")
        cards(res, maximo=2)
        return
    pa, intervalo_txt = pj.pct_a, f"intervalo de 90%: {fpct(pj.p05)} a {fpct(pj.p95)}"
    pct_contado, n_tot = pj.pct_contado, pj.totalizados
    if cargo == 1 and uf:  # Presidente dentro de uma UF: recorte da projeção nacional
        lin = pj.por_uf[pj.por_uf["uf"] == uf]
        if not lin.empty:
            pa, intervalo_txt = float(lin["proj_a"].iloc[0]), "recorte estadual da projeção nacional"
            pct_contado = float(lin["pct_contado"].iloc[0] or 0)
    esperado = float(pj.por_uf.loc[pj.por_uf["uf"] == uf, "esperado"].sum() if uf else pj.por_uf["esperado"].sum())
    proj = res.candidatos.copy()
    proj["pct"] = proj["partido"].map({a: pa, b: 100 - pa}).fillna(0.0)
    proj["votos"] = (proj["pct"] / 100 * esperado).round().astype(int)
    proj["eleito"], proj["situacao"] = False, ""
    proj = proj.sort_values("pct", ascending=False)
    html_real = ui.cards_html(res.candidatos, vagas=1, maximo=2, apurando=not res.final)
    html_proj = ui.cards_html(proj, vagas=1, maximo=2, apurando=True).replace(" votos</div>", " votos projetados</div>").replace(">LIDERA<", ">VENCE<")
    lider = proj.iloc[0]
    chance = pj.prob_a if lider["partido"] == a else 1 - pj.prob_a
    modelo_txt = ("transferência do 1º turno + LightGBM" if pj.usa_ml else
                  "transferência do 1º turno" if n_tot else "hipótese inicial (nenhum município totalizado ainda)")
    chance_txt = (f"{lider['candidato']} lidera a projeção nesta UF" if (cargo == 1 and uf) else
                  f"{lider['candidato']}: chance de vitória **{100 * chance:.0f}%**")
    rodape = (f"{chance_txt} · {intervalo_txt} · "
              f"{fpct(pct_contado)} dos votos esperados contados · {fmt(n_tot)} municípios totalizados · modelo: {modelo_txt}")
    if vertical:
        st.markdown("**Apuração oficial (TSE)**")
        st.markdown(html_real, unsafe_allow_html=True)
        st.markdown("**Projeção do modelo**")
        st.markdown(html_proj, unsafe_allow_html=True)
        st.caption(rodape)
    else:
        e, d = st.columns(2)
        with e:
            st.markdown("**Apuração oficial (TSE)**")
            st.markdown(html_real, unsafe_allow_html=True)
        with d:
            st.markdown("**Projeção do modelo**")
            st.markdown(html_proj, unsafe_allow_html=True)
        st.markdown(rodape)
    hist = __import__("projecao").ler_historico(tse.chave(ambiente), cargo, uf_modelo or "br")
    if len(hist) >= 2 and not (cargo == 1 and uf):
        import plotly.graph_objects as go
        h = hist.sort_values("pct_contado")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["p95"], mode="lines", line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["p05"], mode="lines", fill="tonexty", line=dict(width=0),
                                 fillcolor="rgba(134,142,150,.22)", name="intervalo de 90%", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["proj_a"], mode="lines+markers", name=f"projeção {a}",
                                 line=dict(color=ui.cor_partido(a), width=3)))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["contado_a"], mode="lines+markers", name=f"apuração {a}",
                                 line=dict(color="#868e96", dash="dot")))
        fig.add_hline(y=50, line=dict(color="#495057", width=1))
        fig.update_layout(height=260, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=1.15),
                          xaxis_title="% dos votos esperados já contados", yaxis_title=f"% {a}")
        st.plotly_chart(fig, use_container_width=True, config=CFG, key=f"cmp{cargo}{uf}")

# ------------------------------------------------------------------ visões
def visao_brasil():
    res = um(1, "br")
    if not res:
        return
    st.markdown(ui.secao_html("Presidente da República", "BR"), unsafe_allow_html=True)
    indicadores(res)
    if TURNO2:
        comparacao(1, None, res)
    else:
        cards(res)
    detalhes(res)

    st.markdown(ui.secao_html("Mapa da disputa presidencial"), unsafe_allow_html=True)
    nivel = st.radio("Nível", ["Municípios", "Estados"], horizontal=True, key="nivelbr")
    if nivel == "Municípios":
        longo, ok, falta = municipal(1, list(UFS), rede=False)
        cobertura = longo["cd_ibge"].nunique() if not longo.empty else 0
        if cobertura == 0:
            st.warning("Nenhum município no cache local. Rode `python coletor.py` em outro terminal "
                       "(o ciclo municipal leva alguns minutos) ou use o nível Estados.")
            if st.button("Baixar agora pelo painel (≈5,6 mil arquivos, alguns minutos)"):
                with st.spinner("Baixando municípios..."):
                    _municipal.clear()
                    tse.coletar_municipal(ambiente, 1, list(UFS), demo=demo, rede=True, max_idade=600, workers=12)
                st.rerun()
        else:
            st.caption(f"{fmt(cobertura)} municípios no cache local.")
            bloco_mapa(longo, res, geo.municipios_brasil(leve=True), 950, "br", contorno=[], brasil=True)
    else:
        por_uf = lote([(1, uf) for uf in UFS])
        linhas = []
        for (_, uf), r in por_uf.items():
            d = r.candidatos[["sqcand", "candidato", "partido", "votos", "pct"]].copy()
            d["codarea"], d["uf"], d["pct_secoes"] = str(UFS[uf][1]), uf, r.pct_secoes
            linhas.append(d)
        longo = pd.concat(linhas) if linhas else pd.DataFrame()
        if not longo.empty:
            longo["municipio"] = longo["uf"]
        bloco_mapa(longo, res, geo.ufs(), 800, "bruf", contorno=False, chave="codarea", hover_nome="uf",
                   titulo_area="estados", brasil=True)
    evolucao(1, "br")


def visao_estado():
    uf = st.selectbox("UF", list(UFS), index=list(UFS).index("RN"), format_func=lambda u: f"{u} · {UFS[u][0]}")
    st.markdown(ui.secao_html(UFS[uf][0], uf), unsafe_allow_html=True)
    leg = cargo_legislativo_estadual(uf)
    opcoes = [3, 1, 5, 6, leg]
    if TURNO2:
        opcoes = [3, 1] if uf in tse.ufs_do_cargo(ambiente, 3) else [1]
    abas = st.tabs([CARGOS[c][0] for c in opcoes])
    for aba, cargo in zip(abas, opcoes):
        with aba:
            res = um(cargo, uf)
            if not res:
                continue
            indicadores(res)
            if cargo in (6, 7, 8):
                st.markdown(f"**{res.vagas or '?'} vagas** · eleitos marcados pelo TSE: "
                            f"**{int(res.candidatos['eleito'].sum()) if not res.candidatos.empty else 0}**")
                part = resumo_partidos({(cargo, uf): res}, cargo)
                a, b = st.columns([3, 2])
                with a:
                    if not part.empty:
                        col = "eleitos" if part["eleitos"].sum() > 0 else "votos"
                        d = part.head(20)
                        fig = px.bar(d, x="partido", y=col, color="partido",
                                     color_discrete_map=ui.mapa_cores(d["partido"]),
                                     title=f"Por partido: {col} (votos nominais; legenda não incluída)")
                        fig.update_layout(showlegend=False, height=420)
                        st.plotly_chart(fig, use_container_width=True, config=CFG)
                with b:
                    st.plotly_chart(_silhueta(uf), use_container_width=True, config=CFG, key=f"sil{cargo}")
                filtro = st.text_input("Buscar candidato/partido", key=f"busca{cargo}")
                df = res.candidatos
                if filtro:
                    m = (df["candidato"].str.contains(filtro, case=False)
                         | df["partido"].str.contains(filtro, case=False))
                    df = df[m]
                tabela(df.head(300), altura=640)
                continue
            if cargo in (1, 3):
                esq, dir_ = st.columns([5, 4])
                with esq:
                    longo, ok, falta = municipal(cargo, [uf], rede=True)
                    bloco_mapa(longo, res, geo.municipios_uf(uf), 760, f"{uf}{cargo}", contorno=False,
                               placar_lateral=False)
                with dir_:
                    if TURNO2:
                        comparacao(cargo, uf, res, vertical=True)
                    else:
                        cards(res, maximo=10)
                detalhes(res)
                evolucao(cargo, uf)
            else:
                esq, dir_ = st.columns([2, 3])
                with esq:
                    st.plotly_chart(_silhueta(uf), use_container_width=True, config=CFG, key=f"sil{cargo}")
                    st.caption("Mapa municipal coletado apenas para Presidente e Governador.")
                with dir_:
                    cards(res, maximo=12)
                detalhes(res)


def _silhueta(uf: str):
    g = geo.municipios_uf(uf)
    ids = [f["properties"]["codarea"] for f in g["features"]]
    import plotly.graph_objects as go
    fig = go.Figure(go.Choropleth(geojson=g, locations=ids, z=[1] * len(ids), featureidkey="properties.codarea",
                                  colorscale=[[0, "#3b5b92"], [1, "#3b5b92"]], showscale=False,
                                  text=[f["properties"]["nome"] for f in g["features"]], hoverinfo="text",
                                  marker_line_color="rgba(255,255,255,0.5)", marker_line_width=0.4))
    fig.update_geos(fitbounds="locations", visible=False, bgcolor="rgba(0,0,0,0)")
    fig.update_layout(height=420, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
    return fig


def visao_partidos():
    opcoes = {"Governador": 3, "Senador": 5, "Deputado Federal": 6, "Deputado Estadual/Distrital": 7}
    escolha = st.radio("Cargo", list(opcoes), horizontal=True)
    cargo = opcoes[escolha]
    pedidos = [(cargo_legislativo_estadual(uf) if cargo == 7 else cargo, uf) for uf in UFS]
    with st.spinner(f"Coletando {len(pedidos)} UFs em paralelo..."):
        resultados = lote(pedidos)
    part = resumo_partidos(resultados, cargo)
    if part.empty:
        st.info("Sem dados ainda.")
        return
    c = st.columns(4)
    c[0].metric("UFs com dados", len(resultados))
    c[1].metric("Média % seções", fpct(sum(r.pct_secoes for r in resultados.values()) / max(len(resultados), 1)))
    c[2].metric("Vagas em disputa", fmt(sum(r.vagas for r in resultados.values())))
    c[3].metric("Eleitos já definidos (TSE)", fmt(part["eleitos"].sum()))

    # partido dominante por UF: líder (majoritários) ou mais votado (proporcionais)
    dom = {}
    for (_, uf), r in resultados.items():
        if r.candidatos.empty or r.validos == 0:
            continue
        if cargo in (3, 5):
            dom[uf] = r.candidatos.iloc[0]["partido"]
        else:
            dom[uf] = r.candidatos.groupby("partido")["votos"].sum().idxmax()
    esq, dir_ = st.columns([3, 2])
    with esq:
        st.markdown("**" + ("Partido do líder em cada UF" if cargo in (3, 5) else "Partido mais votado em cada UF")
                    + "**")
        mapa_ufs_partido(dom, 760, "partido")
    with dir_:
        metricas = ["eleitos", "liderando", "votos"] if cargo in (3, 5) else ["eleitos", "votos"]
        if part["eleitos"].sum() == 0:
            metricas = [m for m in metricas if m != "eleitos"] + ["eleitos"]
        metrica = st.radio("Métrica", metricas, horizontal=True,
                           help="liderando = candidatos hoje dentro das vagas da UF (só cargos majoritários).")
        d = part[part[metrica] > 0].head(20)
        if not d.empty:
            fig = px.bar(d, x="partido", y=metrica, color="partido", color_discrete_map=ui.mapa_cores(d["partido"]),
                         text=metrica)
            fig.update_layout(showlegend=False, height=300, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True, config=CFG)
        tabela_partidos(part, cargo, altura=420)
    if cargo in (6, 7):
        st.caption("Cadeiras proporcionais só são contabilizadas quando o TSE marca o candidato como eleito "
                   "(QP/média). Votos por partido = soma dos nominais; votos de legenda não entram.")


def visao_painel():
    with st.spinner("Coletando Governador e Senador das 27 UFs..." if not TURNO2 else "Coletando os 2º turnos estaduais..."):
        gov = lote([(3, uf) for uf in tse.ufs_do_cargo(ambiente, 3)])
        sen = lote([(5, uf) for uf in UFS]) if not TURNO2 else {}
    linhas, dom = [], {}
    for uf in (tse.ufs_do_cargo(ambiente, 3) if TURNO2 else UFS):
        g, s = gov.get((3, uf)), sen.get((5, uf))
        lin = {"bandeira": ui.bandeira(uf), "UF": uf, "% seções": g.pct_secoes if g else None}
        if g is not None and not g.candidatos.empty:
            t = g.candidatos.iloc[0]
            if g.validos > 0:
                dom[uf] = t["partido"]
            lin |= {"foto": t.get("foto", ""), "legenda": ui.logo_partido(t["partido"], True),
                    "Governador (1º)": f"{t['candidato']} ({t['partido']})", "% 1º": t["pct"]}
            if len(g.candidatos) > 1:
                t2 = g.candidatos.iloc[1]
                lin |= {"2º": f"{t2['candidato']} ({t2['partido']})", "% 2º": t2["pct"]}
            lin["situação"] = t["situacao"]
        if s is not None and not s.candidatos.empty:
            vs = max(s.vagas, 1)
            lin["Senado (nas vagas)"] = " · ".join(f"{r.candidato} ({r.partido}) {fpct(r.pct)}"
                                                   for r in s.candidatos.head(vs).itertuples())
        linhas.append(lin)
    esq, dir_ = st.columns([2, 3])
    with esq:
        st.markdown("**Governador: partido do líder em cada UF**")
        mapa_ufs_partido(dom, 820, "partido")
    with dir_:
        st.dataframe(pd.DataFrame(linhas), hide_index=True, use_container_width=True, height=1250, row_height=44,
                     column_config={"bandeira": st.column_config.ImageColumn("", width="small"),
                                    "foto": st.column_config.ImageColumn("", width="small"),
                                    "legenda": st.column_config.ImageColumn("", width="small"),
                                    "% 1º": st.column_config.NumberColumn(format="%.2f"),
                                    "% 2º": st.column_config.NumberColumn(format="%.2f"),
                                    "% seções": st.column_config.ProgressColumn(format="%.1f%%", min_value=0,
                                                                                max_value=100)})




# ------------------------------------------------------------------ 2º turno: projeção e laboratório
@st.cache_data(ttl=900, max_entries=40, show_spinner=False)
def _projetar(cargo, uf, longo, b):
    import projecao
    return projecao.projetar_de_longo(longo, cargo, uf, n_boot=40)


@st.cache_data(ttl=900, max_entries=20, show_spinner=False)
def _oof(cargo, uf, longo, b):
    import projecao
    return projecao.fora_da_amostra(longo, cargo, uf)


@st.cache_data(ttl=3600, show_spinner=False)
def _backtest():
    import projecao
    p = projecao.MODELO / "backtest_2022.parquet"
    return pd.read_parquet(p) if p.exists() else projecao.backtest_2022()


def _nomes(res, partidos):
    """partido -> linha do candidato (nome, número, foto) a partir do resultado ao vivo."""
    out = {}
    if res is not None and not res.candidatos.empty:
        for _, r in res.candidatos.iterrows():
            out[r["partido"]] = r
    return {p: out.get(p) for p in partidos}


def visao_projecao():
    import plotly.graph_objects as go

    import projecao
    alvos = ["Presidente · Brasil"] + [f"Governador · {u}" for u in projecao.UFS_GOV_2T]
    alvo = st.radio("Disputa", alvos, horizontal=True)
    cargo, uf = (1, None) if alvo.startswith("Presidente") else (3, alvo[-2:])
    abr = uf or "br"
    res = um(cargo, abr)
    a, b = projecao.finalistas(cargo, uf)
    nomes = _nomes(res, (a, b))
    nome = {p: (f"{nomes[p]['candidato']} ({p})" if nomes[p] is not None else p) for p in (a, b)}

    longo, ok, falta = municipal(cargo, [uf] if uf else list(UFS), rede=bool(uf))
    if demo:
        st.info("Modo demonstração: os dados fictícios não seguem o padrão do 1º turno, então a projeção não "
                "tem significado. Use os dados oficiais.")
    with st.spinner("Projetando..."):
        pj = _projetar(cargo, uf, longo, bucket(max(intervalo, 120)))

    st.markdown(ui.secao_html(f"Projeção do 2º turno · {alvo}", uf or "BR"), unsafe_allow_html=True)
    # cartões no mesmo estilo da apuração, com a projeção no lugar da parcial
    linhas = []
    total_esp = float(pj.por_uf["esperado"].sum()) if not pj.por_uf.empty else 0.0
    for p, pct in ((a, pj.pct_a), (b, 100 - pj.pct_a)):
        r = nomes[p]
        linhas.append({"candidato": r["candidato"] if r is not None else p, "partido": p,
                       "numero": r["numero"] if r is not None else "", "foto": r.get("foto", "") if r is not None else "",
                       "votos": int(round(total_esp * pct / 100)), "pct": pct, "eleito": False, "situacao": ""})
    cand = pd.DataFrame(linhas).sort_values("pct", ascending=False)
    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(ui.cards_html(cand, vagas=1, maximo=2, apurando=True).replace(" votos</div>", " votos projetados</div>").replace(">LIDERA<", ">VENCE<"),
                    unsafe_allow_html=True)
    with c2:
        k = st.columns(2)
        k[0].metric(f"Chance de {nome[a].split(' (')[0]} vencer", f"{100 * pj.prob_a:.0f}%")
        k[1].metric(f"Chance de {nome[b].split(' (')[0]} vencer", f"{100 * (1 - pj.prob_a):.0f}%")
        k = st.columns(2)
        k[0].metric("Votos esperados já contados", fpct(pj.pct_contado))
        k[1].metric("Municípios totalizados", f"{fmt(pj.totalizados)} de {fmt(pj.municipios)}")
        st.caption(f"{fmt(pj.parciais)} municípios com apuração parcial entram na conta pelo que já foi contado.")
    st.markdown(
        f"Projeção de **{nome[a]}: {fpct(pj.pct_a)}** dos válidos (intervalo de 90%: {fpct(pj.p05)} a "
        f"{fpct(pj.p95)}). Na parcial contada, {nome[a].split(' (')[0]} tem "
        f"{fpct(pj.contado_a) if pj.contado_a == pj.contado_a else 'n/d'}. "
        + ("Modelo: transferência do 1º turno + LightGBM nos resíduos." if pj.usa_ml else
           "Modelo: transferência do 1º turno por município." if pj.totalizados else
           "Nenhum município totalizado ainda: a projeção usa só a hipótese inicial de transferência."))

    # evolução da projeção
    hist = projecao.ler_historico(tse.chave(ambiente), cargo, abr)
    final = res.candidatos.set_index("partido")["pct"].get(a) if (res is not None and res.final) else None
    st.markdown(ui.secao_html("Projeção x parcial durante a apuração"), unsafe_allow_html=True)
    if len(hist) >= 2:
        h = hist.sort_values("pct_contado")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["p95"], mode="lines", line=dict(width=0), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["p05"], mode="lines", fill="tonexty", line=dict(width=0),
                                 fillcolor="rgba(134,142,150,.22)", name="intervalo de 90%", hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["proj_a"], mode="lines+markers", name=f"projeção {nome[a]}",
                                 line=dict(color=ui.cor_partido(a), width=3)))
        fig.add_trace(go.Scatter(x=h["pct_contado"], y=h["contado_a"], mode="lines+markers", name=f"parcial {nome[a]}",
                                 line=dict(color="#868e96", dash="dot")))
        fig.add_hline(y=50, line=dict(color="#495057", width=1))
        if final is not None:
            fig.add_hline(y=final, line=dict(color="#2f9e44", dash="dash"), annotation_text=f"resultado final {fpct(final)}")
        fig.update_layout(height=380, xaxis_title="% dos votos válidos esperados já contados",
                          yaxis_title=f"% de {nome[a].split(' (')[0]} nos válidos", margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, use_container_width=True, config=CFG)
    else:
        st.caption("O gráfico aparece a partir da segunda projeção gravada pelo coletor (uma por ciclo municipal).")

    # transferência estimada
    esq, dir_ = st.columns([2, 3])
    with esq:
        st.markdown(ui.secao_html("Para onde foi o eleitor do 1º turno"), unsafe_allow_html=True)
        nomes_1t = pd.read_parquet(projecao.MODELO / "base_2026.parquet")
        nomes_1t = nomes_1t[nomes_1t["cargo"] == cargo]
        if uf:
            nomes_1t = nomes_1t[nomes_1t["uf"] == uf]
        nomes_1t = nomes_1t.groupby("partido")["candidato"].first().str.title().to_dict()
        tr = pd.DataFrame([{"1º turno": (nomes_1t.get(p, p) + f" ({p})") if p != "OUTROS" else "Demais candidatos",
                            f"→ {nome[a].split(' (')[0]}": 100 * v, f"→ {nome[b].split(' (')[0]}": 100 * (1 - v)}
                           for p, v in pj.betas.items()])
        st.dataframe(tr, hide_index=True, use_container_width=True,
                     column_config={c: st.column_config.ProgressColumn(c, format="%.0f%%", min_value=0, max_value=100)
                                    for c in tr.columns[1:]})
        st.caption("Entre os eleitores de cada candidato eliminado que votaram num finalista. Estimado nos "
                   "municípios totalizados (regressão de transferência); antes deles, é só a hipótese inicial.")
    with dir_:
        st.markdown(ui.secao_html("Projeção por estado"), unsafe_allow_html=True)
        u = pj.por_uf.copy()
        u.insert(0, "bandeira", u["uf"].map(ui.bandeira))
        st.dataframe(u[["bandeira", "uf", "proj_a", "contado_a", "pct_contado"]].sort_values("proj_a", ascending=False),
                     hide_index=True, use_container_width=True, height=420, row_height=34,
                     column_config={"bandeira": st.column_config.ImageColumn("", width="small"),
                                    "proj_a": st.column_config.NumberColumn(f"projeção {a} (%)", format="%.2f"),
                                    "contado_a": st.column_config.NumberColumn(f"parcial {a} (%)", format="%.2f"),
                                    "pct_contado": st.column_config.ProgressColumn("contado", format="%.0f%%",
                                                                                   min_value=0, max_value=100)})

    # laboratório
    st.markdown(ui.secao_html("Laboratório: qualidade da previsão"), unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Validação ao vivo (municípios)", "Projeção x resultado final", "Validação histórica (2022)"])
    with t1:
        oof = _oof(cargo, uf, longo, bucket(max(intervalo, 300)))
        if oof.empty:
            st.info("A validação começa com 30 municípios totalizados.")
        else:
            err = 100 * (oof["oof"] - oof["y"])
            err0 = 100 * (oof["base_1t"] - oof["y"])
            w = oof["w"]
            m = st.columns(4)
            m[0].metric("Erro médio do modelo (por município)", f"{(err.abs() * w).sum() / w.sum():.2f} pp".replace(".", ","))
            m[1].metric("Referência: só o 1º turno dos finalistas", f"{(err0.abs() * w).sum() / w.sum():.2f} pp".replace(".", ","))
            m[2].metric("Viés do modelo", f"{(err * w).sum() / w.sum():+.2f} pp".replace(".", ","))
            m[3].metric("Municípios avaliados", fmt(len(oof)))
            fig = px.scatter(oof.assign(previsto=100 * oof["oof"], real=100 * oof["y"], eleitores=oof["w"]),
                             x="previsto", y="real", size="eleitores", size_max=28, opacity=0.55,
                             color_discrete_sequence=[ui.cor_partido(a)],
                             hover_data={"cd_tse": True, "uf": True})
            fig.add_trace(go.Scatter(x=[0, 100], y=[0, 100], mode="lines", line=dict(color="#495057", dash="dot"),
                                     showlegend=False))
            fig.update_layout(height=460, xaxis_title=f"previsto para {a} (%), sem ver o município",
                              yaxis_title=f"real {a} (%)", margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True, config=CFG)
            st.caption("Cada ponto é um município totalizado, previsto por um modelo treinado sem ele (validação "
                       "cruzada em 5 dobras). Erro em pontos percentuais, ponderado pelos votos.")
            if pj.cv_mae:
                st.caption("Comparação de modelos (erro municipal em validação cruzada): " + " · ".join(
                    f"{k}: {v:.2f} pp".replace(".", ",") for k, v in pj.cv_mae.items()))
    with t2:
        if final is None:
            st.info("Disponível quando o TSE marcar a totalização final. Até lá, o gráfico acima mostra a "
                    "projeção e a parcial ao longo da noite.")
        elif len(hist):
            h = hist.sort_values("pct_contado").assign(erro_projecao=lambda x: x["proj_a"] - final,
                                                      erro_parcial=lambda x: x["contado_a"] - final)
            fig = px.line(h, x="pct_contado", y=["erro_projecao", "erro_parcial"], markers=True,
                          labels={"value": "erro (pp)", "pct_contado": "% contado", "variable": ""})
            fig.add_hline(y=0, line=dict(color="#495057"))
            fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0))
            st.plotly_chart(fig, use_container_width=True, config=CFG)
            primeira = h[h["erro_projecao"].abs() <= 0.5]
            st.markdown(f"Resultado final de {nome[a]}: **{fpct(final)}**. Erro médio da projeção: "
                        f"**{h['erro_projecao'].abs().mean():.2f} pp**; da parcial: {h['erro_parcial'].abs().mean():.2f} pp."
                        + (f" A projeção ficou a menos de 0,5 pp do resultado desde {fpct(primeira['pct_contado'].iloc[0])} "
                           f"dos votos contados." if len(primeira) else ""))
    with t3:
        bt = _backtest()
        st.markdown("Reexecução da noite do 2º turno de 2022 (Lula x Bolsonaro), liberando os municípios na "
                    "**ordem real de totalização** do TSE. Resultado final: Lula 50,90%.")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=bt["marco"], y=bt["contado_lula"], mode="lines+markers", name="parcial contada",
                                 line=dict(color="#868e96", dash="dot")))
        fig.add_trace(go.Scatter(x=bt["marco"], y=bt["projecao_lula"], mode="lines+markers", name="projeção do modelo",
                                 line=dict(color=ui.cor_partido("PT"), width=3),
                                 error_y=dict(type="data", symmetric=False, array=bt["p95"] - bt["projecao_lula"],
                                              arrayminus=bt["projecao_lula"] - bt["p05"])))
        fig.add_hline(y=50.90, line=dict(color="#2f9e44", dash="dash"), annotation_text="final 50,90%")
        fig.add_hline(y=50, line=dict(color="#495057", width=1))
        fig.update_layout(height=380, xaxis_title="% dos votos já contados (municípios totalizados)",
                          yaxis_title="% de Lula nos válidos", margin=dict(l=0, r=0, t=10, b=0),
                          legend=dict(orientation="h", y=1.08))
        st.plotly_chart(fig, use_container_width=True, config=CFG)
        st.dataframe(bt[["marco", "hora", "municipios", "contado_lula", "projecao_lula", "p05", "p95",
                         "erro_contado", "erro_projecao"]].round(2), hide_index=True, use_container_width=True)
        p0 = bt.iloc[0]
        br1 = lambda v: f"{v:.1f}".replace(".", ",")
        st.caption(f"Com {p0['marco']:.0f}% dos votos contados, a parcial errava por {br1(abs(p0['erro_contado']))} pp e a "
                   f"projeção por {br1(abs(p0['erro_projecao']))} pp. Erro máximo da parcial: "
                   f"{br1(bt['erro_contado'].abs().max())} pp; da projeção: {br1(bt['erro_projecao'].abs().max())} pp.")


VISOES = {"Brasil": visao_brasil, "Estado": visao_estado, "Partidos": visao_partidos, "Painel das UFs": visao_painel,
          "Projeção e laboratório": visao_projecao}


@st.fragment(run_every=intervalo if auto else None)
def principal():
    VISOES[visao]()
    st.markdown(f'<div class="rodape">Painel não oficial, sem vínculo com a Justiça Eleitoral. Fonte: dados '
                f'abertos de divulgação do TSE ({ambiente}) · malhas IBGE (via geodata-br) · fotos servidas pelo '
                f'TSE · atualização a cada {intervalo}s · {time.strftime("%H:%M:%S")}</div>', unsafe_allow_html=True)


principal()
