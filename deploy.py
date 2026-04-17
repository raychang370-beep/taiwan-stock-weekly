"""
自動部署腳本：產生週報並推送到 GitHub Pages
執行方式: uv run deploy.py
"""
import subprocess
import sys
import os
import json

BASE = os.path.dirname(os.path.abspath(__file__))

def run(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, shell=True, cwd=cwd or BASE,
                            capture_output=True, text=True,
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip() and check:
        # 只印警告，不終止（git 有些訊息走 stderr）
        for line in result.stderr.strip().split('\n'):
            if any(k in line.lower() for k in ['error','fatal','failed']):
                print(f"  [ERR] {line}")
            else:
                print(f"  [git] {line}")
    return result

def step(msg):
    print(f"\n{'='*48}\n  {msg}\n{'='*48}")

def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    # ── Step 1: 產生週報 ──────────────────────────
    step("1/3  產生台股技術分析週報")
    result = subprocess.run(
        [sys.executable, '-c',
         "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
         "exec(open('main.py', encoding='utf-8').read())"],
        cwd=BASE, capture_output=False,
        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
    )
    if result.returncode != 0:
        print("  [ERR] 週報產生失敗，停止部署")
        sys.exit(1)

    # ── Step 2: Git commit ──────────────────────
    step("2/3  Git commit 週報")

    # 確保 docs 已加入追蹤
    run("git add docs/index.html")

    # 檢查是否有變更
    status = run("git status --porcelain", check=False)
    if not status.stdout.strip():
        print("  [INFO] 本次無內容變更，跳過 commit")
    else:
        from datetime import datetime
        msg = f"[auto] 週報更新 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        run(f'git commit -m "{msg}"')
        print(f"  [OK] 已 commit: {msg}")

    # ── Step 3: Push 到 GitHub ──────────────────
    step("3/3  推送到 GitHub (觸發 Pages 部署)")
    push = run("git push origin master", check=False)

    if push.returncode == 0:
        with open(os.path.join(BASE, 'config.json'), encoding='utf-8') as f:
            cfg = json.load(f)
        repo = cfg.get('github_repo', '')
        owner = repo.split('/')[0] if '/' in repo else ''
        url = f"https://{owner}.github.io/taiwan-stock-weekly/" if owner else "GitHub Pages"
        print(f"\n  [OK] 推送成功！")
        print(f"  [URL] {url}")
        print(f"  [NOTE] GitHub Actions 約需 1-2 分鐘完成部署")
    else:
        print("  [ERR] 推送失敗，請確認網路連線與 GitHub 憑證")
        sys.exit(1)

if __name__ == '__main__':
    main()
