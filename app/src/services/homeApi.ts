import { API_BASE_URL } from '../config';

// server/main.py의 /api/home/summary가 응답을 만든다. 계정·통계 시스템이 아직 없어
// 이번 세션에서 처리한 보호사진·노출후보·신고자료 건수를 그대로 집계한 값이다.

export type HomeSummary = {
  protectedCount: number;
  candidateCount: number;
  reportCount: number;
  lastCheckedAt: string;
};

export async function fetchHomeSummary(): Promise<HomeSummary> {
  const res = await fetch(`${API_BASE_URL}/api/home/summary`);
  if (!res.ok) throw new Error('홈 요약 정보를 불러오지 못했습니다.');
  return res.json();
}
