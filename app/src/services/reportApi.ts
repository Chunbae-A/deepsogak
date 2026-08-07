import { Platform } from 'react-native';
import * as Sharing from 'expo-sharing';
import { Directory, File, Paths } from 'expo-file-system';
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

// 사용자가 "직접 수정"으로 고친 증거 초안을 서버에 반영한다. 이후 동의·패키지 다운로드도
// 이 수정된 값을 그대로 사용한다.
export async function updateEvidenceDraft(fields: EvidenceField[]): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/report/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fields }),
  });
  if (!res.ok) throw new Error('증거 초안 수정에 실패했습니다.');
}

// 사용자가 초안에 동의하면 실제 신고서 제출/공식 채널 접수 단계로 넘어간다.
export async function submitConsent(): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/report/consent`, { method: 'POST' });
  if (!res.ok) throw new Error('동의 처리에 실패했습니다.');
}

// 동의된 증거 초안을 실제 파일로 받아 기기(웹 다운로드 / 네이티브 공유 시트)에 저장한다.
// PDF·ZIP 생성기는 아직 없어 서버가 사람이 읽을 수 있는 텍스트 요약으로 내려준다.
export async function saveReportPackage(): Promise<void> {
  const url = `${API_BASE_URL}/api/report/package`;
  const filenameMatch = /filename="([^"]+)"/;

  if (Platform.OS === 'web') {
    const res = await fetch(url);
    if (!res.ok) throw new Error('신고자료 저장에 실패했습니다.');
    const filename = filenameMatch.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? 'deepsogak_report.txt';
    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    return;
  }

  const downloaded = await File.downloadFileAsync(url, new Directory(Paths.document));
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(downloaded.uri);
  }
}
