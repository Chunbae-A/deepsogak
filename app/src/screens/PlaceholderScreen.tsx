import { StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { colors, spacing, typography } from '../theme';

// 이 탭의 실제 화면은 각 이슈(#3~#6)에서 구현한다. 지금은 하단 탭 이동만 검증하는 자리표시자다.
export function PlaceholderScreen({ step, title }: { step: string; title: string }) {
  return (
    <View style={styles.screen}>
      <AppBar step={step} />
      <View style={styles.body}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.caption}>이 화면은 다음 이슈에서 구현됩니다.</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingHorizontal: spacing.xl, paddingTop: spacing.lg, gap: spacing.md },
  body: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.xs },
  title: { ...typography.bodyStrong, color: colors.text900 },
  caption: { ...typography.caption, color: colors.text500 },
});
