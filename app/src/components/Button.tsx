import { Pressable, StyleSheet, Text } from 'react-native';
import { colors, radii, typography } from '../theme';

type ButtonProps = {
  label: string;
  onPress?: () => void;
  disabled?: boolean;
};

export function PrimaryButton({ label, onPress, disabled }: ButtonProps) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [styles.primary, disabled && styles.disabled, pressed && styles.pressed]}
    >
      <Text style={styles.primaryLabel}>{label}</Text>
    </Pressable>
  );
}

export function SecondaryButton({ label, onPress, disabled }: ButtonProps) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.secondary, pressed && styles.pressed]}>
      <Text style={styles.secondaryLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  primary: {
    backgroundColor: colors.blue600,
    height: 48,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
  },
  primaryLabel: { ...typography.button, color: colors.white },
  secondary: {
    backgroundColor: colors.white,
    height: 48,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.blue600,
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
  },
  secondaryLabel: { ...typography.button, color: colors.blue600 },
  disabled: { opacity: 0.5 },
  pressed: { opacity: 0.85 },
});
