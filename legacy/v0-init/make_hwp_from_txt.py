from pathlib import Path

import win32com.client as win32
from latex_to_hwp import latex_to_hwp_equation


input_path = Path("test_pic_latex.txt")
output_path = Path("test_pic_result.hwp").resolve()


def try_set(obj, name, value):
    try:
        setattr(obj, name, value)
    except Exception as e:
        print(f"{name} 설정 실패: {e}")


hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.XHwpWindows.Item(0).Visible = True
hwp.Open("")


def insert_text(text: str) -> None:
    hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
    try:
        hwp.HParameterSet.HInsertText.Text = text
    except AttributeError:
        hwp.HParameterSet.HInsertText.text = text
    hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet)


def insert_equation(latex: str) -> None:
    equation = latex_to_hwp_equation(latex)
    print("LATEX:", latex)
    print("HWP:", equation)
    print()

    hwp.HAction.GetDefault("EquationCreate", hwp.HParameterSet.HEqEdit.HSet)

    eq = hwp.HParameterSet.HEqEdit
    eq.string = equation + "\n"

    try_set(eq, "Version", "Equation Version 60")
    try_set(eq, "EqFontName", "HYhwpEQ")
    try_set(eq, "TreatAsChar", 1)
    try_set(eq, "FlowWithText", 1)
    try_set(eq, "TextWrap", 0)
    try_set(eq, "AffectsLine", 0)
    try_set(eq, "AllowOverlap", 0)
    try_set(eq, "HoldAnchorObj", 0)
    try_set(eq, "BaseLine", 76)
    try_set(eq, "BaseUnit", 1000)
    try_set(eq, "LineMode", "CHAR")
    try_set(eq, "HorzRelTo", "PARA")
    try_set(eq, "VertRelTo", "PARA")
    try_set(eq, "HorzAlign", "LEFT")
    try_set(eq, "VertAlign", "TOP")
    try_set(eq, "OutsideMarginLeft", 56)
    try_set(eq, "OutsideMarginRight", 56)
    try_set(eq, "OutsideMarginTop", 0)
    try_set(eq, "OutsideMarginBottom", 0)

    hwp.HAction.Execute("EquationCreate", eq.HSet)


lines = input_path.read_text(encoding="utf-8").splitlines()
i = 0

while i < len(lines):
    line = lines[i].rstrip()

    if not line:
        i += 1
        continue

    if line == "BR:":
        hwp.HAction.Run("BreakPara")
        hwp.HAction.Run("BreakPara")
        i += 1
        continue


    if line == "SPACE:":
        insert_text(" ")
        i += 1
        continue


    if line.startswith("TEXT:"):
        insert_text(line[len("TEXT:"):])
        i += 1
        continue

    if line.startswith("EQ:"):
        insert_equation(line[len("EQ:"):].strip())
        i += 1
        continue

    if line == "EQALIGN:":
        eq_lines = []
        i += 1

        while i < len(lines) and lines[i].rstrip() != "END:":
            if lines[i].strip():
                eq_lines.append(lines[i].strip())
            i += 1

        latex = " # ".join(eq_lines)
        insert_equation(latex)

        if i < len(lines) and lines[i].rstrip() == "END:":
            i += 1
        continue

    raise ValueError(f"알 수 없는 줄 형식입니다: {line}")

hwp.SaveAs(str(output_path), "HWP")
hwp.Quit()

print(f"저장 완료: {output_path}")