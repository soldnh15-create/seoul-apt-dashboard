// 내 기준 점수: 항목별 가중치를 정하면 단지 순위를 매겨 준다(백분위 점수)
import { $, D, S, save, F, esc, table, loadIndex, encState, decState, setQuery, share, toast } from '../core.js';

export const CRIT = [
  { k: 'dd', label: '가격 메리트', desc: '전고점보다 많이 내려와 있을수록', dir: -1 },
  { k: 'jr', label: '전세가율', desc: '높을수록(갭이 작을수록)', dir: 1 },
  { k: 'hh', label: '단지 규모', desc: '세대수가 많을수록', dir: 1 },
  { k: 'by', label: '연식', desc: '새 아파트일수록', dir: 1 },
  { k: 'turn', label: '거래 활발', desc: '세대수 대비 거래가 많을수록', dir: 1 },
  { k: 'sub', label: '역 접근성', desc: '지하철역이 가까울수록', dir: -1 },
];
const DEFAULT = { dd: 30, jr: 20, hh: 15, by: 15, turn: 10, sub: 10 };

/** 각 항목을 0~1 백분위로 바꾼 뒤 가중 평균(0~100점). 값이 없는 항목은 중간(0.5)으로 본다. */
export function scoreRows(rows, w) {
  const total = CRIT.reduce((s, c) => s + (w[c.k] || 0), 0) || 1;
  const pr = {};
  for (const c of CRIT) {
    const vals = rows.map(o => o[c.k]).filter(v => v != null).sort((a, b) => a - b);
    pr[c.k] = v => {
      if (v == null || vals.length < 2) return 0.5;
      let lo = 0, hi = vals.length;
      while (lo < hi) { const m = (lo + hi) >> 1; if (vals[m] < v) lo = m + 1; else hi = m; }
      const p = lo / (vals.length - 1);
      return c.dir > 0 ? Math.min(1, p) : 1 - Math.min(1, p);
    };
  }
  return rows.map(o => ({ ...o, score: Math.round(CRIT.reduce((s, c) => s + (w[c.k] || 0) * pr[c.k](o[c.k]), 0) / total * 1000) / 10 }));
}

export async function render(el, r) {
  const index = await loadIndex(), meta = D.meta;
  const q = r.q.w && decState(r.q.w);
  let w = { ...DEFAULT, ...(q ? q.w : S.weights || {}) }, band = (q && q.band) || 'std', gu = (q && q.gu) || '';
  el.innerHTML = `
    <h1>내 기준 점수</h1><p class="muted small">무엇을 중요하게 볼지 정하면, 그 기준으로 단지 순위를 매겨요. 점수는 같은 조건 단지들 안에서의 상대 위치(백분위)예요.</p>
    <div class="grid side">
      <div class="card"><div class="head"><h2>순위</h2><span class="muted small" id="cnt"></span></div><div id="res"></div>
        <p class="note">내가 정한 기준으로 정렬한 것일 뿐, 매수 추천이나 수익 보장이 아니에요.</p></div>
      <div class="card"><h2>중요도</h2><div id="sl"></div>
        <div class="row" style="margin:10px 0"><select id="band" aria-label="면적">${[['all', '전체 면적'], ...meta.bands.map(b => [b.key, b.label])].map(([k, l]) => `<option value="${k}" ${k === band ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select>
          <select id="gu" aria-label="지역"><option value="">전체 지역</option>${Object.entries(D.guName).map(([c, n]) => `<option value="${c}" ${c === gu ? 'selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
        <div class="row"><button class="btn sm" id="reset">처음 값으로</button><button class="btn sm" id="savew">가중치 저장</button><button class="btn sm primary" id="share">공유</button></div>
        <div class="row" style="margin-top:10px"><span class="muted small">저장한 가중치</span><span id="presets" class="chips"></span></div>
        ${meta.features.geo ? '' : '<p class="note">역 접근성은 좌표 데이터가 있을 때만 반영돼요.</p>'}</div>
    </div>`;
  const t = table($('#res', el), {
    rows: [], sort: 'score', limit: 30, csv: `내기준점수_${meta.asof}.csv`,
    cols: [{ k: 'score', label: '점수', num: 1, fmt: v => `<b>${v.toFixed(1)}</b>` }, { k: 'name', label: '단지', fmt: v => `<b>${esc(v)}</b>` }, { k: 'gu', label: '구' },
      { k: 'a', label: '면적', num: 1, fmt: v => `${v}㎡` }, { k: 'price', label: '최근 시세', num: 1, fmt: v => F.eok(v) },
      { k: 'dd', label: '고점 대비', num: 1, color: 1, fmt: v => F.pct(v) }, { k: 'jr', label: '전세가율', num: 1, fmt: v => F.pct0(v) },
      { k: 'hh', label: '세대', num: 1, fmt: v => F.n(v) }, { k: 'by', label: '준공', num: 1 }, { k: 'turn', label: '회전율', num: 1, fmt: v => F.pct0(v) },
      { k: 'sub', label: '역 거리', num: 1, fmt: v => F.m(v) }],
  });
  const run = () => {
    const rows = index.filter(o => !o.stale && (band === 'all' || o.band === band) && (!gu || o.sgg === gu));
    t.update(scoreRows(rows, w));
    $('#cnt', el).textContent = `${F.n(rows.length)}개 단지`;
    S.weights = w; save();
    setQuery('/score', { w: encState({ w, band, gu }) });
  };
  const drawSl = () => {
    $('#sl', el).innerHTML = CRIT.map(c => `<div class="slider" title="${esc(c.desc)}"><label for="w-${c.k}">${esc(c.label)}<br><span class="muted small">${esc(c.desc)}</span></label>
      <input type="range" id="w-${c.k}" data-k="${c.k}" min="0" max="50" step="5" value="${w[c.k] || 0}"><b id="v-${c.k}">${w[c.k] || 0}</b></div>`).join('');
    $('#presets', el).innerHTML = S.presets.score.map((p, i) => `<button class="chip" data-p="${i}">${esc(p.name)}</button><button class="chip" data-pd="${i}" aria-label="삭제">✕</button>`).join('') || '<span class="muted small">없음</span>';
  };
  el.oninput = e => { const k = e.target.dataset && e.target.dataset.k; if (!k) return; w[k] = +e.target.value; $(`#v-${k}`, el).textContent = w[k]; run(); };
  el.onchange = e => { if (e.target.id === 'band') { band = e.target.value; run(); } else if (e.target.id === 'gu') { gu = e.target.value; run(); } };
  el.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.id === 'reset') w = { ...DEFAULT };
    else if (b.id === 'savew') { const name = prompt('이 가중치의 이름을 정해 주세요', `내 기준 ${S.presets.score.length + 1}`); if (!name) return; S.presets.score.push({ name, w: { ...w } }); save(); toast('저장했어요'); }
    else if (b.id === 'share') { share('내 기준 아파트 점수'); return; }
    else if (b.dataset.p) w = { ...DEFAULT, ...S.presets.score[+b.dataset.p].w };
    else if (b.dataset.pd) { S.presets.score.splice(+b.dataset.pd, 1); save(); }
    else return;
    drawSl(); run();
  };
  drawSl(); run();
}
