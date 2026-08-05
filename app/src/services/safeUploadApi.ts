import { Platform } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { API_BASE_URL } from '../config';

export type SelectedPhoto = {
  uri: string;
  fileName: string;
  sizeLabel: string;
  mimeType: string;
};

export async function pickPhoto(): Promise<SelectedPhoto | null> {
  const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
  if (!permission.granted) return null;

  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ImagePicker.MediaTypeOptions.Images,
    quality: 1,
  });
  if (result.canceled || result.assets.length === 0) return null;

  const asset = result.assets[0];
  const fileName = asset.fileName ?? asset.uri.split('/').pop() ?? 'photo.jpg';
  const sizeLabel = asset.fileSize ? `${(asset.fileSize / (1024 * 1024)).toFixed(1)}MB` : '';
  return { uri: asset.uri, fileName, sizeLabel, mimeType: asset.mimeType ?? 'image/jpeg' };
}

async function buildFormData(photo: SelectedPhoto): Promise<FormData> {
  const formData = new FormData();
  if (Platform.OS === 'web') {
    // 웹에서는 uri가 blob: URL이라 실제 Blob으로 가져와 첨부해야 한다.
    const blob = await (await fetch(photo.uri)).blob();
    formData.append('photo', blob, photo.fileName);
  } else {
    // @ts-expect-error React Native FormData는 { uri, name, type } 형태의 파일 참조를 받는다.
    formData.append('photo', { uri: photo.uri, name: photo.fileName, type: photo.mimeType });
  }
  return formData;
}

// EXIF·GPS 제거, C2PA 서명, SHA-256/pHash 계산은 server/main.py의
// POST /api/protection/process가 실제로 처리한다. 딥백신 Beta(적대적 노이즈) 적용은
// 아직 모델이 없어 서버에도 TODO로 남아 있다.
export async function startProtection(photo: SelectedPhoto): Promise<string> {
  const formData = await buildFormData(photo);
  const res = await fetch(`${API_BASE_URL}/api/protection/process`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw new Error('사진 처리 요청에 실패했습니다.');
  const data = await res.json();
  return data.jobId as string;
}
