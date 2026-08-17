import { Platform } from 'react-native';
import * as MediaLibrary from 'expo-media-library/legacy';
import { Directory, File, Paths } from 'expo-file-system';
import { API_BASE_URL } from '../config';

// EXIF·GPS 제거, 딥백신(적대적 노이즈), SHA-256/pHash 계산은
// server/main.py의 백그라운드 작업(POST /api/protection/process)이 실제로 처리한다.
// C2PA 서명은 아직 서명 인프라가 없어 "완료" 여부만 표시하는 수준으로 시뮬레이션되어 있다.

export type DeepbaeksinMeta = {
  applied: boolean;
  reason: string | null;
  iterationsRun: number;
  epsilon: number;
  targetModels: string[];
  usedModels: string[];
  similarityAfter: number | null;
  similarityAfterByModel: Record<string, number> | null;
  endToEndSimilarityAfter: number | null;
  similarityAfterJpegRoundTrip: number | null;
  jpegQualityChecked: number;
  ssim: number | null;
  elapsedSeconds: number;
  thresholdStatus: string;
};

export type ProtectionResult = {
  status: 'completed';
  originalLabel: string;
  protectedLabel: string;
  originalPhotoUrl: string;
  protectedPhotoUrl: string;
  sha256: string;
  phash: string;
  appliedChecks: string[];
  deepbaeksin: DeepbaeksinMeta;
};

export type ProtectionStatus =
  | { status: 'processing' }
  | { status: 'failed'; errorReason: string }
  | ProtectionResult;

async function fetchProtectionStatus(jobId: string): Promise<ProtectionStatus> {
  const res = await fetch(`${API_BASE_URL}/api/protection/result?jobId=${jobId}`);
  if (!res.ok) throw new Error('보호 처리 결과를 불러오지 못했습니다.');
  const data = await res.json();
  if (data.status !== 'completed') return data;
  return {
    ...data,
    originalPhotoUrl: `${API_BASE_URL}${data.originalPhotoUrl}`,
    protectedPhotoUrl: `${API_BASE_URL}${data.protectedPhotoUrl}`,
  };
}

export async function fetchProtectionResult(jobId: string): Promise<ProtectionResult> {
  const data = await fetchProtectionStatus(jobId);
  if (data.status === 'processing') throw new Error('아직 처리 중입니다.');
  if (data.status === 'failed') throw new Error(data.errorReason);
  return data;
}

// 백그라운드 처리(딥백신 등)가 끝날 때까지 짧은 간격으로 상태를 물어본다.
// ProtectingScreen이 떠 있는 동안 호출해, 완료된 뒤에야 결과 화면으로 넘어가게 한다.
export async function pollProtectionResult(
  jobId: string,
  { intervalMs = 1000, timeoutMs = 60000 }: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<ProtectionResult> {
  const startedAt = Date.now();
  while (true) {
    const data = await fetchProtectionStatus(jobId);
    if (data.status === 'completed') return data;
    if (data.status === 'failed') throw new Error(data.errorReason);
    if (Date.now() - startedAt > timeoutMs) throw new Error('처리 시간이 너무 오래 걸립니다.');
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

// 서버 보관본을 남긴 뒤, 실제로 기기 갤러리(네이티브) 또는 다운로드 폴더(웹)에 보호본을 저장한다.
export async function saveProtectedPhoto(jobId: string, protectedPhotoUrl: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/protection/save?jobId=${jobId}`, { method: 'POST' });
  if (!res.ok) throw new Error('보호사진 저장에 실패했습니다.');

  const filename = `deepsogak_protected_${jobId}.jpg`;
  if (Platform.OS === 'web') {
    await downloadToBrowser(protectedPhotoUrl, filename);
    return;
  }

  const { status } = await MediaLibrary.requestPermissionsAsync();
  if (status !== 'granted') {
    throw new Error('사진 라이브러리 접근 권한이 필요합니다.');
  }
  const downloaded = await File.downloadFileAsync(protectedPhotoUrl, new Directory(Paths.cache));
  await MediaLibrary.saveToLibraryAsync(downloaded.uri);
}

async function downloadToBrowser(url: string, filename: string): Promise<void> {
  const res = await fetch(url);
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}
