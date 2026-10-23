# 테스트 결과

검증일: 2026-09-29 / 환경: Windows, Python 3.12, 로컬 127.0.0.1:8765

## 자동 테스트

명령: `.venv\Scripts\python.exe -m pytest -q`

**13 passed**. Starlette TestClient가 HTTPX 대신 HTTPX2를 권장하는 deprecation warning 1건.
현재 고정 의존성에서 실패는 없으며 향후 업그레이드 시 검토한다.

| 검증 영역 | 결과 |
|---|---|
| 4:5 / 1:1 / 9:16 크기, 1 / 2 / 10장 생성 | 통과 |
| ZIP 파일 개수, 캡션 출처 포함 | 통과 |
| 편집 결과 DB 영속 저장 | 통과 |
| 11장 거절, AI·검색 키 누락 오류 | 통과 |
| 자산 ID 경로 조작 거절 | 통과 |
| 사설 네트워크·file URL 거절 | 통과 |
| 다른 Origin의 수정 요청 차단 | 통과 |
| 이미지 업로드·카드 적용·출처 | 통과 |
| 예약 조건·검토·취소·편집 잠금 | 통과 |
| 하루 10개 초과 예약 거절 | 통과 |
| Meta 캐러셀 성공 처리 (모의 API) | 통과 |
| 최종 게시 응답 불명확 → needs_check (모의 API) | 통과 |
| 일일 생성·같은 날 재실행 방지 (모의 검색/AI) | 통과 |

## 실행·화면 확인

- Python 모듈 컴파일, JavaScript 구문 검사 통과.
- 실제 Uvicorn 서버 실행 및 한국어 제작 화면 표시 확인.
- 브라우저에서 예시 원고 입력 → 5장 생성 → 표지 제목 편집 → 재렌더링 확인.
- 생성 결과와 수정 제목이 미리보기에 표시됨을 확인.
- Openverse 라이브 검색: `computer` 검색 12개 결과, 첫 결과 JPEG 다운로드 성공.
- Wikimedia 403 응답 때문에 웹 이미지 공급자를 Openverse로 변경.
- 자체 생성 2초 MP4 업로드 → 현재 장면 캡처 → 선택 이미지 표시 확인.
- 브라우저 다운로드 완료: Downloads/issue-0c3fa795.zip.
- 발표 10장 모두 1280×720 화면에서 가로 넘침·세로 초과 없음.
- 실제 화면 증빙: assets/studio-preview.png, assets/presentation-cover.png.

## 아직 수행하지 않은 검증

OpenAI 실키 문안·이미지 생성, Naver 실키 검색, Meta 실계정 게시,
공개 HTTPS 미디어 호스팅, 24시간 운영, 발표 장소 PC 실행.
외부 인증이 없으므로 테스트 성공을 외부 서비스 운영 성공으로 해석하지 않는다.

## 추가 연결 검증 — YouTube (2026-09-29)

- 사용자가 연결을 요청하여 기존 YouTube Data API 전용 키를 로컬 `.env`에 저장.
- 키 값은 Git·문서·로그에 기록하지 않음. `.env` Git 제외 확인.
- 서버 재시작 후 YouTube 연결 설정 활성 상태 확인.
- 사용자 입력 영상의 제목·설명 조회: HTTP 200, 채널 JTBC News, 본문 827자.
- 한국 지역 인기 영상 조회: HTTP 200, 30건, 경고 0건.
- YouTube 연결 범위는 공개 영상 메타데이터이며 자막·영상 전체 분석이 아님.

## 로컬 연결 거부 복구 (2026-09-29)

- 오류 당시 8765 포트에 실행 중인 서버가 없었음. 앱 모듈 import는 정상.
- start.bat을 독립 백그라운드 실행으로 변경. 실제 리스너 PID와 로그 파일 저장.
- 중복 실행 시 기존 서버 재사용, stop.bat으로 종료 후 재시작 확인.
- 재시작 후 /api/status 응답과 기존 YouTube 설정 유지 확인.
- Windows 재부팅 후 자동 실행은 설정하지 않음. start.bat 재실행 필요.

## 운영 전 확인할 한계

