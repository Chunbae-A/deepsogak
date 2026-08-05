// ---------------------------------------------------------------------------
// TODO(AI 모델 연동): 지금은 목업 후보 3건을 반환한다.
// 실제 연동 시 이 함수 내부만 아래 API 호출로 교체하면 된다 (화면 쪽 코드는 그대로 둠).
//
//   GET {FASTAPI_BASE_URL}/api/monitoring/candidates
//   - similarityPercent: ArcFace 임베딩 코사인 유사도(0~1)를 %로 변환한 값.
//     서버에서 이미 임계값(≥0.6)을 넘긴 후보만 내려준다.
//   - riskLabel / riskLevel: EfficientNet-B4 딥페이크 판별 결과를 사람이 읽는 문구로 변환한 것.
//     신뢰도 구간은 기획서 기준 85%↑ 높음 / 60~84% 중간(확인요청) / 60%↓ 낮음(로그만)이다.
//   - 정렬은 서버가 위험도 내림차순으로 내려준다고 가정한다(첫 후보 = highlighted).
// ---------------------------------------------------------------------------

export type RiskLevel = 'high' | 'medium' | 'low' | 'exclude-recommended';

export type Candidate = {
  id: string;
  label: string; // "후보 1"
  similarityPercent: number; // 92
  riskLabel: string; // "딥페이크 위험도 · 높음"
  riskLevel: RiskLevel;
};

const MOCK_CANDIDATES: Candidate[] = [
  { id: 'c1', label: '후보 1', similarityPercent: 92, riskLabel: '딥페이크 위험도 · 높음', riskLevel: 'high' },
  { id: 'c2', label: '후보 2', similarityPercent: 71, riskLabel: '딥페이크 위험도 · 낮음', riskLevel: 'low' },
  { id: 'c3', label: '후보 3', similarityPercent: 38, riskLabel: '제외 권장', riskLevel: 'exclude-recommended' },
];

export async function fetchCandidates(): Promise<Candidate[]> {
  // TODO: 실제 연동 시 아래로 교체
  //   const res = await fetch(`${FASTAPI_BASE_URL}/api/monitoring/candidates`, {
  //     headers: { Authorization: `Bearer ${sessionToken}` },
  //   });
  //   if (!res.ok) throw new Error('후보 목록을 불러오지 못했습니다.');
  //   return res.json();
  return MOCK_CANDIDATES;
}

// TODO(AI 모델 연동): 사용자가 "제외"하지 않은 후보 id 목록을 서버에 알려
// 실제 신고서 생성(RAG) 단계로 넘길 때 이 함수를 호출한다.
//   POST {FASTAPI_BASE_URL}/api/monitoring/candidates/confirm  { keepIds: string[] }
export async function confirmCandidateSelection(keepIds: string[]): Promise<void> {
  // TODO: 실제 연동 시 fetch POST로 교체. 지금은 no-op.
  void keepIds;
}
