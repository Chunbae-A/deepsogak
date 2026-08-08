// Expo는 EXPO_PUBLIC_ 접두사의 값을 웹·네이티브 번들에 안전하게 주입한다.
// 값이 없으면 기존 로컬 개발 서버 주소를 사용한다.
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? 'http://localhost:8000';
