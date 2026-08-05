import { StyleSheet, Text, View } from 'react-native';
import { colors, typography } from '../theme';

type EvidenceRowProps = {
  field: string;
  value: string;
  /** Figma 05_Incident Report에서는 값 전체가 blue-600(link 톤)으로 표시된다 */
  tone?: 'default' | 'link';
};

export function EvidenceRow({ field, value, tone = 'default' }: EvidenceRowProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.field}>{field}</Text>
      <Text style={[styles.value, tone === 'link' && styles.valueLink]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { height: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', width: '100%' },
  field: { ...typography.caption, color: colors.text500, width: 120 },
  value: { ...typography.label, color: colors.text900, textAlign: 'right', flex: 1 },
  valueLink: { color: colors.blue600 },
});
