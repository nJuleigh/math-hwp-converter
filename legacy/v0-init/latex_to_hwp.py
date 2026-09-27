from __future__ import annotations

import argparse
import re


GREEK = {
    r"\alpha": "alpha",
    r"\beta": "beta",
    r"\gamma": "gamma",
    r"\delta": "delta",
    r"\epsilon": "epsilon",
    r"\varepsilon": "epsilon",
    r"\theta": "theta",
    r"\lambda": "lambda",
    r"\mu": "mu",
    r"\nu": "nu",
    r"\pi": "pi",
    r"\sigma": "sigma",
    r"\phi": "phi",
    r"\varphi": "phi",
    r"\omega": "omega",
    r"\Omega": "Omega",
    r"\varepsilon": "varepsilon",
    r"\nu": "nu",
    r"\varphi": "varphi",
    r"\Omega": "Omega",
    r"\Pi": "Pi",
    r"\Gamma": "Gamma",
}

SYMBOLS = {
    r"\times": " times ",
    r"\cap": " cap ",
    r"\div": " div ",
    r"\pm": " +- ",
    r"\leq": " <= ",
    r"\geq": " >= ",
    r"\neq": " != ",
    r"\infty": " infinity ",
    r"\cdot": " cdot ",
    r"\int": " int ",
    r"\partial": "partial ",
    r"\Delta": " Delta ",
    r"\nabla": " nabla ",
    r"\langle": " langle ",
    r"\rangle": " rangle ",
    r"\|": " vert vert ",
    r"\leq": " <= ",
    r"\int": " int ",
    r"\partial": " partial ",
    r"\Delta": " Delta ",
    r"\nabla": " nabla ",
    r"\langle": " < ",
    r"\rangle": " > ",
    r"\|": " | ",
}


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("LaTeX 중괄호 짝이 맞지 않습니다.")


def read_group(text: str, start: int) -> tuple[str, int]:
    while start < len(text) and text[start].isspace():
        start += 1

    if start >= len(text) or text[start] != "{":
        raise ValueError("LaTeX 명령 뒤에는 { } 그룹이 필요합니다.")

    end = find_matching_brace(text, start)
    return text[start + 1 : end], end + 1



def replace_frac(text: str) -> str:
    command = r"\frac"

    while command in text:
        start = text.index(command)
        numerator, after_numerator = read_group(text, start + len(command))
        denominator, after_denominator = read_group(text, after_numerator)

        converted = (
            "{"
            + latex_to_hwp_equation(numerator)
            + "} over {"
            + latex_to_hwp_equation(denominator)
            + "}"
        )
        text = text[:start] + converted + text[after_denominator:]

    return text


def replace_sqrt(text: str) -> str:
    command = r"\sqrt"

    while command in text:
        start = text.index(command)
        cursor = start + len(command)

        while cursor < len(text) and text[cursor].isspace():
            cursor += 1

        root_index = None

        if cursor < len(text) and text[cursor] == "[":
            close_index = text.find("]", cursor)
            if close_index == -1:
                raise ValueError("LaTeX sqrt 옵션 [] 짝이 맞지 않습니다.")
            root_index = text[cursor + 1 : close_index]
            cursor = close_index + 1

        body, after_body = read_group(text, cursor)

        if root_index:
            converted = "root " + root_index + " of {" + latex_to_hwp_equation(body) + "}"
        else:
            converted = "sqrt {" + latex_to_hwp_equation(body) + "}"

        text = text[:start] + converted + text[after_body:]

    return text


def latex_to_hwp_equation(latex: str) -> str:
    text = latex.strip()
    text = text.replace("$", "")
    text = text.replace(r"\{", "left{")
    text = text.replace(r"\}", "right}")
    #text = text.replace(r"\left", "").replace(r"\right", "")
    text = text.replace(r"\left.", "")
    text = text.replace(r"\right.", "")
    text = text.replace(r"\right|", "|")
    text = text.replace(r"\left|", "|")
    text = text.replace(r"\left", "")
    text = text.replace(r"\right", "")

    text = text.replace(r"\mathcal", "cal")
    text = text.replace(r"\operatorname{Ric}", "Ric")
    text = text.replace(r"\operatorname", "")
    text = text.replace(r"\,", " ")
    text = text.replace(r"\!", "")
    text = text.replace(r"\big", "")
    text = text.replace(r"\Big", "")
    text = text.replace(r"\bigg", "")
    text = text.replace(r"\Bigg", "")
    text = text.replace(r"\left.", "")
    text = text.replace(r"\right.", "")
    text = text.replace(r"\right|", "|")
    text = text.replace(r"\left|", "|")
    text = text.replace(r"\left", "")
    text = text.replace(r"\right", "")

    text = re.sub(r"\\mathcal\s*\{([^{}]+)\}", r"cal \1", text)
    text = re.sub(r"\\operatorname\s*\{([^{}]+)\}", r"\1", text)

    text = text.replace(r"\,", " ")
    text = text.replace(r"\!", "")

    text = text.replace(r"\\", " # ")
    text = text.replace(r"\quad", "    ")
    text = text.replace(r"\qquad", "        ")

    text = replace_frac(text)
    text = replace_sqrt(text)

    for latex_symbol, hwp_symbol in GREEK.items():
        text = text.replace(latex_symbol, hwp_symbol)

    for latex_symbol, hwp_symbol in SYMBOLS.items():
        text = text.replace(latex_symbol, hwp_symbol)

    text = text.replace("^*", "^{*}")
    text = text.replace("_*", "_{*}")
    text = re.sub(r"\^\s*\*", r"^{*}", text)
    text = re.sub(r"_\s*\*", r"_{*}", text)

    text = re.sub(r"_([A-Za-z0-9]+)", r"_{\1}", text)
    text = re.sub(r"\^([A-Za-z0-9]+)", r"^{\1}", text)

# Fix cases where HWP-style superscript/subscript swallowed a following named symbol.
    text = re.sub(r"\^\{([0-9]+)([A-Za-z]+)\}", r"^{\1} \2", text)
    text = re.sub(r"_\{([0-9]+)([A-Za-z]+)\}", r"_{\1} \2", text)

    text = re.sub(r"\^\{([^{}]+)\}([A-Za-z]+)", r"^{\1} \2", text)
    text = re.sub(r"_\{([^{}]+)\}([A-Za-z]+)", r"_{\1} \2", text)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("latex", help=r"Example: \frac{a+b}{c} = \sqrt{x}")
    args = parser.parse_args()

    print(latex_to_hwp_equation(args.latex))


if __name__ == "__main__":
    main()