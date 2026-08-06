import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { PrimaryButton } from '../components/Button';
import { LoadingView, ErrorView } from '../components/ScreenStatus';
import { colors, radii, spacing, typography } from '../theme';
import { HomeSummary, fetchHomeSummary } from '../services/homeApi';

const arrowIcon = require('../../assets/icons/icon-arrow.png');

export function HomeScreen({
  onStartProtection,
  onOpenMonitoring,
}: {
  onStartProtection: () => void;
  onOpenMonitoring: () => void;
}) {
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setError(null);
    setSummary(null);
    fetchHomeSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch(() => {
        if (!cancelled) setError('홈 요약 정보를 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  return (
    <View style={styles.screen}>
      <AppBar step="홈" />
      {error ? (
        <ErrorView message={error} onRetry={load} />
      ) : !summary ? (
        <LoadingView />
      ) : (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>오늘도 사진을 안전하게</Text>
              <Text style={styles.subtitle}>게시 전 보호부터 공개 노출 대응까지 한곳에서 관리하세요.</Text>
            </View>

            <View style={styles.summaryCard}>
              <Text style={styles.summaryTitle}>오늘의 안전 상태</Text>
              <View style={styles.summaryMetrics}>
                <View style={styles.metric}>
                  <Text style={[styles.metricLabel, styles.metricGreen]}>보호사진</Text>
                  <Text style={[styles.metricValue, styles.metricGreen]}>{summary.protectedCount}장</Text>
                </View>
                <View style={styles.metric}>
                  <Text style={[styles.metricLabel, styles.metricBlue]}>노출 후보</Text>
                  <Text style={[styles.metricValue, styles.metricBlue]}>{summary.candidateCount}건</Text>
                </View>
                <View style={styles.metric}>
                  <Text style={styles.metricLabel}>신고자료</Text>
                  <Text style={styles.metricValue}>{summary.reportCount}건</Text>
                </View>
              </View>
            </View>

            <Pressable style={styles.quickAction} onPress={onStartProtection}>
              <View>
                <Text style={styles.quickActionTitle}>게시할 사진 보호하기</Text>
                <Text style={styles.quickActionBody}>EXIF 제거·딥백신·C2PA·해시 생성</Text>
              </View>
              <Image source={arrowIcon} style={styles.arrowIcon} resizeMode="contain" />
            </Pressable>

            <Pressable style={styles.activityCard} onPress={onOpenMonitoring}>
              <View>
                <Text style={styles.activityTitle}>공개 노출 모니터링</Text>
                <Text style={styles.activityBody}>
                  후보 {summary.candidateCount}건 · 최근 확인 {summary.lastCheckedAt}
                </Text>
              </View>
              <StatusChip label={summary.candidateCount > 0 ? '확인 필요' : '이상 없음'} />
            </Pressable>
          </ScrollView>

          <View style={styles.bottomCta}>
            <Text style={styles.bottomHint}>최근 공개 영역 확인 · {summary.lastCheckedAt}</Text>
            <PrimaryButton label="새 보호사진 만들기" onPress={onStartProtection} />
          </View>
        </>
      )}
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
  summaryCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.md,
    width: '100%',
  },
  summaryTitle: { ...typography.bodyStrong, color: colors.text900 },
  summaryMetrics: { flexDirection: 'row', gap: spacing.md },
  metric: { flex: 1, height: 64, borderRadius: radii.md, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', gap: 2 },
  metricLabel: { ...typography.label, color: colors.text700 },
  metricValue: { ...typography.label, color: colors.text700 },
  metricGreen: { color: colors.green600 },
  metricBlue: { color: colors.blue600 },
  quickAction: {
    backgroundColor: colors.blue100,
    borderRadius: radii.lg,
    height: 96,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
  },
  quickActionTitle: { ...typography.bodyStrong, color: colors.text900, fontSize: 16 },
  quickActionBody: { ...typography.caption, color: colors.text700, marginTop: 4 },
  arrowIcon: { width: 20, height: 20 },
  activityCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    height: 88,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
  },
  activityTitle: { ...typography.bodyStrong, color: colors.text900 },
  activityBody: { ...typography.caption, color: colors.text700, marginTop: 4 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg, gap: spacing.sm },
  bottomHint: { ...typography.caption, color: colors.text500, textAlign: 'center' },
});
