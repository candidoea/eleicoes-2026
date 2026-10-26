// Artigo científico Eleições 2026: gera o .docx (capa, resumo, sumário, notas de rodapé, numeração)
// uso: npm install docx  e depois  node estudo/scripts/05_artigo.js   (figuras de 04_figuras.py em estudo/fig)
// Grava em estudo/resultados/ para não sobrescrever a versão revisada em estudo/.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, Header, Footer, AlignmentType,
  HeadingLevel, WidthType, ShadingType, BorderStyle, PageNumber, TableOfContents, PageBreak, FootnoteReferenceRun,
  LevelFormat, TabStopType, VerticalAlign, TableLayoutType,
} = require("docx");

const FIG = path.join(__dirname, "..", "fig") + path.sep;
const AM = "1C5BB5", AM_ESC = "0B2A5B", PRETO = "0B2A5B", CINZA = "6B6B6B", ZEBRA = "F2F5FA";
const FONT = "Calibri";
const W = 9071; // largura útil: A4 11906 - margens 1701 (esq) e 1134 (dir)

// ---------------------------------------------------------------- texto com marcação simples
// **negrito**, ~itálico~, [[n]] = nota de rodapé n, x_{sub} e x^{sup}
function runs(txt, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|~[^~]+~|\[\[\d+\]\]|\{[^}]+\}_\{[^}]+\}|\{[^}]+\}\^\{[^}]+\})/g;
  let last = 0, m;
  while ((m = re.exec(txt))) {
    if (m.index > last) out.push(new TextRun({ text: txt.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else if (t.startsWith("[[")) out.push(new FootnoteReferenceRun(parseInt(t.slice(2, -2))));
    else if (t.startsWith("~")) out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    else {
      const sub = t.includes("}_{");
      const [a, b] = t.slice(1, -1).split(sub ? "}_{" : "}^{");
      out.push(new TextRun({ text: a, italics: true, ...base }));
      out.push(new TextRun({ text: b, italics: true, subScript: sub, superScript: !sub, ...base }));
    }
    last = m.index + t.length;
  }
  if (last < txt.length) out.push(new TextRun({ text: txt.slice(last), ...base }));
  return out;
}
const P = (t, o = {}) => new Paragraph({ children: runs(t, o.run), alignment: o.align ?? AlignmentType.JUSTIFIED,
  spacing: { after: o.after ?? 120, line: 288 }, indent: o.indent, keepNext: o.keepNext });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true });
const H1c = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t, lvl = 0) => new Paragraph({ numbering: { reference: "bul", level: lvl }, children: runs(t),
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 288 } });
const N = (t, ref = "num") => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t),
  alignment: AlignmentType.JUSTIFIED, spacing: { after: 60, line: 288 } });
const EQ = (t, n) => new Paragraph({ alignment: AlignmentType.LEFT, spacing: { before: 100, after: 140 },
  tabStops: [{ type: TabStopType.CENTER, position: Math.round(W / 2) }, { type: TabStopType.RIGHT, position: W }],
  children: [new TextRun({ text: "\t" }), ...runs(t, { size: 24 }), new TextRun({ text: `\t(${n})` })] });
const FONTE = t => new Paragraph({ children: runs(t, { size: 18, color: CINZA }), spacing: { after: 200 } });

let nFig = 0, nTab = 0;
function figura(arq, titulo, fonte, larg = 15.5) {
  nFig++;
  const buf = fs.readFileSync(FIG + arq);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const wpx = larg / 2.54 * 96, hpx = wpx * h / w;
  return [
    new Paragraph({ keepNext: true, spacing: { before: 120, after: 60 }, children: runs(`**Figura ${nFig}** – ${titulo}`, { size: 20 }) }),
    new Paragraph({ keepNext: true, alignment: AlignmentType.CENTER, children: [new ImageRun({ type: "png", data: buf,
      transformation: { width: Math.round(wpx), height: Math.round(hpx) },
      altText: { title: titulo, description: titulo, name: arq } })] }),
    FONTE(`Fonte: ${fonte}`),
  ];
}
const bordas = { top: { style: BorderStyle.SINGLE, size: 4, color: "D9D9D9" }, bottom: { style: BorderStyle.SINGLE, size: 4, color: "D9D9D9" },
  left: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" }, right: { style: BorderStyle.NONE, size: 0, color: "FFFFFF" } };
function tabela(titulo, cab, linhas, pesos, fonte, alinhar = []) {
  nTab++;
  const tot = pesos.reduce((a, b) => a + b, 0);
  const cw = pesos.map(p => Math.floor(W * p / tot)); cw[cw.length - 1] += W - cw.reduce((a, b) => a + b, 0);
  const cel = (t, i, hdr, z) => new TableCell({ width: { size: cw[i], type: WidthType.DXA }, borders: bordas,
    verticalAlign: VerticalAlign.CENTER,
    shading: { fill: hdr ? PRETO : (z ? ZEBRA : "FFFFFF"), type: ShadingType.CLEAR, color: "auto" },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: alinhar[i] === "r" ? AlignmentType.RIGHT : (alinhar[i] === "c" ? AlignmentType.CENTER : AlignmentType.LEFT),
      children: runs(String(t), { size: 18, color: hdr ? "FFFFFF" : "222222", bold: hdr || undefined }) })] });
  return [
    new Paragraph({ keepNext: true, spacing: { before: 160, after: 60 }, children: runs(`**Tabela ${nTab}** – ${titulo}`, { size: 20 }) }),
    new Table({ width: { size: W, type: WidthType.DXA }, columnWidths: cw, layout: TableLayoutType.FIXED,
      rows: [new TableRow({ tableHeader: true, children: cab.map((c, i) => cel(c, i, true)) }),
        ...linhas.map((l, r) => new TableRow({ cantSplit: true, children: l.map((c, i) => cel(c, i, false, r % 2 === 1)) }))] }),
    FONTE(`Fonte: ${fonte}`),
  ];
}


