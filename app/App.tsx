import { useState } from 'react';
import { SafeAreaView, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { BottomNav, TabKey } from './src/components/BottomNav';
import { MonitoringScreen } from './src/screens/MonitoringScreen';
import { PlaceholderScreen } from './src/screens/PlaceholderScreen';
import { colors, spacing } from './src/theme';

export default function App() {
  const [tab, setTab] = useState<TabKey>('Monitoring');

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.body}>
        {tab === 'Protection' && <PlaceholderScreen step="1 / 5" title="딥백신 — 안전 업로드" />}
        {tab === 'Monitoring' && <MonitoringScreen onConfirmCandidates={() => setTab('Report')} />}
        {tab === 'Report' && <PlaceholderScreen step="5 / 5" title="증거·신고서 초안" />}
      </View>
      <View style={styles.navWrap}>
        <BottomNav active={tab} onSelect={setTab} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  body: { flex: 1 },
  navWrap: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
});
