// 단지 상세: 개별 거래 점 + 이동 중위선, 매매·전세 겹쳐 보기, 층별, 낙폭·갭, 스펙
import { $, $$, D, S, save, F, cls, esc, get, table, chart, css, median, toast, share, bandLabel, isDark } from '../core.js';
import { kpiCard } from './home.js';

/** 월별 이동 중위선: 그 달 포함 최근 3개월 거래의 중위값 */
export function movingMedian(points, win = 3) {
  if (!points.length) return [];
  const byM = new Map();
  for (const [d, v] of points) { const m = d.slice(0, 7); if (!byM.has(m)) byM.set(m, []); byM.get(m).push(v); }
  const months = []; let [y, mo] = points[0][0].slice(0, 7).split('-').map(Number);
  const end = points[points.length - 1][0].slice(0, 7);
  for (;;) { const m = `${y}-${String(mo).padStart(2, '0')}`; months.push(m); if (m >= end) break; if (++mo > 12) { mo = 1; y++; } }
  const out = [];
  months.forEach((m, i) => {
    const vals = []; for (let j = Math.max(0, i - win + 1); j <= i; j++) vals.push(...(byM.get(months[j]) || []));
    if (vals.length) out.push([`${m}-15`, Math.round(median(vals))]);
  });
  return out;
}

const FLOORS = [[1, 3, '1~3층'], [4, 7, '4~7층'], [8, 12, '8~12층'], [13, 20, '13~20층'], [21, 999, '21층~']];

