import { API_BASE_URL } from '../config';

export type MonitoringSource = {
  label: string;
  count: string;
};

export type MonitoringSummary = {
  totalCandidates: number;
  lastCheckedAt: string;
  sources: MonitoringSource[];
};

export type MonitoringScanStatusValue =
  | 'queued'
  | 'searching'
  | 'identity_filtering'
  | 'deepfake_analyzing'
  | 'completed'
  | 'partial_failed'
  | 'failed';

export type MonitoringScanCreated = {
  scanId: string;
  status: MonitoringScanStatusValue;
  statusUrl: string;
  candidatesUrl: string;
  referenceCount: number;
  recommendedReferenceCount: number;
  warning: string;
};

export type MonitoringScanStatus = {
  scanId: string;
  status: MonitoringScanStatusValue;
  progressPercent: number;
  searchedCandidateCount: number;
  analyzedCandidateCount: number;
  identityMatchCount: number;
  deepfakeCompletedCount: number;
  errorCode: string | null;
  warning: string;
};

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail?.message === 'string') return detail.message;
  } catch {
    // JSON 오류 본문이 아니면 사용자용 기본 문구를 사용한다.
  }
  return fallback;
}

export async function startMonitoringScan(input: {
  queryText: string;
  webMonitoringConsent: boolean;
  referenceJobIds: string[];
  maximumResults?: number;
}): Promise<MonitoringScanCreated> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/scans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...input,
      maximumResults: input.maximumResults ?? 5,
    }),
  });
  if (!res.ok) {
    throw new Error(await errorMessage(res, '공개 노출 확인을 시작하지 못했습니다.'));
  }
  return res.json();
}

export async function fetchMonitoringScanStatus(scanId: string): Promise<MonitoringScanStatus> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/scans/${encodeURIComponent(scanId)}`);
  if (!res.ok) {
    throw new Error(await errorMessage(res, '모니터링 진행 상태를 불러오지 못했습니다.'));
  }
  return res.json();
}

export async function fetchMonitoringSummary(scanId: string): Promise<MonitoringSummary> {
  const res = await fetch(
    `${API_BASE_URL}/api/monitoring/scans/${encodeURIComponent(scanId)}/summary`,
  );
  if (!res.ok) {
    throw new Error(await errorMessage(res, '모니터링 결과를 불러오지 못했습니다.'));
  }
  return res.json();
}

// 자동 탐색 밖(비공개 계정 등)의 URL을 사용자가 직접 제보해 검토 후보에 포함시킨다.
export async function submitManualReport(url: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/monitoring/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) throw new Error('제보 등록에 실패했습니다. URL을 확인해 주세요.');
}
