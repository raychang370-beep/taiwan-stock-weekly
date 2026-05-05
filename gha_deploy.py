"""
GitHub Actions 部署腳本
執行股票分析並將報告 HTML 存入 Firebase Firestore。
不需要 Firebase Cloud Functions，也不需要 Blaze 方案。

環境變數：
  FIREBASE_CREDENTIALS  Firebase 服務帳戶 JSON（GitHub Secret）
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# 讓 Python 能找到 functions/ 目錄裡的 report_generator
BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)                            # 專案根目錄（stock_analyzer, news_fetcher）
sys.path.insert(0, os.path.join(BASE, "functions")) # functions/ 子目錄（report_generator）

# ── 初始化 Firebase Admin SDK ────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore

def init_firebase():
    cred_json = os.environ.get("FIREBASE_CREDENTIALS")
    if not cred_json:
        print("[ERROR] 找不到環境變數 FIREBASE_CREDENTIALS")
        sys.exit(1)

    # 寫到暫存檔（firebase_admin 需要檔案路徑）
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                    delete=False, encoding="utf-8") as f:
        f.write(cred_json)
        tmp_path = f.name

    cred = credentials.Certificate(tmp_path)
    firebase_admin.initialize_app(cred)
    os.unlink(tmp_path)   # 立即刪除暫存檔
    return firestore.client()


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("=" * 52)
    print("  [GHA] 台股技術分析週報 — GitHub Actions 部署")
    print("=" * 52)

    # ── 1. 載入設定 ──────────────────────────────────────
    with open("config.json", encoding="utf-8") as f:
        config = json.load(f)

    # ── 2. 初始化 Firebase ───────────────────────────────
    print("\n[1/5] 連線 Firebase ...")
    db = init_firebase()
    print("  ✓ Firebase Admin SDK 已連線")

    # 若 Firestore 有較新的設定（透過 Firebase Console 修改的），優先使用
    cfg_doc = db.collection("config").document("settings").get()
    if cfg_doc.exists:
        config.update(cfg_doc.to_dict())
        print("  ✓ 已從 Firestore 讀取最新設定")

    # ── 3. 分析股票 ──────────────────────────────────────
    print("\n[2/5] 分析股票技術指標 ...")
    from stock_analyzer import analyze_company
    results = []
    for company in config["companies"]:
        r = analyze_company(company, config)
        results.append(r)
        print(f"  ✓ {r['name']:8s} | {r.get('pattern','?'):12s} "
              f"| {r.get('category','?'):4s} "
              f"| K={r.get('k_value',0):.1f} D={r.get('d_value',0):.1f}")

    # ── 4. 抓取新聞 ──────────────────────────────────────
    print("\n[3/5] 抓取財經新聞 ...")
    from news_fetcher import fetch_all_news
    news = fetch_all_news(config["companies"])
    print(f"  ✓ 市場新聞 {len(news.get('market', []))} 則")

    # ── 5. 產生 HTML ─────────────────────────────────────
    print("\n[4/5] 產生 HTML 報告 ...")
    from report_generator import generate_report_html
    html = generate_report_html(results, news, config)
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"  ✓ HTML 大小: {size_kb:.1f} KB")

    # ── 6. 儲存到 Firestore ──────────────────────────────
    print("\n[5/5] 上傳到 Firestore ...")
    summary = {r["name"]: r.get("category", "等待") for r in results}
    db.collection("reports").document("latest").set({
        "html":        html,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sizeBytes":   int(size_kb * 1024),
        "summary":     summary,
        "source":      "github-actions",
    })
    print("  ✓ 已上傳到 Firestore reports/latest")

    # ── 摘要 ────────────────────────────────────────────
    print("\n" + "=" * 52)
    print("  📋 本週分析摘要")
    print("=" * 52)
    for cat in ["必買", "買入", "等待", "賣出", "必賣"]:
        stocks = [r for r in results if r.get("category") == cat]
        if stocks:
            print(f"  {cat}: {', '.join(r['name'] for r in stocks)}")
    print("=" * 52)
    print("\n  🌐 報告網址: https://raychang370-beep.github.io/taiwan-stock-weekly/")
    password = os.environ.get("REPORT_PASSWORD", "(請查看 GitHub Secrets)")
    print(f"  🔑 密碼: {password}")


if __name__ == "__main__":
    main()

