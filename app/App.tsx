import { useState } from 'react';
import { SafeAreaView, StyleSheet, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { BottomNav, TabKey } from './src/components/BottomNav';
import { MonitoringScreen } from './src/screens/MonitoringScreen';
import { CandidateReviewScreen } from './src/screens/CandidateReviewScreen';
import { IncidentReportScreen } from './src/screens/IncidentReportScreen';
import { ReportReadyScreen } from './src/screens/ReportReadyScreen';
import { SafeUploadScreen } from './src/screens/SafeUploadScreen';
import { ProtectionResultScreen } from './src/screens/ProtectionResultScreen';
import { colors, spacing } from './src/theme';

// 얼굴가드(모니터링→후보검토)·딥백신(안전업로드→보호결과)·즉각소각(초안→완료)은
// 각각 별도 탭으로 넘어가기 전까지 안에서 진행되는 하나의 흐름이라, 별도 스택 없이
// 로컬 스텝으로만 관리한다. 화면이 더 늘어나면 react-navigation 스택으로 옮긴다.
type MonitoringFlowStep = 'monitoring' | 'candidates';
type ProtectionFlowStep = 'upload' | 'result';
type ReportFlowStep = 'draft' | 'ready';

export default function App() {
  const [tab, setTab] = useState<TabKey>('Monitoring');
  const [flowStep, setFlowStep] = useState<MonitoringFlowStep>('monitoring');
  const [protectionStep, setProtectionStep] = useState<ProtectionFlowStep>('upload');
  const [protectionJobId, setProtectionJobId] = useState<string | null>(null);
  const [reportStep, setReportStep] = useState<ReportFlowStep>('draft');

  const handleSelectTab = (next: TabKey) => {
    if (next === 'Monitoring') setFlowStep('monitoring');
    if (next === 'Protection') setProtectionStep('upload');
    if (next === 'Report') setReportStep('draft');
    setTab(next);
  };

  return (
    <View style={styles.webBackdrop}>
      <SafeAreaView style={styles.safe}>
        <StatusBar style="dark" />
        <View style={styles.body}>
          {tab === 'Protection' && protectionStep === 'upload' && (
            <SafeUploadScreen
              onCreateProtectedPhoto={(jobId) => {
                setProtectionJobId(jobId);
                setProtectionStep('result');
              }}
            />
          )}
          {tab === 'Protection' && protectionStep === 'result' && protectionJobId && (
            <ProtectionResultScreen
              jobId={protectionJobId}
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
          {tab === 'Report' && reportStep === 'draft' && (
            <IncidentReportScreen onConfirmConsent={() => setReportStep('ready')} />
          )}
          {tab === 'Report' && reportStep === 'ready' && (
            <ReportReadyScreen
              onGoHome={() => {
                setProtectionStep('upload');
                setTab('Protection');
              }}
            />
          )}
        </View>
        <View style={styles.navWrap}>
          <BottomNav active={tab} onSelect={handleSelectTab} />
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  // 넓은 데스크톱 브라우저에서도 Figma가 의도한 폰 화면 비율을 유지하기 위한 프레임.
  // 네이티브(iOS/Android)에서는 화면 자체가 이미 이 너비 근처라 영향이 없다.
  webBackdrop: { flex: 1, alignItems: 'center', backgroundColor: colors.border },
  safe: { flex: 1, width: '100%', maxWidth: 480, backgroundColor: colors.surface },
  body: { flex: 1 },
  navWrap: { paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
});
