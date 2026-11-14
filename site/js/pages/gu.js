// 구 목록 / 구 상세: 추이, 동별 분해, 단지 목록
import { $, $$, D, F, cls, esc, get, table, chart, seriesChart, css, loadIndex, bandLabel } from '../core.js';
import { kpiCard, NH_COLS, withHref, ageChart, controls } from './home.js';

export const APT_COLS = [
  { k: 'name', label: '단지', fmt: (v, r) => `<b>${esc(v)}</b>${r.nh ? '<span class="tag nh">신고가</span>' : ''}` },
  { k: 'umd', label: '동' },
  { k: 'by', label: '준공', num: 1 },
  { k: 'hh', label: '세대', num: 1, fmt: v => F.n(v), need: 'kapt' },
  { k: 'a', label: '면적', num: 1, fmt: v => `${v}㎡`, tip: '거래가 가장 많은 대표 면적' },
  { k: 'price', label: '최근 시세', num: 1, fmt: v => F.eok(v), tip: '최근 6개월 중위 거래가(없으면 마지막 거래)' },
  { k: 'ppy', label: '평단가', num: 1, fmt: v => F.man(v) },
  { k: 'dd', label: '고점 대비', num: 1, color: 1, fmt: v => F.pct(v) },
  { k: 'jr', label: '전세가율', num: 1, fmt: v => F.pct0(v) },
  { k: 'n12', label: '1년 거래', num: 1, fmt: v => F.n(v) },
];

async function list(el) {
  const meta = D.meta;
  const docs = await Promise.all(meta.sidos.map(s => get(`sido/${s.code}.json`)));
  el.innerHTML = `<h1>구별 보기</h1><p class="muted small">구를 누르면 추이·동별·단지 목록이 나와요. 오름세가 서열 위에서 아래로 어디까지 번졌는지는 <a href="#/flow"><b>서열과 확산</b></a>에서 한눈에 볼 수 있어요.</p>` + docs.map(d => `
    <div class="card"><h2>${esc(d.name)}</h2><div class="guc">${[...d.gus].sort((a, b) => (b.ppy || 0) - (a.ppy || 0)).map(g => `
      <a href="#/gu/${g.sgg}"><div class="kpi"><div class="lab">${esc(g.name)}</div><div class="val">${F.man(g.ppy)}</div>
      <div class="sub"><span class="${cls(g.chg3m)}">${F.pct(g.chg3m)}</span> <span class="muted">· ${F.n(g.vol3m)}건</span></div></div></a>`).join('')}</div>
      <p class="note">숫자 = 최근 3개월 중위 평단가(3.3㎡당) · 직전 3개월 대비(같은 집끼리 비교) · 지난 3개월 거래량</p></div>`).join('');
}