로컬 원문 배치는 긴 원고를 요약하지 않아 생략될 수 있다. 캡션/원문을 함께 검토한다.
외부 기사 추출은 사이트 구조에 영향을 받는다. 원문 대조와 이미지 이용 조건 검토가 필요하다.
현재 실시간 게시 전 비용 상한·토큰 갱신·실패 알림은 구현되지 않았다.

## 2026-10-01 KIE AI 카드 이미지 추가

명령: `python -m pytest tests -q` (작업 환경 Linux VM, Python 3.10 / 고정 의존성)

**49 passed** (기존 39 + KIE 10). `node --check static/app.js` 통과.
신규 `tests/test_kie.py` 8건(모의 KIE API), `tests/test_studio.py` 2건(KIE 선택 생성, 키 누락 시 사전 중단).
실제 KIE 이미지 생성은 실행하지 않았다(유료). 키 인증 기록: `data/media-connection-status.json`.


## 2026-10-16 실행 서버 소재 기준 수정

- 12시간/10만 회 경계, 누락·비공개·조회 실패, 검색 필터, 유료 제작 전 만료, 예약 중 만료, 실제 게시 직전 조회 및 Meta 처리 중 만료를 검사.
- 크롭 사진 묶음 검사의 누락/중복 응답 차단, 실제 크롭만 검사, 한 번의 요청, 빈 후보 무호출 확인.
- 관련 7개 테스트 파일: 81 passed. 테스트는 외부 유료 생성·실제 게시를 실행하지 않음.
- 서버 재시작 후 `/api/status.source_policy`에서 `youtube-12h-100k-v1`, `max_age_hours=12`, `min_views=100000`, 두 검사 플래그 true 확인.
- 기존 일일 소재 9회/생성 7회 카운터를 초기화하지 않고 자동 제작·게시 재개. 게시 간격 5분 유지.
- 실제 YouTube API 후보 확인 기록: `data/candidate-check-12h-20261016.json`; 과거 게시 원본 점검: `data/source-audit-20261016.json`. 조회수는 해당 확인 시각의 값이며 과거 게시 시점 수치로 추정하지 않음.
- 18시간 이상 지난 기존 예약 1건을 취소하고, 원본 시각·조회수 재조회에서 부적격인 점 확인. 이미 게시한 글은 수정/재게시하지 않음.


## 2026-10-16 14:23 KST 운영 지침 서버 적용

- app/operations.py: 모든 publish 진입점의 실제 게시 간격, 완료/결과 미확인 중복 전송 차단, 자동제작물 전 카드 캡처 자산 및 최종 JPG 읽기 검증.
- app/delivery.py: 기존 자동 예약 이미지 검사를 분리해 자동/수동 전송 직전에도 동일한 외부 이미지 바이트 검증을 적용.
- API /api/status.operations: 실행 중 정책 버전/로드 시각/실제 한도와 자동제작분 전달 실적, 반복 보류 사유, 오늘 전체 게시와 원격 조회 확인 수를 분리.
- 프런트의 과거 소재 3배/최대 3차 문구를 실제 하루 소재 150회·영상당 2회·생성 20회 기준으로 정정. 새 제한 추가나 카운터 초기화 없음.
- 관련 테스트 118 passed; node --check 통과; 스킬 quick_validate UTF-8 실행 통과.
- 실행 서버 재시작 후 publication-guards-20261016-v1 확인, cadence/provider/예약/재시도 시각/소재 27회·생성 7회 보존 확인.
- 최종 JPG 3장 외부 응답과 로컬 파일 일치를 읽기 전용으로 재확인.
- 현재 자동제작분 게시/예약 0건 및 원문/캡처 보류는 해결 완료로 표시하지 않음. 서버 operations.status=needs_attention으로 노출하며, 기존 허용된 자동 운영은 유지.
- 확인 기록: data/operations-deployment-20261016.json. 실제 게시 성공은 publication_preflight가 아닌 publication_verification으로 별도 판정.


## 2026-10-19 source/capture recovery

