r"""LaTeX -> 한글(HWP) 수식 스크립트 변환기.

기존 버전 대비 주요 변경점
  * 심볼 치환을 "딕셔너리 순서대로 str.replace" 에서
    "\\[A-Za-z]+ 를 한 번에 잡는 정규식 + 콜백" 으로 교체.
    -> \\int 가 \\in 에 먹히는 류의 접두사 충돌이 구조적으로 불가능해짐.
  * 표에 없는 명령은 조용히 뭉개지 않고 UNSUPPORTED 로 수집.
  * _n C_k 처럼 base 가 없는 첨자 앞에 {} 를 자동 삽입 (HWP 렌더 실패 방지).
  * \\left( ... \\right) 를 삭제하지 않고 left ( ... right ) 로 보존.
  * cases / pmatrix / bmatrix / vmatrix / matrix / array / aligned 환경 지원.
"""

from __future__ import annotations

import argparse
import re
from typing import List, Tuple

# ---------------------------------------------------------------------------
# 심볼 표 : 단일 dict. 순서 무관 (전체 토큰 단위로 매칭하므로).
# 값이 None 이면 "그냥 지운다" 는 뜻.
# ---------------------------------------------------------------------------

SYMBOLS = {
    # 그리스 문자
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "varepsilon", "zeta": "zeta",
    "eta": "eta", "theta": "theta", "vartheta": "vartheta", "iota": "iota",
    "kappa": "kappa", "lambda": "lambda", "mu": "mu", "nu": "nu", "xi": "xi",
    "pi": "pi", "rho": "rho", "sigma": "sigma", "tau": "tau",
    "upsilon": "upsilon", "phi": "phi", "varphi": "varphi", "chi": "chi",
    "psi": "psi", "omega": "omega",
    "Gamma": "GAMMA", "Delta": "DELTA", "Theta": "THETA", "Lambda": "LAMBDA",
    "Xi": "XI", "Pi": "PI", "Sigma": "SIGMA", "Upsilon": "UPSILON",
    "Phi": "PHI", "Psi": "PSI", "Omega": "OMEGA",

    # 관계 / 부등호
    "leq": "<=", "le": "<=", "geq": ">=", "ge": ">=",
    "leqq": "<=", "geqq": ">=",          # 일본 교과서 표기 ≦ ≧
    "leqslant": "<=", "geqslant": ">=",
    "nleq": "notle", "ngeq": "notge",
    "neq": "!=", "ne": "!=", "equiv": "equiv", "approx": "approx",
    "sim": "sim", "simeq": "simeq", "cong": "cong", "propto": "prop",
    "ll": "<<", "gg": ">>",

    # 집합 / 논리
    "in": "in", "notin": "notin", "ni": "owns",
    "subset": "subset", "subseteq": "subseteq",
    "supset": "supset", "supseteq": "supseteq",
    "cap": "cap", "cup": "cup", "setminus": "\\",
    "emptyset": "emptyset", "varnothing": "emptyset",
    "forall": "forall", "exists": "exists",
    "land": "and", "lor": "or", "lnot": "not", "neg": "not",
    "wedge": "and", "vee": "or",          # 3~5장에서 쓰임
    "nmid": "\u2224",                      # ∤ : HWP 키워드가 없어 문자로 직접
    "hline": "",                           # array 의 가로줄 : HWP 수식에 대응물 없음

    # 연산자
    "times": "times", "div": "div", "cdot": "cdot", "pm": "+-", "mp": "-+",
    "ast": "*", "star": "*", "circ": "circ", "bullet": "bullet",
    "oplus": "oplus", "otimes": "otimes", "perp": "perp",
    "parallel": "parallel",

    # 큰 연산자
    "sum": "sum", "prod": "prod", "int": "int", "iint": "dint",
    "iiint": "tint", "oint": "oint", "bigcup": "union", "bigcap": "inter",

    # 화살표
    "to": "rightarrow", "rightarrow": "rightarrow", "leftarrow": "leftarrow",
    "Rightarrow": "\u21d2", "Leftarrow": "\u21d0",
    "leftrightarrow": "\u2194", "Leftrightarrow": "\u21d4",
    "mapsto": "mapsto", "longrightarrow": "rightarrow",
    "longleftarrow": "leftarrow", "longleftrightarrow": "leftrightarrow",
    "Longrightarrow": "\u21d2", "Longleftarrow": "\u21d0",
    "Longleftrightarrow": "\u21d4", "iff": "\u21d4", "implies": "\u21d2",
    "uparrow": "uparrow", "downarrow": "downarrow",
    "nwarrow": "\u2196", "nearrow": "\u2197",   # ↖ ↗ : HWP 키워드 없음, 문자로
    "swarrow": "\u2199", "searrow": "\u2198",   # ↙ ↘
    "mathrel": "", "mathbin": "", "mathord": "",   # 간격 지정 래퍼 : 내용만 남김
    "middle": "",                                  # \middle| -> | 만 남김
    "nearrow": "nearrow", "searrow": "searrow",

    # 함수명 (HWP 는 rm 으로 세워야 정자체로 나옴)
    "sin": "rm sin it", "cos": "rm cos it", "tan": "rm tan it",
    "sec": "rm sec it", "csc": "rm csc it", "cot": "rm cot it",
    "arcsin": "rm arcsin it", "arccos": "rm arccos it", "arctan": "rm arctan it",
    "sinh": "rm sinh it", "cosh": "rm cosh it", "tanh": "rm tanh it",
    "log": "rm log it", "ln": "rm ln it", "exp": "rm exp it",
    "lim": "rm lim it", "limsup": "rm lim sup it", "liminf": "rm lim inf it",
    "min": "rm min it", "max": "rm max it", "sup": "rm sup it", "inf": "rm inf it",
    "gcd": "rm gcd it", "lcm": "rm lcm it", "det": "rm det it", "dim": "rm dim it",
    "ker": "rm ker it", "deg": "rm deg it", "Pr": "rm Pr it", "bmod": "rm mod it",

    # 점 / 생략
    "cdots": "cdots", "ldots": "dotslow", "dots": "dotslow",
    "dotsb": "cdots", "dotsc": "dotslow", "hdots": "cdots",
    "vdots": "vdots", "ddots": "ddots",

    # 기타 기호
    "infty": "inf", "partial": "partial", "nabla": "nabla",
    "angle": "angle", "triangle": "triangle", "square": "square",
    "prime": "'", "degree": "degree", "hbar": "hbar", "ell": "l",
    "aleph": "aleph", "Re": "Re", "Im": "Im",
    "therefore": "therefore", "because": "because",
    "ne": "!=", "not": "not", "colon": ":", "vert": "|",
    "binom": "binom", "choose": "atop", "over": "over",
    "left": "left", "right": "right",

    # 간격
    "quad": "`", "qquad": "``", "thinspace": "~", "enspace": "~",
    ",": "~", ";": "`", ":": "~", "!": "", " ": "~",

    # 모델이 지어내는 명령들 (표준 LaTeX 에 없음)
    "maru": "", "circled": "", "kanji": "", "text{}": "",

    # 무시해도 되는 것들
    "rm": "rm", "it": "it", "bf": "bold", "sf": "", "tt": "",
    "displaystyle": "", "textstyle": "", "scriptstyle": "",
    "limits": "", "nolimits": "", "!": "", "bigl": "", "bigr": "",
    "Bigl": "", "Bigr": "", "biggl": "", "biggr": "",
    "big": "", "Big": "", "bigg": "", "Bigg": "",
    "phantom": "", "vphantom": "",
}

