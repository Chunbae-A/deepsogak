import { useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { InfoPanel } from '../components/InfoPanel';
import { PrimaryButton, SecondaryButton } from '../components/Button';
import { colors, radii, spacing, typography } from '../theme';
import { saveReportPackage } from '../services/reportApi';

const GENERATED_FILES = [
  { label: '플랫폼 신고용 요약서', value: 'PDF 1개' },
  { label: '수사기관 제출용 증거 목록', value: 'PDF 1개' },
  { label: '캡처·해시 원본', value: 'ZIP 1개' },
];

function formatGeneratedAt(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}.${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function ReportReadyScreen({ onGoHome }: { onGoHome: () => void }) {
  const [generatedAt] = useState(() => formatGeneratedAt(new Date()));
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await saveReportPackage();
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <View style={styles.screen}>
      <AppBar step="완료" />
      <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>신고자료가 준비됐어요</Text>
          <Text style={styles.subtitle}>기기에 안전하게 저장한 뒤 원하는 기관에 직접 제출할 수 있어요.</Text>
        </View>

        <View style={styles.successCard}>
          <View style={styles.successIcon}>
            <Text style={styles.successCheck}>✓</Text>
          </View>
          <Text style={styles.successTitle}>증거·신고서 패키지 생성 완료</Text>
          <Text style={styles.successMeta}>{generatedAt} · 기기 내 생성</Text>
        </View>

        <View style={styles.packageCard}>
          <Text style={styles.packageTitle}>생성된 자료</Text>
          {GENERATED_FILES.map((file) => (
            <View key={file.label} style={styles.packageRow}>
              <Text style={styles.packageLabel}>{file.label}</Text>
              <Text style={styles.packageValue}>{file.value}</Text>
            </View>
          ))}
        </View>

        <View style={styles.nextActions}>
          <Text style={styles.nextActionsTitle}>다음 단계</Text>
          <Text style={styles.nextActionsItem}>1. 플랫폼 신고 센터에 직접 제출</Text>
          <Text style={styles.nextActionsItem}>2. 필요 시 수사기관에 증거 목록 제출</Text>
        </View>

        <InfoPanel
          title="아직 외부로 전송되지 않았어요"
          body="저장된 자료는 사용자가 직접 확인하고 제출할 때만 외부에 공유됩니다."
        />
      </ScrollView>

      <View style={styles.bottomCta}>
        <SecondaryButton label={isSaving ? '저장 중...' : '자료 패키지 저장'} onPress={handleSave} disabled={isSaving} />
        <PrimaryButton label="홈으로 돌아가기" onPress={onGoHome} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.surface, alignItems: 'center', paddingHorizontal: spacing.xl, paddingTop: spacing.lg, gap: spacing.md },
  content: { flex: 1, width: '100%' },
  contentInner: { gap: spacing.md, paddingBottom: spacing.md },
  headerCopy: { gap: spacing.xs },
  title: { ...typography.title, color: colors.text900 },
  subtitle: { ...typography.caption, color: colors.text700 },
  successCard: {
    backgroundColor: colors.green100,
    borderRadius: radii.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: 18,
    alignItems: 'center',
    gap: 6,
    width: '100%',
  },
  successIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.green600,
    alignItems: 'center',
    justifyContent: 'center',
  },
  successCheck: { color: colors.white, fontSize: 24, fontWeight: '700' },
  successTitle: { ...typography.bodyStrong, color: colors.text900 },
  successMeta: { ...typography.caption, color: colors.text700 },
  packageCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
    width: '100%',
  },
  packageTitle: { ...typography.bodyStrong, color: colors.text900 },
  packageRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  packageLabel: { ...typography.caption, color: colors.text700 },
  packageValue: { ...typography.bodyStrong, color: colors.green600 },
  nextActions: {
    backgroundColor: colors.blue100,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
    width: '100%',
  },
  nextActionsTitle: { ...typography.bodyStrong, color: colors.text900 },
  nextActionsItem: { ...typography.caption, color: colors.text700 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg, gap: spacing.sm },
});
