import { useEffect, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { InfoPanel } from '../components/InfoPanel';
import { CheckRow } from '../components/CheckRow';
import { StatusChip } from '../components/StatusChip';
import { PrimaryButton } from '../components/Button';
import { colors, radii, spacing, typography } from '../theme';
import { SelectedPhoto } from '../services/safeUploadApi';

const uploadIcon = require('../../assets/icons/icon-upload.png');

const STAGES = ['EXIF·GPS 정보 제거', '딥백신 Beta 적용', 'C2PA·SHA-256·pHash 생성'];

export function ProtectingScreen({ photo }: { photo: SelectedPhoto }) {
  const [percent, setPercent] = useState(8);

  useEffect(() => {
    // 실제 서버 응답이 오기 전까지 진행률을 점진적으로 올려 대기 체감을 줄인다.
    // 90%에서 멈추고, 실제 처리가 끝나면 상위 화면이 다음 단계로 넘어가면서 이 화면은 사라진다.
    const interval = setInterval(() => {
      setPercent((prev) => (prev >= 90 ? 90 : prev + Math.round(4 + Math.random() * 6)));
    }, 400);
    return () => clearInterval(interval);
  }, []);

  const currentStageIndex = Math.min(STAGES.length - 1, Math.floor((percent / 100) * STAGES.length));

  return (
    <View style={styles.screen}>
      <AppBar step="1 / 5" />
      <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>사진을 보호하고 있어요</Text>
          <Text style={styles.subtitle}>원본은 기기에 두고 보호 설정을 순서대로 적용합니다.</Text>
        </View>

        <View style={styles.photoPreview}>
          <Image source={{ uri: photo.uri }} style={styles.previewImage} resizeMode="cover" />
          <View style={styles.photoPreviewCopy}>
            <Text style={styles.photoPreviewTitle}>선택한 얼굴 사진</Text>
            <Text style={styles.photoPreviewHint}>
              {photo.fileName} · {photo.sizeLabel}
            </Text>
          </View>
          <View style={styles.uploadIconWrap}>
            <Image source={uploadIcon} style={styles.uploadIcon} resizeMode="contain" />
          </View>
        </View>

        <View style={styles.progressCard}>
          <View style={styles.progressHeader}>
            <Text style={styles.progressLabel}>보호 설정 적용 중</Text>
            <Text style={styles.progressPercent}>{percent}%</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${percent}%` }]} />
          </View>
          {STAGES.map((stage, index) =>
            index < currentStageIndex ? (
              <CheckRow key={stage} label={`${stage} 완료`} />
            ) : index === currentStageIndex ? (
              <View key={stage} style={styles.currentStepRow}>
                <Text style={styles.currentStepLabel}>{stage}</Text>
                <StatusChip label="진행 중" />
              </View>
            ) : null,
          )}
        </View>

        <InfoPanel title="앱을 닫아도 계속 처리돼요" body="완료되면 기기 알림으로 알려드립니다." />
      </ScrollView>

      <View style={styles.bottomCta}>
        <PrimaryButton label="보호 처리 중..." onPress={() => {}} disabled />
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
  photoPreview: {
    backgroundColor: colors.blue100,
    borderRadius: radii.lg,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    width: '100%',
  },
  previewImage: { width: 76, height: 76, borderRadius: radii.md },
  photoPreviewCopy: { flex: 1, gap: spacing.xs },
  photoPreviewTitle: { ...typography.bodyStrong, color: colors.text900 },
  photoPreviewHint: { ...typography.caption, color: colors.text500 },
  uploadIconWrap: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: colors.blue100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadIcon: { width: 20, height: 20 },
  progressCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
    width: '100%',
  },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  progressLabel: { ...typography.bodyStrong, color: colors.text900 },
  progressPercent: { ...typography.heading, color: colors.blue600 },
  progressTrack: { height: 8, backgroundColor: colors.blue100, borderRadius: 4, overflow: 'hidden', width: '100%' },
  progressFill: { height: 8, backgroundColor: colors.blue600, borderRadius: 4 },
  currentStepRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', height: 30 },
  currentStepLabel: { ...typography.label, color: colors.text700 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
