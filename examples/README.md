# examples

* `Sample.tex` — 문제 1개와 해설(두 가지 풀이). 인라인 수식, 디스플레이 수식, `aligned`, `\boxed`, `\mathbb`, `\binom`, 중괄호 생략(`\frac12`) 등이 들어 있다.
* `Sample_dsl.txt` — `python src/tex_to_dsl.py -i examples/Sample.tex -o Sample_dsl.txt` 의 결과. 문제 1, 해설 1, TEXT 80, EQ 40, EQD 30.

윈도우에서 hwp 까지 만들어 보려면:

```
python src\make_hwp_from_txt.py -i examples\Sample_dsl.txt -o Sample.hwp
```

한글 없이 문단 구조만 보려면:

```
python tools/sim_build.py src/make_hwp_from_txt.py examples/Sample_dsl.txt
```
