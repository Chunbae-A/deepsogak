// ---------------------------------------------------------------------------
// TODO(AI 모델 연동): 지금은 안전 업로드 단계에서 넘어온 것으로 가정하고
// 고정된 적용 결과를 반환한다.
// 실제 연동 시 이 함수 내부만 아래 API 호출로 교체하면 된다 (화면 쪽 코드는 그대로 둠).
//
//   GET {FASTAPI_BASE_URL}/api/protection/result?jobId={jobId}
//   - safeUploadApi.startProtection이 반환한 jobId로 처리 결과를 조회한다.
//   - protectedPhotoUrl: 딥백신 Beta 적용 후 게시용 보호본 (원본은 서버에 남기지 않음).
//   - appliedChecks: EXIF/GPS 제거, C2PA 서명, SHA-256/pHash 등록 완료 여부.
// ---------------------------------------------------------------------------

export type ProtectionResult = {
  originalLabel: string;
  protectedLabel: string;
  appliedChecks: string[];
};

const MOCK_RESULT: ProtectionResult = {
  originalLabel: '원본 사진',
  protectedLabel: '보호본',
  appliedChecks: [
    '딥백신 Beta 적용 완료',
    '불필요한 위치정보 제거 완료',
    'C2PA 출처정보 생성 완료',
    'SHA-256·pHash 등록 완료',
  ],
};

export async function fetchProtectionResult(): Promise<ProtectionResult> {
  // TODO: 실제 연동 시 아래로 교체
  //   const res = await fetch(`${FASTAPI_BASE_URL}/api/protection/result?jobId=${jobId}`, {
  //     headers: { Authorization: `Bearer ${sessionToken}` },
  //   });
  //   if (!res.ok) throw new Error('보호 처리 결과를 불러오지 못했습니다.');
  //   return res.json();
  return MOCK_RESULT;
}

// TODO(AI 모델 연동): 기기 갤러리(또는 웹 다운로드)에 보호본 저장을 요청한다.
export async function saveProtectedPhoto(): Promise<void> {
  // TODO: 실제 연동 시 expo-media-library(앱) / <a download>(웹)로 교체. 지금은 no-op.
}
