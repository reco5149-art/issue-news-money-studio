# API 연결 안내 — 처음 설정하는 운영자용

지금은 API 키가 없어도 **로컬 원고 배치 → 카드 생성 → 수정 → ZIP 저장**이 가능합니다.
외부 AI·검색·실제 게시 연결은 아래 순서로 추가합니다. 비밀 키는 채팅이나 GitHub에 보내지 마세요.

## 0. 입력할 파일

프로젝트의 `.env.example`을 `.env`로 복사합니다. 각 `=` 뒤에 값을 넣고 저장한 뒤 앱을 재시작합니다.
`.env`는 Git에서 제외되어 저장소에 올라가지 않습니다. 키가 있는 화면을 발표 자료에 캡처하지 마세요.

## 1. AI 원고·이미지 — OpenAI

1. https://platform.openai.com 에 본인 계정으로 로그인합니다.
2. 프로젝트와 API 결제/사용 한도를 확인합니다. ChatGPT 구독과 API 사용료는 별도입니다.
3. https://platform.openai.com/api-keys 에서 해당 프로젝트의 키를 직접 생성합니다.
4. `.env`의 `OPENAI_API_KEY=`에 넣습니다.
5. 기본 모델 접근 가능 여부를 확인하고 필요하면 `OPENAI_TEXT_MODEL`, `OPENAI_IMAGE_MODEL`을 변경합니다.
6. 앱 재시작 → 연결 설정에서 설정 존재 확인 → 짧은 원고로 `AI 요약` 1회 테스트.
7. AI 이미지 생성은 별도 비용이 발생하므로 텍스트 확인 후 1개부터 테스트합니다.

모델 접근 권한, 계정 인증, 사용 한도에 따라 API가 거절될 수 있습니다. 실패 메시지를 확인하고
프로젝트 키·결제·모델 접근 권한을 점검하세요. 실제 키 값은 공유하지 않습니다.

## 2. 뉴스 소재 — Naver 검색 API

1. https://developers.naver.com/apps/#/register 에서 애플리케이션을 직접 등록합니다.
2. 사용 API에 **검색**을 선택합니다. 화면의 필수 환경 정보는 본인 앱 정보로 입력합니다.
3. 발급된 Client ID와 Client Secret을 확인합니다.
4. `.env`에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`을 입력합니다.
5. 앱 재시작 → 트렌드 탐색 → AI/경제 등 한 주제로 실시간 검색합니다.
6. 원문을 가져와 제목·본문·출처가 맞는지 확인합니다.

공식 안내: https://developers.naver.com/docs/serviceapi/search/news/news.md

## 3. 영상 소재 — YouTube Data API

1. https://console.cloud.google.com 에 로그인하고 본인 프로젝트를 선택/생성합니다.
2. API 라이브러리에서 **YouTube Data API v3**를 활성화합니다.
3. 사용자 인증 정보에서 API 키를 직접 생성합니다.
4. 키의 API 제한을 YouTube Data API v3로 설정합니다. 앱은 로컬 서버에서 호출하므로
   브라우저 HTTP referrer 전용 제한을 적용하면 서버 호출이 실패할 수 있습니다.
5. `.env`의 `YOUTUBE_API_KEY`에 넣고 앱을 재시작합니다.
6. 트렌드 탐색 또는 보유한 공개 영상 링크로 제목·설명 조회를 테스트합니다.

이 연결은 자막·영상 자동 다운로드 권한을 제공하지 않습니다.
공식 안내: https://developers.google.com/youtube/v3/getting-started

## 4. 실제 게시 — Meta / Instagram Login

사용자 계정은 프로페셔널이므로 계정 유형 조건은 확인되었습니다. 다음 설정이 별도로 필요합니다.

1. https://developers.facebook.com/apps/ 에서 본인의 개발자 계정과 앱을 준비합니다.
2. **Instagram API with Instagram Login** 흐름으로 연결합니다. 앱 생성 메뉴 이름은 계정/콘솔 버전에 따라 다를 수 있습니다.
3. 본인 Instagram 계정을 앱의 테스트/연결 대상에 추가하고, 계정에서 필요한 초대를 수락합니다.
4. 게시에 필요한 권한(`instagram_business_basic`, `instagram_business_content_publish`)이 포함된
   **Instagram 사용자 토큰**과 Instagram 사용자 ID를 직접 발급·확인합니다.
5. `.env`의 `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`에 넣습니다.
6. 앱에서 허용되는 `META_API_VERSION`을 확인합니다. 테스트 계정 밖으로 서비스할 때는 앱 검수 등 별도 조건을 확인해야 합니다.
7. 아래 공개 이미지 주소까지 설정한 뒤 단일 카드 1장으로 테스트합니다.

토큰 생성·권한 승인·계정 설정은 소유자가 직접 진행해야 합니다. 비밀번호를 프로그램에 넣지 않습니다.
토큰은 만료/취소될 수 있으며 현재 버전에는 자동 갱신이 없습니다.

공식 자료:
- https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/
- https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api

## 5. Meta가 읽을 이미지 주소

로컬 `127.0.0.1` 주소는 Meta가 읽을 수 없습니다. **생성 이미지 폴더만** HTTPS로 제공해야 합니다.

선택 A: `data/media`를 본인 정적 호스팅에 업로드하고 새 이미지 생성 때마다 동기화합니다.
선택 B: 프로젝트의 미디어 전용 서버를 실행하고 본인이 관리하는 HTTPS 터널에 연결합니다.

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.media_server:app --host 127.0.0.1 --port 8766
```

- 8766은 미디어만 제공합니다. 8765 편집 앱을 외부에 공개하지 않습니다.
- 공개 루트 주소를 `PUBLIC_MEDIA_BASE_URL`에 입력합니다.
- `{공개주소}/{콘텐츠ID}/01.jpg`가 외부 네트워크에서 인증 없이 열리는지 확인합니다.
- 이미지 URL의 공개는 인스타그램으로 전달할 제작 이미지에만 한정합니다.
- 터널 설치/공개 연결은 아직 실행하지 않았습니다. 서비스와 도메인 선택 후 설정이 필요합니다.

## 6. 첫 게시 확인 순서

1. 자체 작성 원고와 자체 디자인으로 1장 생성.
2. 사실·권리 확인 → 저장.
3. 한국 시간으로 몇 분 뒤 예약.
4. 앱 실행을 유지하고 실제 Instagram 계정에서 게시 확인.
5. 성공 후 2장 캐러셀 → 일일 예약 순서로 확대.
6. 게시 결과가 `확인 필요`이면 계정에서 실제 게시 여부부터 확인. 무조건 다시 예약하지 않기.

## 권장 연결 순서와 금요일 제출

OpenAI → Naver → YouTube → Meta → 공개 이미지 호스팅 순서로 연결합니다.
심사나 권한 설정이 지연되면 발표는 키 없는 원고 제작 흐름으로 진행하고,
실제 게시 검증은 최종 체크리스트의 미완료 항목으로 표시합니다.
