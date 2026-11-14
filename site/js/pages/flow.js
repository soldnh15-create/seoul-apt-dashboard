// 서열과 확산: 구를 평단가 순(서열)으로 세워 오름세가 어디까지 번졌는지 보고, 구끼리 10년 흐름을 겹쳐 본다.
// 모두 지금까지의 실거래 기록이다. 전망·추천을 담지 않는다.
import { $, $$, D, F, cls, esc, get, chart, css, median, setQuery, share } from '../core.js';

const METRICS = [
  { k: 'yoy', label: '1년 변동률', desc: '1년 전 같은 3개월 대비 · 같은 집끼리 비교', fmt: F.pct, signed: 1 },
  { k: 'chg3m', label: '3개월 변동률', desc: '직전 3개월 대비 · 같은 집끼리 비교', fmt: F.pct, signed: 1 },
  { k: 'dd', label: '전고점 대비', desc: '같은 집끼리 비교한 흐름이 가장 높았던 때 대비(3개월 단위)', fmt: F.pct, signed: 1 },
  { k: 'nh30', label: '최근 30일 신고가', desc: '이전 최고가를 넘은 거래 건수', fmt: v => (v == null ? '-' : `${F.n(v)}건`) },
];
const COLORS = ['#e03131', '#1971c2', '#2f9e44', '#f08c00'];
const PERIODS = [[12, '3년'], [20, '5년'], [40, '10년']];   // 분기 수

/** 서열을 위·가운데·아래 셋으로 나눠 각 띠의 중간값을 낸다(어느 띠가 가장 뜨거운지 한 줄로). */
export function bands3(gus, k) {
  const n = gus.length, cut = [Math.round(n / 3), Math.round(n * 2 / 3)];
  return [[0, cut[0]], [cut[0], cut[1]], [cut[1], n]].map(([a, b]) => {
    const v = gus.slice(a, b).map(g => g[k]).filter(x => x != null);
    return { from: a + 1, to: b, med: v.length ? Math.round(median(v) * 10) / 10 : null };
  });
}

/** 지수를 기간 시작 = 100 으로 다시 맞춘다. idx: {m, v}, months: 맞출 달 목록 */
export function rebase(idx, months) {
  const map = new Map(idx.m.map((m, i) => [m, idx.v[i]]));
  const base = months.map(m => map.get(m)).find(v => v != null);      // 시작 분기가 비어 있으면 그다음 분기를 출발점으로
  return months.map(m => (base && map.get(m) != null ? Math.round(map.get(m) / base * 1000) / 10 : null));
}

