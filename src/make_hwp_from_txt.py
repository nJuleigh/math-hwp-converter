"""DSL(.txt) -> HWP 문서 생성기 (v2).

v1 대비 변경
  * 새 문서가 2개 열리던 문제 수정 (EnsureDispatch 가 이미 빈 문서를 하나 만든다)
  * 종료 시 열린 문서를 전부 닫아 "저장하시겠습니까?" 팝업 제거
  * 문단 서식 명령 추가 : ALIGN: / INDENT: / EQD:

DSL 명령
    TEXT: 본문                본문 삽입 (뒤쪽 공백 보존)
    EQ: <LaTeX>               줄 안에 들어가는 수식
    EQD: <LaTeX>              독립 행 + 가운데 정렬 수식 (앞뒤 문단 자동 처리)
    EQALIGN: ... END:         여러 줄 수식 (독립 행 + 가운데 정렬)
    BR:                       문단 나누기
    ALIGN: center             이후 문단 정렬 (left/center/right/justify/distribute)
    INDENT: left=10 first=-10 문단 왼쪽 여백 / 첫 줄 들여쓰기 (mm)
    IMG: 경로 | 높이(mm)      그림 삽입 (높이 지정, 원본 비율로 너비 계산)
    FIG: 번호 | 설명 | 폭mm   그림 자리표시자 (아직 이미지가 없을 때)
    NEWPAGE:                  쪽 나누기
    SPACE:                    공백 한 칸 (구버전 호환)
    SEC: 제목                 절 제목 (굵게)
    PROB: 번호                문제 시작 (굵은 번호)
    EXAM: 6・1 | 제목          해설편 예제/문제
    SOURCE: 출처              출처 (오른쪽 정렬)
    ANS:                      ……〔답〕 표시
    SOL: ... ENDSOL:          해답. 기본은 미주, --solutions inline 이면 본문
    UNSURE: 원문              판독 불명 표시

사용
    python make_hwp_from_txt.py -i in.txt -o out.hwp
    python make_hwp_from_txt.py -i in.txt -o out.hwp --template style.hwp
"""

from __future__ import annotations

import argparse
import sys
import time
import re
from collections import Counter
from pathlib import Path

import win32com.client as win32

# convert 가 아니라 예외를 삼키는 래퍼를 쓴다 (깨진 LaTeX 한 줄에 전체가 죽지 않도록)
from latex_to_hwp import latex_to_hwp_equation, pop_unsupported

UNSUPPORTED_TOTAL: Counter = Counter()
UNKNOWN_COMMANDS: Counter = Counter()

ALIGN_ACTIONS = {
    "left": "ParagraphShapeAlignLeft",
    "center": "ParagraphShapeAlignCenter",
    "right": "ParagraphShapeAlignRight",
    "justify": "ParagraphShapeAlignJustify",
    "distribute": "ParagraphShapeAlignDistribute",
}


# ---------------------------------------------------------------------------
# HWP 준비 / 정리
# ---------------------------------------------------------------------------

def check_security_module() -> bool:
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\HNC\HwpAutomation\Modules")
        winreg.QueryValueEx(key, "FilePathCheckerModule")
        return True
    except OSError:
        return False


def start_hwp(visible: bool):
    hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
    if check_security_module():
        hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
    else:
        print("[경고] 보안 모듈 미등록 → Open/SaveAs 마다 접근 허용 팝업이 뜹니다.")
        print("       register_hwp_security.py 를 먼저 실행하세요.")
    hwp.XHwpWindows.Item(0).Visible = visible
    return hwp


def ensure_single_blank_document(hwp) -> None:
    """EnsureDispatch 시점에 이미 빈 문서가 하나 있다. Add 를 또 부르면 2개가 된다."""
    try:
        count = hwp.XHwpDocuments.Count
    except Exception:
        count = 1
    if count == 0:
        hwp.XHwpDocuments.Add(0)


