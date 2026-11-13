// 조건 검색: 조건을 쌓아 단지를 거르고, 조건을 주소에 담아 공유
import { $, $$, D, S, save, F, esc, table, loadIndex, encState, decState, setQuery, share, toast } from '../core.js';
import { APT_COLS } from './gu.js';

export const FIELDS = [
  { k: 'a', label: '대표 면적(㎡)' }, { k: 'price', label: '최근 시세(억)', scale: 10000 },
  { k: 'ppy', label: '평단가(만원/3.3㎡)' }, { k: 'dd', label: '전고점 대비(%)' }, { k: 'reb', label: '저점 대비 반등(%)' },
  { k: 'jr', label: '전세가율(%)' }, { k: 'gap', label: '갭(억)', scale: 10000 }, { k: 'hh', label: '세대수' },
  { k: 'by', label: '준공연도' }, { k: 'age', label: '연식(년)' }, { k: 'n12', label: '최근 1년 거래(건)' },
  { k: 'turn', label: '회전율(%)' }, { k: 'chg1y', label: '1년 전 대비(%)' }, { k: 'sub', label: '지하철역 거리(m)' },
];
const EXAMPLES = [
  { name: '84㎡ · 고점 -15% 이하 · 전세가율 60%↑ · 500세대↑', st: { band: 'std', gu: [], conds: [{ k: 'dd', op: 'le', v: -15 }, { k: 'jr', op: 'ge', v: 60 }, { k: 'hh', op: 'ge', v: 500 }] } },
  { name: '소형 · 갭 2억 이하 · 역 500m 안', st: { band: 'small', gu: [], conds: [{ k: 'gap', op: 'le', v: 2 }, { k: 'sub', op: 'le', v: 500 }] } },
  { name: '준공 10년 이내 · 1,000세대↑', st: { band: 'all', gu: [], conds: [{ k: 'age', op: 'le', v: 10 }, { k: 'hh', op: 'ge', v: 1000 }] } },
];

export function applyFilter(index, st) {
  return index.filter(o => {
    if (o.stale) return false;
    if (st.band && st.band !== 'all' && o.band !== st.band) return false;
    if (st.gu && st.gu.length && !st.gu.includes(o.sgg)) return false;
    for (const c of st.conds || []) {
      const f = FIELDS.find(x => x.k === c.k);
      if (!f || c.v === '' || c.v == null || isNaN(c.v)) continue;
      const v = o[c.k];
      if (v == null) return false;
      const t = c.v * (f.scale || 1);
      if (c.op === 'ge' ? v < t : v > t) return false;
    }
    return true;
  });
}