# \left \right 뒤에 붙는 구분자
DELIMS = {
    "(": "(", ")": ")", "[": "[", "]": "]",
    "\\{": "lbrace", "\\}": "rbrace",
    "|": "|", "\\|": "dline", "/": "/", "\\backslash": "\\",
    "<": "langle", ">": "rangle",
    "\\langle": "langle", "\\rangle": "rangle",
    "\\lfloor": "lfloor", "\\rfloor": "rfloor",
    "\\lceil": "lceil", "\\rceil": "rceil",
    ".": "",  # \left. \right. -> 보이지 않는 구분자
}

# 홀로 쓰이는 구분자
LONE_DELIMS = {
    "lbrace": "lbrace", "rbrace": "rbrace",
    "langle": "langle", "rangle": "rangle",
    "lfloor": "lfloor", "rfloor": "rfloor",
    "lceil": "lceil", "rceil": "rceil",
    "vert": "|", "Vert": "dline", "mid": "|",
    "backslash": "\\",
}
SYMBOLS.update(LONE_DELIMS)

# 환경 이름 -> (HWP 명령, 여는 괄호, 닫는 괄호)
ENVIRONMENTS = {
    "cases": ("cases", "", ""),
    "matrix": ("matrix", "", ""),
    "pmatrix": ("pmatrix", "", ""),
    "bmatrix": ("bmatrix", "", ""),
    "vmatrix": ("dmatrix", "", ""),
    "Bmatrix": ("matrix", "left lbrace ", " right rbrace"),
    "Vmatrix": ("matrix", "left dline ", " right dline"),
    "array": ("matrix", "", ""),
    "aligned": ("eqalign", "", ""),
    "align": ("eqalign", "", ""),
    "align*": ("eqalign", "", ""),
    "gathered": ("eqalign", "", ""),
    "smallmatrix": ("matrix", "", ""),
}