def set_endnote_at_document_end(hwp) -> None:
    """미주를 문서 맨 끝에 모은다.

    기본값이 '구역 끝' 이면 본문 중간에 미주 구분선과 해설이 끼어든다.
    파라미터 이름이 버전마다 달라 여러 후보를 시도하고, 실패해도 그냥 넘어간다.
    """
    try:
        hwp.HAction.GetDefault("FootnoteShape", hwp.HParameterSet.HFootnoteShape.HSet)
        shape = hwp.HParameterSet.HFootnoteShape
    except Exception as error:
        print(f"[참고] 미주 위치 설정을 건너뜁니다: {error}")
        return

    applied = []
    for name, value in (("PlaceEndnote", 1), ("EndnotePlace", 1),
                        ("PlaceType", 1), ("BeneathText", 0)):
        try:
            setattr(shape, name, value)
            applied.append(name)
        except Exception:
            pass

    try:
        hwp.HAction.Execute("FootnoteShape", shape.HSet)
        print(f"[참고] 미주 위치 설정 적용: {applied or '없음'}")
    except Exception as error:
        print(f"[참고] 미주 위치 설정 실패(무시함): {error}")


def shutdown(hwp) -> None:
    """열려 있는 문서를 전부 '저장 안 함'으로 닫은 뒤 종료."""
    try:
        for _ in range(hwp.XHwpDocuments.Count):
            try:
                hwp.XHwpDocuments.Item(0).Close(isDirty=False)
            except Exception:
                break
    except Exception:
        pass
    try:
        hwp.Quit()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 문단 서식
# ---------------------------------------------------------------------------

def set_align(hwp, name: str) -> None:
    action = ALIGN_ACTIONS.get(name.lower())
    if action is None:
        raise ValueError(f"알 수 없는 정렬: {name}")
    hwp.HAction.Run(action)


def set_indent(hwp, left_mm=None, right_mm=None, first_mm=None) -> None:
    hwp.HAction.GetDefault("ParagraphShape", hwp.HParameterSet.HParaShape.HSet)
    shape = hwp.HParameterSet.HParaShape
    if left_mm is not None:
        shape.LeftMargin = hwp.MiliToHwpUnit(left_mm)
    if right_mm is not None:
        shape.RightMargin = hwp.MiliToHwpUnit(right_mm)
    if first_mm is not None:
        shape.Indentation = hwp.MiliToHwpUnit(first_mm)
    hwp.HAction.Execute("ParagraphShape", shape.HSet)


# ---------------------------------------------------------------------------
# 삽입
# ---------------------------------------------------------------------------

# COM 객체에는 임의 속성을 붙일 수 없으므로 상태를 모듈 쪽에 둔다
_BOLD_ON = False


def set_bold(hwp, on: bool) -> None:
    """굵게 켜기/끄기. CharShapeBold 는 토글이라 상태를 직접 관리한다."""
    global _BOLD_ON
    if _BOLD_ON == on:
        return
    try:
        hwp.HAction.Run("CharShapeBold")
        _BOLD_ON = on
    except Exception as error:
        print(f"[경고] 굵게 설정 실패(무시함): {error}")


def open_endnote(hwp):
    """미주를 만들고 커서를 그 안으로 옮긴다.

    성공하면 '들어가기 전 위치'를 돌려준다. 이 위치의 첫 값(리스트 번호)이
    본문을 가리키므로, 나중에 여기로 돌아왔는지 확인하는 기준이 된다.
    실패하면 None.
    """
    try:
        saved = hwp.GetPos()
    except Exception:
        saved = None

    for action in ("InsertEndnote", "Endnote"):
        try:
            hwp.HAction.Run(action)
        except Exception:
            continue
        try:
            # 리스트 번호가 바뀌었으면 실제로 미주 안으로 들어간 것
            if saved is None or hwp.GetPos()[0] != saved[0]:
                return saved if saved is not None else (0, 0, 0)
        except Exception:
            return saved if saved is not None else (0, 0, 0)
    return None


def close_endnote(hwp, saved) -> bool:
    """미주에서 빠져나와 본문 끝으로 돌아간다."""
    for action in ("CloseEx", "Close"):
        try:
            hwp.HAction.Run(action)
        except Exception:
            continue
        try:
            if saved is None or hwp.GetPos()[0] == saved[0]:
                hwp.HAction.Run("MoveDocEnd")
                return True
        except Exception:
            pass

    # 액션이 듣지 않으면 저장해 둔 위치로 직접 이동
    if saved is not None:
        try:
            hwp.SetPos(*saved)
            hwp.HAction.Run("MoveDocEnd")
            return True
        except Exception:
            pass
    print("[경고] 미주에서 빠져나오지 못했습니다. --solutions inline 을 쓰세요.")
    return False


