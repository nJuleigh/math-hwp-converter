r"""여러 hwp 를 순서대로 한 파일로 합친다.

    python merge_hwp.py -o 전체.hwp 3장-1.hwp 3장-2.hwp ... 5장-3.hwp
    python merge_hwp.py -o 전체.hwp --glob "*장-*.hwp"      # 이름순 자동 정렬

첫 파일을 열고, 문서 끝으로 가서 다음 파일을 '끼워넣기'(InsertFile) 하는 방식이다.
미주는 끼워넣기 할 때 같이 딸려 오고 번호는 한글이 다시 매긴다.
  -> 합친 뒤 두 번째 파일이 시작되는 문제의 미주 번호가 앞에서 이어지는지(예: 32) 꼭 확인할 것.
     1 로 다시 시작하면 알려주기 바람. 여기서는 실제 한글로 검증하지 못했다.

돌아가는 동안 한글을 열지 말 것 (열면 그 문서에 끼워넣기 시작함).
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from pathlib import Path

import make_hwp_from_txt as base   # start_hwp / shutdown / 보안모듈 처리 재사용


def natural_key(path: Path):
    """3장-1, 3장-2, ..., 3장-10 이 문자열순(1,10,2)이 아니라 숫자순으로 오게."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name)]


def insert_file(hwp, path: Path) -> None:
    hwp.HAction.Run("MoveDocEnd")
    hwp.HAction.Run("BreakPara")          # 앞 파일 마지막 문단과 붙지 않게
    param = hwp.HParameterSet.HInsertFile
    hwp.HAction.GetDefault("InsertFile", param.HSet)
    param.filename = str(path)
    param.KeepSection = 0                 # 구역/용지 설정은 첫 파일 것을 유지
    param.KeepCharshape = 1
    param.KeepParashape = 1
    param.KeepStyle = 1
    hwp.HAction.Execute("InsertFile", param.HSet)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="*", type=Path)
    parser.add_argument("--glob", help='예: "*장-*.hwp"')
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--visible", action="store_true")
    args = parser.parse_args()

    inputs = list(args.inputs)
    if args.glob:
        inputs += [Path(p) for p in glob.glob(args.glob)]
    inputs = sorted({p.resolve() for p in inputs}, key=natural_key)
    if len(inputs) < 2:
        print("합칠 파일이 두 개 이상 필요합니다."); return 1
    missing = [p for p in inputs if not p.exists()]
    if missing:
        print("없는 파일:", *missing, sep="\n  "); return 1

    print("합치는 순서:")
    for i, p in enumerate(inputs, 1):
        print(f"  {i:2d}. {p.name}")

    hwp = base.start_hwp(visible=args.visible)
    try:
        hwp.Open(str(inputs[0]), "HWP", "")
        for path in inputs[1:]:
            print(f"끼워넣기: {path.name}")
            insert_file(hwp, path)
        output = args.output.resolve()
        hwp.SaveAs(str(output), "HWP")
        print(f"저장: {output}")
    finally:
        base.shutdown(hwp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
