import { useEffect, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { CheckRow } from '../components/CheckRow';
import { InfoPanel } from '../components/InfoPanel';
import { PrimaryButton, SecondaryButton } from '../components/Button';
import { colors, radii, spacing, typography } from '../theme';
import { ProtectionResult, fetchProtectionResult, saveProtectedPhoto } from '../services/protectionResultApi';

const thumbnail = require('../../assets/icons/thumbnail-blurred.png');
const protectedIcon = require('../../assets/icons/icon-protected.png');

export function ProtectionResultScreen({ onStartMonitoring }: { onStartMonitoring: () => void }) {
  // TODO(AI 모델 연동): result는 아직 목업이다. fetchProtectionResult가 실제
  // 처리 job 결과를 반환하게 되면 로딩/에러 처리를 추가한다.
  const [result, setResult] = useState<ProtectionResult | null>(null);

  useEffect(() => {
    fetchProtectionResult().then(setResult);
  }, []);

  if (!result) return null;

  return (
    <View style={styles.screen}>
      <AppBar step="2 / 5" />
      <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>보호사진이 준비됐어요</Text>
          <Text style={styles.subtitle}>원본은 그대로, 게시용 보호본만 안전하게 만들었습니다.</Text>
        </View>

        <StatusChip label="보호 생성 완료" />

        <View style={styles.compareCard}>
          <View style={styles.comparePane}>
            <Image source={thumbnail} style={styles.previewImage} resizeMode="cover" />
            <Text style={styles.paneLabel}>{result.originalLabel}</Text>
          </View>
          <View style={styles.comparePane}>
            <View style={styles.protectedPreviewWrap}>
              <Image source={thumbnail} style={styles.previewImage} resizeMode="cover" />
              <View style={styles.protectedBadge}>
                <Image source={protectedIcon} style={styles.protectedBadgeIcon} resizeMode="contain" />
              </View>
            </View>
            <Text style={styles.paneLabelProtected}>{result.protectedLabel}</Text>
          </View>
        </View>

        <View style={styles.resultsCard}>
          <Text style={styles.resultsTitle}>적용 결과</Text>
          {result.appliedChecks.map((label) => (
            <CheckRow key={label} label={label} />
          ))}
        </View>

        <InfoPanel
          title="중요한 한계"
          body="딥페이크 생성을 100% 차단하지는 않습니다. 게시 후 공개 노출 모니터링을 함께 사용하세요."
        />
      </ScrollView>

      <View style={styles.bottomCta}>
        <PrimaryButton label="보호사진 저장" onPress={() => saveProtectedPhoto()} />
        <SecondaryButton label="공개 노출 모니터링 시작" onPress={onStartMonitoring} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingHorizontal: spacing.xl, paddingTop: spacing.lg, gap: spacing.md },
  content: { width: '100%' },
  contentInner: { gap: spacing.md, paddingBottom: spacing.md },
  headerCopy: { gap: spacing.xs },
  title: { ...typography.title, color: colors.text900 },
  subtitle: { ...typography.caption, color: colors.text700 },
  compareCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    flexDirection: 'row',
    gap: spacing.sm,
    width: '100%',
  },
  comparePane: { flex: 1, gap: 6, alignItems: 'center' },
  previewImage: { width: '100%', height: 96, borderRadius: radii.md },
  protectedPreviewWrap: { width: '100%', height: 96 },
  protectedBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: colors.green100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  protectedBadgeIcon: { width: 14, height: 14 },
  paneLabel: { ...typography.label, color: colors.text700 },
  paneLabelProtected: { ...typography.label, color: colors.green600 },
  resultsCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.xs,
    width: '100%',
  },
  resultsTitle: { ...typography.bodyStrong, color: colors.text900 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg, gap: spacing.sm },
});