def ensure_body_end(hwp) -> None:
    """커서를 본문의 맨 끝으로 되돌린다.

    미주 편집 영역에 남아 있거나 사용자가 실수로 커서를 옮긴 경우,
    이후 내용이 엉뚱한 자리에 쌓이는 것을 막는다.
    """
    try:
        if hwp.GetPos()[0] != 0:        # 0 이 본문 리스트
            hwp.SetPos(0, 0, 0)
    except Exception:
        pass
    try:
        hwp.HAction.Run("MoveDocEnd")
    except Exception:
        pass


def insert_heading(hwp, text: str, body_align: str) -> None:
    hwp.HAction.Run("BreakPara")
    set_bold(hwp, True)
    insert_text(hwp, text)
    set_bold(hwp, False)
    hwp.HAction.Run("BreakPara")
    set_align(hwp, body_align)


def insert_text(hwp, text: str) -> None:
    if not text:
        return
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    param = hwp.HParameterSet.HInsertText
    try:
        param.Text = text
    except AttributeError:
        param.text = text
    hwp.HAction.Execute("InsertText", param.HSet)


def try_set(obj, name, value) -> None:
    try:
        setattr(obj, name, value)
    except Exception:
        pass


def insert_equation(hwp, source: str, verbose: bool = False, raw: bool = False) -> None:
    script = source if raw else latex_to_hwp_equation(source)
    missing = [] if raw else pop_unsupported()
    if missing:
        UNSUPPORTED_TOTAL.update(missing)
        print(f"[미지원] {sorted(set(missing))}  <-  {source[:60]}")
    if verbose:
        print("LATEX:", source)
        print("HWP  :", script, "\n")

    hwp.HAction.GetDefault("EquationCreate", hwp.HParameterSet.HEqEdit.HSet)
    eq = hwp.HParameterSet.HEqEdit
    try:
        eq.string = script
    except AttributeError:
        eq.String = script

    try_set(eq, "Version", "Equation Version 60")
    try_set(eq, "EqFontName", "HYhwpEQ")
    try_set(eq, "TreatAsChar", 1)
    try_set(eq, "BaseLine", 76)
    try_set(eq, "BaseUnit", 1000)
    try_set(eq, "LineMode", "CHAR")
    try_set(eq, "OutsideMarginLeft", 56)
    try_set(eq, "OutsideMarginRight", 56)

    hwp.HAction.Execute("EquationCreate", eq.HSet)
    hwp.HAction.Run("Cancel")


def insert_display_equation(hwp, source: str, body_align: str, verbose: bool,
                            after_display: bool = False) -> None:
    """독립 행에 가운데 정렬로 수식을 넣는다.

    바로 앞도 독립 수식이었다면 이미 가운데 정렬 문단에 있으므로
    문단을 한 번만 나눈다. 그러지 않으면 연속 수식 사이가 두 배로 벌어진다.
    """
    if not after_display:
        hwp.HAction.Run("BreakPara")
        set_align(hwp, "center")
    insert_equation(hwp, source, verbose)
    hwp.HAction.Run("BreakPara")
    if not after_display:
        set_align(hwp, body_align)


def insert_figure_placeholder(hwp, tag: str, note: str, width_mm: float,
                              height_mm: float, body_align: str) -> None:
    """그림이 들어갈 자리를 눈에 띄는 상자로 표시해 둔다.

    나중에 실제 이미지가 준비되면 이 문단을 IMG: 로 바꾸면 된다.
    한/글에서 '찾기'로 [[FIG 를 검색하면 남은 자리를 모두 찾을 수 있다.
    """
    hwp.HAction.Run("BreakPara")
    set_align(hwp, "center")

    label = f"[[FIG {tag}]] {note}".strip()
    insert_text(hwp, f"┌{'─' * 28}┐")
    hwp.HAction.Run("BreakPara")
    insert_text(hwp, f"  {label}  ")
    hwp.HAction.Run("BreakPara")
    insert_text(hwp, f"  ({width_mm:.0f} x {height_mm:.0f} mm)  ")
    hwp.HAction.Run("BreakPara")
    insert_text(hwp, f"└{'─' * 28}┘")

    hwp.HAction.Run("BreakPara")
    set_align(hwp, body_align)


def insert_image(hwp, path: Path, width_mm: float | None) -> None:
    if not path.exists():
        print(f"[경고] 그림 파일 없음: {path}")
        return
    kwargs = dict(Embedded=True, sizeoption=1, Reverse=False, watermark=False, effect=0)
    if width_mm:
        kwargs["Width"] = hwp.MiliToHwpUnit(width_mm)
    hwp.InsertPicture(str(path.resolve()), **kwargs)


