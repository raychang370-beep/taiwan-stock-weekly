"""
新增自選股並立即重新分析
用法: uv run add_stock.py <代號> <名稱> [產業]
範例: uv run add_stock.py 2317 鴻海 電子零組件
      uv run add_stock.py 2330 台積電 半導體
      uv run add_stock.py 2454 聯發科 半導體
移除: uv run add_stock.py --remove 2317
列出: uv run add_stock.py --list
"""
import sys
import json
import os
import subprocess

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE        = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, 'config.json')

def load():
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)

def save(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def run_deploy():
    print("\n  正在重新分析並推送到 GitHub Pages，請稍候...\n")
    result = subprocess.run(
        [sys.executable, 'deploy.py'],
        cwd=BASE,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    )
    return result.returncode == 0

def cmd_list():
    cfg = load()
    print("\n  目前自選股清單：")
    print("  " + "-" * 40)
    for i, c in enumerate(cfg['companies'], 1):
        print(f"  {i:2d}. {c['name']:<10} {c['symbol']:<12} {c['industry']}")
    print("  " + "-" * 40)
    print(f"  共 {len(cfg['companies'])} 檔")

def cmd_remove(symbol_raw):
    symbol = symbol_raw.upper()
    if not symbol.endswith('.TW') and not symbol.endswith('.TWO'):
        symbol += '.TW'
    cfg = load()
    before = len(cfg['companies'])
    target = next((c for c in cfg['companies'] if c['symbol'] == symbol), None)
    if not target:
        print(f"  [!] 找不到 {symbol}，目前清單：")
        cmd_list()
        sys.exit(1)
    cfg['companies'] = [c for c in cfg['companies'] if c['symbol'] != symbol]
    save(cfg)
    print(f"  [-] 已移除 {target['name']} ({symbol})")
    ok = run_deploy()
    if ok:
        print(f"\n  完成！{target['name']} 已從報告中移除。")
    else:
        print("\n  [!] 分析/推送失敗，請檢查錯誤訊息。")

def cmd_add(symbol_raw, name, industry):
    symbol = symbol_raw.upper()
    if not symbol.endswith('.TW') and not symbol.endswith('.TWO'):
        symbol += '.TW'
    cfg = load()
    symbols = [c['symbol'] for c in cfg['companies']]
    if symbol in symbols:
        existing = next(c for c in cfg['companies'] if c['symbol'] == symbol)
        print(f"  [i] {existing['name']} ({symbol}) 已在清單中，直接重新分析...")
    else:
        cfg['companies'].append({'name': name, 'symbol': symbol, 'industry': industry})
        save(cfg)
        print(f"  [+] 已加入 {name} ({symbol}) — {industry}")

    ok = run_deploy()
    if ok:
        print(f"\n  完成！{name} 已出現在報告中。")
    else:
        print("\n  [!] 分析/推送失敗，請檢查錯誤訊息。")

# ── 主程式 ─────────────────────────────────────────
args = sys.argv[1:]

if not args or args[0] in ('-h', '--help'):
    print(__doc__)
    sys.exit(0)

if args[0] == '--list':
    cmd_list()

elif args[0] == '--remove':
    if len(args) < 2:
        print("  用法: uv run add_stock.py --remove <代號>")
        sys.exit(1)
    cmd_remove(args[1])

else:
    if len(args) < 2:
        print("  用法: uv run add_stock.py <代號> <名稱> [產業]")
        print("  範例: uv run add_stock.py 2317 鴻海 電子零組件")
        sys.exit(1)
    symbol   = args[0]
    name     = args[1]
    industry = args[2] if len(args) > 2 else "其他"
    cmd_add(symbol, name, industry)
