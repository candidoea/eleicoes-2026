"""Figuras do artigo (estudo/fig). Rode depois de 01, 02 e 03."""
import glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager

for f in font_manager.findSystemFonts():
    if "Carlito" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams.update({"font.family": "Carlito", "font.size": 11, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#9aa0a6", "axes.labelcolor": "#333", "xtick.color": "#555", "ytick.color": "#555",
                     "figure.dpi": 200, "savefig.bbox": "tight", "savefig.pad_inches": 0.12})
NAVY, AZUL, VERM, CINZA, CINZA_CL, OURO = "#0b2a5b", "#1c5bb5", "#c0392b", "#9AA0A6", "#D3D8DF", "#d4a017"
from comum import DADOS, FIG, RES

OUT = str(FIG) + "/"
br = lambda v, d=1: f"{v:.{d}f}".replace(".", ",")
REAL = 51.779


def _reexec(cargo, uf):
    """Junta as partes de 01_reexecucao.py (se ela foi rodada dividida em processos)."""
    arqs = sorted(glob.glob(str(RES / f"reexecucao_{cargo}_{uf}*.csv")))
    return pd.concat([pd.read_csv(a) for a in arqs]).sort_values("t").reset_index(drop=True)


def _pct_fmt(ax, eixo="x", d=0):
    f = matplotlib.ticker.FuncFormatter(lambda v, _: br(v, d) + "%")
    (ax.xaxis if eixo == "x" else ax.yaxis).set_major_formatter(f)


def f1_noite():
    j = pd.read_json(DADOS / "projecao_noite_c1_br.jsonl", lines=True)
    j = j[(j.totalizados > 0) & (j.pct_contado < 99.99)]
    r = _reexec(1, "BR")
    r = r[(r.tot >= 400) & (r.pct < 99.5)]
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    ax.fill_between(j.pct_contado, j.p05, j.p95, color=AZUL, alpha=0.13, lw=0, label="intervalo de 90% (noite real)")
    ax.plot(j.pct_contado, j.contado_a, color=CINZA, lw=2, label="parcial do TSE")
    ax.plot(j.pct_contado, j.proj_a, color=NAVY, lw=2.6, label="projeção da noite (só transferência)")
    ax.plot(r.pct, r.proj, color=OURO, lw=2, ls="--", label="reexecução com LightGBM ativo")
    ax.axhline(REAL, color=VERM, lw=1.2, ls=":")
    ax.text(101, REAL, "final\n" + br(REAL, 2) + "%", color=VERM, va="center", fontsize=9)
    ax.axhline(50, color="#777", lw=0.8)
    ax.text(101, 50, "50%", color="#777", va="center", fontsize=9)
    ax.set_xlim(0, 100); ax.set_ylim(49, 52.6)
    _pct_fmt(ax); _pct_fmt(ax, "y", 1)
    ax.set_xlabel("Votos válidos contados (% do total esperado)")
    ax.set_ylabel("Lula, % dos válidos")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.grid(axis="y", color="#eee")
    fig.savefig(OUT + "f1_noite.png"); plt.close(fig)


def f2_erro():
    r = _reexec(1, "BR")
    r = r[(r.tot > 0) & (r.pct < 99.5)]
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    ax.plot(r.pct, r.contado - REAL, color=CINZA, lw=2, label="parcial do TSE")
    ax.plot(r.pct, r.transf - REAL, color=NAVY, lw=2.4, label="projeção (só transferência)")
    ax.plot(r.pct, r.so_fatia - REAL, color=AZUL, lw=1.4, ls="--", label="erro só de fatia (comparecimento verdadeiro)")
    ax.plot(r.pct, r.so_comparecimento - REAL, color=OURO, lw=1.4, ls="--", label="erro só de comparecimento (fatia verdadeira)")
    ax.axhline(0, color="#555", lw=0.8)
    ax.set_xlim(0, 100); ax.set_ylim(-2.7, 0.6)
    _pct_fmt(ax)
    ax.set_xlabel("Votos válidos contados (% do total esperado)")
    ax.set_ylabel("Erro em pontos percentuais")
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    ax.grid(axis="y", color="#eee")
    fig.savefig(OUT + "f2_erro.png"); plt.close(fig)


GOV = {"AC": ("PP", "Republicanos"), "AM": ("PSD", "PL"), "DF": ("PT", "PP"), "ES": ("MDB", "Republicanos"),
       "RN": ("PT", "União"), "TO": ("União", "PSDB")}


