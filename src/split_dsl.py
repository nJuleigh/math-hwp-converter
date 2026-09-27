r"""DSL 을 장(챕터) 단위로 나눈다. 문제 경계(PROB:) 에서만 자르므로 미주가 찢어지지 않는다.

    python split_dsl.py -i 임시_dsl.txt                 -> 3장.txt 4장.txt 5장.txt
    python split_dsl.py -i 임시_dsl.txt --max-lines 3000 -> 3장-1.txt 3장-2.txt ... (장 안에서 다시 분할)

장 판정: '예제 N-M.' / '문제 N-M.' 의 N. 번호만 있는 헤더(123.)는 직전 헤더의 장을 따른다.
한글은 문서가 커질수록 느려지므로(줄 수의 제곱에 비례), 3,000줄 안팎으로 쪼개는 쪽을 권한다.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

LABELED = re.compile(r"^PROB:\s*(?:예제|문제)\s*(\d+)-\d+\.")


def split(lines: list[str], max_lines: int | None) -> list[tuple[str, list[str]]]:
    # 1) 문제 단위로 묶는다
    units: list[tuple[str, list[str]]] = []      # (장, 줄들)
    chapter = "0"
    current: list[str] = []
    for line in lines:
        if line.startswith("PROB:"):
            if current:
                units.append((chapter, current))
            match = LABELED.match(line)
            if match:
                chapter = match.group(1)
            current = []
        current.append(line)
    if current:
        units.append((chapter, current))

    # 2) 장별로 모으고, 필요하면 max_lines 로 다시 나눈다
    #    (--renumber all 로 '예제 3-1' 같은 라벨이 사라진 DSL 은 장 구분이 없으므로 '부분' 으로)
    chunks: list[tuple[str, list[str]]] = []
    if all(c == "0" for c, _ in units):
        units = [("부분", u) for _, u in units]
    for chapter in sorted({c for c, _ in units}, key=lambda c: int(c) if c.isdigit() else 0):
        chapter_units = [u for c, u in units if c == chapter]
        if max_lines is None:
            chunks.append((f"{chapter}장" if chapter.isdigit() else chapter, sum(chapter_units, [])))
            continue
        part, size, number = [], 0, 1
        for unit in chapter_units:
            if part and size + len(unit) > max_lines:
                chunks.append(((f"{chapter}장" if chapter.isdigit() else chapter) + f"-{number}", part))
                part, size, number = [], 0, number + 1
            part.extend(unit)
            size += len(unit)
        if part:
            chunks.append(((f"{chapter}장" if chapter.isdigit() else chapter) + f"-{number}", part))
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", type=Path, required=True)
    parser.add_argument("-o", "--outdir", type=Path, default=Path("."))
    parser.add_argument("--max-lines", type=int, default=None,
                        help="장 안에서 이 줄 수를 넘지 않게 다시 나눈다 (권장 3000)")
    args = parser.parse_args()

    lines = args.input.read_text(encoding="utf-8").split("\n")
    args.outdir.mkdir(parents=True, exist_ok=True)

    maker = Path(__file__).resolve().parent / "make_hwp_from_txt.py"
    batch = ["@echo off", "chcp 65001 > nul"]
    for name, chunk in split(lines, args.max_lines):
        path = args.outdir / f"{name}.txt"
        path.write_text("\n".join(chunk).rstrip("\n") + "\n", encoding="utf-8")
        problems = sum(1 for l in chunk if l.startswith("PROB:"))
        equations = sum(1 for l in chunk if l.startswith(("EQ:", "EQD:")))
        print(f"{path.name:12s} {len(chunk):6,d}줄  문제 {problems:3d}  수식 {equations:5,d}")
        batch.append(f'python "{maker}" -i "{path.name}" -o "{name}.hwp"')
    batch.append("echo 전부 끝")
    (args.outdir / "run_all.bat").write_text("\r\n".join(batch) + "\r\n", encoding="utf-8")
    print(f"\n{args.outdir / 'run_all.bat'} 생성. 이걸 더블클릭하면 차례로 전부 돌아간다.")
    print("돌아가는 동안 한글을 절대 열지 말 것.")


if __name__ == "__main__":
    main()
