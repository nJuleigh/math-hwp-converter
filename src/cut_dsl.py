r"""DSL 에서 일부 문제 구간만 잘라낸다 (샘플 실행용).

    python cut_dsl.py -i 임시_dsl.txt -o 샘플_dsl.txt --from "예제 3-19" --to "5."

--from 라벨의 PROB: 줄부터 --to 라벨의 PROB: 줄 *직전* 까지. --to 를 생략하면 끝까지.
라벨은 PROB: 뒤 문자열의 앞부분만 맞으면 된다 ("예제 3-19" 는 "예제 3-19. 자연수열의 전도수" 에 맞음).
"""
import argparse
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", type=Path, required=True)
    ap.add_argument("-o", "--output", type=Path, required=True)
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end")
    a = ap.parse_args()

    lines = a.input.read_text(encoding="utf-8").split("\n")
    heads = [(i, l[5:].strip()) for i, l in enumerate(lines) if l.startswith("PROB:")]
    s = next((i for i, lab in heads if lab.startswith(a.start)), None)
    if s is None:
        print(f"시작 라벨을 못 찾음: {a.start}"); return 1
    e = len(lines)
    if a.end:
        e = next((i for i, lab in heads if i > s and lab.startswith(a.end)), None)
        if e is None:
            print(f"끝 라벨을 못 찾음: {a.end}"); return 1
    chunk = lines[s:e]
    a.output.write_text("\n".join(chunk).rstrip("\n") + "\n", encoding="utf-8")
    n = sum(1 for l in chunk if l.startswith("PROB:"))
    q = sum(1 for l in chunk if l.startswith(("EQ:", "EQD:")))
    print(f"저장: {a.output}  {len(chunk):,}줄  문제 {n}  수식 {q}")
    for i, lab in heads:
        if s <= i < e:
            print("   ", lab[:40])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
