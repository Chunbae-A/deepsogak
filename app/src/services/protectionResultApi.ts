import { Platform } from 'react-native';
import * as MediaLibrary from 'expo-media-library/legacy';
import { Directory, File, Paths } from 'expo-file-system';
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
