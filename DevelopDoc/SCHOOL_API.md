# 세명대학교 API 연결

`set-school-api.bat`를 열고 학교 API 키를 비공개 입력합니다. **지원 모델 조회**는 공식 게이트웨이의 모델 목록만 읽으며 콘텐츠를 생성하지 않습니다. 응답에서 확인된 GPT 모델 중 문안·사진 검수·영상 장면 검수 모델을 각각 선택할 수 있습니다. 목록에 있다고 모든 모델의 이미지 입력·구조화 출력 호환성이 검증된 것은 아닙니다.

학교 연결 활성화 체크 후 저장하면 `.env`의 `AI_PROVIDER=semyung`이 설정됩니다. 서버 재시작 후 적용됩니다. 체크하지 않으면 학교 설정만 저장하고 기존 연결 선택을 유지합니다. 개인 연결로 돌아갈 때는 `AI_PROVIDER=openai`로 변경하고 재시작합니다. 개인 OpenAI 키를 삭제하거나 덮어쓰지 않습니다.

- 공식 주소: `https://factchat-cloud.mindlogic.ai/v1/gateway`
- 키: `SEMYUNG_API_KEY`
- 모델: `SEMYUNG_TEXT_MODEL`, `SEMYUNG_REVIEW_MODEL`, `SEMYUNG_FRAME_MODEL`
- 공식 주소 외에는 학교 키를 보내지 않습니다. 실패 시 개인 API로 자동 전환하지 않습니다.
- 현재 학교 연동은 Responses API 문안·사진 검수 범위입니다. 학교의 비동기 음성 전사·이미지 생성 API는 아직 연결하지 않았으며 명시적인 오류로 중단합니다. 자막이 있는 영상은 자막 분석을 사용할 수 있습니다.
- KIE 이미지, YouTube 검색, Instagram 인증은 별도 연결입니다. 학교 API 설정으로 YouTube 검색 할당량 문제가 해결되지는 않습니다.
- 키는 로컬 `.env`에만 저장하며 `/api/status`는 공급자·모델·설정 여부만 반환합니다. 키를 Git이나 채팅에 넣지 않습니다.

학교 크레딧 잔액·이용 조건은 학교 계정에서 확인합니다. 모델 조회 성공과 실제 생성 성공은 별개이므로 전환 후 소량의 실제 생성·검수로 호환성을 확인해야 합니다.

공식 문서: https://docs.mindlogic.ai/docs/semyung-ac/api-gateway/reference/responses-api
