import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { InfoPanel } from '../components/InfoPanel';
import { PrimaryButton } from '../components/Button';
import { ErrorView } from '../components/ScreenStatus';
import { colors, radii, spacing, typography } from '../theme';
import {
  fetchMonitoringScanStatus,
  fetchMonitoringSummary,
  MonitoringScanCreated,
  MonitoringScanStatus,
  MonitoringScanStatusValue,
  MonitoringSummary,
  startMonitoringScan,
  submitManualReport,
} from '../services/monitoringApi';

const addIcon = require('../../assets/icons/icon-add.png');

const SHORT_SOURCE_LABELS: Record<string, string> = {
  검색엔진: '검색',
  '공개 SNS': 'SNS',
  '기타 웹사이트': '웹',
};

const STATUS_LABELS: Record<MonitoringScanStatusValue, string> = {
  queued: '작업 시작 대기',
  searching: '공개 후보 검색 중',
  identity_filtering: '본인 얼굴 후보 확인 중',
  deepfake_analyzing: '딥페이크 신호 분석 중',
  completed: '분석 완료',
  partial_failed: '일부 후보 분석 완료',
  failed: '분석 실패',
};

const FINAL_STATUSES = new Set<MonitoringScanStatusValue>(['completed', 'partial_failed', 'failed']);

type MonitoringScreenProps = {
  referenceJobId: string | null;
  onConfirmCandidates: (scanId: string) => void;
};

