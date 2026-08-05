// Figma "MVP/Components" (node 5:40) 디자인 토큰 그대로 반영.
export const colors = {
  blue600: '#2f6bff',
  blue100: '#eaf2ff',
  green600: '#168a5b',
  green100: '#e8f6ef',
  amber600: '#a86600',
  amber100: '#fff5dc',
  navy900: '#0b1f3a',
  text900: '#142036',
  text700: '#4b5872',
  text500: '#73809a',
  white: '#ffffff',
  border: '#dce3ed',
  surface: '#f6f8fb',
} as const;

export const radii = {
  sm: 3,
  md: 12,
  lg: 16,
  full: 999,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
} as const;

// Figma는 'Noto Sans KR'을 쓰지만 폰트 파일을 아직 번들하지 않아 시스템 기본 폰트로 대체한다.
export const typography = {
  title: { fontSize: 22, lineHeight: 32, fontWeight: '700' as const },
  display: { fontSize: 28, lineHeight: 38, fontWeight: '700' as const },
  heading: { fontSize: 18, lineHeight: 26, fontWeight: '700' as const },
  bodyStrong: { fontSize: 14, lineHeight: 22, fontWeight: '700' as const },
  label: { fontSize: 13, lineHeight: 18, fontWeight: '500' as const },
  button: { fontSize: 15, lineHeight: 20, fontWeight: '700' as const },
  caption: { fontSize: 12, lineHeight: 18, fontWeight: '400' as const },
  navLabel: { fontSize: 11, lineHeight: 16, fontWeight: '500' as const },
};
