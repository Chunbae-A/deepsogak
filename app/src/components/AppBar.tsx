import { Image, StyleSheet, Text, View } from 'react-native';
import { colors, radii, spacing, typography } from '../theme';

const shieldCheckIcon = require('../../assets/icons/icon-shield-check.png');

type AppBarProps = {
  step: string; // e.g. "3 / 5"
};

export function AppBar({ step }: AppBarProps) {
  return (
    <View style={styles.container}>
      <View style={styles.brand}>
        <View style={styles.logo}>
          <Image source={shieldCheckIcon} style={styles.logoIcon} resizeMode="contain" />
        </View>
        <Text style={styles.title}>딥소각</Text>
      </View>
      <Text style={styles.step}>{step}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.white,
    height: 56,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
  },
  brand: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  logo: {
    width: 32,
    height: 32,
    borderRadius: radii.full,
    backgroundColor: colors.blue100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  logoIcon: { width: 18, height: 18 },
  title: { ...typography.bodyStrong, color: colors.navy900 },
  step: { ...typography.label, color: colors.blue600 },
});
