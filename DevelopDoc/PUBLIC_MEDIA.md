# 공개 카드 이미지 서버

2026-09-30 Cloudflare Quick Tunnel을 통해 카드 이미지용 공개 HTTPS 연결을 구성했다.

- 관리 화면: `http://127.0.0.1:8765` (로컬 전용)
- 이미지 원본 서버: `http://127.0.0.1:8766`
- 공개 URL: 로컬 `data/public-media-url.txt` 및 `.env`의 `PUBLIC_MEDIA_BASE_URL`
- 공개 경로: `/{32자리 콘텐츠 ID}/{01~10}.jpg` 또는 `.png`만 제공
- 목록, 원고 JSON, API, 설정, 비밀값은 공개하지 않는다. 이미지 URL을 아는 사람은 이미지를 볼 수 있다.

## 실행과 중지

`start-public-media.bat`으로 실행한다. 실행 중이면 기존 주소를 보여준다. 새 터널 주소는 `.env`에 자동 반영하고 제작 서버를 재시작한다.

`stop-public-media.bat`으로 이미지 공개를 중지한다. 제작 서버는 계속 실행된다. `stop.bat`은 제작 서버만 중지하므로 이미지 공개를 중지하려면 별도 중지 파일을 사용해야 한다.

`data/tools/cloudflared.exe`는 공식 cloudflare/cloudflared GitHub 릴리스 2026.9.3에서 다운로드하여 릴리스 SHA-256으로 검증했다. 실행 파일은 Git에 포함되지 않는다.

## 운영 범위

Quick Tunnel은 임시 시연용이며 서버 가동 보장이 없다. PC와 서버·터널이 실행 중이어야 하며 터널 재시작 시 주소가 바뀐다. 매일 지속 운영하려면 고정 도메인의 터널 또는 상시 운영 이미지 호스팅으로 전환해야 한다.

## 검증

### 2026-10-20 복구 보완

- 10월 19일 18:14 KST에 터널이 종료된 후 관리 서버만 복구되어 만료된 공개 주소가 남은 장애를 확인했다.
- 기존 `IssueStudio-ServerWatchdog`가 5분마다 실제 공개 JPG의 내용 유형과 SHA-256을 로컬 원본과 비교한다. DNS 성공만으로 정상 처리하지 않는다.
- 장애 시 관리 서버가 제작·게시 중이 아니고 다음 작업까지 2분 이상 남았을 때 이미지 서버와 터널을 복구한다. 새 주소에서 실제 이미지 검증에 성공한 뒤 설정을 반영한다.
- `media.paused`가 있으면 자동 복구하지 않는다. `stop-public-media.bat`이 기록하고 사용자가 `start-public-media.bat`을 실행하면 해제한다.
- 중복 복구는 프로세스 간 mutex로 차단하며, 자동 생성·전송 중 또는 결과 확인이 필요한 게시물이 있으면 재시작하지 않는다. 일일 생성 한도나 5분 게시 간격을 초기화하지 않는다.
- 공개 이미지만 노출하는 8766 포트를 유지한다. Quick Tunnel 주소는 여전히 임시 주소이므로 고정 주소나 무중단 운영을 보장하지 않는다.

- [x] 공개 HTTPS 이미지 요청 200, image/jpeg 및 원본 파일 바이트 일치
- [x] 공개 `/api/status`, `/.env`, `/docs`, 콘텐츠 JSON 경로 404
- [x] 로컬 서버 재시작 후 Instagram 설정 준비 상태 확인
- [x] Meta 계정 조회 및 게시 한도 조회 200 (토큰 연결 단계)
- [x] 실제 Instagram 단일 이미지 예약 게시 성공: 2026-09-30 00:53 KST, https://www.instagram.com/p/Dd4IHAtmSEp/
- [x] 게시 완료 후 Meta 미디어 조회 200 및 permalink 확인

테스트 콘텐츠는 실제 뉴스가 아닌 자체 제작 테스트 안내 카드 1장이다. OpenAI 원고 생성 후 문구와 이미지 가독성을 검토·수정하고, 공개 이미지 조회를 확인한 다음 프로그램 예약 경로로 게시했다. 캐러셀 게시와 매일 10개 운영은 별도 검증이 필요하다.

공식 설명: https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/do-more-with-tunnels/trycloudflare/


## 2026-10-23 연결 복구와 감시 프로세스

- 사진 원본 서비스(8766)와 cloudflared 프로세스가 없고 저장된 `tobago-gets-plugins-rear.trycloudflare.com` DNS가 실패했다. Instagram 계정 GET과 YouTube GET은 현재 정상임을 별도 확인했다. 이전 일반 연결 오류는 로그에 서비스 이름이 없어 당시 네트워크 원인까지 확정할 수 없다.
- 감시기가 `powershell.exe ... | Out-File`로 서버 시작 헬퍼를 실행하면 장기 실행 자식이 상속한 출력 핸들 때문에 다음 건강 점검으로 진행하지 못할 수 있다. 실제 감시 로그가 서버 시작에서 끝난 상태였다.
- `run-managed-helper.ps1`은 헬퍼 출력을 별도 파일에 보관하고 프로세스 자체의 제한 시간 있는 WaitForExit를 사용한다. Windows PowerShell 5.1의 ExitCode 유실을 막도록 Handle을 먼저 확보한다. 서버 시작과 터널 복구 후에도 감시 루프가 계속된다.
- 동일한 부모 종료/장기 자식 실행 상황과 비정상 종료 코드 전달을 Windows PowerShell로 회귀 테스트했다. 종료하지 않은 자식 때문에 부모의 성공 확인이 지연되지 않는다.
- 감시 작업의 시작 버전, 사진 연결 건강 상태 변화, 복구 성공·보류를 watchdog.log에 남긴다. watch-start / watch-media / media-editor-start / media-editor-stop 로그에는 각 헬퍼 결과를 분리한다.
- `providers.api`의 연결 오류는 서비스명·호스트·예외 종류만 출력한다. URL 경로·쿼리·토큰·원본 예외 문구는 출력하지 않는다. autopilot.blocker_code에는 비용 오류 외의 명시적 연결 오류 코드도 보존한다.
- 적용 서버 loaded_at: 2026-10-23T10:13:16.124820+09:00. 계정과 공개 JPG 실제 바이트 검증을 통과했다. 12시간/10만 조회 조건, 유튜브 캡처, 실제 게시 간격 5분, 기존 시도 한도와 승인은 유지했다.
- 임시 Quick Tunnel의 주소 자체가 영구화된 것은 아니다. PC·네트워크 중단 시 제공이 멈출 수 있으며 감시기가 실행되는 동안 복구를 시도한다.
