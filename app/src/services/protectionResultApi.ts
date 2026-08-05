import { API_BASE_URL } from '../config';

// EXIF·GPS 제거, SHA-256/pHash 계산은 server/main.py가 실제로 처리해 반환한다.
// 딥백신 Beta(적대적 노이즈)·C2PA 서명은 아직 모델·서명 인프라가 없어
// 서버에서도 "완료" 여부만 표시하는 수준으로 시뮬레이션되어 있다 (server/main.py 참고).

export type ProtectionResult = {
  originalLabel: string;
  protectedLabel: string;
  originalPhotoUrl: string;
  protectedPhotoUrl: string;
  appliedChecks: string[];
};

export async function fetchProtectionResult(jobId: string): Promise<ProtectionResult> {
  const res = await fetch(`${API_BASE_URL}/api/protection/result?jobId=${jobId}`);
  if (!res.ok) throw new Error('보호 처리 결과를 불러오지 못했습니다.');
  const data = await res.json();
  return {
    ...data,
    originalPhotoUrl: `${API_BASE_URL}${data.originalPhotoUrl}`,
    protectedPhotoUrl: `${API_BASE_URL}${data.protectedPhotoUrl}`,
  };
}

// TODO(AI 모델 연동): 기기 갤러리(또는 웹 다운로드)에 보호본 저장을 요청한다.
export async function saveProtectedPhoto(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/protection/save?jobId=${jobId}`, { method: 'POST' });
  if (!res.ok) throw new Error('보호사진 저장에 실패했습니다.');
}