def f3_governadores():
    fig, axs = plt.subplots(2, 3, figsize=(7.6, 4.8), sharex=True)
    for ax, (uf, (a, b)) in zip(axs.flat, GOV.items()):
        r = _reexec(3, uf)
        r = r[r.pct > 0].copy()
        real = r.real.iloc[0]
        ax.fill_between(r.pct, r.proj_lo, r.proj_hi, color=AZUL, alpha=0.13, lw=0)
        ax.plot(r.pct, r.contado, color=CINZA, lw=1.6)
        ax.plot(r.pct, r.proj, color=NAVY, lw=2)
        ax.axhline(real, color=VERM, lw=1, ls=":")
        ax.axhline(50, color="#777", lw=0.7)
        ax.set_title(f"{uf}: {a} x {b}", fontsize=10, loc="left")
        lo, hi = min(r.contado.min(), r.proj_lo.min(), 50), max(r.contado.max(), r.proj_hi.max(), 50)
        ax.set_ylim(max(lo - 1, 0), min(hi + 1, 100))
        ax.set_xlim(0, 100)
        _pct_fmt(ax)
        ax.tick_params(labelsize=8)
        ax.grid(axis="y", color="#eee")
    for ax in axs[1]:
        ax.set_xlabel("% contado", fontsize=9)
    for ax in axs[:, 0]:
        ax.set_ylabel(f"% do 1º nome", fontsize=9)
    from matplotlib.lines import Line2D
    fig.legend(handles=[Line2D([], [], color=CINZA, lw=1.6, label="parcial"), Line2D([], [], color=NAVY, lw=2, label="projeção"),
                        Line2D([], [], color=VERM, lw=1, ls=":", label="resultado final")],
               frameon=False, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.04), fontsize=9)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT + "f3_governadores.png"); plt.close(fig)


def f4_fluxo():
    f = pd.read_csv(RES / "fluxo_nacional.csv", index_col=0) * 100
    lo = pd.read_csv(RES / "fluxo_lo.csv", index_col=0)
    hi = pd.read_csv(RES / "fluxo_hi.csv", index_col=0)
    ordem = ["cury1", "caiado1", "renan1", "outros_z1", "bn1", "abst1"]
    nomes = {"cury1": "Cury (Avante)", "caiado1": "Caiado (PSD)", "renan1": "Renan (Missão)", "outros_z1": "Zema e demais",
             "bn1": "Branco e nulo no 1º turno", "abst1": "Abstenção no 1º turno"}
    f = f.loc[ordem][::-1]
    fig, ax = plt.subplots(figsize=(7.4, 3.5))
    y = np.arange(len(f))
    esq = np.zeros(len(f))
    for col, cor, rot in (("lula", VERM, "Lula"), ("flavio", NAVY, "Flávio"), ("nao_votou_valido", CINZA_CL, "não votou válido")):
        ax.barh(y, f[col], left=esq, color=cor, height=0.62, label=rot)
        for i, (v, e) in enumerate(zip(f[col], esq)):
            if v >= 7:
                ax.text(e + v / 2, i, br(v, 0) + "%", ha="center", va="center", fontsize=9,
                        color="white" if col != "nao_votou_valido" else "#333")
        esq += f[col].to_numpy()
    ax.set_yticks(y, [nomes[i] for i in f.index])
    ax.set_xlim(0, 100); _pct_fmt(ax)
    ax.set_xlabel("Destino no 2º turno (% do grupo de origem)")
    ax.legend(frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(0.45, 1.13), fontsize=9)
    fig.savefig(OUT + "f4_fluxo.png"); plt.close(fig)


def f5_abstencao_uf():
    u = pd.read_csv(RES / "uf.csv").sort_values("dabst_mil")
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    cor = [AZUL if v < 0 else VERM for v in u.dabst_mil]
    ax.bar(u.uf, u.dabst_mil, color=cor, width=0.7)
    ax.axhline(0, color="#555", lw=0.8)
    for x, v in zip(u.uf, u.dabst_mil):
        if abs(v) > 300:
            ax.text(x, v - 30, br(v / 1000, 2).replace(",", ",") + " mi", ha="center", va="top", fontsize=8, color="#333")
    ax.set_ylabel("Variação da abstenção (mil eleitores)")
    ax.tick_params(axis="x", labelsize=8)
    ax.grid(axis="y", color="#eee")
    fig.savefig(OUT + "f5_abstencao_uf.png"); plt.close(fig)


