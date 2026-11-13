// 관심 단지와 내 설정(이 기기 브라우저에만 저장)
import { $, D, S, save, F, cls, esc, table, loadIndex, encState, exportSettings, importSettings, toast } from '../core.js';

export async function render(el) {
  await loadIndex();
  const pv = S.prevVisit;
  const rows = Object.entries(S.watch).map(([id, w]) => {
    const o = D.byId.get(id);
    const before = pv && pv.snap && pv.snap[id] ? pv.snap[id].price : null;
    return o ? { id, name: o.name, gu: o.gu, a: o.a, price: o.price, dd: o.dd, target: w.target, href: o.href,
      toTarget: w.target ? (o.price - w.target) / w.target * 100 : null,
      since: before ? (o.price - before) / before * 100 : null,
      fromAdd: w.base ? (o.price - w.base) / w.base * 100 : null, nh: o.nh, added: w.added }
      : { id, name: `${w.name} (데이터 없음)`, gu: '-', a: w.a, price: null, added: w.added };
  });
  el.innerHTML = `
    <h1>관심 단지</h1><p class="muted small">관심 단지·목표가·저장한 조건은 이 기기(브라우저)에만 저장돼요. 다른 기기로 옮기려면 아래 '내보내기'를 쓰세요.</p>
    ${pv ? `<div class="card since"><b>지난 방문(${esc(pv.asof)} 기준) → 지금(${esc(D.meta.asof)} 기준)</b> 사이의 시세 변화를 '지난 방문 이후' 칸에서 볼 수 있어요.</div>` : ''}
    <div class="card"><div id="t"></div>${rows.length ? '' : '<p class="note">단지 화면에서 "☆ 관심 단지에 담기"를 누르면 여기에 모여요.</p>'}</div>
    <div class="grid two">
      <div class="card"><h2>저장한 조건 검색</h2><div class="chips">${S.presets.screener.map(p => `<a class="chip" href="#/screener?c=${encState(p.st)}">${esc(p.name)}</a>`).join('') || '<span class="muted small">없음</span>'}</div>
        <h2 style="margin-top:14px">저장한 점수 가중치</h2><div class="chips">${S.presets.score.map(p => `<a class="chip" href="#/score?w=${encState({ w: p.w, band: 'std', gu: '' })}">${esc(p.name)}</a>`).join('') || '<span class="muted small">없음</span>'}</div></div>
      <div class="card"><h2>내 설정 옮기기</h2>
        <div class="row"><button class="btn" id="exp">내보내기(파일 저장)</button><label class="btn" for="imp">가져오기</label><input type="file" id="imp" accept="application/json,.json" hidden>
        <button class="btn" id="clr">전부 지우기</button></div>
        <p class="note">내보낸 파일에는 관심 단지·목표가·저장한 조건·가중치만 들어 있어요.</p></div>
    </div>`;
  table($('#t', el), {
    rows, sort: 'name', dir: 1, limit: 50, csv: `관심단지_${D.meta.asof}.csv`, empty: '아직 담은 단지가 없어요',
    cols: [{ k: 'name', label: '단지', fmt: (v, r) => `<b>${esc(v)}</b>${r.nh ? '<span class="tag nh">신고가</span>' : ''}` }, { k: 'gu', label: '구' },
      { k: 'a', label: '면적', num: 1, fmt: v => `${v}㎡` }, { k: 'price', label: '최근 시세', num: 1, fmt: v => F.eok(v) },
      { k: 'since', label: '지난 방문 이후', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'fromAdd', label: '담은 뒤', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'dd', label: '고점 대비', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'target', label: '목표가', num: 1, fmt: v => F.eok(v) },
      { k: 'toTarget', label: '목표가 대비', num: 1, color: 1, fmt: v => F.pct(v) },
      { k: 'id', label: '', fmt: v => `<button class="btn sm rm" data-id="${esc(v)}" aria-label="관심 단지에서 빼기">빼기</button>`, raw: () => '' }],
  });
  el.onclick = e => {
    const rm = e.target.closest('.rm');
    if (rm) { delete S.watch[rm.dataset.id]; save(); render(el); return; }
    if (e.target.id === 'exp') exportSettings();
    if (e.target.id === 'clr' && confirm('관심 단지와 저장한 조건을 모두 지울까요? 되돌릴 수 없어요.')) {
      S.watch = {}; S.presets = { screener: [], score: [] }; S.weights = null; save(); toast('지웠어요'); render(el);
    }
  };
  $('#imp', el).onchange = async e => {
    const f = e.target.files[0]; if (!f) return;
    try { importSettings(await f.text()); toast('가져왔어요'); render(el); } catch (err) { toast(err.message || '파일을 읽지 못했어요'); }
  };
  void cls;
}
