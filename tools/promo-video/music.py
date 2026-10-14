# Synthesised background music (100 BPM, Am-F-C-G) for the promo video. Needs only numpy.
# usage: python music.py <seconds> <cut1,cut2,...> <out.wav>
import numpy as np,sys,wave
SR=44100;T=float(sys.argv[1]);cuts=[float(x) for x in sys.argv[2].split(',')];n=int(SR*T);t=np.arange(n)/SR
rng=np.random.default_rng(7);out=np.zeros((n,2))
BPM=100;beat=60/BPM;bar=4*beat
f=lambda m:440*2**((m-69)/12)
prog=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]   # Am F C G
INTRO,OUTRO=5.0,T-7.0
def env_adsr(L,a,d,s,r,sr=SR):
    e=np.ones(L)*s;A=int(a*sr);D=int(d*sr);R=int(r*sr)
    e[:A]=np.linspace(0,1,A,endpoint=False) if A else e[:A];e[A:A+D]=np.linspace(1,s,len(e[A:A+D]));
    if R:e[-R:]*=np.linspace(1,0,R)
    return e
def add(x,start,sig,pan=0.0,gain=1.0):
    i=int(start*SR);j=min(n,i+len(sig))
    if i>=n or j<=0:return
    s=sig[:j-i]*gain;x[i:j,0]+=s*(1-pan)*0.5*2**0.5;x[i:j,1]+=s*(1+pan)*0.5*2**0.5
def saw(fr,L,harm=8):
    tt=np.arange(L)/SR;return sum(np.sin(2*np.pi*fr*k*tt)/k for k in range(1,harm+1))*0.55
def lowpass(x,a):  # one-pole
    y=np.empty_like(x);acc=0.
    for i in range(len(x)):acc+=a*(x[i]-acc);y[i]=acc
    return y
nb=int(T/bar)+1
# pad
for b in range(nb):
    s=b*bar;L=int((bar+0.6)*SR);ch=prog[b%4]
    sig=sum(saw(f(m-12)*(1+d),L,6) for m in ch for d in (-0.003,0.003))/6
    add(out,s,sig*env_adsr(L,0.6,0.4,0.8,0.6),gain=0.11)
# arp 16ths
step=beat/4
pat=[0,1,2,1,0,2,1,2]
for k in range(int(T/step)):
    s=k*step;b=int(s/bar);ch=prog[b%4];m=ch[pat[k%8]%3]+12+(12 if (k//8)%4==3 else 0)
    L=int(0.22*SR);tt=np.arange(L)/SR
    sig=(np.sin(2*np.pi*f(m)*tt)+0.3*np.sin(2*np.pi*f(m)*2*tt))*np.exp(-tt*18)
    g=0.07 if s<INTRO else 0.085
    add(out,s,sig,pan=0.35*np.sin(k*0.7),gain=g)
    add(out,s+beat*0.75,sig,pan=-0.4,gain=g*0.35)   # dotted-8th echo
full=lambda s:INTRO<=s<OUTRO
for k in range(int(T/beat)):
    s=k*beat;b=int(s/bar);ch=prog[b%4]
    if not full(s):continue
    # kick on every beat
    L=int(0.3*SR);tt=np.arange(L)/SR;kick=np.sin(2*np.pi*(45+90*np.exp(-tt*25))*tt)*np.exp(-tt*9);add(out,s,kick,gain=0.55)
    # snare on 2 and 4
    if k%4 in (1,3):
        L=int(0.25*SR);tt=np.arange(L)/SR;nz=rng.standard_normal(L);nz=nz-lowpass(nz,0.15)
        sn=(0.6*nz*np.exp(-tt*22)+0.5*np.sin(2*np.pi*190*tt)*np.exp(-tt*30));add(out,s,sn,gain=0.22)
    # hats on 8ths
    for h in (0,0.5):
        L=int(0.06*SR);tt=np.arange(L)/SR;nz=rng.standard_normal(L);nz=nz-lowpass(nz,0.5)
        add(out,s+h*beat,nz*np.exp(-tt*70),pan=0.3,gain=0.05 if h else 0.035)
    # bass 8ths on chord root
    for h in (0,0.5):
        L=int(beat*0.48*SR);tt=np.arange(L)/SR;r=ch[0]-24
        bs=np.tanh(1.8*np.sin(2*np.pi*f(r)*tt))*np.exp(-tt*4)*np.minimum(1,tt*200)
        add(out,s+h*beat,bs,gain=0.16)
# whoosh at cuts
for c in cuts:
    L=int(0.9*SR);nz=rng.standard_normal(L);sw=lowpass(nz,0.08)*np.sin(np.pi*np.arange(L)/L)**2
    add(out,c-0.6,sw,gain=0.35)
# master: fade in/out, soft clip
fade=np.minimum(1,t/1.5)*np.minimum(1,(T-t)/4.0);out*=fade[:,None]
out=np.tanh(out*1.3)/np.tanh(1.3);out*=0.89/np.abs(out).max()
pcm=(np.clip(out,-1,1)*32767).astype('<i2')
with wave.open(sys.argv[3],'wb') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes(pcm.tobytes())
print('music ok',T)
