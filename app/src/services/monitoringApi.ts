import { API_BASE_URL } from '../config';

// server/main.py의 /api/monitoring/summary가 응답을 만든다. 실제 얼굴 임베딩(ArcFace)
// 순찰(SerpApi + Google Cloud Vision) 모델·키가 아직 없어 서버도 고정된 시뮬레이션
// 데이터를 반환한다 — 이 함수는 그 서버를 호출하는 지점이고, 진짜 모델이 붙으면
// server/main.py의 get_monitoring_summary 내부만 교체하면 된다.

export type MonitoringSource = {
  label: string;
  count: string;
};

export type MonitoringSummary = {
  totalCandidates: number;
  lastCheckedAt: string;
  sources: MonitoringSource[];
};

export async function fetchMonitoringSummary(): Promise<MonitoringSummary> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/summary`);
  if (!res.ok) throw new Error('모니터링 결과를 불러오지 못했습니다.');
  return res.json();
}
