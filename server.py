"""
台股週報本機伺服器 (port 8899)
- http://localhost:8899        → 管理頁面（新增/移除自選股、觸發分析）
- http://localhost:8899/report → 預覽本地報告
- 執行方式: uv run server.py
"""
import json
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')
REPORT_PATH = os.path.join(BASE_DIR, 'docs', 'index.html')

# ── 管理頁面 HTML（內嵌，不依賴外部檔案）────────────────
MANAGE_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股週報 — 自選股管理</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Microsoft JhengHei','Noto Sans TC',sans-serif;
       background:#f0f4f8;min-height:100vh;padding:2rem 1rem;}
  .card{background:#fff;border-radius:14px;box-shadow:0 4px 20px rgba(0,0,0,.1);
        max-width:700px;margin:0 auto;padding:2rem;}
  h1{font-size:1.4rem;margin-bottom:.3rem;color:#1a1a2e;}
  .sub{color:#888;font-size:.82rem;margin-bottom:1.5rem;}
  label{font-size:.78rem;color:#666;display:block;margin-bottom:.25rem;}
  input,select{width:100%;padding:.55rem .8rem;border:1.5px solid #ccc;
               border-radius:8px;font-size:.92rem;outline:none;font-family:inherit;
               margin-bottom:.9rem;}
  input:focus,select:focus{border-color:#1a73e8;}
  .row{display:flex;gap:.8rem;}
  .row>div{flex:1;}
  .btn{width:100%;padding:.65rem;border:none;border-radius:9px;font-size:.95rem;
       font-weight:700;cursor:pointer;font-family:inherit;transition:opacity .2s;}
  .btn-add{background:#1a73e8;color:#fff;margin-bottom:.7rem;}
  .btn-run{background:#00b300;color:#fff;}
  .btn:hover{opacity:.85;}
  .btn:disabled{background:#aaa;cursor:not-allowed;opacity:1;}
  #msg{margin-top:1rem;padding:.6rem .9rem;border-radius:8px;font-size:.85rem;display:none;}
  #msg.ok{background:#e6ffe6;color:#006600;display:block;}
  #msg.err{background:#ffe6e6;color:#cc0000;display:block;}
  #msg.info{background:#e8f0fe;color:#1a73e8;display:block;}
  .stocks{margin-top:1.5rem;border-top:1.5px solid #eee;padding-top:1rem;}
  .stocks h3{font-size:.9rem;color:#1a1a2e;margin-bottom:.7rem;}
  .tag-list{display:flex;flex-wrap:wrap;gap:.5rem;}
  .tag{display:flex;align-items:center;gap:.4rem;background:#f0f4ff;
       border:1.5px solid #c5d5ff;border-radius:20px;padding:.3rem .8rem;font-size:.82rem;}
  .tag .rm{cursor:pointer;color:#cc0000;font-weight:700;font-size:.95rem;margin-left:.1rem;}
  .tag .rm:hover{opacity:.7;}
  .divider{border:none;border-top:1.5px solid #eee;margin:1.2rem 0;}
  a.report-link{display:block;text-align:center;margin-top:1rem;color:#1a73e8;
                font-size:.82rem;text-decoration:none;}
  a.report-link:hover{text-decoration:underline;}
</style>
</head>
<body>
<div class="card">
  <h1>⭐ 自選股管理</h1>
  <div class="sub">台股週報本機管理介面 — 新增或移除自選股並重新分析</div>

  <div class="row">
    <div>
      <label>股票代號（如 2317）</label>
      <input id="sym" type="text" placeholder="2317" maxlength="12">
    </div>
    <div>
      <label>公司名稱</label>
      <input id="nm" type="text" placeholder="鴻海" maxlength="20">
    </div>
  </div>
  <div>
    <label>產業</label>
    <select id="ind">
      <option>半導體</option><option>記憶體</option>
      <option selected>電子零組件</option><option>金融</option>
      <option>傳產</option><option>生技</option><option>其他</option>
    </select>
  </div>

  <button class="btn btn-add" onclick="addStock()">＋ 加入並立即分析</button>
  <button class="btn btn-run" id="btnRun" onclick="runOnly()">🔄 重新分析（不新增）</button>

  <div id="msg"></div>

  <div class="stocks">
    <h3>目前自選股清單</h3>
    <div class="tag-list" id="tagList"><span style="color:#aaa;font-size:.82rem;">載入中...</span></div>
  </div>

  <hr class="divider">
  <a class="report-link" href="/report" target="_blank">📊 預覽本地報告（不需密碼）</a>
</div>

<script>
const API = '';   // 同 origin，不需要 http://localhost:8899

var _t = null;
function msg(text, type){
  const el = document.getElementById('msg');
  if(_t){ clearTimeout(_t); _t=null; }
  el.removeAttribute('style');
  el.textContent = text;
  el.className = type;
  _t = setTimeout(function(){ el.className=''; }, 10000);
}

function loadStocks(){
  fetch('/api/config').then(r=>r.json()).then(function(cfg){
    const list = document.getElementById('tagList');
    list.innerHTML = '';
    if(!cfg.companies || cfg.companies.length===0){
      list.innerHTML = '<span style="color:#aaa;font-size:.82rem;">尚無自選股</span>';
      return;
    }
    cfg.companies.forEach(function(s){
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.innerHTML = '<b>'+s.name+'</b>&nbsp;<span style="color:#888;font-size:.75rem;">'+s.symbol+'</span>'
        +'<span class="rm" onclick="removeStock(\''+s.symbol+'\',\''+s.name+'\')" title="移除">×</span>';
      list.appendChild(tag);
    });
  }).catch(function(){ msg('載入設定失敗','err'); });
}

function disableAll(){ document.querySelectorAll('.btn').forEach(b=>b.disabled=true); }
function enableAll(){  document.querySelectorAll('.btn').forEach(b=>b.disabled=false); }

function addStock(){
  const sym = document.getElementById('sym').value.trim().toUpperCase();
  const nm  = document.getElementById('nm').value.trim();
  const ind = document.getElementById('ind').value;
  if(!sym){ msg('⚠️ 請輸入股票代號','err'); return; }
  if(!nm){  msg('⚠️ 請輸入公司名稱','err'); return; }
  const symbol = sym.includes('.') ? sym : sym+'.TW';

  disableAll();
  msg('⏳ 正在加入 '+nm+' 並啟動分析，請稍候（約20秒）...','info');

  fetch('/api/add-stock',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({name:nm, symbol:symbol, industry:ind})
  })
  .then(r=>r.json())
  .then(function(d){
    if(!d.ok) throw new Error(d.error||'加入失敗');
    document.getElementById('sym').value='';
    document.getElementById('nm').value='';
    msg('✅ 已加入 '+nm+'！正在重新分析...','info');
    return fetch('/api/run',{method:'POST'});
  })
  .then(r=>r.json())
  .then(function(d){
    enableAll();
    if(!d.ok) throw new Error(d.error||'分析失敗');
    loadStocks();
    msg('🎉 分析完成！報告已更新並推送至 GitHub Pages','ok');
  })
  .catch(function(e){ enableAll(); msg('❌ '+e.message,'err'); });
}

function removeStock(symbol, name){
  if(!confirm('確定移除「'+name+'」？移除後將立即重新分析。')){ return; }
  disableAll();
  msg('⏳ 正在移除 '+name+' 並重新分析...','info');

  fetch('/api/remove-stock',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({symbol:symbol})
  })
  .then(r=>r.json())
  .then(function(d){
    if(!d.ok) throw new Error(d.error||'移除失敗');
    return fetch('/api/run',{method:'POST'});
  })
  .then(r=>r.json())
  .then(function(d){
    enableAll();
    if(!d.ok) throw new Error(d.error||'分析失敗');
    loadStocks();
    msg('✅ 已移除 '+name+'，報告已更新','ok');
  })
  .catch(function(e){ enableAll(); msg('❌ '+e.message,'err'); });
}

function runOnly(){
  disableAll();
  msg('⏳ 重新分析中，請稍候（約20秒）...','info');
  fetch('/api/run',{method:'POST'})
    .then(r=>r.json())
    .then(function(d){
      enableAll();
      if(d.ok){ loadStocks(); msg('🎉 分析完成！報告已更新','ok'); }
      else     { msg('❌ '+d.error,'err'); }
    })
    .catch(function(){ enableAll(); msg('❌ 分析失敗','err'); });
}

loadStocks();
</script>
</body>
</html>"""


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
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_str):
        body = html_str.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, mime='text/html'):
        try:
            with open(path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{mime}; charset=utf-8')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self.send_error(404, 'File not found')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html', '/manage'):
            self.send_html(MANAGE_HTML)
        elif path == '/report':
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
                # 呼叫 deploy.py（內部已包含 main.py + git push）
                script = (
                    "import sys; sys.stdout.reconfigure(encoding='utf-8'); "
                    "exec(open('deploy.py', encoding='utf-8').read())"
                )
                result = subprocess.run(
                    [sys.executable, '-c', script],
                    cwd=BASE_DIR,
                    capture_output=True, text=True, timeout=180,
                    env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                if result.returncode == 0:
                    print("  [OK] 分析+推送完成")
                    self.send_json({'ok': True, 'output': result.stdout[-500:]})
                else:
                    print("  [ERR]", result.stderr[-200:])
                    self.send_json({'ok': False, 'error': result.stderr[-300:]}, 500)
            except subprocess.TimeoutExpired:
                self.send_json({'ok': False, 'error': '分析逾時（180秒）'}, 500)
            except Exception as e:
                self.send_json({'ok': False, 'error': str(e)}, 500)
        else:
            self.send_error(404)


if __name__ == '__main__':
    port = 8899
    server = HTTPServer(('localhost', port), Handler)
    print("=" * 50)
    print("  Taiwan Stock Weekly - 本機管理伺服器")
    print(f"  管理頁面: http://localhost:{port}")
    print(f"  本地報告: http://localhost:{port}/report")
    print("  按 Ctrl+C 停止")
    print("=" * 50)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  伺服器已停止")
