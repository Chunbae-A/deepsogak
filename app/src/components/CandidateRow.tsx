import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, radii, spacing, typography } from '../theme';

const thumbnail = require('../../assets/icons/thumbnail-blurred.png');

type CandidateRowProps = {
  candidate: string;
  similarity: string;
  risk: string;
  /** 실제 검색으로 발견된 출처 (예: "공개 SNS", "검색엔진") */
  sourceLabel?: string;
  /** 실제 검색으로 찾은 이미지 URL. 없으면 흐림 처리된 기본 썸네일을 보여준다. */
  thumbnailUrl?: string | null;
  excluded: boolean;
  onToggleExclude: () => void;
  /** Figma: 검토 목록에서 가장 위험도가 높은 후보를 파란 테두리로 강조 표시 */
  highlighted?: boolean;
  /** 후보 상세 분석 화면으로 이동 (제외 버튼 영역은 별도로 처리되어 여기 포함되지 않음) */
  onPress?: () => void;
};

export function CandidateRow({
  candidate,
  similarity,
  risk,
  sourceLabel,
  thumbnailUrl,
  excluded,
  onToggleExclude,
  highlighted,
  onPress,
}: CandidateRowProps) {
  return (
    <Pressable style={[styles.row, highlighted && styles.rowHighlighted]} onPress={onPress}>
      <Image source={thumbnailUrl ? { uri: thumbnailUrl } : thumbnail} style={styles.thumbnail} resizeMode="cover" />
      <View style={styles.info}>
        <Text style={styles.candidate}>{candidate}</Text>
        {sourceLabel ? <Text style={styles.source}>{sourceLabel}에서 발견</Text> : null}
        <Text style={styles.similarity}>{similarity}</Text>
        <Text style={styles.risk}>{risk}</Text>
      </View>
      <Pressable style={styles.excludeControl} onPress={onToggleExclude}>
        <View style={[styles.checkbox, excluded && styles.checkboxChecked]} />
        <Text style={styles.excludeLabel}>제외</Text>
      </Pressable>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
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
  rowHighlighted: { borderWidth: 2, borderColor: colors.blue600 },
  thumbnail: { width: 72, height: 72, borderRadius: radii.md },
  info: { flex: 1, gap: 2 },
  candidate: { ...typography.bodyStrong, color: colors.text900 },
  source: { ...typography.caption, color: colors.text500 },
  similarity: { ...typography.caption, color: colors.text700 },
  risk: { ...typography.caption, color: colors.blue600 },
  excludeControl: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    height: 32,
    width: 58,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
  },
  checkbox: { width: 14, height: 14, borderRadius: 3, borderWidth: 1, borderColor: colors.text500, backgroundColor: colors.white },
  checkboxChecked: { backgroundColor: colors.blue600, borderColor: colors.blue600 },
  excludeLabel: { ...typography.caption, color: colors.text700 },
});
