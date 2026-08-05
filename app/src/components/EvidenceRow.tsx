import { StyleSheet, Text, View } from 'react-native';
import { colors, typography } from '../theme';

export function EvidenceRow({ field, value }: { field: string; value: string }) {
  return (
    <View style={styles.row}>
      <Text style={styles.field}>{field}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { height: 34, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', width: '100%' },
  field: { ...typography.caption, color: colors.text500, width: 120 },
  value: { ...typography.label, color: colors.text900, textAlign: 'right', flex: 1 },
});
