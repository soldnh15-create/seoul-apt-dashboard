# 강남박공 서울 아파트 실거래 대시보드

서울 25개 구 아파트 실거래(매매·전월세)를 **매일 자동으로 받아서 분석하고, 누구나 무료로 보는 웹 대시보드**로 내보내는 프로그램입니다.

- 운영비 0원: GitHub 공개 저장소 + GitHub Actions(자동 실행) + GitHub Pages(사이트)만 씁니다.
- 공식 무료 API만 씁니다(국토교통부 실거래가 — 공공데이터포털). 네이버부동산·KB·호갱노노 같은 곳은 긁어 오지 않습니다.
- 인증키는 코드에 없습니다. GitHub Secrets(자동 실행)나 내 PC 환경변수(직접 실행)에만 둡니다.
- 지역 확장: `config/regions.yaml` 한 파일만 고치면 수도권·전국으로 늘어납니다.

> 이 사이트는 투자 권유가 아니며, 데이터는 국토교통부 등 공공데이터를 가공한 것입니다.

---

## 1. 무엇을 볼 수 있나

| 화면 | 내용 |
|---|---|
| 홈 | 핵심 지표 카드, 거래량·평단가 추이, 구별 순위(정렬), 신고가 목록, 주간 거래량, 연식별 평단가 |
| 구별 | 구 추이, 면적 구간·기간 필터, 동별 비교, 단지 목록 |
| 단지 상세 | 거래 하나하나(점) + 3개월 중위선, 매매·전세 겹쳐 보기, 전고점 대비 낙폭, 전세가율·갭, 층별 시세, 단지 스펙, 역·학교 거리, 목표가 |
| 지도 | 단지·구 마커. 색 기준 선택(평단가·낙폭·전세가율·거래량) |
| 조건 검색 | 조건을 쌓아 단지 거르기. 조건이 주소에 담겨 그대로 공유됨 |
| 내 기준 점수 | 항목별 중요도 슬라이더로 단지 순위 매기기 |
| 단지 비교 | 최대 4곳 평단가 흐름 겹쳐 보기 |
| 관심 단지 | 관심 단지·목표가·"지난 방문 이후 변화"·설정 내보내기/가져오기 (이 기기 브라우저에만 저장) |
| 주간 리포트 | 계산된 숫자로 만든 요약(+ 선택: 숫자 검증을 통과한 AI 글) |

그 밖에: 단지명 검색(초성·오타 허용), 모든 표 CSV 내려받기, 다크모드, 홈 화면에 추가(PWA), 텔레그램 알림(선택).

## 2. 따라 하기 — 내 사이트 띄우기 (개발 지식 없이)

> 스크린샷 자리: `docs/img/01-fork.png` 등. 그림은 나중에 채웁니다.

