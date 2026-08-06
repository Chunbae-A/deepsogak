import { useCallback, useEffect, useState } from 'react';
import { Image, Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { InfoPanel } from '../components/InfoPanel';
import { PrimaryButton, SecondaryButton } from '../components/Button';
import { LoadingView, ErrorView } from '../components/ScreenStatus';
import { colors, radii, spacing, typography } from '../theme';
import { CandidateDetail, fetchCandidateDetail } from '../services/candidateApi';

const thumbnail = require('../../assets/icons/thumbnail-blurred.png');

export function CandidateDetailScreen({
  candidateId,
  onExclude,
  onCreateReport,
}: {
  candidateId: string;
  onExclude: () => void;
  onCreateReport: () => void;
}) {
  const [detail, setDetail] = useState<CandidateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setError(null);
    setDetail(null);
    fetchCandidateDetail(candidateId)
      .then((data) => {
        if (!cancelled) setDetail(data);
      })
      .catch(() => {
        if (!cancelled) setError('후보 상세 정보를 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, [candidateId]);

  useEffect(() => load(), [load]);

  const hasSourceLink = !!detail && detail.sourceUrl !== '-';
  const openSource = useCallback(() => {
    if (!detail || detail.sourceUrl === '-') return;
    const url = detail.sourceUrl.startsWith('http') ? detail.sourceUrl : `https://${detail.sourceUrl}`;
    Linking.openURL(url);
  }, [detail]);

  return (
    <View style={styles.screen}>
      <AppBar step="4 / 5" />
      {error ? (
        <ErrorView message={error} onRetry={load} />
      ) : !detail ? (
        <LoadingView />
      ) : (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>{detail.label}을 상세 분석했어요</Text>
              <Text style={styles.subtitle}>출처와 분석 신호를 확인한 뒤 다음 조치를 선택하세요.</Text>
            </View>

            <View style={styles.summaryCard}>
              <Image source={thumbnail} style={styles.thumbnail} resizeMode="cover" />
              <View style={styles.summaryInfo}>
                <Text style={styles.summaryTitle}>
                  {detail.label} · {detail.sourceLabel}
                </Text>
                <Text style={styles.summaryText}>얼굴 유사도 {detail.similarityPercent}%</Text>
                <Text style={styles.summaryRisk}>{detail.riskLabel}</Text>
              </View>
            </View>

            <View style={styles.sourceCard}>
              <Text style={styles.sourceTitle}>발견 출처</Text>
              <Pressable onPress={openSource} disabled={!hasSourceLink}>
                <Text style={[styles.sourceUrl, hasSourceLink && styles.sourceUrlLink]}>{detail.sourceUrl}</Text>
              </Pressable>
              <Text style={styles.sourceMeta}>
                게시 계정 {detail.sourceAccount} · {detail.foundAt}
              </Text>
              {hasSourceLink && (
                <Pressable onPress={openSource} style={styles.sourceLinkButton}>
                  <Text style={styles.sourceLinkButtonText}>발견된 페이지 열어보기 →</Text>
                </Pressable>
              )}
            </View>

            <View style={styles.metricsRow}>
              <View style={[styles.metricCard, styles.metricCardBlue]}>
                <Text style={styles.metricLabel}>얼굴 유사도</Text>
                <Text style={styles.metricValue}>{detail.similarityPercent}%</Text>
              </View>
              <View style={[styles.metricCard, styles.metricCardAmber]}>
                <Text style={styles.metricLabel}>딥페이크 위험도</Text>
                <Text style={styles.metricValueAmber}>{detail.riskLabel.replace('딥페이크 위험도 · ', '')}</Text>
              </View>
            </View>

            <View style={styles.signalsCard}>
              <Text style={styles.signalsTitle}>AI 분석 신호</Text>
              {detail.signals.map((signal) => (
                <Text key={signal} style={styles.signalItem}>
                  • {signal}
                </Text>
              ))}
            </View>

            <InfoPanel
              title="판단 기준 안내"
              body="얼굴 유사도는 딥페이크 확률이 아니며, AI 분석은 최종 판단을 돕는 참고 정보입니다."
            />
          </ScrollView>

          <View style={styles.bottomCta}>
            <SecondaryButton label="오탐으로 제외" onPress={onExclude} />
            <PrimaryButton label="이 후보로 신고자료 만들기" onPress={onCreateReport} />
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
    borderRadius: radii.md,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    width: '100%',
  },
  thumbnail: { width: 72, height: 72, borderRadius: radii.md },
  summaryInfo: { flex: 1, gap: 2 },
  summaryTitle: { ...typography.bodyStrong, color: colors.text900 },
  summaryText: { ...typography.caption, color: colors.text700 },
  summaryRisk: { ...typography.caption, color: colors.blue600 },
  sourceCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 4,
    width: '100%',
  },
  sourceTitle: { ...typography.label, color: colors.text900, fontWeight: '700' },
  sourceUrl: { ...typography.label, color: colors.text700 },
  sourceUrlLink: { color: colors.blue600, textDecorationLine: 'underline' },
  sourceMeta: { ...typography.caption, color: colors.text500 },
  sourceLinkButton: { marginTop: 2 },
  sourceLinkButtonText: { ...typography.label, color: colors.blue600, fontWeight: '700' },
  metricsRow: { flexDirection: 'row', gap: spacing.sm, width: '100%' },
  metricCard: { flex: 1, borderRadius: radii.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 3 },
  metricCardBlue: { backgroundColor: colors.blue100 },
  metricCardAmber: { backgroundColor: colors.amber100 },
  metricLabel: { ...typography.caption, color: colors.text700 },
  metricValue: { ...typography.heading, color: colors.text900 },
  metricValueAmber: { ...typography.heading, color: colors.amber600 },
  signalsCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 4,
    width: '100%',
  },
  signalsTitle: { ...typography.label, color: colors.text900, fontWeight: '700' },
  signalItem: { ...typography.caption, color: colors.text700 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg, gap: spacing.sm },
});
