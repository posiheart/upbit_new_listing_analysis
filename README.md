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

`--refresh`는 Upbit 캐시보다 네트워크 갱신을 우선하되, 일시적인 API/WAF 오류가 발생하면 마지막 정상 캐시를 사용합니다. 공지 목록의 마지막 정상 응답은 엔드포인트별 캐시와 별도로 보존하므로 Upbit가 비공개 API 경로나 파라미터를 바꾸거나 CI IP를 HTTP 403으로 차단해도 기존 분석 결과가 빈 보고서로 바뀌지 않습니다. 따라서 Actions 캐시인 `data/cache`를 삭제하지 않는 것이 중요합니다. Binance의 정상 응답(거래소 정보와 일봉)도 같은 디렉터리에 저장되어 다음 실행에서 재사용됩니다. `--request-timeout`으로 HTTP 제한 시간을 설정합니다. `--as-of`는 UTC 날짜이고, 생략하면 실행 시점의 UTC 날짜입니다. `--output`을 생략하면 `output/report.html`에 생성됩니다. HTML은 CSS, SVG, 검색/필터/정렬용 표준 JavaScript까지 내장한 단일 파일입니다. 일부 API 또는 가격 수집 실패도 경고와 결측 상태로 남기고 보고서는 계속 생성합니다. Upbit의 비공개 웹 공지 API 변경에 대비해 `notices`에는 `thread_name=general`, `announcements`에는 `category=all`이라는 각 경로에 맞는 파라미터를 사용합니다. Binance USDⓈ-M은 지역 제한(HTTP 451), WAF의 HTML 응답 등에 대비해 공식 기본 `fapi`와 `fapi1`~`fapi4` 호스트를 순서대로 대체 사용합니다. HTTP 451은 주소가 틀렸다는 뜻이 아니라 Binance가 실행 위치의 접속을 제한한 응답이므로, 이 경우 접속 가능한 네트워크에서 한 번 실행해 생성한 `data/cache`를 보존해야 합니다.

GitHub 호스팅 러너의 공용 IP가 거래소에서 차단되는 저장소는 접근 가능한 지역에 HTTPS 역방향 프록시를 두고 `UPBIT_API_BASE_URL`(예: `https://proxy.example/upbit/api/v1`)과 `BINANCE_API_BASE_URLS`(쉼표로 구분한 Binance 루트 URL)를 설정할 수 있습니다. 선택적으로 `API_PROXY_TOKEN`을 설정하면 모든 프록시 요청에 `X-Proxy-Token` 헤더로 전달됩니다. 토큰과 URL은 명령줄 대신 환경 변수 또는 GitHub **Actions secrets**에 저장해 로그에 노출하지 마십시오. 프록시는 요청 경로와 쿼리를 그대로 원본으로 전달해야 합니다. 즉 Upbit 루트 뒤의 `/notices`, `/announcements`와 Binance 루트 뒤의 `/fapi/v1/exchangeInfo`, `/fapi/v1/klines`를 지원해야 합니다. 공개 프록시나 User-Agent 위장은 안정적이거나 안전한 IP 제한 우회책이 아니므로 사용하지 않습니다.

저장소에는 인증과 경로 allowlist를 포함한 최소 Cloudflare Worker 예제가 `infra/exchange-proxy/`에 있습니다. 거래소 이용약관과 해당 지역의 법률상 접근이 허용되는 위치에서만 다음처럼 배포하십시오.

```bash
cd infra/exchange-proxy
npx wrangler secret put PROXY_TOKEN
npx wrangler deploy
```

배포 URL이 `https://listing-proxy.example.workers.dev`라면 Actions secret을 다음과 같이 설정합니다.

* `UPBIT_API_BASE_URL=https://listing-proxy.example.workers.dev/upbit/api/v1`
* `BINANCE_API_BASE_URLS=https://listing-proxy.example.workers.dev/binance`
* `API_PROXY_TOKEN`: `wrangler secret put`에 입력한 값

Worker 배포 위치에서도 거래소가 접속을 허용하지 않는다면, 허용된 네트워크에 self-hosted runner를 설치하고 repository variable `COLLECTION_RUNNER`를 그 runner label(예: `self-hosted`)로 설정하십시오. Pages 파일 자체는 정적이며 데이터 수집은 배포 작업이 실행되는 runner에서만 수행됩니다.

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

워크플로는 정상 응답 캐시를 실행 사이에 재사용합니다. GitHub Pages는 정적 호스팅이므로 브라우저에서 거래소 API를 직접 호출하지 않고 Actions가 만든 HTML만 제공합니다. `--fail-on-collection-error`는 수집 오류가 발생하면 출력 파일을 쓰기 **전에** 종료하므로 빈 경고 페이지를 만들지 않습니다. 이 명령 자체가 실패하더라도 Pages 배포 작업은 저장소에 포함된 마지막 정상 보고서인 `output/report.html`을 `public/index.html`로 복사해 배포합니다. 따라서 캐시가 없는 최초 실행에서 GitHub 호스팅 러너의 IP가 Upbit와 Binance 양쪽에서 거부되어도 워크플로 전체가 실패하거나 기존 보고서가 빈 페이지로 교체되지 않습니다. 이 경우 Actions 로그에는 fallback 사용 경고가 표시되며, 최신 데이터로 갱신하려면 아래 프록시 또는 self-hosted runner 설정이 필요합니다.

GitHub 호스팅 IP가 차단되는 경우 저장소 **Settings → Secrets and variables → Actions**에 다음 repository secret을 추가하십시오.

| Secret | 필수 여부 | 값 |
|---|---|---|
| `UPBIT_API_BASE_URL` | 프록시 사용 시 | 프록시의 Upbit `/api/v1` 루트 |
| `BINANCE_API_BASE_URLS` | 프록시 사용 시 | 프록시의 Binance 루트(여러 개는 쉼표 구분) |
| `API_PROXY_TOKEN` | 선택 | 프록시가 검사할 비밀 토큰 |

Secrets를 비워 두면 로컬 실행과 마찬가지로 공식 호스트를 사용합니다. GitHub 러너의 지역/IP 제한 자체는 애플리케이션에서 우회할 수 없으므로, 제한이 계속되면 프록시 또는 해당 지역의 self-hosted runner가 필요합니다. 수동으로 같은 배포 파일을 확인하려면 다음을 실행하십시오.

```bash
pip install -e .
listing-analysis --output public/index.html --cache-dir data/cache \
  --symbol-overrides config/symbol_overrides.json --request-timeout 30
python -m http.server 8000 --directory public
```

그런 다음 브라우저에서 `http://localhost:8000/`을 여십시오. `--as-of`를 지정하지 않은 Pages 빌드는 실행 시점의 UTC 날짜를 기준일로 사용합니다.
