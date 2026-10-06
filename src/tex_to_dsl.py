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
HEADER = re.compile(r"^(?:\\medskip\s*|\\bigskip\s*|\\smallskip\s*|\\noindent\s*)*\\textbf\{")
SECTION = re.compile(r"^\\(?:section|subsection|subsubsection|paragraph|chapter)\*?\{")

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
UNWRAP_ONE = ("textbf", "textit", "emph", "text", "mbox", "underline", "textrm", "textup", "textsc", "texttt", "textnormal", "textsf", "textmd")

UNKNOWN_TEXT_COMMANDS: Counter = Counter()
UNRENDERED_HEADINGS: list[str] = []

# 제목 줄 안의 수식은 EQ: 로 뺄 수 없다 (PROB: 은 한 줄짜리 굵은 글씨 한 덩어리).
# 다행히 제목에 쓰인 수식은 변수 이름과 곱셈 기호 수준이라 유니코드로 그대로 쓴다.
HEADING_MATH = {
    r"\leq": "≤", r"\geq": "≥", r"\neq": "≠",
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
DEFAULT_ENUM_STYLE = "num"


def number_items(run: str) -> str:
    r"""enumerate 의 \item -> (1) (2) ..., itemize 의 \item -> ·.  \item[라벨] 은 라벨 그대로.
    환경 시작/끝은 문단 나누기로만 남긴다. 중첩 enumerate 는 안쪽부터 따로 센다."""
    out = []
    stack = ITEM_STACK    # 문단이 갈려도 (항목 안에 디스플레이 수식이 있으면 문단이 나뉜다) 번호가 이어지도록 전역
    pos = 0
    token = re.compile(r"\\begin\{(enumerate|itemize)\}(?:\s*\[(.*?)\](?!\}))?|\\end\{(enumerate|itemize)\}|\\item\s*(?:\[([^\]]*)\])?\s*")
    for m in token.finditer(run):
        out.append(run[pos:m.start()])
        pos = m.end()
        if m.group(1):
            style = DEFAULT_ENUM_STYLE
            opt = m.group(2) or ""
            tmpl = None
            lm = re.search(r"label\s*=\s*(.+?)(?:,\s*[a-z]+\s*=|$)", opt)
            if lm:
                tmpl = re.sub(r"\\(?:textbf|bfseries|textit|emph|rm|sf)\s*", "", lm.group(1)).strip()
                tmpl = tmpl[1:-1].strip() if tmpl.startswith("{") and tmpl.endswith("}") else tmpl
                if not re.search(r"\\(?:arabic|alph|Alph|roman|Roman)\*", tmpl):
                    tmpl = None
            if "alph" in opt: style = "alph"
            elif "roman" in opt: style = "roman"
            stack.append([m.group(1), 0, style, tmpl]); out.append("\x00BR\x00")
        elif m.group(3):
            if stack: stack.pop()
            out.append("\x00BR\x00")
        else:
            if m.group(4) is not None:
                label = m.group(4)
            elif stack and stack[-1][0] == "enumerate":
                stack[-1][1] += 1; k = stack[-1][1]
                st = stack[-1][2] if len(stack[-1]) > 2 else "num"
                tmpl = stack[-1][3] if len(stack[-1]) > 3 else None
                roman = ['i','ii','iii','iv','v','vi','vii','viii','ix','x']
                if tmpl:      # label=\textbf{1-\arabic*.} 같은 사용자 템플릿
                    label = tmpl
                    for pat, val in ((r"\\arabic\*", str(k)), (r"\\alph\*", chr(96 + k)), (r"\\Alph\*", chr(64 + k)),
                                     (r"\\roman\*", roman[k - 1] if k <= 10 else str(k)), (r"\\Roman\*", (roman[k - 1] if k <= 10 else str(k)).upper())):
                        label = re.sub(pat, val, label)
                    label = label.replace("{", "").replace("}", "")
                else:
                    label = f"({k})" if st == "num" else (f"({chr(96 + k)})" if st == "alph" else f"({roman[k-1]})")
            else:
                label = "·"
            out.append("\x00BR\x00" + label + " ")
    out.append(run[pos:])
    return "".join(out)


def emit_text_run(run: str, out: list[str], inlines: list[str]) -> None:
    """본문 덩어리 하나를 TEXT:/EQ:/EQD:/BR: 줄들로 바꿔 out 에 넣는다."""
    run = number_items(run)          # enumerate 옵션의 \textbf 가 벗겨지기 전에 먼저 (라벨 템플릿 보존)
    run = unwrap_commands(run)

    # 남은 본문 명령 치환
    for name, value in TEXT_COMMANDS.items():
        run = run.replace(name, value)

    run = re.sub(r"\\\\(\[[^\]]*\])?", "\x00BR\x00", run)      # 본문 강제 줄바꿈
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
            piece = re.sub(r"\s+", " ", piece).replace("{", "").replace("}", "")
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


def substitute_args(bodytxt: str, args: list[str]) -> str:
    r"""매크로 본문의 #1,#2... 를 인자로 바꾼다.

    TeX 는 토큰 단위로 끼워 넣으므로 \left\lVert#1\right\rVert 에 N 을 넣으면 \lVert 와 N 은 따로다.
    문자열로 그냥 이어 붙이면 \lVertN 이라는 없는 명령이 되므로, 필요한 자리에 공백을 넣는다.
    """
    pieces = re.split(r"#(\d)", bodytxt)
    out = pieces[0]
    for k in range(1, len(pieces), 2):
        index = int(pieces[k]) - 1
        arg = args[index] if 0 <= index < len(args) else ""
        tail = pieces[k + 1] if k + 1 < len(pieces) else ""
        if arg and arg[0].isalpha() and re.search(r"\\[A-Za-z]+$", out):
            out += " "
        out += arg
        if tail[:1].isalpha() and re.search(r"\\[A-Za-z]+$", out):
            out += " "
        out += tail
    return out


IFNUM = re.compile(r"\\ifnum\s*(-?\d+)\s*(=|<|>)\s*(-?\d+)\s*"
                   r"((?:(?!\\ifnum|\\else|\\fi).)*)"
                   r"(?:\\else((?:(?!\\ifnum|\\fi).)*))?\\fi", re.S)


def resolve_ifnum(body: str) -> str:
    r"""매크로를 전개한 뒤 남는 \ifnum 16=16 ... \else ... \fi 를 실제로 판정한다 (중첩 없는 단순형)."""
    for _ in range(20):
        new = IFNUM.sub(lambda m: (m.group(4) if {"=": m.group(1) == m.group(3),
                                                  "<": int(m.group(1)) < int(m.group(3)),
                                                  ">": int(m.group(1)) > int(m.group(3))}[m.group(2)]
                                   else (m.group(5) or "")), body)
        if new == body:
            break
        body = new
    return body


STAR_RATING = re.compile(r"\\foreach\s*\\[A-Za-z]+\s*in\s*\{\s*1\s*,\s*\.\.\.\s*,\s*(\d+)\s*\}.*?\\ifnum\s*\\[A-Za-z]+\s*>\s*#1", re.S)


def expand_macros(full_source: str, body: str) -> str:
    r"""프리앰블의 \newcommand{\X}[n]{...} / \newcommand{\X}{...} 를 본문에서 문자 치환으로 전개."""
    macros = []
    star_macros: dict[str, int] = {}
    # \input{…} 로 불러오는 프리앰블이 없을 때를 대비한 흔한 기본 매크로 (문서에 정의가 있으면 그쪽이 우선)
    defined = set(re.findall(r"\\(?:re)?newcommand\{\\([A-Za-z]+)\}|\\DeclareMathOperator\*?\{\\([A-Za-z]+)\}", full_source))
    defined = {a or b for a, b in defined}
    for name, rep in (("R", "\\mathbb{R}"), ("N", "\\mathbb{N}"), ("Z", "\\mathbb{Z}"), ("Q", "\\mathbb{Q}"), ("C", "\\mathbb{C}")):
        if name not in defined and re.search(r"\\" + name + r"(?![A-Za-z])", body):
            macros.append((name, 0, rep))
    for m in re.finditer(r"\\DeclareMathOperator\*?\{\\([A-Za-z]+)\}\{([^{}]*)\}", full_source):
        macros.append((m.group(1), 0, "\\operatorname{" + m.group(2) + "}"))
    for m in re.finditer(r"\\(?:re)?newcommand\{\\([A-Za-z]+)\}(?:\[(\d)\])?\{", full_source):
        name, nargs = m.group(1), int(m.group(2) or 0)
        bodytxt, _ = take_braced(full_source, m.end() - 1)
        # 매크로 본문 줄 끝의 '%' 는 줄바꿈을 먹는 주석이다 (전개한 뒤에는 주석 제거가 끝나 있으므로 여기서 지운다)
        bodytxt = re.sub(r"(?<!\\)%[^\n]*\n[ \t]*", "", bodytxt)
        bodytxt = re.sub(r"(?<!\\)%[^\n]*$", "", bodytxt)
        star = STAR_RATING.search(bodytxt) if "tikzpicture" in bodytxt else None
        if star and nargs == 1:
            # 별점 그림(\foreach \i in {1,...,5} ... \ifnum \i > #1)은 ★☆ 글자로 그린다
            star_macros[name] = int(star.group(1))
            continue
        macros.append((name, nargs, bodytxt))
    # 이름이 긴 것부터 (\\Range 와 \\R 구분)
    for name, nargs, bodytxt in sorted(macros, key=lambda t: -len(t[0])):
        pat = re.compile(r"\\" + name + r"(?![A-Za-z])")
        pos = 0
        while True:
            m = pat.search(body, pos)
            if not m:
                break
            args = []; end = m.end()
            for _ in range(nargs):
                while end < len(body) and body[end] in " \t": end += 1
                if end < len(body) and body[end] == "{":
                    a, end = take_braced(body, end); args.append(a)
                elif end < len(body) and body[end] == "\\":
                    # \norm A 처럼 중괄호 없이 한 토큰만 주는 TeX 관례
                    tok = re.match(r"\\[A-Za-z]+|\\.", body[end:])
                    args.append(tok.group(0)); end += tok.end()
                elif end < len(body) and body[end] not in "\n}]&$%":
                    args.append(body[end]); end += 1
                else:
                    args.append("")
            rep = substitute_args(bodytxt, args)
            body = body[:m.start()] + rep + body[end:]
            pos = m.start() + len(rep)
    for name, total in star_macros.items():
        def stars(m, total=total):
            try: filled = max(0, min(total, int(m.group(1).strip())))
            except ValueError: return ""
            return "★" * filled + "☆" * (total - filled)
        body = re.sub(r"\\" + name + r"(?![A-Za-z])\s*\{([^{}]*)\}", stars, body)
    if star_macros:   # '$★★☆☆☆$' 처럼 수식으로 감싸져 있으면 수식 표시를 벗긴다
        body = re.sub(r"(?<!\\)\$\s*([★☆]+)\s*\$", r"\1", body)
        body = re.sub(r"\\\(\s*([★☆]+)\s*\\\)", r"\1", body)
    body = resolve_ifnum(body)
    # \newenvironment{problem}[1][]{...} 류: \begin{problem}[옵션] -> 'Problem N. (옵션)' 헤더로
    env_names = re.findall(r"\\newenvironment\{([A-Za-z]+)\}", full_source)
    for name in ("problem", "solution", "exercise", "example"):
        if name not in env_names and re.search(r"\\begin\{" + name + r"\}", body):
            env_names.append(name)
    env_counters: dict[str, int] = {}
    for name in env_names:
        word = {"problem": "Problem", "solution": "Solution", "exercise": "Problem", "example": "Example",
                "proof": "Proof", "theorem": "Theorem", "lemma": "Lemma", "remark": "Remark"}.get(name.lower(), name.capitalize())
        def begin(m, word=word, name=name):
            env_counters[name] = env_counters.get(name, 0) + 1
            opt = (" (" + m.group(1).strip() + ")") if m.group(1) else ""
            return "\n\n\\noindent\\textbf{" + word + " " + str(env_counters[name]) + "." + opt + "}\n"
        body = re.sub(r"\\begin\{" + name + r"\}(?:\[([^\]]*)\])?", begin, body)
        body = re.sub(r"\\end\{" + name + r"\}", "\n\n", body)
    # \refstepcounter{prob} ... \theprob : 매크로로 번호를 자동 매기는 문서 (Putnam 파일)
    counters: dict[str, int] = {}
    def step(m):
        counters[m.group(1)] = counters.get(m.group(1), 0) + 1; return ""
    def the(m):
        return str(counters.get(m.group(1), 0))
    names = set(re.findall(r"\\(?:newcounter|refstepcounter|stepcounter)\{([A-Za-z]+)\}", full_source + body))
    if not names:
        return re.sub(r"\\par(?![A-Za-z])", "\n\n", body)
    out = []; pos = 0
    # \theta 같은 명령과 섞이지 않게, 선언된 카운터 이름만 \the<name> 으로 인식
    for m in re.finditer(r"\\(?:refstepcounter|stepcounter)\{([A-Za-z]+)\}|\\the(" + "|".join(sorted(names, key=len, reverse=True)) + r")(?![A-Za-z])", body):
        out.append(body[pos:m.start()])
        if m.group(1): step(m)
        else: out.append(str(counters.get(m.group(2), 0)))
        pos = m.end()
    out.append(body[pos:]); body = "".join(out)
    body = re.sub(r"\\par(?![A-Za-z])", "\n\n", body)
    return body


# 인자 두 개를 받는 조판 명령 (두 번째 {} 까지 지운다)
LAYOUT_CMDS2 = re.compile(r"\\(?:setlength|setcounter|addtocounter|pdfbookmark|bookmark|hypertarget|markboth)(?:\[[^\[\]]*\])?\{[^{}]*\}\{[^{}]*\}")
# 인자 한 개를 받는 조판 명령
LAYOUT_CMDS = re.compile(r"\\(?:vspace\*?|hspace\*?|addvspace|Needspace\*?|needspace|label|pagestyle|thispagestyle|enlargethispage|typeout|markright)(?:\[[^\[\]]*\])?\{[^{}]*\}")
# 인자 없이 쓰는 조판 명령 (지워도 본문이 달라지지 않는 것)
BARE_LAYOUT_CMDS = re.compile(r"\\(?:hrule|hrulefill|hfill|vfill|null|thepage|phantomsection|ignorespaces|nobreak|begingroup|endgroup|bgroup|egroup|relax|leavevmode)(?![A-Za-z])")
# \hangindent=2em, \hangafter=1 같은 TeX 치수/숫자 대입
TEX_ASSIGN = re.compile(r"\\(?:hangindent|hangafter|parindent|parskip|baselineskip|lineskip|leftskip|rightskip|hsize|vsize|hoffset|voffset|looseness|clubpenalty|widowpenalty)\s*=?\s*-?[\d.]*\s*(?:em|ex|pt|mm|cm|in|sp|bp|dd|pc)?\s*(?:plus[^\\\n]*)?")
# \makebox[2em][l]{(1)} / \raisebox{..}{X} / \parbox[t]{..}{X} : 내용만 남긴다
BOX_CMDS = re.compile(r"\\(?:makebox|framebox|mbox|fbox|raisebox|parbox|resizebox|scalebox|hbox|vbox)\s*(?:\[[^\[\]]*\]|\{[-\d.]*\s*(?:em|ex|pt|mm|cm|in)?\})*\s*(?=\{)")
SIZE_CMDS = re.compile(r"\\(?:Large|large|LARGE|huge|Huge|small|footnotesize|scriptsize|tiny|normalsize|bfseries|itshape|centering)\b")
# '{\large\bfseries 제목}' 처럼 크기+굵게로만 만든 제목 (\section 을 안 쓰는 문서)
TITLE_GROUP = re.compile(r"\{\s*((?:\\(?:large|Large|LARGE|huge|Huge|bfseries|sffamily|itshape)\s*){2,})")


def promote_title_groups(body: str) -> str:
    out = []; pos = 0
    while True:
        m = TITLE_GROUP.search(body, pos)
        if not m:
            break
        prefix = m.group(1)
        if not (re.search(r"large|Large|LARGE|huge|Huge", prefix) and "bfseries" in prefix):
            out.append(body[pos:m.end()]); pos = m.end(); continue
        try:
            inner, end = take_braced(body, m.start())
        except ValueError:
            out.append(body[pos:m.end()]); pos = m.end(); continue
        inner = SIZE_CMDS.sub("", inner).strip()
        if not inner or "\n\n" in inner:          # 제목 한 줄이 아니면 건드리지 않는다
            out.append(body[pos:end]); pos = end; continue
        out.append(body[pos:m.start()])
        # \textbf 헤더로 넘겨 준다: 번호가 붙어 있으면 뒤에서 문제/해설 헤더로, 아니면 절 제목으로 처리된다
        out.append("\n\n\\textbf{" + inner + "}\n\n")
        pos = end
    out.append(body[pos:])
    return "".join(out)


SECTION_CMD = re.compile(r"\\(?:sub){0,2}section\*?\s*(?=\{)|\\(?:chapter|part|paragraph|subparagraph)\*?\s*(?=\{)")


def isolate_sections(body: str) -> str:
    r"""\section*{...} 을 반드시 한 줄로 떼어 놓는다.

    매크로를 전개하면 '\clearpage\section*{문제 1-(2)}' 처럼 줄 중간에 붙어 나오는데,
    절 제목은 줄 머리에서만 알아보기 때문에 그대로 두면 본문 글자로 섞여 버린다.
    """
    out = []; pos = 0
    while True:
        m = SECTION_CMD.search(body, pos)
        if not m:
            break
        try:
            inner, end = take_braced(body, m.end())
        except ValueError:
            pos = m.end(); continue
        out.append(body[pos:m.start()])
        out.append("\n\n" + m.group(0).strip() + "{" + inner + "}\n\n")
        pos = end
    out.append(body[pos:])
    return "".join(out)


def normalize_layout(body: str) -> str:
    # 줄 머리의 '{\large\textbf{제목}}' 류 -> 절 제목
    body = re.sub(r"(?m)^\s*\{\s*\\(?:large|Large|LARGE|huge|Huge)\s*\\(?:textbf|bfseries)\s*\{(.*)\}\s*\}\s*(\\\\)?\s*$",
                  lambda m: "\n\\section*{" + m.group(1) + "}\n", body)
    # 글을 감싸기만 하는 환경 (quote, minipage ...) 은 문단 구분으로 바꾼다
    body = re.sub(r"\\(?:begin|end)\{(?:quote|quotation|verse|flushleft|flushright|minipage|multicols\*?|small|footnotesize|spacing|adjustwidth)\}"
                  r"(?:\[[^\[\]]*\]|\{[^{}]*\})*", "\n\n", body)
    # \hspace 는 지우되 자리에 공백을 남긴다 ('1번\hspace{.65em}★★☆☆☆' 가 붙지 않게).
    # \quad 류는 수식 안에서 쓰이므로 여기서 건드리지 않는다.
    body = protect_math_then(body, lambda t: re.sub(r"\\(?:hspace\*?|hskip)\s*(?:\{[^{}]*\}|[-\d.]+\s*(?:em|ex|pt|mm|cm|in))", " ", t))
    body = LAYOUT_CMDS2.sub("", body)
    body = LAYOUT_CMDS.sub("", body)
    body = BOX_CMDS.sub("", body)          # \makebox[2em][l]{(1)} -> {(1)}
    body = TEX_ASSIGN.sub("", body)
    body = promote_title_groups(body)
    body = BARE_LAYOUT_CMDS.sub("", body)
    body = SIZE_CMDS.sub("", body)
    # \begin{center} ... \end{center} : 줄마다 굵은 제목 줄로
    def center(m):
        inner = m.group(1).replace("\\\\", "\n")
        inner = re.sub(r"\[[0-9.]+(?:em|mm|pt|cm)\]", "", inner)
        lines = [l.strip() for l in inner.split("\n") if l.strip()]
        return "\n\n" + "\n\n".join(l if l.startswith("\\section*{") else "\\section*{" + l + "}" for l in lines) + "\n\n"
    body = re.sub(r"\\begin\{center\}(.*?)\\end\{center\}", center, body, flags=re.S)
    return isolate_sections(body)


def resolve_eqrefs(body: str) -> str:
    r"""\eqref{lbl} -> (번호).  \tag{2.1}\label{lbl} 이면 (2.1), 그 밖에 equation 환경 안 \label 은 등장 순서로 (1),(2),..."""
    numbers: dict[str, str] = {}
    for m in re.finditer(r"\\tag\*?\{([^{}]*)\}\s*\\label\{([^{}]*)\}|\\label\{([^{}]*)\}\s*\\tag\*?\{([^{}]*)\}", body):
        if m.group(1): numbers[m.group(2)] = m.group(1)
        else: numbers[m.group(3)] = m.group(4)
    k = 0
    for m in re.finditer(r"\\begin\{equation\}(.*?)\\end\{equation\}", body, re.S):
        k += 1
        for lm in re.finditer(r"\\label\{([^{}]*)\}", m.group(1)):
            numbers.setdefault(lm.group(1), str(k))
    body = re.sub(r"\\eqref\{([^{}]*)\}", lambda m: "(" + numbers.get(m.group(1), "?") + ")", body)
    body = re.sub(r"\\ref\{([^{}]*)\}", lambda m: numbers.get(m.group(1), "?"), body)
    body = body.replace("\\tableofcontents", "")
    return body


ACCENTS = {"v": "\u030c", "'": "\u0301", "`": "\u0300", '"': "\u0308", "^": "\u0302", "~": "\u0303", "c": "\u0327", "=": "\u0304", "u": "\u0306", ".": "\u0307"}


def normalize_text_mode(body: str) -> str:
    """수식 밖 텍스트의 LaTeX 표기를 유니코드로: 악센트(\\v{c} \\'{c}), ``..'', ---, --, 그룹 크기명령."""
    import unicodedata
    def acc(m):
        mark = ACCENTS.get(m.group(1)); ch = m.group(2) or m.group(3)
        return unicodedata.normalize("NFC", ch + mark) if mark and ch else m.group(0)
    body = re.sub(r"\\([vcu])\s*\{([A-Za-z])\}()", acc, body)                 # \v{c} : 중괄호 필수
    body = re.sub(r"\\(['`\"^~=.])\s*(?:\{([A-Za-z])\}|([A-Za-z]))", acc, body)   # \'{c} 또는 \'c
    body = body.replace("``", "\u201c").replace("''", "\u201d")
    body = body.replace("---", "\u2014")
    def circled(m):
        c = m.group(1)
        if c.isdigit() and c != "0": return chr(0x2460 + int(c) - 1)      # ①②③
        if "a" <= c <= "z": return chr(0x24d0 + ord(c) - 97)             # ⓐⓑⓒ
        if "A" <= c <= "Z": return chr(0x24b6 + ord(c) - 65)             # ⒜ 아님: Ⓐ
        return c
    body = re.sub(r"\\textcircled\s*\{\s*(?:\\[a-zA-Z]+\s*)?([0-9A-Za-z])\s*\}", circled, body)
    return body


def protect_math_then(body: str, fn) -> str:
    """수식 부분은 건드리지 않고 나머지 텍스트에만 fn 적용."""
    pat = re.compile(r"(\$\$.*?\$\$|\$.*?\$|\\\(.*?\\\)|\\\[.*?\\\]|\\begin\{(align\*?|aligned|equation\*?|gather\*?|array|pmatrix|bmatrix|vmatrix|cases)\}.*?\\end\{\2\})", re.S)
    out = []; pos = 0
    for m in pat.finditer(body):
        out.append(fn(body[pos:m.start()])); out.append(m.group(0)); pos = m.end()
    out.append(fn(body[pos:]))
    return "".join(out)


def strip_preamble(source: str) -> str:
    r"""\documentclass … \begin{document} 프리앰블 블록을 (여러 개라도) 모두 제거한다.

    \documentclass 앞에 본문 조각이 붙어 있거나, 여러 문서가 한 파일에 이어진 경우가 있어서
    \begin{document} 앞을 통째로 버리지 않는다. 남은 \begin{document}/\end{document} 표시도 지운다.
    """
    while True:
        start = source.find("\\documentclass")
        if start == -1:
            break
        m = re.search(r"\\begin\{document\}", source[start:])
        if m:
            source = source[:start] + source[start + m.end():]
            continue
        # \begin{document} 가 없는 프리앰블: 프리앰블 성격의 줄만 걸러내고 본문은 남긴다
        head, tail = source[:start], source[start:].split("\n")
        keep, done = [], False
        for line in tail:
            if not done and (not line.strip()
                             or re.match(r"\s*%", line)
                             or re.match(r"\s*\\(?:documentclass|usepackage|RequirePackage|geometry|setmainfont|setsansfont|pagestyle|fancyhf|fancyhead|fancyfoot|linespread|setlist|setlength|hypersetup|author|date)\b", line)
                             or re.match(r"\s*[a-z]+\s*=", line) or re.match(r"\s*\}\s*$", line)):
                continue
            done = True; keep.append(line)
        source = head + "\n".join(keep)
        break
    source = re.sub(r"\\(?:begin|end)\{document\}", "", source)
    return source


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


def reorder_bound_solutions(out: list[str]) -> list[str]:
    """'SOL@3' 해설 블록을 그 앞에 나온 가장 가까운 'PROB@3' 문제 블록 끝으로 옮긴다.
    (같은 번호가 절마다 반복돼도 — Additional Problems 1~5 처럼 — 직전 것에 붙는다)"""
    units = []; cur = None
    for line in out:
        if line.startswith(("PROB@", "PROB:", "SOL@")):
            cur = [line]; units.append(cur)
        elif cur is None:
            units.append([line])
        else:
            cur.append(line)
            if line == "ENDSOL:" and cur[0].startswith("SOL@"):
                cur = []; units.append(cur)          # 해설이 닫힌 뒤 내용은 별도 단위 (절 제목 등)
    has_problem = any(u and u[0].startswith(("PROB@", "PROB:", "GOTO:")) for u in units)
    if not has_problem:
        # 해설만 있는 문서: 미주로 만들 대상이 없으니 굵은 제목 + 본문으로 편다
        result = []
        for line in out:
            m = re.match(r"^SOL@[^|]*\|(.*)$", line)
            if m: result.append("SEC: " + m.group(1))
            elif line == "SOL:": result.append("SEC: 해설")
            elif line == "ENDSOL:": pass
            else: result.append(line)
        return result
    if not any(u[0].startswith("SOL@") for u in units):
        return [re.sub(r"^PROB@[^:]*:\s*", "PROB: ", l) if l.startswith("PROB@") else l for l in out]
    attach: dict[int, list] = {}
    for i, u in enumerate(units):
        m = re.match(r"^SOL@([^|]+)\|", u[0]) if u else None
        if not m:
            continue
        target = None
        for j in range(i - 1, -1, -1):
            pm = re.match(r"^PROB@([^:]*):", units[j][0]) if units[j] else None
            if pm and pm.group(1) == m.group(1):
                target = j; break
        if target is None:
            u[0] = "SOL:"                     # 짝을 못 찾으면 제자리에 그냥 둔다
        else:
            attach.setdefault(target, []).append(u)
    result = []
    for i, u in enumerate(units):
        if not u:
            continue
        if u[0].startswith("SOL@"):
            continue
        if u[0].startswith("PROB@"):
            result.append(re.sub(r"^PROB@[^:]*:\s*", "PROB: ", u[0]))
            result.extend(l for l in u[1:] if not re.fullmatch(r"SEC:\s*(?!.*Problem)(?:[^\n]{0,12}\s)?(?:Solutions?\b.*|Answers?\b.*|해설|해답|풀이)\s*", l))
            for su in attach.get(i, []):
                result.append("SOL:"); result.extend(su[1:])
                if result[-1] != "ENDSOL:": result.append("ENDSOL:")
            continue
        result.extend(l for l in u if not re.fullmatch(r"SEC:\s*(?!.*Problem)(?:[^\n]{0,12}\s)?(?:Solutions?\b.*|Answers?\b.*|해설|해답|풀이)\s*", l))   # 'Solutions' 절 제목은 뺀다
    return result


def convert(source: str, solutions: str = "endnote", renumber: str = "none",
            start: int = 1, full_source: str | None = None) -> tuple[list[str], dict]:
    full_source = full_source or source
    source = strip_preamble(source)
    source = expand_macros(full_source, source)
    # \maketitle -> 프리앰블의 \title{...} 을 굵은 제목 줄로
    if "\\maketitle" in source:
        tm = re.search(r"\\title\{", full_source)
        title = take_braced(full_source, tm.end() - 1)[0] if tm else ""
        title = re.sub(r"\\\\\s*(\[[^\]]*\])?", " – ", title); title = re.sub(r"\s+", " ", title).strip()
        source = source.replace("\\maketitle", ("\n\\section*{" + title + "}\n") if title else "", 1)
    source = resolve_eqrefs(source)

    tikz_note = "\n\n[그림: 원문 tikz 그림]\n\n"
    source = re.sub(r"\\begin\{center\}\s*\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}\s*\\end\{center\}", tikz_note, source, flags=re.S)
    source = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", tikz_note, source, flags=re.S)
    # 문제부/해설부를 가르는 제목: 가운데 정렬 '해설/해답', 또는 \section*{Solution|해설|해답|...}
    hm = (re.search(r"\\begin\{center\}[^{}]*\{?\s*(?:\\[A-Za-z]+\s*)*[^{}\n]*(?:해설|해답|풀이|Solutions?)[^{}\n]*\}?\s*\\end\{center\}", source, re.I)
          or re.search(r"\\(?:sub)?section\*?\{\s*(?:해설|해답|풀이|Solutions?)\s*\}", source, re.I))
    if hm:
        head, tail = source[:hm.end()], source[hm.end():]
        # 해설부의 \section*{(3)} / {[3]} / {3} -> '(3) 해설' 헤더 (문제 번호에 묶인 해설)
        tail = re.sub(r"\\(?:sub)?section\*?\{\s*[\(\[]?(\d{1,3})[\)\]]?\s*\}", r"\\noindent\\textbf{(\1) 해설}", tail)
        source = head + tail
    source = re.sub(r"(\\begin\{(?:enumerate|itemize)\})\s*\[(.*?)\](?!\})",
                    lambda m: m.group(1) + "[" + " ".join(m.group(2).split()) + "]", source, flags=re.S)
    source = normalize_layout(source)
    source = protect_math_then(source, normalize_text_mode)
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
    has_solutions = bool(re.search(r"\\textbf\{[^{}]*(?:해설|Solution|Proof|풀이)", source))
    paren_problems = bool(re.search(r"\\textbf\{\(\d{1,3}\)\s*해설", source))   # '(3) 해설' 형식 문서인가
    ITEM_STACK.clear()
    global DEFAULT_ENUM_STYLE
    sl = re.search(r"\\setlist\[enumerate[^\]]*\]\{[^}]*label=\(?\\(alph|roman|arabic)", full_source)
    DEFAULT_ENUM_STYLE = {"alph": "alph", "roman": "roman"}.get(sl.group(1), "num") if sl else "num"
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
        if re.match(r"^\s+\\(?:noindent|medskip|bigskip|smallskip)?\s*\\textbf\{", line):
            line = line.lstrip()          # 매크로 전개로 앞에 공백이 붙은 굵은 헤더 줄

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
        if SECTION.match(line):
            position = line.index("{")
            label, after = take_braced(line, position)
            flush()
            if not (in_solution and re.match(r"^\\(?:subsection|subsubsection|paragraph)", line)):
                close_solution()
            out.append("SEC: " + heading_text(unwrap_commands(label)).replace("{", "").replace("}", "").strip())
            if line[after:].strip():
                buffer.append(line[after:].strip())
            continue

        if HEADER.match(line) and (line.startswith(("\\noindent", "\\medskip", "\\bigskip", "\\smallskip")) or index == 0
                                   or not lines[index - 1].strip() or lines[index - 1].strip() in ("\\noindent", "\\newpage", "\\medskip", "\\bigskip", "\\smallskip")):
            position = line.index("{")
            label, after = take_braced(line, position)
            label = unwrap_commands(label).strip()
            rest = line[after:].strip()
            # '\\textbf{Problem 1.} \\textbf{(20 points)}' / '... \\hfill \\textbf{[7 points]}' -> 제목에 합침
            rest_plain = unwrap_commands(re.sub(r"\\\\(?:hfill|quad|qquad)", " ", rest)).strip()
            if rest_plain and len(rest_plain) <= 30 and rest_plain[0] in "([":
                label = label + " " + rest_plain; rest = ""

            flush()
            attach = re.match(r"^(\d{1,3})\s*번\s*해설\s*[.:：]?\s*(.*)$", label)
            if attach:
                close_solution()
                out.append("GOTO: " + attach.group(1)); out.append("SOL:")
                in_solution = True; stats["문제"] += 1; stats["해설"] += 1
                if attach.group(2): buffer.append(attach.group(2))
                if rest: buffer.append(rest)
                continue

            # 번호가 붙은 해설: 'Solution to Problem 3.' / '(3) 해설' -> 그 번호 문제 뒤로 옮긴다
            bound = (re.match(r"^(?:문제|예제|Problem)\s*(\d{1,3}[a-z]?)\s*(?:해설|풀이|Solution)\s*[.:：]?$", label, re.I)
                     or re.match(r"^Solution\s+(?:to|of|for)\s+Problem\s*(\d{1,3}[a-z]?)\.?\s*$", label, re.I)
                     or re.match(r"^Solution\s*(\d{1,3}[a-z]?)\.?\s*$", label, re.I)
                     or re.match(r"^\((\d{1,3})\)\s*해설\s*[.:：]?$", label))
            if bound:
                close_solution()
                out.append("SOL@" + bound.group(1) + "|" + heading_text(label))   # 재배치 표시 (마지막에 정리)
                in_solution = True; stats["해설"] += 1
                if rest: buffer.append(rest)
                continue

            if re.fullmatch(r"(해설|Solution|Proof)\s*[.:：]?", label, re.I):
                for note in figure_for.pop(current_key, []):
                    emit_paragraph(note, equations, out); stats["그림메모"] += 1
                close_solution()
                if solutions == "inline":
                    out.append("SEC: 해설")
                else:
                    out.append("SOL:"); in_solution = True
                stats["해설"] += 1
                if rest: buffer.append(rest)
                continue

            label = re.sub(r"^\[(\d{1,3})\]\s*$", r"(\1)", label)      # '[3]' 도 문항 번호로
            if (re.match(r"^\(\d{1,3}\)\s*$", label) and not paren_problems) or (
                    re.match(r"^\([a-zA-Z가-힣\d]{1,3}\)", label) and not re.match(r"^\(\d{1,3}\)\s*$", label)):
                buffer.append(unwrap_commands(line))      # 하위 문항 라벨 (1) (a) (가) ... : 본문 그대로
                continue
            if (not has_solutions) and re.match(r"^\d{1,3}\.\s*\S", label):
                close_solution(); out.append("SEC: " + heading_text(label))   # '1. 요약.' : 보고서의 절 번호
                if rest: buffer.append(rest)
                continue
            is_problem = (re.match(r"^(?:예제|문제)\s*\d", label) or re.match(r"^(?:예제|문제)\s*[.:：]?$", label)
                          or re.match(r"^\[\d{1,3}\]\s*(?:문제|예제|Problem\b)", label, re.I)
                          or re.match(r"^\d{1,3}\s*번(?:\s|$|[★☆])", label)
                          or re.match(r"^\d{1,3}\.", label)
                          or re.match(r"^(?:Bonus\s+|Extra\s+|Challenge\s+)?Problem\b", label, re.I) or re.match(r"^\(\d{1,3}\)\s*$", label))
            if is_problem:
                close_solution()
                km = (re.match(r"^((?:예제|문제)\s*\d+[-.]\d+)", label)
                      or re.match(r"^\[(\d{1,3})\]\s*(?:문제|예제|Problem\b)", label, re.I)
                      or re.match(r"^(\d{1,3})\s*번(?:\s|$|[★☆])", label)
                      or re.match(r"^문제\s*(\d{1,3}[a-z]?)", label) or re.match(r"^(\d{1,3})\.", label)
                      or re.match(r"^Problem\s*(\d{0,3}[a-z]?)", label, re.I) or re.match(r"^\((\d{1,3})\)", label))
                current_key = km.group(1).replace(" ", "") if km else ""
                if re.match(r"^\((\d{1,3})\)\s*$", label):
                    prob_id = km.group(1)                # '(3)' 형식은 재배치용 번호를 따로 기억
                    out.append("PROB@" + prob_id + ": " + heading_text(label))
                else:
                    pm = (re.match(r"^Problem\s*(\d{1,3}[a-z]?)", label, re.I)
                          or re.match(r"^\[(\d{1,3})\]\s*(?:문제|예제|Problem\b)", label, re.I)
                          or re.match(r"^(\d{1,3})\s*번(?:\s|$|[★☆])", label))
                    prob_id = pm.group(1) if pm else ""
                    new_label, old_label = relabel(heading_text(label), renumber, counter)
                    if old_label is not None: mapping.append((old_label, new_label))
                    out.append(("PROB@" + prob_id + ": " if prob_id else "PROB: ") + new_label)
                stats["문제"] += 1
            else:
                # 그 밖의 굵은 제목 줄 (Definition 1.5 / (가) / Problems and Solutions ...) -> 굵은 제목 줄
                out.append("SEC: " + heading_text(label))
            if rest: buffer.append(rest)
            continue

        buffer.append(line)

    flush()
    close_solution()
    out = reorder_bound_solutions(out)

    # 연속 BR: 을 최대 하나로 (문단 사이 여백은 한글에서 따로 준다)
    cleaned: list[str] = []
    for line in out:
        if line == "BR:":
            last_real = next((l for l in reversed(cleaned) if not l.startswith("FIX:")), "")
            if last_real in ("BR:", "NEWPAGE:"):      # 빈 줄 반복, 쪽 첫머리의 빈 줄은 버린다
                continue
        cleaned.append(line)
    while cleaned and cleaned[0] in ("BR:", "NEWPAGE:"):   # 문서 맨 앞의 빈 쪽/빈 줄은 버린다
        cleaned.pop(0)

    # 해설(미주) 끝에 걸린 쪽 넘김은 미주 안에서 의미가 없다 -> 미주 밖으로 뺀다
    result: list[str] = []
    for line in cleaned:
        if line == "ENDSOL:":
            moved = []
            while result and result[-1] in ("BR:", "NEWPAGE:"):
                last = result.pop()
                if last == "NEWPAGE:":
                    moved.append(last)
            result.append("ENDSOL:"); result.extend(moved)
            continue
        result.append(line)
    cleaned = result

    # PROB:/SOL: 은 자체 문단을 만들고 미주는 첫 줄이 비면 안 되므로,
    # 그 직후의 BR: 과 ENDSOL:/PROB: 직전의 BR: 은 뺀다 (이전 DSL 과 같은 꼴).
    trimmed: list[str] = []
    for index, line in enumerate(cleaned):
        if line == "BR:":
            prev = next((l for l in reversed(trimmed) if not l.startswith("FIX:")), "")
            nxt = next((l for l in cleaned[index + 1:] if not l.startswith("FIX:")), "")
            if prev == "SOL:" or prev.startswith(("PROB:", "PROB@", "GOTO:", "SEC:")):
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
        # \begin{document} 앞이 순수 프리앰블일 때만 잘라낸다.
        # (프리앰블 앞에 본문 조각이 붙어 있는 파일이 있어서 — 2026-09-23)
        pieces.append(strip_preamble(path.read_text(encoding="utf-8")))
    source = "\n\n".join(pieces)
    lines, stats = convert(source, args.solutions, args.renumber, args.start,
                           full_source="\n".join(path.read_text(encoding="utf-8") for path in args.input))
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
