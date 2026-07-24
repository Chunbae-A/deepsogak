# 딥소각 — 데이터셋 수집 계획

**작성 목적**: 개발 착수 전, "무슨 데이터를 어디서 어떻게 확보해서 어떤 용도로 쓸지"를 하나로
묶어 팀이 바로 신청·실행할 수 있게 한다. 특히 **한국인/동양인 얼굴 비중이 높은 데이터셋**을
우선순위에 두었다 — 팀원 본인 얼굴로 직접 검증했을 때 신뢰할 수 있는 결과가 나오려면, 학습·
검증 데이터 자체가 한국인 얼굴을 충분히 대표해야 하기 때문이다(서구인 위주 데이터로만 학습한
모델은 동양인 얼굴에서 정확도가 떨어지는 경향이 실제로 보고되어 있음).

---

## 0. 핵심 발견 — AI-Hub "딥페이크 변조영상"의 정체와 실제 규모

"AI-Hub 딥페이크 변조영상"이라 불렀던 데이터셋은 **KoDF(Korean DeepFake Detection Dataset,
고려대·DeepBrainAI 공동 연구, ICCV 2021 발표)와 동일한 데이터셋**이다. 다만 웹페이지 URL의
`aidata/8005`는 사람이 보는 화면 번호일 뿐, **`aihubshell` API가 실제로 쓰는 datasetkey는
`55`**다 — 이번에 `aihubshell -mode l`로 직접 조회해서 확인했다(이 조회는 API 키 없이도
동작하는 공개 기능이라 로그인 없이 실행 가능).

- **실제 확인된 규모**: zip 파일 **102개, 총 약 2,800GB(≈2.8TB)** — Training/Validation,
  원본/변조영상/오디오, "탐지방해"(perturbation) 조건까지 세분화되어 있음
- **인종 구성**: 피험자 403명 중 **395명이 한국인, 8명이 동남아시아인**
- **합성 방법**: FaceSwap, DeepFaceLab, FSGAN 등 6가지 서로 다른 생성 기법
- **전체 파일 목록**: [`scripts/aihub_inventory.py`](scripts/aihub_inventory.py)로 생성한
  [`data/inventory/55_inventory.md`](data/inventory/55_inventory.md)에 파일명·용량·filekey가
  전부 정리되어 있다 — **2.8TB를 통째로 받지 말고 이 표에서 filekey를 골라 선택 다운로드할 것**
  (예: 라벨링데이터(`validate_meta.zip`, 113KB)부터 받아 구조 확인 후, 필요한 변조 방법 1~2종만
  우선 확보).
- **주의**: 2025년 9월부터 구글 드라이브 링크가 제한된 기간에만 열리는 방식으로도 병행 운영
  중이므로, 승인받으면 즉시 다운로드해야 한다.

---

## 1. 용도별 데이터셋 전체 지도

| 용도 | 데이터셋 | 인종 구성 | 규모 | 역할 |
|---|---|---|---|---|
| 판별 모델 1차 학습 | FaceForensics++ | 대부분 서구인 | 약 5,000쌍(원본+변조) | 1차 베이스라인 모델 학습 |
| 판별 모델 1차 학습 | Celeb-DF v2 | 대부분 서구 유명인 | 실제 590 + 가짜 5,639 영상 | 고품질 딥페이크 검출력 보강 |
| **판별 모델 한국인 파인튜닝 (★핵심)** | **KoDF (=AI-Hub datasetkey 55)** | **한국인 98%** | zip 102개, 약 2.8TB(전체) — filekey 선택 다운로드 권장 | 한국인 얼굴 파인튜닝 — 본인 얼굴 검증 신뢰도의 근거 |
| 판별 모델 강건성 테스트 | DeeperForensics-1.0 | 26개국·4가지 피부톤 | 영상 60,000개 | 압축·블러·조명 등 왜곡 조건 스트레스 테스트 |
| 얼굴 유사도 필터 검증(★) | **K-FACE** | **한국인 100%** | 1,000명 × 약 30,000장 | ArcFace 임베딩 한국인 검증·임계값(0.6) 재보정 |
| 자기 검증(선택) | 팀원 본인 얼굴 소규모 셋 | 한국인(팀 본인) | 팀원 3인 × 다각도 촬영 | 정성적 데모·발표용 검증 |

---

## 2. 신청 절차·소요 시간

