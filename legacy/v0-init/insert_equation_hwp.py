from pathlib import Path
import win32com.client as win32


equation = r"varphi, varepsilon, partial^{*}Omega_{varepsilon}"
output = Path("generated_equation.hwp").resolve()


def try_set(obj, name, value):
    try:
        setattr(obj, name, value)
    except Exception as e:
        print(f"{name} 설정 실패: {e}")


hwp = win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule")
hwp.XHwpWindows.Item(0).Visible = True
hwp.Open("")

hwp.HAction.Run("MoveDocBegin")
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

hwp.SaveAs(str(output), "HWP")
print(f"saved: {output}")