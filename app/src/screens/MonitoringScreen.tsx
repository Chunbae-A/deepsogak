import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { InfoPanel } from '../components/InfoPanel';
import { PrimaryButton } from '../components/Button';
import { LoadingView, ErrorView } from '../components/ScreenStatus';
import { colors, radii, spacing, typography } from '../theme';
import { fetchMonitoringSummary, MonitoringSummary, submitManualReport } from '../services/monitoringApi';

const addIcon = require('../../assets/icons/icon-add.png');

// Figma의 축약 칩 라벨(검색·SNS·웹)과 서버 응답 라벨을 매핑한다.
const SHORT_SOURCE_LABELS: Record<string, string> = {
  검색엔진: '검색',
  '공개 SNS': 'SNS',
  '기타 웹사이트': '웹',
};

export function MonitoringScreen({ onConfirmCandidates }: { onConfirmCandidates: () => void }) {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [reportUrl, setReportUrl] = useState('');
  const [isSubmittingReport, setIsSubmittingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportDone, setReportDone] = useState(false);

  const load = useCallback(() => {
    let cancelled = false;
    setError(null);
    setSummary(null);
    fetchMonitoringSummary()
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch(() => {
        if (!cancelled) setError('모니터링 결과를 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const handleToggleReport = () => {
    setReportError(null);
    setReportDone(false);
    setIsReportOpen((prev) => !prev);
  };

  const handleSubmitReport = async () => {
    setIsSubmittingReport(true);
    setReportError(null);
    try {
      await submitManualReport(reportUrl);
      setReportUrl('');
      setReportDone(true);
      load();
    } catch (e) {
      setReportError(e instanceof Error ? e.message : '제보 등록에 실패했습니다.');
    } finally {
      setIsSubmittingReport(false);
    }
  };

  return (
    <View style={styles.screen}>
      <AppBar step="3 / 5" />
      {error ? (
        <ErrorView message={error} onRetry={load} />
      ) : !summary ? (
        <LoadingView />
      ) : (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>공개 노출을 확인하고 있어요</Text>
              <Text style={styles.subtitle}>임의의 점수 대신 실제 공개 탐색 결과만 보여드려요.</Text>
            </View>

            <StatusChip label={`최근 확인 · ${summary.lastCheckedAt}`} />

            <View style={styles.guideChips}>
              <View style={[styles.chip, styles.chipActive]}>
                <Text style={styles.chipActiveText}>전체 {summary.totalCandidates}</Text>
              </View>
              {summary.sources.map((source) => (
                <View key={source.label} style={styles.chip}>
                  <Text style={styles.chipText}>
                    {SHORT_SOURCE_LABELS[source.label] ?? source.label} {source.count.replace('건', '')}
                  </Text>
                </View>
              ))}
            </View>

            <View style={styles.resultCard}>
              <Text style={styles.resultLabel}>공개 탐색 결과</Text>
              <Text style={styles.resultCount}>공개 노출 후보 {summary.totalCandidates}건</Text>
              {summary.sources.map((r) => (
                <View key={r.label} style={styles.resultRow}>
                  <Text style={styles.resultRowLabel}>{r.label}</Text>
                  <Text style={styles.resultRowValue}>{r.count}</Text>
                </View>
              ))}
            </View>

            <InfoPanel title="확인하는 공개 영역" body="검색엔진에 색인되거나 접근이 허용된 공개 영역만 확인합니다." />
            <InfoPanel
              tone="warning"
              title="자동 탐색하지 않는 영역"
              body="비공개 계정과 암호화 메신저는 자동 탐색하지 않습니다."
            />

            <Pressable style={styles.directReport} onPress={handleToggleReport}>
              <View style={styles.directReportCopy}>
                <Text style={styles.directReportTitle}>URL·캡처·파일 직접 제보</Text>
                <Text style={styles.directReportBody}>제보 자료도 분석 후보에 포함할 수 있어요.</Text>
              </View>
              <View style={styles.addButton}>
                <Image source={addIcon} style={styles.addIcon} resizeMode="contain" />
              </View>
            </Pressable>

            {isReportOpen && (
              <View style={styles.reportForm}>
                <TextInput
                  style={styles.reportInput}
                  placeholder="제보할 게시물 URL을 입력하세요"
                  placeholderTextColor={colors.text500}
                  value={reportUrl}
                  onChangeText={setReportUrl}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                {reportError && <Text style={styles.reportError}>{reportError}</Text>}
                {reportDone && !reportError && <Text style={styles.reportSuccess}>제보가 등록됐습니다.</Text>}
                <PrimaryButton
                  label={isSubmittingReport ? '등록 중...' : '제보하기'}
                  onPress={handleSubmitReport}
                  disabled={isSubmittingReport || !reportUrl.trim()}
                />
              </View>
            )}
          </ScrollView>

          <View style={styles.bottomCta}>
            <PrimaryButton label={`후보 ${summary.totalCandidates}건 확인`} onPress={onConfirmCandidates} />
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
  guideChips: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  chip: { height: 28, borderRadius: radii.full, paddingHorizontal: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.blue100 },
  chipText: { ...typography.label, color: colors.blue600 },
  chipActive: { backgroundColor: colors.navy900 },
  chipActiveText: { ...typography.label, color: colors.white },
  resultCard: { backgroundColor: colors.navy900, borderRadius: radii.lg, paddingHorizontal: spacing.lg, paddingVertical: 14, gap: spacing.xs },
  resultLabel: { ...typography.caption, color: colors.blue100 },
  resultCount: { ...typography.display, color: colors.white, marginBottom: spacing.xs },
  resultRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', height: 34 },
  resultRowLabel: { ...typography.caption, color: colors.blue100 },
  resultRowValue: { ...typography.label, color: colors.white },
  directReport: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingLeft: spacing.lg,
    paddingRight: 14,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  directReportCopy: { flex: 1, gap: 2 },
  directReportTitle: { ...typography.bodyStrong, color: colors.text900 },
  directReportBody: { ...typography.caption, color: colors.text700 },
  addButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.blue100, alignItems: 'center', justifyContent: 'center' },
  addIcon: { width: 18, height: 18 },
  reportForm: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  reportInput: {
    height: 40,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    color: colors.text900,
  },
  reportError: { ...typography.caption, color: colors.amber600 },
  reportSuccess: { ...typography.caption, color: colors.green600 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