// ---------------------------------------------------------------- notas de rodapé
const NOTAS = {
  1: "Os totais do TSE incluem o voto no exterior. As análises por município usam apenas os 5.571 municípios brasileiros, por isso os percentuais municipais diferem dos oficiais na segunda casa decimal (51,78% contra 51,79% para Lula).",
  2: "Fatia bipartidária: votos de Lula divididos pela soma dos votos de Lula e Flávio. No 2º turno ela coincide com o percentual de votos válidos.",
  3: "Os arquivos de divulgação trazem o horário de totalização de cada município, mas na base consolidada todos chegaram com o mesmo carimbo (23h27). A ordem de chegada foi reconstruída pelo horário em que o coletor gravou cada mudança no banco, com resolução de cerca de cinco minutos.",
  4: "O LightGBM usa OpenMP para paralelizar o treino. Chamado ao mesmo tempo por duas threads do Streamlit no Windows, o processo terminava com violação de acesso; o código de produção passou a capturar a falha e seguir só com a transferência. A correção (uma thread, trava global e reserva) foi publicada depois da noite.",
  5: "Inferência ecológica: conclusões sobre grupos de eleitores a partir de dados agregados por território. O risco clássico é a falácia ecológica (ROBINSON, 1950). As matrizes de transição aqui são médias nacionais com restrições lógicas, não afirmações sobre indivíduos.",
  6: "O DF é um único município para o TSE. Sem variação entre municípios, o modelo não aprende a transferência no DF e a projeção é a mistura da parcial com a hipótese inicial.",
  7: "Composição do eleitorado apto por sexo, idade e escolaridade agregada das seções para o município, a partir do perfil do eleitorado de 2026 do TSE. As variáveis foram padronizadas com média e desvio-padrão ponderados pelo eleitorado.",
};
const footnotes = Object.fromEntries(Object.entries(NOTAS).map(([k, v]) => [k, { children: [new Paragraph({ children: runs(v, { size: 17 }) })] }]));

// ---------------------------------------------------------------- capa
const capaFig = fs.readFileSync(FIG + "f1_noite.png");
const cw0 = capaFig.readUInt32BE(16), ch0 = capaFig.readUInt32BE(20);
const capa = [
  new Paragraph({ spacing: { before: 600, after: 160 }, children: [new TextRun({ text: "ARTIGO CIENTÍFICO", bold: true, color: AM, size: 20 }),
    new TextRun({ text: "  |  ", color: CINZA, size: 20 }), new TextRun({ text: "DADOS ABERTOS DO TSE", bold: true, color: AM, size: 20 })] }),
  new Paragraph({ spacing: { after: 200 }, children: [new TextRun({ text: "Eleições 2026: a virada do 2º turno e a projeção em tempo real", bold: true, size: 48, color: PRETO })] }),
  new Paragraph({ spacing: { after: 300 }, border: { bottom: { style: BorderStyle.SINGLE, size: 24, color: AM, space: 12 } },
    children: [new TextRun({ text: "Avaliação de um modelo de projeção durante a apuração, fluxos de voto entre turnos, abstenção e as disputas de governador", size: 26, color: CINZA })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 300, after: 80 }, children: [new ImageRun({ type: "png", data: capaFig,
    transformation: { width: 520, height: Math.round(520 * ch0 / cw0) }, altText: { title: "Noite da apuração", description: "Parcial e projeção de Lula ao longo da apuração do 2º turno", name: "capa" } })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 900 }, children: runs("Parcial do TSE e projeção do modelo para Lula ao longo da apuração de 25 de outubro de 2026", { size: 16, color: CINZA }) }),
  new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Eduardo Cândido", bold: true, size: 26 })] }),
  new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Cientista de Dados  ·  Estudo independente com dados abertos", size: 20, color: CINZA })] }),
  new Paragraph({ children: [new TextRun({ text: "Natal, outubro de 2026", size: 20, color: CINZA })] }),
];

