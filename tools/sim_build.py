"""make_hwp_from_txt.build() 를 가짜 HWP 로 돌려 문단 구조만 뽑아본다 (윈도우/한글 불필요)."""
import sys, types
for m in ("win32com","win32com.client","pythoncom","win32com.client.gencache"):
    sys.modules[m]=types.ModuleType(m)
sys.modules["win32com.client"].gencache=sys.modules["win32com.client.gencache"]
from unittest.mock import MagicMock
import importlib.util
spec=importlib.util.spec_from_file_location("mk",sys.argv[1]); mk=importlib.util.module_from_spec(spec); spec.loader.exec_module(mk)

def simulate(dsl_lines):
    log=[]; hwp=MagicMock()
    state={}
    class PS:  # 파라미터셋 흉내: 속성 대입을 기록
        def __setattr__(self,k,v): state[k]=v
        def __getattr__(self,k): return MagicMock()
    hwp.HParameterSet.HInsertText=PS(); hwp.HParameterSet.HEqEdit=PS()
    def run(a): log.append(("RUN",a)); return True
    def execute(a,h):
        if a=="InsertText": log.append(("TEXT",str(state.get("Text",""))))
        elif a=="EquationCreate": log.append(("EQ",str(state.get("String",""))))
        return True
    hwp.HAction.Run.side_effect=run; hwp.HAction.Execute.side_effect=execute
    hwp.GetPos.return_value=(0,0,0)
    mk.build(hwp, dsl_lines, verbose=False, default_align="left")
    para=[]; cur=[]
    for k,v in log:
        if k=="RUN" and v=="BreakPara": para.append(cur); cur=[]
        elif k=="TEXT": cur.append(v)
        elif k=="EQ": cur.append("[수식 "+v.strip()+"]")
        elif k=="RUN" and v in ("InsertEndnote","Endnote"): cur.append("<<미주>>")
        elif k=="RUN" and v=="CloseEx": cur.append("<<미주끝>>")
    para.append(cur)
    return para

if __name__=="__main__":
    dsl=open(sys.argv[2],encoding="utf-8").read().split("\n")
    for i,p in enumerate(simulate(dsl)): print(f"{i:3d} | {' '.join(p) if p else '(빈 문단)'}")