- Root cause: candidate metadata did not request duration; live/long uploads were admitted, then yt-dlp silently skipped them before metadata JSON existed. Added explicit preflight duration/live classification and accurate metadata errors. Upload age/view-count criteria remain 12 hours/100,000.
- Retrieval: normalize whitespace/Unicode in grounded queries; if all proposed terms are invalid, use exact headline tokens without inventing names. Article and claim checks still run.
- Frames: high-detail planning, overlay boundary margin, one review of up to 15 actual crops before selecting five. Lower-ranked usable crops are no longer discarded before verification. Persist original frames, crop coordinates/reasons and crop verdicts under data/source-audits.
- Reuse successful transcript/evidence results for six hours; source eligibility is always refreshed. No quota/counter resets or failed AI-call retries added.
- Validation: 82 relevant tests passed (autopilot/frame/source/operations and metadata-limit regression tests); runtime reports high-detail-crops-20261019-v2.
- Production/publication outcome is recorded separately in data/repair-20261019; passing tests does not assert a live publication.

### Production follow-up: actual-crop-first-20261019-v4

High-detail planning alone still predicted every frame unusable. Inspection of actual saved frames disproved that blanket rejection. Added one real inner-scene crop when the plan rejects a frame, then separate batches for overlay cleanliness and original-vs-crop integrity. The final fallback top boundary excludes broadcast date labels as well as corner logos. Maximum original candidates remains 15, returned assets at most five, and final JPG inspection remains mandatory.

The user-requested repair continued saved transcripts/articles/captures rather than recollecting sources or resetting attempts. Each continuation version and failure was recorded in the journal; original source_attempts and generation_attempts were retained. Runtime policy reports actual-crop-first-20261019-v4. A human final-image check also removed an unrelated Belgium frame from the France story, a clipped studio presenter and an unrelated weapons image from the Ukraine story. Claim attribution and topic-specific CTAs were rechecked after edits. This review found model limitations; automated pass does not guarantee a perfect frame.

85 relevant tests passed before the final boundary adjustment; the 17 affected frame/integrity tests passed again after it. Live-publication proof is stored separately in data/repair-20261019/publication-results.json once all scheduled items finish.


### 2026-10-19 final runtime and live publication verification

- Final related regression suite: 86 passed (autopilot, frames, source policy, operations, metadata limits and crop integrity).
- Server reloaded at 2026-10-19T14:10:13.611070+09:00; actual-crop-first-20261019-v4, 12-hour/100,000-view criteria, 5-minute spacing and white/yellow headlines confirmed.
- Historical holds remain intact; current summary is unresolved 0, unsupported sources 7, recovered and live-verified 3. Counters preserved at source attempts 13 / generation attempts 3.
- Live verified: 57f857f73e904b18906571e104d81177; 2026-10-19T13:58:01.081766+09:00; 5 image(s); https://www.instagram.com/p/Deqc_EyjyzH/
- Live verified: 1bd26e976f8d4a3cad7028818c144ad9; 2026-10-19T14:03:50.490911+09:00; 1 image(s); https://www.instagram.com/p/DeqdplEj21D/
- Live verified: a7214472ec86429c8baa59c4a9e7487d; 2026-10-19T14:09:30.364143+09:00; 2 image(s); https://www.instagram.com/p/DeqeS7oj80I/
- Actual publication intervals: 349.409 seconds, 339.873 seconds. No duplicate publications; final proof: data/repair-20261019/publication-results.json.


### 2026-10-20 public media recovery and live publication

- Cause: the managed tunnel received a termination signal at 2026-10-19 18:14 KST. The existing watchdog restarted only the editor, leaving a stale Quick Tunnel address. The original media origin and tunnel processes were absent.
- Recovered the image-only origin and a new tunnel, verified actual JPG content type and SHA-256 against local files, and confirmed public management/configuration routes return 404.
- Existing watchdog now checks public image bytes every five minutes and repairs only when automatic production/publication is idle and no reservation or retry is imminent. Intentional media stop is respected. Duplicate repairs are mutex-protected. Watchdog is running.
- 24 focused tests passed (recovery, cadence, consent, live-publication verification); all three changed PowerShell scripts parsed. Healthy startup was exercised without restarting the active server or tunnel.
- Daily counters, 12-hour/100,000-view criteria and minimum five-minute posting gap preserved. No quota resets or provider changes.
- Produced and live-verified two 5-image carousels. Both were inspected on Instagram. First CTA was refined; second corrected an unsupported execution-location implication. Both content revisions passed fresh quality, factual and final-image review.
- Live verified: cf81de364a3241f58244bafd05482a6b; 2026-10-20T15:02:05.566078+09:00; https://www.instagram.com/p/DetJG9Qmeik/
- Live verified: 7b688ea3e9814a92a381caf260cf3059; 2026-10-20T15:08:43.433200+09:00; https://www.instagram.com/p/DetJ3pomXzx/
- Actual completion gap: 397.867 seconds. Current round has five source holds (two file-size limits, two bounded copy failures, one insufficient independent-source check); these were not represented as publications. Proof: data/recovery-20261020/verified-results.json.

