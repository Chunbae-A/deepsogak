import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { InfoPanel } from '../components/InfoPanel';
import { CheckRow } from '../components/CheckRow';
import { PrimaryButton } from '../components/Button';
import { ProtectingScreen } from './ProtectingScreen';
import { colors, radii, spacing, typography } from '../theme';
import { SelectedPhoto, pickPhoto, startProtection } from '../services/safeUploadApi';

const uploadIcon = require('../../assets/icons/icon-upload.png');

const PROTECTION_FEATURES = [
  '불필요한 EXIF·GPS 정보 제거',
  'SHA-256·pHash 생성',
  'ArcFace 보호 전후 얼굴 확인',
  'ONNX 딥페이크 연결 시험',
];

export function SafeUploadScreen({ onCreateProtectedPhoto }: { onCreateProtectedPhoto: (jobId: string) => void }) {
  const [photo, setPhoto] = useState<SelectedPhoto | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const handleSelectPhoto = async () => {
    setUploadError(null);
    const result = await pickPhoto();
    if (result.status === 'selected') {
      setPhoto(result.photo);
    } else if (result.status === 'permission-denied') {
      setUploadError('사진 접근 권한이 없어 선택할 수 없습니다.');
    }
  };

  const handleCreate = async () => {
    if (!photo) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const jobId = await startProtection(photo);
      onCreateProtectedPhoto(jobId);
    } catch {
      setUploadError('업로드에 실패했습니다. 다시 시도해 주세요.');
    } finally {
      setIsUploading(false);
    }
  };

  if (isUploading && photo) {
    return <ProtectingScreen photo={photo} />;
  }

  return (
    <View style={styles.screen}>
      <AppBar step="1 / 5" />
      <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>안전하게 게시할 사진을 준비해요</Text>
          <Text style={styles.subtitle}>사진 속 개인 정보와 출처 정보를 먼저 보호합니다.</Text>
        </View>

        <Pressable style={styles.photoSelect} onPress={handleSelectPhoto}>
          <View style={styles.uploadIconWrap}>
            <Image source={uploadIcon} style={styles.uploadIcon} resizeMode="contain" />
          </View>
          <Text style={styles.photoSelectTitle}>게시할 얼굴 사진 선택</Text>
          <Text style={styles.photoSelectHint}>
            {photo ? `${photo.fileName} · ${photo.sizeLabel}` : 'JPG·PNG · 최대 20MB'}
          </Text>
        </Pressable>

        <View style={styles.featuresCard}>
          <Text style={styles.featuresTitle}>보호 기능 4가지</Text>
          {PROTECTION_FEATURES.map((label) => (
            <CheckRow key={label} label={label} />
          ))}
        </View>

        <InfoPanel
          title="딥백신 Beta 계획"
          body="적대적 노이즈 기반 보호는 아직 적용되지 않았습니다. 이번 데모는 EXIF 제거와 모델 API 연결만 검증합니다."
        />
        <InfoPanel
          title="현재 데모의 얼굴 정보 처리"
          body="선택한 사진은 로컬 개발 서버와 모델 API에서 처리됩니다. 실제 운영 전에는 암호화·보관 기간·삭제 정책을 추가해야 합니다."
        />
      </ScrollView>

      <View style={styles.bottomCta}>
        <Text style={styles.bottomHint}>{uploadError ?? '사진은 로컬 개발 서버로 전송됩니다'}</Text>
        <PrimaryButton label="보호사진 만들기" onPress={handleCreate} disabled={!photo} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingHorizontal: spacing.xl, paddingTop: spacing.lg, gap: spacing.md },
  content: { flex: 1, width: '100%' },
  contentInner: { gap: spacing.md, paddingBottom: spacing.md },
  headerCopy: { gap: spacing.xs },
  title: { ...typography.title, color: colors.text900 },
  subtitle: { ...typography.caption, color: colors.text700 },
  photoSelect: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.blue600,
    borderStyle: 'dashed',
    borderRadius: radii.lg,
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    width: '100%',
  },
  uploadIconWrap: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.blue100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadIcon: { width: 20, height: 20 },
  photoSelectTitle: { ...typography.bodyStrong, color: colors.text900 },
  photoSelectHint: { ...typography.caption, color: colors.text500 },
  featuresCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.xs,
    width: '100%',
  },
  featuresTitle: { ...typography.bodyStrong, color: colors.text900 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg, gap: spacing.sm },
  bottomHint: { ...typography.caption, color: colors.text500, textAlign: 'center' },
});
