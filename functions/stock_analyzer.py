"""
台股技術分析模組（多指標綜合評分版）
- 抓取股價資料
- KD（含鈍化與背離偵測）+ MACD + RSI + 布林通道 + 量能
- 各指標加權投票 → 綜合評分 0~100 → 必買/買入/等待/賣出/必賣
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def fetch_stock_data(symbol: str, days: int = 120) -> pd.DataFrame:
    """抓取股票歷史資料"""
    end = datetime.today()
    start = end - timedelta(days=days)
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
        if df.empty:
            return pd.DataFrame()
        # 展平多層欄位
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        return df
    except Exception as e:
        print(f"  [警告] 無法取得 {symbol} 資料: {e}")
        return pd.DataFrame()

def calculate_kd(df: pd.DataFrame, k_period: int = 9, d_period: int = 3) -> pd.DataFrame:
    """計算 KD 隨機指標（台灣版 RSV 法）"""
    if df.empty or len(df) < k_period:
        return df

    low_min  = df['low'].rolling(window=k_period).min()
    high_max = df['high'].rolling(window=k_period).max()
    rsv = ((df['close'] - low_min) / (high_max - low_min).replace(0, np.nan)) * 100

    k = pd.Series(index=df.index, dtype=float)
    d = pd.Series(index=df.index, dtype=float)
    k.iloc[0] = 50.0
    d.iloc[0] = 50.0
    for i in range(1, len(rsv)):
        rv = rsv.iloc[i] if not pd.isna(rsv.iloc[i]) else 50
        k.iloc[i] = k.iloc[i-1] * (2/3) + rv * (1/3)
        d.iloc[i] = d.iloc[i-1] * (2/3) + k.iloc[i] * (1/3)

    df = df.copy()
    df['K'] = k
    df['D'] = d
    df['RSV'] = rsv
    return df

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """計算 MACD（DIF、MACD訊號線、柱狀體）"""
    if df.empty or len(df) < slow + signal:
        return df
    df = df.copy()
    ema_fast = df['close'].ewm(span=fast, adjust=False).mean()
    ema_slow = df['close'].ewm(span=slow, adjust=False).mean()
    df['DIF']  = ema_fast - ema_slow
    df['MACD'] = df['DIF'].ewm(span=signal, adjust=False).mean()
    df['HIST'] = df['DIF'] - df['MACD']
    return df

def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """計算 RSI（Wilder 平滑法）"""
    if df.empty or len(df) < period + 1:
        return df
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    return df

def calculate_bollinger(df: pd.DataFrame, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """計算布林通道（中軌 = MA20，上下軌 = ±2 標準差）"""
    if df.empty or len(df) < period:
        return df
    df = df.copy()
    mid = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    df['BB_MID']   = mid
    df['BB_UPPER'] = mid + num_std * std
    df['BB_LOWER'] = mid - num_std * std
    return df

def detect_kd_divergence(df: pd.DataFrame, window: int = 30) -> str:
    """
    偵測 KD 背離：
    - 低檔背離：價格創新低但 K 值沒創新低 → 可能反轉向上
    - 高檔背離：價格創新高但 K 值沒創新高 → 可能反轉向下
    回傳 'bullish' / 'bearish' / ''
    """
    if 'K' not in df.columns or len(df) < window:
        return ''
    recent = df.tail(window)
    closes = recent['close'].values
    ks     = recent['K'].values
    half = window // 2
    # 前半段 vs 後半段的極值比較
    if np.nanmin(closes[half:]) < np.nanmin(closes[:half]) and \
       np.nanmin(ks[half:]) > np.nanmin(ks[:half]) + 3:
        return 'bullish'
    if np.nanmax(closes[half:]) > np.nanmax(closes[:half]) and \
       np.nanmax(ks[half:]) < np.nanmax(ks[:half]) - 3:
        return 'bearish'
    return ''

def detect_kd_stagnation(df: pd.DataFrame, days: int = 3) -> str:
    """
    偵測 KD 鈍化（連續 days 天 K>80 或 K<20）
    高檔鈍化 = 強勢股特徵（不宜直接視為賣出訊號）
    回傳 'high' / 'low' / ''
    """
    if 'K' not in df.columns or len(df) < days:
        return ''
    k_recent = df['K'].tail(days).values
    if np.all(k_recent > 80):
        return 'high'
    if np.all(k_recent < 20):
        return 'low'
    return ''

def detect_pattern(df: pd.DataFrame) -> dict:
    """
    簡化型態辨識，回傳型態名稱與分類
    分類：必買/買入/等待/賣出/必賣
    """
    if df.empty or len(df) < 20:
        return {"pattern": "資料不足", "category": "等待", "confidence": 0}

    closes = df['close'].dropna().values
    k_vals  = df['K'].dropna().values
    d_vals  = df['D'].dropna().values

    if len(k_vals) < 3:
        return {"pattern": "計算中", "category": "等待", "confidence": 0}

    k_now, k_prev = k_vals[-1], k_vals[-2]
    d_now, d_prev = d_vals[-1], d_vals[-2]
    price_now = closes[-1]

    # ── KD 交叉判斷 ──────────────────────────────
    gold_cross  = (k_prev < d_prev) and (k_now > d_now)   # 黃金交叉
    death_cross = (k_prev > d_prev) and (k_now < d_now)   # 死亡交叉
    k_oversold  = k_now < 20   # 超賣
    k_overbought= k_now > 80   # 超買

    # ── 簡化價格型態辨識 ────────────────────────
    window = min(30, len(closes))
    recent = closes[-window:]
    ma5  = np.mean(closes[-5:])  if len(closes) >= 5  else price_now
    ma10 = np.mean(closes[-10:]) if len(closes) >= 10 else price_now
    ma20 = np.mean(closes[-20:]) if len(closes) >= 20 else price_now

    # 找區域極值（高低點）
    peaks  = []
    troughs= []
    for i in range(1, len(recent)-1):
        if recent[i] > recent[i-1] and recent[i] > recent[i+1]:
            peaks.append((i, recent[i]))
        if recent[i] < recent[i-1] and recent[i] < recent[i+1]:
            troughs.append((i, recent[i]))

    pattern_name  = "整理中"
    pattern_cat   = "等待"
    confidence    = 50

    # ── W底（雙底）判斷 ─────────────────────────
    if len(troughs) >= 2:
        t1, t2 = troughs[-2][1], troughs[-1][1]
        if abs(t1 - t2) / max(t1, 1) < 0.03 and price_now > max(t1, t2) * 1.01:
            pattern_name = "W底（雙底）"
            pattern_cat  = "必買" if (gold_cross or k_oversold) else "買入"
            confidence   = 80

    # ── M頭（雙頂）判斷 ─────────────────────────
    elif len(peaks) >= 2:
        p1, p2 = peaks[-2][1], peaks[-1][1]
        if abs(p1 - p2) / max(p1, 1) < 0.03 and price_now < min(p1, p2) * 0.99:
            pattern_name = "M頭（雙頂）"
            pattern_cat  = "必賣" if (death_cross or k_overbought) else "賣出"
            confidence   = 80

    # ── 頭肩底判斷 ───────────────────────────────
    elif len(troughs) >= 3:
        t1, t2, t3 = troughs[-3][1], troughs[-2][1], troughs[-1][1]
        if t2 < t1 and t2 < t3 and abs(t1 - t3) / max(t1, 1) < 0.05:
            pattern_name = "頭肩底"
            pattern_cat  = "必買" if gold_cross else "買入"
            confidence   = 85

    # ── 三重頂判斷 ───────────────────────────────
    elif len(peaks) >= 3:
        p1, p2, p3 = peaks[-3][1], peaks[-2][1], peaks[-1][1]
        if abs(p1 - p2) / max(p1, 1) < 0.04 and abs(p2 - p3) / max(p2, 1) < 0.04:
            pattern_name = "三重頂"
            pattern_cat  = "必賣" if death_cross else "賣出"
            confidence   = 75

    # ── 依均線趨勢補充判斷 ───────────────────────
    else:
        uptrend   = ma5 > ma10 > ma20
        downtrend = ma5 < ma10 < ma20

        if uptrend:
            if gold_cross and k_oversold:
                pattern_name, pattern_cat, confidence = "上升旗形", "必買", 80
            elif gold_cross:
                pattern_name, pattern_cat, confidence = "上升趨勢", "買入", 65
            else:
                pattern_name, pattern_cat, confidence = "上升通道", "等待", 50
        elif downtrend:
            if death_cross and k_overbought:
                pattern_name, pattern_cat, confidence = "下跌旗形", "必賣", 80
            elif death_cross:
                pattern_name, pattern_cat, confidence = "下跌趨勢", "賣出", 65
            else:
                pattern_name, pattern_cat, confidence = "箱型盤整", "等待", 50
        else:
            pattern_name, pattern_cat, confidence = "三角收斂", "等待", 50

    # ═══════════════════════════════════════════════
    #  多指標綜合評分（各指標投票 -3 ~ +3，加總後換算 0~100）
    # ═══════════════════════════════════════════════
    votes = 0.0
    signals = []   # 給報告顯示的訊號說明

    stagnation = detect_kd_stagnation(df)
    divergence = detect_kd_divergence(df)

    # ── 1. KD 訊號 ──────────────────────────────
    if gold_cross:
        if k_oversold or k_now < 30:
            votes += 3; signals.append("🟡 KD低檔黃金交叉（強力買訊）")
        else:
            votes += 2; signals.append("🟡 KD黃金交叉")
    elif death_cross:
        if k_overbought or k_now > 70:
            votes -= 3; signals.append("⚫ KD高檔死亡交叉（強力賣訊）")
        else:
            votes -= 2; signals.append("⚫ KD死亡交叉")

    # KD 鈍化：高檔鈍化是強勢股特徵，視為趨勢延續而非賣訊
    if stagnation == 'high':
        votes += 1; signals.append("🔥 KD高檔鈍化（強勢趨勢延續，留意回檔）")
    elif stagnation == 'low':
        votes -= 1; signals.append("🧊 KD低檔鈍化（弱勢趨勢，勿急接刀）")

    # KD 背離：反轉領先訊號
    if divergence == 'bullish':
        votes += 2; signals.append("🎯 KD低檔背離（價創低但KD墊高，反轉前兆）")
    elif divergence == 'bearish':
        votes -= 2; signals.append("⚠️ KD高檔背離（價創高但KD走低，回檔前兆）")

    # ── 2. MACD 訊號（趨勢動能確認）─────────────
    macd_dif = macd_sig = macd_hist = None
    if 'HIST' in df.columns:
        hist = df['HIST'].dropna().values
        dif  = df['DIF'].dropna().values
        sig  = df['MACD'].dropna().values
        if len(hist) >= 2:
            macd_dif, macd_sig, macd_hist = float(dif[-1]), float(sig[-1]), float(hist[-1])
            if hist[-2] <= 0 < hist[-1]:
                votes += 2; signals.append("📈 MACD柱狀體翻紅（動能轉強）")
            elif hist[-2] >= 0 > hist[-1]:
                votes -= 2; signals.append("📉 MACD柱狀體翻綠（動能轉弱）")
            elif hist[-1] > 0 and hist[-1] > hist[-2]:
                votes += 1; signals.append("📈 MACD紅柱放大（多方動能增強）")
            elif hist[-1] < 0 and hist[-1] < hist[-2]:
                votes -= 1; signals.append("📉 MACD綠柱放大（空方動能增強）")

    # ── 3. RSI 訊號（超買超賣過濾）───────────────
    rsi_now = None
    if 'RSI' in df.columns:
        rsi_vals = df['RSI'].dropna().values
        if len(rsi_vals) >= 2:
            rsi_now = float(rsi_vals[-1])
            if rsi_now < 30:
                votes += 1.5; signals.append(f"💚 RSI超賣（{rsi_now:.0f}，跌深反彈機會）")
            elif rsi_now > 70:
                votes -= 1.5; signals.append(f"🔻 RSI超買（{rsi_now:.0f}，追高風險）")
            elif rsi_now > 50 and rsi_vals[-1] > rsi_vals[-2]:
                votes += 0.5
            elif rsi_now < 50 and rsi_vals[-1] < rsi_vals[-2]:
                votes -= 0.5

    # ── 4. 布林通道（波段位置）──────────────────
    bb_pos = None
    if 'BB_UPPER' in df.columns:
        bu = df['BB_UPPER'].dropna()
        bl = df['BB_LOWER'].dropna()
        if len(bu) and len(bl):
            upper, lower = float(bu.iloc[-1]), float(bl.iloc[-1])
            if upper > lower:
                bb_pos = (price_now - lower) / (upper - lower)  # %b：0=下軌 1=上軌
                if bb_pos < 0.05:
                    votes += 1.5; signals.append("💧 觸及布林下軌（波段低點區）")
                elif bb_pos > 0.95:
                    votes -= 1.5; signals.append("🎈 觸及布林上軌（波段高點區）")

    # ── 5. 量能確認（價量配合才是真訊號）─────────
    vol_ratio = None
    if 'volume' in df.columns:
        vols = df['volume'].dropna().values
        if len(vols) >= 20 and np.mean(vols[-20:]) > 0:
            vol_ratio = float(np.mean(vols[-5:]) / np.mean(vols[-20:]))
            price_up_5d = price_now > closes[-5] if len(closes) >= 5 else False
            if vol_ratio > 1.3 and price_up_5d:
                votes += 1.5; signals.append("🔊 價漲量增（買盤進場確認）")
            elif vol_ratio > 1.3 and not price_up_5d:
                votes -= 1; signals.append("📢 價跌量增（賣壓沉重）")
            elif vol_ratio < 0.7 and price_up_5d:
                votes -= 0.5; signals.append("🔇 價漲量縮（上攻力道不足）")

    # ── 6. 均線趨勢排列 ─────────────────────────
    if ma5 > ma10 > ma20:
        votes += 1.5; signals.append("📊 均線多頭排列")
    elif ma5 < ma10 < ma20:
        votes -= 1.5; signals.append("📊 均線空頭排列")

    # ── 7. 型態加分 ─────────────────────────────
    bull_patterns = ("W底（雙底）", "頭肩底")
    bear_patterns = ("M頭（雙頂）", "三重頂")
    if pattern_name in bull_patterns:
        votes += 2; signals.append(f"📐 {pattern_name}型態成形")
    elif pattern_name in bear_patterns:
        votes -= 2; signals.append(f"📐 {pattern_name}型態成形")

    # ── 綜合評分與分類 ──────────────────────────
    score = int(np.clip(50 + votes * 4.5, 0, 100))
    if score >= 75:
        pattern_cat = "必買"
    elif score >= 60:
        pattern_cat = "買入"
    elif score > 40:
        pattern_cat = "等待"
    elif score > 25:
        pattern_cat = "賣出"
    else:
        pattern_cat = "必賣"

    # 信心度 = 訊號一致性（同方向訊號越多越有信心）
    confidence = int(np.clip(50 + abs(votes) * 5 + len(signals) * 3, 40, 98))
    if not signals:
        signals.append("😴 無明顯訊號，觀望為宜")

    return {
        "pattern":    pattern_name,
        "category":   pattern_cat,
        "confidence": confidence,
        "score":      score,
        "signals":    signals,
        "k_value":    round(float(k_now), 1),
        "d_value":    round(float(d_now), 1),
        "rsi":        round(rsi_now, 1) if rsi_now is not None else None,
        "macd_dif":   round(macd_dif, 2) if macd_dif is not None else None,
        "macd_hist":  round(macd_hist, 3) if macd_hist is not None else None,
        "bb_pos":     round(bb_pos * 100, 0) if bb_pos is not None else None,
        "vol_ratio":  round(vol_ratio, 2) if vol_ratio is not None else None,
        "gold_cross": gold_cross,
        "death_cross": death_cross,
        "ma5":  round(float(ma5), 2),
        "ma10": round(float(ma10), 2),
        "ma20": round(float(ma20), 2),
    }

def get_kd_history(df: pd.DataFrame, display_days: int = 60) -> dict:
    """
    取得近期 K 棒 + KD + 各期均線資料（用於圖表繪製）
    - display_days: 顯示最近幾根 K 棒（預設60）
    - 均線計算需要更長歷史，但只顯示近 display_days 筆
    """
    if df.empty:
        return {"dates": [], "k": [], "d": [], "close": [],
                "high": [], "low": [], "open": [], "volume": [],
                "ma5": [], "ma10": [], "ma20": [],
                "ma60": [], "ma120": [], "ma240": []}

    def _ma(series, n):
        ma = series.rolling(window=n).mean()
        return [round(float(v), 2) if not pd.isna(v) else None for v in ma]

    close = df['close']
    recent = df.tail(display_days)

    # 計算均線（用全部資料，再取尾段）
    ma5   = _ma(close, 5)[-display_days:]
    ma10  = _ma(close, 10)[-display_days:]
    ma20  = _ma(close, 20)[-display_days:]
    ma60  = _ma(close, 60)[-display_days:]
    ma120 = _ma(close, 120)[-display_days:]
    ma240 = _ma(close, 240)[-display_days:]

    def _safe(series, rnd=2):
        return [round(float(v), rnd) if not pd.isna(v) else None for v in series]

    return {
        "dates":  [str(d.date()) for d in recent.index],
        "k":      _safe(recent['K'], 1),
        "d":      _safe(recent['D'], 1),
        "close":  _safe(recent['close']),
        "high":   _safe(recent['high']),
        "low":    _safe(recent['low']),
        "open":   _safe(recent['open']),
        "volume": [int(v) if not pd.isna(v) else None for v in recent['volume']],
        "ma5":    ma5,
        "ma10":   ma10,
        "ma20":   ma20,
        "ma60":   ma60,
        "ma120":  ma120,
        "ma240":  ma240,
    }

def analyze_company(company: dict, config: dict) -> dict:
    """完整分析單一公司"""
    print(f"  分析 {company['name']} ({company['symbol']}) ...")
    df = fetch_stock_data(company['symbol'], days=config.get('lookback_days', 120))
    if df.empty:
        return {
            "name":     company['name'],
            "symbol":   company['symbol'],
            "industry": company['industry'],
            "error":    "無法取得資料",
            "category": "等待",
            "pattern":  "N/A",
            "confidence": 0,
            "score":    50, "signals": [],
            "k_value":  50, "d_value": 50,
            "rsi": None, "macd_dif": None, "macd_hist": None,
            "bb_pos": None, "vol_ratio": None,
            "price":    0, "change_pct": 0,
            "kd_history": {"dates": [], "k": [], "d": [], "close": []},
        }

    df = calculate_kd(df,
                      k_period=config.get('kd_period', 9),
                      d_period=config.get('kd_signal_period', 3))
    df = calculate_macd(df)
    df = calculate_rsi(df)
    df = calculate_bollinger(df)
    analysis = detect_pattern(df)
    kd_hist  = get_kd_history(df, display_days=config.get('chart_display_days', 60))

    # 計算漲跌幅
    close_vals = df['close'].dropna().values
    price      = round(float(close_vals[-1]), 2) if len(close_vals) >= 1 else 0
    change_pct = round(float((close_vals[-1] - close_vals[-2]) / close_vals[-2] * 100), 2) \
                 if len(close_vals) >= 2 else 0

    return {
        "name":       company['name'],
        "symbol":     company['symbol'],
        "industry":   company['industry'],
        "price":      price,
        "change_pct": change_pct,
        "category":   analysis['category'],
        "pattern":    analysis['pattern'],
        "confidence": analysis['confidence'],
        "score":      analysis.get('score', 50),
        "signals":    analysis.get('signals', []),
        "k_value":    analysis['k_value'],
        "d_value":    analysis['d_value'],
        "rsi":        analysis.get('rsi'),
        "macd_dif":   analysis.get('macd_dif'),
        "macd_hist":  analysis.get('macd_hist'),
        "bb_pos":     analysis.get('bb_pos'),
        "vol_ratio":  analysis.get('vol_ratio'),
        "gold_cross": analysis.get('gold_cross', False),
        "death_cross":analysis.get('death_cross', False),
        "ma5":        analysis.get('ma5', 0),
        "ma10":       analysis.get('ma10', 0),
        "ma20":       analysis.get('ma20', 0),
        "kd_history": kd_hist,
        "error":      None,
    }
