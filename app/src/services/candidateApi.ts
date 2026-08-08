import { API_BASE_URL } from '../config';

export type RiskLevel = 'high' | 'medium' | 'low' | 'exclude-recommended';
export type RecommendedAction =
  | 'review_required'
  | 'identity_review_required'
  | 'monitor'
  | 'exclude_recommended'
  | 'analysis_unavailable';

export type Candidate = {
  id: string;
  label: string;
  faceSimilarity: number | null;
  deepfakeScore: number | null;
  faceMatchLevel: 'matched' | 'review' | 'not_matched' | 'unavailable';
  deepfakeSignal: 'suspected' | 'not_suspected' | 'not_analyzed' | 'unavailable';
  recommendedAction: RecommendedAction;
  analysisStatus: 'completed' | 'partial_failed' | 'unavailable';
  riskLabel: string;
  riskLevel: RiskLevel;
  sourceLabel: string;
  thumbnailUrl: string | null;
  warning: string;
};

export type CandidateDetail = Candidate & {
  sourceUrl: string;
  sourceAccount: string;
  foundAt: string;
  signals: string[];
};

export async function fetchCandidates(scanId: string): Promise<Candidate[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/monitoring/scans/${encodeURIComponent(scanId)}/candidates`,
  );
  if (!res.ok) throw new Error('후보 목록을 불러오지 못했습니다.');
  return res.json();
}

export async function fetchCandidateDetail(id: string): Promise<CandidateDetail> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/candidates/${encodeURIComponent(id)}`);
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
