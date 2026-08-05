import { Image, StyleSheet, Text, View } from 'react-native';
import { colors, radii, typography } from '../theme';

const checkIcon = require('../../assets/icons/icon-check.png');

export function CheckRow({ label }: { label: string }) {
  return (
    <View style={styles.row}>
      <View style={styles.iconWrap}>
        <Image source={checkIcon} style={styles.icon} resizeMode="contain" />
      </View>
      <Text style={styles.label}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { height: 30, flexDirection: 'row', alignItems: 'center', gap: 8, width: '100%' },
  iconWrap: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.green100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: { width: 12, height: 12 },
  label: { ...typography.caption, color: colors.text700, flex: 1 },
});
