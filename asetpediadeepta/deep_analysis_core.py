"""
deep_analysis_core.py
Fungsi inti matematika dari ta_lib_deep_analysis + talib_deep_analysis
"""
import numpy as np, pandas as pd, talib, math, warnings
from scipy import stats, signal
from scipy.ndimage import uniform_filter1d
from scipy.fft import fft, fftfreq
from scipy.signal import find_peaks
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from collections import defaultdict
warnings.filterwarnings('ignore')

def validate_ohlcv(df):
    req = ['open','high','low','close','volume']
    df = df.copy()
    for c in req:
        if c not in df.columns: raise ValueError(f"Kolom '{c}' tidak ditemukan.")
    df[req] = df[req].astype(float).dropna(subset=req)
    if len(df) < 50: raise ValueError("Data terlalu pendek. Minimal 50 baris.")
    return df

class TAEnhanced:
    @staticmethod
    def all_indicators(df):
        o,h,l,c,v = df['open'],df['high'],df['low'],df['close'],df['volume']
        ind = {}
        ind['bbands_upper'],ind['bbands_middle'],ind['bbands_lower'] = talib.BBANDS(c,20,2,2,0)
        ind['ema_9']=talib.EMA(c,9); ind['ema_21']=talib.EMA(c,21); ind['ema_50']=talib.EMA(c,50); ind['ema_200']=talib.EMA(c,200)
        ind['sar']=talib.SAR(h,l,0.02,0.2); ind['dema']=talib.DEMA(c,30); ind['tema']=talib.TEMA(c,30)
        ind['kama']=talib.KAMA(c,30); ind['wma']=talib.WMA(c,30); ind['t3']=talib.T3(c,5,0.7)
        ind['macd'],ind['macd_signal'],ind['macd_hist']=talib.MACD(c,12,26,9)
        ind['adx']=talib.ADX(h,l,c,14); ind['plus_di']=talib.PLUS_DI(h,l,c,14); ind['minus_di']=talib.MINUS_DI(h,l,c,14)
        ind['rsi_6']=talib.RSI(c,6); ind['rsi_14']=talib.RSI(c,14); ind['rsi_21']=talib.RSI(c,21)
        ind['stoch_slowk'],ind['stoch_slowd']=talib.STOCH(h,l,c,5,3,0,3,0)
        ind['cci']=talib.CCI(h,l,c,14); ind['mfi']=talib.MFI(h,l,c,v,14); ind['willr']=talib.WILLR(h,l,c,14)
        ind['atr']=talib.ATR(h,l,c,14); ind['natr']=talib.NATR(h,l,c,14); ind['obv']=talib.OBV(c,v)
        ind['roc']=talib.ROC(c,10); ind['mom']=talib.MOM(c,10); ind['ultosc']=talib.ULTOSC(h,l,c)
        ind['bop']=talib.BOP(o,h,l,c); ind['cmo']=talib.CMO(c,14)
        ind['linearreg_slope']=talib.LINEARREG_SLOPE(c,14); ind['stddev']=talib.STDDEV(c,20,1)
        ind['ad']=talib.AD(h,l,c,v); ind['adosc']=talib.ADOSC(h,l,c,v,3,10)
        for k,v_ in ind.items():
            if isinstance(v_, np.ndarray): ind[k] = pd.Series(v_, index=df.index)
        return pd.DataFrame(ind, index=df.index)