### 2026-10-23 media DNS and watchdog recovery

- Confirmed failure: saved Cloudflare Quick Tunnel hostname no longer resolved; the image origin and tunnel were absent. Instagram account and YouTube read requests succeeded. The older generic network message alone did not identify its historical failing request and is not evidence of insufficient credit.
- Root cause preventing recovery: PowerShell helper output was piped into a file, so inherited output handles in long-running server descendants kept the watchdog waiting. Added a managed helper that waits for the helper process itself, with separate stdout/stderr logs, a bounded wait and captured process handle for Windows PowerShell 5.1 exit-code reliability.
- Applied the helper to watchdog server/media startup and media recovery editor stop/start. Restarted the existing managed watchdog and server. New server loaded at 10:13:16 KST; watchdog at 10:13:38, with actual public-image health confirmed. Existing counters, provider, source criteria and cadence were preserved.
- Provider network failures now identify the external service, hostname and exception class without exposing credentials, query strings or raw exception contents. A new run clears stale blocker codes.
- Validation: 39 focused tests passed (DNS diagnostics, autopilot and public-media recovery), including a Windows regression that confirms a helper returns while its child stays running. Public JPG bytes matched the local file; account delivery checks passed.
- Resumed automatic production once: 13 age/view-qualified candidates, 11 excluded for duration over the existing 20-minute collector limit, one excluded as live, one produced. No holds in this round and no excluded-source eligibility bypass.
- Polished the produced two-card JOMO carousel with a targeted curiosity hook and a single save CTA; removed unsupported health-benefit inference. Fresh quality, factual, source and final-overlay checks passed; both final JPGs inspected visually. Caption length: 462 characters.
- Published and remotely verified 08c1fe5579e34b48928400970f384199 at 2026-10-23T10:21:12.166054+09:00: https://www.instagram.com/p/De0XWfCgZlb/ . Meta confirmed CAROUSEL_ALBUM with two images; the Instagram page, caption and both cards were also inspected in the browser.
- Source rechecked immediately before publication: 166,748 views, upload age 3.614 hours. The previous completed publication was 2026-10-20T16:36:28+09:00, safely outside the minimum five-minute gap. No other active reservation remained. Automatic source checking remains enabled with the next check at 10:45 KST.
- Proof: data/recovery-20261023/deployment.json, card-final-checks.json and verified-results.json. Temporary-tunnel recovery is not a guarantee of uninterrupted service while the computer is asleep/offline.

### 2026-10-23 cumulative GitHub snapshot validation

- Ran the complete suite against a temporary `ISSUE_DATA_DIR`, with dotenv loading disabled, credential environment variables removed and external socket connections blocked. Final result: **253 passed** in 34.02 seconds. No paid generation, live posting or runtime setting changes were performed for this validation.
- The first run found one stale test expecting the former 75-point quality threshold. Updated its fixture to exercise the approved 65-point boundary, retain rejection below the boundary and preserve the independent factual/image/critical-error gates. Production quality thresholds were not changed in this commit preparation.
- `node --check` passed for `static/app.js`, `public-demo/demo.js` and `public-demo/source.js`. All eight PowerShell scripts parsed without syntax errors; the suite also exercises managed-helper process exit behavior on Windows.
- One upstream Starlette warning remains about its httpx-based TestClient compatibility. It does not fail the tests; dependency migration was not included in this snapshot.
- Updated README to describe implemented source capture, grounded hooks/CTA, white/yellow titles, automatic publication guards, live verification and media recovery. Local operating settings and new-install defaults are distinguished; team login and remote shared use are not described as implemented.
- Checked Git candidates for known credential formats, exact matches to locally configured secret values and private runtime paths. No credentials, `.env`, runtime DB, generated media or logs were included. Pretendard font files include their SIL Open Font License.
- Local machine-readable test proof: `data/git-publish-20261023/pytest.xml` (excluded from Git). GitHub commit/push verification is recorded separately from deployment and publication verification.
