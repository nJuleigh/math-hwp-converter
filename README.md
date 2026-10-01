# math-hwp-converter

수학 문제 자료(문제·수식·해설)를 구조를 인식해 **편집 가능한 한글(.hwp) 문서**로 재구성하는 자동화 도구.
수식은 그림이 아니라 한글 수식 편집기의 수식 객체로, 해설은 미주로 들어갑니다.

## 배경

수식이 포함된 문제와 해설을 자유롭게 편집하고, 해설을 미주 형태로 관리할 수 있는 한글 문서가 필요해 개인 프로젝트로 시작했습니다.

처음 목표는 **이미지·PDF 형태의 문제 자료를 곧바로 한글 문서로 변환**하는 것이었습니다. 그러나 OCR 단계의 정확도 문제가 변환 단계의 문제와 뒤섞여 원인을 가리기 어려웠기 때문에, OCR 을 분리하고 **LaTeX → HWP 변환 파이프라인**을 먼저 구현했습니다. 이미지·PDF 는 현재 LaTeX 로 옮긴 뒤 이 파이프라인에 넣는 방식입니다.

## 현재 구조

```
.tex ──(tex_to_dsl.py)──▶ DSL(.txt) ──(split_dsl.py)──▶ 조각 ──(make_hwp_from_txt.py)──▶ .hwp ──(merge_hwp.py)──▶ 하나의 .hwp
       리눅스/맥/윈도우 어디서나              │                        윈도우 + 한글 필요
                                            └─ latex_to_hwp.py : LaTeX 수식 → 한글 수식 스크립트
```

LaTeX 문서의 본문·문제·해설·수식·그림 구조를 한 줄 단위의 중간 언어 **DSL** 로 바꾼 뒤, Python 과 한컴오피스 **COM 자동화**(`win32com`)로 한글을 조종해 문서를 만듭니다. DSL 은 사람이 읽고 손으로 고칠 수 있는 형식입니다 (아래 "DSL 명령").

지원 범위:

* 인라인 / 독립 수식, `aligned`·`cases`·행렬(`pmatrix` 등)·`array` 환경
* 문제 번호 인식과 재번호 매김, 교차 참조 자동 치환
* 문단 서식(정렬·들여쓰기), 쪽 나누기, 그림 삽입과 그림 자리표시자
* 해설의 미주 배치(또는 본문 배치), 기존 hwp 문서의 문항에 미주 덧붙이기
* **지원하지 않는 LaTeX 명령은 조용히 지우지 않고 별도로 수집**해 실행이 끝나면 빈도와 함께 출력 — 오류 원인을 바로 확인할 수 있습니다

## 검증 상태

다양한 수식이 포함된 대규모 원고(문제 수백 개, 수식 6,000여 개)를 반복 변환하며 정확도를 검증·보완했습니다.

| 단계 | 상태 |
|---|---|
| tex → DSL | 리눅스에서 검증. 문제/해설 1:1 대응 확인 |
| 수식 변환 | 20-30페이지 분량의 수십개의 파일 변환 실패 0 |
| DSL → hwp | 윈도우에서 실제 한글로 확인 |
| **미검증** | `merge_hwp.py` 로 합친 뒤 미주 번호가 이어지는지 / `IMG:` 의 `InsertPicture` 크기 단위 / `--attach` 의 `GOTO:` 대상 문항 대조 / `register_hwp_security.py` |

일반적인 수식은 안정적으로 변환되지만 모든 LaTeX 표현을 지원하지는 않습니다. 예외 사례는 "미지원 명령" 출력을 보며 계속 보완 중입니다.

## 개발 흐름과 실패한 시도

자세한 내용은 [HISTORY.md](HISTORY.md).

1. **v0 — 이미지/PDF 직접 변환 (보류)** — 사진에서 옮겨 적은 `TEXT:`/`EQ:` 파일을 COM 으로 한글에 넣는 실험. 수식이 편집 가능한 객체로 들어가는 것은 확인했으나, OCR 오류와 변환 오류가 섞여 원인 분리가 안 됨 → OCR 을 떼어내고 LaTeX 입력으로 전환.
2. **tex 파서 추가** — `.tex` 를 읽어 DSL 을 만들고 해설을 미주로 빼는 구조로 확장. 그러나 COM 은 문서가 커질수록 느려져 대규모 원고에 수 시간이 걸림.
3. **v3 — hwpx 직접 생성 (실패)** — 속도 문제를 피하려고 한글 없이 hwpx(XML)를 직접 써 보는 시도. 문단·미주·수식 컨트롤은 정상 생성됐고 0.8초면 끝났지만, 한글이 수식 크기(`hp:sz`)를 파일에 저장된 값 그대로 쓰고 열 때 재계산하지 않아 인라인 수식이 뒤 글자와 겹침. 정확한 크기는 한글 수식 엔진만 알므로 "한글 없이 끝내기" 는 성립하지 않는다고 판단해 중단.
4. **현재** — COM 방식으로 복귀하되, DSL 을 3,000 줄 단위로 쪼개 돌리고 나중에 합치는 방식으로 속도 문제를 우회. 수식 변환기는 토큰 단위 치환으로 재작성.

