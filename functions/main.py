"""
台股週報 Firebase Cloud Functions
------------------------------------------------------
架構：GitHub Pages（前端）+ Firebase（後端）+ Firestore（資料庫）

run_analysis     POST /api/run         → 手動觸發分析，結果存 Firestore
api_config       GET  /api/config      → 讀取自選股設定（健康檢查用）
api_add_stock    POST /api/add-stock   → 新增自選股
api_remove_stock POST /api/remove-stock→ 移除自選股
weekly_analysis  [排程] 每週一 08:00 台北時間 → 自動分析

前端（GitHub Pages docs/index.html）用 Firebase JS SDK 直接讀 Firestore reports/latest
"""
import json
import os
import traceback
from datetime import datetime, timezone

from firebase_functions import https_fn, scheduler_fn, options
from firebase_admin import initialize_app, firestore as _fs

initialize_app()

BASE = os.path.dirname(__file__)
CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


# ── 共用輔助函式 ────────────────────────────────────────────────────────────

def _db():
    return _fs.client()


def _get_config() -> dict:
    """從 Firestore 讀取設定，若無則使用 default_config.json"""
    doc = _db().collection("config").document("settings").get()
    if doc.exists:
        return doc.to_dict()
    cfg_path = os.path.join(BASE, "default_config.json")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(config: dict) -> None:
    _db().collection("config").document("settings").set(config)


def _run_analysis_and_save() -> list:
    """執行完整股票分析並將報告 HTML 存入 Firestore"""
    print("=== 開始台股週報分析 ===")
    config = _get_config()

    # ── 1. 分析各股 ──────────────────────────────────
    from stock_analyzer import analyze_company
    results = []
    for company in config.get("companies", []):
        r = analyze_company(company, config)
        results.append(r)
        print(
            f"  ✓ {r['name']:8s} | {r.get('pattern','?'):12s} "
            f"| {r.get('category','?'):4s} "
            f"| K={r.get('k_value',0):.1f} D={r.get('d_value',0):.1f}"
        )

    # ── 2. 抓取新聞 ──────────────────────────────────
    print("  抓取財經新聞 ...")
    from news_fetcher import fetch_all_news
    news = fetch_all_news(config.get("companies", []))
    print(f"  ✓ 市場新聞: {len(news.get('market', []))} 則")

    # ── 3. 產生 HTML ─────────────────────────────────
    print("  產生 HTML 報告 ...")
    from report_generator import generate_report_html
    html = generate_report_html(results, news, config)

    html_bytes = html.encode("utf-8")
    print(f"  ✓ HTML 大小: {len(html_bytes)/1024:.1f} KB")

    # ── 4. 存入 Firestore ────────────────────────────
    summary = {r["name"]: r.get("category", "等待") for r in results}
    _db().collection("reports").document("latest").set({
        "html": html,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sizeBytes": len(html_bytes),
        "summary": summary,
    })
    print("=== 分析完成，已存入 Firestore ===")

    return results


# ── HTTP Functions ─────────────────────────────────────────────────────────


@https_fn.on_request(
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    region="asia-east1",
)
def run_analysis(req: https_fn.Request) -> https_fn.Response:
    """手動觸發分析（POST /api/run）"""
    headers = {**CORS, "Content-Type": "application/json"}

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204, headers=headers)
    if req.method != "POST":
        return https_fn.Response(
            json.dumps({"ok": False, "error": "Method Not Allowed"}),
            status=405, headers=headers
        )
    try:
        results = _run_analysis_and_save()
        summary = {r["name"]: r.get("category", "等待") for r in results}
        return https_fn.Response(
            json.dumps({"ok": True, "summary": summary}, ensure_ascii=False),
            headers=headers,
        )
    except Exception as e:
        print(traceback.format_exc())
        return https_fn.Response(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            status=500, headers=headers,
        )


@https_fn.on_request(region="asia-east1")
def api_config(req: https_fn.Request) -> https_fn.Response:
    """取得自選股設定（GET /api/config）"""
    headers = {**CORS, "Content-Type": "application/json"}
    try:
        config = _get_config()
        return https_fn.Response(
            json.dumps({
                "companies": config.get("companies", []),
                "industries": config.get("industries", []),
                "report_title": config.get("report_title", "台股技術分析週報"),
            }, ensure_ascii=False),
            headers=headers,
        )
    except Exception as e:
        return https_fn.Response(
            json.dumps({"error": str(e)}, ensure_ascii=False),
            status=500, headers=headers,
        )


