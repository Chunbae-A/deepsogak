import { API_BASE_URL } from '../config';

// server/main.py의 /api/report/draft가 응답을 만든다. SHA-256/pHash/C2PA/AI 분석 결과는
// 안전 업로드·모니터링 단계와 달리 아직 실제 신고 대상 게시물에 대해 계산되지 않고
// 고정된 시뮬레이션 데이터다 — 진짜 신고서 생성(RAG) 파이프라인이 붙으면
// server/main.py의 get_report_draft 내부만 교체하면 된다.

export type EvidenceField = {
  key: string;
  label: string;
  value: string;
};

export async function fetchEvidenceDraft(): Promise<EvidenceField[]> {
  const res = await fetch(`${API_BASE_URL}/api/report/draft`);
  if (!res.ok) throw new Error('증거 초안을 불러오지 못했습니다.');
  return res.json();
}

// 사용자가 초안에 동의하면 실제 신고서 제출/공식 채널 접수 단계로 넘어간다.
export async function submitConsent(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/report/consent`, { method: 'POST' });
  if (!res.ok) throw new Error('동의 처리에 실패했습니다.');
}