// ---------------------------------------------------------------- pré-textuais
const resumo = [
  H1c("Resumo"),
  P("Flávio Bolsonaro terminou o 1º turno de 2026 à frente (47,0% contra 45,2% dos válidos nos municípios brasileiros), e Lula venceu o 2º turno com 51,79% dos válidos. Este artigo usa apenas dados abertos do Tribunal Superior Eleitoral e os registros de um painel independente de apuração para responder a três grupos de perguntas: como se comportou, minuto a minuto, um modelo de projeção que estimava o resultado final enquanto os municípios eram totalizados; de onde vieram os votos que decidiram a eleição; e o que mudou no comparecimento entre os turnos. O modelo combina uma regressão de transferência com limites (fatia do 2º turno explicada pelas fatias do 1º), um termo de LightGBM nos resíduos, uma razão de comparecimento por UF e bootstrap. Reexecutado na ordem real de chegada dos 5.571 municípios, ele apontou o vencedor certo desde o primeiro dado, com 0,2% dos votos contados e probabilidade de 99,1%, enquanto a parcial do TSE mostrou Flávio à frente entre 15% e 50% da apuração. O erro médio da projeção foi de 0,48 ponto, contra 1,31 da parcial; quase todo ele veio da transferência aprendida nos primeiros municípios, e não do comparecimento, e teria caído para 0,14 ponto com o LightGBM, desligado na noite por uma falha técnica. O intervalo de 90% cobriu o resultado em apenas 46% dos instantes. Uma matriz de transição ecológica restrita estima que 61% dos eleitores de Cury votaram em Lula, enquanto 72% dos de Renan Santos e 55% dos de Caiado foram para Flávio. A abstenção caiu 2,92 milhões de eleitores (de 20,8% para 19,0%), mas subiu em sete UFs do Norte e no Maranhão. Nos governos estaduais, o modelo acertou o vencedor cedo nas seis disputas, mas errou a margem por vários pontos nas disputas com poucos municípios e grande mudança em relação ao 1º turno.", { after: 120 }),
  P("**Palavras-chave:** eleições brasileiras; projeção eleitoral; inferência ecológica; aprendizado de máquina; abstenção; segundo turno."),
  new Paragraph({ spacing: { before: 300 }, children: [] }),
  H1c("Abstract"),
  P("Flávio Bolsonaro led the first round of Brazil's 2026 presidential election (47.0% to 45.2% of valid votes in domestic municipalities), and Lula won the runoff with 51.79%. Using only open data from the Superior Electoral Court and the logs of an independent results dashboard, this article asks how a live projection model behaved while municipalities were being reported, where the decisive votes came from, and how turnout changed between rounds. The model combines a bounded transfer regression, a LightGBM residual term, a state-level turnout ratio and a bootstrap. Replayed in the true reporting order of all 5,571 municipalities, it called the right winner from the first data point, with 0.2% of the vote counted and a 99.1% probability, while the official running count showed Flávio ahead between 15% and 50% of the count. The mean projection error was 0.48 points, against 1.31 for the running count; almost all of it came from transfer rates learned in the first municipalities, not from turnout, and it would have fallen to 0.14 points had the LightGBM term not been disabled that night by a technical failure. The 90% interval covered the outcome in only 46% of the snapshots. A constrained ecological transition matrix estimates that 61% of Cury's voters went to Lula, while 72% of Renan Santos's and 55% of Caiado's went to Flávio. Abstention fell by 2.92 million voters (from 20.8% to 19.0%) but rose in seven northern states and Maranhão. In the six gubernatorial runoffs the model called the winner early, but missed the margin by several points in states with few municipalities and large shifts from the first round."),
  P("**Keywords:** Brazilian elections; election night forecasting; ecological inference; machine learning; turnout; runoff."),
];
const sumario = [
  new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun("Sumário")] }),
  new TableOfContents("Sumário", { hyperlink: true, headingStyleRange: "1-2" }),
  P("~Se o sumário aparecer vazio, clique nele com o botão direito e escolha Atualizar campo.~", { run: { size: 18, color: CINZA } }),
];

// ---------------------------------------------------------------- 1 introdução
const intro = [
  H1("1 Introdução"),
  P("A eleição presidencial de 2026 foi decidida no 2º turno, em 25 de outubro, entre Luiz Inácio Lula da Silva (PT) e Flávio Bolsonaro (PL). No 1º turno, em 4 de outubro, Flávio teve a maior votação; três semanas depois, Lula venceu por 4,43 milhões de votos (64.256.232 contra 59.826.041, ou 51,79% dos válidos).[[1]] Também houve 2º turno para governador em seis unidades da federação: Acre, Amazonas, Distrito Federal, Espírito Santo, Rio Grande do Norte e Tocantins."),
  P("Na noite da apuração, o TSE libera os municípios à medida que são totalizados, e a ordem de chegada não é aleatória: capitais, regiões e perfis de eleitorado chegam em momentos diferentes. A parcial oficial, por isso, pode apontar um vencedor diferente do final por boa parte da noite. Um painel independente construído para acompanhar a apuração incluía um modelo que projetava o resultado final a cada ciclo de coleta. Este artigo avalia esse modelo com os registros da própria noite e usa os resultados municipais para entender a virada."),
  P("O trabalho responde a seis perguntas de pesquisa:"),
  N("**Q1. Desempenho.** Quanto a projeção errou ao longo da apuração, comparada à parcial do TSE, e o intervalo de confiança foi honesto?"),
  N("**Q2. Momento do acerto.** A partir de quando a projeção apontou o vencedor certo, e com que probabilidade?"),
  N("**Q3. Origem do erro.** O erro veio da fatia de cada candidato ou do comparecimento estimado, e o termo de aprendizado de máquina teria ajudado?"),
  N("**Q4. Fluxos.** Para onde foram os eleitores dos candidatos eliminados, os que votaram branco ou nulo e os que se abstiveram no 1º turno?"),
  N("**Q5. Comparecimento e perfil.** Onde a abstenção caiu ou subiu, e que composição do eleitorado está associada à mudança de voto e de comparecimento?"),
  N("**Q6. Governadores.** O mesmo modelo funcionou nas disputas estaduais?"),
  P("A seção 2 descreve os dados; a seção 3, os métodos; a seção 4, os resultados; a seção 5 discute limites e melhorias; a seção 6 conclui."),
];

