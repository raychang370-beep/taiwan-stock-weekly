"""
台股技術分析模組
- 抓取股價資料
- 計算 KD 線（隨機指標）
- 辨識圖表型態（買入/賣出/等待）
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

    # ── KD 強化訊號 ──────────────────────────────
    if gold_cross and k_oversold and pattern_cat in ("買入", "等待"):
        pattern_cat = "必買"
        confidence  = min(confidence + 15, 100)
    elif death_cross and k_overbought and pattern_cat in ("賣出", "等待"):
        pattern_cat = "必賣"
        confidence  = min(confidence + 15, 100)

    return {
        "pattern":    pattern_name,
        "category":   pattern_cat,
        "confidence": confidence,
        "k_value":    round(float(k_now), 1),
        "d_value":    round(float(d_now), 1),
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
            "k_value":  50, "d_value": 50,
            "price":    0, "change_pct": 0,
            "kd_history": {"dates": [], "k": [], "d": [], "close": []},
        }

    df = calculate_kd(df,
                      k_period=config.get('kd_period', 9),
                      d_period=config.get('kd_signal_period', 3))
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
        "k_value":    analysis['k_value'],
        "d_value":    analysis['d_value'],
        "gold_cross": analysis.get('gold_cross', False),
        "death_cross":analysis.get('death_cross', False),
        "ma5":        analysis.get('ma5', 0),
        "ma10":       analysis.get('ma10', 0),
        "ma20":       analysis.get('ma20', 0),
        "kd_history": kd_hist,
        "error":      None,
    }
