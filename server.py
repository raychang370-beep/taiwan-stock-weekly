"""
台股週報本機伺服器 (port 8899)
- 提供 HTTP 服務，讓瀏覽器可以新增/移除股票並觸發重新分析
- 執行方式: uv run server.py
"""
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
REPORT_PATH = os.path.join(os.path.dirname(__file__), 'docs', 'index.html')

def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  [{self.address_string()}] {format % args}")

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, mime='text/html'):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{mime}; charset=utf-8')
            self.send_header('Content-Length', len(content))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, 'File not found')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            self.send_file(REPORT_PATH)
        elif path == '/api/config':
            self.send_json(load_config())
        else:
            self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length) or b'{}')

        if path == '/api/add-stock':
            try:
                cfg = load_config()
                symbols = [c['symbol'] for c in cfg['companies']]
                symbol = body.get('symbol', '')
                if not symbol.endswith('.TW') and not symbol.endswith('.TWO'):
                    symbol += '.TW'
                if symbol not in symbols:
                    cfg['companies'].append({
                        'name':     body.get('name', symbol),
                        'symbol':   symbol,
                        'industry': body.get('industry', '其他'),
                    })
                    save_config(cfg)
                    print(f"  [+] 已加入 {body.get('name')} ({symbol})")
                self.send_json({'ok': True, 'symbol': symbol})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/api/remove-stock':
            try:
                cfg = load_config()
                symbol = body.get('symbol', '')
                before = len(cfg['companies'])
                cfg['companies'] = [c for c in cfg['companies'] if c['symbol'] != symbol]
                save_config(cfg)
                print(f"  [-] 已移除 {symbol} (剩 {len(cfg['companies'])} 檔)")
                self.send_json({'ok': True, 'removed': before - len(cfg['companies'])})
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)

        elif path == '/api/run':
            try:
                print("  [*] 開始重新分析...")
                result = subprocess.run(
                    [sys.executable, '-c',
                     "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
                     "exec(open('main.py',encoding='utf-8').read())"],
                    cwd=os.path.dirname(__file__),
                    capture_output=True, text=True, timeout=120,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                if result.returncode == 0:
                    print("  [OK] 分析完成")
                    self.send_json({'ok': True, 'output': result.stdout[-500:]})
                else:
                    print("  [ERR]", result.stderr[-200:])
                    self.send_json({'ok': False, 'error': result.stderr[-300:]}, 500)
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': '分析逾時（120秒）'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)
        else:
            self.send_error(404)


if __name__ == '__main__':
    port = 8899
    server = HTTPServer(('localhost', port), Handler)
    print("=" * 45)
    print(f"  Taiwan Stock Weekly - Local Server")
    print(f"  http://localhost:{port}")
    print(f"  按 Ctrl+C 停止")
    print("=" * 45)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  伺服器已停止")