// ---------------------------------------------------------------- 2 dados
const dados = [
  H1("2 Dados"),
  P("Todas as bases vêm de arquivos públicos do TSE (Tabela 1). Os resultados do 2º turno vieram dos arquivos JSON de divulgação (eleições 6258, federal, e 6260, estadual), coletados pelo painel a cada um a cinco minutos durante a noite e gravados num banco SQL Server com o horário de cada coleta."),
  ...tabela("Bases de dados utilizadas", ["Base", "Fonte", "Recorte", "Uso no estudo"], [
    ["Resultado por município, 1º turno", "TSE, divulgação", "Presidente e governador, 04/10/2026", "Variáveis do modelo e fluxos"],
    ["Resultado por município, 2º turno", "TSE, divulgação", "Presidente e governador, 25/10/2026", "Resultado final e fluxos"],
    ["Registros da noite (snapshots)", "Painel, a partir do TSE", "99.166 linhas: Brasil, UF e município ao longo da noite", "Reexecução da projeção"],
    ["Histórico das projeções", "Painel", "Uma linha por ciclo, Presidente e 6 governadores", "Desempenho como rodou"],
    ["Perfil do eleitorado por seção", "TSE, dados abertos", "2026, sexo, idade e escolaridade", "Composição municipal"],
  ], [3, 2, 3, 2.6], "elaboração própria."),
  P("Os dados municipais cobrem os 5.571 municípios; o voto no exterior fica de fora das análises municipais.[[1]] A ordem de chegada dos municípios foi reconstruída a partir dos registros do coletor.[[3]] O eleitorado apto é praticamente o mesmo nos dois turnos (157.828.968 e 157.828.819 nos municípios), o que permite comparar comparecimento e abstenção diretamente."),
];

// ---------------------------------------------------------------- 3 metodologia
const metodo = [
  H1("3 Metodologia"),
  H2("3.1 Modelo de projeção"),
  P("Em cada município ~m~ já totalizado, a fatia de Lula no 2º turno ~y~ é explicada pelas fatias do 1º turno:[[2]]"),
  EQ("{y}_{m} = {s}_{A,m} + γ + Σ {β}_{k} {s}_{k,m} + {u}_{UF(m)} + {f}({x}_{m})", 1),
  P("em que {s}_{A} é a fatia de Lula no 1º turno, {s}_{k} a fatia de cada candidato eliminado (Cury, Renan, Caiado, Zema e os demais), {β}_{k} ∈ [0, 1] a fração do eleitor de ~k~ que foi para Lula, γ o deslocamento comum, ~u~ um efeito de UF encolhido para zero e ~f~ um LightGBM (KE et al., 2017) treinado nos resíduos com o perfil do município, que só entra com 400 municípios ou mais e se reduzir o erro em validação cruzada. Os coeficientes são estimados por mínimos quadrados ponderados pelos votos, com limites e uma penalidade leve em direção a uma hipótese inicial. Antes do primeiro município, a projeção é só essa hipótese inicial."),
  P("Nos municípios ainda não totalizados, a fatia projetada mistura a parcial observada e a prevista pelo modelo, na proporção das seções apuradas. O total de votos esperado é o de válidos do 1º turno vezes uma razão de comparecimento estimada por UF nos municípios já totalizados. A incerteza vem de um bootstrap dos municípios totalizados, somado a um piso de erro, e a probabilidade de vitória supõe distribuição normal."),
  H2("3.2 Reexecução da noite e decomposição do erro"),
  P("Para cada instante de cinco em cinco minutos, das 17h10 às 23h30, reconstruiu-se o estado de cada município (seções apuradas e votos) com o último registro anterior àquele instante e rodou-se o modelo. Três variantes foram comparadas: só transferência, que reproduz exatamente o que rodou na noite; transferência com LightGBM; e duas versões com informação perfeita parcial, que isolam as fontes de erro:"),
  B("**erro só de fatia:** a fatia projetada de cada município aplicada ao total final verdadeiro de votos do município;"),
  B("**erro só de comparecimento:** a fatia final verdadeira de cada município aplicada ao total de votos projetado."),
  H2("3.3 Matriz de transição entre turnos"),
  P("Para estimar para onde foi cada grupo do 1º turno, tomou-se o eleitorado apto de cada município dividido em oito grupos de origem (Lula, Flávio, Cury, Renan, Caiado, Zema e demais, branco ou nulo, abstenção) e três destinos (Lula, Flávio, não votou válido). A matriz ~T~, com linhas somando 1 e entradas não negativas, minimiza o erro quadrático ponderado das fatias do 2º turno:"),
  EQ("min Σ {w}_{m} ‖ {z}_{m} − {T}^{⊤} {o}_{m} ‖² , com T ≥ 0 e T·1 = 1", 2),
  P("em que {o}_{m} são as fatias de origem e {z}_{m} as de destino no município. As restrições evitam as frações acima de 100% que a regressão de Goodman sem restrição produz (GOODMAN, 1953; KING, 1997). O intervalo de 90% vem de 60 reamostragens dos municípios.[[5]]"),
  H2("3.4 Perfil da mudança"),
  P("O ganho de Lula entre turnos, a variação do comparecimento e a abstenção do 2º turno foram regredidos, por mínimos quadrados ponderados com efeito fixo de UF e erros agrupados por UF (CAMERON; MILLER, 2015), sobre a composição do eleitorado do município: proporção com superior completo, de 18 a 24 anos, de 60 anos ou mais e de mulheres.[[7]] O efeito fixo de UF absorve diferenças regionais e de disputa estadual, de modo que os coeficientes comparam municípios do mesmo estado."),
  H2("3.5 Governadores"),
  P("O mesmo modelo foi aplicado a cada UF com 2º turno de governador, tendo como finalista de referência o primeiro da Tabela 5 e os demais candidatos do 1º turno como eliminados.[[6]]"),
];

