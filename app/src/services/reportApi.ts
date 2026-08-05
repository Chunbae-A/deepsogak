// ---------------------------------------------------------------------------
// TODO(AI 모델 연동): 지금은 목업 증거 초안 8개 필드를 반환한다.
// 실제 연동 시 이 함수 내부만 아래 API 호출로 교체하면 된다 (화면 쪽 코드는 그대로 둠).
//
//   GET {FASTAPI_BASE_URL}/api/report/draft
//   - 게시물 URL/계정/발견 시각: 모니터링 단계에서 수집한 원본 메타데이터.
//   - SHA-256 / pHash: 캡처 파일에 대해 서버가 계산한 해시값 (신고서 위·변조 방지용).
//   - C2PA 확인 상태: Content Credentials(C2PA) 서명 검증 결과.
//   - AI 분석 결과: EfficientNet-B4 딥페이크 판별 결과 요약.
//   - 신고서 본문 생성은 RAG(+Claude) 기반으로 별도 엔드포인트에서 처리하며,
//     여기서는 "직접 수정" 진입 전 보여줄 구조화된 초안 필드만 다룬다.
// ---------------------------------------------------------------------------

export type EvidenceField = {
  key: string;
  label: string;
  value: string;
};

const MOCK_EVIDENCE_DRAFT: EvidenceField[] = [
  { key: 'postUrl', label: '게시물 URL', value: 'example.com/p/1248' },
  { key: 'account', label: '게시 계정', value: '@public_sample' },
  { key: 'foundAt', label: '발견 시각', value: '2026.08.02 14:21' },
  { key: 'capture', label: '캡처 또는 파일', value: 'capture_01.png' },
  { key: 'sha256', label: 'SHA-256', value: '확인 완료' },
  { key: 'phash', label: 'pHash', value: '등록 완료' },
  { key: 'c2pa', label: 'C2PA 확인 상태', value: '원본 불일치' },
  { key: 'aiResult', label: 'AI 분석 결과', value: '위험도 높음' },
];

export async function fetchEvidenceDraft(): Promise<EvidenceField[]> {
  // TODO: 실제 연동 시 아래로 교체
  //   const res = await fetch(`${FASTAPI_BASE_URL}/api/report/draft`, {
  //     headers: { Authorization: `Bearer ${sessionToken}` },
  //   });
  //   if (!res.ok) throw new Error('증거 초안을 불러오지 못했습니다.');
  //   return res.json();
  return MOCK_EVIDENCE_DRAFT;
}

// TODO(AI 모델 연동): 사용자가 초안에 동의하면 실제 신고서 제출/공식 채널 접수 단계로 넘어간다.
//   POST {FASTAPI_BASE_URL}/api/report/consent  { evidenceDraftId }
// 서버는 이 시점에 TSA(타임스탬프) 서명을 확정하고 신고서 PDF 생성을 트리거한다.
export async function submitConsent(): Promise<void> {
  // TODO: 실제 연동 시 fetch POST로 교체. 지금은 no-op.
}
