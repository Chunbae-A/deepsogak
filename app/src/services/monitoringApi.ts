// ---------------------------------------------------------------------------
// TODO(백엔드 연동): 지금은 목업 데이터를 반환한다.
// 실제 연동 시 이 함수 내부만 아래 API 호출로 교체하면 된다 (화면 쪽 코드는 그대로 둠).
//
//   GET {FASTAPI_BASE_URL}/api/monitoring/summary
//   - 서버가 등록된 얼굴 임베딩(ArcFace)으로 이미 순찰(SerpApi + Google Cloud Vision)한
//     결과를 집계해 내려준다. 클라이언트는 원본 얼굴 이미지를 다루지 않는다.
//   - 응답 예시: { totalCandidates, lastCheckedAt, sources: [{ label, count }] }
//   - 인증: 온디바이스에서 생성한 얼굴 임베딩 등록 시 발급받은 세션 토큰을 Authorization
//     헤더로 전달 (얼굴 원본은 등록 시점 이후 서버로 재전송하지 않는다).
//   - 실패/네트워크 오류 시 마지막으로 캐시된 결과를 보여주고 배너로 안내할 것.
// ---------------------------------------------------------------------------

export type MonitoringSource = {
  label: string;
  count: string;
};

export type MonitoringSummary = {
  totalCandidates: number;
  lastCheckedAt: string;
  sources: MonitoringSource[];
};

const MOCK_SUMMARY: MonitoringSummary = {
  totalCandidates: 6,
  lastCheckedAt: '2026.08.02 14:32',
  sources: [
    { label: '검색엔진', count: '3건' },
    { label: '공개 SNS', count: '2건' },
    { label: '기타 웹사이트', count: '1건' },
  ],
};

export async function fetchMonitoringSummary(): Promise<MonitoringSummary> {
  // TODO: 실제 연동 시 아래로 교체
  //   const res = await fetch(`${FASTAPI_BASE_URL}/api/monitoring/summary`, {
  //     headers: { Authorization: `Bearer ${sessionToken}` },
  //   });
  //   if (!res.ok) throw new Error('모니터링 결과를 불러오지 못했습니다.');
  //   return res.json();
  return MOCK_SUMMARY;
}