export async function render(el, r) {
  const meta = D.meta, sido = meta.sidos[0];
  const doc = await get(`sido/${sido.code}.json`);
  const gus = [...doc.gus].filter(g => g.ppy).sort((a, b) => b.ppy - a.ppy).map((g, i) => ({ ...g, rank: i + 1 }));
  const hasIdx = doc.gu_idx && doc.idx && doc.idx.m.length > 2;
  const pick = n => (gus[Math.min(gus.length - 1, n)] || {}).sgg;
  let metric = METRICS.some(m => m.k === r.q.m) ? r.q.m : 'yoy';
  let period = PERIODS.some(p => String(p[0]) === r.q.p) ? +r.q.p : 20;
  // 처음에는 서열 1위 · 가운데 · 맨 아래 구를 겹쳐 보여 준다(위가 먼저, 아래가 나중인지 바로 보이게)
  let sel = (r.q.g ? r.q.g.split(',') : [pick(0), pick(Math.floor(gus.length / 2)), pick(gus.length - 1)]).filter(c => D.guName[c]).slice(0, 4);
  const site = meta.site || {};

  el.innerHTML = `
    <h1>서열과 확산</h1>
    <p class="muted small">${esc(sido.name)}의 구를 평단가 순(서열)으로 세우고, 오름세가 어디까지 번졌는지 봐요. 거래 기준일 ${doc.asof} · 지금까지의 실거래 기록이며 전망이 아니에요.</p>
    <div class="card"><div class="head"><h2>서열 순으로 본 구별 흐름</h2><button class="btn sm primary" id="share">공유</button></div>
      <div class="chips" id="metric" style="margin:6px 0 10px">${METRICS.filter(m => gus.some(g => g[m.k] != null)).map(m => `<button class="chip ${m.k === metric ? 'on' : ''}" data-v="${m.k}">${esc(m.label)}</button>`).join('')}</div>
      <p class="flow-sum" id="sum"></p>
      <div class="flow" id="bars"></div>
      <p class="note" id="mnote"></p>
    </div>
    ${hasIdx ? `<div class="card"><h2>구끼리 흐름 겹쳐 보기</h2>
      <p class="muted small" style="margin:0 0 8px">구를 4곳까지 골라 같은 출발점(= 100)에서 겹쳐 봐요. 어느 구가 먼저 오르고 어느 구가 뒤따랐는지 보여요.</p>
      <div class="row" style="margin-bottom:8px"><select id="add" aria-label="구 추가"><option value="">구 추가…</option>${gus.map(g => `<option value="${g.sgg}">${g.rank}위 ${esc(g.name)}</option>`).join('')}</select>
        <span class="chips" id="sel"></span></div>
      <div class="chips" id="period" style="margin-bottom:8px">${PERIODS.map(([n, l]) => `<button class="chip ${n === period ? 'on' : ''}" data-v="${n}">${l}</button>`).join('')}</div>
      <div class="chart lg" id="c"></div>
      <div class="tblwrap"><table class="tbl" id="t"></table></div>
      <p class="note">과거 각 시점(3개월 단위)을 지금과 같은 단지·같은 면적끼리 직접 비교한 흐름이에요(기간 시작 = 100). 비싼 집이 많이 팔린 달에 평균이 튀는 영향을 뺐어요. 거래가 적은 구는 선이 들쭉날쭉할 수 있어요. 점선은 ${esc(sido.name)} 전체.</p>
    </div>` : ''}
    <div class="card"><h2>이 화면을 읽는 법</h2>
      <ol class="flow-how">
        <li><b>서열 위쪽이 먼저 움직였는지</b> 봐요. 위쪽 구의 1년 변동률이 작아지고 3개월 변동률이 0 근처면, 먼저 오른 곳이 쉬는 구간이에요.</li>
        <li><b>막대가 가장 긴 띠가 서열 몇 위쯤인지</b> 봐요. 지금 오름세가 몰려 있는 자리예요.</li>
        <li><b>그 아래 서열은 전고점까지 얼마나 남았는지</b> 봐요('전고점 대비'로 바꿔 보기).</li>
        <li>관심 있는 구를 누르면 그 구의 동별·단지별 화면으로 이어져요. 같은 순서(1등 동 → 다른 동 → 단지)로 내려가 보세요.</li>
      </ol>
      <p class="note">순서를 보여 줄 뿐, 앞으로의 가격을 말하지 않아요. 매수 추천이 아니에요.${site.home_url ? ` 서열과 확산을 읽는 기준은 <a href="${esc(site.home_url)}" target="_blank" rel="noopener">${esc(site.brand || '')} 강의</a>에서 차근차근 다뤄요.` : ''}</p>
    </div>`;

  const q = () => setQuery('/flow', { m: metric, p: String(period), g: sel.join(',') });

  // ── 서열 막대 ──
  const drawBars = () => {
    const m = METRICS.find(x => x.k === metric);
    const vals = gus.map(g => g[m.k]).filter(v => v != null);
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), span = hi - lo || 1;
    const zero = (0 - lo) / span * 100;                       // 0 기준선 위치(%)
    $('#bars', el).innerHTML = gus.map(g => {
      const v = g[m.k];
      const w = v == null ? 0 : Math.abs(v) / span * 100;
      const left = v == null || v >= 0 ? zero : zero - w;
      return `<a class="flow-row" href="#/gu/${g.sgg}"><span class="rk">${g.rank}</span><span class="nm">${esc(g.name)}</span><span class="pp">${F.man(g.ppy)}</span>
        <span class="bar"><i class="z" style="left:${zero}%"></i><i class="b ${m.signed ? cls(v) : 'cnt'}" style="left:${left}%;width:${w}%"></i></span>
        <span class="vl ${m.signed ? cls(v) : ''}">${m.fmt(v)}</span></a>`;
    }).join('');
    const b = bands3(gus, m.k);
    const txt = x => (m.k === 'nh30' ? `${F.n(x)}건` : F.pct(x));
    $('#sum', el).innerHTML = b.every(x => x.med != null)
      ? `서열 <b>${b[0].from}~${b[0].to}위</b> ${txt(b[0].med)} · <b>${b[1].from}~${b[1].to}위</b> ${txt(b[1].med)} · <b>${b[2].from}~${b[2].to}위</b> ${txt(b[2].med)} <span class="muted small">(각 띠의 중간값)</span>` : '';
    $('#mnote', el).textContent = `${m.label}: ${m.desc}. 평단가는 최근 3개월 중위(3.3㎡당). 구를 누르면 그 구 화면으로 가요.`;
  };
  $('#metric', el).onclick = e => {
    const b = e.target.closest('.chip'); if (!b) return;
    metric = b.dataset.v; $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); drawBars(); q();
  };
  $('#share', el).onclick = () => share('서울 아파트 서열과 확산');
  drawBars();

  // ── 구끼리 겹쳐 보기 ──
  if (hasIdx) {
    let ch;
    const drawCmp = () => {
      $('#sel', el).innerHTML = sel.map((c, i) => `<button class="chip on" data-c="${c}" style="background:${COLORS[i]};border-color:${COLORS[i]};color:#fff">${esc(D.guName[c])} ✕</button>`).join('') || '<span class="muted small">구를 골라 주세요</span>';
      const months = doc.idx.m.slice(-(period + 1));
      const lines = sel.map((c, i) => ({ c, name: D.guName[c], color: COLORS[i], v: rebase(doc.gu_idx[c] || { m: [], v: [] }, months) }));
      const all = rebase(doc.idx, months);
      if (ch) ch.dispose();
      ch = chart($('#c', el), {
        tooltip: { trigger: 'axis', confine: true, valueFormatter: v => (v == null ? '-' : v.toFixed(1)) },
        xAxis: { type: 'category', data: months, axisLabel: { formatter: v => v.slice(2) } },
        yAxis: { type: 'value', scale: true, splitLine: { lineStyle: { color: css('--line') } } },
        series: [...lines.map(l => ({ name: l.name, type: 'line', data: l.v, symbol: 'none', connectNulls: true, lineStyle: { width: 2.5 }, itemStyle: { color: l.color } })),
          { name: `${sido.short || sido.name} 전체`, type: 'line', data: all, symbol: 'none', connectNulls: true, lineStyle: { width: 1.5, type: 'dashed' }, itemStyle: { color: css('--muted') } }],
      });
      // 기간 안에서 가장 높았던 때와 지금을 표로(누가 먼저 고점을 찍었는지)
      const row = (name, v, color) => {
        const ok = v.map((x, i) => [x, i]).filter(x => x[0] != null);
        if (!ok.length) return `<tr><td>${esc(name)}</td><td class="num" colspan="3">자료가 부족해요</td></tr>`;
        const peak = ok.reduce((a, b) => (b[0] > a[0] ? b : a)), last = ok[ok.length - 1];
        return `<tr><td>${color ? `<b style="color:${color}">${esc(name)}</b>` : esc(name)}</td><td class="num">${last[0].toFixed(1)}</td>
          <td class="num">${months[peak[1]].replace('-', '년 ')}월 (${peak[0].toFixed(1)})</td><td class="num ${cls(last[0] - peak[0])}">${F.pct((last[0] / peak[0] - 1) * 100)}</td></tr>`;
      };
      $('#t', el).innerHTML = `<thead><tr><th>구</th><th class="num">지금 (시작 = 100)</th><th class="num">기간 안 가장 높았던 때</th><th class="num">그때 대비</th></tr></thead><tbody>${
        lines.map(l => row(l.name, l.v, l.color)).join('')}${row(`${sido.short || sido.name} 전체`, all)}</tbody>`;
    };
    $('#add', el).onchange = e => {
      const c = e.target.value; e.target.value = '';
      if (!c || sel.includes(c)) return;
      if (sel.length >= 4) sel.shift();
      sel.push(c); drawCmp(); q();
    };
    $('#sel', el).onclick = e => { const b = e.target.closest('.chip'); if (!b) return; sel = sel.filter(c => c !== b.dataset.c); drawCmp(); q(); };
    $('#period', el).onclick = e => {
      const b = e.target.closest('.chip'); if (!b) return;
      period = +b.dataset.v; $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); drawCmp(); q();
    };
    drawCmp();
  }
}
