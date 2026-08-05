import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { PrimaryButton } from './Button';
import { colors, spacing, typography } from '../theme';

export function LoadingView() {
  return (
    <View style={styles.center}>
      <ActivityIndicator color={colors.blue600} />
    </View>
  );
}

export function ErrorView({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={styles.center}>
      <Text style={styles.message}>{message}</Text>
      <PrimaryButton label="다시 시도" onPress={onRetry} />
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, paddingHorizontal: spacing.xl },
  message: { ...typography.caption, color: colors.amber600, textAlign: 'center' },
});
