import { StyleSheet, Text, View } from 'react-native';
import { colors, radii, typography } from '../theme';

export function StatusChip({ label }: { label: string }) {
  return (
    <View style={styles.chip}>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    backgroundColor: colors.green100,
    height: 28,
    borderRadius: radii.full,
    paddingHorizontal: 10,
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'flex-start',
  },
  label: { ...typography.label, color: colors.green600 },
});