// ---------------------------------------------------------------- 4 resultados
const res = [
  H1("4 Resultados"),
  H2("4.1 Do 1º ao 2º turno"),
  P("Lula ganhou 10,3 milhões de votos entre os turnos nos municípios brasileiros, e Flávio, 3,7 milhões (Tabela 2). O total de votos válidos cresceu 4,74 milhões: 2,92 milhões de eleitores a mais compareceram e 1,82 milhão a menos votou branco ou nulo."),
  ...tabela("Resultado nos municípios brasileiros, 1º e 2º turno", ["Indicador", "1º turno (04/10)", "2º turno (25/10)", "Variação"], [
    ["Lula (PT)", "53.722.151 (45,16%)", "64.056.078 (51,78%)", "+10.333.927"],
    ["Flávio Bolsonaro (PL)", "55.960.603 (47,04%)", "59.654.544 (48,22%)", "+3.693.941"],
    ["Demais candidatos", "9.287.152 (7,81%)", "–", "–"],
    ["Votos válidos", "118.969.906", "123.710.622", "+4.740.716"],
    ["Brancos e nulos", "5.964.163", "4.144.009", "−1.820.154"],
    ["Abstenção", "32.894.899 (20,84%)", "29.974.188 (18,99%)", "−2.920.711"],
  ], [2.6, 2.4, 2.4, 1.8], "TSE, resultados por município, sem exterior; elaboração própria.", ["l", "r", "r", "r"]),
  P("A virada aparece em quase todo o país. Lula aumentou sua fatia em 5.567 dos 5.571 municípios (mediana de +5,1 pontos) e passou a vencer em 213 municípios onde Flávio tinha vencido no 1º turno; o movimento inverso ocorreu em um único município (Figura 1)."),
  ...figura("f6_dispersao.png", "Fatia de Lula nos válidos por município, 1º e 2º turno", "TSE, 5.571 municípios; tamanho do ponto proporcional ao eleitorado.", 13),

  H2("4.2 Desempenho da projeção na noite"),
  P("Os resultados de Presidente começaram a ser liberados às 19h; o primeiro ciclo com municípios totalizados foi às 19h06. Antes disso, a hipótese inicial do modelo apontava Flávio com 52,5% (probabilidade de 88%), um erro de 4,3 pontos que mostra que as frações de transferência supostas antes da noite estavam erradas. Com os dois primeiros municípios, a projeção passou a 50,94% para Lula, com 99,1% de probabilidade, e o vencedor nunca mais mudou (Figura 2 e Tabela 3). A menor probabilidade registrada depois disso foi de 96,6%, às 19h11."),
  ...figura("f1_noite.png", "Parcial do TSE e projeção de Lula ao longo da apuração do 2º turno", "TSE; registros do painel; reexecução própria. Linha pontilhada: resultado final nos municípios.", 15.5),
  ...tabela("Parcial e projeção em instantes da apuração presidencial", ["Hora", "Contado", "Parcial Lula", "Projeção", "Intervalo de 90%", "P(Lula)", "Com LightGBM"], [
    ["19h06", "0,2%", "51,87%", "50,94%", "50,29 a 51,60", "99,1%", "–"],
    ["19h11", "1,2%", "50,27%", "50,79%", "50,08 a 51,49", "96,6%", "–"],
    ["19h30", "4,2%", "50,77%", "51,24%", "50,57 a 51,92", "99,9%", "–"],
    ["19h45", "12,0%", "50,10%", "51,23%", "50,64 a 51,83", ">99,9%", "–"],
    ["20h10", "28,3%", "49,34%", "51,23%", "50,75 a 51,70", ">99,9%", "51,58%"],
    ["20h34", "55,3%", "50,24%", "51,42%", "51,12 a 51,72", ">99,9%", "51,61%"],
    ["20h54", "78,8%", "51,16%", "51,71%", "51,57 a 51,85", ">99,9%", "51,77%"],
    ["21h10", "96,2%", "51,67%", "51,79%", "51,77 a 51,82", ">99,9%", "51,79%"],
  ], [1, 1.1, 1.3, 1.2, 1.8, 1.1, 1.4], "registros da projeção na noite; última coluna: reexecução com o LightGBM ativo. Resultado final nos municípios: 51,78%.", ["l", "r", "r", "r", "r", "r", "r"]),
  P("Entre o primeiro dado e 99,5% de votos contados, o erro absoluto médio da projeção foi de 0,48 ponto (máximo de 0,99), contra 1,31 ponto da parcial (máximo de 2,44). A parcial mostrou Flávio à frente das 19h50 às 20h30, entre 15% e 50% dos votos contados, enquanto a projeção nunca desceu de 50,8% para Lula. O erro, porém, teve sinal constante: a projeção subestimou Lula durante toda a noite (erro médio de −0,48 ponto) e só convergiu a menos de 0,05 ponto com cerca de 85% dos votos contados. Por isso o intervalo de 90% cobriu o resultado final em apenas 46% dos instantes: ele mede a incerteza dos coeficientes, mas não o viés de quem chega primeiro."),

  H2("4.3 De onde veio o erro"),
  P("A decomposição da Figura 3 responde à pergunta Q3. Com a fatia verdadeira de cada município e o total de votos projetado, o erro médio seria de 0,04 ponto; com a fatia projetada e o total verdadeiro, de 0,31 ponto. O comparecimento, portanto, foi bem estimado, e quase todo o erro veio das frações de transferência aprendidas nos municípios que chegaram primeiro."),
  ...figura("f2_erro.png", "Erro da parcial e da projeção ao longo da apuração, com a decomposição entre fatia e comparecimento", "reexecução própria com os registros da noite.", 15.5),
  P("Os coeficientes mostram o mecanismo (Tabela 4). Nos primeiros municípios, a fração estimada do eleitor de Caiado que foi para Lula era 0,14, e a do eleitor de Renan, 0,25; com todos os municípios, chegaram a 0,31 e 0,35. Os 400 primeiros municípios totalizados eram menores (mediana de 4 mil eleitores, contra 10 mil nos demais), menos escolarizados (17,6% com superior, contra 28,2%) e com pouco peso do Sudeste (10%, contra 31%). Neles, o eleitor de centro-direita migrou menos para Lula do que no país como um todo, e o modelo levou essa fração menor para os municípios que ainda faltavam."),
  ...tabela("Fração do eleitor de cada candidato eliminado que foi para Lula, estimada ao longo da noite (β da equação 1)", ["Candidato no 1º turno", "1,1% contado", "5% contado", "30% contado", "Final", "Intervalo de 90% (final)"], [
    ["Cury (Avante)", "0,46", "0,52", "0,49", "0,55", "0,53 a 0,56"],
    ["Renan Santos (Missão)", "0,25", "0,27", "0,26", "0,35", "0,32 a 0,37"],
    ["Ronaldo Caiado (PSD)", "0,14", "0,19", "0,23", "0,31", "0,30 a 0,33"],
    ["Romeu Zema (NOVO)", "0,16", "0,16", "0,15", "0,17", "0,17 a 0,18"],
  ], [2.8, 1.3, 1.3, 1.3, 1.1, 1.9], "reexecução própria; intervalo por bootstrap de 200 reamostragens dos municípios.", ["l", "r", "r", "r", "r", "r"]),
  P("O termo de LightGBM existe justamente para corrigir esse tipo de diferença de perfil, mas não rodou na noite.[[4]] Na reexecução com ele ativo, o erro médio entre 20% e 96% dos votos contados cai de 0,33 para 0,14 ponto, o erro máximo de 0,67 para 0,33, e o intervalo passa a cobrir o resultado em todos os instantes desse trecho (Tabela 3, última coluna, e Figura 2). Esse ganho, contudo, só começa com 400 municípios totalizados (cerca de 20% dos votos), e a primeira hora continua dependente da transferência."),

  H2("4.4 Para onde foram os votos"),
  P("A matriz de transição (Figura 4) indica que a virada foi construída principalmente com o eleitor de Cury, do qual 61% votaram em Lula e nenhuma fração relevante em Flávio; o restante não votou validamente no 2º turno. O eleitor de Renan Santos foi majoritariamente para Flávio (72%, intervalo de 66% a 78%), assim como o de Caiado (55%), com 40% para Lula. Zema e os demais candidatos, que somaram 0,5% dos válidos, foram inteiramente para Flávio."),
  ...figura("f4_fluxo.png", "Destino no 2º turno de cada grupo de eleitores do 1º turno", "TSE; matriz de transição ecológica com restrições, equação (2).", 15),
  P("Dois resultados exigem cautela. A estimativa de que todo eleitor que votou branco ou nulo no 1º turno votou em Lula no 2º e a de que só 2% dos abstencionistas do 1º turno votaram em Lula estão no limite das restrições. É provável que reflitam parte da mobilização de novos eleitores sendo atribuída ao grupo errado, uma limitação conhecida da inferência ecológica quando grupos pequenos variam junto entre municípios. A conclusão robusta é que os votos novos do 2º turno, vindos de quem antes se absteve ou anulou, favoreceram Lula; a divisão exata entre esses dois grupos não é identificada com segurança."),

  H2("4.5 Abstenção: menor, mas ainda alta"),
  P("A abstenção caiu de 20,8% para 19,0% do eleitorado nos municípios brasileiros, ou 2,92 milhões de pessoas a menos. Ainda assim, 29,97 milhões de eleitores não votaram, quase sete vezes a diferença entre os dois candidatos. A queda se concentrou no Sudeste e no Nordeste: São Paulo (−932 mil), Minas Gerais (−407 mil) e Bahia (−368 mil) respondem por 58% dela. Em sentido contrário, a abstenção subiu em todas as UFs do Norte e no Maranhão: Pará, Amapá, Amazonas, Acre, Maranhão, Roraima, Tocantins e Rondônia (Figura 5); no Amapá, passou de 17,4% para 25,5%, e no Acre, de 20,4% para 26,1%."),
  ...figura("f5_abstencao_uf.png", "Variação da abstenção entre o 1º e o 2º turno, por UF", "TSE, resultados por município; elaboração própria.", 15),
  P("A queda foi maior nos municípios mais escolarizados (Figura 6): no quintil com mais eleitores de nível superior, a abstenção caiu 2,3 pontos; no quintil com menos, 0,7 ponto. Lula cresceu em todos os quintis, de 4,9 pontos no menos escolarizado a 7,3 no mais escolarizado; essa diferença, porém, quase desaparece quando se comparam municípios do mesmo estado (seção 4.6)."),
  ...figura("f8_escolaridade.png", "Abstenção e voto em Lula por quintil de escolaridade do município", "TSE; perfil do eleitorado 2026; elaboração própria.", 15.5),

  H2("4.6 Perfil da mudança"),
  P("Dentro da mesma UF, municípios com mais mulheres tiveram ganho maior de Lula (+0,82 ponto por desvio-padrão) e aumento maior de comparecimento (+0,62 ponto); municípios com mais idosos e mais jovens de 18 a 24 anos tiveram ganho menor de Lula (−0,64 e −0,40 ponto). A abstenção do 2º turno é bem maior onde há mais jovens e mais idosos (+2,5 e +2,4 pontos por desvio-padrão) e menor onde há mais eleitores com superior (−0,6 ponto). A escolaridade quase não explica o ganho de Lula depois do efeito de UF (Figura 7). As associações são municipais e não descrevem eleitores individuais."),
  ...figura("f7_perfil.png", "Associação entre a composição do eleitorado e a mudança entre os turnos", "TSE; regressões ponderadas com efeito fixo de UF e erros agrupados por UF. Pontos azuis: significativos a 5%.", 15.5),

  H2("4.7 Governadores"),
  P("O modelo apontou o vencedor certo desde o primeiro dado em cinco das seis disputas e, no Rio Grande do Norte, a partir de 3,9% dos votos contados (Tabela 5 e Figura 8). O desempenho nos números, porém, foi desigual. No Amazonas, a projeção ficou mais perto do final que a parcial durante toda a noite. No Acre e no Espírito Santo, a parcial foi melhor que a projeção na primeira metade da apuração, e o intervalo cobriu o resultado em só 23% e 10% dos instantes."),
  ...tabela("2º turno de governador: resultado e desempenho da projeção", ["UF", "Finalistas", "1º turno", "2º turno", "Projeção com 5%", "Erro máx. projeção", "Erro máx. parcial", "Vencedor certo desde"], [
    ["AC", "PP x Republicanos", "49,8 x 32,3", "66,2", "60,0", "7,4", "9,0", "0,5%"],
    ["AM", "PSD x PL", "40,6 x 24,5", "61,4", "57,7", "3,7", "7,5", "1,8%"],
    ["DF", "PT x PP", "34,5 x 50,0", "42,8", "41,0", "2,1", "1,5", "0,6%"],
    ["ES", "MDB x Republicanos", "34,1 x 49,7", "47,8", "42,6", "6,4", "4,0", "0,1%"],
    ["RN", "PT x União", "36,2 x 36,9", "50,8", "51,1", "2,3", "20,3", "3,9%"],
    ["TO", "União x PSDB", "45,5 x 43,9", "35,5", "45,9", "11,9", "20,3", "0,1%"],
  ], [0.7, 2.2, 1.5, 1, 1.3, 1.3, 1.3, 1.5], "TSE; reexecução própria. Percentuais do primeiro finalista nos válidos; erros em pontos percentuais.", ["l", "l", "r", "r", "r", "r", "r", "r"]),
  ...figura("f3_governadores.png", "Parcial e projeção nas seis disputas de governador", "TSE; reexecução própria. Faixa azul: intervalo de 90%.", 15.5),
  P("Os dois piores casos têm causas diferentes. No Tocantins, o candidato do União liderou o 1º turno com 45,5% e terminou com 35,5%: perdeu eleitores próprios, e não só deixou de ganhar os dos eliminados. A equação (1) supõe que quem votou num finalista fica com ele e só representa uma perda desse tipo pelo termo comum γ, que nos primeiros municípios ainda estava preso à hipótese inicial; a projeção ficou até 12 pontos acima do resultado. No Espírito Santo, o problema foi o mesmo da disputa presidencial, ampliado pelo número pequeno de municípios (78): nos 66 municípios que somaram a primeira metade dos votos, o MDB ganhou 9,4 pontos sobre o 1º turno; nos 12 maiores, totalizados depois das 21h, ganhou 18,0 pontos, em alguns deles mais do que toda a votação do PT no 1º turno. O modelo, com o coeficiente do PT já no limite de 1, subestimou o candidato em 4 a 5 pontos até a metade da apuração. No DF, que é um único município, a projeção dependeu da hipótese inicial e da parcial."),
];

