import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, radii, spacing, typography } from '../theme';

export type TabKey = 'Protection' | 'Monitoring' | 'Report';

const icons: Record<TabKey, { active: ReturnType<typeof require>; inactive: ReturnType<typeof require> }> = {
  Protection: {
    active: require('../../assets/icons/nav-protection-active.png'),
    inactive: require('../../assets/icons/nav-protection-inactive.png'),
  },
  Monitoring: {
    active: require('../../assets/icons/nav-monitoring-active.png'),
    inactive: require('../../assets/icons/nav-monitoring-inactive.png'),
  },
  Report: {
    active: require('../../assets/icons/nav-report-active.png'),
    inactive: require('../../assets/icons/nav-report-inactive.png'),
  },
};

const tabs: { key: TabKey; label: string }[] = [
  { key: 'Protection', label: '보호' },
  { key: 'Monitoring', label: '모니터링' },
  { key: 'Report', label: '신고자료' },
];

type BottomNavProps = {
  active: TabKey;
  onSelect: (key: TabKey) => void;
};

export function BottomNav({ active, onSelect }: BottomNavProps) {
  return (
    <View style={styles.container}>
      {tabs.map(({ key, label }) => {
        const isActive = key === active;
        return (
          <Pressable key={key} style={[styles.item, isActive && styles.itemActive]} onPress={() => onSelect(key)}>
            <Image source={isActive ? icons[key].active : icons[key].inactive} style={styles.icon} resizeMode="contain" />
            <Text style={[styles.label, isActive && styles.labelActive]}>{label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    height: 64,
    padding: spacing.xs,
    flexDirection: 'row',
    gap: spacing.xs,
    width: '100%',
  },
  item: {
    flex: 1,
    height: 56,
    borderRadius: radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  itemActive: { backgroundColor: colors.blue100 },
  icon: { width: 20, height: 20 },
  label: { ...typography.navLabel, color: colors.text500 },
  labelActive: { color: colors.blue600 },
});