# ---------------------------------------------------------------------------
# DSL
# ---------------------------------------------------------------------------

def parse_kv(spec: str) -> dict:
    result = {}
    for token in spec.split():
        if "=" in token:
            key, value = token.split("=", 1)
            result[key.strip()] = value.strip()
    return result


NO_SPACE_BEFORE = set(" \t([{'\"\u2018\u201c")     # 이 글자 뒤에는 공백을 넣지 않는다
NO_SPACE_AFTER = set(" \t.,;:!?)]}'\"\u2019\u201d")  # 이 글자 앞에는 공백을 넣지 않는다

def is_hangul(char: str) -> bool:
    return "\uac00" <= char <= "\ud7a3"


def needs_space_after_equation(body: str) -> bool:
    """수식 뒤에 오는 텍스트 앞에 공백을 넣어야 하는가.

    한국어는 조사가 앞말에 붙으므로 한글로 시작하면 붙여 쓰는 것이 기본이다.
        EQ: A  +  TEXT: 가 k회   ->  "A가 k회"
        EQ: n  +  TEXT: 회째까지  ->  "n회째까지"
    띄어야 하는 경우에는 DSL 에서 공백을 하나 더 넣어 표시한다.
        TEXT:  정사면체          ->  "A 정사면체"
    """
    if not body:
        return False
    if body[0] in NO_SPACE_AFTER:
        return False
    return not is_hangul(body[0])


def read_paragraph_head(hwp, para: int, length: int = 12):
    """para 번 문단의 앞부분을 읽는다 (검증용). 못 읽으면 None.

    문단 번호 범위를 주는 InitScan 은 미주가 생긴 뒤 엉뚱한 리스트를 읽는 것이
    확인돼서(9/9), 커서를 문단 첫머리에 두고 문단 끝까지 '선택' 한 다음
    선택 영역(Range=0xff)만 읽는 방식으로 바꿨다.
    """
    text = None
    try:
        hwp.SetPos(0, para, 0)
        selected = False
        for action in ("MoveSelParaEnd", "MoveSelLineEnd"):
            try:
                if hwp.HAction.Run(action):
                    selected = True
                    break
            except Exception:
                continue
        if not selected:
            return None
        hwp.InitScan(Range=0xff)
        text = ""
        while True:
            state, chunk = hwp.GetText()
            if state <= 1:
                break
            text += chunk
        hwp.ReleaseScan()
    except Exception:
        try:
            hwp.ReleaseScan()
        except Exception:
            pass
        text = None
    finally:
        try:
            hwp.HAction.Run("Cancel")        # 선택 해제
        except Exception:
            pass
    return text[:length] if text is not None else None


def insert_picture(hwp, image: Path, height_mm: float) -> None:
    """그림을 '글자처럼 취급' 으로 현재 위치에 넣는다. 세로 height_mm, 가로는 비율대로.

    InsertPicture(Path, Embedded, sizeoption, Reverse, watermark, Effect, Width, Height)
      sizeoption=1 : Width/Height(mm) 로 크기 지정.   (9/10 기준 실측 전 — 샘플로 확인할 것)
    """
    try:
        from PIL import Image
        with Image.open(image) as im:
            ratio = im.width / im.height
    except Exception:
        ratio = 1.0
    width_mm = height_mm * ratio
    ctrl = hwp.InsertPicture(str(image), True, 1, False, False, 0, width_mm, height_mm)
    try:
        props = ctrl.Properties
        props.SetItem("TreatAsChar", True)
        ctrl.Properties = props
    except Exception:
        print(f"[경고] 그림 '글자처럼 취급' 설정 실패: {image.name} (문단 정렬이 안 먹을 수 있음)")


def build_goto_map(path) -> dict:
    """기존 hwp 를 한글 없이 읽어 {'12': (문단번호, 'N.' 뒤 위치, '12.')} 를 만든다."""
    import re as _re
    import hwp_read
    result = {}
    paras = hwp_read.paragraphs(str(path))
    heads = []
    for k, text in enumerate(paras):
        m = _re.match(r"^(\s*)(\d{1,3})\.(\s|$)", text)
        if m and m.group(2) not in result:
            number = m.group(2)
            result[number] = [k, len(m.group(1)) + len(number) + 1, number + ".", k]
            heads.append((k, number))
    # 각 문제의 '마지막 내용 문단' = 다음 문제 헤더 앞의 마지막 비어있지 않은 문단 (그림은 그 뒤에 붙인다)
    for i, (k, number) in enumerate(heads):
        end = heads[i + 1][0] if i + 1 < len(heads) else len(paras)
        last = k
        for j in range(k, end):
            if paras[j].strip():
                last = j
        result[number][3] = last
    return {n: tuple(v) for n, v in result.items()}


