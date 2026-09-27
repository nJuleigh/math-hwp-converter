"""hwp(5.0) 본문 문단 텍스트 읽기 (한글 없이). 최소 OLE 리더 + 레코드 파서."""
import struct, zlib

def read_ole(path):
    d=open(path,'rb').read()
    assert d[:8]==b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', "OLE 파일이 아님 (hwpx 인가?)"
    ss=1<<struct.unpack('<H',d[30:32])[0]; mss=1<<struct.unpack('<H',d[32:34])[0]
    nfat=struct.unpack('<I',d[44:48])[0]; dir1=struct.unpack('<I',d[48:52])[0]
    minicut=struct.unpack('<I',d[56:60])[0]; mfat1=struct.unpack('<I',d[60:64])[0]; nmfat=struct.unpack('<I',d[64:68])[0]
    difat1=struct.unpack('<I',d[68:72])[0]; ndifat=struct.unpack('<I',d[72:76])[0]
    sec=lambda n: d[(n+1)*ss:(n+2)*ss]
    difat=list(struct.unpack('<109I',d[76:512])); s=difat1
    for _ in range(ndifat):
        blk=sec(s); difat+=list(struct.unpack(f'<{ss//4-1}I',blk[:-4])); s=struct.unpack('<I',blk[-4:])[0]
    fat=[]
    for n in difat[:nfat]: fat+=list(struct.unpack(f'<{ss//4}I',sec(n)))
    def chain(start):
        out=b''; n=start
        while n<0xFFFFFFFE: out+=sec(n); n=fat[n]
        return out
    directory=chain(dir1)
    mfat=[]; n=mfat1
    for _ in range(nmfat): mfat+=list(struct.unpack(f'<{ss//4}I',sec(n))); n=fat[n]
    entries=[]
    for i in range(0,len(directory),128):
        e=directory[i:i+128]; nl=struct.unpack('<H',e[64:66])[0]
        if nl==0: continue
        entries.append((e[:nl-2].decode('utf-16le'), e[66], struct.unpack('<I',e[116:120])[0], struct.unpack('<Q',e[120:128])[0]))
    root=[e for e in entries if e[1]==5][0]; ministream=chain(root[2])
    def read(name):
        e=[x for x in entries if x[0]==name and x[1]==2][0]
        if e[3]<minicut:
            out=b''; n=e[2]
            while n<0xFFFFFFFE: out+=ministream[n*mss:(n+1)*mss]; n=mfat[n]
            return out[:e[3]]
        return chain(e[2])[:e[3]]
    return [e[0] for e in entries], read

INLINE_CTRL={1,2,3,11,12,14,15,16,17,18,21,22,23}   # 16바이트짜리 컨트롤 문자

def paragraphs(path, section=0):
    """(문단번호, 텍스트) 목록. 문단번호는 본문 최상위(level 0) 문단만 센다 = SetPos 의 para 인덱스."""
    names, read = read_ole(path)
    flags=struct.unpack('<I',read('FileHeader')[36:40])[0]
    data=read(f'Section{section}')
    if flags&1: data=zlib.decompress(data,-15)
    paras=[]; i=0; cur=None
    while i<len(data):
        h=struct.unpack('<I',data[i:i+4])[0]; tag=h&0x3ff; level=(h>>10)&0x3ff; size=(h>>20)&0xfff; i+=4
        if size==0xfff: size=struct.unpack('<I',data[i:i+4])[0]; i+=4
        body=data[i:i+size]; i+=size
        if tag==66 and level==0:            # PARA_HEADER (본문 최상위)
            cur=len(paras); paras.append('')
        elif tag==67 and level==1 and cur is not None:   # PARA_TEXT (그 문단의 텍스트)
            txt=''; j=0
            while j+1<len(body):
                c=struct.unpack('<H',body[j:j+2])[0]
                if c<32:
                    if c in INLINE_CTRL: txt+=('⟦수식⟧' if c==11 else ''); j+=16
                    else: j+=2
                else: txt+=chr(c); j+=2
            paras[cur]=txt
    return paras

if __name__=='__main__':
    import sys
    for k,p in enumerate(paragraphs(sys.argv[1])): print(k,'|',p[:80])
