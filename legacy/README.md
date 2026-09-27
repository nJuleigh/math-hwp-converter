# legacy

참고용으로 남겨 둔 이전 시도. 현재 파이프라인(`src/`)과 호환되지 않으며 유지보수하지 않는다. 각 시도의 경위와 실패 원인은 [docs/HISTORY.md](../docs/HISTORY.md).

| 폴더 | 내용 |
|---|---|
| `v0-init/` | 이미지/PDF 에서 손으로 옮겨 적은 `TEXT:`/`EQ:`/`EQALIGN:` 파일을 한글 수식 객체로 넣는 첫 실험. `TreatAsChar=1`, `Equation Version 60` 등 지금도 쓰는 설정을 여기서 찾았다. 당시 개발 기록은 `development_log.md`. |
| `v3-hwpx-attempt/` | COM 의 속도 문제를 피하려고 hwpx(XML)를 직접 생성해 보던 시기의 변환 스크립트. 한글이 수식 크기(`hp:sz`)를 열 때 재계산하지 않아 인라인 수식이 뒤 글자와 겹쳤고, 정확한 크기는 한글 엔진 없이는 얻을 수 없어 중단. |

원고와 산출물(hwpx, DSL)은 저장소에 포함하지 않았다.