// ---------------------------------------------------------------- 5 discussão
const disc = [
  H1("5 Discussão"),
  H2("5.1 O que funcionou"),
  P("O resultado mais importante é o mais simples: com dois municípios totalizados, o modelo identificou o vencedor que a parcial do TSE só confirmaria mais de uma hora depois, e manteve essa leitura durante os 40 minutos em que a parcial mostrava Flávio na frente. Isso decorre da ideia central do modelo: comparar cada município com ele mesmo no 1º turno elimina a maior parte do viés de ordem de chegada, porque o que importa é quanto cada lugar mudou, e não quanto ele vota em cada candidato. O comparecimento, a outra metade da projeção, foi estimado com erro desprezível."),
  H2("5.2 O que falhou"),
  P("Três problemas aparecem, em ordem de gravidade. Primeiro, o intervalo de 90% foi otimista: a projeção teve viés de sinal constante porque os primeiros municípios não são uma amostra aleatória do país, e o bootstrap não captura isso. Segundo, o termo de aprendizado de máquina, que reduziria esse viés à metade, estava desligado por uma falha técnica na noite. Terceiro, nas disputas estaduais com poucos municípios, esse mesmo viés foi maior, e a hipótese de que o eleitor do finalista fica com ele falhou onde houve mudança real de lado, como no Tocantins. A hipótese inicial do modelo, usada antes do primeiro dado, também estava errada e apontava Flávio, o que reforça que o modelo é útil para ler a apuração, e não para prever a eleição antes dela."),
  H2("5.3 Melhorias propostas para o modelo"),
  B("**Viés de ordem de chegada no intervalo.** Somar ao bootstrap um termo de erro que diminua com a fração contada, calibrado na reexecução das noites de 2022 e de 2026, de modo que a cobertura de 90% seja verdadeira."),
  B("**Pós-estratificação dos primeiros municípios.** Até 400 municípios, reponderar os totalizados para que reproduzam a composição do país por região, porte e perfil; com isso, as frações de transferência dos primeiros minutos deixam de refletir só o interior."),
  B("**Retenção dos finalistas.** Estimar também a fração do eleitor de cada finalista que fica com ele, com limite inferior e penalidade, para que trocas de lado como a do Tocantins possam aparecer."),
  B("**LightGBM robusto.** Já corrigido no código publicado: treino em uma thread, trava global e reserva para a transferência pura, com registro no histórico de quando o termo é usado."),
  B("**DF por zona eleitoral.** Usar as zonas do DF como unidades de aprendizado, em vez de um único município."),
  H2("5.4 Limitações"),
  B("**Inferência ecológica.** Fluxos e associações de perfil valem para municípios, não para eleitores; resultados no limite das restrições, como o de brancos e nulos, não são identificados com segurança (ROBINSON, 1950; KING, 1997)."),
  B("**Ordem de chegada aproximada.** A ordem foi reconstruída pelo horário de coleta, com resolução de cerca de cinco minutos, e não pelo horário oficial de totalização."),
  B("**Exterior.** As análises municipais excluem o voto no exterior, que não altera nenhuma conclusão."),
  B("**Causas da abstenção no Norte.** O aumento da abstenção nas sete UFs do Norte e no Maranhão foi medido, mas suas causas (logística, clima, desmobilização local) não foram testadas."),
];

