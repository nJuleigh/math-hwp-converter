# Development Log

## 1. 목표
사진/PDF에 있는 수식 문서를 HWP의 편집 가능한 수식 객체로 변환하는 프로그램을 만든다.

## 2. 핵심 문제
처음에는 수식이 이미지처럼 들어가거나, inline 위치가 깨지거나,
varphi/varepsilon 같은 수식 기호가 본문에서 이상하게 렌더링되는 문제가 있었다.

## 3. 해결한 점
- HWP COM API의 EquationCreate 사용
- HEqEdit.string 속성 사용
- TreatAsChar = 1 설정으로 수식을 글자처럼 취급
- Version = "Equation Version 60" 설정으로 렌더링 문제 완화
- HWPX XML 비교를 통해 정상 수식 객체와 자동 생성 객체의 차이 확인

## 4. 현재 한계
- 이미지/PDF를 자동 OCR로 읽는 단계는 아직 수동 변환
- 수식 번호 정렬은 개선 필요
- 기존 HWP 파일에 이어쓰기 기능은 다음 단계