export async function render(el, r) {
  const [sgg, id] = r.parts;
  const apt = await get(`apt/${sgg}/${id}.json`);
  let a = apt.types.some(t => t.a === +r.q.a) ? +r.q.a : apt.main;
  let showRent = true, range = 0, ch, fch;
  const asof = D.meta.asof;
  const w = () => S.watch[apt.id];

  const draw = () => {
    const t = apt.types.find(x => x.a === a);
    const trades = apt.trades.filter(x => Math.floor(x[1]) === a);
    const rents = apt.rents.filter(x => Math.floor(x[1]) === a);
    const from = range ? new Date(new Date(asof) - range * 365 * 864e5).toISOString().slice(0, 10) : '';
    const inR = x => x[0] >= from;
    const target = w() && w().target;
    $('#stats', el).innerHTML = `
      ${kpiCard('최근 시세', F.eok(t.recent), t.stale ? '<b class="down">1년 넘게 거래 없음</b>' : `최근 6개월 ${t.rn}건 중위 · 평단가 ${F.man(t.ppy)}`)}
      ${kpiCard('전고점 대비', F.pct(t.dd), `최고 ${F.eok(t.peak)} (${t.peak_d.slice(0, 7)})`, cls(t.dd))}
      ${kpiCard('전세 · 전세가율', t.jeonse ? `${F.eok(t.jeonse)}` : '-', t.jr != null ? `전세가율 <b>${F.pct0(t.jr)}</b> · 갭 <b>${F.eok(t.gap)}</b>` : '최근 전세 거래 없음')}
      ${kpiCard('1년 전 대비', F.pct(t.chg1y), t.reb != null ? `고점 뒤 저점(${F.eok(t.trough)}) 대비 ${F.pct(t.reb)}` : '고점 이후 거래 없음', cls(t.chg1y))}
      ${kpiCard('저층 / 그 외 층', `${F.eokS(t.low)} / ${F.eokS(t.high)}`, `${D.meta.params.low_floor_max}층 이하 / 초과 · 최근 2년 중위`)}
      ${kpiCard('1년 거래 · 회전율', `${F.n(apt.n12)}건`, apt.turn != null ? `세대수 대비 ${F.pct0(apt.turn)}` : apt.spec && apt.spec.shared ? '여러 단지가 한 묶음이라 회전율은 계산하지 않아요' : '세대수 정보 없음')}
      ${target ? kpiCard('내 목표가', F.eok(target), `현재 시세가 목표가보다 <b class="${cls(t.recent - target)}">${F.pct((t.recent - target) / target * 100)}</b>`) : ''}`;

    const pt = x => ({ value: [x[0], x[3]], f: x[2], fl: x[4] });
    const ok = trades.filter(x => !(x[4] & 1) && inR(x));
    const series = [
      { name: '매매', type: 'scatter', symbolSize: 7, itemStyle: { color: isDark() ? '#adb5bd' : '#495057', opacity: .75 }, data: ok.filter(x => !(x[4] & 14)).map(pt) },
      { name: '신고가', type: 'scatter', symbolSize: 11, itemStyle: { color: css('--up') }, data: ok.filter(x => x[4] & 4).map(pt) },
      { name: '직거래', type: 'scatter', symbol: 'diamond', symbolSize: 9, itemStyle: { color: css('--down') }, data: ok.filter(x => (x[4] & 2) && !(x[4] & 4)).map(pt) },
      { name: '해제', type: 'scatter', symbol: 'emptyCircle', symbolSize: 8, itemStyle: { color: '#adb5bd' }, data: trades.filter(x => (x[4] & 1) && inR(x)).map(pt) },
      { name: '매매 중위선', type: 'line', symbol: 'none', smooth: .2, lineStyle: { width: 2.5, color: css('--up') }, itemStyle: { color: css('--up') },
        data: movingMedian(trades.filter(x => !(x[4] & 9)).map(x => [x[0], x[3]])).filter(inR) },
    ];
    if (showRent) {
      const js = rents.filter(x => !x[4]);
      series.push({ name: '전세', type: 'scatter', symbolSize: 5, itemStyle: { color: '#37b24d', opacity: .45 }, data: js.filter(inR).map(x => ({ value: [x[0], x[3]], f: x[2], rn: x[5] })) },
        { name: '전세 중위선', type: 'line', symbol: 'none', smooth: .2, lineStyle: { width: 2, type: 'dashed', color: '#37b24d' }, itemStyle: { color: '#37b24d' }, data: movingMedian(js.map(x => [x[0], x[3]])).filter(inR) });
    }
    if (target) series[4].markLine = { silent: true, symbol: 'none', lineStyle: { color: css('--accent'), type: 'dashed' }, label: { formatter: '목표가', color: css('--accent') }, data: [{ yAxis: target }] };
    if (ch) ch.dispose();
    ch = chart($('#c-main', el), {
      tooltip: { trigger: 'item', confine: true, formatter: p => p.seriesType === 'line'
        ? `${p.seriesName}<br>${p.value[0].slice(0, 7)} · <b>${F.eok(p.value[1])}</b>`
        : `${p.seriesName} · ${p.value[0]}<br><b>${F.eok(p.value[1])}</b>${p.data.f != null ? ` · ${p.data.f}층` : ''}${p.data.rn ? ' · 갱신' : ''}` },
      xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
      yAxis: { type: 'value', scale: true, axisLabel: { formatter: v => F.eokS(v) }, splitLine: { lineStyle: { color: css('--line') } } },
      dataZoom: [{ type: 'inside' }], series,
    });

    const y3 = new Date(new Date(asof) - 3 * 365 * 864e5).toISOString().slice(0, 10);
    const rec = trades.filter(x => !(x[4] & 9) && x[0] >= y3 && x[2] != null);
    const fl = FLOORS.map(([lo, hi, lab]) => { const v = rec.filter(x => x[2] >= lo && x[2] <= hi).map(x => x[3]); return { lab, med: v.length ? Math.round(median(v)) : null, n: v.length }; }).filter(x => x.n);
    if (fch) fch.dispose();
    fch = chart($('#c-floor', el), {
      legend: { show: false }, xAxis: { type: 'category', data: fl.map(x => x.lab) },
      yAxis: { type: 'value', scale: true, axisLabel: { formatter: v => F.eokS(v) }, splitLine: { lineStyle: { color: css('--line') } } },
      tooltip: { trigger: 'axis', formatter: ps => `${ps[0].name}<br><b>${F.eok(ps[0].value)}</b> · ${fl[ps[0].dataIndex].n}건` },
      series: [{ type: 'bar', data: fl.map(x => x.med), barMaxWidth: 40, itemStyle: { color: css('--accent'), borderRadius: [6, 6, 0, 0] }, label: { show: true, position: 'top', fontSize: 11, formatter: p => `${fl[p.dataIndex].n}건` } }],
    });

    const tag = f => `${f & 4 ? '<span class="tag nh">신고가</span>' : ''}${f & 2 ? '<span class="tag dir">직거래</span>' : ''}${f & 1 ? '<span class="tag cx">해제</span>' : ''}`;
    table($('#t-trade', el), {
      sort: 'date', limit: 15, csv: `${apt.name}_${a}㎡_매매.csv`,
      rows: trades.map(x => ({ date: x[0], area: x[1], floor: x[2], price: x[3], flag: x[4] })),
      cols: [{ k: 'date', label: '계약일' }, { k: 'area', label: '전용(㎡)', num: 1 }, { k: 'floor', label: '층', num: 1 },
        { k: 'price', label: '거래가', num: 1, fmt: (v, r2) => `${F.eok(v)}${tag(r2.flag)}` },
        { k: 'flag', label: '구분', fmt: v => [v & 1 ? '해제' : '', v & 2 ? '직거래' : '중개', v & 4 ? '신고가' : ''].filter(Boolean).join(' · '), raw: v => [v & 1 ? '해제' : '', v & 2 ? '직거래' : '중개', v & 4 ? '신고가' : ''].filter(Boolean).join(' ') }],
    });
    table($('#t-rent', el), {
      sort: 'date', limit: 10, csv: `${apt.name}_${a}㎡_전월세.csv`,
      rows: rents.map(x => ({ date: x[0], area: x[1], floor: x[2], deposit: x[3], monthly: x[4], renew: x[5] ? '갱신' : '신규' })),
      cols: [{ k: 'date', label: '계약일' }, { k: 'floor', label: '층', num: 1 }, { k: 'deposit', label: '보증금', num: 1, fmt: v => F.eok(v) },
        { k: 'monthly', label: '월세', num: 1, fmt: v => v ? F.man(v) : '전세' }, { k: 'renew', label: '구분' }],
    });
    history.replaceState(null, '', `#/apt/${sgg}/${id}${a === apt.main ? '' : `?a=${a}`}`);
    drawCalc();
  };
  /** 필요 자금: 매매가 − 대출금, 월 상환액(원리금균등), 전세 끼고 살 때(갭) */
  const drawCalc = () => {
    const t = apt.types.find(x => x.a === a);
    const c = S.calc || (S.calc = { loan: 0, rate: 4, years: 30 });
    const loan = Math.max(0, c.loan || 0) * 10000, r = Math.max(0, c.rate || 0) / 1200, n = Math.max(1, c.years || 30) * 12;
    const monthly = !loan ? 0 : r ? loan * r / (1 - Math.pow(1 + r, -n)) : loan / n;
    $('#calc', el).innerHTML = `
      ${kpiCard('최근 시세', F.eok(t.recent), `${a}㎡`)}
      ${kpiCard('필요 현금 (매매)', F.eok(Math.max(0, t.recent - loan)), `시세 − 대출금 ${F.eok(loan)}`)}
      ${kpiCard('월 상환액', loan ? `${F.n(Math.round(monthly))}만원` : '-', loan ? `원리금균등 · 연 ${c.rate}% · ${c.years}년` : '대출금을 넣어 보세요')}
      ${kpiCard('전세 끼고 살 때 필요 현금', t.gap != null ? F.eok(t.gap) : '-', t.gap != null ? `시세 − 전세 ${F.eok(t.jeonse)}` : '최근 전세 거래 없음')}`;
  };

  const sp = apt.spec || {}, geo = apt.geo || {};
  el.innerHTML = `
    <div class="head"><div><h1>${esc(apt.name)}</h1>
      <p class="muted small"><a href="#/gu/${sgg}">${esc(apt.gu)}</a> ${esc(apt.umd)} ${esc(apt.jibun)} · ${apt.by ? `${apt.by}년 준공` : '준공연도 미상'}${sp.hh ? ` · ${F.n(sp.hh)}세대` : ''}</p></div>
      <div class="row"><button class="btn star" id="star"></button><a class="btn" id="cmp">비교에 담기</a><button class="btn" id="share">공유</button></div></div>
    <div class="row" style="margin-bottom:12px"><span class="muted small">면적</span><div class="chips" id="types">${apt.types.map(t =>
      `<button class="chip" data-a="${t.a}">${t.a}㎡ <span class="small">(${t.n}건)</span></button>`).join('')}</div></div>
    <div class="kpis" id="stats"></div>
    <div class="card"><div class="head"><h2>거래 하나하나와 흐름</h2>
      <div class="row"><label class="small"><input type="checkbox" id="rent" checked> 전세 겹쳐 보기</label>
      <div class="chips" id="range">${[[3, '3년'], [5, '5년'], [0, '전체']].map(([v, l]) => `<button class="chip ${v === 0 ? 'on' : ''}" data-v="${v}">${l}</button>`).join('')}</div></div></div>
      <div class="chart lg" id="c-main"></div>
      <p class="note">점 = 거래 1건, 굵은 선 = 최근 3개월 중위값. 두 손가락(또는 휠)으로 확대할 수 있어요. 해제·저가 직거래는 선 계산에서 뺐어요.</p></div>
    <div class="grid two">
      <div class="card"><h2>층별 중위 거래가 (최근 3년)</h2><div class="chart sm" id="c-floor"></div></div>
      <div class="card"><h2>단지 정보</h2><dl class="dl">${[
          ['준공', sp.used ? esc(sp.used) : (apt.by ? `${apt.by}년` : '')],
          ['주소', esc([apt.gu, apt.umd, apt.jibun].filter(Boolean).join(' '))],
          ['세대수 · 동수', sp.hh ? `${F.n(sp.hh)}세대${sp.dongs ? ` · ${sp.dongs}개 동` : ''}${sp.shared ? ' (같은 이름으로 묶인 단지 전체)' : ''}` : ''],
          ['최고 층', sp.top ? `${sp.top}층` : ''],
          ['주차', sp.parking ? `${F.n(sp.parking)}대${sp.hh ? ` (세대당 ${(sp.parking / sp.hh).toFixed(2)}대)` : ''}` : ''],
          ['난방', esc(sp.heat || '')], ['시공', esc(sp.builder || '')],
          ['가까운 역', geo.subway ? `${esc(geo.subway.name)} · ${F.m(geo.subway.dist)}` : ''],
          ['가까운 초등학교', geo.school ? `${esc(geo.school.name)} · ${F.m(geo.school.dist)}` : ''],
        ].filter(([, v]) => v).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>
        ${apt.spec ? '' : '<p class="note">세대수·주차 정보는 공동주택관리정보시스템(K-apt)에 올라온 단지만 나와요(큰 단지 위주).</p>'}
        <div class="row" style="margin-top:12px"><label class="small" for="target">내 목표가(억)</label>
          <input type="number" id="target" step="0.1" min="0" style="width:90px" placeholder="예: 12.5"><button class="btn sm" id="tsave">저장</button></div>
        <p class="note">목표가는 이 기기(브라우저)에만 저장돼요.</p></div>
    </div>
    <div class="card"><h2>필요 자금 계산 <span class="muted small">(참고용 · 선택한 면적의 최근 시세 기준)</span></h2>
      <div class="row"><label class="small">대출금(억) <input type="number" id="loan" step="0.1" min="0" style="width:84px" placeholder="예: 5"></label>
        <label class="small">금리(연 %) <input type="number" id="rate" step="0.1" min="0" style="width:72px"></label>
        <label class="small">기간(년) <input type="number" id="years" step="1" min="1" max="50" style="width:64px"></label></div>
      <div class="kpis" id="calc" style="margin:10px 0 0"></div>
      <p class="note">단순 계산이에요. 취득세·중개보수 같은 부대비용은 빠져 있고, 실제 대출 한도와 금리는 금융회사 심사에 따라 달라요.</p></div>
    <div class="grid two">
      <div class="card"><h2>매매 내역</h2><div id="t-trade"></div></div>
      <div class="card"><h2>전월세 내역</h2><div id="t-rent"></div></div>
    </div>`;

  const star = $('#star', el);
  const drawStar = () => { star.textContent = w() ? '★ 관심 단지' : '☆ 관심 단지에 담기'; star.classList.toggle('on', !!w()); if (w() && w().target) $('#target', el).value = w().target / 10000; };
  const ensure = () => {
    if (!w()) {
      const t = apt.types.find(x => x.a === apt.main);
      S.watch[apt.id] = { sgg, name: apt.name, a: apt.main, added: asof, base: t.recent, target: null };
      if (S.visit) S.visit.snap[apt.id] = { price: t.recent, nh: null };
    }
  };
  star.onclick = () => { if (w()) { delete S.watch[apt.id]; toast('관심 단지에서 뺐어요'); } else { ensure(); toast('관심 단지에 담았어요'); } save(); drawStar(); draw(); };
  $('#tsave', el).onclick = () => { const v = parseFloat($('#target', el).value); ensure(); S.watch[apt.id].target = v > 0 ? Math.round(v * 10000) : null; save(); drawStar(); draw(); toast(v > 0 ? '목표가를 저장했어요' : '목표가를 지웠어요'); };
  $('#cmp', el).href = `#/compare?ids=${sgg}~${id}`;
  $('#share', el).onclick = () => share(`${apt.name} 실거래`);
  const mark = () => $$('#types .chip', el).forEach(b => b.classList.toggle('on', +b.dataset.a === a));
  $('#types', el).onclick = e => { const b = e.target.closest('.chip'); if (!b) return; a = +b.dataset.a; mark(); draw(); };
  $('#rent', el).onchange = e => { showRent = e.target.checked; draw(); };
  $('#range', el).onclick = e => { const b = e.target.closest('.chip'); if (!b) return; range = +b.dataset.v; $$('.chip', b.parentElement).forEach(x => x.classList.toggle('on', x === b)); draw(); };
  const cv = S.calc || (S.calc = { loan: 0, rate: 4, years: 30 });
  $('#loan', el).value = cv.loan || ''; $('#rate', el).value = cv.rate; $('#years', el).value = cv.years;
  for (const k of ['loan', 'rate', 'years']) $(`#${k}`, el).oninput = e => { S.calc[k] = parseFloat(e.target.value) || 0; save(); drawCalc(); };
  mark(); drawStar(); draw();
  void bandLabel;
}