// ---------------------------------------------------------------- 6 conclusão
const concl = [
  H1("6 Conclusão"),
  P("A eleição de 2026 foi virada no 2º turno com votos que, no 1º, não eram de nenhum dos dois finalistas: o eleitor de Cury, em sua maioria, e eleitores que antes não tinham votado validamente. Flávio herdou a maior parte do eleitor de Renan Santos, de Caiado e de Zema, o que não bastou. A abstenção caiu quase 3 milhões, sobretudo no Sudeste e no Nordeste, mas permaneceu perto de 30 milhões de eleitores, e subiu na maior parte do Norte."),
  P("Como instrumento de leitura da apuração, o modelo do painel cumpriu o principal: apontou o vencedor certo com 0,2% dos votos contados e errou, em média, pouco mais de um terço do que errou a parcial. Seu ponto fraco foi a calibração da incerteza e a dependência dos primeiros municípios, ambos tratáveis com as melhorias da seção 5.3. Nos governos estaduais, o modelo é confiável para o vencedor, mas não para a margem nas UFs com poucos municípios ou quando o eleitor de um finalista muda de lado."),
  P("O código do painel, do modelo e da reexecução está no repositório eleicoes-2026. Como agenda, as mesmas ferramentas podem ser aplicadas às eleições municipais de 2028, em que a ordem de chegada das seções dentro de cada cidade terá papel semelhante ao dos municípios em 2026."),
];

