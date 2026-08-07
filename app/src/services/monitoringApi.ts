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

// 자동 탐색 밖(비공개 계정 등)의 URL·캡처를 사용자가 직접 제보해 분석 후보에 포함시킨다.
export async function submitManualReport(url: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error('제보 등록에 실패했습니다. URL을 확인해 주세요.');
}