UNSUPPORTED: List[str] = []

# \fbox 로 표시된 빈칸에 붙일 이름 (ア -> A, イ -> B …).
# 수식 하나를 변환하는 동안 유지되고, 다음 수식에서 초기화된다.
_BLANK_LABELS: dict = {}


# ---------------------------------------------------------------------------
# 괄호/인자 파싱 유틸
# ---------------------------------------------------------------------------

def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{" and (index == 0 or text[index - 1] != "\\"):
            depth += 1
        elif text[index] == "}" and text[index - 1] != "\\":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("LaTeX 중괄호 짝이 맞지 않습니다: " + text[open_index:open_index + 40])


def read_group(text: str, start: int) -> Tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != "{":
        raise ValueError("LaTeX 명령 뒤에는 { } 그룹이 필요합니다: " + text[start:start + 40])
    end = find_matching_brace(text, start)
    return text[start + 1:end], end + 1


def read_atom(text: str, start: int) -> Tuple[str, int]:
    """{...} 그룹, \\명령, 또는 문자 하나를 읽는다."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        raise ValueError("LaTeX 명령 뒤에 항이 필요합니다.")
    if text[start] == "{":
        end = find_matching_brace(text, start)
        return text[start + 1:end], end + 1
    if text[start] == "\\":
        end = start + 1
        while end < len(text) and text[end].isalpha():
            end += 1
        if end == start + 1:  # \{ \} \, 같은 한 글자 명령
            end = start + 2
        return text[start:end], end
    return text[start], start + 1


# ---------------------------------------------------------------------------
# 구조 명령 처리
# ---------------------------------------------------------------------------

def replace_environments(text: str) -> str:
    """\\begin{env} ... \\end{env} -> HWP matrix/cases/eqalign."""
    pattern = re.compile(r"\\begin\s*\{([A-Za-z*]+)\}")
    while True:
        match = pattern.search(text)
        if match is None:
            return text
        name = match.group(1)
        end_token = r"\end{" + name + "}"
        end_index = text.find(end_token, match.end())
        if end_index == -1:
            raise ValueError(f"\\begin{{{name}}} 에 대응하는 \\end 가 없습니다.")

        body = text[match.end():end_index]
        # array 는 {cc} 같은 열 정렬 인자를 하나 더 먹는다
        if name == "array":
            body = re.sub(r"^\s*\{[^{}]*\}", "", body, count=1)

        command, prefix, suffix = ENVIRONMENTS.get(name, ("matrix", "", ""))
        rows = [r for r in re.split(r"\\\\", body)]
        converted_rows = []
        for row in rows:
            if not row.strip():
                continue
            cells = [convert(c) for c in row.split("&")]
            converted_rows.append(" & ".join(cells))
        inner = " # ".join(converted_rows)
        replacement = f"{prefix}{command}{{{inner}}}{suffix}"
        text = text[:match.start()] + replacement + text[end_index + len(end_token):]


def replace_two_group_command(text: str, command: str, template: str) -> str:
    while True:
        start = text.find(command)
        if start == -1:
            return text
        # \fracture 같은 더 긴 이름 오인 방지
        tail = start + len(command)
        if tail < len(text) and text[tail].isalpha():
            return text
        first, after_first = read_group(text, tail)
        second, after_second = read_group(text, after_first)
        replacement = " " + template.format(a=convert(first), b=convert(second)) + " "
        text = text[:start] + replacement + text[after_second:]


def replace_sqrt(text: str) -> str:
    command = r"\sqrt"
    while True:
        start = text.find(command)
        if start == -1:
            return text
        cursor = start + len(command)
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        root_index = None
        if cursor < len(text) and text[cursor] == "[":
            close_index = text.find("]", cursor)
            if close_index == -1:
                raise ValueError("\\sqrt 의 [] 짝이 맞지 않습니다.")
            root_index = text[cursor + 1:close_index]
            cursor = close_index + 1
        body, after_body = read_atom(text, cursor)
        if root_index:
            converted = f" root {convert(root_index)} of {{{convert(body)}}} "
        else:
            converted = f" sqrt {{{convert(body)}}} "
        text = text[:start] + converted + text[after_body:]


def replace_one_atom_command(text: str, command: str, before: str, after: str = "") -> str:
    while True:
        start = text.find(command)
        if start == -1:
            return text
        tail = start + len(command)
        if tail < len(text) and text[tail].isalpha():
            return text
        body, after_body = read_atom(text, tail)
        converted = " " + before + convert(body) + after + " "
        text = text[:start] + converted + text[after_body:]


CIRCLED = "\u2460\u2461\u2462\u2463\u2464\u2465\u2466\u2467\u2468\u2469" \
          "\u246a\u246b\u246c\u246d\u246e\u246f\u2470\u2471\u2472\u2473"


def replace_circled(text: str) -> str:
    r"""\maru{1} \circled{1} -> 원문자 ①. 모델이 지어내는 명령이라 여기서 흡수한다."""
    for command in (r"\maru", r"\circled", r"\textcircled"):
        while True:
            start = text.find(command)
            if start == -1:
                break
            tail = start + len(command)
            if tail < len(text) and text[tail].isalpha():
                break
            try:
                body, after = read_atom(text, tail)
            except ValueError:
                text = text[:start] + text[tail:]
                continue
            body = body.strip()
            mark = CIRCLED[int(body) - 1] if body.isdigit() and 1 <= int(body) <= 20 else body
            text = text[:start] + mark + text[after:]
    return text


def replace_fbox(text: str) -> str:
    r"""\fbox{...} -> 답을 써 넣는 네모 칸.

    원본은 ア イ ウ … 같은 일본어 기호로 칸에 이름을 붙인다.
    한국어 문서에서는 A B C … 로 바꾸는 편이 읽기 쉬우므로,
    한 수식 안에서 나오는 순서대로 A, B, C … 를 붙인다.
    """
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    for command in (r"\fbox", r"\framebox", r"\Box"):
        while True:
            start = text.find(command)
            if start == -1:
                break
            tail = start + len(command)
            if tail < len(text) and text[tail].isalpha():
                break
            try:
                body, after = read_atom(text, tail)
            except ValueError:
                text = text[:start] + " \u25a1 " + text[tail:]
                continue

            body = body.strip()
            if not body:
                replacement = " \u25a1 "
            else:
                # 같은 기호는 같은 글자로, 새 기호는 다음 글자로.
                # 재귀 호출에서도 이어지도록 카운터를 모듈에 둔다.
                if body not in _BLANK_LABELS:
                    _BLANK_LABELS[body] = letters[len(_BLANK_LABELS) % len(letters)]
                replacement = f" \u3010{_BLANK_LABELS[body]}\u3011 "
            text = text[:start] + replacement + text[after:]
    return text


def replace_text_command(text: str) -> str:
    r"""\text{...} \mathrm{...} -> HWP 는 rm "..." 로 정자체 문자열."""
    for command in (r"\text", r"\mathrm", r"\textrm", r"\mbox", r"\operatorname"):
        while True:
            start = text.find(command)
            if start == -1:
                break
            tail = start + len(command)
            if tail < len(text) and text[tail].isalpha():
                break
            body, after_body = read_group(text, tail)
            # \text{if } 처럼 앞뒤 공백이 의미를 가지므로 HWP 공백(~)으로 보존한다
            lead = " ~ " if body[:1].isspace() else " "
            trail = " ~ " if body[-1:].isspace() else " "
            core = body.strip()
            # rm 은 '이후 전부'에 걸리는 모드 전환이므로 반드시 it 으로 복귀시킨다
            if re.fullmatch(r"[A-Za-z]+", core):
                converted = f"rm {core} it"
            else:
                converted = f'rm "{core}" it'
            text = text[:start] + lead + converted + trail + text[after_body:]
    return text


def replace_left_right(text: str) -> str:
    """\\left( -> left (  /  \\right) -> right )  (삭제하지 않고 보존)."""
    # 뒤따르는 글자가 실제 구분자일 때만 소비한다.
    # 그러지 않으면 \rightarrow 의 'a' 를 구분자로 먹어 \righta 가 되어버린다.
    pattern = re.compile(r"\\(left|right)\s*(\\[A-Za-z]+|\\[{}|.]|[()\[\]|/<>.])")

    def repl(match: re.Match) -> str:
        side, delim = match.group(1), match.group(2)
        mapped = DELIMS.get(delim)
        if mapped is None:
            UNSUPPORTED.append(f"\\{side}{delim}")
            mapped = delim
        if mapped == "":
            return f" {side} {{}} " if side == "left" else " right {} "
        return f" {side} {mapped} "

    return pattern.sub(repl, text)


# ---------------------------------------------------------------------------
# 남은 \명령 일괄 치환 (순서 충돌 없음)
# ---------------------------------------------------------------------------

MACRO_RE = re.compile(r"\\([A-Za-z]+|[,;:!\s{}|])")


def replace_macros(text: str) -> str:
    def repl(match: re.Match) -> str:
        name = match.group(1)
        if name == "{":
            return " lbrace "
        if name == "}":
            return " rbrace "
        if name == "|":
            return " dline "
        if name in SYMBOLS:
            value = SYMBOLS[name]
            if not value:
                return " "
            # 60^\circ -> 60^circ 로 두면 HWP 가 ^ 뒤 한 글자만 첨자로 먹어서
            # 60^{c} irc 로 깨진다. 첨자 자리에 온 여러 글자 심볼은 묶어준다.
            before = match.string[:match.start()].rstrip()
            if len(value) > 1 and before.endswith(("^", "_")):
                return "{" + value + "}"
            return f" {value} "
        UNSUPPORTED.append("\\" + name)
        return f" ?{name}? "

    return MACRO_RE.sub(repl, text)


# ---------------------------------------------------------------------------
# 첨자 정규화
# ---------------------------------------------------------------------------

def normalize_scripts(text: str) -> str:
    # x_ab -> x_{a} b  (LaTeX 의미: 첫 글자만 첨자)
    text = re.sub(r"([_^])\s*([A-Za-z0-9])(?![A-Za-z0-9])", r"\1{\2}", text)
    text = re.sub(r"([_^])\s*([A-Za-z0-9])([A-Za-z0-9]+)", r"\1{\2} \3", text)
    text = re.sub(r"([_^])\s*(\\?[*'+\-])", r"\1{\2}", text)

    # HWP 는 첨자 뒤에 바로 식별자가 붙으면 삼켜버리므로 공백을 넣어준다.
    text = re.sub(r"([_^]\{[^{}]*\})([A-Za-z])", r"\1 \2", text)

    # 첨자 앞 공백 제거 : int _{0} -> int_{0}
    text = re.sub(r"\s+([_^])", r"\1", text)

    # base 없는 선행 첨자(_n C_k)는 HWP 에서 렌더 실패 -> {} 를 base 로 넣는다.
    text = re.sub(r"(^|[{(\[,=+\-*/<>#&~`]|\s\s)\s*([_^])", r"\1{}\2", text)
    return text


# ---------------------------------------------------------------------------
# 메인 변환
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 인자 정규화 : \frac12, \frac{a}2, \binom44 처럼 중괄호를 생략한 표기 보정
# ---------------------------------------------------------------------------

TWO_ARG_COMMANDS = (
    "frac", "dfrac", "tfrac", "binom", "dbinom", "tbinom",
    "overset", "underset", "stackrel",
)
ONE_ARG_COMMANDS = (
    "sqrt", "boxed", "text", "textbf", "textit", "mathbb", "mathcal",
    "mathrm", "mathbf", "mathit", "bar", "hat", "widehat", "tilde",
    "dot", "ddot", "vec", "overline", "underline", "overrightarrow",
    "underbrace", "overbrace", "pmod", "operatorname",
)

ARG_COMMAND_RE = re.compile(
    r"\\(" + "|".join(TWO_ARG_COMMANDS + ONE_ARG_COMMANDS) + r")(?![a-zA-Z])"
)


def _read_group(text: str, index: int) -> Tuple[str, int]:
    """text[index:] 에서 인자 하나를 읽어 항상 {...} 꼴로 돌려준다."""
    while index < len(text) and text[index] in " \t":
        index += 1
    if index >= len(text):
        return "{}", index

    if text[index] == "{":
        depth = 0
        cursor = index
        while cursor < len(text):
            if text[cursor] == "\\":
                cursor += 2
                continue
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
                if depth == 0:
                    return text[index:cursor + 1], cursor + 1
            cursor += 1
        return text[index:], len(text)

    if text[index] == "\\":                      # \alpha, \pi ... 한 덩어리
        match = re.match(r"\\[a-zA-Z]+|\\.", text[index:])
        end = index + (match.end() if match else 1)
        return "{" + text[index:end] + "}", end

    return "{" + text[index] + "}", index + 1    # \frac12 의 '1'


def normalize_arguments(text: str) -> str:
    r"""\frac12 -> \frac{1}{2}, \frac{n(n+1)}2 -> \frac{n(n+1)}{2} 처럼 편다.

    LaTeX 은 인자가 한 글자면 중괄호를 생략할 수 있는데, 원고에 이 표기가
    600군데 넘게 쓰였다. 아래 변환 단계들은 모두 {} 를 전제하므로 여기서 채운다.
    """
    result = []
    cursor = 0
    while True:
        match = ARG_COMMAND_RE.search(text, cursor)
        if not match:
            result.append(text[cursor:])
            break
        name = match.group(1)
        result.append(text[cursor:match.end()])
        index = match.end()

        if name == "sqrt" and index < len(text) and text[index] == "[":
            close = text.find("]", index)
            if close >= 0:
                result.append(text[index:close + 1])
                index = close + 1

        count = 2 if name in TWO_ARG_COMMANDS else 1
        for _ in range(count):
            group, index = _read_group(text, index)
            # \boxed{\frac{n(n+1)}2} 처럼 인자 안에 또 명령이 있을 수 있다
            if len(group) >= 2 and group[0] == "{":
                group = "{" + normalize_arguments(group[1:-1]) + "}"
            result.append(group)
        cursor = index
    return "".join(result)


def convert(latex: str) -> str:
    text = latex.strip()
    text = text.replace("$$", "").replace("$", "")
    # \[ ... \text{... \(A\) ...} ... \] 처럼 수식 안에 인라인 구분자가 다시
    # 들어오는 경우가 있다. 이미 수식 안이므로 구분자만 걷어낸다.
    text = text.replace(r"\(", "").replace(r"\)", "")
    text = re.sub(r"%.*", "", text)          # 주석 제거
    text = text.replace("&=", "= &")          # align 정렬점 보정

    text = normalize_arguments(text)
    text = replace_environments(text)
    text = replace_text_command(text)

    text = replace_two_group_command(text, r"\frac", "{{{a}}} over {{{b}}}")
    text = replace_two_group_command(text, r"\dfrac", "{{{a}}} over {{{b}}}")
    text = replace_two_group_command(text, r"\tfrac", "{{{a}}} over {{{b}}}")
    text = replace_two_group_command(text, r"\binom", "left ( {{{a}}} atop {{{b}}} right )")
    text = replace_two_group_command(text, r"\overset", "{{{b}}} ^{{{a}}}")
    text = replace_two_group_command(text, r"\underset", "{{{b}}} _{{{a}}}")
    text = replace_sqrt(text)

    text = replace_one_atom_command(text, r"\overrightarrow", "vec {", "}")
    text = replace_one_atom_command(text, r"\vec", "vec {", "}")
    text = replace_one_atom_command(text, r"\overline", "bar {", "}")
    text = replace_one_atom_command(text, r"\bar", "bar {", "}")
    text = replace_one_atom_command(text, r"\underline", "under {", "}")
    text = replace_one_atom_command(text, r"\widehat", "hat {", "}")
    text = replace_one_atom_command(text, r"\hat", "hat {", "}")
    text = replace_one_atom_command(text, r"\tilde", "tilde {", "}")
    text = replace_one_atom_command(text, r"\dot", "dot {", "}")
    text = replace_one_atom_command(text, r"\ddot", "ddot {", "}")
    text = replace_one_atom_command(text, r"\mathcal", "cal ", "")
    text = replace_one_atom_command(text, r"\mathbb", "", "")   # 이중선체는 HWP 미지원 -> 평문
    text = replace_one_atom_command(text, r"\mathbf", "bold ", "")
    text = replace_one_atom_command(text, r"\textbf", "bold ", "")   # 수식 안 굵은 라벨
    text = replace_one_atom_command(text, r"\mathit", "italic ", "")
    text = replace_one_atom_command(text, r"\textit", "italic ", "")
    text = replace_one_atom_command(text, r"\boxed", "", "")
    text = replace_fbox(text)
    text = replace_circled(text)
    text = replace_one_atom_command(text, r"\underbrace", "", "")
    text = replace_one_atom_command(text, r"\overbrace", "", "")
    text = replace_one_atom_command(text, r"\xrightarrow", "rightarrow ", "")
    text = replace_one_atom_command(text, r"\xleftarrow", "leftarrow ", "")
    text = replace_one_atom_command(text, r"\pmod", " ( rm mod ", " ) ")
    text = replace_one_atom_command(text, r"\bmod", " rm mod ", "")

    text = replace_left_right(text)
    text = text.replace("\\\\", " # ")
    text = replace_macros(text)

    text = normalize_scripts(text)
    # rm lim it_{n} 처럼 it 이 첨자를 가로채면 안 되므로 첨자 뒤로 밀어낸다
    text = re.sub(r"\bit\s*((?:[_^]\{[^{}]*\})+)", r"\1 it ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*#\s*", " # ", text)
    return text.strip()


# 예전 이름 호환
def latex_to_hwp_equation(latex: str) -> str:
    """변환에 실패해도 예외를 던지지 않는다.

    모델이 깨진 LaTeX 를 내보내는 일이 있는데, 그 한 줄 때문에
    문서 전체 생성이 중단되면 안 된다. 실패하면 원문을 최대한 살려서
    돌려주고 UNSUPPORTED 에 기록한다.
    """
    _BLANK_LABELS.clear()
    try:
        return convert(latex)
    except Exception as error:
        UNSUPPORTED.append(f"[변환실패] {type(error).__name__}")
        fallback = re.sub(r"\\[A-Za-z]+", " ", latex)
        fallback = fallback.replace("$", "").replace("\\", " ")
        return re.sub(r"\s+", " ", fallback).strip() or "?"


def pop_unsupported() -> List[str]:
    global UNSUPPORTED
    found, UNSUPPORTED = UNSUPPORTED, []
    return found


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("latex", nargs="?", help=r"예: \frac{a+b}{c} = \sqrt{x}")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        cases = [
            r"\int_0^1 x\,dx",
            r"\pmod{3}",
            r"\mathbb{R}",
            r"\mathcal{L}",
            r"{}_n C_k",
            r"_n C_k",
            r"P(X=k)=\frac{{}_n C_k \times 3}{3^n}",
            r"\left(\frac{1}{2}\right)^{n-1}",
            r"\begin{cases} 1 & x>0 \\ 0 & x\le 0 \end{cases}",
            r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
            r"\sum_{k=1}^{n-1} k\binom{n}{k}",
            r"\{1,2,3\}",
            r"\lim_{n \to \infty} \frac{1}{n} = 0",
            r"\sqrt[3]{x+1}",
            r"\text{이때 } x \ge 0",
        ]
        for c in cases:
            print(f"{c}\n  -> {convert(c)}")
        left = pop_unsupported()
        if left:
            print("\n미지원:", sorted(set(left)))
        return

    print(convert(args.latex))
    left = pop_unsupported()
    if left:
        print("미지원:", sorted(set(left)))


if __name__ == "__main__":
    main()
