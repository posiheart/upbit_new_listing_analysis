# Upbit KRW 신규 상장 분석

업비트 공식 공지의 최근 KRW 신규 상장을 찾고, 업비트 거래 시작 UTC 날짜의 Binance USDⓈ-M 무기한 계약 일봉을 D0로 삼아 고정 기간 수익률을 계산하는 재현 가능한 Python 도구입니다.

## 설치와 실행

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e .
listing-analysis --as-of 2025-12-31 --lookback-days 365 \
  --output output/report.html --cache-dir data/cache \
  --symbol-overrides config/symbol_overrides.json --save-json analysis.json
```

`--refresh`는 Upbit 캐시를 무시하며 `--request-timeout`으로 HTTP 제한 시간을 설정합니다. `--as-of`는 UTC 날짜이고, 생략하면 실행 시점의 UTC 날짜입니다. `--output`을 생략하면 `output/report.html`에 생성됩니다. HTML은 CSS, SVG, 검색/필터/정렬용 표준 JavaScript까지 내장한 단일 파일입니다. 일부 API 또는 가격 수집 실패도 경고와 결측 상태로 남기고 보고서는 계속 생성합니다. Upbit 공지 요청에는 현재 웹 API가 요구하는 `os=web`, `category=all`을 포함하고, Binance USDⓈ-M은 기본 호스트의 지역 제한(HTTP 451 등)에 대비해 공식 `fapi1`~`fapi4` 호스트를 순서대로 대체 사용합니다.

런타임 외부 의존성은 HTTP용 **requests**, HTML 파싱용 **beautifulsoup4** 두 개뿐입니다. pandas, numpy, matplotlib, plotly, selenium은 사용하지 않습니다. pytest는 `[project.optional-dependencies].dev`에만 분리되어 있으며 `pip install -e '.[dev]'`로 설치합니다.

## 데이터 정의

* 대상은 기준일 이전 `lookback-days` 이내 게시된 공식 공지 중 제목과 본문을 함께 검사해 KRW **거래지원 추가**가 명시된 자산입니다. BTC/USDT 전용 추가는 제외하고, 복수 자산은 분리합니다.
* 공지 게시일은 상장일이 아닙니다. 본문의 KRW 거래 시작 KST 시각(변경 문구가 있으면 마지막 변경 시각)을 UTC로 변환하며 원문 ID/URL을 보존합니다.
* Binance 계약은 USDT 결제 `PERPETUAL`만 사용합니다. 정확한 일반 심볼을 우선하며 `1000PEPEUSDT` 같은 유일한 숫자 접두 배율 계약도 탐색합니다. 모호하거나 예외인 연결은 `config/symbol_overrides.json`에 ticker, 심볼, 배율, 선택/제외 사유를 기록합니다.
* 배율 계약 가격은 원 토큰 단가로 환산하지 않습니다. 동일 계약의 두 종가 수익률에서는 고정 배율이 소거되며, 계약 심볼과 배율은 상세표에 표시됩니다.

## UTC 일봉과 기간 규칙

업비트 거래 시작 시각이 속한 **UTC 날짜**의 Binance `1d` 확정 종가가 D0입니다. 아직 닫히지 않은 일봉은 쓰지 않습니다. D+7, D+30, D+90, D+180은 달력 월이 아닌 각각 정확히 7, 30, 90, 180일을 더한 UTC 날짜입니다. 목표 날짜와 정확히 일치하는 캔들만 사용하며 인접 일봉으로 대체하지 않습니다. D0가 있어야 `((target / D0) - 1) × 100`을 `Decimal`로 계산합니다. JSON은 가격과 Decimal을 문자열로 보존하고 HTML은 수익률만 표시 자릿수로 반올림합니다.

## 결측 상태

| 상태 | 의미 |
|---|---|
| `AVAILABLE` | 확정 목표 UTC 일봉 종가가 있음 |
| `NOT_MATURED` | 목표일이 기준일 뒤이거나 일봉이 아직 미확정 |
| `NO_BINANCE_CONTRACT` | 대응 USDⓈ-M 무기한 계약 없음 |
| `DELAYED_BINANCE_LISTING` | Binance onboard가 원래 Upbit D0 일봉 뒤임(새 D0로 대체하지 않음) |
| `NO_D0_CLOSE` | 계약은 있으나 D0 종가가 없거나 0 이하 |
| `MISSING_TARGET_CANDLE` | D0는 있지만 정확한 목표일 캔들이 없음 |
| `CONTRACT_DELISTED` | 목표일 전에 종료된 계약의 가격이 없음 |
| `SYMBOL_MAPPING_REQUIRED` | 안전하게 하나의 계약으로 확정 불가 |
| `FETCH_ERROR` | API 오류로 판정 불가 |

## 재현과 테스트

같은 `--as-of`, lookback, override 파일을 사용하고 `data/cache/upbit/` 캐시와 선택적 `--save-json` 결과를 보관하십시오. Binance 가격은 목표 UTC 날짜를 명시적으로 조회합니다. 테스트는 저장된 fixture와 가짜 데이터만 사용하며 네트워크를 호출하지 않습니다.

```bash
pip install -e '.[dev]'
pytest
```

## GitHub Actions와 GitHub Pages

`.github/workflows/pages.yml`은 다음 상황에 테스트를 실행한 뒤 최신 단일 HTML 보고서를 빌드하고 GitHub Pages에 배포합니다.

* `main` 또는 `master` 브랜치에 push할 때
* 매일 00:30 UTC(09:30 KST)에 예약 실행할 때
* Actions 화면에서 **Build and deploy report**를 수동 실행할 때

최초 한 번 저장소의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 선택하십시오. 이후 Actions 실행의 `deploy` 작업에 표시되는 URL 또는 `https://<계정>.github.io/<저장소>/`에서 보고서를 볼 수 있습니다. 공개되는 `index.html`은 외부 CSS/JavaScript 없이 요약, 기간별 수익률 차트, 검색·상태 필터·열 정렬이 가능한 상세표를 모두 포함합니다.

워크플로는 테스트가 성공한 경우에만 배포하며, Upbit 응답 캐시는 실행 사이에 재사용합니다. 수동으로 같은 배포 파일을 확인하려면 다음을 실행하십시오.

```bash
pip install -e .
listing-analysis --output public/index.html --cache-dir data/cache \
  --symbol-overrides config/symbol_overrides.json --request-timeout 30
python -m http.server 8000 --directory public
```

그런 다음 브라우저에서 `http://localhost:8000/`을 여십시오. `--as-of`를 지정하지 않은 Pages 빌드는 실행 시점의 UTC 날짜를 기준일로 사용합니다.