## 저장소 구성

```
src/
  tex_to_dsl.py             .tex → DSL
  latex_to_hwp.py           LaTeX 수식 → 한글 수식 스크립트
  split_dsl.py              DSL 을 장/줄 수 단위로 쪼개고 run_all.bat 생성
  cut_dsl.py                DSL 에서 특정 문제 구간만 잘라내기 (시험 실행용)
  make_hwp_from_txt.py      DSL → .hwp          (윈도우 + 한글)
  merge_hwp.py              여러 .hwp 를 한 파일로 (윈도우 + 한글)
  hwp_read.py               한글 없이 .hwp 본문 문단 읽기 (--attach 의 문항 찾기에 사용)
  register_hwp_security.py  한글 자동화 보안 모듈 등록 도우미 (윈도우)
HISTORY.md                  개발 흐름, 실패한 시도와 원인
```

## 요구 사항

* Python 3.10 이상
* 윈도우에서 hwp 를 만들 때만: `pip install pywin32`, 한글(한컴오피스) 설치, 보안 모듈 등록(아래)

```
pip install -r requirements.txt
```

## 사용법

### 1. tex → DSL (어느 OS 든)

```
python src/tex_to_dsl.py -i 원고.tex -o 원고_dsl.txt
```

여러 파일을 이어 붙이려면 `-i a.tex b.tex c.tex`. 실행이 끝나면 문제/해설/수식 개수와 "처리하지 못하고 지운 명령" 목록을 찍어 주므로 **개수가 tex 의 문제 수와 맞는지** 먼저 확인합니다.

| 옵션 | 뜻 |
|---|---|
| `--solutions endnote\|inline` | 해설을 미주(기본)로 뺄지, 본문에 굵은 "해설" 제목으로 이어 붙일지 |
| `--renumber none\|numbered\|all` | `numbered`: 번호만 있는 문제(`123.`)를 1부터 다시 매김 / `all`: 예제·문제까지 전부 |
| `--start N` | 다시 매길 때 시작 번호 |

재번호를 하면 `*_numbermap.txt` 대조표가 같이 생기고, 본문의 교차 참조("문제 12 참고")도 새 번호로 자동 치환됩니다. 치환하지 못한 참조는 `[확인 필요]` 로 출력합니다. `% [그림 필요: …]` 형태의 메모는 해당 문제 끝에 `FIX:` 로 모아 둡니다(문서에는 안 들어감).

### 2. (선택) 쪼개기

한글은 문서가 커질수록 느려집니다(체감상 줄 수의 제곱). 3,000 줄 안팎으로 나누는 것을 권합니다.

```
python src/split_dsl.py -i 원고_dsl.txt -o out --max-lines 3000
```

`out/3장-1.txt, 3장-2.txt, …` 와 이것들을 차례로 돌리는 `out/run_all.bat` 이 생깁니다. 문제 경계(`PROB:`)에서만 자르므로 미주가 찢어지지 않습니다.

### 3. DSL → hwp (윈도우 + 한글)

```
python src/make_hwp_from_txt.py -i 원고_dsl.txt -o 원고.hwp
```

| 옵션 | 뜻 |
|---|---|
| `--prob-gap N` | 문제와 문제 사이 빈 문단 수 (기본 3) |
| `--solutions inline` | `SOL:` 블록을 미주가 아니라 본문에 |
| `--attach 기존.hwp` | 기존 hwp 를 열어 그 안의 `N.` 문항에 `GOTO:`/`SOL:` 로 미주·그림을 붙임 (`-o` 는 다른 이름) |
| `--align` | 본문 기본 정렬 (기본 justify) |
| `--append` | `-o` 파일이 이미 있으면 그 끝에 이어 붙임 |
| `--template style.hwp` | 서식 파일에 이어서 작성 |
| `--visible` | 한글 창을 보이게 (디버깅용, 기본은 숨김) |

### 4. 합치기 (윈도우 + 한글)

```
python src/merge_hwp.py -o 전체.hwp --glob "out/*장-*.hwp"
```

첫 파일을 열고 문서 끝에 다음 파일을 끼워넣기(InsertFile)하는 방식입니다. 이름의 숫자를 자연 정렬합니다(3장-2 가 3장-10 앞).

## ⚠️ 실행 중 주의

