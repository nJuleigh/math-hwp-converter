r"""임시.tex -> DSL(.txt) 변환기.

`make_hwp_from_txt.py` 가 먹는 DSL 로 바꾼다. 규칙 요약:

    \noindent\textbf{예제 3-1. 연의 총수}   ->  PROB: 예제 3-1. 연의 총수
    \noindent\textbf{문제 5-1. ...}         ->  PROB: 문제 5-1. ...
    \noindent\textbf{123.}                  ->  PROB: 123.
    \noindent\textbf{해설}                  ->  SOL:  ... ENDSOL:   (미주)

    \[ ... \]      ->  EQD: ...   (여러 줄이면 한 줄로 접음)
    \(...\)        ->  EQ: ...
    빈 줄          ->  BR:
    \bigskip       ->  BR:
    \newpage       ->  NEWPAGE:

그림 자리표시자는 tex 에 적힌 형식을 그대로 둔다.
  * 본문에 보이는 것 (\textit{[그림 필요: ...]})  -> TEXT: 로 그대로 노출
  * 주석으로만 있는 것 (% [그림 필요: ...])       -> FIX: 로 보존 (문서에는 안 들어감)

사용
    python tex_to_dsl.py -i 임시.tex -o 임시_dsl.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# 정규식
# ---------------------------------------------------------------------------

# 헤더. 닫는 중괄호 뒤에 다른 내용이 붙는 경우가 있으므로 줄 끝 앵커를 걸지 않는다.
# (예: \noindent\textbf{예제 3-9. 평면에서의 색칠} [그림 필요: ...])
HEADER = re.compile(r"^\\noindent\\textbf\{")

DISPLAY = re.compile(r"(?<!\\)\\\[(.*?)(?<!\\)\\\]", re.S)
INLINE = re.compile(r"(?<!\\)\\\((.*?)(?<!\\)\\\)", re.S)

EQD_TOKEN = "\x00EQD%d\x00"
EQD_TOKEN_RE = re.compile(r"\x00EQD(\d+)\x00")

EQ_TOKEN = "\x00EQ%d\x00"
EQ_TOKEN_RE = re.compile(r"\x00EQ(\d+)\x00")

FIGURE_NOTE = re.compile(r"\[그림 필요:")
FIGURE_LIST_ITEM = re.compile(r"^\\noindent\s+(예제\s*\d+-\d+|\d{1,3}번)\s+\\textbf\{\[그림 필요")

# 본문(수식 밖)에서 만나는 명령. 값은 대체 문자열.
TEXT_COMMANDS = {
    r"\noindent": "",
    r"\bigskip": "\x00BR\x00",
    r"\medskip": "\x00BR\x00",
    r"\smallskip": "\x00BR\x00",
    r"\newpage": "\x00NEWPAGE\x00",
    r"\clearpage": "\x00NEWPAGE\x00",
    r"\par": "\x00BR\x00",
    r"\centering": "",
    r"\hfill": " ",
    r"\,": " ",
    r"\;": " ",
    r"\ ": " ",
    r"\quad": "  ",
    r"\qquad": "    ",
    r"\%": "%",
    r"\&": "&",
    r"\_": "_",
    r"\#": "#",
    r"\$": "$",
    r"\{": "{",
    r"\}": "}",
    r"\ldots": "…",
    r"\cdots": "…",
    r"\dots": "…",
}

# {...} 인자를 하나 받고 내용만 남기는 본문 명령
UNWRAP_ONE = ("textbf", "textit", "emph", "text", "mbox", "underline", "textrm")

UNKNOWN_TEXT_COMMANDS: Counter = Counter()
UNRENDERED_HEADINGS: list[str] = []

# 제목 줄 안의 수식은 EQ: 로 뺄 수 없다 (PROB: 은 한 줄짜리 굵은 글씨 한 덩어리).
# 다행히 제목에 쓰인 수식은 변수 이름과 곱셈 기호 수준이라 유니코드로 그대로 쓴다.
HEADING_MATH = {
    r"\times": "×", r"\cdot": "·", r"\ldots": "…", r"\cdots": "…",
    r"\dots": "…", r"\quad": " ", r"\qquad": " ", r"\,": "", r"\;": "",
    r"\le": "≤", r"\ge": "≥", r"\ne": "≠", r"\pm": "±",
}
SUBSCRIPT_CHARS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ",
    "a": "ₐ", "e": "ₑ", "o": "ₒ", "x": "ₓ", "h": "ₕ",
}


def math_to_plain(body: str) -> str:
    """제목 안의 짧은 수식을 유니코드 본문 글자로 편다."""
    for name, value in HEADING_MATH.items():
        body = body.replace(name, value)
    # X_1 / A_i -> X₁ / Aᵢ
    body = re.sub(
        r"_\{?([0-9A-Za-z])\}?",
        lambda m: SUBSCRIPT_CHARS.get(m.group(1), "_" + m.group(1)),
        body,
    )
    if re.search(r"\\[a-zA-Z]+", body):
        UNRENDERED_HEADINGS.append(body)
        body = re.sub(r"\\[a-zA-Z]+\s*", "", body)
    return body.replace("{", "").replace("}", "")


def heading_text(label: str) -> str:
    """헤더 라벨에서 \\(...\\) 를 걷어내고 한 줄짜리 제목 문자열로 만든다."""
    label = INLINE.sub(lambda m: math_to_plain(m.group(1)), label)
    for name, value in HEADING_MATH.items():
        label = label.replace(name, value)
    label = label.replace("--", "–")
    return re.sub(r"\s{2,}", " ", label).strip()


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------


def take_braced(text: str, start: int) -> tuple[str, int]:
    """text[start] 가 '{' 일 때 짝이 맞는 '}' 까지의 내용과 다음 위치를 돌려준다."""
    assert text[start] == "{"
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":            # 이스케이프된 중괄호는 건너뛴다
            index += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
        index += 1
    raise ValueError("중괄호 짝이 맞지 않습니다: " + text[start:start + 40])


def unwrap_commands(text: str) -> str:
    """\textbf{X} 류를 X 로 편다. 중첩도 처리한다."""
    changed = True
    while changed:
        changed = False
        for name in UNWRAP_ONE:
            pattern = "\\" + name + "{"
            position = text.find(pattern)
            if position < 0:
                continue
            inner, after = take_braced(text, position + len(pattern) - 1)
            text = text[:position] + inner + text[after:]
            changed = True
    return text


def flatten_equation(body: str) -> str:
    r"""여러 줄 수식을 한 줄로 접는다. \\ 로 끊기는 줄바꿈은 보존."""
    body = body.replace("\r", "")
    # \\[2mm] 처럼 붙은 간격 지정은 버린다 (한글 수식에 대응물이 없다)
    body = re.sub(r"\\\\\s*\[[^\]]*\]", r"\\\\ ", body)
    body = re.sub(r"\s*\n\s*", " ", body)
    body = re.sub(r"[ \t]{2,}", " ", body)
    return body.strip()


# 첫 행 = \begin{array}{..} (앞에 \hline 이 올 수도 있음) 부터 첫 \\ 까지
ARRAY_HEAD = re.compile(r"(\\begin\{array\}\{[^}]*\}\s*(?:\\hline)?)(.*?)(\\\\)", re.S)


def bold_table_header(body: str) -> str:
    r"""\hline 로 머리글을 구분한 array 의 첫 행 \text{...} 를 \textbf{...} 로.
    한글 수식 matrix 에는 가로줄이 없어서, 머리글을 굵게 해 표 느낌을 살린다."""
    if "\\hline" not in body:
        return body
    def repl(m: re.Match) -> str:
        head = m.group(2).replace("\\text{", "\\textbf{")
        return m.group(1) + head + m.group(3)
    return ARRAY_HEAD.sub(repl, body)


def convert_tags(body: str) -> str:
    r"""\tag{1} -> \qquad\text{(1)}. 한글 수식에는 번호 태그가 없다."""
    def repl(match: re.Match) -> str:
        return r"\qquad\text{(" + match.group(1) + ")}"
    return re.sub(r"\\tag\*?\{([^{}]*)\}", repl, body)


# ---------------------------------------------------------------------------
# 본문 조각 -> DSL 줄
# ---------------------------------------------------------------------------


ITEM_STACK: list = []


def number_items(run: str) -> str:
    r"""enumerate 의 \item -> (1) (2) ..., itemize 의 \item -> ·.  \item[라벨] 은 라벨 그대로.
    환경 시작/끝은 문단 나누기로만 남긴다. 중첩 enumerate 는 안쪽부터 따로 센다."""
    out = []
    stack = ITEM_STACK    # 문단이 갈려도 (항목 안에 디스플레이 수식이 있으면 문단이 나뉜다) 번호가 이어지도록 전역
    pos = 0
    token = re.compile(r"\\begin\{(enumerate|itemize)\}|\\end\{(enumerate|itemize)\}|\\item\s*(?:\[([^\]]*)\])?\s*")
    for m in token.finditer(run):
        out.append(run[pos:m.start()])
        pos = m.end()
        if m.group(1):
            stack.append([m.group(1), 0]); out.append("\x00BR\x00")
        elif m.group(2):
            if stack: stack.pop()
            out.append("\x00BR\x00")
        else:
            if m.group(3) is not None:
                label = m.group(3)
            elif stack and stack[-1][0] == "enumerate":
                stack[-1][1] += 1; label = f"({stack[-1][1]})"
            else:
                label = "·"
            out.append("\x00BR\x00" + label + " ")
    out.append(run[pos:])
    return "".join(out)


def emit_text_run(run: str, out: list[str], inlines: list[str]) -> None:
    """본문 덩어리 하나를 TEXT:/EQ:/EQD:/BR: 줄들로 바꿔 out 에 넣는다."""
    run = unwrap_commands(run)

    # 남은 본문 명령 치환
    for name, value in TEXT_COMMANDS.items():
        run = run.replace(name, value)

    run = number_items(run)

    run = run.replace("--", "–")

    # 처리하지 못한 명령 수집 후 제거
    for name in re.findall(r"\\([a-zA-Z]+)", run):
        UNKNOWN_TEXT_COMMANDS[name] += 1
    run = re.sub(r"\\[a-zA-Z]+\s*", "", run)

    # 토큰 단위로 쪼개서 순서대로 방출
    for piece in re.split(r"(\x00BR\x00|\x00NEWPAGE\x00|\x00EQD\d+\x00|\x00EQ\d+\x00)", run):
        if not piece:
            continue
        if piece == "\x00BR\x00":
            out.append("BR:")
        elif piece == "\x00NEWPAGE\x00":
            out.append("NEWPAGE:")
        elif EQD_TOKEN_RE.fullmatch(piece):
            out.append(piece)          # 나중에 실제 EQD: 로 바꿔 넣는다
        elif EQ_TOKEN_RE.fullmatch(piece):
            out.append("EQ: " + inlines[int(EQ_TOKEN_RE.fullmatch(piece).group(1))])
        else:
            # 원문의 줄바꿈은 LaTeX 에서 공백 한 칸이다 (490군데 모두 어절 경계).
            piece = re.sub(r"\s+", " ", piece)
            if piece.strip():
                out.append("TEXT: " + piece.strip())


def emit_paragraph(paragraph: str, equations: list[str], out: list[str]) -> None:
    r"""문단 하나를 DSL 로. 인라인 수식은 EQ:, 디스플레이는 EQD: 로 나간다.

    \textbf{... \(x\) ...} 처럼 본문 명령이 인라인 수식을 감싸는 경우가 있으므로,
    수식을 먼저 토큰으로 빼둔 뒤에 본문 명령을 편다. 순서를 뒤집으면 중괄호가
    수식 경계에서 잘려 짝이 깨진다.
    """
    inlines: list[str] = []

    def stash(match: re.Match) -> str:
        inlines.append(convert_tags(flatten_equation(match.group(1))))
        return EQ_TOKEN % (len(inlines) - 1)

    paragraph = INLINE.sub(stash, paragraph)

    staged: list[str] = []
    emit_text_run(paragraph, staged, inlines)

    for line in staged:
        token = EQD_TOKEN_RE.fullmatch(line)
        if token:
            out.append("EQD: " + equations[int(token.group(1))])
        else:
            out.append(line)


# ---------------------------------------------------------------------------
# 메인 변환
# ---------------------------------------------------------------------------


def normalize_dollars(source: str) -> str:
    r"""$$...$$ -> \[...\],  $...$ -> \(...\).  \$ (달러 기호 자체) 는 보존."""
    protected = source.replace(r"\$", "\x00DOLLAR\x00")
    protected = re.sub(r"\$\$(.+?)\$\$", lambda m: "\\[" + m.group(1) + "\\]", protected, flags=re.S)
    protected = re.sub(r"\$(.+?)\$", lambda m: "\\(" + m.group(1) + "\\)", protected, flags=re.S)
    return protected.replace("\x00DOLLAR\x00", r"\$")


def normalize_top_level_environments(source: str) -> str:
    r"""\begin{align*}..\end{align*} 처럼 \[ \] 없이 쓰는 디스플레이 환경을
    \[\begin{aligned}..\end{aligned}\] 로 감싼다 (7장에서 align* 28회)."""
    def wrap(m):
        name, body = m.group(1), m.group(2)
        inner = "aligned" if name.startswith("align") else "gathered"
        return "\\[\n\\begin{" + inner + "}" + body + "\\end{" + inner + "}\n\\]"
    return re.sub(r"\\begin\{(align\*?|gather\*?|equation\*?|multline\*?)\}(.*?)\\end\{\1\}",
                  wrap, source, flags=re.S)


def relabel(label: str, mode: str, counter: list[int]) -> tuple[str, str | None]:
    """--renumber 처리. (새 라벨, 대조표용 원래 라벨 or None) 을 돌려준다."""
    # '문제 487' (7장 형식) 은 번호형과 같게 취급, '문제 7.1' 은 라벨형
    # '123.' / '문제 487' / '문제 1.'  모두 번호형.  '문제 7.1' '예제 3-1.' 은 라벨형
    is_bare = (re.match(r"^\d{1,3}\.\s*(.*)$", label)
               or re.match(r"^문제\s*\d{1,3}[a-z]?\.?(?![.\d-])\s*(.*)$", label)    # '문제 4a.' 도 번호형
               or re.match(r"^Problem\s*\d{0,3}[a-z]?\.?\s*(.*)$", label))
    if mode == "numbered" and is_bare:
        rest = is_bare.group(1)
        new = f"{counter[0]}." + (" " + rest if rest else "")
        counter[0] += 1
        return new, label
    if mode == "all":
        # '예제 3-1. 연의 총수' / '문제 5-1. ...' / '123.' -> 'N. 제목'
        m = re.match(r"^(?:예제|문제)\s*\d+[-.]\d+\.?\s*(.*)$", label) or is_bare
        rest = m.group(1) if m else label
        new = f"{counter[0]}." + (" " + rest if rest else "")
        counter[0] += 1
        return new, label
    return label, None


def apply_xrefs(lines: list[str], mapping: list[tuple[str, str]]) -> tuple[list[str], list[str], list[str]]:
    r"""본문 안의 교차 참조를 새 번호로 바꾼다.

    바꾸는 것
      * '예제 3-8' / '문제 5-1'  -> '12번'   (라벨이 대조표에 있을 때)
      * '123번'                  -> '1번'    단, [그림 필요] 줄에서만.
        본문의 '동전을 5번 던질 때' 같은 '횟수' 표현과 구분할 방법이 없어서
        일반 본문의 'N번' 은 손대지 않는다 (원고에 142건, 전부 횟수 의미).
    돌려주는 것: (바뀐 줄들, 치환 기록, 대조표에 없어 못 바꾼 참조)
    """
    table: dict[str, str] = {}
    for old, new in mapping:
        m = (re.match(r"^((?:예제|문제)\s*\d+[-.]\d+)\.?", old)
             or re.match(r"^문제\s*(\d{1,3}[a-z]?)\.?(?![.\d-])", old)
             or re.match(r"^Problem\s*(\d{0,3}[a-z]?)", old)
             or re.match(r"^(\d{1,3})\.", old))
        key = m.group(1).replace(" ", "")
        table[key] = re.match(r"^(\d+)\.", new).group(1)

    changed, unresolved = [], []
    relabeled_labels = any(not k[0].isdigit() for k in table)   # 예제/문제 라벨이 바뀐 모드인가
    out = []
    for line in lines:
        if not line.startswith(("TEXT:", "FIX:")):
            out.append(line); continue
        original = line

        def labeled(m: re.Match) -> str:
            key = (m.group(1) + m.group(2)).replace(" ", "")
            if key in table:
                return table[key] + "번"
            if relabeled_labels:          # 라벨을 번호로 바꾼 모드인데 표에 없음 -> 진짜 미해결
                unresolved.append(m.group(0) + "  ←  " + original[:60])
            return m.group(0)
        line = re.sub(r"(예제|문제)\s*(\d+[-.]\d+)", labeled, line)

        if "그림 필요" in line:
            line = re.sub(r"(?<![\d-])(\d{1,3})번",
                          lambda m: (table.get(m.group(1), m.group(1))) + "번", line)
        if line != original:
            changed.append(original[:50] + "  →  " + line[:50])
        out.append(line)
    return out, changed, unresolved


def convert(source: str, solutions: str = "endnote", renumber: str = "none",
            start: int = 1) -> tuple[list[str], dict]:
    if "\\begin{document}" in source:
        source = source.split("\\begin{document}", 1)[1]
    source = source.rsplit("\\end{document}", 1)[0]
    source = normalize_dollars(source)
    source = normalize_top_level_environments(source)

    # --- 주석 분리 -------------------------------------------------------
    # 연속된 주석 줄은 한 덩어리로 합친다 (그림 설명이 두세 줄에 걸친 곳이 6군데)
    figure_notes: list[tuple[int, str]] = []
    kept: list[str] = []
    pending: list[str] = []

    def flush_comment() -> None:
        if pending:
            note = " ".join(pending)
            if FIGURE_NOTE.search(note):
                figure_notes.append((len(kept), note))
            pending.clear()

    for line in source.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("%"):
            pending.append(stripped.lstrip("%").strip())
            continue
        flush_comment()
        kept.append(line)
    flush_comment()
    body = "\n".join(kept)

    # --- 그림 체크리스트 수집 (본문 어디에 있든 해당 문제 끝에 붙인다) ----------
    # '\\noindent 예제 3-2 \\textbf{[그림 필요: ...]}' / '\\noindent 123번 \\textbf{[그림 필요: ...]}'
    # tex 작성 시 3장 예제 끝에 몰아서 적힌 것. 각 항목을 가리키는 문제의 본문 끝에 넣는다.
    figure_for: dict[str, list[str]] = {}
    remaining = []
    for line in kept:
        m = FIGURE_LIST_ITEM.match(line)
        if m:
            key = m.group(1).replace(" ", "").rstrip("번")
            note = unwrap_commands(line.replace("\\noindent", "", 1))
            note = re.sub(r"^\s*(?:예제\s*\d+-\d+|\d{1,3}번)\s*", "", note).strip()
            figure_for.setdefault(key, []).append(note)
        else:
            remaining.append(line)
    kept = remaining
    body = "\n".join(kept)
    stats_figures = sum(len(v) for v in figure_for.values())

    # --- 디스플레이 수식을 토큰으로 빼둔다 --------------------------------
    equations: list[str] = []

    def stash(match: re.Match) -> str:
        equations.append(convert_tags(bold_table_header(flatten_equation(match.group(1)))))
        return "\n" + (EQD_TOKEN % (len(equations) - 1)) + "\n"

    body = DISPLAY.sub(stash, body)

    # --- 줄 단위 처리 -----------------------------------------------------
    out: list[str] = []
    buffer: list[str] = []
    in_solution = False
    counter = [start]
    mapping: list[tuple[str, str]] = []
    current_key = ""
    ITEM_STACK.clear()
    stats = Counter()
    pending_notes = {index: note for index, note in figure_notes}

    def flush() -> None:
        if not buffer:
            return
        emit_paragraph("\n".join(buffer), equations, out)
        buffer.clear()

    def close_solution() -> None:
        nonlocal in_solution
        if in_solution:
            flush()
            out.append("ENDSOL:")
            in_solution = False

    lines = body.split("\n")
    for index, raw in enumerate(lines):
        line = raw.rstrip()

        if index in pending_notes:
            flush()
            out.append("FIX: " + pending_notes[index])

        if not line.strip():
            flush()
            if out and out[-1] != "BR:":
                out.append("BR:")
            continue

        # '\noindent 예제 3-2 \textbf{[그림 필요: ...]}' 꼴의 그림 체크리스트 (3장 예제 끝에 41줄).
        # 직전 해설(미주) 안에 딸려 들어가면 안 되므로 해설을 닫고 FIX: 로 보존만 한다.
        if HEADER.match(line):
            position = line.index("{")
            label, after = take_braced(line, position)
            label = unwrap_commands(label).strip()
            rest = line[after:].strip()

            flush()
            attach = re.match(r"^(\d{1,3})\s*번\s*해설\s*[.:：]?\s*(.*)$", label)
            if attach:
                # 'N번 해설.' : 기존 hwp 의 N번 문항에 미주로 붙이는 용도 (make_hwp --attach)
                close_solution()
                out.append("GOTO: " + attach.group(1))
                out.append("SOL:")
                in_solution = True
                stats["문제"] += 1
                stats["해설"] += 1
                if attach.group(2):          # '19번 해설. 미적분학 3 범위이므로 생략 가능' 의 뒷부분
                    buffer.append(attach.group(2))
                if rest:
                    buffer.append(rest)
                continue
            if re.fullmatch(r"(해설|Solution|Proof)\s*[.:：]?", label, re.I):
                for note in figure_for.pop(current_key, []):
                    emit_paragraph(note, equations, out)
                    stats["그림메모"] += 1
                close_solution()
                if solutions == "inline":
                    out.append("SEC: 해설")          # 굵은 '해설' 줄, 본문에 그대로
                else:
                    out.append("SOL:")
                    in_solution = True
                stats["해설"] += 1
            else:
                close_solution()
                km = (re.match(r"^((?:예제|문제)\s*\d+[-.]\d+)", label)
                      or re.match(r"^문제\s*(\d{1,3}[a-z]?)", label) or re.match(r"^(\d{1,3})\.", label)
                      or re.match(r"^Problem\s*(\d{0,3}[a-z]?)", label))
                current_key = km.group(1).replace(" ", "") if km else ""
                new_label, old_label = relabel(heading_text(label), renumber, counter)
                if old_label is not None:
                    mapping.append((old_label, new_label))
                out.append("PROB: " + new_label)
                stats["문제"] += 1
            if rest:
                buffer.append(rest)
            continue

        buffer.append(line)

    flush()
    close_solution()

    # 연속 BR: 을 최대 하나로 (문단 사이 여백은 한글에서 따로 준다)
    cleaned: list[str] = []
    for line in out:
        if line == "BR:":
            last_real = next((l for l in reversed(cleaned) if not l.startswith("FIX:")), "")
            if last_real == "BR:":
                continue
        cleaned.append(line)
    while cleaned and cleaned[0] == "BR:":
        cleaned.pop(0)

    # PROB:/SOL: 은 자체 문단을 만들고 미주는 첫 줄이 비면 안 되므로,
    # 그 직후의 BR: 과 ENDSOL:/PROB: 직전의 BR: 은 뺀다 (이전 DSL 과 같은 꼴).
    trimmed: list[str] = []
    for index, line in enumerate(cleaned):
        if line == "BR:":
            prev = next((l for l in reversed(trimmed) if not l.startswith("FIX:")), "")
            nxt = next((l for l in cleaned[index + 1:] if not l.startswith("FIX:")), "")
            if prev == "SOL:" or prev.startswith(("PROB:", "GOTO:")):
                continue
            if nxt in ("ENDSOL:", "SOL:", "") or nxt.startswith(("PROB:", "GOTO:")):
                continue
        trimmed.append(line)
    cleaned = trimmed

    stats["EQD"] = sum(1 for line in cleaned if line.startswith("EQD:"))
    stats["EQ"] = sum(1 for line in cleaned if line.startswith("EQ:"))
    stats["TEXT"] = sum(1 for line in cleaned if line.startswith("TEXT:"))
    stats["FIX"] = sum(1 for line in cleaned if line.startswith("FIX:"))
    stats["mapping"] = mapping
    stats["그림메모_미배치"] = {k: v for k, v in figure_for.items()}
    stats["xref_changed"], stats["xref_unresolved"] = [], []
    if mapping:
        cleaned, stats["xref_changed"], stats["xref_unresolved"] = apply_xrefs(cleaned, mapping)
    return cleaned, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="임시.tex -> DSL 변환")
    parser.add_argument("-i", "--input", type=Path, required=True, nargs="+",
                        help="tex 파일 (여러 개면 순서대로 이어 붙여 한 DSL 로)")
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--solutions", choices=("endnote", "inline"), default="endnote",
                        help="해설을 미주(SOL:)로 뺄지, 본문에 굵은 '해설' 제목으로 둘지")
    parser.add_argument("--renumber", choices=("none", "numbered", "all"), default="none",
                        help="numbered: 번호만 있는 문제(123.)를 1부터 다시 매김 / "
                             "all: 예제·문제 포함 전부 1부터")
    parser.add_argument("--start", type=int, default=1, help="다시 매길 때 시작 번호")
    args = parser.parse_args()

    for path in args.input:
        if path.resolve() == args.output.resolve():
            print(f"입력과 출력이 같은 파일입니다: {path}\n원본 tex 가 덮어써집니다. -o 에 다른 이름을 주세요.")
            return 1
    pieces = []
    for path in args.input:
        text = path.read_text(encoding="utf-8")
        if "\\begin{document}" in text:
            text = text.split("\\begin{document}", 1)[1]
        text = text.rsplit("\\end{document}", 1)[0]
        pieces.append(text)
    source = "\n\n".join(pieces)
    lines, stats = convert(source, args.solutions, args.renumber, args.start)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if stats["xref_changed"]:
        print(f"\n교차 참조 {len(stats['xref_changed'])}건을 새 번호로 바꿈:")
        for item in stats["xref_changed"]:
            print("   ", item)
    if stats["xref_unresolved"]:
        print(f"\n[확인 필요] 대조표에 없어 못 바꾼 참조 {len(stats['xref_unresolved'])}건 (tex 에서 직접 손볼 것):")
        for item in stats["xref_unresolved"]:
            print("   ", item)
    if stats["mapping"]:
        table = args.output.with_name(args.output.stem + "_numbermap.txt")
        table.write_text("\n".join(f"{old}\t->\t{new}" for old, new in stats["mapping"]) + "\n",
                         encoding="utf-8")
        print(f"번호 대조표(numbermap): {table}  ({len(stats['mapping'])}건, "
              f"{stats['mapping'][0][1].split('.')[0]}~{stats['mapping'][-1][1].split('.')[0]})")

    print(f"저장: {args.output}  ({len(lines):,}줄)")
    for name in ("문제", "해설", "TEXT", "EQ", "EQD", "FIX", "그림메모"):
        print(f"  {name:5s} {stats[name]:6,d}")
    if stats["그림메모_미배치"]:
        print("  [확인 필요] 붙일 문제를 못 찾은 그림 메모:", stats["그림메모_미배치"])

    if UNKNOWN_TEXT_COMMANDS:
        print("\n=== 본문에서 처리하지 못하고 지운 명령 ===")
        for name, count in UNKNOWN_TEXT_COMMANDS.most_common():
            print(f"  {count:5d}  \\{name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
