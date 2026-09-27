# HWP Math Converter (v0 — 초기 실험, 참고용)

이미지/PDF에서 읽은 수식과 문장을 TEXT/EQ 형식으로 정리한 뒤,
한글(HWP)에 편집 가능한 수식 객체로 삽입하는 실험용 변환기입니다.

## 주요 기능
- LaTeX 형식 수식을 HWP 수식 문법으로 변환
- HWP 수식 객체로 삽입
- 일반 텍스트와 수식을 섞어서 입력
- inline 수식의 글자처럼 취급 처리
- align 수식에서 & 정렬과 # 줄바꿈 처리

## 실행 방법
1. pywin32 설치
   pip install pywin32

2. 입력 파일 작성
   examples/test_pic_latex.txt

3. 실행
   python src/make_hwp_from_txt.py