export function MonitoringScreen({ referenceJobId, onConfirmCandidates }: MonitoringScreenProps) {
  const [queryText, setQueryText] = useState('');
  const [hasSearchConsent, setHasSearchConsent] = useState(false);
  const [scan, setScan] = useState<MonitoringScanCreated | null>(null);
  const [scanStatus, setScanStatus] = useState<MonitoringScanStatus | null>(null);
  const [summary, setSummary] = useState<MonitoringSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [reportUrl, setReportUrl] = useState('');
  const [isSubmittingReport, setIsSubmittingReport] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportDone, setReportDone] = useState(false);

  const handleStart = useCallback(async () => {
    if (!referenceJobId) {
      setError('먼저 보호 탭에서 본인 얼굴 사진을 등록해 주세요.');
      return;
    }
    setIsStarting(true);
    setError(null);
    setSummary(null);
    setScanStatus(null);
    try {
      const created = await startMonitoringScan({
        queryText: queryText.trim(),
        webMonitoringConsent: hasSearchConsent,
        referenceJobIds: [referenceJobId],
        maximumResults: 5,
      });
      setScan(created);
    } catch (e) {
      setError(e instanceof Error ? e.message : '공개 노출 확인을 시작하지 못했습니다.');
    } finally {
      setIsStarting(false);
    }
  }, [hasSearchConsent, queryText, referenceJobId]);

  useEffect(() => {
    if (!scan) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const current = await fetchMonitoringScanStatus(scan.scanId);
        if (cancelled) return;
        setScanStatus(current);
        if (current.status === 'failed') {
          setError(`분석을 완료하지 못했습니다${current.errorCode ? ` (${current.errorCode})` : ''}.`);
          return;
        }
        if (FINAL_STATUSES.has(current.status)) {
          const nextSummary = await fetchMonitoringSummary(scan.scanId);
          if (!cancelled) setSummary(nextSummary);
          return;
        }
        timer = setTimeout(poll, 1200);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '모니터링 상태를 확인하지 못했습니다.');
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [scan]);

  const handleSubmitReport = async () => {
    if (!scan) return;
    setIsSubmittingReport(true);
    setReportError(null);
    try {
      await submitManualReport(reportUrl);
      setReportUrl('');
      setReportDone(true);
      setSummary(await fetchMonitoringSummary(scan.scanId));
    } catch (e) {
      setReportError(e instanceof Error ? e.message : '제보 등록에 실패했습니다.');
    } finally {
      setIsSubmittingReport(false);
    }
  };

  const resetScan = () => {
    setScan(null);
    setScanStatus(null);
    setSummary(null);
    setError(null);
  };

  return (
    <View style={styles.screen}>
      <AppBar step="3 / 5" />
      {!scan ? (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>공개 노출 확인을 시작해요</Text>
              <Text style={styles.subtitle}>검색어로 공개 후보를 찾은 뒤 본인 얼굴과 딥페이크 신호를 순서대로 확인합니다.</Text>
            </View>

            <View style={styles.startCard}>
              <Text style={styles.inputLabel}>공개 검색어</Text>
              <TextInput
                style={styles.searchInput}
                placeholder="예: 이름, 활동명 또는 공개 게시물 키워드"
                placeholderTextColor={colors.text500}
                value={queryText}
                onChangeText={setQueryText}
                autoCorrect={false}
              />
              <Text style={styles.helperText}>사진은 검색엔진에 보내지 않고, 입력한 검색어만 로컬 SearXNG에 전달합니다.</Text>
            </View>

            <Pressable style={styles.consentRow} onPress={() => setHasSearchConsent((value) => !value)}>
              <View style={[styles.checkbox, hasSearchConsent && styles.checkboxChecked]}>
                {hasSearchConsent && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.consentText}>공개 웹에서 위 검색어로 후보를 찾는 데 동의합니다.</Text>
            </Pressable>

            {!referenceJobId && (
              <InfoPanel tone="warning" title="등록 사진이 필요해요" body="보호 탭에서 본인 사진을 먼저 올린 뒤 다시 시작해 주세요." />
            )}
            <InfoPanel title="얼굴 역검색은 아닙니다" body="SearXNG이 키워드 후보를 찾고, ArcFace가 각 후보가 본인인지 후속 확인합니다." />
            <InfoPanel tone="warning" title="자동 판정·신고하지 않아요" body="ONNX 모델 점수는 연구용 원점수이며 의심 후보는 사람이 원문을 확인해야 합니다." />
            {error && <Text style={styles.formError}>{error}</Text>}
          </ScrollView>
          <View style={styles.bottomCta}>
            <PrimaryButton
              label={isStarting ? '확인 시작 중...' : '공개 노출 확인 시작'}
              onPress={handleStart}
              disabled={isStarting || !queryText.trim() || !hasSearchConsent || !referenceJobId}
            />
          </View>
        </>
      ) : error && !summary ? (
        <ErrorView message={error} onRetry={resetScan} />
      ) : summary ? (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>공개 노출 후보를 찾았어요</Text>
              <Text style={styles.subtitle}>후보별 얼굴 유사도와 조작 의심 신호는 다음 화면에서 따로 확인합니다.</Text>
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
              <Text style={styles.resultLabel}>실제 공개 탐색 결과</Text>
              <Text style={styles.resultCount}>공개 노출 후보 {summary.totalCandidates}건</Text>
              {summary.sources.map((source) => (
                <View key={source.label} style={styles.resultRow}>
                  <Text style={styles.resultRowLabel}>{source.label}</Text>
                  <Text style={styles.resultRowValue}>{source.count}</Text>
                </View>
              ))}
            </View>

            <InfoPanel title="확인하는 공개 영역" body="검색엔진에 색인되거나 접근이 허용된 공개 영역만 확인합니다." />
            <InfoPanel tone="warning" title="점수는 확률이 아닙니다" body="후보 화면의 얼굴·딥페이크 수치는 모델 원점수이며 최종 판단은 사람이 합니다." />

            <Pressable style={styles.directReport} onPress={() => setIsReportOpen((value) => !value)}>
              <View style={styles.directReportCopy}>
                <Text style={styles.directReportTitle}>URL 직접 제보</Text>
                <Text style={styles.directReportBody}>자동 검색에서 빠진 공개 게시물도 검토 목록에 추가할 수 있어요.</Text>
              </View>
              <View style={styles.addButton}>
                <Image source={addIcon} style={styles.addIcon} resizeMode="contain" />
              </View>
            </Pressable>

            {isReportOpen && (
              <View style={styles.reportForm}>
                <TextInput
                  style={styles.searchInput}
                  placeholder="제보할 게시물 URL을 입력하세요"
                  placeholderTextColor={colors.text500}
                  value={reportUrl}
                  onChangeText={setReportUrl}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                {reportError && <Text style={styles.formError}>{reportError}</Text>}
                {reportDone && !reportError && <Text style={styles.reportSuccess}>제보가 검토 목록에 추가됐습니다.</Text>}
                <PrimaryButton
                  label={isSubmittingReport ? '등록 중...' : '제보하기'}
                  onPress={handleSubmitReport}
                  disabled={isSubmittingReport || !reportUrl.trim()}
                />
              </View>
            )}
          </ScrollView>
          <View style={styles.bottomCta}>
            <PrimaryButton
              label={`후보 ${summary.totalCandidates}건 확인`}
              onPress={() => onConfirmCandidates(scan.scanId)}
              disabled={summary.totalCandidates === 0}
            />
          </View>
        </>
      ) : (
        <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
          <View style={styles.headerCopy}>
            <Text style={styles.title}>공개 노출을 확인하고 있어요</Text>
            <Text style={styles.subtitle}>검색 → 본인 얼굴 확인 → 딥페이크 분석 순서로 처리합니다.</Text>
          </View>
          <StatusChip label={STATUS_LABELS[scanStatus?.status ?? scan.status]} />
          <View style={styles.progressCard}>
            <Text style={styles.progressValue}>{scanStatus?.progressPercent ?? 0}%</Text>
            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${scanStatus?.progressPercent ?? 0}%` }]} />
            </View>
            <Text style={styles.progressText}>검색 후보 {scanStatus?.searchedCandidateCount ?? 0}건 · 얼굴 분석 {scanStatus?.analyzedCandidateCount ?? 0}건</Text>
          </View>
          <InfoPanel title="화면을 닫지 않아도 돼요" body="서버가 작업 ID로 진행 상태를 관리합니다. 현재 데모는 서버 재시작 시 작업이 사라집니다." />
        </ScrollView>
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
  startCard: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, padding: spacing.md, gap: spacing.sm },
  inputLabel: { ...typography.bodyStrong, color: colors.text900 },
  searchInput: { height: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, paddingHorizontal: spacing.md, color: colors.text900, backgroundColor: colors.white },
  helperText: { ...typography.caption, color: colors.text500 },
  consentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, padding: spacing.md },
  checkbox: { width: 22, height: 22, borderWidth: 1, borderColor: colors.text500, borderRadius: 5, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.white },
  checkboxChecked: { backgroundColor: colors.blue600, borderColor: colors.blue600 },
  checkmark: { color: colors.white, fontWeight: '700' },
  consentText: { ...typography.label, color: colors.text700, flex: 1 },
  formError: { ...typography.caption, color: colors.amber600 },
  reportSuccess: { ...typography.caption, color: colors.green600 },
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
  progressCard: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.lg, padding: spacing.lg, gap: spacing.md },
  progressValue: { ...typography.display, color: colors.blue600 },
  progressTrack: { height: 10, backgroundColor: colors.blue100, borderRadius: radii.full, overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colors.blue600, borderRadius: radii.full },
  progressText: { ...typography.caption, color: colors.text700 },
  directReport: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, paddingLeft: spacing.lg, paddingRight: 14, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  directReportCopy: { flex: 1, gap: 2 },
  directReportTitle: { ...typography.bodyStrong, color: colors.text900 },
  directReportBody: { ...typography.caption, color: colors.text700 },
  addButton: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.blue100, alignItems: 'center', justifyContent: 'center' },
  addIcon: { width: 18, height: 18 },
  reportForm: { backgroundColor: colors.white, borderWidth: 1, borderColor: colors.border, borderRadius: radii.md, padding: spacing.md, gap: spacing.sm },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
