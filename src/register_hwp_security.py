r"""한글 자동화 보안 모듈(FilePathCheckerModule) 등록 도우미.

make_hwp_from_txt.py / merge_hwp.py 는 시작할 때 이 모듈이 등록돼 있는지 확인한다.
등록돼 있지 않으면 Open / SaveAs 를 부를 때마다 "파일 접근 허용" 팝업이 떠서
--invisible 로 돌리는 배치가 중간에 멈춘다.

준비물: 한컴 자동화 SDK 에 포함된 FilePathCheckerModuleExample.dll
        (한컴 개발자 사이트에서 배포. 저장소에는 포함하지 않는다.)

사용 (관리자 권한 명령 프롬프트):
    python register_hwp_security.py --dll "C:\경로\FilePathCheckerModuleExample.dll"
    python register_hwp_security.py --check          # 등록 여부만 확인

하는 일
  1. regsvr32 /s <dll>           (COM 등록)
  2. HKCU\Software\HNC\HwpAutomation\Modules 에
     FilePathCheckerModule = <dll 절대경로>   값을 기록

※ 이 스크립트는 윈도우 실기에서 검증되지 않았다.
   실패하면 위 두 단계를 손으로 해도 결과는 같다.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

KEY_PATH = r"Software\HNC\HwpAutomation\Modules"
VALUE_NAME = "FilePathCheckerModule"


def current_value():
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY_PATH)
        value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        return value
    except OSError:
        return None


def register(dll: Path) -> None:
    import winreg
    dll = dll.resolve()
    if not dll.exists():
        print(f"DLL 이 없습니다: {dll}"); sys.exit(1)
    result = subprocess.run(["regsvr32", "/s", str(dll)])
    if result.returncode != 0:
        print(f"regsvr32 실패 (코드 {result.returncode}). 관리자 권한으로 다시 실행하세요.")
        sys.exit(1)
    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY_PATH)
    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, str(dll))
    print(f"등록 완료: {VALUE_NAME} = {dll}")


def main() -> None:
    if sys.platform != "win32":
        print("윈도우 전용 스크립트입니다."); sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--dll", type=Path, help="FilePathCheckerModuleExample.dll 경로")
    parser.add_argument("--check", action="store_true", help="등록 여부만 출력")
    args = parser.parse_args()

    if args.check or not args.dll:
        value = current_value()
        print("등록됨: " + value if value else "미등록 (--dll 로 등록하세요)")
        return
    register(args.dll)


if __name__ == "__main__":
    main()
