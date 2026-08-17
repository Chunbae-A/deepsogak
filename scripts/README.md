# 데이터셋별 확보 안내

모든 데이터셋이 승인제라 자동 다운로드가 불가능하다. 각 데이터셋을 신청해서 승인받은 뒤,
아래 표에 맞는 폴더에 압축을 풀어두면 이후 전처리 스크립트가 이 구조를 기준으로 동작한다.

| 데이터셋 | 신청 링크 | 저장 위치 |
|---|---|---|
| FaceForensics++ | https://github.com/ondyari/FaceForensics | `data/raw/ffpp/` |
| Celeb-DF v2 | https://github.com/yuezunli/celeb-deepfakeforensics | `data/raw/celebdf/` |
| KoDF (AI-Hub datasetkey=55) | https://aihub.or.kr/aidata/8005 (API 내부 키는 55) | `data/raw/kodf/` — `aihub_download.sh`로 다운로드 |
| DeeperForensics-1.0 | https://github.com/EndlessSora/DeeperForensics-1.0 | `data/raw/deeperforensics/` |
| K-FACE | https://kface.aihub.or.kr/ | `data/raw/kface/` |
| 자기 검증 셋 | 팀 자체 촬영 | `data/raw/self_check/` |

`python scripts/setup_dirs.py` 실행하면 위 폴더를 한 번에 생성한다.

## KoDF(AI-Hub)만 예외 — 셀프서비스로 자동화되어 있음

KoDF는 사람 검토 없이 AI-Hub 회원가입 + 휴대폰 인증만으로 API 키를 바로 받을 수 있어, 아래
두 스크립트로 조회·다운로드가 자동화되어 있다.

```bash
# 1. 파일 목록 확인 (API 키 불필요, CI에서 매주 자동 실행됨)
python scripts/aihub_inventory.py --dataset-key 55
cat data/inventory/55_inventory.md   # filekey 확인

# 2. 필요한 파일만 선택 다운로드 (AI-Hub API 키 필요)
AIHUB_API_KEY=발급받은키 ./scripts/aihub_download.sh 55 38522,38523
```

**전체 2.8TB를 한 번에 받지 말 것** — `55_inventory.md`에서 필요한 filekey만 골라서 받는다.

자세한 배경(용도별 지도, 라이선스, 확보 순서, 무엇이 자동화되고 무엇이 안 되는지)은
[`../DATA_PLAN.md`](../DATA_PLAN.md) 참고.
