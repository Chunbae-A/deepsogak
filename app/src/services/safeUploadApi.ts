// ---------------------------------------------------------------------------
// TODO(AI 모델 연동): 지금은 파일 선택을 목업(고정 파일명)으로 처리하고,
// 보호 처리 자체도 즉시 완료된 것처럼 흉내만 낸다.
// 실제 연동 시 이 함수 내부만 아래 흐름으로 교체하면 된다 (화면 쪽 코드는 그대로 둠).
//
//   1) 파일 선택: 앱은 react-native-image-picker(또는 expo-image-picker),
//      웹은 <input type="file" accept="image/jpeg,image/png">로 실제 파일을 받는다.
//      클라이언트에서 JPG/PNG, 최대 20MB 검증을 먼저 수행한다.
//   2) 보호 처리 요청:
//        POST {FASTAPI_BASE_URL}/api/protection/process  (multipart: photo)
//      서버는 EXIF·GPS 메타데이터 제거 → 딥백신 Beta(적대적 노이즈) 적용 →
//      C2PA Content Credentials 서명 → SHA-256/pHash 생성을 순차 수행한다.
//      얼굴 등록(특징 벡터 변환)은 기기에서만 이뤄지며 원본 셀카는 서버로 전송하지 않는다.
//   3) 응답으로 받은 protectedPhotoUrl/appliedChecks를 보호사진 생성 완료 화면에 전달한다.
// ---------------------------------------------------------------------------

export type SelectedPhoto = {
  fileName: string;
  sizeLabel: string;
};

export async function pickPhoto(): Promise<SelectedPhoto> {
  // TODO: 실제 연동 시 네이티브/웹 파일 선택 API로 교체
  return { fileName: 'photo_01.jpg', sizeLabel: '3.2MB' };
}

// TODO(AI 모델 연동): 선택된 사진을 서버로 보내 보호 처리를 요청한다.
//   POST {FASTAPI_BASE_URL}/api/protection/process
export async function startProtection(photo: SelectedPhoto): Promise<void> {
  // TODO: 실제 연동 시 fetch POST(multipart)로 교체. 지금은 no-op.
  void photo;
}
