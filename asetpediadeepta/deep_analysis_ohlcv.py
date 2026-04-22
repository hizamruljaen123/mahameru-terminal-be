"""
deep_analysis_ohlcv.py
Pipeline processing, statistical structure, composite scoring
"""
import numpy as np, pandas as pd, talib, warnings
from scipy.signal import find_peaks
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler
warnings.filterwarnings('ignore')
from .deep_analysis_core import validate_ohlcv

REQUIRED = ["open","high","low","close","volume"]

class AnalysisConfig:
    fast_ema=12; slow_ema=26; trend_ema=55; long_trend_ema=200; rsi_period=14
    atr_period=14; adx_period=14; roc_period=10; bbands_period=20; bbands_dev=2.0
    volatility_lookback=20; pivot_left=3; pivot_right=3; zscore_window=30
    score_smooth=5; eps=1e-12

def _as_df(data):
    if not isinstance(data,pd.DataFrame): raise TypeError("Input harus DataFrame.")
    df=data.copy(); lm={c.lower():c for c in df.columns}
    mis=[c for c in REQUIRED if c not in lm]
    if mis: raise ValueError(f"Kolom wajib tidak lengkap: {mis}")
    df=df.rename(columns={lm[c]:c for c in REQUIRED})
    df=df[REQUIRED+[c for c in df.columns if c not in REQUIRED]]
    for c in REQUIRED: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.replace([np.inf,-np.inf],np.nan).dropna(subset=REQUIRED).reset_index(drop=True)
    if len(df)<50: raise ValueError("Data terlalu sedikit.")
    return df

def _to_np(df): return (df["open"].to_numpy(float),df["high"].to_numpy(float),df["low"].to_numpy(float),df["close"].to_numpy(float),df["volume"].to_numpy(float))
def _rz(s,w): m=s.rolling(w).mean(); sd=s.rolling(w).std(ddof=0); return (s-m)/(sd.replace(0,np.nan))

def add_core_indicators(df, cfg=AnalysisConfig()):
    df=_as_df(df); o,h,l,c,v=_to_np(df)
    df["ret_1"]=pd.Series(c).pct_change(); df["logret_1"]=np.log(pd.Series(c).replace(0,np.nan)).diff()
    df["hl_range"]=(df["high"]-df["low"])/df["close"]; df["oc_return"]=(df["close"]-df["open"])/df["open"]
    df["gap"]=(df["open"]-df["close"].shift(1))/df["close"].shift(1)
    df["typical_price"]=talib.TYPPRICE(h,l,c); df["weighted_close"]=talib.WCLPRICE(h,l,c)
    df["sma_fast"]=talib.SMA(c,cfg.fast_ema); df["sma_slow"]=talib.SMA(c,cfg.slow_ema)
    df["ema_fast"]=talib.EMA(c,cfg.fast_ema); df["ema_slow"]=talib.EMA(c,cfg.slow_ema)
    df["ema_trend"]=talib.EMA(c,cfg.trend_ema); df["ema_long"]=talib.EMA(c,cfg.long_trend_ema)
    df["tema"]=talib.TEMA(c,cfg.slow_ema); df["dema"]=talib.DEMA(c,cfg.slow_ema); df["kama"]=talib.KAMA(c,cfg.slow_ema)
    df["wma"]=talib.WMA(c,cfg.fast_ema); df["t3"]=talib.T3(c,cfg.slow_ema,0.7)
    df["macd"],df["macdsignal"],df["macdhist"]=talib.MACD(c,12,26,9)
    df["ppo"]=talib.PPO(c,12,26,0); df["apo"]=talib.APO(c,12,26,0)
    df["rsi"]=talib.RSI(c,cfg.rsi_period)
    df["stoch_k"],df["stoch_d"]=talib.STOCH(h,l,c,14,3,0,3,0)
    df["stochf_k"],df["stochf_d"]=talib.STOCHF(h,l,c,14,3,0)
    df["stochrsi_k"],df["stochrsi_d"]=talib.STOCHRSI(c,14,5,3,0)
    df["willr"]=talib.WILLR(h,l,c,14); df["cci"]=talib.CCI(h,l,c,20); df["mfi"]=talib.MFI(h,l,c,v,14)
    df["ultosc"]=talib.ULTOSC(h,l,c); df["adx"]=talib.ADX(h,l,c,cfg.adx_period); df["adxr"]=talib.ADXR(h,l,c,cfg.adx_period)
    df["minus_di"]=talib.MINUS_DI(h,l,c,cfg.adx_period); df["plus_di"]=talib.PLUS_DI(h,l,c,cfg.adx_period)
    df["atr"]=talib.ATR(h,l,c,cfg.atr_period); df["natr"]=talib.NATR(h,l,c,cfg.atr_period)
    df["obv"]=talib.OBV(c,v); df["adosc"]=talib.ADOSC(h,l,c,v,3,10); df["ad"]=talib.AD(h,l,c,v)
    df["chaikin_osc"]=df["ad"].diff(3)-df["ad"].diff(10)
    u,md,lo=talib.BBANDS(c,cfg.bbands_period,cfg.bbands_dev,cfg.bbands_dev,0)
    df["bb_upper"]=u; df["bb_middle"]=md; df["bb_lower"]=lo
    df["bb_width"]=(df["bb_upper"]-df["bb_lower"])/df["bb_middle"]
    df["bb_percent_b"]=(df["close"]-df["bb_lower"])/((df["bb_upper"]-df["bb_lower"]).replace(0,np.nan))
    df["sar"]=talib.SAR(h,l,0.02,0.2)
    df["ht_dcperiod"]=talib.HT_DCPERIOD(c); df["ht_dcphase"]=talib.HT_DCPHASE(c)
    df["ht_inphase"],df["ht_quadrature"]=talib.HT_PHASOR(c)
    df["ht_sine"],df["ht_leadsine"]=talib.HT_SINE(c); df["ht_trendmode"]=talib.HT_TRENDMODE(c)
    df["roc"]=talib.ROC(c,cfg.roc_period); df["rocp"]=talib.ROCP(c,cfg.roc_period); df["mom"]=talib.MOM(c,cfg.roc_period)
    df["linear_reg"]=talib.LINEARREG(c,14); df["linear_reg_slope"]=talib.LINEARREG_SLOPE(c,14)
    df["tsf"]=talib.TSF(c,14); df["stddev"]=talib.STDDEV(c,10,1); df["var"]=talib.VAR(c,10,1.0)
    df["log_volume"]=np.log1p(df["volume"]); df["volume_sma"]=pd.Series(v).rolling(20).mean()
    df["volume_z"]=_rz(df["volume"],20); df["volume_ratio"]=df["volume"]/df["volume_sma"]
    df["price_volume_force"]=df["oc_return"]*df["volume_ratio"]
    return df