def detect_volume_price_divergence(df, lookback=20, threshold=0.65):
    c,v = df['close'].values, df['volume'].values; n=len(c)
    pc = np.diff(c)/c[:-1]; vc = np.diff(v)/(v[:-1]+1e-10)
    sc = np.full(n,np.nan); dt = np.zeros(n,dtype=int)
    for i in range(lookback,n):
        if np.std(pc[i-lookback:i])<1e-10 or np.std(vc[i-lookback:i])<1e-10: continue
        corr,_=stats.spearmanr(pc[i-lookback:i],vc[i-lookback:i]); sc[i]=corr
        if corr < -threshold: dt[i] = 1 if np.mean(pc[i-lookback//2:i])>0 else 2
    return pd.DataFrame({'divergence_correlation':sc,'divergence_type':dt},index=df.index)

def volume_flow_intensity(df, short=5, long=20):
    """
    Replaces pseudo-scientific 'acceleration' with robust Volume-Price Flow.
    Measures the momentum of dollar volume with Gaussian smoothing to reduce noise.
    """
    c, v = df['close'].values, df['volume'].values
    n = len(c)
    # Dollar Volume (Liquidity Flow)
    dv = c * v
    # Standardize to avoid scale issues across different assets
    dv_norm = (dv - np.mean(dv[:long])) / (np.std(dv[:long]) + 1e-10)
    
    # Velocity: 1st derivative of smoothed flow
    flow_smooth = uniform_filter1d(dv_norm, size=short)
    vel = np.gradient(flow_smooth)
    
    # Impact Force: Speed of change in momentum relative to price volatility
    atr = talib.ATR(df['high'].values, df['low'].values, c, timeperiod=14)
    force = (vel * v) / (atr + 1e-10)
    
    return pd.DataFrame({
        'flow_velocity': vel,
        'flow_impact_force': uniform_filter1d(force, size=short),
        'flow_efficiency': vel / (uniform_filter1d(v, size=short) + 1e-10)
    }, index=df.index)

def multi_period_rsi_entropy(df, periods=[5,7,14,21,28,42,63]):
    c=df['close'].values; n=len(c); rm=np.zeros((n,len(periods)))
    for j,p in enumerate(periods): rm[:,j]=talib.RSI(c,timeperiod=p)
    ent=np.full(n,np.nan); rd=np.full(n,np.nan); rp=np.full(n,np.nan)
    for i in range(max(periods)+10,n):
        rn=np.clip(rm[i]/100.0,0.001,0.999); ent[i]=-np.sum(rn*np.log2(rn))
        rd[i]=np.mean(rm[i]); rp[i]=np.std(rm[i])
    v=ent[~np.isnan(ent)]
    en=(ent-np.nanmin(ent))/(np.nanmax(ent)-np.nanmin(ent)+1e-10) if len(v)>0 else ent
    return pd.DataFrame({'rsi_entropy':ent,'rsi_entropy_normalized':en,'rsi_cross_period_mean':rd,'rsi_dispersion':rp},index=df.index)

def hurst_exponent_rolling(prices, window=100):
    n=len(prices); h=np.full(n,np.nan)
    for i in range(window,n):
        s=prices[i-window:i]; ls=np.log(s/s[0]+1e-10); mk=min(20,window//4)
        if mk<2: continue
        rsv=[]; nsv=[]
        for k in range(2,mk+1):
            ch=[ls[j:j+k] for j in range(0,len(ls)-k,k)]
            if len(ch)<2: continue
            rl=[]
            for cc in ch:
                m_=np.mean(cc); cd=np.cumsum(cc-m_); R_=np.max(cd)-np.min(cd); S_=np.std(cc)+1e-10
                rl.append(R_/S_)
            if rl: rsv.append(np.mean(rl)); nsv.append(k)
        if len(rsv)>=2:
            sl,_,_,_,_=stats.linregress(np.log(nsv),np.log(rsv)); h[i]=sl
    return h

def fractal_dimension(df, window=50):
    c=df['close'].values; n=len(c); fd=np.full(n,np.nan)
    for i in range(window,n):
        seg=c[i-window:i]; mn,mx=np.min(seg),np.max(seg); rng=mx-mn
        if rng<1e-10: fd[i]=1.0; continue
        nm=(seg-mn)/rng; bs=[2,4,8,16]; cnt=[]
        for b in bs:
            bx=set(); [bx.add((int(j*b/len(nm)),int(nm[j]*(b-1)))) for j in range(len(nm))]; cnt.append(len(bx))
        if len(cnt)>=2: sl,_,_,_,_=stats.linregress(np.log(1.0/np.array(bs[:len(cnt)])),np.log(cnt)); fd[i]=sl
    return pd.Series(fd,index=df.index,name='fractal_dimension')

def market_regime_detector(df, window=100):
    c=df['close'].values; h_=hurst_exponent_rolling(c,window); fd=fractal_dimension(df,window)
    atr_=talib.ATR(df['high'].values,df['low'].values,c,14); an=atr_/(np.nanmean(c)+1e-10)
    reg=np.full(len(c),np.nan); rc=np.full(len(c),np.nan)
    for i in range(window,len(c)):
        hv, fv, vo = h_[i], fd[i], an[i]
        if np.isnan(hv) or np.isnan(fv): continue
        ts=hv-0.5; cs=fv-1.5; pt=(c[i]-c[i-window//2])/(c[i-window//2]+1e-10)
        if cs>0.2 or vo>0.05: reg[i]=3; rc[i]=min(1.0,cs+vo*10)
        elif ts>0.1: reg[i]=1 if pt>0.01 else 2; rc[i]=min(1.0,ts*3+abs(pt)*10)
        else: reg[i]=0; rc[i]=min(1.0,abs(ts)*3+(0.5-hv)*5)
    return pd.DataFrame({'market_regime':reg,'regime_confidence':rc,'hurst_exponent':h_,'fractal_dim':fd},index=df.index)

def detect_head_shoulders(df, sensitivity=0.7):
    c=df['close'].values; n=len(c); sig=np.zeros(n); pks=[],trh=[]
    for i in range(5,n-5): w=c[i-5:i+6]; (pks if c[i]==np.max(w) else trh).append(i)
    for j in range(len(pks)-2):
        p1,p2,p3=pks[j],pks[j+1],pks[j+2]
        if p3-p1>n*0.5: continue
        t1s=[t for t in trh if p1<t<p2]; t2s=[t for t in trh if p2<t<p3]
        if not t1s or not t2s: continue
        t1,t2=t1s[len(t1s)//2],t2s[len(t2s)//2]
        if c[p2]>c[p1] and c[p2]>c[p3]:
            rl=(c[p2]-c[p1])/(c[p2]+1e-10); rr=(c[p2]-c[p3])/(c[p2]+1e-10)
            if 1.0-abs(rl-rr)>sensitivity and abs(c[t2]-c[t1])/(p3-p1+1e-10)<0.005: sig[p3:]=-1
    for j in range(len(trh)-2):
        t1,t2,t3=trh[j],trh[j+1],trh[j+2]
        if t3-t1>n*0.5: continue
        p1s=[p for p in pks if t1<p<t2]; p2s=[p for p in pks if t2<p<t3]
        if not p1s or not p2s: continue
        p1,p2=p1s[len(p1s)//2],p2s[len(p2s)//2]
        if c[t2]<c[t1] and c[t2]<c[t3]:
            rl=(c[t1]-c[t2])/(c[t2]+1e-10); rr=(c[t3]-c[t2])/(c[t2]+1e-10)
            if 1.0-abs(rl-rr)>sensitivity: sig[t3:]=1
    return pd.Series(sig,index=df.index,name='hs_pattern')

def detect_double_top_bottom(df, tolerance=0.03):
    c=df['close'].values; n=len(c); sig=np.zeros(n); pks=[],trh=[]
    for i in range(10,n-10):
        if c[i]==np.max(c[i-10:i+11]): pks.append(i)
        elif c[i]==np.min(c[i-10:i+11]): trh.append(i)
    for j in range(len(pks)-1):
        p1,p2=pks[j],pks[j+1]
        if 20<p2-p1<n*0.3 and abs(c[p1]-c[p2])/((c[p1]+c[p2])/2+1e-10)<tolerance:
            if (c[p1]-np.min(c[p1:p2]))/(c[p1]+1e-10)>0.01: sig[p2:]=-1; break
    for j in range(len(trh)-1):
        t1,t2=trh[j],trh[j+1]
        if 20<t2-t1<n*0.3 and abs(c[t1]-c[t2])/((c[t1]+c[t2])/2+1e-10)<tolerance:
            if (np.max(c[t1:t2])-c[t1])/(c[t1]+1e-10)>0.01: sig[t2:]=1; break
    return pd.Series(sig,index=df.index,name='double_pattern')

def detect_wedge_patterns(df, lookback=30, max_samples=300):
    """
    Optimized Wedge Detection.
    Limits analysis to the recent window to prevent unnecessary linear regressions 
    on aging historical data.
    """
    h, l = df['high'].values, df['low'].values
    n = len(h)
    sig = np.zeros(n)
    # Only calculate for the last max_samples to save CPU
    start_calc = max(lookback*2, n - max_samples)
    for i in range(start_calc, n):
        x = np.arange(lookback * 2)
        window_h = h[i-lookback*2:i]
        window_l = l[i-lookback*2:i]
        sh, _, _, _, _ = stats.linregress(x, window_h)
        sl, _, _, _, _ = stats.linregress(x, window_l)
        conv = (sh - sl) / (abs(sh) + abs(sl) + 1e-10)
        if conv > 0.3 and sh > 0 and sl > 0: sig[i] = -1
        elif conv < -0.3 and sh < 0 and sl < 0: sig[i] = 1
    return pd.Series(sig, index=df.index, name='wedge_pattern')

def zscore_dynamic_support_resistance(df, min_touches=3, lookback=1000):
    """
    Optimized Dynamic S/R.
    Uses a lookback window for extrema detection to prevent DBSCAN O(N^2) bottlenecks 
    on large datasets.
    """
    c, h, l = df['close'].values, df['high'].values, df['low'].values
    n = len(c)
    
    # Use only recent window for performance
    start_idx = max(5, n - lookback)
    c_slice = c[start_idx:]
    h_slice = h[start_idx:]
    l_slice = l[start_idx:]
    
    mn = np.mean(c_slice)
    sd = np.std(c_slice)
    
    ext = []
    for i in range(5, len(c_slice) - 5):
        if h_slice[i] >= np.max(h_slice[i-5:i+6]): ext.append(h_slice[i])
        if l_slice[i] <= np.min(l_slice[i-5:i+6]): ext.append(l_slice[i])
        
    if len(ext) < min_touches: 
        return pd.DataFrame({'dynamic_support': np.nan, 'dynamic_resistance': np.nan}, index=df.index)
        
    pr = np.array(ext).reshape(-1, 1)
    # DBSCAN 1D on limited extrema is efficient
    cl = DBSCAN(eps=sd * 0.05, min_samples=min_touches).fit(pr)
    
    sl = np.full(n, np.nan); rl = np.full(n, np.nan)
    for lb in set(cl.labels_):
        if lb == -1: continue
        lv = np.mean(pr[cl.labels_ == lb])
        if lv < mn: sl.fill(lv)
        else: rl.fill(lv)
        
    return pd.DataFrame({'dynamic_support': sl, 'dynamic_resistance': rl}, index=df.index)

def spectral_cycle_analysis(df, min_p=5, max_p=100):
    """
    Refined Spectral Analysis.
    Instead of assuming stationarity, we use Detrended Fluctuations and a 
    windowed FFT to find the local dominant spectral component.
    """
    c = df['close'].values
    n = len(c)
    # Use log returns to stabilize variance for FFT
    returns = np.diff(np.log(c + 1e-10))
    # Detrend the series
    detrended = signal.detrend(returns)
    
    # Pad for FFT performance
    n_fft = 1 << (len(detrended) - 1).bit_length()
    yf = fft(detrended, n=n_fft)
    xf = fftfreq(n_fft)
    
    pm = xf > 0
    xp = xf[pm]
    pw = np.abs(yf[pm])**2
    
    per = 1.0 / (xp + 1e-10)
    vm = (per >= min_p) & (per <= max_p)
    vp, pwv = per[vm], pw[vm]
    
    if len(pwv) == 0:
        return pd.DataFrame({
            'dominant_cycle_period': np.nan,
            'spectral_density_score': 0.0,
            'spectral_entropy': np.nan
        }, index=df.index)
        
    di = np.argmax(pwv)
    dp = vp[di]
    tp = np.sum(pwv) + 1e-10
    pb = pwv / tp
    se = -np.sum(pb * np.log2(pb + 1e-10))
    
    # Broadcast to full index length
    return pd.DataFrame({
        'dominant_cycle_period': dp,
        'spectral_density_score': pwv[di] / tp,
        'spectral_entropy': se
    }, index=df.index)

def wavelet_trend_decomposition(df, level=3):
    c=df['close'].values; n=len(c)
    try:
        from scipy.signal import cwt,ricker; ws=np.arange(1,min(64,n//4)); cw=cwt(c-np.mean(c),ricker,ws)
        tr=uniform_filter1d(cw[0],size=level*5)+np.mean(c); cy=uniform_filter1d(cw[min(level,len(cw)-1)],size=3)
        return pd.DataFrame({'wavelet_trend':tr,'wavelet_cycle':cy,'wavelet_noise':c-tr-cy},index=df.index)
    except: return pd.DataFrame({'wavelet_trend':c,'wavelet_cycle':np.zeros(n),'wavelet_noise':np.zeros(n)},index=df.index)

def sequential_entropy_index(df, window=50):
    """
    Replaces pseudo-scientific 'Kolmogorov Complexity' with 5-level Quantized Entropy.
    Preserves magnitude and volatility info by using standard deviation bins.
    """
    c = df['close'].values
    n = len(c)
    cx = np.full(n, np.nan)
    
    for i in range(window, n):
        returns = np.diff(c[i-window:i]) / (c[i-window:i-1] + 1e-10)
        std = np.std(returns) + 1e-10
        
        # Quantize into 5 levels based on sigma
        # -2: <-2sig, -1: <-0.5sig, 0: flat, 1: >0.5sig, 2: >2sig
        bins = np.digitize(returns, [-2*std, -0.5*std, 0.5*std, 2*std]) - 2
        
        # Calculate Shannon entropy of the sequence
        _, counts = np.unique(bins, return_counts=True)
        probs = counts / len(bins)
        entropy = -np.sum(probs * np.log2(probs + 1e-10))
        
        # Normalize by max possible entropy (log2(5))
        cx[i] = entropy / np.log2(5)
        
    return pd.Series(cx, index=df.index, name='sequential_entropy_index')

def mutual_information_price_volume(df, lag=10, bins=20):
    c,v=df['close'].values,df['volume'].values; n=len(c); mi=np.full(n,np.nan)
    # Gunakan window yang cukup untuk statistik distribusi
    window = max(lag, bins * 2)
    for i in range(window, n):
        # Hitung return dan volume change
        pr = np.diff(c[i-window:i]) / (c[i-window:i-1] + 1e-10)
        vc = np.diff(v[i-window:i]) / (v[i-window:i-1] + 1e-10)
        
        ph, _ = np.histogram(pr, bins=bins, range=(np.percentile(pr, 1), np.percentile(pr, 99)), density=True)
        vh, _ = np.histogram(vc, bins=bins, range=(np.percentile(vc, 1), np.percentile(vc, 99)), density=True)
        jh, _, _ = np.histogram2d(pr, vc, bins=bins, density=True)
        
        px = ph + 1e-10; py = vh + 1e-10; pxy = jh + 1e-10
        # Formula: Sum( P(x,y) * log( P(x,y) / (P(x)*P(y)) ) )
        # broadcast px dan py ke 2D
        px_2d = np.tile(px.reshape(-1, 1), (1, bins))
        py_2d = np.tile(py.reshape(1, -1), (bins, 1))
        
        mi[i] = max(0, np.sum(pxy * np.log2(pxy / (px_2d * py_2d + 1e-10) + 1e-10)))
    return pd.Series(mi, index=df.index, name='mi_price_volume')

def volume_profile_poc(df, num_bins=50):
    """
    Menghitung Point of Control (POC) dan Value Area (70%) dari Volume Profile.
    """
    c, v, h, l = df['close'].values, df['volume'].values, df['high'].values, df['low'].values
    n = len(c)
    
    # Ambil range harga dari 200 bar terakhir
    pn, px = np.min(l[-min(200, n):]), np.max(h[-min(200, n):])
    pr = np.zeros(num_bins)
    bn = np.linspace(pn, px, num_bins + 1)
    
    # Distribusikan volume ke dalam bins
    for i in range(max(0, n - 200), n):
        tp = (h[i] + l[i] + c[i]) / 3
        bi = np.clip(int((tp - pn) / (px - pn + 1e-10) * num_bins), 0, num_bins - 1)
        pr[bi] += v[i]
        
    # Hitung Point of Control (Harga dengan volume tertinggi)
    pi = np.argmax(pr)
    pp = (bn[pi] + bn[pi + 1]) / 2
    
    # Hitung Value Area (70% dari total volume di sekitar POC)
    sp = np.sort(pr)[::-1]
    vt = np.sum(pr) * 0.7
    cu = 0
    vb = []
    
    for vo in sp:
        cu += vo
        indices = np.where(pr == vo)[0]
        vb.append(indices)
        if cu >= vt:
            break
            
    # Tentukan batas atas (VAH) dan batas bawah (VAL) dari Value Area
    vi = sorted(set(np.concatenate(vb)))
    vh = bn[vi[-1] + 1] if len(vi) > 0 else px
    vl = bn[vi[0]] if len(vi) > 0 else pn
    
    return pd.DataFrame({
        'poc_price': pp,
        'value_area_high': vh,
        'value_area_low': vl,
        'poc_distance': (c - pp) / (pp + 1e-10)
    }, index=df.index)


def vwap_deviation_bands(df, std_mult=2.0):
    c,v,h,l=df['close'].values,df['volume'].values,df['high'].values,df['low'].values; n=len(c)
    tp=(h+l+c)/3; cv=np.cumsum(tp*v); cvo=np.cumsum(v); vw=cv/(cvo+1e-10)
    vs=np.full(n,np.nan); vu=np.full(n,np.nan); vl=np.full(n,np.nan)
    for i in range(20,n): s=np.std(tp[i-20:i]-vw[i-20:i]); vs[i]=s; vu[i]=vw[i]+s*std_mult; vl[i]=vw[i]-s*std_mult
    return pd.DataFrame({'vwap':vw,'vwap_upper':vu,'vwap_lower':vl,'vwap_std':vs},index=df.index)

def volume_delta_imbalance(df, window=14):
    o,c,h,l,v=df['open'].values,df['close'].values,df['high'].values,df['low'].values,df['volume'].values; n=len(o)
    bv=np.zeros(n); sv=np.zeros(n)
    for i in range(n):
        bd=abs(c[i]-o[i]); tr=h[i]-l[i]+1e-10
        if c[i]>=o[i]: br=np.clip((bd/2+(c[i]-o[i]))/tr,0.4,0.9); bv[i]=v[i]*br; sv[i]=v[i]*(1-br)
        else: sr=np.clip((bd/2+(o[i]-c[i]))/tr,0.4,0.9); sv[i]=v[i]*sr; bv[i]=v[i]*(1-sr)
    return pd.DataFrame({'buy_volume':bv,'sell_volume':sv,'cumulative_delta':np.cumsum(bv-sv),'imbalance_ratio':(bv-sv)/(v+1e-10)},index=df.index)

def polynomial_trend_momentum(df, degree=3, window=50):
    c=df['close'].values; n=len(c); mom=np.full(n,np.nan); cur=np.full(n,np.nan)
    for i in range(window,n):
        x=np.arange(window); cf=np.polyfit(x,c[i-window:i],degree)
        mom[i]=sum(cf[j]*degree*x[-1]**(degree-j-1) for j in range(degree))
        if degree>=2: cur[i]=sum(cf[j]*degree*(degree-1)*x[-1]**(degree-j-2) for j in range(degree-1))
    return pd.DataFrame({'poly_momentum':mom,'poly_curvature':cur},index=df.index)

def adaptive_macd(df, signal_period=9):
    c=df['close'].values; n=len(c); em=talib.EMA(c,10); df_=em-np.roll(em,1)
    zc=[i for i in range(20,n-1) if df_[i-1]*df_[i]<0]
    if len(zc)>=2:
        dc=np.median(np.diff(zc)); af=max(5,int(dc/4)); asl=max(10,int(dc/2))
    else: af,asl,dc=12,26,np.nan
    m,ms,mh=talib.MACD(c,af,asl,signal_period); hs=np.nanstd(mh[-min(100,n):])
    return pd.DataFrame({'adaptive_macd':m,'adaptive_macd_signal':ms,'adaptive_macd_hist':mh,'adaptive_macd_hist_norm':mh/(hs+1e-10),'detected_cycle':dc},index=df.index)

def composite_momentum_score(df):
    """
    Refined Momentum Composite.
    Instead of a 'Kitchen Sink' PCA, we group indicators by quality (Speed vs Strength)
    to prevent over-representation of redundant signals.
    """
    c, h, l, v = df['close'].values, df['high'].values, df['low'].values, df['volume'].values
    
    # Fast Momentum
    rsi = (talib.RSI(c, 14) - 50) / 50
    willr = talib.WILLR(h, l, c, 14) / 100
    
    # Trend Strength
    adx = talib.ADX(h, l, c, 14) / 100
    m, ms, mh = talib.MACD(c, 12, 26, 9)
    macd_norm = np.clip(mh / (talib.STDDEV(mh, 50) + 1e-10), -2, 2) / 2
    
    # Volume Intensity
    mfi = (talib.MFI(h, l, c, v, 14) - 50) / 50
    
    # Feature Matrix
    ft = pd.DataFrame({
        'fast': rsi * 0.7 + willr * 0.3,
        'trend': adx * np.sign(macd_norm),
        'macd': macd_norm,
        'volume': mfi
    }, index=df.index).dropna()
    
    if len(ft) < 50: return pd.DataFrame({'composite_score': np.nan}, index=df.index)
    
    # PCA on concentrated feature groups
    sc = StandardScaler().fit_transform(ft)
    pca = PCA(n_components=1).fit(sc)
    cp = pca.transform(sc).flatten()
    
    res = pd.DataFrame({'composite_score': np.nan}, index=df.index)
    # Ensure directionality: score stays positive if trend is bullish
    loadings = pca.components_[0]
    if loadings[1] < 0: cp = -cp 
    
    res.loc[ft.index, 'composite_score'] = cp
    return res

def regime_adaptive_signal(df):
    c,h,l=df['close'].values,df['high'].values,df['low'].values; n=len(c)
    rsi=talib.RSI(c,14); bu,bm,bl=talib.BBANDS(c,20); m,ms,mh=talib.MACD(c); ad=talib.ADX(h,l,c,14); at=talib.ATR(h,l,c,14)
    km=talib.EMA(c,20); ku=km+2*talib.ATR(h,l,c,20); kl=km-2*talib.ATR(h,l,c,20)
    sig=np.full(n,0,dtype=float); ss=np.full(n,0.0)
    for i in range(200,n):
        rg='trending' if ad[i]>25 else ('volatile' if at[i]/c[i]>0.03 else 'ranging')
        if rg=='trending':
            if mh[i]>0 and mh[i-1]<=0: sig[i]=1; ss[i]=ad[i]/100
            elif mh[i]<0 and mh[i-1]>=0: sig[i]=-1; ss[i]=ad[i]/100
        elif rg=='ranging':
            if rsi[i]<30 and c[i]<bl[i]: sig[i]=1; ss[i]=(30-rsi[i])/30
            elif rsi[i]>70 and c[i]>bu[i]: sig[i]=-1; ss[i]=(rsi[i]-70)/30
        elif rg=='volatile':
            if c[i]>ku[i]: sig[i]=1; ss[i]=(c[i]-ku[i])/(at[i]+1e-10)
            elif c[i]<kl[i]: sig[i]=-1; ss[i]=(kl[i]-c[i])/(at[i]+1e-10)
    return pd.DataFrame({'adaptive_signal':sig,'signal_strength':ss},index=df.index)

def detect_price_anomalies(df, contamination=0.05, lookback=500):
    """
    Optimized Anomaly Detection.
    Limits IsolationForest execution to the recent lookback to avoid O(N^2) bottlenecks.
    """
    c, h, l, v = df['close'].values, df['high'].values, df['low'].values, df['volume'].values
    n = len(c)
    # Use only recent window for performance
    start_idx = max(0, n - lookback)
    slice_df = df.iloc[start_idx:]
    
    # Features (Relative)
    rets = np.log(slice_df['close'] / slice_df['close'].shift(1)).fillna(0)
    vol_z = (slice_df['volume'] - slice_df['volume'].rolling(50).mean()) / (slice_df['volume'].rolling(50).std() + 1e-10)
    
    ft = pd.DataFrame({
        'returns': rets,
        'vol_z': vol_z.fillna(0),
        'hl_range': (slice_df['high'] - slice_df['low']) / slice_df['close']
    }).dropna()
    
    if len(ft) < 50: 
        return pd.DataFrame({'anomaly_score': 0.0, 'is_anomaly': False}, index=df.index)
        
    iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=64)
    pr = iso.fit_predict(ft)
    sc = -iso.score_samples(ft)
    
    res = pd.DataFrame({'anomaly_score': 0.0, 'is_anomaly': False}, index=df.index)
    res.loc[ft.index, 'anomaly_score'] = sc
    res.loc[ft.index, 'is_anomaly'] = pr == -1
    return res

def tail_risk_indicator(df, window=252):
    """
    Stabilized Cornish-Fisher VaR.
    Handles heteroskedasticity (volatility clustering) by standardizing returns 
    with EWMA volatility before calculating skewness and kurtosis.
    """
    c = df['close'].values
    n = len(c)
    ret = np.diff(np.log(c + 1e-10))
    
    # 1. Estimate Local Volatility (EWMA) to handle heteroskedasticity
    vol_est = pd.Series(ret).ewm(span=20).std().values
    std_ret = ret / (vol_est + 1e-10) # Standardized Residuals
    
    c95 = np.full(n, np.nan); c99 = np.full(n, np.nan)
    sk = np.full(n, np.nan); ku = np.full(n, np.nan)
    
    for i in range(window, len(std_ret)):
        wr = std_ret[i-window:i]
        mu_raw, sig_raw = np.mean(ret[i-window:i]), np.std(ret[i-window:i])
        
        # Calculate moments on standardized returns (stationary assumption)
        s, k = stats.skew(wr), stats.kurtosis(wr)
        sk[i+1], ku[i+1] = s, k
        
        # Cornish-Fisher Expansion Z-score
        z05 = -1.645
        zcf_95 = z05 + (s/6*(z05**2-1) + k/24*(z05**3-3*z05) - s**2/36*(2*z05**3-5*z05))
        
        z01 = -2.326
        zcf_99 = z01 + (s/6*(z01**2-1) + k/24*(z01**3-3*z01) - s**2/36*(2*z01**3-5*z01))
        
        # Re-scale to original volatility
        c95[i+1] = -(mu_raw + sig_raw * zcf_95)
        c99[i+1] = -(mu_raw + sig_raw * zcf_99)
        
    return pd.DataFrame({'cornish_fisher_var_95': c95, 'cornish_fisher_var_99': c99, 'skew_std': sk, 'kurt_std': ku}, index=df.index)

def multi_indicator_divergence(df):
    c,h,l=df['close'].values,df['high'].values,df['low'].values; n=len(c)
    rsi=talib.RSI(c,14); m,ms,mh=talib.MACD(c,12,26,9); sk,_=talib.STOCH(h,l,c)
    agr=np.full(n,0.0); dcnt=np.full(n,0)
    for i in range(30,n):
        sc=0
        pc=c[i]>c[i-10]; pr=rsi[i]>rsi[i-10]; pm=mh[i]>mh[i-10]; pk=sk[i]>sk[i-10]
        if pc and not pr: sc-=1; dcnt[i]+=1
        if not pc and pr: sc+=1; dcnt[i]+=1
        if pc and not pm: sc-=1; dcnt[i]+=1
        if not pc and pm: sc+=1; dcnt[i]+=1
        agr[i]=sc
    return pd.DataFrame({'indicator_agreement':agr,'divergence_count':dcnt},index=df.index)

def price_manifold_embedding(df, dim=3, delay=2):
    from scipy.spatial.distance import cdist
    c = df['close'].values; n = len(c)
    nn_d = np.full(n, np.nan); rr = np.full(n, np.nan)
    
    # Pre-calculate embeddings for efficiency
    # Setiap row i adalah vektor [c[i], c[i-delay], c[i-2*delay], ...]
    start_idx = (dim - 1) * delay
    if n <= start_idx + 10: return pd.DataFrame({'nn_distance': nn_d, 'recurrence_rate': rr}, index=df.index)
    
    embeddings = []
    for i in range(start_idx, n):
        embeddings.append([c[i - j * delay] for j in range(dim)])
    embeddings = np.array(embeddings)
    
    # Loop untuk hitung NN distance dan Recurrence Rate
    # Kita mulai setelah ada cukup sejarah (misal 30 bar)
    for i in range(30, len(embeddings)):
        latest = embeddings[i]
        history = embeddings[:i] # Semua vektor sebelum i
        
        # Hitung jarak Euclidean ke semua titik sebelumnya
        dists = cdist([latest], history, 'euclidean')[0]
        dists = dists[dists > 0] # Hindari jarak nol (titik yang sama)
        
        if len(dists) > 0:
            nn_d[i + start_idx] = np.min(dists)
            # Recurrence Rate: % titik yang jaraknya di bawah threshold (10-percentile korelasi)
            thr = np.percentile(dists, 10) if len(dists) > 10 else np.mean(dists) * 0.1
            rr[i + start_idx] = np.sum(dists < (thr + 1e-10)) / len(dists)
            
    return pd.DataFrame({'nn_distance': nn_d, 'recurrence_rate': rr}, index=df.index)

def normalized_rolling_deviation(df, window=50):
    """
    Replaces pseudo-scientific 'Persistence Homology' with Normalized Rolling Deviation.
    Measures the normalized volatility-adjusted price range.
    """
    c = df['close'].values
    n = len(c)
    dev = np.full(n, np.nan)
    for i in range(window, n):
        seg = c[i-window:i]
        mn, mx = np.min(seg), np.max(seg)
        # Normalized Range: (Max - Min) / Standard Deviation
        dev[i] = (mx - mn) / (np.std(seg) + 1e-10)
    return pd.Series(dev, index=df.index, name='normalized_rolling_deviation')

def volume_zscore_mean_reversion(df, window=20):
    v=df['volume'].values; n=len(v); zs=np.full(n,np.nan); sig=np.zeros(n)
    for i in range(window,n):
        mu=np.mean(v[i-window:i]); sd=np.std(v[i-window:i])+1e-10
        zs[i]=(v[i]-mu)/sd
        if zs[i]>2: sig[i]=-1 # Overbought volume -> sell
        elif zs[i]<-2: sig[i]=1 # Oversold volume -> buy
    return pd.DataFrame({'volume_zscore':zs,'mean_reversion_signal':sig},index=df.index)

def elliott_wave_detector(df):
    c=df['close'].values; n=len(c); pos=np.zeros(n,dtype=int)
    pks,trh=[],[]
    for i in range(5,n-5): w=c[i-5:i+6]; (pks if c[i]==np.max(w) else trh).append(i)
    # Simplified Elliott wave counting based on peak/trough progression
    for i in range(len(pks)-4):
        pts=[pks[i+j] for j in range(5)]
        vals=[c[p] for p in pts]
        if vals[0]<vals[1]<vals[2]>vals[3]<vals[4]:
            for j,p in enumerate(pts): pos[p]=j+1
    return pd.DataFrame({'elliott_wave_position':pos},index=df.index)

def detect_order_blocks(df):
    o,c,h,l=df['open'].values,df['close'].values,df['high'].values,df['low'].values; n=len(o)
    bol=np.full(n,np.nan); boh=np.full(n,np.nan); bsl=np.full(n,np.nan); bsh=np.full(n,np.nan)
    for i in range(2,n):
        # Bullish OB: last bearish candle before a strong bullish move
        if c[i-1]<o[i-1] and c[i]>o[i] and (c[i]-o[i])>2*np.std(c[:i]+1e-10):
            bol[i:]=l[i-1]; boh[i:]=h[i-1]
        # Bearish OB
        if c[i-1]>o[i-1] and c[i]<o[i] and (o[i]-c[i])>2*np.std(c[:i]+1e-10):
            bsl[i:]=l[i-1]; bsh[i:]=h[i-1]
    return pd.DataFrame({'bullish_ob_low':bol,'bullish_ob_high':boh,'bearish_ob_low':bsl,'bearish_ob_high':bsh},index=df.index)

def detect_fair_value_gaps(df):
    h,l=df['high'].values,df['low'].values; n=len(h); ft=np.zeros(n,dtype=int); fb=np.full(n,np.nan); ft_=np.full(n,np.nan)
    for i in range(2,n):
        if l[i]>h[i-2]: ft[i]=1; fb[i]=h[i-2]; ft_[i]=l[i] # Bullish FVG
        elif h[i]<l[i-2]: ft[i]=2; fb[i]=l[i-2]; ft_[i]=h[i] # Bearish FVG
    return pd.DataFrame({'fvg_type':ft,'fvg_bottom':fb,'fvg_top':ft_},index=df.index)

def detect_liquidity_sweeps(df, lookback=20):
    c,h,l=df['close'].values,df['high'].values,df['low'].values; n=len(c); sw=np.zeros(n)
    for i in range(lookback,n):
        rh=np.max(h[i-lookback:i]); rl=np.min(l[i-lookback:i])
        if l[i]<rl and c[i]>rl: sw[i]=-1 # Sweep low
        elif h[i]>rh and c[i]<rh: sw[i]=1 # Sweep high
    return pd.Series(sw,index=df.index,name='liquidity_sweep')

def smart_money_concepts(df):
    c,h,l=df['close'].values,df['high'].values,df['low'].values; n=len(c)
    bos=np.zeros(n); choc=np.zeros(n)
    for i in range(20,n):
        rh=np.max(h[i-20:i]); rl=np.min(l[i-20:i])
        if c[i]>rh: bos[i]=1
        elif c[i]<rl: bos[i]=-1
        # CHoCH: Trend change
        if i>20 and bos[i-1]!=0 and bos[i]!=0 and bos[i]!=bos[i-1]: choc[i]=bos[i]
    return pd.DataFrame({'break_of_structure':bos,'change_of_character':choc},index=df.index)

def dynamic_position_sizer(df, risk_pct=0.02):
    c=df['close'].values; n=len(c); at=talib.ATR(df['high'].values,df['low'].values,c,14)
    ps=np.full(n,np.nan); az=np.full(n,np.nan)
    for i in range(20,n):
        sl=at[i]*2; risk_per_share=sl
        pos_size=(c[i]*risk_pct)/risk_per_share if risk_per_share>0 else 0
        ps[i]=min(pos_size,100); az[i]=(at[i]-np.mean(at[i-20:i]))/(np.std(at[i-20:i])+1e-10)
    return pd.DataFrame({'position_size_pct':ps,'atr_zscore':az},index=df.index)

# ================== TALIB DEEP ANALYSIS FUNCTIONS ==================
def spectral_momentum_score(close, volume, period=14):
    h=np.maximum(close,np.roll(close,1)); l=np.minimum(close,np.roll(close,1))
    rsi=talib.RSI(close,period); cci=talib.CCI(h,l,close,period); wr=talib.WILLR(h,l,close,period); mfi=talib.MFI(h,l,close,volume,period)
    m=np.vstack([rsi,(cci+200)/4,wr+100,mfi]); z=np.zeros_like(m)
    for i in range(4): v_=m[i]; vd=~np.isnan(v_); z[i,vd]=stats.zscore(v_[vd]) if vd.sum()>1 else 0
    vm=talib.EMA(volume.astype(float),period); vr=np.where(vm>0,volume/vm,1.0)
    return np.nanmean(z,axis=0)*np.log1p(vr)

def price_volume_impulse(open_, close, volume, period=20):
    """
    Replaces pseudo-scientific 'Kinetic Energy' with Price-Volume Impulse.
    Measures the magnitude of price movement normalized by volume efficiency.
    """
    # Use Log Returns for mathematical rigor
    returns = np.log(close / (open_ + 1e-10))
    # Impulse = Volume * Squared Return (Magnitude of activity)
    impulse = volume * (returns ** 2)
    # Smooth with EMA to capture trend in intensity
    impulse_ema = talib.EMA(impulse.astype(float), period)
    
    # Normalize via Rolling Rank (Percentile) to make it scale-invariant
    res = np.full_like(impulse_ema, np.nan)
    for i in range(period, len(impulse_ema)):
        window = impulse_ema[max(0, i-100):i+1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            res[i] = stats.percentileofscore(valid, impulse_ema[i])
    return res

def momentum_divergence_index(close, volume, period=14):
    pr=talib.ROC(close,period); vr=talib.ROC(volume.astype(float),period); d=pr-vr; mdi=np.full_like(d,np.nan)
    vd=~np.isnan(d)
    if vd.sum()>1: mdi[vd]=stats.zscore(d[vd])
    return mdi

def adaptive_momentum_oscillator(close, period=20):
    dir_=np.abs(close-np.roll(close,period)); vol=np.zeros(len(close))
    for i in range(period,len(close)): vol[i]=np.sum(np.abs(np.diff(close[i-period:i+1])))
    er=np.where(vol>0,dir_/vol,0.5); er[:period]=np.nan; ap=np.round(5+(1-er)*25).astype(int)
    amo=np.full(len(close),np.nan)
    for i in range(30,len(close)): p=int(ap[i]); amo[i]=talib.RSI(close[:i+1],timeperiod=p)[-1] if not np.isnan(close[i-p]) else np.nan
    return amo

def volatility_regime_classifier(close, period=20):
    h=close*1.005; l=close*0.995; at=talib.ATR(h,l,close,period); u,md,lo=talib.BBANDS(close,period)
    bw=(u-lo)/md; ad=talib.ADX(h,l,close,period); hv=talib.STDDEV(close,period)/close*100
    bm=pd.Series(bw).rolling(100).median().values; reg=np.full(len(close),np.nan)
    for i in range(period+1,len(close)):
        hv_=bw[i]>(bm[i] if not np.isnan(bm[i]) else 0.02); tr=ad[i]>25 if not np.isnan(ad[i]) else False
        reg[i]=0 if tr and not hv_ else 1 if tr and hv_ else 2 if not tr and not hv_ else 3
    lb={0:"LowVol_Trend",1:"HighVol_Trend",2:"LowVol_Chop",3:"HighVol_Chop"}
    return pd.DataFrame({"regime_code":reg,"regime_label":[lb.get(r,"?") for r in reg],"atr":at,"bb_width":bw,"adx":ad,"hv_pct":hv})

def fractal_volatility_index(close, periods=None):
    if periods is None: periods=[5,10,20,40]
    h=close*1.005; l=close*0.995; ats=[talib.ATR(h,l,close,p) for p in periods]; av=np.vstack(ats)
    lp=np.log(periods); fv=np.full(len(close),np.nan)
    for i in range(max(periods),len(close)):
        y=np.log(av[:,i]+1e-10)
        if not np.any(np.isnan(y)): fv[i]=stats.linregress(lp,y)[0]
    return fv

def bollinger_squeeze_intensity(close, period=20, kc_mult=1.5):
    h=close*1.005; l=close*0.995
    ub,mb,lb=talib.BBANDS(close,period,2,2); bbw=ub-lb
    at=talib.ATR(h,l,close,period); em=talib.EMA(close,period); ku=em+kc_mult*at; kl=em-kc_mult*at; kw=ku-kl
    return np.where(kw>0,(kw-bbw)/kw,0)

def yang_zhang_volatility(open_, high, low, close, period=20):
    k=0.34/(1.34+(period+1)/(period-1)); n=len(close)
    lo=np.log(open_/np.roll(close,1)); lc=np.log(close/open_); lh=np.log(high/open_); ll=np.log(low/open_)
    rs=lh*(lh-lc)+ll*(ll-lc); yz=np.full(n,np.nan)
    for i in range(period,n):
        ov=np.var(lo[i-period+1:i+1]); oc=np.var(lc[i-period+1:i+1]); rv=np.mean(rs[i-period+1:i+1])
        yz[i]=np.sqrt(ov+k*oc+(1-k)*rv)*np.sqrt(252)
    return yz

def triple_ema_confluence_score(close, periods=(8,21,55)):
    p1,p2,p3=periods; e1=talib.EMA(close,p1); e2=talib.EMA(close,p2); e3=talib.EMA(close,p3)
    n=len(close); sc=np.zeros(n); al=np.zeros(n); sp=np.zeros(n); sl=np.zeros(n)
    for i in range(p3+1,n):
        if np.any(np.isnan([e1[i],e2[i],e3[i]])): continue
        ba=(e1[i]>e2[i]>e3[i]); be=(e1[i]<e2[i]<e3[i])
        al[i]=1 if ba else (-1 if be else 0)
        cs=(e1[i]-e3[i])/e3[i]*100; ps=(e1[i-1]-e3[i-1])/e3[i-1]*100; sp[i]=1 if cs>ps else -1
        sl[i]=np.sign(np.mean([e1[i]-e1[i-1],e2[i]-e2[i-1],e3[i]-e3[i-1]]))
        sc[i]=al[i]+sp[i]+sl[i]
    return pd.DataFrame({"tecs_score":sc,"ema_aligned":al,"ema_spread":sp,"ema_slope":sl,"ema_fast":e1,"ema_mid":e2,"ema_slow":e3})

def supertrend_dynamic(high, low, close, atr_period=10, multiplier=3.0):
    at=talib.ATR(high,low,close,atr_period); ap=pd.Series(at).rolling(100).rank(pct=True).values
    ml=multiplier*(0.7+ap*0.6); hl2=(high+low)/2; ub=hl2+ml*at; lb=hl2-ml*at
    st=np.full(len(close),np.nan); dr=np.zeros(len(close))
    for i in range(1,len(close)):
        if np.isnan(at[i]): continue
        if ub[i]<ub[i-1] or close[i-1]>ub[i-1]: pass
        else: ub[i]=ub[i-1]
        if lb[i]>lb[i-1] or close[i-1]<lb[i-1]: pass
        else: lb[i]=lb[i-1]
        if np.isnan(st[i-1]): st[i]=lb[i]; dr[i]=1
        elif st[i-1]==ub[i-1]: dr[i]=-1 if close[i]<=ub[i] else 1
        else: dr[i]=1 if close[i]>=lb[i] else -1
        st[i]=lb[i] if dr[i]==1 else ub[i]
    return pd.DataFrame({"supertrend":st,"direction":dr})

def multi_ma_ribbon_score(close, ema_range=None):
    if ema_range is None: ema_range=[5,8,13,21,34,55,89,144]
    ems={p:talib.EMA(close,p) for p in ema_range}; bc=np.zeros(len(close)); ss=np.zeros(len(close)); sp=np.zeros(len(close))
    for i in range(max(ema_range)+1,len(close)):
        vs=[ems[p][i] for p in ema_range if not np.isnan(ems[p][i])]; pr=[ems[p][i-1] for p in ema_range if not np.isnan(ems[p][i-1])]
        if len(vs)<2: continue
        bc[i]=sum(1 for v in vs if close[i]>v); ss[i]=np.mean([(v-p)/p*100 for v,p in zip(vs,pr)]); sp[i]=(max(vs)-min(vs))/close[i]*100
    return pd.DataFrame({"mmrs_bull_count":bc,"mmrs_score":bc/len(ema_range)*2-1,"ribbon_slope":ss,"ribbon_spread":sp})

def volume_price_momentum_divergence(close, volume, period=14):
    ob=talib.OBV(close,volume); pm,ps,ph=talib.MACD(close,12,26,9); vm,vs,vh=talib.MACD(ob,12,26,9)
    vd=vh-ph; vdz=np.full_like(vd,np.nan); vd_=~np.isnan(vd)
    if vd_.sum()>1: vdz[vd_]=stats.zscore(vd[vd_])
    return pd.DataFrame({"vpmd_raw":vd,"vpmd_zscore":vdz,"price_hist":ph,"obv_hist":vh,"obv":ob})

def vwap_bands_lib3(high, low, close, volume, period=20, n_std=2.0):
    tp=(high+low+close)/3; tv=tp*volume; vw=np.full(len(close),np.nan); sd=np.full(len(close),np.nan)
    for i in range(period-1,len(close)):
        tw=tv[i-period+1:i+1]; wv=volume[i-period+1:i+1]
        if wv.sum()>0: vw[i]=tw.sum()/wv.sum(); sd[i]=np.std(tp[i-period+1:i+1])
    return pd.DataFrame({"vwap":vw,"upper_2":vw+n_std*sd,"upper_1":vw+sd,"lower_1":vw-sd,"lower_2":vw-n_std*sd,"vwap_dev":(close-vw)/(sd+1e-10)})

def cumulative_delta_proxy(open_, high, low, close, volume):
    hr=high-low+1e-10; bd=volume*(2*close-high-low)/hr; cd=np.cumsum(bd); cm,cs,ch=talib.MACD(cd,12,26,9)
    return pd.DataFrame({"bar_delta":bd,"cdp":cd,"cdp_macd":cm,"cdp_signal":cs,"cdp_hist":ch})

def volume_weighted_rsi(close, volume, period=14):
    d=np.diff(close,prepend=close[0]); g=np.where(d>0,d*volume,0); l_=np.where(d<0,-d*volume,0)
    ge=talib.EMA(g,period); le=talib.EMA(l_,period); rs=np.where(le!=0,ge/le,100)
    return 100-(100/(1+rs))

def on_balance_momentum(close, volume, fast=5, slow=20):
    ob=talib.OBV(close,volume); of_=talib.EMA(ob,fast); os=talib.EMA(ob,slow); ol=of_-os; om=talib.EMA(ol,9)
    return pd.DataFrame({"obm_line":ol,"obm_sig":om,"obm_hist":ol-om,"obv":ob})

def candlestick_composite_signal(open_, high, low, close):
    """
    Intelligent Candlestick Confluence.
    Instead of summing 61 patterns (O(61*N)), we group by intent and 
    use a non-linear confluence score to avoid redundant overconfidence.
    """
    bull_patterns = [
        'CDLHAMMER', 'CDLINVERTEDHAMMER', 'CDLMORNINGSTAR', 'CDLPIERCING', 
        'CDLENGULFING', 'CDL3WHITESOLDIERS', 'CDLBELTHOLD'
    ]
    bear_patterns = [
        'CDLSHOOTINGSTAR', 'CDLHANGINGMAN', 'CDLEVENINGSTAR', 'CDLDARKCLOUDCOVER',
        'CDLENGULFING', 'CDL3BLACKCROWS', 'CDLBELTHOLD'
    ]
    
    n = len(close)
    bull_confluence = np.zeros(n)
    bear_confluence = np.zeros(n)
    
    for fn in bull_patterns:
        try: 
            r = getattr(talib, fn)(open_, high, low, close)
            # Only count as bullish if value is positive (talib returns +/- 100)
            bull_confluence += np.where(r > 0, 100, 0)
        except: pass
        
    for fn in bear_patterns:
        try:
            r = getattr(talib, fn)(open_, high, low, close)
            bear_confluence += np.where(r < 0, 100, 0)
        except: pass
        
    # Non-linear normalization: Confluence is high if multiple patterns agree,
    # but with diminishing returns for redundant patterns.
    bull_score = np.tanh(bull_confluence / 200.0)
    bear_score = -np.tanh(bear_confluence / 200.0)
    
    return pd.DataFrame({
        "bull_intensity": bull_score,
        "bear_intensity": bear_score,
        "ccs_score": bull_score + bear_score
    })

def pivot_point_analysis(high, low, close, method="all"):
    pp=(high+low+close)/3; res={"pivot":pp}; hr=high-low
    if method in ("classic","all"): res.update({"r1":2*pp-low,"s1":2*pp-high,"r2":pp+hr,"s2":pp-hr,"r3":high+2*(pp-low),"s3":low-2*(high-pp)})
    if method in ("fibonacci","all"): res.update({"fib_r1":pp+0.382*hr,"fib_r2":pp+0.618*hr,"fib_s1":pp-0.382*hr,"fib_s2":pp-0.618*hr})
    if method in ("camarilla","all"): res.update({"cam_r3":close+hr*1.1/4,"cam_s3":close-hr*1.1/4})
    return pd.DataFrame(res)

def fractal_support_resistance(high, low, window=5):
    n=len(high); fh=np.full(n,np.nan); fl=np.full(n,np.nan)
    for i in range(window,n-window):
        if high[i]==max(high[i-window:i+window+1]): fh[i]=high[i]
        if low[i]==min(low[i-window:i+window+1]): fl[i]=low[i]
    lfh=np.full(n,np.nan); lfl=np.full(n,np.nan); ch=cf=np.nan
    for i in range(n):
        if not np.isnan(fh[i]): ch=fh[i]
        if not np.isnan(fl[i]): cf=fl[i]
        lfh[i]=ch; lfl[i]=cf
    return pd.DataFrame({"fractal_high":fh,"fractal_low":fl,"nearest_resist":lfh,"nearest_support":lfl})

def relative_vigor_index_enhanced(open_, high, low, close, period=10):
    def swm(a, n):
        o = np.full(len(a), np.nan)
        w = np.array([1, 2, 2, 1]) / 6.0
        for i in range(3, len(a)): # Adjusted range for dot product window
            o[i] = np.dot(a[i-3:i+1], w)
        return o

    nu = swm(close - open_, 4)
    de = swm(high - low, 4)
    rv = np.where(de != 0, nu / de, 0)
    re = talib.EMA(rv, period)
    sg = swm(re, 4)
    return pd.DataFrame({"rvi": re, "signal": sg, "hist": re - sg})


def stochastic_rsi_divergence(close, period=14, smooth_k=3, smooth_d=3):
    rsi=talib.RSI(close,period); lr=talib.MIN(rsi,period); hr=talib.MAX(rsi,period); rr=hr-lr
    sr=np.where(rr>0,(rsi-lr)/rr*100,50); k=talib.EMA(sr,smooth_k); d=talib.EMA(k,smooth_d); dv=np.zeros(len(close))
    for i in range(period*2,len(close)):
        ps=close[i-period*2:i+1]; ss=k[i-period*2:i+1]
        if np.any(np.isnan(ss)): continue
        pl=find_peaks(-ps,distance=5)[0]; sl=find_peaks(-ss,distance=5)[0]
        if len(pl)>=2 and len(sl)>=2:
            p_,s_=pl[-2:],sl[-2:]
            if ps[p_[-1]]<ps[p_[-2]] and ss[s_[-1]]>ss[s_[-2]]: dv[i]=1
        ph=find_peaks(ps,distance=5)[0]; sh=find_peaks(ss,distance=5)[0]
        if len(ph)>=2 and len(sh)>=2:
            p_,s_=ph[-2:],sh[-2:]
            if ps[p_[-1]]>ps[p_[-2]] and ss[s_[-1]]<ss[s_[-2]]: dv[i]=-1
    return pd.DataFrame({"stoch_rsi_k":k,"stoch_rsi_d":d,"divergence":dv})

def chande_kroll_stop(high, low, close, atr_period=10, stop_period=9, q=1.5):
    at=talib.ATR(high,low,close,atr_period); hh=talib.MAX(high,stop_period); ll=talib.MIN(low,stop_period)
    fh=hh-q*at; fl=ll+q*at; ss=talib.MAX(fh,stop_period); sl=talib.MIN(fl,stop_period)
    tr=np.where(close>ss,1,np.where(close<sl,-1,0))
    return pd.DataFrame({"stop_long":sl,"stop_short":ss,"trend":tr})

def dmi_crossover_quality(high, low, close, period=14):
    ad=talib.ADX(high,low,close,period); pd_=talib.PLUS_DI(high,low,close,period); md_=talib.MINUS_DI(high,low,close,period)
    co=np.zeros(len(close)); qu=np.zeros(len(close))
    for i in range(1,len(close)):
        if np.isnan(ad[i]): continue
        bc=(pd_[i]>md_[i]) and (pd_[i-1]<=md_[i-1]); be=(pd_[i]<md_[i]) and (pd_[i-1]>=md_[i-1])
        if bc or be:
            co[i]=1 if bc else -1; qu[i]=min(ad[i],60)/60*40+min(max(ad[i]-ad[i-1],0),5)/5*30+min(abs(pd_[i]-md_[i]),30)/30*30
    return pd.DataFrame({"adx":ad,"plus_di":pd_,"minus_di":md_,"crossover":co,"quality":qu})

def dominant_cycle_detector(close, window=64):
    n=len(close); dp=np.full(n,np.nan); pw=np.full(n,np.nan); ph=np.full(n,np.nan)
    for i in range(window,n):
        s=close[i-window:i]-np.mean(close[i-window:i]); w=np.hanning(window); y=np.fft.rfft(s*w)
        p=np.abs(y)**2; f=np.fft.rfftfreq(window); m=(f>1/window)&(f<0.5)
        if m.sum()==0: continue
        di=np.argmax(p[m]); df=f[m][di]; dp[i]=1.0/df if df>0 else np.nan; pw[i]=p[m][di]; ph[i]=np.degrees(np.angle(y[m][di]))
    return pd.DataFrame({"dom_period":dp,"dom_power":pw,"phase_deg":ph})

def spectral_band_filter(close, low_cut=0.05, high_cut=0.25):
    n=len(close); yf=np.fft.rfft(close); f=np.fft.rfftfreq(n)
    yf_bp=yf.copy(); yf_bp[~((np.abs(f)>=low_cut)&(np.abs(f)<=high_cut))]=0
    yf_lp=yf.copy(); yf_lp[np.abs(f)>=low_cut]=0
    yf_hp=yf.copy(); yf_hp[np.abs(f)<=high_cut]=0
    return pd.DataFrame({"filtered_price":np.fft.irfft(yf_bp,n=n),"trend_component":np.fft.irfft(yf_lp,n=n),"noise_component":np.fft.irfft(yf_hp,n=n)})

def instantaneous_phase_indicator(close, period=7):
    hs,hl=talib.HT_SINE(close); hp,hq=talib.HT_PHASOR(close); ip=np.degrees(np.arctan2(hq,hp))%360
    pv=np.gradient(np.unwrap(np.radians(ip)))
    return pd.DataFrame({"ht_sine":hs,"ht_lead":hl,"inphase":hp,"quadrature":hq,"inst_phase_deg":ip,"phase_velocity":pv,"dcperiod":talib.HT_DCPERIOD(close),"dcphase":talib.HT_DCPHASE(close),"trendmode":talib.HT_TRENDMODE(close)})

def price_entropy_score(close, period=20, bins=10):
    ret=np.diff(np.log(close),prepend=np.log(close[0])); pe=np.full(len(close),np.nan)
    for i in range(period,len(close)):
        h,_=np.histogram(ret[i-period:i],bins=bins,density=True); h=h[h>0]
        pe[i]=-np.sum(h*np.log(h))
    mn,mx=np.nanmin(pe),np.nanmax(pe); pe=(pe-mn)/(mx-mn+1e-10) if mx>mn else pe
    return pe

def hurst_lib3(close, period=100):
    def hr(ts):
        n=len(ts); d=np.diff(np.log(ts)); m=np.cumsum(d)-np.cumsum(d)/n*np.arange(1,n+1)
        R=np.max(m)-np.min(m); S=np.std(d)
        return np.log(R/S)/np.log(n/2) if S>0 else 0.5
    hu=np.full(len(close),np.nan)
    for i in range(period,len(close)):
        s=close[i-period:i+1]
        if not np.any(s<=0):
            try: hu[i]=hr(s)
            except: pass
    return hu

def permutation_entropy(close, period=20, order=3):
    from itertools import permutations
    def pe(x,m):
        n=len(x); ct={}; t=0
        for i in range(n-m+1): p=tuple(np.argsort(x[i:i+m])); ct[p]=ct.get(p,0)+1; t+=1
        pr=np.array(list(ct.values()))/t
        return -np.sum(pr*np.log2(pr+1e-12))/np.log2(math.factorial(m))
    r=np.full(len(close),np.nan)
    for i in range(period+order,len(close)): r[i]=pe(close[i-period:i],order)
    return r

def market_inefficiency_index(close, volume, period=20):
    ret=np.diff(np.log(close),prepend=np.log(close[0])); mii=np.full(len(close),np.nan)
    for i in range(period*2,len(close)):
        s=ret[i-period*2:i]; ac=np.corrcoef(s[:-1],s[1:])[0,1] if np.std(s[:-1])>0 else 0
        v1=np.var(s); v5=np.var(s[::5]) if len(s[::5])>2 else v1; vd=abs((v5/(5*v1+1e-10))-1.0)
        h,_=np.histogram(s,bins=8,density=True); h=h[h>0]; en=np.sum(h*np.log(h+1e-10))/np.log(8)
        mii[i]=(abs(ac)*0.4+vd*0.3+(1-en)*0.3)*100
    return mii

def master_signal_score(open_, high, low, close, volume, period=14):
    """
    Deconstructs the 'Frankenstein Model' and replaces it with a Regime-Adaptive Score.
    Weights are dynamically allocated based on ADX and Volatility Regime.
    """
    # 1. Component Calculation
    rsi = talib.RSI(close, period)
    m, ms, mh = talib.MACD(close, 12, 26, 9)
    # Standardize MACD Histogram to its local volatility
    mh_std = talib.STDDEV(mh, timeperiod=50) + 1e-10
    mh_norm = np.clip(mh / mh_std, -2, 2)
    
    ci = talib.CCI(high, low, close, period)
    ad = talib.ADX(high, low, close, period)
    pdi = talib.PLUS_DI(high, low, close, period)
    mdi = talib.MINUS_DI(high, low, close, period)
    sk, sd = talib.STOCH(high, low, close)
    mf = talib.MFI(high, low, close, volume, period)
    st = supertrend_dynamic(high, low, close)
    
    # 2. Determine Regime
    # Trending if ADX > 25 and separating DI lines
    trend_strength = np.clip(ad / 50.0, 0, 1)
    is_trending = (ad > 25) & (np.abs(pdi - mdi) > 10)
    
    # 3. Component Scores (Normalized to [-1, 1])
    # Trend Component
    trend_score = np.where(pdi > mdi, 1.0, -1.0) * trend_strength
    st_score = st["direction"].values
    
    # Oscillator Component (Inverse relationship in trends vs range)
    # RSI: Neutralize towards 50 for normalization
    rsi_norm = (rsi - 50) / 50.0
    # Stochastic: -1 to 1 mapping
    stoch_norm = (sk - 50) / 50.0
    
    # 4. Regime-Adaptive Weighting
    # Logic: In trends, give more weight to MACD/Trend and LESS to RSI (which stays overbought/oversold)
    # In range, give more weight to RSI/Stoch and ignore trend filters.
    
    mss_total = np.zeros(len(close))
    
    for i in range(period*2, len(close)):
        if is_trending[i]:
            # TRENDING REGIME
            w_trend = 0.5
            w_mom = 0.3
            w_osc = 0.1
            w_vol = 0.1
            
            score = (
                (trend_score[i] * 0.6 + st_score[i] * 0.4) * w_trend +
                (mh_norm[i] / 2.0) * w_mom +
                (0) * w_osc + # Ignore RSI in strong trends to avoid 'Neutral' drift
                (np.sign(mf[i] - 50) * 0.5) * w_vol
            )
        else:
            # RANGING / MEAN-REVERTING REGIME
            w_trend = 0.1
            w_mom = 0.2
            w_osc = 0.5
            w_vol = 0.2
            
            # Oscillators are primary signal in range
            osc_sig = -1.0 if rsi[i] > 70 else (1.0 if rsi[i] < 30 else 0)
            stoch_sig = -1.0 if sk[i] > 80 else (1.0 if sk[i] < 20 else 0)
            
            score = (
                (trend_score[i]) * w_trend +
                (mh_norm[i] / 2.0) * w_mom +
                (osc_sig * 0.6 + stoch_sig * 0.4) * w_osc +
                (np.sign(mf[i] - 50) * 0.5) * w_vol
            )
        
        mss_total[i] = score * 10.0 # Scale to roughly [-10, 10]

    res = pd.DataFrame({
        "mss_total": mss_total,
        "regime": np.where(is_trending, "TRENDING", "RANGING"),
        "trend_power": trend_strength
    })
    
    res["mss_signal"] = np.where(res["mss_total"] > 6, "STRONG BUY",
                        np.where(res["mss_total"] > 2, "BUY",
                        np.where(res["mss_total"] < -6, "STRONG SELL",
                        np.where(res["mss_total"] < -2, "SELL", "NEUTRAL"))))
    
    return res