def f6_dispersao():
    d = pd.read_parquet(RES / "municipios.parquet")
    x, y = 100 * d.lula1 / d.vv1, 100 * d.lula2 / d.vv2
    vira = (d.lula1 <= d.flavio1) & (d.lula2 > d.flavio2)
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    s = np.clip(d.aptos2 / 4000, 2, 120)
    ax.scatter(x[~vira], y[~vira], s=s[~vira], color=NAVY, alpha=0.18, lw=0)
    ax.scatter(x[vira], y[vira], s=s[vira], color=OURO, alpha=0.8, lw=0, label=f"virou para Lula ({vira.sum()} municípios)")
    ax.plot([0, 100], [0, 100], color="#777", lw=0.8, ls="--")
    ax.text(88, 84, "sem mudança", fontsize=8, color="#777", rotation=35)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100)
    _pct_fmt(ax); _pct_fmt(ax, "y")
    ax.set_xlabel("Lula no 1º turno (% dos válidos)")
    ax.set_ylabel("Lula no 2º turno (% dos válidos)")
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    fig.savefig(OUT + "f6_dispersao.png"); plt.close(fig)


def f7_perfil():
    p = pd.read_csv(RES / "perfil_reg.csv")
    nomes = {"p_esc_sup": "superior completo", "p_a18_24": "18 a 24 anos", "p_60m": "60 anos ou mais", "p_fem": "mulheres"}
    ys = {"dlula": "Ganho de Lula (pp)", "dcomp": "Variação do comparecimento (pp)", "abst2r": "Abstenção no 2º turno (pp)"}
    fig, axs = plt.subplots(1, 3, figsize=(7.6, 2.9), sharey=True)
    for ax, (yv, tit) in zip(axs, ys.items()):
        q = p[p.y == yv].set_index("x").loc[list(nomes)][::-1]
        yy = np.arange(len(q))
        cor = [AZUL if abs(c) > 1.96 * s else CINZA for c, s in zip(q.coef_pp, q.se_pp)]
        ax.errorbar(q.coef_pp, yy, xerr=1.96 * q.se_pp, fmt="none", ecolor="#999", lw=1.2, capsize=2)
        ax.scatter(q.coef_pp, yy, color=cor, s=28, zorder=3)
        ax.axvline(0, color="#555", lw=0.8)
        ax.set_title(tit, fontsize=10)
        ax.set_yticks(yy, [nomes[i] for i in q.index])
        ax.tick_params(labelsize=8.5)
        ax.grid(axis="x", color="#eee")
    axs[1].set_xlabel("Efeito de +1 desvio-padrão da composição do eleitorado, com efeito fixo de UF (IC 95%)", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT + "f7_perfil.png"); plt.close(fig)


def f8_escolaridade():
    q = pd.read_csv(RES / "quintis_esc.csv")
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.0))
    x = np.arange(5)
    w = 0.38
    axs[0].bar(x - w / 2, 100 * q.abst1, w, color=CINZA, label="1º turno")
    axs[0].bar(x + w / 2, 100 * q.abst2, w, color=NAVY, label="2º turno")
    axs[0].set_ylim(15, 23); axs[0].set_title("Abstenção (% do eleitorado)", fontsize=10)
    axs[1].bar(x - w / 2, 100 * q.l1, w, color=CINZA, label="1º turno")
    axs[1].bar(x + w / 2, 100 * q.l2, w, color=VERM, label="2º turno")
    axs[1].set_ylim(30, 72); axs[1].set_title("Lula (% dos válidos)", fontsize=10)
    for ax in axs:
        ax.set_xticks(x, ["Q1\nmenos", "Q2", "Q3", "Q4", "Q5\nmais"])
        ax.set_xlabel("Quintil de municípios por % de eleitores com superior", fontsize=9)
        ax.legend(frameon=False, fontsize=8.5, loc="upper right" if ax is axs[0] else "upper right")
        _pct_fmt(ax, "y"); ax.grid(axis="y", color="#eee"); ax.tick_params(labelsize=8.5)
    fig.tight_layout()
    fig.savefig(OUT + "f8_escolaridade.png"); plt.close(fig)


if __name__ == "__main__":
    for f in (f1_noite, f2_erro, f3_governadores, f4_fluxo, f5_abstencao_uf, f6_dispersao, f7_perfil, f8_escolaridade):
        f()
        print("ok", f.__name__)