def build(hwp, lines: list[str], verbose: bool, default_align: str,
          auto_space: bool = True, solutions: str = "endnote",
          progress: int = 200, prob_gap: int = 3,
          goto_map: dict | None = None, img_height_mm: float = 23.0,
          image_dir: Path | None = None) -> None:
    body_align = default_align
    problems_done = 0
    goto_map = goto_map or {}
    in_endnote = None
    last_char = ""          # 직전에 삽입한 본문의 마지막 글자
    pending_eq = False      # 직전에 인라인 수식을 넣었는가
    index = 0
    total = len(lines)
    started = time.time()
    last_report = 0
    last_was_display = False
    prev_was_display = False

    while index < len(lines):
        if progress and index - last_report >= progress:
            last_report = index
            done = index / total if total else 1
            elapsed = time.time() - started
            remain = elapsed / done - elapsed if done > 0 else 0
            print(f"  {index:6d}/{total}줄  ({done:5.1%})  "
                  f"경과 {elapsed / 60:.1f}분  남은 시간 약 {remain / 60:.0f}분",
                  flush=True)

        line = lines[index].rstrip("\r\n")
        stripped = line.strip()
        # EQD: 사이에 낀 BR:/빈 줄은 건너뛰는 줄이므로 '연속 수식' 상태를 깨지 않는다
        if stripped and not stripped.startswith("EQD:") and stripped != "BR:":
            last_was_display = False
            prev_was_display = False

        if not stripped:
            index += 1
            continue

        if stripped == "BR:":
            # 독립 수식(EQD:)은 스스로 앞뒤 문단을 나누므로, 그 바로 앞뒤의 BR: 을
            # 그대로 실행하면 수식 위아래에 빈 줄이 하나씩 생긴다. 건너뛴다.
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            next_stripped = lines[next_index].strip() if next_index < len(lines) else ""
            if next_stripped.startswith("EQD:") or prev_was_display:
                index += 1
                continue
            hwp.HAction.Run("BreakPara")
            last_char = ""
            pending_eq = False
            index += 1
            continue

        if stripped == "NEWPAGE:":
            hwp.HAction.Run("BreakPage")
            last_char = ""
            pending_eq = False
            index += 1
            continue

        if stripped == "SPACE:":
            insert_text(hwp, " ")
            index += 1
            continue

        if line.startswith("ALIGN:"):
            body_align = line[len("ALIGN:"):].strip().lower()
            set_align(hwp, body_align)
            index += 1
            continue

        if line.startswith("INDENT:"):
            values = parse_kv(line[len("INDENT:"):])
            set_indent(
                hwp,
                left_mm=float(values["left"]) if "left" in values else None,
                right_mm=float(values["right"]) if "right" in values else None,
                first_mm=float(values["first"]) if "first" in values else None,
            )
            index += 1
            continue

        if line.startswith(("SUBPROB:", "CHAP:", "TITLE:", "ANSWER:")):
            # 모델이 지어낸 이름들. 내용은 살리고 문단만 나눈다.
            body = line.split(":", 1)[1].strip()
            if body:
                hwp.HAction.Run("BreakPara")
                insert_text(hwp, body)
                last_char = body[-1]
            index += 1
            continue

        if line.startswith(("BLANKBOX:", "FBOX:")):
            insert_text(hwp, " \u25a1 ")   # 답을 써 넣는 네모 칸
            last_char = ""
            index += 1
            continue

        if stripped in ("HLINE:", "TREE:"):
            hwp.HAction.Run("BreakPara")
            last_char = ""; pending_eq = False; index += 1
            continue

        if stripped in ("BOX:", "ENDBOX:"):
            hwp.HAction.Run("BreakPara")     # 상자 테두리는 아직 미구현, 문단만 나눈다
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("SEC:"):
            insert_heading(hwp, line[len("SEC:"):].strip(), body_align)
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("GOTO_END:"):
            # 기존 문서의 N번 문항 본문 마지막 문단 끝으로 (그림은 여기 뒤에 새 문단으로 들어간다)
            if in_endnote is not None:
                set_bold(hwp, False)
                close_endnote(hwp, in_endnote)
                in_endnote = None
            number = line[len("GOTO_END:"):].strip()
            if number not in goto_map:
                raise RuntimeError(f"GOTO_END: {number} — 기존 문서에서 '{number}.' 문항을 못 찾음")
            para, pos, expect, last = goto_map[number]
            head = read_paragraph_head(hwp, para)
            if head is not None and not head.lstrip().startswith(expect):
                raise RuntimeError(f"GOTO_END: {number} — {para}번 문단이 '{expect}' 로 시작하지 않음: {head[:40]!r}")
            hwp.SetPos(0, last, 0)
            hwp.HAction.Run("MoveParaEnd")
            if verbose:
                print(f"  GOTO_END {number}: 문단 {last} 끝")
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("IMG:"):
            # IMG: 파일경로 [| 세로 mm]   -> 가운데 정렬된 새 문단에, 비율 유지, 세로 길이 고정
            parts = [x.strip() for x in line[len("IMG:"):].split("|")]
            image = Path(parts[0])
            height_mm = float(parts[1]) if len(parts) > 1 and parts[1] else img_height_mm
            if not image.is_absolute():
                image = (image_dir / image) if image_dir else image.resolve()
            if not image.exists():
                raise RuntimeError(f"IMG: 파일 없음 {image}")
            hwp.HAction.Run("BreakPara")
            set_align(hwp, "center")
            insert_picture(hwp, image, height_mm)
            hwp.HAction.Run("BreakPara")
            set_align(hwp, body_align)
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("GOTO:"):
            # 기존 문서의 'N.' 문항 헤더 바로 뒤로 커서 이동 (--attach 모드)
            if in_endnote is not None:
                set_bold(hwp, False)
                close_endnote(hwp, in_endnote)
                in_endnote = None
            number = line[len("GOTO:"):].strip()
            if number not in goto_map:
                raise RuntimeError(f"GOTO: {number} — 기존 문서에서 '{number}.' 로 시작하는 문단을 못 찾음")
            para, pos, expect, _last = goto_map[number]
            hwp.SetPos(0, para, pos)
            got = tuple(hwp.GetPos())
            if got[:2] != (0, para):
                raise RuntimeError(f"GOTO: {number} — SetPos(0,{para},{pos}) 후 위치가 {got}")
            head = read_paragraph_head(hwp, para)
            if head is not None and not head.lstrip().startswith(expect):
                raise RuntimeError(f"GOTO: {number} — {para}번 문단이 '{expect}' 로 시작하지 않음: {head[:40]!r}")
            hwp.SetPos(0, para, pos)
            if verbose:
                print(f"  GOTO {number}: 문단 {para}, 위치 {pos}  ({head[:30] if head else '?'})")
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("PROB:"):
            if in_endnote is not None:      # ENDSOL: 이 빠져도 여기서 닫는다
                set_bold(hwp, False)
                close_endnote(hwp, in_endnote)
                in_endnote = None
            number = line[len("PROB:"):].strip()
            ensure_body_end(hwp)        # 커서가 새 나갔으면 본문 끝으로 복귀
            # 문제 사이 간격: 엔터 prob_gap 번 (insert_heading 이 1번 치므로 나머지를 여기서)
            if problems_done > 0:
                for _ in range(max(0, prob_gap - 1)):
                    hwp.HAction.Run("BreakPara")
            problems_done += 1
            insert_heading(hwp, number, body_align)
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("EXAM:"):
            parts = [x.strip() for x in line[len("EXAM:"):].split("|")]
            title = f"【예제 {parts[0]}】" + (f"  {parts[1]}" if len(parts) > 1 else "")
            ensure_body_end(hwp)
            insert_heading(hwp, title, body_align)
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("SOURCE:"):
            hwp.HAction.Run("BreakPara")
            set_align(hwp, "right")
            insert_text(hwp, "(" + line[len("SOURCE:"):].strip() + ")")
            hwp.HAction.Run("BreakPara")
            set_align(hwp, body_align)
            last_char = ""; pending_eq = False; index += 1
            continue

        if stripped == "ANS:":
            index += 1          # 〔답〕 표시는 넣지 않는다
            continue

        if stripped == "SOL:":
            set_bold(hwp, False)
            saved = open_endnote(hwp) if solutions == "endnote" else None
            if saved is not None:
                in_endnote = saved
            else:
                hwp.HAction.Run("BreakPara")
                insert_text(hwp, "[해답]")
                hwp.HAction.Run("BreakPara")
            last_char = ""; pending_eq = False; index += 1
            continue

        if stripped == "ENDSOL:":
            if in_endnote is not None:
                set_bold(hwp, False)
                close_endnote(hwp, in_endnote)
                in_endnote = None
            last_char = ""; pending_eq = False; index += 1
            continue

        if line.startswith("FIX:"):
            index += 1          # 정정 기록은 문서에 넣지 않는다 (보고서로만)
            continue

        if line.startswith("UNSURE:"):
            insert_text(hwp, " [[확인필요: " + line[len("UNSURE:"):].strip() + "]] ")
            last_char = "]"; index += 1
            continue

        if line.startswith("TEXT:"):
            body = line[len("TEXT:"):]
            if body.startswith(" "):
                body = body[1:]
            if auto_space and pending_eq and needs_space_after_equation(body):
                insert_text(hwp, " ")
            insert_text(hwp, body)
            if body:
                last_char = body[-1]
            pending_eq = False
            index += 1
            continue

        if line.startswith("EQD:"):
            # 다음 '실질' 줄을 본다 (사이에 낀 BR:/빈 줄은 어차피 건너뛰므로).
            # 그래야 EQD: BR: EQD: 도 연속 수식으로 인식되어 사이에 빈 문단이 안 생긴다.
            look = index + 1
            while look < len(lines) and lines[look].strip() in ("", "BR:"):
                look += 1
            next_line = lines[look].strip() if look < len(lines) else ""
            insert_display_equation(hwp, line[len("EQD:"):].strip(), body_align,
                                    verbose, last_was_display)
            last_was_display = next_line.startswith("EQD:")
            prev_was_display = True
            if not last_was_display:
                set_align(hwp, body_align)
            index += 1
            continue

        if line.startswith("RAWEQ:"):
            # 한글 수식 스크립트를 변환 없이 그대로 넣는다 (표기 실험용)
            insert_equation(hwp, line[len("RAWEQ:"):].strip(), verbose, raw=True)
            last_char = ""; pending_eq = True; index += 1
            continue

        if line.startswith("EQ:"):
            if auto_space and last_char and last_char not in NO_SPACE_BEFORE:
                insert_text(hwp, " ")
            insert_equation(hwp, line[len("EQ:"):].strip(), verbose)
            last_char = ""
            pending_eq = True
            index += 1
            continue

        if line.startswith("IMG:"):
            spec = line[len("IMG:"):].strip()
            if "|" in spec:
                raw_path, raw_width = spec.split("|", 1)
                width = float(raw_width.strip().rstrip("m"))
            else:
                raw_path, width = spec, None
            insert_image(hwp, Path(raw_path.strip()), width)
            index += 1
            continue

        if line.startswith("FIG:"):
            parts = [x.strip() for x in line[len("FIG:"):].split("|")]
            tag = parts[0] if parts else "?"
            note = parts[1] if len(parts) > 1 else ""
            size = parts[2] if len(parts) > 2 else "70x50"
            try:
                w_mm, _, h_mm = size.lower().replace("mm", "").partition("x")
                width_mm, height_mm = float(w_mm), float(h_mm or 50)
            except ValueError:
                width_mm, height_mm = 70.0, 50.0
            insert_figure_placeholder(hwp, tag, note, width_mm, height_mm, body_align)
            last_char = ""
            pending_eq = False
            index += 1
            continue

        if stripped == "EQALIGN:":
            rows = []
            index += 1
            while index < len(lines) and lines[index].strip() != "END:":
                if lines[index].strip():
                    rows.append(lines[index].strip())
                index += 1
            insert_display_equation(hwp, " \\\\ ".join(rows), body_align, verbose)
            if index < len(lines):
                index += 1
            continue

        # 모르는 명령 때문에 전체 작업이 죽지 않도록 한다.
        # DSL 명령처럼 생겼으면 건너뛰고, 아니면 본문으로 취급한다.
        if re.match(r"^[A-Z][A-Z0-9_]{1,12}:", stripped):
            UNKNOWN_COMMANDS[stripped.split(":")[0]] += 1
        else:
            insert_text(hwp, stripped)
            last_char = stripped[-1] if stripped else ""
        index += 1
        continue


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", required=True, type=Path)
    parser.add_argument("-o", "--output", required=True, type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--align", default="justify",
                        choices=sorted(ALIGN_ACTIONS), help="본문 기본 정렬")
    parser.add_argument("--solutions", default="endnote",
                        choices=["endnote", "inline"],
                        help="해답을 미주로 뺄지 본문에 이어 붙일지")
    parser.add_argument("--no-auto-space", action="store_true",
                        help="본문과 인라인 수식 사이 공백 자동 삽입을 끈다")
    parser.add_argument("--attach", type=Path,
                        help="기존 hwp 를 열어 그 안의 'N.' 문항에 GOTO:/SOL: 로 미주를 붙인다 (-o 는 다른 이름)")
    parser.add_argument("--img-height-mm", type=float, default=23.0,
                        help="IMG: 그림의 세로 길이(mm). 본문 4줄 ≈ 23mm (10pt, 줄간격 160%% 기준)")
    parser.add_argument("--image-dir", type=Path, default=None,
                        help="IMG: 의 상대 경로를 이 폴더 기준으로 찾는다")
    parser.add_argument("--prob-gap", type=int, default=3,
                        help="문제와 문제 사이 엔터 횟수 (기본 3)")
    parser.add_argument("--invisible", action="store_true", default=True,
                        help="한글 창을 숨기고 실행 (기본값)")
    parser.add_argument("--visible", dest="invisible", action="store_false",
                        help="한글 창을 보이게 실행 (디버깅용)")
    parser.add_argument("--progress", type=int, default=200,
                        help="몇 줄마다 진행률을 찍을지 (0 이면 끄기)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    output = args.output.resolve()
    lines = args.input.read_text(encoding="utf-8").splitlines()

    goto_map = {}
    if args.attach:
        if args.attach.resolve() == output:
            print("--attach 원본과 -o 가 같습니다. 원본을 보존하려면 -o 에 다른 이름을 주세요.")
            return 1
        goto_map = build_goto_map(args.attach.resolve())
        wanted = [l.split(":", 1)[1].strip() for l in lines if l.startswith("GOTO:")]
        missing = [n for n in wanted if n not in goto_map]
        print(f"기존 문서 문항 {len(goto_map)}개, DSL 의 GOTO {len(wanted)}개, 못 찾음 {len(missing)}개")
        if missing:
            print("  못 찾은 번호:", ", ".join(missing)); return 1

    hwp = start_hwp(visible=not args.invisible)
    try:
        if args.attach:
            hwp.Open(str(args.attach.resolve()))
        elif args.append and output.exists():
            hwp.Open(str(output))
            hwp.HAction.Run("MoveDocEnd")
            hwp.HAction.Run("BreakPara")
        elif args.template:
            hwp.Open(str(args.template.resolve()))
            hwp.HAction.Run("MoveDocEnd")
        else:
            ensure_single_blank_document(hwp)

        set_endnote_at_document_end(hwp)
        set_align(hwp, args.align)
        build(hwp, lines, args.verbose, args.align,
              not args.no_auto_space, args.solutions, args.progress,
              prob_gap=args.prob_gap, goto_map=goto_map,
              img_height_mm=args.img_height_mm,
              image_dir=args.image_dir.resolve() if args.image_dir else None)
        hwp.HAction.Run("MoveDocEnd")
        hwp.SaveAs(str(output), "HWP")
        if output.exists():
            print(f"저장 완료: {output}  ({output.stat().st_size:,} bytes)")
        else:
            print(f"[경고] SaveAs 는 호출됐으나 파일이 없습니다: {output}")
            print("       보안 모듈 미등록이면 접근 허용 팝업을 눌러야 저장됩니다.")
    except Exception as error:
        print(f"[실패] {error}", file=sys.stderr)
        raise
    finally:
        shutdown(hwp)

    if UNKNOWN_COMMANDS:
        print("\n=== 알 수 없는 DSL 명령 (건너뜀) ===")
        for name, count in UNKNOWN_COMMANDS.most_common():
            print(f"  {count:4d}  {name}:")

    if UNSUPPORTED_TOTAL:
        print("\n=== 미지원 명령 빈도 ===")
        for name, count in UNSUPPORTED_TOTAL.most_common():
            print(f"  {count:3d}  {name}")


if __name__ == "__main__":
    main()
