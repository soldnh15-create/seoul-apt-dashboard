// 홈: 시도 요약 — 핵심 지표, 추이, 구별 순위, 신고가
import { $, $$, D, S, F, cls, esc, get, table, chart, seriesChart, css, isDark, setQuery, loadIndex } from '../core.js';

export const kpiCard = (lab, val, sub = '', c = '') => `<div class="kpi"><div class="lab">${lab}</div><div class="val ${c}">${val}</div><div class="sub muted">${sub}</div></div>`;

export const NH_COLS = [
  { k: 'date', label: '계약일' }, { k: 'gu', label: '구' },
  { k: 'name', label: '단지', fmt: (v, r) => `${esc(v)} <span class="muted small">${r.a}㎡</span>` },
  { k: 'floor', label: '층', num: 1 },
  { k: 'price', label: '거래가', num: 1, fmt: v => F.eok(v) },
  { k: 'prev', label: '직전 최고가', num: 1, fmt: v => F.eok(v) },
  { k: 'rise', label: '상승률', num: 1, color: 1, fmt: v => F.pct(v) },
];
export const AN_COLS = [
  { k: 'date', label: '계약일' }, { k: 'gu', label: '구' },
  { k: 'name', label: '단지', fmt: (v, r) => `${esc(v)} <span class="muted small">${r.a}㎡</span>` },
  { k: 'price', label: '거래가', num: 1, fmt: v => F.eok(v) },
  { k: 'ref', label: '직전 6개월 시세', num: 1, fmt: v => F.eok(v) },
  { k: 'disc', label: '차이', num: 1, color: 1, fmt: v => F.pct(v) },
];
export const withHref = rows => rows.map(x => ({ ...x, href: `#/apt/${x.sgg}/${x.id}` }));

export function ageChart(el, age) {
  return chart(el, {
    legend: { show: false }, xAxis: { type: 'category', data: age.map(a => a.label) },
    yAxis: { type: 'value', name: '3.3㎡당(만원)', splitLine: { lineStyle: { color: css('--line') } } },
    series: [{ type: 'bar', data: age.map(a => a.ppy), barMaxWidth: 36, itemStyle: { color: css('--accent'), borderRadius: [6, 6, 0, 0] }, label: { show: true, position: 'top', formatter: p => F.n(p.value), fontSize: 11 } }],
  });
}

export function controls(bands, band, months) {
  return `<div class="chips" data-g="band"><button class="chip ${band === 'all' ? 'on' : ''}" data-v="all">전체 면적</button>${
    bands.map(b => `<button class="chip ${band === b.key ? 'on' : ''}" data-v="${b.key}">${esc(b.label)}</button>`).join('')}</div>
  <div class="chips" data-g="months">${[[36, '3년'], [60, '5년'], [120, '10년'], [0, '전체']].map(([v, l]) =>
    `<button class="chip ${months === v ? 'on' : ''}" data-v="${v}">${l}</button>`).join('')}</div>`;
}

