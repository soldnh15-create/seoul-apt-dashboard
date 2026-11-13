// 단지 비교: 최대 4곳의 평단가 흐름과 핵심 지표를 나란히
import { $, D, F, cls, esc, get, chart, css, loadIndex, searchItems, setQuery, debounce, share, PY, toast } from '../core.js';
import { movingMedian } from './apt.js';

const COLORS = ['#e03131', '#1971c2', '#2f9e44', '#f08c00'];

export async function render(el, r) {
  const index = await loadIndex();
  let ids = (r.q.ids || '').split(',').filter(Boolean).map(x => x.split('~')).filter(x => D.byId.has(x[1])).slice(0, 4);
  el.innerHTML = `
    <h1>단지 비교</h1><p class="muted small">최대 4곳까지 담아서 흐름을 겹쳐 볼 수 있어요. 각 단지의 대표 면적(거래가 가장 많은 면적) 기준이에요.</p>
    <div class="card"><div class="row"><div style="position:relative;flex:1 1 220px">
      <input type="search" class="in" id="add" placeholder="비교할 단지 이름 검색" autocomplete="off" style="width:100%" aria-label="비교할 단지 검색"><div class="qres" id="add-res" hidden></div></div>
      <button class="btn sm primary" id="share">공유</button></div>
      <div class="chips" id="sel" style="margin-top:10px"></div></div>
    <div class="card"><h2>평단가 흐름 (3.3㎡당, 3개월 중위)</h2><div class="chart lg" id="c"></div></div>
    <div class="card"><h2>나란히 보기</h2><div class="tblwrap"><table class="tbl" id="t"></table></div></div>`;
  let ch;
  const draw = async () => {
    setQuery('/compare', { ids: ids.map(x => x.join('~')).join(',') });
    $('#sel', el).innerHTML = ids.map(([, id], i) => `<button class="chip on" data-i="${i}" style="background:${COLORS[i]};border-color:${COLORS[i]};color:#fff">${esc(D.byId.get(id).name)} ✕</button>`).join('') || '<span class="muted small">위에서 단지를 검색해 담아 주세요.</span>';
    const apts = await Promise.all(ids.map(([sgg, id]) => get(`apt/${sgg}/${id}.json`)));
    if (ch) ch.dispose();
    ch = chart($('#c', el), {
      tooltip: { trigger: 'axis', valueFormatter: v => F.man(v) }, xAxis: { type: 'time' },
      yAxis: { type: 'value', scale: true, name: '만원', splitLine: { lineStyle: { color: css('--line') } } }, dataZoom: [{ type: 'inside' }],
      series: apts.map((a, i) => {
        const t = a.types.find(x => x.a === a.main);
        const pts = a.trades.filter(x => Math.floor(x[1]) === a.main && !(x[4] & 9)).map(x => [x[0], x[3] / t.area * PY]);
        return { name: `${a.name} ${a.main}㎡`, type: 'line', symbol: 'none', smooth: .2, lineStyle: { width: 2.5 }, itemStyle: { color: COLORS[i] }, data: movingMedian(pts) };
      }),
    });
    const o = ids.map(([, id]) => D.byId.get(id));
    const rowsDef = [['구 · 동', x => `${esc(x.gu)} ${esc(x.umd)}`], ['준공', x => F.yr(x.by)], ['세대수', x => F.n(x.hh)], ['대표 면적', x => `${x.a}㎡`],
      ['최근 시세', x => `<b>${F.eok(x.price)}</b>`], ['평단가', x => F.man(x.ppy)], ['전고점 대비', x => `<span class="${cls(x.dd)}">${F.pct(x.dd)}</span>`],
      ['1년 전 대비', x => `<span class="${cls(x.chg1y)}">${F.pct(x.chg1y)}</span>`], ['전세가율', x => F.pct0(x.jr)], ['갭', x => F.eok(x.gap)],
      ['1년 거래', x => `${F.n(x.n12)}건`], ['역 거리', x => F.m(x.sub)]];
    $('#t', el).innerHTML = o.length ? `<thead><tr><th></th>${o.map((x, i) => `<th class="num"><a href="${x.href}" style="color:${COLORS[i]}">${esc(x.name)}</a></th>`).join('')}</tr></thead><tbody>${
      rowsDef.map(([lab, f]) => `<tr><td class="muted">${lab}</td>${o.map(x => `<td class="num">${f(x)}</td>`).join('')}</tr>`).join('')}</tbody>` : '<tbody><tr><td class="empty">담은 단지가 없어요</td></tr></tbody>';
  };
  const inp = $('#add', el), box = $('#add-res', el);
  inp.oninput = debounce(() => {
    const items = searchItems(index, inp.value, 8);
    box.innerHTML = items.map(o => `<a data-id="${o.id}" data-sgg="${o.sgg}"><span>${esc(o.name)}</span><span class="muted small">${esc(o.gu)} · ${F.eokS(o.price)}</span></a>`).join('');
    box.hidden = !items.length;
  }, 120);
  box.onclick = e => {
    const a = e.target.closest('a'); if (!a) return;
    if (ids.length >= 4) toast('4곳까지만 담을 수 있어요');
    else if (!ids.some(x => x[1] === a.dataset.id)) ids.push([a.dataset.sgg, a.dataset.id]);
    inp.value = ''; box.hidden = true; draw();
  };
  $('#sel', el).onclick = e => { const b = e.target.closest('.chip'); if (!b) return; ids.splice(+b.dataset.i, 1); draw(); };
  $('#share', el).onclick = () => share('아파트 단지 비교');
  await draw();
}
