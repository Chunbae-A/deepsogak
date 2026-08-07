import { useCallback, useEffect, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { AppBar } from '../components/AppBar';
import { StatusChip } from '../components/StatusChip';
import { EvidenceRow } from '../components/EvidenceRow';
import { PrimaryButton, SecondaryButton } from '../components/Button';
import { LoadingView, ErrorView } from '../components/ScreenStatus';
import { colors, radii, spacing, typography } from '../theme';
import { EvidenceField, fetchEvidenceDraft, submitConsent, updateEvidenceDraft } from '../services/reportApi';

const editIcon = require('../../assets/icons/icon-edit.png');

export function IncidentReportScreen({ onConfirmConsent }: { onConfirmConsent: () => void }) {
  const [draft, setDraft] = useState<EvidenceField[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editedFields, setEditedFields] = useState<EvidenceField[] | null>(null);
  const [isSavingEdit, setIsSavingEdit] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  const load = useCallback(() => {
    let cancelled = false;
    setError(null);
    setDraft(null);
    fetchEvidenceDraft()
      .then((data) => {
        if (!cancelled) setDraft(data);
      })
      .catch(() => {
        if (!cancelled) setError('증거 초안을 불러오지 못했습니다.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  const handleStartEdit = () => {
    if (!draft) return;
    setEditedFields(draft.map((f) => ({ ...f })));
    setEditError(null);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedFields(null);
    setEditError(null);
  };

  const handleFieldChange = (key: string, value: string) => {
    setEditedFields((prev) => (prev ? prev.map((f) => (f.key === key ? { ...f, value } : f)) : prev));
  };

  const handleSaveEdit = async () => {
    if (!editedFields) return;
    setIsSavingEdit(true);
    setEditError(null);
    try {
      await updateEvidenceDraft(editedFields);
      setDraft(editedFields);
      setIsEditing(false);
      setEditedFields(null);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : '증거 초안 수정에 실패했습니다.');
    } finally {
      setIsSavingEdit(false);
    }
  };

  const handleConfirm = () => {
    submitConsent().catch(() => {});
    onConfirmConsent();
  };

  return (
    <View style={styles.screen}>
      <AppBar step="5 / 5" />
      {error ? (
        <ErrorView message={error} onRetry={load} />
      ) : !draft ? (
        <LoadingView />
      ) : (
        <>
          <ScrollView style={styles.content} contentContainerStyle={styles.contentInner} showsVerticalScrollIndicator={false}>
            <View style={styles.headerCopy}>
              <Text style={styles.title}>증거·신고서 초안이 준비됐어요</Text>
              <Text style={styles.subtitle}>동의 전에는 어디로도 전송되지 않습니다.</Text>
            </View>

            <StatusChip label="필수 누락 항목 0개" />

            <View style={styles.draftCard}>
              <View style={styles.draftHeader}>
                <Text style={styles.draftHeaderTitle}>증거 초안</Text>
                {!isEditing && (
                  <Pressable style={styles.editPill} onPress={handleStartEdit}>
                    <Image source={editIcon} style={styles.editIcon} resizeMode="contain" />
                    <Text style={styles.editLabel}>직접 수정</Text>
                  </Pressable>
                )}
              </View>
              <View style={styles.divider} />
              {isEditing && editedFields ? (
                <View style={styles.rows}>
                  {editedFields.map((field) => (
                    <View key={field.key} style={styles.editRow}>
                      <Text style={styles.editRowLabel}>{field.label}</Text>
                      <TextInput
                        style={styles.editRowInput}
                        value={field.value}
                        onChangeText={(text) => handleFieldChange(field.key, text)}
                      />
                    </View>
                  ))}
                  {editError && <Text style={styles.editError}>{editError}</Text>}
                  <View style={styles.editActions}>
                    <View style={styles.editActionButton}>
                      <SecondaryButton label="취소" onPress={handleCancelEdit} disabled={isSavingEdit} />
                    </View>
                    <View style={styles.editActionButton}>
                      <PrimaryButton label={isSavingEdit ? '저장 중...' : '수정 저장'} onPress={handleSaveEdit} disabled={isSavingEdit} />
                    </View>
                  </View>
                </View>
              ) : (
                <View style={styles.rows}>
                  {draft.map((field) => (
                    <EvidenceRow key={field.key} field={field.label} value={field.value} tone="link" />
                  ))}
                </View>
              )}
            </View>

            <View style={styles.consentBox}>
              <View style={styles.consentCheckbox} />
              <View style={styles.consentText}>
                <Text style={styles.consentTitle}>동의 전에는 전송되지 않아요</Text>
                <Text style={styles.consentBody}>
                  신고서 초안과 증거 자료는 회원님이 동의 버튼을 누르기 전까지 어떤 채널로도 제출되지 않습니다.
                </Text>
              </View>
            </View>
          </ScrollView>

          <View style={styles.bottomCta}>
            <PrimaryButton label="초안 검토 후 동의" onPress={handleConfirm} />
          </View>
        </>
      )}
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
  draftCard: {
    backgroundColor: colors.white,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.lg,
    padding: spacing.md,
    width: '100%',
    gap: spacing.sm,
  },
  draftHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  draftHeaderTitle: { ...typography.bodyStrong, color: colors.text900 },
  editPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.full,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  editIcon: { width: 14, height: 14 },
  editRow: { gap: 4, paddingVertical: 6 },
  editRowLabel: { ...typography.caption, color: colors.text500 },
  editRowInput: {
    height: 40,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
    paddingHorizontal: spacing.sm,
    color: colors.text900,
  },
  editError: { ...typography.caption, color: colors.amber600 },
  editActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
  editActionButton: { flex: 1 },
  editLabel: { ...typography.caption, color: colors.text700 },
  divider: { height: 1, backgroundColor: colors.border, width: '100%' },
  rows: { gap: 0 },
  consentBox: {
    backgroundColor: colors.white,
    borderWidth: 1.5,
    borderColor: colors.green600,
    borderRadius: radii.md,
    padding: spacing.md,
    flexDirection: 'row',
    gap: spacing.sm,
    width: '100%',
  },
  consentCheckbox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: colors.green600,
    backgroundColor: colors.white,
  },
  consentText: { flex: 1, gap: 2 },
  consentTitle: { ...typography.bodyStrong, color: colors.text900 },
  consentBody: { ...typography.caption, color: colors.text700 },
  bottomCta: { width: '100%', paddingBottom: spacing.lg },
});