// ---------------------------------------------------------------- referências
const REF = [
  "CAMERON, A. C.; MILLER, D. L. A practitioner's guide to cluster-robust inference. ~Journal of Human Resources~, v. 50, n. 2, p. 317-372, 2015.",
  "EFRON, B.; TIBSHIRANI, R. J. ~An introduction to the bootstrap~. New York: Chapman & Hall, 1993.",
  "GOODMAN, L. A. Ecological regressions and behavior of individuals. ~American Sociological Review~, v. 18, n. 6, p. 663-664, 1953.",
  "KE, G. et al. LightGBM: a highly efficient gradient boosting decision tree. In: ~Advances in Neural Information Processing Systems 30~. 2017. p. 3146-3154.",
  "KING, G. ~A solution to the ecological inference problem~: reconstructing individual behavior from aggregate data. Princeton: Princeton University Press, 1997.",
  "ROBINSON, W. S. Ecological correlations and the behavior of individuals. ~American Sociological Review~, v. 15, n. 3, p. 351-357, 1950.",
  "TRIBUNAL SUPERIOR ELEITORAL. Divulgação de resultados das Eleições 2026: arquivos de dados por município, 1º e 2º turno. Disponível em: https://resultados.tse.jus.br/. Acesso em: 26 out. 2026.",
  "TRIBUNAL SUPERIOR ELEITORAL. Portal de Dados Abertos do TSE: perfil do eleitorado por seção eleitoral, 2026. Disponível em: https://dadosabertos.tse.jus.br/. Acesso em: 26 out. 2026.",
];
const refs = [H1("Referências"), ...REF.map(r => new Paragraph({ children: runs(r), alignment: AlignmentType.LEFT, spacing: { after: 160, line: 264 } }))];

// ---------------------------------------------------------------- documento
const cab = new Header({ children: [new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: AM, space: 4 } },
  children: [new TextRun({ text: "Eleições 2026  |  Artigo científico com dados abertos", size: 16, color: CINZA })] })] });
const rod = new Footer({ children: [new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: W }],
  children: [new TextRun({ text: "Eduardo Cândido  |  outubro de 2026", size: 16, color: CINZA }), new TextRun({ text: "\t", size: 16 }),
    new TextRun({ children: [PageNumber.CURRENT], size: 16, color: CINZA }), new TextRun({ text: " / ", size: 16, color: CINZA }),
    new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: CINZA })] })] });
const margens = { top: 1701, right: 1134, bottom: 1134, left: 1701, header: 709, footer: 567 };

const doc = new Document({
  creator: "Eduardo Cândido", title: "Eleições 2026: a virada do 2º turno e a projeção em tempo real", description: "Artigo científico independente",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: FONT, color: PRETO }, paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: AM, space: 6 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: FONT, color: PRETO }, paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: [
    { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 567, hanging: 283 } } } }] },
    { reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 567, hanging: 340 } } } }] },
  ] },
  footnotes,
  sections: [
    { properties: { page: { size: { width: 11906, height: 16838 }, margin: margens } }, children: capa },
    { properties: { page: { size: { width: 11906, height: 16838 }, margin: margens } }, headers: { default: cab }, footers: { default: rod },
      children: [...resumo, ...sumario, ...intro, ...dados, ...metodo, ...res, ...disc, ...concl, ...refs] },
  ],
});
Packer.toBuffer(doc).then(b => { fs.writeFileSync(path.join(__dirname, "..", "resultados", "Eleicoes_2026_artigo_gerado.docx"), b); console.log("ok", b.length); });