export async function render(el, r) {
  const meta = D.meta;
  const code = meta.sidos.some(s => s.code === r.q.sido) ? r.q.sido : meta.sidos[0].code;
  const [d, macro] = await Promise.all([get(`sido/${code}.json`), meta.features.macro ? get('macro.json').catch(() => null) : null]);
  const k = d.kpi;
  let band = 'all', months = 60, useMacro = false, nhDays = 30, ch;
  const weekAgo = new Date(new Date(d.asof) - 7 * 864e5).toISOString().slice(0, 10);
  const pv = S.prevVisit;
  const sinceN = pv ? d.newhighs.filter(x => x.date > pv.asof).length : 0;

  el.innerHTML = `
    <div class="head"><div><h1>${esc(d.short)} 아파트 실거래 한눈에</h1>
      <p class="muted small">거래 기준일 ${d.asof} · 매일 자동 갱신 · 최근 달은 신고 기한(30일) 때문에 더 늘 수 있어요</p></div>
      ${meta.sidos.length > 1 ? `<select id="sido" aria-label="지역">${meta.sidos.map(s => `<option value="${s.code}" ${s.code === code ? 'selected' : ''}>${esc(s.name)}</option>`).join('')}</select>` : ''}
    </div>
    ${pv ? `<div class="card since"><b>지난 방문(${esc(pv.asof)} 기준) 이후</b> 새 신고가 ${F.n(sinceN)}건이 더해졌어요. ${Object.keys(S.watch).length ? '<a href="#/my">관심 단지 변화 보기 →</a>' : ''}</div>` : ''}
    <div class="kpis">
      ${kpiCard('중위 평단가 (3.3㎡당)', F.man(k.ppy), `같은 집끼리 비교 · 직전 3개월 대비 <b class="${cls(k.chg3m)}">${F.pct(k.chg3m)}</b>`)}
      ${kpiCard('지난달 매매 신고', `${F.n(k.vol_last)}건`, `그 전달 ${F.n(k.vol_prev)}건`)}
      ${kpiCard('전세가율', F.pct0(k.jr), '같은 단지·면적끼리 비교한 중간값')}
      ${kpiCard('최근 30일 신고가', `${F.n(k.nh30)}건`, `최근 7일 ${F.n(k.nh7)}건`)}
      ${kpiCard('1년 전 대비', F.pct(k.yoy), '같은 단지·면적끼리 비교한 중간값', cls(k.yoy))}
      ${kpiCard('전고점 대비', F.pct(k.dd), '같은 집끼리 비교한 흐름 기준(3개월 단위)', cls(k.dd))}
      ${kpiCard('해제 거래 비율', F.pct0(k.cancel), '최근 3개월')}
      ${kpiCard('직거래 비율', F.pct0(k.direct), '최근 3개월')}
    </div>
    <div class="card">
      <div class="head"><h2>거래량과 평단가 추이</h2>
        ${macro ? '<label class="small"><input type="checkbox" id="macro"> 금리 겹쳐 보기</label>' : ''}</div>
      <div class="row" id="ctl" style="margin-bottom:8px">${controls(meta.bands, band, months)}</div>
      <div class="chart" id="c-main"></div>
    </div>
    <div class="card"><div class="head"><h2>구별 순위</h2><span class="muted small">제목을 누르면 정렬돼요 · <a href="#/flow">서열과 확산으로 보기 →</a></span></div><div id="t-gu"></div></div>
    <div class="card"><div class="head"><h2>단지 순위</h2>
      <div class="chips" id="rk-ctl"><button class="chip on" data-k="n12" data-d="-1">거래 많은 순</button><button class="chip" data-k="chg1y" data-d="-1">1년 많이 오른 순</button>
        <button class="chip" data-k="dd" data-d="1">고점 대비 많이 내린 순</button><button class="chip" data-k="jr" data-d="-1">전세가율 높은 순</button></div></div>
      <div id="t-rk"><p class="muted small">불러오는 중…</p></div>
      <p class="note">각 단지의 대표 면적 기준. 1년 넘게 거래가 없는 단지와 전용 40㎡ 미만(원룸형)은 빼요. 순위일 뿐 추천이 아니에요.</p></div>
    <div class="card">
      <div class="head"><h2>신고가 거래</h2>
        <div class="chips" id="nh-ctl"><button class="chip" data-v="7">최근 7일</button><button class="chip on" data-v="30">최근 30일</button></div></div>
      <div id="t-nh"></div>
      <p class="note">신고가 = 같은 단지·같은 면적에서 이전 최고가를 넘은 거래(이전 거래 ${meta.params.new_high_min_prior}건 이상일 때). 해제된 거래는 뺐어요.</p>
    </div>
    <div class="grid two">
      <div class="card"><h2>주간 매매 거래량 (최근 26주)</h2><div class="chart sm" id="c-week"></div></div>
      <div class="card"><h2>연식별 평단가 (최근 6개월)</h2><div class="chart sm" id="c-age"></div></div>
    </div>
    <details class="card"><summary><b>시세보다 낮은 직거래 ${F.n(d.anoms.length)}건</b> <span class="muted small">(참고용)</span></summary>
      <div id="t-an" style="margin-top:10px"></div>
      <p class="note">직거래이면서 같은 단지·면적의 직전 6개월 중개거래 중위가보다 ${meta.params.anomaly_direct_discount_pct}% 이상 낮은 거래. 가족 간 거래 등 사정이 있을 수 있어 시세 계산에서는 뺐어요.</p>
    </details>`;

  const drawMain = () => { if (ch) ch.dispose(); ch = seriesChart($('#c-main', el), d.series, { band, months, macro: useMacro ? macro : null }); };
  drawMain();
  $('#ctl', el).onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    const g = b.parentElement.dataset.g;
    if (g === 'band') band = b.dataset.v; else months = +b.dataset.v;
    $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b));
    drawMain();
  };
  if (macro) $('#macro', el).onchange = e => { useMacro = e.target.checked; drawMain(); };
  if ($('#sido', el)) $('#sido', el).onchange = e => { location.hash = `#/?sido=${e.target.value}`; };

  table($('#t-gu', el), {
    sort: 'ppy', limit: 30, csv: `${d.short}_구별순위_${d.asof}.csv`,
    rows: d.gus.map(g => ({ ...g, href: `#/gu/${g.sgg}` })),
    cols: [
      { k: 'name', label: '구', fmt: v => `<b>${esc(v)}</b>` },
      { k: 'ppy', label: '평단가', num: 1, fmt: v => F.man(v), tip: '최근 3개월 중위, 3.3㎡당' },
      { k: 'chg3m', label: '3개월', num: 1, color: 1, fmt: v => F.pct(v), tip: '같은 단지·면적끼리 비교 · 직전 3개월 대비' },
      { k: 'yoy', label: '1년', num: 1, color: 1, fmt: v => F.pct(v), tip: '같은 단지·면적끼리 비교 · 1년 전 같은 3개월 대비' },
      { k: 'vol3m', label: '거래량', num: 1, fmt: v => F.n(v), tip: '지난 3개월(끝난 달) 매매 건수' },
      { k: 'volchg', label: '거래 증감', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'jr', label: '전세가율', num: 1, fmt: v => F.pct0(v) },
      { k: 'dd', label: '고점 대비', num: 1, color: 1, fmt: v => F.pct(v) },
    ],
  });
  const nhRows = () => withHref(d.newhighs.filter(x => nhDays === 30 || x.date >= weekAgo));
  const nhT = table($('#t-nh', el), { cols: NH_COLS, rows: nhRows(), sort: 'date', limit: 15, csv: `${d.short}_신고가_${d.asof}.csv`, empty: '이 기간에 신고가 거래가 없어요' });
  $('#nh-ctl', el).onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    nhDays = +b.dataset.v; $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); nhT.update(nhRows());
  };
  table($('#t-an', el), { cols: AN_COLS, rows: withHref(d.anoms), sort: 'date', limit: 10, csv: `${d.short}_저가직거래_${d.asof}.csv` });
  chart($('#c-week', el), {
    legend: { show: false }, xAxis: { type: 'category', data: d.weekly.w.map(w => w.slice(5)) },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: css('--line') } } },
    series: [{ type: 'bar', name: '매매(건)', data: d.weekly.n, itemStyle: { color: isDark() ? '#5c7cfa' : '#4263eb', borderRadius: [4, 4, 0, 0] } }],
  });
  ageChart($('#c-age', el), d.age);
  setQuery('/', { sido: code === meta.sidos[0].code ? '' : code });

  // 단지 순위는 색인을 받은 뒤에 채운다(첫 화면을 늦추지 않게)
  Promise.all([loadIndex(), import('./gu.js')]).then(([index, gu]) => {
    const sggs = new Set(d.gus.map(g => g.sgg));
    // 원룸형(전용 40㎡ 미만)은 분양 물량이 한꺼번에 신고돼 순위를 왜곡하므로 순위에서만 뺀다(검색·조건 검색에는 그대로 있음).
    const rows = index.filter(o => sggs.has(o.sgg) && !o.stale && o.a >= 40);
    const cols = [{ k: 'gu', label: '구' }, ...gu.APT_COLS.filter(c => !['umd', 'by', 'hh'].includes(c.k)), { k: 'chg1y', label: '1년', num: 1, color: 1, fmt: v => F.pct(v) }];
    const show = (k, dir) => table($('#t-rk', el), { cols, rows: rows.filter(o => o[k] != null), sort: k, dir, limit: 10, csv: `${d.short}_단지순위_${d.asof}.csv` });
    show('n12', -1);
    $('#rk-ctl', el).onclick = e => {
      const b = e.target.closest('.chip'); if (!b) return;
      $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); show(b.dataset.k, +b.dataset.d);
    };
  }).catch(() => { const t = $('#t-rk', el); if (t) t.innerHTML = '<p class="muted small">단지 순위를 불러오지 못했어요.</p>'; });
}
