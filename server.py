"""
台股週報本機管理伺服器 (Flask)
執行: uv run server.py
管理: http://localhost:8899
"""
import json, os, subprocess, sys, threading
from flask import Flask, jsonify, request, send_file

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE        = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, 'config.json')
REPORT_PATH = os.path.join(BASE, 'docs', 'index.html')

app = Flask(__name__)

# ── 鎖，防止同時跑兩次分析 ───────────────────────
_analysis_lock = threading.Lock()

def load_config():
    with open(CONFIG_PATH, encoding='utf-8') as f:
        return json.load(f)

def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

# ── 管理頁面 HTML ────────────────────────────────
MANAGE_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股週報 自選股管理</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Microsoft JhengHei',sans-serif;background:#f0f4f8;
     display:flex;justify-content:center;padding:2rem 1rem;}
.card{background:#fff;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.12);
      width:100%;max-width:640px;padding:2rem 2.5rem;}
h1{font-size:1.5rem;margin-bottom:.25rem;color:#1a1a2e;}
.sub{color:#888;font-size:.82rem;margin-bottom:1.8rem;}
.row{display:flex;gap:.75rem;margin-bottom:.9rem;}
.col{flex:1;}
label{display:block;font-size:.76rem;color:#666;margin-bottom:.3rem;}
input,select{width:100%;padding:.55rem .8rem;border:1.5px solid #ddd;
             border-radius:8px;font-size:.92rem;font-family:inherit;outline:none;}
input:focus,select:focus{border-color:#1a73e8;box-shadow:0 0 0 3px rgba(26,115,232,.15);}
.btns{display:flex;flex-direction:column;gap:.65rem;margin-top:1.2rem;}
button{padding:.7rem;border:none;border-radius:10px;font-size:.95rem;font-weight:700;
       cursor:pointer;font-family:inherit;transition:opacity .15s;}
button:hover:not(:disabled){opacity:.85;}
button:disabled{opacity:.5;cursor:not-allowed;}
.btn-add{background:#1a73e8;color:#fff;}
.btn-run{background:#00b300;color:#fff;}
.btn-list{background:#f4f4f4;color:#333;font-size:.85rem;}
#status{margin-top:1rem;padding:.65rem .9rem;border-radius:8px;font-size:.85rem;
        display:none;line-height:1.5;}
#status.ok  {background:#e6ffe6;color:#006600;display:block;}
#status.err {background:#ffe6e6;color:#cc0000;display:block;}
#status.info{background:#e8f0fe;color:#1a73e8;display:block;}
.divider{border:none;border-top:1.5px solid #eee;margin:1.5rem 0;}
.stocks{margin-top:.5rem;}
.stocks h3{font-size:.88rem;color:#444;margin-bottom:.65rem;}
.tag-wrap{display:flex;flex-wrap:wrap;gap:.45rem;min-height:2rem;}
.tag{display:inline-flex;align-items:center;gap:.35rem;background:#f0f4ff;
     border:1.5px solid #c5d5ff;border-radius:20px;padding:.28rem .75rem;font-size:.82rem;}
.rm{cursor:pointer;color:#cc0000;font-weight:bold;font-size:1rem;line-height:1;
    margin-left:.1rem;}
.rm:hover{opacity:.7;}
.report-link{display:block;text-align:center;color:#1a73e8;font-size:.8rem;
             text-decoration:none;margin-top:1.2rem;}
</style>
</head>
<body>
<div class="card">
  <h1>⭐ 自選股管理</h1>
  <div class="sub">台股週報本機管理 — 新增/移除自選股，自動重新分析並推送報告</div>

  <div class="row">
    <div class="col">
      <label>股票代號</label>
      <input id="sym" type="text" placeholder="2317" maxlength="12"
             onkeydown="if(event.key==='Enter')document.getElementById('nm').focus()">
    </div>
    <div class="col">
      <label>公司名稱</label>
      <input id="nm" type="text" placeholder="鴻海" maxlength="20"
             onkeydown="if(event.key==='Enter')addStock()">
    </div>
  </div>
  <div>
    <label>產業</label>
    <select id="ind">
      <option>半導體</option><option>記憶體</option>
      <option>電子零組件</option><option>金融</option>
      <option>傳產</option><option>生技</option><option>其他</option>
    </select>
  </div>

  <div class="btns">
    <button type="button" class="btn-add" id="btnAdd" onclick="addStock()">
      ＋ 加入並立即分析
    </button>
    <button type="button" class="btn-run" id="btnRun" onclick="runOnly()">
      🔄 重新分析（不新增）
    </button>
    <button type="button" class="btn-list" onclick="loadList()">
      ↻ 重新載入清單
    </button>
  </div>

  <div id="status"></div>

  <hr class="divider">

  <div class="stocks">
    <h3>目前自選股清單</h3>
    <div class="tag-wrap" id="tagWrap">載入中...</div>
  </div>

  <a class="report-link" href="/report" target="_blank">📊 預覽本地報告</a>
</div>

<script>
var _st = null;
function showStatus(text, type) {
  var el = document.getElementById('status');
  if (_st) { clearTimeout(_st); _st = null; }
  el.innerHTML = text;
  el.className = type;
  if (type !== 'info') {
    _st = setTimeout(function(){ el.className = ''; }, 12000);
  }
}

function disableButtons(disabled) {
  document.getElementById('btnAdd').disabled = disabled;
  document.getElementById('btnRun').disabled = disabled;
}

function loadList() {
  fetch('/api/config')
    .then(function(r) { return r.json(); })
    .then(function(cfg) {
      var wrap = document.getElementById('tagWrap');
      wrap.innerHTML = '';
      if (!cfg.companies || cfg.companies.length === 0) {
        wrap.innerHTML = '<span style="color:#aaa">尚無自選股</span>';
        return;
      }
      cfg.companies.forEach(function(s) {
        var tag = document.createElement('span');
        tag.className = 'tag';
        tag.innerHTML =
          '<b>' + s.name + '</b>' +
          '<span style="color:#888;font-size:.75rem">' + s.symbol + '</span>' +
          '<span class="rm" title="移除" onclick="removeStock(\'' +
            s.symbol + '\',\'' + s.name + '\')">&times;</span>';
        wrap.appendChild(tag);
      });
    })
    .catch(function() {
      document.getElementById('tagWrap').innerHTML =
        '<span style="color:red">載入失敗</span>';
    });
}

function addStock() {
  var sym = document.getElementById('sym').value.trim().toUpperCase();
  var nm  = document.getElementById('nm').value.trim();
  var ind = document.getElementById('ind').value;
  if (!sym) { showStatus('⚠️ 請輸入股票代號', 'err'); return; }
  if (!nm)  { showStatus('⚠️ 請輸入公司名稱', 'err'); return; }
  var symbol = sym.indexOf('.') >= 0 ? sym : sym + '.TW';

  disableButtons(true);
  showStatus('⏳ 加入 ' + nm + ' 並啟動分析中，請稍候約 30 秒...', 'info');

  fetch('/api/add-stock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: nm, symbol: symbol, industry: ind })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (!d.ok) throw new Error(d.error || '加入失敗');
    document.getElementById('sym').value = '';
    document.getElementById('nm').value  = '';
    showStatus('✅ 已加入 ' + nm + '！正在執行分析和推送...', 'info');
    return fetch('/api/run', { method: 'POST' });
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    disableButtons(false);
    if (!d.ok) throw new Error(d.error || '分析失敗');
    loadList();
    showStatus('🎉 完成！<br>報告已更新並推送至 GitHub Pages。<br>約 1~2 分鐘後可在手機上查看。', 'ok');
  })
  .catch(function(e) {
    disableButtons(false);
    showStatus('❌ 錯誤：' + e.message, 'err');
  });
}

function removeStock(symbol, name) {
  if (!confirm('確定移除「' + name + '」？')) return;
  disableButtons(true);
  showStatus('⏳ 移除 ' + name + ' 並重新分析中...', 'info');

  fetch('/api/remove-stock', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol: symbol })
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (!d.ok) throw new Error(d.error || '移除失敗');
    return fetch('/api/run', { method: 'POST' });
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    disableButtons(false);
    if (!d.ok) throw new Error(d.error || '分析失敗');
    loadList();
    showStatus('✅ 已移除 ' + name + '，報告已更新', 'ok');
  })
  .catch(function(e) {
    disableButtons(false);
    showStatus('❌ 錯誤：' + e.message, 'err');
  });
}

function runOnly() {
  disableButtons(true);
  showStatus('⏳ 重新分析中，請稍候約 30 秒...', 'info');
  fetch('/api/run', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(d) {
      disableButtons(false);
      if (d.ok) {
        loadList();
        showStatus('🎉 分析完成！報告已更新', 'ok');
      } else {
        showStatus('❌ ' + d.error, 'err');
      }
    })
    .catch(function(e) {
      disableButtons(false);
      showStatus('❌ 錯誤：' + e.message, 'err');
    });
}

loadList();
</script>
</body>
</html>"""


# ── Flask 路由 ────────────────────────────────────

@app.route('/')
def index():
    return MANAGE_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/report')
def report():
    return send_file(REPORT_PATH)

@app.route('/api/config')
def api_config():
    return jsonify(load_config())

@app.route('/api/add-stock', methods=['POST'])
def api_add_stock():
    try:
        data   = request.get_json(force=True)
        cfg    = load_config()
        symbol = data.get('symbol', '').upper()
        if not symbol.endswith('.TW') and not symbol.endswith('.TWO'):
            symbol += '.TW'
        exists = any(c['symbol'] == symbol for c in cfg['companies'])
        if not exists:
            cfg['companies'].append({
                'name':     data.get('name', symbol),
                'symbol':   symbol,
                'industry': data.get('industry', '其他'),
            })
            save_config(cfg)
            print(f'  [+] 已加入 {data.get("name")} ({symbol})')
        else:
            print(f'  [i] {symbol} 已存在，略過')
        return jsonify({'ok': True, 'symbol': symbol})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/remove-stock', methods=['POST'])
def api_remove_stock():
    try:
        data   = request.get_json(force=True)
        symbol = data.get('symbol', '')
        cfg    = load_config()
        before = len(cfg['companies'])
        cfg['companies'] = [c for c in cfg['companies'] if c['symbol'] != symbol]
        save_config(cfg)
        print(f'  [-] 已移除 {symbol}（剩 {len(cfg["companies"])} 檔）')
        return jsonify({'ok': True, 'removed': before - len(cfg['companies'])})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/api/run', methods=['POST'])
def api_run():
    if not _analysis_lock.acquire(blocking=False):
        return jsonify({'ok': False, 'error': '分析已在執行中，請稍候'}), 429
    try:
        print('  [*] 開始分析並部署...')
        result = subprocess.run(
            [sys.executable, 'deploy.py'],
            cwd=BASE,
            capture_output=True,
            encoding='utf-8',
            errors='replace',
            timeout=300,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
        )
        if result.stdout:
            print(result.stdout[-800:])
        if result.returncode == 0:
            print('  [OK] 分析完成')
            return jsonify({'ok': True})
        else:
            err = result.stderr[-400:] if result.stderr else '未知錯誤'
            print(f'  [ERR] {err}')
            return jsonify({'ok': False, 'error': err}), 500
    except subprocess.TimeoutExpired:
        return jsonify({'ok': False, 'error': '逾時（300秒）'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        _analysis_lock.release()


if __name__ == '__main__':
    print('=' * 50)
    print('  Taiwan Stock Weekly - 本機管理伺服器')
    print('  管理頁面: http://localhost:8899')
    print('  本地報告: http://localhost:8899/report')
    print('  按 Ctrl+C 停止')
    print('=' * 50)
    app.run(host='localhost', port=8899, debug=False, threaded=True)