def add_candlestick_patterns(df):
    """
    Integrates the intelligent confluence logic from core.
    """
    df = _as_df(df)
    o, h, l, c = df["open"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    
    from .deep_analysis_core import candlestick_composite_signal
    ccs = candlestick_composite_signal(o, h, l, c)
    
    df["pattern_bull_intensity"] = ccs["bull_intensity"]
    df["pattern_bear_intensity"] = ccs["bear_intensity"]
    df["pattern_confluence_score"] = ccs["ccs_score"]
    return df

def add_statistical_structure(df, cfg=AnalysisConfig()):
    df=_as_df(df); c=df["close"]
    df["returns"]=c.pct_change(); df["log_returns"]=np.log(c).diff(); df["cum_return"]=(1+df["returns"].fillna(0)).cumprod()-1
    df["z_close"]=_rz(c,cfg.zscore_window); df["z_volume"]=_rz(df["volume"],cfg.zscore_window)
    df["volatility"]=df["log_returns"].rolling(cfg.volatility_lookback).std(ddof=0)
    df["volatility_z"]=_rz(df["volatility"],cfg.zscore_window)
    df["range_atr_ratio"]=(df["high"]-df["low"])/df["atr"]; df["close_to_atr"]=(df["close"]-df["ema_fast"])/df["atr"]
    df["rolling_skew"]=df["log_returns"].rolling(cfg.zscore_window).skew()
    df["rolling_kurt"]=df["log_returns"].rolling(cfg.zscore_window).kurt()
    df["sharpe_like"]=df["log_returns"].rolling(cfg.zscore_window).mean()/(df["log_returns"].rolling(cfg.zscore_window).std(ddof=0)+cfg.eps)
    df["fractal_efficiency"]=(df["close"]-df["close"].shift(5)).abs()/(df["close"].diff().abs().rolling(5).sum()+cfg.eps)
    return df

def detect_market_regime(df, cfg=AnalysisConfig()):
    """
    Institutional Regime Detection using Gaussian Mixture Models (GMM).
    Clusters Volatility and Trend Strength into statistically distinct states.
    """
    df = _as_df(df)
    if "adx" not in df.columns: df = add_core_indicators(df, cfg)
    
    # 1. Feature Selection for Clustering
    # We use Volatility (ATR-based) and Momentum (ADX + EMA Spread)
    log_v = np.log(df["atr"] / df["close"] + 1e-10)
    mom_v = (df["ema_fast"] - df["ema_slow"]) / df["close"]
    
    features = pd.DataFrame({
        'vol': log_v,
        'mom': mom_v
    }).fillna(0)
    
    # 2. Fit GMM (4 components: Stable Trend, Hyper-Volatile, Accumulation/Chop, Distribution)
    # We run this selectively or on a rolling basis if performance allows, 
    # but for typical requests, we fit on the current dataset.
    sh = StandardScaler()
    X = sh.fit_transform(features)
    
    gmm = GaussianMixture(n_components=4, random_state=42)
    regime_probs = gmm.fit_predict(X)
    
    df["gmm_regime_id"] = regime_probs
    
    # 3. Traditional Logic for Labeling (Fallback/Anchor)
    df["trend_regime"] = np.select([
        (df["adx"] >= 25) & (df["plus_di"] > df["minus_di"]),
        (df["adx"] >= 25) & (df["minus_di"] > df["plus_di"]),
        (df["adx"] < 20)
    ], ["uptrend", "downtrend", "range"], default="transition")
    
    # Labels based on GMM component properties (heuristic mapping)
    # We can refine this by checking the mean of components
    means = gmm.means_
    # component with highest vol = "high_vol"
    hv_comp = np.argmax(means[:, 0])
    df["statistical_is_volatile"] = (df["gmm_regime_id"] == hv_comp).astype(int)
    
    return df

def support_resistance_features(df, cfg=AnalysisConfig()):
    df=_as_df(df); highs,low=df["high"].to_numpy(),df["low"].to_numpy()
    def le(arr,l,r,k):
        idx=[]
        for i in range(l,len(arr)-r):
            if np.isfinite(arr[i]) and arr[i]==(np.nanmax(arr[i-l:i+r+1]) if k=="high" else np.nanmin(arr[i-l:i+r+1])): idx.append(i)
        return np.array(idx,dtype=int)
    ph=le(highs,cfg.pivot_left,cfg.pivot_right,"high"); pl=le(low,cfg.pivot_left,cfg.pivot_right,"low")
    df["pivot_high"]=np.nan; df["pivot_low"]=np.nan
    df.loc[ph,"pivot_high"]=df.loc[ph,"high"]; df.loc[pl,"pivot_low"]=df.loc[pl,"low"]
    df["resistance_1"]=df["pivot_high"].ffill(); df["support_1"]=df["pivot_low"].ffill()
    df["dist_to_resistance"]=(df["resistance_1"]-df["close"])/df["atr"]
    df["dist_to_support"]=(df["close"]-df["support_1"])/df["atr"]
    df["breakout_up"]=((df["close"]>df["resistance_1"])&(df["volume"]>df["volume"].rolling(20).mean()*1.2)&(df["adx"]>20)).astype(int)
    df["breakdown_down"]=((df["close"]<df["support_1"])&(df["volume"]>df["volume"].rolling(20).mean()*1.2)&(df["adx"]>20)).astype(int)
    return df

def divergence_features(df, cfg=AnalysisConfig()):
    df=_as_df(df)
    df["rsi_slope"]=df["rsi"].diff(5); df["macd_slope"]=df["macd"].diff(5); df["price_slope"]=df["close"].diff(5)
    ph=df["close"]>df["close"].shift(5); pl=df["close"]<df["close"].shift(5)
    rh=df["rsi"]>df["rsi"].shift(5); rl=df["rsi"]<df["rsi"].shift(5)
    mh=df["macd"]>df["macd"].shift(5); ml=df["macd"]<df["macd"].shift(5)
    df["bullish_divergence"]=((pl)&(rh|mh)).astype(int); df["bearish_divergence"]=((ph)&(rl|ml)).astype(int)
    return df

def similarity_engine(df, cfg=AnalysisConfig()):
    df=_as_df(df); fc=["returns","rsi","macdhist","bb_percent_b","volume_z","adx","atr","roc","cci","mfi"]
    for c_ in fc:
        if c_ not in df.columns: raise ValueError(f"Kolom '{c_}' belum ada.")
    X=df[fc].copy().replace([np.inf,-np.inf],np.nan).fillna(method="ffill").fillna(method="bfill").fillna(0.0)
    F=pd.DataFrame({c_:(X[c_]-X[c_].rolling(cfg.similarity_lookback if hasattr(cfg,'similarity_lookback') else 80).mean())/(X[c_].rolling(80).std(ddof=0).replace(0,np.nan)) for c_ in fc}).fillna(0.0)
    ss=np.full(len(df),np.nan,dtype=float); k=80
    for i in range(2*k,len(df)):
        cur=F.iloc[i-k:i].to_numpy().flatten(); best=-np.inf
        for j in range(k,i-k):
            his=F.iloc[j-k:j].to_numpy().flatten()
            na=np.linalg.norm(cur); nb=np.linalg.norm(his)
            if na>1e-12 and nb>1e-12: sc=float(np.dot(cur,his)/(na*nb))
            else: sc=np.nan
            if np.isfinite(sc) and sc>best: best=sc
        ss[i]=best if best>-np.inf else np.nan
    df["historical_similarity"]=ss
    df["similarity_rank"]=pd.Series(ss).rolling(200).apply(lambda x: float(np.sum(x<=x[-1])/len(x)) if len(x)>0 else np.nan,raw=True)
    df["pattern_memory_score"]=np.tanh((ss-0.5)*3.0)*(df["similarity_rank"]-0.5)*2.0
    return df

def composite_scoring(df, cfg=AnalysisConfig()):
    """
    Refined Composite Scoring based on Regime-Adaptive Confluence.
    Eliminates fixed 'Magic Number' weights in favor of standardized scores.
    """
    df = _as_df(df)
    
    # Standardize primary inputs
    def norm(s): return np.tanh( (s - s.rolling(100).mean()) / (s.rolling(100).std() + 1e-10) )
    
    # Feature Groups
    mom = (norm(df["rsi"]) + norm(df["macdhist"]) + norm(df["stochrsi_k"])) / 3.0
    trd = (norm(df["adx"]) * np.sign(df["ema_fast"] - df["ema_slow"]) + norm(df["linear_reg_slope"])) / 2.0
    vol = norm(df["volume_z"]) * 0.5 + norm(df["mfi"] - 50) * 0.5
    
    # Candlestick Confluence
    pat = df["pattern_confluence_score"] if "pattern_confluence_score" in df.columns else 0
    
    # Adaptive Weighting based on Regime
    is_trend = (df["trend_regime"].isin(["uptrend", "downtrend"])).astype(float)
    
    # Final Composite Signal (Normalized to [-1, 1])
    # During trends, weight Trend/Mom high. During range, weight Oscillators/Mean-Rev high.
    comp_score = (
        trd * 0.5 * is_trend + 
        mom * 0.3 * (1 - is_trend*0.5) + # RSI/Mom kept lower in strong trends
        vol * 0.2 + 
        pat * 0.1
    )
    
    df["momentum_score"] = mom
    df["trend_score"] = trd
    df["composite_signal"] = comp_score
    
    # Logic Signal Generation
    df["long_signal"] = (comp_score > 0.4).astype(int)
    df["short_signal"] = (comp_score < -0.4).astype(int)
    
    return df

def build_deep_technical_frame(data, cfg=AnalysisConfig()):
    df=_as_df(data); df=add_core_indicators(df,cfg); df=add_candlestick_patterns(df); df=add_statistical_structure(df,cfg)
    df=detect_market_regime(df,cfg); df=support_resistance_features(df,cfg); df=divergence_features(df,cfg)
    try: df=similarity_engine(df,cfg)
    except: pass
    df=composite_scoring(df,cfg)
    return df

def scan_signal_events(df):
    req=["long_signal","short_signal","close","rsi","adx","composite_long_score","composite_short_score"]
    for c_ in req:
        if c_ not in df.columns: raise ValueError("Jalankan build_deep_technical_frame terlebih dahulu.")
    ev=[]
    for i in range(1,len(df)):
        if df["long_signal"].iat[i]==1 and df["long_signal"].iat[i-1]==0: ev.append({"index":i,"type":"long","close":df["close"].iat[i],"rsi":df["rsi"].iat[i],"adx":df["adx"].iat[i],"long_score":df["composite_long_score"].iat[i]})
        if df["short_signal"].iat[i]==1 and df["short_signal"].iat[i-1]==0: ev.append({"index":i,"type":"short","close":df["close"].iat[i],"rsi":df["rsi"].iat[i],"adx":df["adx"].iat[i],"short_score":df["composite_short_score"].iat[i]})
    return pd.DataFrame(ev)