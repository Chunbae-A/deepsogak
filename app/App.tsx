import { useState } from 'react';
import { SafeAreaView, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { BottomNav, TabKey } from './src/components/BottomNav';
import { MonitoringScreen } from './src/screens/MonitoringScreen';
import { CandidateReviewScreen } from './src/screens/CandidateReviewScreen';
import { IncidentReportScreen } from './src/screens/IncidentReportScreen';
import { SafeUploadScreen } from './src/screens/SafeUploadScreen';
import { ProtectionResultScreen } from './src/screens/ProtectionResultScreen';
import { colors, spacing } from './src/theme';

// 얼굴가드(모니터링→후보검토)와 딥백신(안전업로드→보호결과)은 각각 별도 탭으로
// 넘어가기 전까지 안에서 진행되는 하나의 흐름이라, 별도 스택 없이 로컬 스텝으로만
// 관리한다. 화면이 더 늘어나면 react-navigation 스택으로 옮긴다.
type MonitoringFlowStep = 'monitoring' | 'candidates';
type ProtectionFlowStep = 'upload' | 'result';

export default function App() {
  const [tab, setTab] = useState<TabKey>('Monitoring');
  const [flowStep, setFlowStep] = useState<MonitoringFlowStep>('monitoring');
  const [protectionStep, setProtectionStep] = useState<ProtectionFlowStep>('upload');

  const handleSelectTab = (next: TabKey) => {
    if (next === 'Monitoring') setFlowStep('monitoring');
    if (next === 'Protection') setProtectionStep('upload');
    setTab(next);
  };

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar style="dark" />
      <View style={styles.body}>
        {tab === 'Protection' && protectionStep === 'upload' && (
          <SafeUploadScreen onCreateProtectedPhoto={() => setProtectionStep('result')} />
        )}
        {tab === 'Protection' && protectionStep === 'result' && (
          <ProtectionResultScreen
            onStartMonitoring={() => {
              setFlowStep('monitoring');
              setTab('Monitoring');
            }}
          />
        )}
        {tab === 'Monitoring' && flowStep === 'monitoring' && (
          <MonitoringScreen onConfirmCandidates={() => setFlowStep('candidates')} />
        )}
        {tab === 'Monitoring' && flowStep === 'candidates' && (
          <CandidateReviewScreen onConfirmSelection={() => setTab('Report')} />
        )}
        {tab === 'Report' && <IncidentReportScreen onConfirmConsent={() => setTab('Protection')} />}
      </View>
      <View style={styles.navWrap}>
        <BottomNav active={tab} onSelect={handleSelectTab} />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  body: { flex: 1 },
  navWrap: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
});
