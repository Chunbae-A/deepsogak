import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { InfoPanel } from '../components/InfoPanel';
import { CandidateRow } from '../components/CandidateRow';
import { PrimaryButton } from '../components/Button';
import { colors, spacing, typography } from '../theme';
import { Candidate, fetchCandidates, confirmCandidateSelection } from '../services/candidateApi';

export function CandidateReviewScreen({ onConfirmSelection }: { onConfirmSelection: () => void }) {
  // TODO(AI 모델 연동): candidates는 아직 목업이다. fetchCandidates가 실제
  // ArcFace·EfficientNet-B4 결과를 반환하게 되면 로딩/에러 처리를 추가한다.
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchCandidates().then(setCandidates);
  }, []);

  if (!candidates) return null;

  const toggleExclude = (id: string) => {
    setExcludedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirm = () => {
    const keepIds = candidates.filter((c) => !excludedIds.has(c.id)).map((c) => c.id);
    confirmCandidateSelection(keepIds);
    onConfirmSelection();
  };

  return (
    <View style={styles.screen}>
      <AppBar step="4 / 5" />
      <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>의심 후보를 검토해 주세요</Text>
          <Text style={styles.subtitle}>유사도와 합성 위험 신호를 분리해 확인합니다.</Text>
        </View>

        <StatusChip label={`검토 후보 ${candidates.length}건`} />

        <View style={styles.list}>
          {candidates.map((c, index) => (
            <CandidateRow
              key={c.id}
              candidate={c.label}
              similarity={`얼굴 유사도 ${c.similarityPercent}%`}
              risk={c.riskLabel}
              excluded={excludedIds.has(c.id)}
              onToggleExclude={() => toggleExclude(c.id)}
              highlighted={index === 0}
            />
          ))}
        </View>

        <InfoPanel
          title="얼굴 유사도는 딥페이크 확률이 아닙니다"
          body="유사도는 동일 인물 가능성만 나타냅니다. 오탐으로 판단되면 각 후보의 '제외'를 선택하세요."
        />
      </ScrollView>

      <View style={styles.bottomCta}>
        <PrimaryButton label="선택 후보 상세 분석" onPress={handleConfirm} />
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
  list: { gap: spacing.sm, width: '100%' },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
