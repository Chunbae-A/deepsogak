# 데이터셋별 확보 안내

모든 데이터셋이 승인제라 자동 다운로드가 불가능하다. 각 데이터셋을 신청해서 승인받은 뒤,
아래 표에 맞는 폴더에 압축을 풀어두면 이후 전처리 스크립트가 이 구조를 기준으로 동작한다.

| 데이터셋 | 신청 링크 | 저장 위치 |
|---|---|---|
| FaceForensics++ | https://github.com/ondyari/FaceForensics | `data/raw/ffpp/` |
| Celeb-DF v2 | https://github.com/yuezunli/celeb-deepfakeforensics | `data/raw/celebdf/` |
| KoDF | https://aihub.or.kr/aidata/8005 / https://deepbrainai-research.github.io/kodf/ | `data/raw/kodf/` |
| DeeperForensics-1.0 | https://github.com/EndlessSora/DeeperForensics-1.0 | `data/raw/deeperforensics/` |
| K-FACE | https://kface.aihub.or.kr/ | `data/raw/kface/` |
| 자기 검증 셋 | 팀 자체 촬영 | `data/raw/self_check/` |

`python scripts/setup_dirs.py` 실행하면 위 폴더를 한 번에 생성한다.

자세한 배경(용도별 지도, 라이선스, 확보 순서)은 [`../DATA_PLAN.md`](../DATA_PLAN.md) 참고.