| 데이터셋 | 신청 링크 | 예상 소요 | 필요 서류 |
|---|---|---|---|
| FaceForensics++ | https://github.com/ondyari/FaceForensics | 1주 이상 가능 | 없음(구글 폼) |
| Celeb-DF v2 | https://github.com/yuezunli/celeb-deepfakeforensics | 수일~1주 | 없음 |
| KoDF (=AI-Hub datasetkey 55) | https://aihub.or.kr/aidata/8005 (국내, 사람 화면 번호) — API에서는 datasetkey **55** 사용 | **셀프서비스**: AI-Hub 가입 + 휴대폰 인증만으로 API 키 즉시 발급(사람 검토 대기 없음) | AI-Hub 휴대폰 본인인증 |
| DeeperForensics-1.0 | https://github.com/EndlessSora/DeeperForensics-1.0 | 수일 | 가능하면 교육기관 이메일 |
| K-FACE | https://kface.aihub.or.kr/ | **사람 검토 필요** — 재직/재학증명서 + 활용계획서 제출 후 심사 | 재직/재학증명서, 데이터 활용계획서(팀에서 이미 작성 중인 PDF 2건이 이 절차용으로 확인됨) |
| 자기 검증 셋 | 팀 자체 촬영 | 즉시 | 팀원 개인정보 동의 |

---

## 3. 확보 순서

1. **(Day 0) FF++ / Celeb-DF / KoDF / DeeperForensics 동시 신청**
2. **(Day 0~1) K-FACE 신청** — 회원가입 기반이라 가장 빠름
3. **(대기 중) 전처리 파이프라인 코드 작성** — 얼굴 검출·크롭·정렬, train/val/test 분할
4. **(FF++·Celeb-DF 도착) 1차 모델 학습**
5. **(KoDF 도착) 한국인 파인튜닝** — 이 시점부터 본인 얼굴 정성 검증이 의미를 가짐
6. **(DeeperForensics 도착) 강건성 테스트**

KoDF 승인이 늦어지면 FF++·Celeb-DF만으로 1차 모델을 완성하고, KoDF는 2단계 보강으로 미룬다.

---

## 4. 라이선스

| 데이터셋 | 라이선스 |
|---|---|
| FaceForensics++ / Celeb-DF v2 / DeeperForensics-1.0 | 비상업적 연구 목적만 허용 |
| KoDF | 페이지에 구체 라이선스 문구 명시 안 됨 — 신청 시 동의서 문구 재확인 필요 |
| K-FACE | AI-Hub 표준 이용정책(연구 목적) |

해커톤 단계는 비상업 연구 목적이라 문제없으나, 사업화 단계에서는 전 데이터셋 라이선스를 다시
확인해야 한다.

---

## 5. 데이터 분할 전략

- **train**: FF++ + Celeb-DF + KoDF train split
- **validation**: 인물 단위로 겹치지 않게 분리(subject-level split — 안 그러면 성능 과대평가됨)
- **test**: KoDF test split + DeeperForensics-1.0 전체(강건성) + 팀원 자기 검증 셋(정성적)

## 6. 무엇이 자동화되고, 무엇이 안 되는가

| 구분 | 데이터셋 | 자동화 가능 여부 |
|---|---|---|
| **완전 자동화(CI로 실행 중)** | KoDF/AI-Hub 파일 목록 조회 | `.github/workflows/update-aihub-inventory.yml`이 매주 자동 실행, API 키 불필요(공개 조회) |
| **셀프서비스(승인 대기 없음)** | KoDF 실제 파일 다운로드 | `scripts/aihub_download.sh` 실행 — 팀원이 AI-Hub API 키만 발급받으면(가입 즉시) 스크립트로 바로 다운로드 가능 |
| **사람 검토 필요(자동화 불가)** | FaceForensics++ / Celeb-DF v2 / DeeperForensics-1.0 / K-FACE | 구글 폼 제출 또는 서류(재직증명서 등) 제출 후 담당자가 검토·승인해야 함 — 계정 도용·본인인증 우회가 되므로 대리 진행 불가, 팀원이 직접 신청해야 한다 |

## 7. 이 브랜치의 스크립트

- **`scripts/aihub_inventory.py`**: AI-Hub 데이터셋(기본 datasetkey=55, KoDF)의 파일 트리를
  조회해 `data/inventory/`에 JSON·마크다운 인벤토리를 생성한다. API 키 불필요, CI에서 매주
  자동 실행.
- **`scripts/aihub_download.sh`**: `AIHUB_API_KEY` 환경변수와 filekey 목록을 받아 실제 파일을
  `data/raw/kodf`에 내려받는다. 사용 전 `data/inventory/55_inventory.md`에서 필요한 filekey를
  고를 것.
- **`scripts/setup_dirs.py`**: FF++·Celeb-DF·DeeperForensics·K-FACE·자기 검증 셋을 위한
  `data/raw|processed/<데이터셋>` 폴더를 만든다(이 4개는 수동 승인 후 이 폴더에 직접 옮겨 담음).

실제 원본 데이터(영상·이미지)는 `data/raw`, `data/processed`에 두되 용량이 크고 라이선스상
재배포 금지이므로 **git에는 커밋하지 않는다**(`.gitignore` 처리). 인벤토리(파일 목록·크기·
filekey)만 커밋해 팀이 무엇을 받을 수 있는지 항상 최신 상태로 볼 수 있게 한다.
