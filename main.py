"""
台股週報主程式
執行方式: uv run main.py [--open]
"""
import json
import os
import sys
import argparse

def load_config(path: str = "config.json") -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def main():
    parser = argparse.ArgumentParser(description='台股技術分析週報產生器')
    parser.add_argument('--open', action='store_true', help='產生後自動開啟瀏覽器')
    parser.add_argument('--config', default='config.json', help='設定檔路徑')
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print("=" * 50)
    print("  [**] Taiwan Stock Weekly Report Generator")
    print("=" * 50)

    config = load_config(args.config)

    # 1. 分析各公司股票
    from stock_analyzer import analyze_company
    print("\n[1/3] 分析股票技術指標 ...")
    results = []
    for company in config['companies']:
        r = analyze_company(company, config)
        results.append(r)
        cat = r.get('category', '等待')
        k   = r.get('k_value', 0)
        d   = r.get('d_value', 0)
        print(f"    ✓ {r['name']:8s} | {r['pattern']:12s} | {cat:4s} | K={k:.1f} D={d:.1f}")

    # 2. 抓取財經新聞
    print("\n[2/3] 抓取財經新聞 ...")
    from news_fetcher import fetch_all_news
    news = fetch_all_news(config['companies'])
    print(f"    ✓ 市場新聞: {len(news['market'])} 則")

    # 3. 產生 HTML 報告
    print("\n[3/3] 產生 HTML 週報 ...")
    from report_generator import generate_report
    output_path = generate_report(results, news, config)
    abs_path = os.path.abspath(output_path)
    print(f"    ✓ 週報已儲存: {abs_path}")

    # 顯示摘要
    print("\n" + "=" * 50)
    print("  📋 本週分析摘要")
    print("=" * 50)
    for cat in ['必買', '買入', '等待', '賣出', '必賣']:
        stocks = [r for r in results if r.get('category') == cat]
        if stocks:
            names = ', '.join(r['name'] for r in stocks)
            print(f"  {cat:4s}: {names}")
    print("=" * 50)

    # 自動開啟瀏覽器
    if args.open:
        import webbrowser
        webbrowser.open(f"file:///{abs_path.replace(os.sep, '/')}")
        print("\n  🌐 已在瀏覽器開啟週報")

    return abs_path

if __name__ == '__main__':
    main()
