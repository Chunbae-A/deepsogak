import { API_BASE_URL } from '../config';

// server/main.py의 /api/monitoring/candidates가 응답을 만든다. similarityPercent(ArcFace
// 코사인 유사도)와 riskLabel/riskLevel(EfficientNet-B4 딥페이크 판별)은 아직 모델이
// 없어 서버도 고정된 시뮬레이션 데이터를 반환한다 — 진짜 모델이 붙으면
// server/main.py의 get_candidates 내부만 교체하면 된다.

export type RiskLevel = 'high' | 'medium' | 'low' | 'exclude-recommended';

export type Candidate = {
  id: string;
  label: string; // "후보 1"
  similarityPercent: number; // 92
  riskLabel: string; // "딥페이크 위험도 · 높음"
  riskLevel: RiskLevel;
};

export type CandidateDetail = Candidate & {
  sourceLabel: string; // "공개 SNS"
  sourceUrl: string;
  sourceAccount: string;
  foundAt: string;
  signals: string[];
};

export async function fetchCandidates(): Promise<Candidate[]> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/candidates`);
  if (!res.ok) throw new Error('후보 목록을 불러오지 못했습니다.');
  return res.json();
}

export async function fetchCandidateDetail(id: string): Promise<CandidateDetail> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/candidates/${id}`);
  if (!res.ok) throw new Error('후보 상세 정보를 불러오지 못했습니다.');
  return res.json();
}

// 사용자가 "제외"하지 않은 후보 id 목록을 서버에 알려 다음 단계(신고서 초안)로 넘긴다.
export async function confirmCandidateSelection(keepIds: string[]): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/candidates/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ keepIds }),
  });
  if (!res.ok) throw new Error('후보 선택을 저장하지 못했습니다.');
}