export async function render(el, r) {
  const index = await loadIndex(), meta = D.meta;
  let st = (r.q.c && decState(r.q.c)) || { band: 'all', gu: [], conds: [{ k: 'dd', op: 'le', v: -10 }] };
  st.conds = st.conds || []; st.gu = st.gu || [];
  el.innerHTML = `
    <h1>조건 검색</h1><p class="muted small">조건을 쌓아서 단지를 골라 보세요. 조건은 주소에 담겨서 그대로 공유할 수 있어요. (1년 넘게 거래가 없는 단지는 빼요)</p>
    <div class="card">
      <div class="row" style="margin-bottom:10px"><span class="muted small">예시</span>${EXAMPLES.map((e, i) => `<button class="chip" data-ex="${i}">${esc(e.name)}</button>`).join('')}</div>
      <div class="row" style="margin-bottom:10px"><span class="muted small">내 조건</span><span id="presets" class="chips"></span></div>
      <div class="row" style="margin-bottom:10px"><span class="muted small">면적</span><div class="chips" id="band"></div></div>
      <div class="row" style="margin-bottom:10px"><span class="muted small">지역</span>
        <select id="gu-add"><option value="">구 추가…</option>${Object.entries(D.guName).map(([c, n]) => `<option value="${c}">${esc(n)}</option>`).join('')}</select>
        <span id="gus" class="chips"></span></div>
      <div id="conds"></div>
      <div class="row" style="margin-top:8px"><button class="btn sm" id="add">+ 조건 추가</button>
        <button class="btn sm" id="savep">이 조건 저장</button><button class="btn sm primary" id="share">조건 공유</button></div>
    </div>
    <div class="card"><div class="head"><h2>결과</h2><span class="muted small" id="cnt"></span></div><div id="res"></div>
      <p class="note">조건에 맞는 단지를 나열한 것일 뿐, 매수 추천이 아니에요.</p></div>`;

  const t = table($('#res', el), { cols: [{ k: 'gu', label: '구' }, ...APT_COLS, { k: 'gap', label: '갭', num: 1, fmt: v => F.eok(v) }, { k: 'sub', label: '역 거리', num: 1, fmt: v => F.m(v) }], rows: [], sort: 'dd', dir: 1, limit: 30, csv: `조건검색_${meta.asof}.csv` });
  const run = () => {
    const rows = applyFilter(index, st);
    t.update(rows);
    $('#cnt', el).textContent = `${F.n(rows.length)} / ${F.n(index.length)}개 단지`;
    setQuery('/screener', { c: encState(st) });
  };
  const drawForm = () => {
    $('#band', el).innerHTML = `<button class="chip ${st.band === 'all' ? 'on' : ''}" data-v="all">전체</button>` + meta.bands.map(b => `<button class="chip ${st.band === b.key ? 'on' : ''}" data-v="${b.key}">${esc(b.label)}</button>`).join('');
    $('#gus', el).innerHTML = st.gu.map(c => `<button class="chip on" data-g="${c}">${esc(D.guName[c] || c)} ✕</button>`).join('') || '<span class="muted small">전체</span>';
    $('#conds', el).innerHTML = st.conds.map((c, i) => `<div class="cond" data-i="${i}">
      <select class="f" aria-label="항목">${FIELDS.map(f => `<option value="${f.k}" ${f.k === c.k ? 'selected' : ''}>${esc(f.label)}</option>`).join('')}</select>
      <select class="o" aria-label="비교"><option value="ge" ${c.op === 'ge' ? 'selected' : ''}>이상 (≥)</option><option value="le" ${c.op === 'le' ? 'selected' : ''}>이하 (≤)</option></select>
      <input class="v" type="number" step="any" value="${c.v ?? ''}" aria-label="값"><button class="btn sm del" aria-label="조건 삭제">✕</button></div>`).join('');
    $('#presets', el).innerHTML = S.presets.screener.map((p, i) => `<button class="chip" data-p="${i}">${esc(p.name)}</button><button class="chip" data-pd="${i}" aria-label="삭제">✕</button>`).join('') || '<span class="muted small">저장한 조건이 없어요</span>';
  };
  el.onclick = e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.ex) st = structuredClone(EXAMPLES[+b.dataset.ex].st);
    else if (b.dataset.p) st = structuredClone(S.presets.screener[+b.dataset.p].st);
    else if (b.dataset.pd) { S.presets.screener.splice(+b.dataset.pd, 1); save(); }
    else if (b.dataset.v && b.closest('#band')) st.band = b.dataset.v;
    else if (b.dataset.g) st.gu = st.gu.filter(c => c !== b.dataset.g);
    else if (b.id === 'add') st.conds.push({ k: 'jr', op: 'ge', v: 50 });
    else if (b.classList.contains('del')) st.conds.splice(+b.closest('.cond').dataset.i, 1);
    else if (b.id === 'savep') { const name = prompt('이 조건의 이름을 정해 주세요', `내 조건 ${S.presets.screener.length + 1}`); if (!name) return; S.presets.screener.push({ name, st: structuredClone(st) }); save(); toast('저장했어요'); }
    else if (b.id === 'share') { share('아파트 조건 검색'); return; }
    else return;
    drawForm(); run();
  };
  el.onchange = e => {
    if (e.target.id === 'gu-add') { if (e.target.value && !st.gu.includes(e.target.value)) st.gu.push(e.target.value); e.target.value = ''; drawForm(); run(); return; }
    const row = e.target.closest('.cond'); if (!row) return;
    const c = st.conds[+row.dataset.i];
    c.k = $('.f', row).value; c.op = $('.o', row).value; c.v = $('.v', row).value === '' ? '' : +$('.v', row).value;
    run();
  };
  el.oninput = e => { if (e.target.classList.contains('v')) el.onchange(e); };
  drawForm(); run();
  void $$;
}
