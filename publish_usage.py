"""
把 Claude 用量發布到 GitHub Pages，讓 Grok 等 bot 讀取。

用法：
  python publish_usage.py usage.json          # 寫入 docs/ 並 git push
  python publish_usage.py usage.json --no-push

usage.json 是 mcp__ccd_session_mgmt__get_usage 的輸出（整份或只有 plan 物件都可以）。
產出：
  docs/claude-usage.html  純靜態 HTML，不需要 JS、沒有密碼，bot 直接讀得到
  docs/claude-usage.json  最新一筆 + 歷史紀錄（最多 104 筆）
"""
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, "docs")
JSON_PATH = os.path.join(DOCS, "claude-usage.json")
HTML_PATH = os.path.join(DOCS, "claude-usage.html")
TPE = timezone(timedelta(hours=8))
MAX_HISTORY = 104

LABELS = {
    "5-hour limit": "目前工作階段（5 小時）",
    "Weekly · all models": "本週（所有模型）",
}


def to_taipei(iso: str) -> str:
    if not iso:
        return ""
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TPE)
    return (dt + timedelta(seconds=30)).strftime("%Y-%m-%d %H:%M")


def parse(raw: dict) -> dict:
    plan = raw.get("plan", raw)
    if plan.get("status") != "ok":
        raise SystemExit(f"用量狀態不是 ok：{plan.get('status')} {plan.get('note', '')}")
    windows = [
        {
            "label": LABELS.get(w["label"], w["label"]),
            "percentUsed": w["percentUsed"],
            "resetsAt": to_taipei(w.get("resetsAt", "")),
        }
        for w in plan.get("windows", [])
    ]
    return {
        "readAt": datetime.now(TPE).strftime("%Y-%m-%d %H:%M"),
        "plan": plan.get("plan", ""),
        "windows": windows,
    }


def render(data: dict) -> str:
    latest = data["latest"]
    e = html.escape
    lines = "".join(
        f"<li><b>{e(w['label'])}</b>：已使用 <b>{w['percentUsed']}%</b>"
        f"（{e(w['resetsAt'])} 重設，台北時間）</li>"
        for w in latest["windows"]
    )
    rows = "".join(
        "<tr><td>{}</td>{}</tr>".format(
            e(h["readAt"]),
            "".join(f"<td>{w['percentUsed']}%</td>" for w in h["windows"]),
        )
        for h in reversed(data["history"])
    )
    heads = "".join(f"<th>{e(w['label'])}</th>" for w in latest["windows"])
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Claude 用量</title>
<style>
  body{{font-family:system-ui,"Microsoft JhengHei",sans-serif;max-width:720px;margin:2rem auto;padding:0 16px;color:#222;background:#fff;line-height:1.7}}
  table{{border-collapse:collapse;width:100%;font-size:.9rem}}
  th,td{{border:1px solid #ddd;padding:.35rem .6rem;text-align:left}}
  th{{background:#f4f4f4}}
  .muted{{color:#777;font-size:.85rem}}
</style>
</head>
<body>
<h1>Claude 用量</h1>
<p>讀取時間：{e(latest['readAt'])}（台北時間）｜方案：{e(latest['plan'])}</p>
<ul>{lines}</ul>
<h2>歷史紀錄</h2>
<table><thead><tr><th>讀取時間</th>{heads}</tr></thead><tbody>{rows}</tbody></table>
<p class="muted">每週日 21:00 隨台股週報自動更新。機器可讀版本：<a href="claude-usage.json">claude-usage.json</a></p>
</body>
</html>
"""


INDEX_PATH = os.path.join(DOCS, "index.html")
MARK_START, MARK_END = "<!--CLAUDE_USAGE-->", "<!--/CLAUDE_USAGE-->"


def usage_snippet(latest: dict) -> str:
    """週報頁首的一行小字（純 HTML，bot 不跑 JS 也讀得到）"""
    parts = []
    for w in latest["windows"]:
        short = "工作階段" if "5 小時" in w["label"] else "本週" if "本週" in w["label"] else w["label"]
        parts.append(f"{short} {w['percentUsed']}%")
    weekly = next((w for w in latest["windows"] if "本週" in w["label"]), None)
    reset = f"（{weekly['resetsAt'][5:].replace('-', '/')} 重設）" if weekly else ""
    return (f'🤖 Claude 用量：{html.escape(" ｜ ".join(parts))}{html.escape(reset)}'
            f' ｜ 讀取於 {html.escape(latest["readAt"][5:].replace("-", "/"))}'
            f' ｜ <a href="claude-usage.html">歷史</a>')


def inject_index(latest: dict | None = None) -> bool:
    """把用量寫進 docs/index.html 的標記之間；latest 省略時用 claude-usage.json 的最新一筆。"""
    if latest is None:
        if not os.path.exists(JSON_PATH):
            return False
        with open(JSON_PATH, encoding="utf-8") as f:
            latest = json.load(f)["latest"]
    if not os.path.exists(INDEX_PATH):
        return False
    with open(INDEX_PATH, encoding="utf-8", newline="") as f:
        page = f.read()
    start, end = page.find(MARK_START), page.find(MARK_END)
    if start < 0 or end < start:
        print("  [警告] index.html 沒有 CLAUDE_USAGE 標記，略過")
        return False
    page = page[:start + len(MARK_START)] + usage_snippet(latest) + page[end:]
    with open(INDEX_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(page)
    return True


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    with open(args[0], encoding="utf-8") as f:
        latest = parse(json.load(f))

    data = {"latest": latest, "history": []}
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, encoding="utf-8") as f:
            data["history"] = json.load(f).get("history", [])
    data["history"] = (data["history"] + [latest])[-MAX_HISTORY:]
    data["latest"] = latest

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(render(data))
    print("已寫入", HTML_PATH)
    if inject_index(latest):
        print("已更新週報頁首的用量")
    for w in latest["windows"]:
        print(f"  {w['label']}: {w['percentUsed']}%（{w['resetsAt']} 重設）")

    if "--no-push" in sys.argv:
        return
    os.chdir(BASE)
    subprocess.run(["git", "add", "docs/claude-usage.html", "docs/claude-usage.json",
                    "docs/index.html"], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode == 0:
        print("沒有變更，跳過 commit。")
        return
    subprocess.run(["git", "commit", "-m", f"Claude 用量更新：{latest['readAt']}"], check=True)
    subprocess.run(["git", "push"], check=True)
    print("已推送：https://raychang370-beep.github.io/taiwan-stock-weekly/claude-usage.html")


if __name__ == "__main__":
    main()