export async function render(el, r) {
  const sgg = r.parts[0];
  if (!sgg || !D.guName[sgg]) return list(el);
  const [g, index] = await Promise.all([get(`gu/${sgg}.json`), loadIndex()]);
  const s = g.stats, meta = D.meta;
  let band = 'all', months = 60, ch, aptBand = 'all', dong = '';
  el.innerHTML = `
    <div class="head"><div><h1>${esc(g.name)}</h1><p class="muted small">거래 기준일 ${g.asof} · 단지 ${F.n(s.apts)}곳</p></div>
      <select id="go" aria-label="다른 구로 이동">${Object.entries(D.guName).map(([c, n]) => `<option value="${c}" ${c === sgg ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
    <div class="kpis">
      ${kpiCard('중위 평단가 (3.3㎡당)', F.man(s.ppy), `같은 집끼리 비교 · 직전 3개월 대비 <b class="${cls(s.chg3m)}">${F.pct(s.chg3m)}</b>`)}
      ${kpiCard('지난 3개월 거래량', `${F.n(s.vol3m)}건`, `그 전 3개월 대비 <b class="${cls(s.volchg)}">${F.pct(s.volchg)}</b>`)}
      ${kpiCard('전세가율', F.pct0(s.jr), '같은 단지·면적끼리 비교한 중간값')}
      ${kpiCard('전고점 대비', F.pct(s.dd), `1년 전 대비 ${F.pct(s.yoy)}`, cls(s.dd))}
    </div>
    <div class="card"><h2>거래량과 평단가 추이</h2>
      <div class="row" id="ctl" style="margin-bottom:8px">${controls(meta.bands, band, months)}</div>
      <div class="chart" id="c-main"></div>
      <p class="note">면적 구간별 평단가(최근 3개월): ${meta.bands.map(b => `${esc(b.label)} <b>${F.man(s.band_ppy[b.key])}</b>`).join(' · ')}</p></div>
    <div class="grid two">
      <div class="card"><div class="head"><h2>동별 비교</h2></div><div id="t-dong"></div></div>
      <div class="card"><div class="head"><h2>동별 평단가 추이</h2>
        <select id="dong" aria-label="동 선택">${g.dongs.map(d => `<option>${esc(d.umd)}</option>`).join('')}</select></div>
        <div class="chart sm" id="c-dong"></div></div>
    </div>
    <div class="card"><div class="head"><h2>단지 목록</h2>
      <div class="chips" id="apt-ctl"><button class="chip on" data-v="all">전체</button>${meta.bands.map(b => `<button class="chip" data-v="${b.key}">${esc(b.label)}</button>`).join('')}</div></div>
      <div id="t-apt"></div></div>
    <div class="grid two">
      <div class="card"><h2>최근 신고가</h2><div id="t-nh"></div></div>
      <div class="card"><h2>연식별 평단가 (최근 6개월)</h2><div class="chart sm" id="c-age"></div></div>
    </div>`;

  const drawMain = () => { if (ch) ch.dispose(); ch = seriesChart($('#c-main', el), g.series, { band, months }); };
  drawMain();
  $('#ctl', el).onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    if (b.parentElement.dataset.g === 'band') band = b.dataset.v; else months = +b.dataset.v;
    $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); drawMain();
  };
  $('#go', el).onchange = e => { location.hash = `#/gu/${e.target.value}`; };

  table($('#t-dong', el), {
    sort: 'ppy', limit: 12, csv: `${g.name}_동별_${g.asof}.csv`, rows: g.dongs,
    cols: [{ k: 'umd', label: '동' }, { k: 'ppy', label: '평단가', num: 1, fmt: v => F.man(v) },
      { k: 'chg3m', label: '3개월', num: 1, color: 1, fmt: v => F.pct(v) }, { k: 'yoy', label: '1년', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'vol3m', label: '거래량', num: 1, fmt: v => F.n(v) }, { k: 'jr', label: '전세가율', num: 1, fmt: v => F.pct0(v) }],
  });
  let dch;
  const drawDong = () => {
    if (dch) dch.dispose();
    const ds = g.dong_series[dong]; if (!ds) return;
    const guMap = new Map(g.series.m.map((m, i) => [m, g.series.ppy[i]]));
    dch = chart($('#c-dong', el), {
      xAxis: { type: 'category', data: ds.m, axisLabel: { formatter: v => v.slice(2) } },
      yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: css('--line') } } },
      series: [{ name: dong, type: 'line', data: ds.ppy, symbol: 'none', connectNulls: true, lineStyle: { width: 2.5 }, itemStyle: { color: css('--up') } },
        { name: `${g.name} 전체`, type: 'line', data: ds.m.map(m => guMap.get(m) ?? null), symbol: 'none', connectNulls: true, lineStyle: { type: 'dashed' }, itemStyle: { color: css('--muted') } }],
    });
  };
  dong = g.dongs.length ? [...g.dongs].sort((a, b) => (b.vol3m || 0) - (a.vol3m || 0))[0].umd : '';
  $('#dong', el).value = dong; drawDong();
  $('#dong', el).onchange = e => { dong = e.target.value; drawDong(); };

  const mine = index.filter(o => o.sgg === sgg);
  const aptT = table($('#t-apt', el), { cols: APT_COLS, rows: mine, sort: 'n12', limit: 20, csv: `${g.name}_단지목록_${g.asof}.csv` });
  $('#apt-ctl', el).onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    aptBand = b.dataset.v; $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b));
    aptT.update(aptBand === 'all' ? mine : mine.filter(o => o.band === aptBand));
  };
  table($('#t-nh', el), { cols: NH_COLS.filter(c => c.k !== 'gu'), rows: withHref(g.newhighs), sort: 'date', limit: 8, empty: '최근 30일 신고가가 없어요' });
  ageChart($('#c-age', el), g.age);
  void bandLabel;
}