1. **GitHub 가입·로그인** 후 이 저장소 오른쪽 위 **Fork** 를 누릅니다. *(스크린샷 자리 1)*
2. **공공데이터포털(data.go.kr) 가입** 후 아래 2개를 "활용신청" 합니다(무료, 보통 바로 승인).
   - [국토교통부_아파트 매매 실거래가 상세 자료](https://www.data.go.kr/data/15126468/openapi.do)
   - [국토교통부_아파트 전월세 실거래가 자료](https://www.data.go.kr/data/15126474/openapi.do)
   - (선택) 단지 정보: [공동주택 단지 목록제공 서비스](https://www.data.go.kr/data/15057332/openapi.do), [공동주택 기본 정보제공 서비스](https://www.data.go.kr/data/15058453/openapi.do)
3. 포털 **마이페이지 → 인증키** 에서 "일반 인증키"를 복사합니다(Encoding·Decoding 아무거나 됩니다). *(스크린샷 자리 2)*
4. 내 저장소 **Settings → Secrets and variables → Actions → New repository secret** *(스크린샷 자리 3)*
   - Name: `DATA_GO_KR_KEY` / Secret: 복사한 키 → Add secret
5. **Settings → Pages → Source 를 "GitHub Actions"** 로 바꿉니다. *(스크린샷 자리 4)*
6. **Actions 탭 → "매일 업데이트와 배포" → Run workflow** 를 누릅니다. *(스크린샷 자리 5)*
   - 처음에는 최근 달부터 과거 10년 치를 채웁니다. 하루 호출 한도(API마다 10,000건) 안에서 받고, 남은 것은 **다음 날 자동으로 이어받습니다.** 서울은 보통 하루면 끝납니다.
7. 끝나면 `https://<내 아이디>.github.io/<저장소 이름>/` 에서 사이트가 열립니다. 그 뒤로는 매일 새벽 4시 30분(한국 시간)에 알아서 갱신됩니다.

### 내 지역으로 바꾸기
`config/regions.yaml` 에서 원하는 시도를 `enabled: true` 로 바꾸고 시군구(법정동코드 앞 5자리)를 적습니다. 코드는 [행정표준코드관리시스템](https://www.code.go.kr)에서 찾습니다.

### 내 이름으로 바꾸기
`config/site.yaml` 의 `brand`·`title`·`home_url`·`home_label` 을 고칩니다. `python scripts/make_images.py` 를 실행하면 공유용 이미지도 새 이름으로 만들어집니다.

### 선택 기능 켜기 (Secrets 를 넣으면 켜지고, 없으면 자동으로 꺼짐)

| Secret 이름 | 켜지는 기능 | 키 받는 곳 |
|---|---|---|
| `KAKAO_REST_KEY` | 단지 좌표, 가까운 역·초등학교 거리, 단지 단위 지도 | Kakao Developers (REST API 키) |
| `ECOS_KEY` | 기준금리·주담대 금리 겹쳐 보기 | 한국은행 ECOS Open API |
| `RONE_KEY` | 부동산원 주간지수(통계표 ID를 `config/settings.yaml` 에 적어야 함) | 한국부동산원 R-ONE Open API |
| `GEMINI_API_KEY` | AI 주간 요약(주 1회) | Google AI Studio |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | 신고가·저가 직거래 알림 | 텔레그램 BotFather |

사이트 주소를 알림에 넣으려면 **Variables** 에 `SITE_URL` 을 추가합니다.

## 3. 내 PC 에서 직접 돌리기

```bash
pip install -r requirements.txt
python -m pytest -q                      # 테스트
python -m pipeline sample                # 인증키 없이 가상 샘플로 전체 흐름 (site/data 생성)
python -m http.server 8790 --directory site   # http://localhost:8790 에서 보기
```

실제 데이터(인증키 필요):

**인증키 넣는 법 (Windows)** — 키는 본인만 보이는 곳에 직접 넣습니다. 코드·파일·채팅에 붙여 넣지 마세요.
1. 시작 메뉴에서 "환경 변수" 검색 → **계정의 환경 변수 편집**
2. **새로 만들기** → 변수 이름 `DATA_GO_KR_KEY`, 변수 값에 인증키 → 확인
3. 열려 있던 터미널·프로그램을 닫았다가 다시 엽니다.

```bash
python -m pipeline collect --mode daily        # 최근 3개월
python -m pipeline collect --mode backfill     # 과거 10년(이어받기)
python -m pipeline build                       # 지표 계산 + 사이트 데이터
python -m pipeline validate                    # 배포 전 검증
python -m pipeline csv --sgg 11680 --from 202601 --to 202610     # 지역·기간 → 엑셀용 CSV (out/ 폴더)
python -m pipeline csv --sgg 11680 11650 --from 202601 --to 202610 --kind rent --apt 래미안
```

## 4. 구조

```text
config/        regions.yaml(지역) · settings.yaml(기간·한도·지표 기준) · site.yaml(브랜드) · complex_overrides.yaml(단지 수동 보정)
pipeline/      api(호출·재시도·오류 감지) → parse(정제) → store(저장) → collect(백필·일일)
               → complexes(단지 식별) → metrics(지표) → export(사이트 JSON) → validate(검증)
               extras(선택 기능) · report(주간 요약) · exportcsv(표 저장) · mock_api(가상 샘플)
data/raw/      원천 데이터: {trade|rent}/{시군구}/{연도}.csv.gz  (저장소에 커밋)
data/state/    체크포인트·실행 기록·검증 기준
site/          정적 사이트(HTML·CSS·JS, 빌드 도구 없음). site/data/ 는 실행 때 만들어짐
tests/         공식 응답 형식 픽스처 + 단위 테스트
.github/workflows/   daily.yml(매일 수집·검증·배포) · ci.yml(테스트)
```

### 안전장치
- **이어받기**: 받은 달을 `data/state/checkpoint.json` 에 적어 두고, 한도에 걸리면 멈췄다가 다음 실행에서 이어받습니다.
- **매일 최근 3개월 재수집**: 신고 기한(계약 후 30일)·정정·해제를 반영합니다. 같은 달을 다시 받으면 그 달만 통째로 바꾸므로 여러 번 돌려도 결과가 같습니다.
- **오류 감지**: HTTP 200 이어도 본문 속 오류 코드(인증키·한도·서버 오류)를 잡아냅니다. 일시 오류는 1.5 → 3 → 6 → 12초 간격으로 다시 시도합니다.
- **이상한 0건 방지**: 거래가 많던 달이 갑자기 0건으로 오면 덮어쓰지 않습니다.
- **배포 전 검증**: 행 수 급감, 가격 이상치, 열 누락, 수집 중단(최신 거래일이 오래됨), 가상 샘플 섞임을 감지하면 **배포하지 않고 실패**합니다.
- **단지 매칭**: 매매의 단지 일련번호를 기준으로 하고, 전월세는 동·지번·단지명으로 붙입니다. 못 붙인 것은 `data/state/unmatched_rent.csv` 에 남고 `config/complex_overrides.yaml` 로 손으로 보정할 수 있습니다.

### 저장소가 커지면
원천 데이터는 시군구·연도별로 나눠 압축하므로 파일 하나가 50MB 를 넘지 않습니다. 저장소 전체가 1GB 에 가까워지면(전국 확장 시) 오래된 연도 파일을 GitHub Releases 자산으로 옮기고, 실행할 때 내려받도록 바꾸는 방안을 씁니다(아직 미구현 — `docs/설계안.md` 참고).

## 5. 지표 기준 (요약)

- **평단가**: 거래가 ÷ 전용면적 × 3.3058, 중위값. **최근 시세**: 최근 6개월 거래의 중위값(없으면 마지막 거래).
- **신고가**: 같은 단지·같은 면적(㎡ 정수)에서 이전 최고가를 넘은 거래(이전 거래 3건 이상일 때).
- **전고점 대비**: (최근 시세 − 역대 최고가) ÷ 역대 최고가. **반등률**: 고점 이후 최저가 대비.
- **전세가율·갭**: 같은 단지·면적의 최근 6개월 전세 보증금 중위값 ÷ 최근 시세, 그 차이.
- **저가 직거래**: 직거래이면서 직전 6개월 중개거래 중위가보다 20% 이상 낮은 거래 → 시세 계산에서 제외.
- 해제된 거래는 모든 가격 계산에서 빼고 "해제 비율"로만 셉니다. 기준값은 모두 `config/settings.yaml` 에서 바꿉니다.

## 6. 자료 출처와 이용 조건

- 국토교통부 실거래가 공개시스템 자료(공공데이터포털 제공, 이용허락범위 제한 없음). 출처를 표시합니다.
- 지도: © OpenStreetMap 기여자. 차트: Apache ECharts. 지도 도구: Leaflet.