* **스크립트가 도는 동안 한글을 열지 마세요.** 창이 숨겨진 채로 한글이 돌고 있는데 사용자가 한글을 열면, 스크립트가 **그 문서에 쓰기 시작합니다.** `run_all.bat` 처럼 여러 개를 돌릴 때 특히 주의.
* 보안 모듈(FilePathCheckerModule)이 등록돼 있지 않으면 파일을 열고 저장할 때마다 "접근 허용" 팝업이 떠서 배치가 멈춥니다. 한컴 자동화 SDK 의 `FilePathCheckerModuleExample.dll` 을 받아 `python src/register_hwp_security.py --dll <경로>` 로 등록하거나, `regsvr32` + 레지스트리 `HKCU\Software\HNC\HwpAutomation\Modules\FilePathCheckerModule` 값을 손으로 잡아 주세요.
* 진행 상황은 200 줄마다 콘솔에 찍힙니다(`--progress 0` 으로 끔).

## 인식하는 tex 형식

문제/해설 경계는 `\noindent\textbf{…}` 헤더로 판단합니다.

| tex | DSL |
|---|---|
| `\noindent\textbf{예제 3-1. 제목}` `{문제 5-1. 제목}` | `PROB: 예제 3-1. 제목` |
| `{문제 487}` `{문제 1.}` `{문제 4a.}` `{123.}` `{Problem 1.}` `{Problem.}` | `PROB: …` |
| `\noindent\textbf{해설}` `{해설.}` `{Solution.}` `{Proof.}` | `SOL:` … `ENDSOL:` (미주) |
| `\noindent\textbf{12번 해설.}` | `GOTO: 12` + `SOL:` (기존 hwp 에 붙이는 `--attach` 용) |
| `\( \)` `$ $` | `EQ:` |
| `\[ \]` `$$ $$` `align*` `equation*` … | `EQD:` (여러 줄은 한 줄로 접음) |
| 빈 줄, `\bigskip`, `\par` | `BR:` |
| `\newpage` | `NEWPAGE:` |
| `enumerate` / `itemize` | `(1) (2) …` / `·` |
| `\textbf{…}` `\textit{…}` `\emph{…}` | 내용만 남김 (제목 줄 제외) |
| `% [그림 필요: …]` | `FIX:` (문서에는 안 들어감) |

제목 줄 안의 짧은 수식(`X_1`, `\times`)은 유니코드 문자로 펴서 넣습니다(`X₁`, `×`).

## 수식 변환 (latex_to_hwp.py)

실제 한글에서 렌더링을 보며 맞춘 규칙 몇 가지:

* `\frac12`, `\sqrt2` 처럼 중괄호를 생략한 인자도 처리
* `60^\circ` → `60^{circ}`, `\mathbb{R}` → `VecR`, `\mathcal{L}` → `bold L` (대응 키워드가 없어 대체)
* `\left( … \right)` 는 지우지 않고 `left ( … right )` 로 보존
* `_n C_k` 처럼 base 가 없는 첨자 앞에 `{}` 자동 삽입 (렌더 실패 방지)
* `\int` 가 `\in` 에 먹히는 류의 접두사 충돌이 없도록 토큰 단위로 치환

단독으로도 씁니다:

```
python src/latex_to_hwp.py "\frac{a+b}{c} = \sqrt{x}"
python src/latex_to_hwp.py --selftest
```

## DSL 명령

`tex_to_dsl.py` 가 내는 것:

| 명령 | 뜻 |
|---|---|
| `PROB: 라벨` | 문제 시작 (굵은 제목 문단) |
| `TEXT: 본문` | 본문. 인라인 수식 앞뒤에서 나뉜다 |
| `EQ: <LaTeX>` / `EQD: <LaTeX>` | 줄 안 수식 / 독립 행 가운데 정렬 수식 |
| `BR:` | 문단 나누기 |
| `SOL:` … `ENDSOL:` | 해설 블록 (기본 미주) |
| `SEC: 제목` | 굵은 절 제목 |
| `GOTO: N` | 기존 hwp 의 `N.` 문항 뒤로 이동 (`--attach` 전용) |
| `FIX: 메모` | 작업 메모. 문서에 들어가지 않음 |
| `NEWPAGE:` | 쪽 나누기 |

손으로 DSL 을 다듬을 때 추가로 쓸 수 있는 것: `IMG: 경로 | 폭mm`, `FIG: 번호 | 설명 | 70x50`(자리표시자), `EQALIGN:` … `END:`(여러 줄 수식), `ALIGN:`, `INDENT: left=10 first=-10`, `SOURCE:`, `ANS:`, `UNSURE:`. 모르는 명령은 건너뛰고 마지막에 개수를 출력합니다.

예:

```
PROB: 예제 3-1. 연의 총수
TEXT: 두 종류의 문자
EQ: a,b
TEXT: 를 사용하여 …
BR:
EQD: n>m\ge2
SOL:
TEXT: 첫 번째 방법 …
ENDSOL:
```

## 라이선스

MIT — [LICENSE](LICENSE)