@https_fn.on_request(region="asia-east1")
def api_add_stock(req: https_fn.Request) -> https_fn.Response:
    """新增自選股（POST /api/add-stock）"""
    headers = {**CORS, "Content-Type": "application/json"}

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204, headers=headers)
    if req.method != "POST":
        return https_fn.Response(
            json.dumps({"ok": False, "error": "Method Not Allowed"}),
            status=405, headers=headers,
        )
    try:
        data = req.get_json(silent=True) or {}
        symbol = data.get("symbol", "").strip()
        name   = data.get("name",   "").strip()
        industry = data.get("industry", "其他").strip()

        if not symbol:
            return https_fn.Response(
                json.dumps({"ok": False, "error": "請提供 symbol（股票代號）"}),
                status=400, headers=headers,
            )

        # 若未提供名稱，自動從 yfinance 查詢
        if not name:
            try:
                import yfinance as yf
                info = yf.Ticker(symbol).info
                name = (info.get("shortName") or info.get("longName") or
                        symbol.replace(".TW", "").replace(".TWO", ""))
                for suffix in [" Inc.", " Co., Ltd.", " Corp.", " Co.", " Ltd."]:
                    name = name.replace(suffix, "")
                name = name.strip() or symbol.replace(".TW", "")
            except Exception:
                name = symbol.replace(".TW", "").replace(".TWO", "")

        config = _get_config()
        companies = config.get("companies", [])

        if any(c["symbol"] == symbol for c in companies):
            return https_fn.Response(
                json.dumps({"ok": False, "error": f"{symbol} 已在清單中"}),
                status=409, headers=headers,
            )

        companies.append({"name": name, "symbol": symbol, "industry": industry})
        config["companies"] = companies
        _save_config(config)

        return https_fn.Response(
            json.dumps({"ok": True, "message": f"已加入 {name}（{symbol}）"}, ensure_ascii=False),
            headers=headers,
        )
    except Exception as e:
        return https_fn.Response(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            status=500, headers=headers,
        )


@https_fn.on_request(region="asia-east1")
def api_remove_stock(req: https_fn.Request) -> https_fn.Response:
    """移除自選股（POST /api/remove-stock）"""
    headers = {**CORS, "Content-Type": "application/json"}

    if req.method == "OPTIONS":
        return https_fn.Response("", status=204, headers=headers)
    if req.method != "POST":
        return https_fn.Response(
            json.dumps({"ok": False, "error": "Method Not Allowed"}),
            status=405, headers=headers,
        )
    try:
        data = req.get_json(silent=True) or {}
        symbol = data.get("symbol", "").strip()

        if not symbol:
            return https_fn.Response(
                json.dumps({"ok": False, "error": "請提供 symbol"}),
                status=400, headers=headers,
            )

        config = _get_config()
        original = len(config.get("companies", []))
        config["companies"] = [
            c for c in config.get("companies", []) if c["symbol"] != symbol
        ]

        if len(config["companies"]) == original:
            return https_fn.Response(
                json.dumps({"ok": False, "error": f"{symbol} 不在清單中"}),
                status=404, headers=headers,
            )

        _save_config(config)
        return https_fn.Response(
            json.dumps({"ok": True, "message": f"已移除 {symbol}"}, ensure_ascii=False),
            headers=headers,
        )
    except Exception as e:
        return https_fn.Response(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
            status=500, headers=headers,
        )


# ── Scheduled Function ─────────────────────────────────────────────────────

@scheduler_fn.on_schedule(
    schedule="0 8 * * 1",   # 每週一 08:00（台北時間）
    timezone="Asia/Taipei",
    memory=options.MemoryOption.GB_1,
    timeout_sec=300,
    region="asia-east1",
)
def weekly_analysis(event: scheduler_fn.ScheduledEvent) -> None:
    """每週一台北時間 08:00 自動執行台股技術分析週報"""
    print(f"=== 定時任務觸發: {event.schedule_time} ===")
    _run_analysis_and_save()
