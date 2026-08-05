import { StyleSheet, Text, View } from 'react-native';
import { colors, radii, spacing, typography } from '../theme';

type InfoPanelProps = {
  title: string;
  body: string;
  tone?: 'info' | 'warning';
};

export function InfoPanel({ title, body, tone = 'info' }: InfoPanelProps) {
  const isWarning = tone === 'warning';
  return (
    <View style={[styles.panel, { backgroundColor: isWarning ? colors.amber100 : colors.blue100 }]}>
      <Text style={[styles.title, { color: isWarning ? colors.amber600 : colors.navy900 }]}>{title}</Text>
      <Text style={styles.body}>{body}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    borderRadius: radii.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    gap: spacing.xs,
    width: '100%',
  },
  title: { ...typography.bodyStrong },
  body: { ...typography.caption, color: colors.text700 },
});
