import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { InfoPanel } from '../components/InfoPanel';
import { CandidateRow } from '../components/CandidateRow';
import { PrimaryButton } from '../components/Button';
import { LoadingView, ErrorView } from '../components/ScreenStatus';
import { CandidateDetailScreen } from './CandidateDetailScreen';
import { colors, spacing, typography } from '../theme';
import { Candidate, RiskLevel, fetchCandidates, confirmCandidateSelection } from '../services/candidateApi';

type FilterKey = 'all' | RiskLevel;

const FILTER_LABELS: Record<RiskLevel, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
  'exclude-recommended': '제외',
};

export function CandidateReviewScreen({ onConfirmSelection }: { onConfirmSelection: () => void }) {
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>('all');
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setError(null);
    setCandidates(null);
    fetchCandidates()
      .then((data) => {
        if (!cancelled) setCandidates(data);
      })
      .catch(() => {
        if (!cancelled) setError('후보 목록을 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const toggleExclude = (id: string) => {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirm = (onlyId?: string) => {
    if (!candidates) return;
    const keepIds = onlyId ? [onlyId] : candidates.filter((c) => !excludedIds.has(c.id)).map((c) => c.id);
    confirmCandidateSelection(keepIds).catch(() => {});
    onConfirmSelection();
  };

  if (selectedCandidateId) {
    return (
      <CandidateDetailScreen
        candidateId={selectedCandidateId}
        onExclude={() => {
          toggleExclude(selectedCandidateId);
          setSelectedCandidateId(null);
        }}
        onCreateReport={() => handleConfirm(selectedCandidateId)}
      />
    );
  }

  return (
    <View style={styles.screen}>
      <AppBar step="4 / 5" />
      {error ? (
        <ErrorView message={error} onRetry={load} />
      ) : !candidates ? (
        <LoadingView />
      ) : (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>의심 후보를 검토해 주세요</Text>
              <Text style={styles.subtitle}>유사도와 합성 위험 신호를 분리해 확인합니다.</Text>
            </View>

            <StatusChip label={`검토 후보 ${candidates.length}건`} />

            <View style={styles.filterChips}>
              <FilterChip
                label={`전체 ${candidates.length}`}
                active={filter === 'all'}
                tone="neutral"
                onPress={() => setFilter('all')}
              />
              {(Object.keys(FILTER_LABELS) as RiskLevel[])
                .filter((level) => candidates.some((c) => c.riskLevel === level))
                .map((level) => (
                  <FilterChip
                    key={level}
                    label={`${FILTER_LABELS[level]} ${candidates.filter((c) => c.riskLevel === level).length}`}
                    active={filter === level}
                    tone={level === 'high' ? 'amber' : level === 'low' ? 'blue' : 'neutral'}
                    onPress={() => setFilter(level)}
                  />
                ))}
            </View>

            <View style={styles.list}>
              {candidates
                .filter((c) => filter === 'all' || c.riskLevel === filter)
                .map((c) => (
                  <CandidateRow
                    key={c.id}
                    candidate={c.label}
                    similarity={`얼굴 유사도 ${c.similarityPercent}%`}
                    risk={c.riskLabel}
                    sourceLabel={c.sourceLabel}
                    thumbnailUrl={c.thumbnailUrl}
                    excluded={excludedIds.has(c.id)}
                    onToggleExclude={() => toggleExclude(c.id)}
                    highlighted={c.id === candidates[0]?.id}
                    onPress={() => setSelectedCandidateId(c.id)}
                  />
                ))}
            </View>

            <InfoPanel
              title="얼굴 유사도는 딥페이크 확률이 아닙니다"
              body="유사도는 동일 인물 가능성만 나타냅니다. 오탐으로 판단되면 각 후보의 '제외'를 선택하세요."
            />
          </ScrollView>

          <View style={styles.bottomCta}>
            <PrimaryButton label="선택 후보 상세 분석" onPress={() => handleConfirm()} />
          </View>
        </>
      )}
    </View>
  );
}

type FilterChipTone = 'neutral' | 'amber' | 'blue';

function FilterChip({
  label,
  active,
  tone,
  onPress,
}: {
  label: string;
  active: boolean;
  tone: FilterChipTone;
  onPress: () => void;
}) {
  const toneStyle = tone === 'amber' ? styles.chipAmber : tone === 'blue' ? styles.chipBlue : styles.chipNeutral;
  const toneTextStyle = tone === 'amber' ? styles.chipAmberText : tone === 'blue' ? styles.chipBlueText : styles.chipNeutralText;
  return (
    <Pressable style={[styles.chip, active ? styles.chipActive : toneStyle]} onPress={onPress}>
      <Text style={active ? styles.chipActiveText : toneTextStyle}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingHorizontal: spacing.xl, paddingTop: spacing.lg, gap: spacing.md },
  content: { flex: 1, width: '100%' },
  contentInner: { gap: spacing.md, paddingBottom: spacing.md },
  headerCopy: { gap: spacing.xs },
  title: { ...typography.title, color: colors.text900 },
  subtitle: { ...typography.caption, color: colors.text700 },
  filterChips: { flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' },
  chip: { height: 28, borderRadius: 999, paddingHorizontal: 10, alignItems: 'center', justifyContent: 'center' },
  chipActive: { backgroundColor: colors.navy900 },
  chipActiveText: { ...typography.label, color: colors.white },
  chipNeutral: { backgroundColor: colors.surface },
  chipNeutralText: { ...typography.label, color: colors.text700 },
  chipAmber: { backgroundColor: colors.amber100 },
  chipAmberText: { ...typography.label, color: colors.amber600 },
  chipBlue: { backgroundColor: colors.blue100 },
  chipBlueText: { ...typography.label, color: colors.blue600 },
  list: { gap: spacing.sm, width: '100%' },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
