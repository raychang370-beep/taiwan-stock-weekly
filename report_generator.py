"""
HTML 週報產生器 v2
- 頂部「型態分類依據」視覺說明
- 自選股新增/管理 UI（透過本機 API 伺服器）
- KD 線圖表（Chart.js）
- 買入/必買/賣出/必賣 分類顯示
"""
import json
import os
from datetime import datetime
from jinja2 import Template

CATEGORY_CONFIG = {
    "必買": {"color": "#00b300", "bg": "#e6ffe6", "border": "#00b300", "icon": "🚀", "order": 1},
    "買入": {"color": "#33cc33", "bg": "#f0fff0", "border": "#33cc33", "icon": "📈", "order": 2},
    "等待": {"color": "#ff9900", "bg": "#fff8e6", "border": "#ff9900", "icon": "⏳", "order": 3},
    "賣出": {"color": "#ff3333", "bg": "#fff0f0", "border": "#ff3333", "icon": "📉", "order": 4},
    "必賣": {"color": "#cc0000", "bg": "#ffe6e6", "border": "#cc0000", "icon": "💣", "order": 5},
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ title }} — {{ week_label }}</title>
<!-- 密碼保護：在 Chart.js 之前執行，防止頁面內容被看到 -->
<script>
(function(){
  const HASH = "{{ password_hash }}"; // SHA-256 of password
  const KEY  = "tw_stock_auth";
  async function sha256(msg){
    const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(msg));
    return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');
  }
  async function check(){
    const saved = sessionStorage.getItem(KEY);
    if(saved === HASH){ document.getElementById('lock').style.display='none'; return; }
    document.getElementById('lock').style.display='flex';
    document.getElementById('main-body').style.display='none';
    document.getElementById('pw-input').focus();
    document.getElementById('pw-form').onsubmit = async function(e){
      e.preventDefault();
      const pw = document.getElementById('pw-input').value;
      const h  = await sha256(pw);
      if(h === HASH){
        sessionStorage.setItem(KEY, h);
        document.getElementById('lock').style.display='none';
        document.getElementById('main-body').style.display='block';
      } else {
        document.getElementById('pw-err').textContent='密碼錯誤，請再試一次';
        document.getElementById('pw-input').value='';
        document.getElementById('pw-input').focus();
      }
    };
  }
  window.addEventListener('DOMContentLoaded', check);
})();
</script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --buy-strong:#00b300; --buy:#33cc33; --wait:#e6a800;
    --sell:#ff3333; --sell-strong:#cc0000;
    --bg:#f5f7fa; --card:#fff; --text:#1a1a2e; --sub:#666;
    --radius:12px;
  }
  *{box-sizing:border-box;margin:0;padding:0;}
  body{font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif;background:var(--bg);color:var(--text);}

  /* ── Header ── */
  header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:1.6rem 2rem;text-align:center;}
  header h1{font-size:1.9rem;margin-bottom:.3rem;}
  .subtitle{color:#aaa;font-size:.85rem;}
  .cat-summary{display:flex;gap:.6rem;justify-content:center;flex-wrap:wrap;margin-top:1rem;}
  .cat-pill{padding:.35rem .9rem;border-radius:20px;font-weight:700;font-size:.82rem;display:flex;align-items:center;gap:.3rem;}

  /* ── 自選股管理面板 ── */
  .stock-manager{background:#fff;border-bottom:3px solid #e0e0e0;padding:1.2rem 2rem;}
  .stock-manager h2{font-size:1rem;font-weight:700;margin-bottom:.8rem;color:#1a1a2e;display:flex;align-items:center;gap:.4rem;}
  .manager-row{display:flex;gap:.8rem;flex-wrap:wrap;align-items:flex-end;}
  .manager-row input,
  .manager-row select{padding:.45rem .75rem;border:1.5px solid #ccc;border-radius:8px;font-size:.88rem;outline:none;font-family:inherit;}
  .manager-row input:focus,
  .manager-row select:focus{border-color:#1a73e8;}
  .btn{padding:.45rem 1.1rem;border:none;border-radius:8px;font-size:.88rem;font-weight:600;cursor:pointer;font-family:inherit;transition:opacity .2s;}
  .btn-add{background:#1a73e8;color:#fff;}
  .btn-run{background:#00b300;color:#fff;}
  .btn-run:disabled{background:#999;cursor:not-allowed;}
  .btn:hover:not(:disabled){opacity:.85;}
  .stocks-list{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.8rem;}
  .stock-tag{display:flex;align-items:center;gap:.3rem;background:#f0f4ff;border:1.5px solid #c5d5ff;border-radius:20px;padding:.25rem .7rem;font-size:.82rem;}
  .stock-tag .remove{cursor:pointer;color:#cc0000;font-weight:700;margin-left:.2rem;font-size:.9rem;}
  .stock-tag.new-tag{background:#e6ffe6;border-color:#00b300;color:#006600;}
  #manager-msg{font-size:.82rem;margin-top:.5rem;padding:.35rem .8rem;border-radius:6px;display:none;}
  #manager-msg.ok{background:#e6ffe6;color:#006600;display:block;}
  #manager-msg.err{background:#ffe6e6;color:#cc0000;display:block;}
  #manager-msg.info{background:#e6f0ff;color:#1a73e8;display:block;}

  /* ── 型態分類依據 ── */
  .pattern-guide{background:#fff;padding:1.2rem 2rem;border-bottom:3px solid #e0e0e0;}
  .pattern-guide h2{font-size:1rem;font-weight:700;margin-bottom:.9rem;color:#1a1a2e;}
  .guide-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:.7rem;}
  .guide-card{border-radius:10px;padding:.75rem 1rem;border:1.5px solid;}
  .guide-card h4{font-size:.82rem;font-weight:700;margin-bottom:.45rem;display:flex;align-items:center;gap:.3rem;}
  .guide-card ul{list-style:none;font-size:.78rem;line-height:1.8;}
  .guide-card ul li::before{content:"▸ ";}
  .guide-kd{display:flex;gap:.6rem;flex-wrap:wrap;margin-top:.9rem;}
  .kd-tag{padding:.3rem .75rem;border-radius:8px;font-size:.78rem;font-weight:600;}

  /* ── 容器 ── */
  .container{max-width:1400px;margin:0 auto;padding:1.5rem;}
  .section-title{font-size:1.15rem;font-weight:700;margin:1.5rem 0 .7rem;
                 padding:.4rem .9rem;border-left:4px solid;border-radius:5px;}
  .cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:1.2rem;margin-bottom:1.5rem;}
  .card{background:var(--card);border-radius:var(--radius);padding:1.2rem;
        box-shadow:0 2px 10px rgba(0,0,0,.08);border-top:4px solid;transition:transform .2s;}
  .card:hover{transform:translateY(-3px);}
  .card-header{display:flex;justify-content:space-between;align-items:flex-start;}
  .stock-name{font-size:1.05rem;font-weight:700;}
  .stock-symbol{color:var(--sub);font-size:.78rem;}
  .price{font-size:1.35rem;font-weight:700;}
  .change{font-size:.83rem;}
  .change.up{color:var(--buy);}
  .change.down{color:var(--sell);}
  .pattern-badge{display:inline-block;margin:.55rem 0;padding:.2rem .7rem;border-radius:20px;font-size:.78rem;font-weight:600;}
  .kd-row{display:flex;gap:.8rem;margin:.35rem 0;font-size:.82rem;}
  .kd-item{background:#f4f4f4;padding:.2rem .6rem;border-radius:6px;}
  .kd-item span{font-weight:700;}
  .cross-tag{font-size:.73rem;padding:.12rem .5rem;border-radius:10px;background:#fff3cd;color:#856404;font-weight:600;margin-left:.3rem;}
  .chart-wrap{margin-top:.75rem;height:130px;position:relative;}
  .chart-wrap canvas{max-height:130px;}
  .ma-row{display:flex;gap:.7rem;margin:.3rem 0;font-size:.76rem;color:var(--sub);}
  .confidence-bar{background:#e0e0e0;border-radius:4px;height:5px;margin:.35rem 0;overflow:hidden;}
  .confidence-fill{height:100%;border-radius:4px;}

  /* ── 新聞 ── */
  .news-section{background:var(--card);border-radius:var(--radius);padding:1.2rem;
                margin-bottom:1.5rem;box-shadow:0 2px 8px rgba(0,0,0,.07);}
  .news-section h3{margin-bottom:.7rem;font-size:.95rem;}
  .news-item{padding:.45rem 0;border-bottom:1px solid #eee;font-size:.83rem;}
  .news-item:last-child{border-bottom:none;}
  .news-item a{color:#1a73e8;text-decoration:none;}
  .news-item a:hover{text-decoration:underline;}
  .news-source{color:var(--sub);font-size:.74rem;margin-top:.15rem;}

  footer{text-align:center;padding:2rem;color:var(--sub);font-size:.78rem;}
</style>
</head>
<body>

<!-- 密碼鎖定畫面 -->
<div id="lock" style="display:none;position:fixed;inset:0;background:linear-gradient(135deg,#1a1a2e,#16213e);
     z-index:9999;align-items:center;justify-content:center;flex-direction:column;">
  <div style="background:#fff;border-radius:16px;padding:2.5rem 3rem;text-align:center;max-width:360px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,.4);">
    <div style="font-size:3rem;margin-bottom:.5rem;">🔐</div>
    <h2 style="font-size:1.2rem;margin-bottom:.3rem;color:#1a1a2e;">台股週報</h2>
    <p style="color:#666;font-size:.85rem;margin-bottom:1.2rem;">請輸入密碼以查看報告</p>
    <form id="pw-form">
      <input id="pw-input" type="password" placeholder="輸入密碼"
        style="width:100%;padding:.6rem .9rem;border:2px solid #ddd;border-radius:8px;
               font-size:1rem;outline:none;margin-bottom:.5rem;font-family:inherit;" />
      <div id="pw-err" style="color:#cc0000;font-size:.82rem;min-height:1.2rem;margin-bottom:.5rem;"></div>
      <button type="submit"
        style="width:100%;padding:.65rem;background:#1a1a2e;color:#fff;border:none;
               border-radius:8px;font-size:.95rem;cursor:pointer;font-weight:600;">
        進入報告 →
      </button>
    </form>
  </div>
</div>

<!-- 主要內容（密碼正確後顯示） -->
<div id="main-body">

<!-- ① Header -->
<header>
  <h1>📊 {{ title }}</h1>
  <div class="subtitle">{{ week_label }} ｜ 產生時間：{{ generated_at }}</div>
  <div class="cat-summary">
    {% for cat, cfg in categories.items() %}
    <span class="cat-pill" style="background:{{cfg.bg}};color:{{cfg.color}};border:1px solid {{cfg.border}}">
      {{cfg.icon}} {{cat}} ({{ cat_counts[cat] }})
    </span>
    {% endfor %}
  </div>
</header>

<!-- ② 自選股管理面板 -->
<div class="stock-manager">
  <h2>⭐ 自選股管理</h2>
  <div class="manager-row">
    <div>
      <div style="font-size:.75rem;color:#888;margin-bottom:.3rem;">股票代號（如 2330）</div>
      <input id="inp-symbol" type="text" placeholder="2330" maxlength="10" style="width:110px">
    </div>
    <div>
      <div style="font-size:.75rem;color:#888;margin-bottom:.3rem;">公司名稱</div>
      <input id="inp-name" type="text" placeholder="台積電" maxlength="20" style="width:120px">
    </div>
    <div>
      <div style="font-size:.75rem;color:#888;margin-bottom:.3rem;">產業</div>
      <select id="inp-industry">
        <option>半導體</option>
        <option>記憶體</option>
        <option>電子零組件</option>
        <option>金融</option>
        <option>傳產</option>
        <option>生技</option>
        <option>其他</option>
      </select>
    </div>
    <button class="btn btn-add" onclick="addStock()">＋ 加入</button>
    <button class="btn btn-run" id="btn-run" onclick="runAnalysis()">🔄 重新分析</button>
  </div>
  <div class="stocks-list" id="stocks-list"></div>
  <div id="manager-msg"></div>
</div>

<!-- ③ 型態分類依據 -->
<div class="pattern-guide">
  <h2>📐 型態分類依據（依圖表技術分析）</h2>
  <div class="guide-grid">
    <div class="guide-card" style="background:#e6ffe6;border-color:#00b300;">
      <h4 style="color:#006600;">🚀 必買（80–100% 信心）</h4>
      <ul style="color:#006600;">
        <li>KD 黃金交叉 ＋ K&lt;20 超賣</li>
        <li>W底（雙底）突破頸線</li>
        <li>頭肩底完成</li>
        <li>三重底確認</li>
      </ul>
    </div>
    <div class="guide-card" style="background:#f0fff0;border-color:#33cc33;">
      <h4 style="color:#33cc33;">📈 買入（65–79% 信心）</h4>
      <ul style="color:#2a7a2a;">
        <li>上升旗形突破</li>
        <li>倒頭肩型完成</li>
        <li>上升三角形突破</li>
        <li>下降楔形向上突破</li>
        <li>均線多頭排列</li>
      </ul>
    </div>
    <div class="guide-card" style="background:#fff8e6;border-color:#e6a800;">
      <h4 style="color:#a07000;">⏳ 等待（50% 信心）</h4>
      <ul style="color:#a07000;">
        <li>三角收斂（方向未定）</li>
        <li>箱型盤整中</li>
        <li>擴散三角形</li>
        <li>上升通道中段</li>
        <li>KD 糾纏無方向</li>
      </ul>
    </div>
    <div class="guide-card" style="background:#fff0f0;border-color:#ff3333;">
      <h4 style="color:#cc0000;">📉 賣出（65–79% 信心）</h4>
      <ul style="color:#cc0000;">
        <li>下跌旗形確認</li>
        <li>上升楔形向下跌破</li>
        <li>均線空頭排列</li>
        <li>M頭頸線跌破</li>
        <li>三重頂確認</li>
      </ul>
    </div>
    <div class="guide-card" style="background:#ffe6e6;border-color:#cc0000;">
      <h4 style="color:#cc0000;">💣 必賣（80–100% 信心）</h4>
      <ul style="color:#cc0000;">
        <li>KD 死亡交叉 ＋ K&gt;80 超買</li>
        <li>M頭（雙頂）完成</li>
        <li>菱形頂突破</li>
        <li>倒V型反轉</li>
        <li>三重頂確認</li>
      </ul>
    </div>
    <div class="guide-card" style="background:#f5f0ff;border-color:#8844cc;">
      <h4 style="color:#6622aa;">📊 KD 線判讀</h4>
      <ul style="color:#6622aa;">
        <li>K&lt;20 超賣區（低點）</li>
        <li>K&gt;80 超買區（高點）</li>
        <li>K線上穿D線 = 黃金交叉↑</li>
        <li>K線下穿D線 = 死亡交叉↓</li>
        <li>MA5&gt;MA10&gt;MA20 多頭</li>
      </ul>
    </div>
  </div>
  <div class="guide-kd">
    <span class="kd-tag" style="background:#e6ffe6;color:#006600;">✅ 賣出警告 100% → M頭防範暴跌</span>
    <span class="kd-tag" style="background:#f0fff0;color:#228822;">📉 80% → 下跌旗形趕快賣出</span>
    <span class="kd-tag" style="background:#fff8e6;color:#a07000;">⚠️ 65% → 菱形頂緩慢下跌</span>
    <span class="kd-tag" style="background:#e6f0ff;color:#1a73e8;">🔄 50% → 箱型盤整危險別碰</span>
    <span class="kd-tag" style="background:#f0fff0;color:#228822;">📈 65% → W底趕緊買入</span>
    <span class="kd-tag" style="background:#e6ffe6;color:#006600;">🚀 80–100% → 上升旗形/頭肩底迎接暴漲</span>
  </div>
</div>

<!-- ④ 主內容 -->
<div class="container">

  <!-- 市場新聞 -->
  <div class="news-section">
    <h3>📰 本週市場焦點新聞</h3>
    {% for n in market_news %}
    <div class="news-item">
      <a href="{{ n.link }}" target="_blank">{{ n.title }}</a>
      <div class="news-source">{{ n.source }} ｜ {{ n.published[:16] if n.published else '' }}</div>
    </div>
    {% endfor %}
    {% if not market_news %}<p style="color:#999;font-size:.85rem;">暫無新聞資料</p>{% endif %}
  </div>

  <!-- 各分類股票 -->
  {% for cat in ['必買','買入','等待','賣出','必賣'] %}
  {% set cat_stocks = results | selectattr('category','equalto',cat) | list %}
  {% if cat_stocks %}
  {% set cfg = categories[cat] %}
  <div class="section-title" style="color:{{cfg.color}};border-color:{{cfg.color}};background:{{cfg.bg}}">
    {{ cfg.icon }} {{ cat }} — {{ cat_stocks|length }} 檔
  </div>
  <div class="cards">
    {% for s in cat_stocks %}
    <div class="card" style="border-color:{{cfg.color}}">
      <div class="card-header">
        <div>
          <div class="stock-name">{{ s.name }}</div>
          <div class="stock-symbol">{{ s.symbol }} ｜ {{ s.industry }}</div>
        </div>
        <div style="text-align:right;">
          {% if s.price %}
          <div class="price" style="color:{{cfg.color}}">{{ s.price }}</div>
          <div class="change {{'up' if s.change_pct>=0 else 'down'}}">
            {{ '+' if s.change_pct>=0 else '' }}{{ s.change_pct }}%
          </div>
          {% else %}
          <div class="price" style="color:#999;">N/A</div>
          {% endif %}
        </div>
      </div>

      <div style="margin:.3rem 0;">
        <span class="pattern-badge" style="background:{{cfg.bg}};color:{{cfg.color}};border:1px solid {{cfg.border}}">
          📐 {{ s.pattern }}
        </span>
        {% if s.gold_cross %}
        <span class="cross-tag">🟡 KD黃金交叉</span>
        {% elif s.death_cross %}
        <span class="cross-tag" style="background:#f8d7da;color:#842029;">⚫ KD死亡交叉</span>
        {% endif %}
      </div>

      <div class="kd-row">
        <div class="kd-item">K值 <span style="color:{{cfg.color}}">{{ s.k_value }}</span></div>
        <div class="kd-item">D值 <span style="color:{{cfg.color}}">{{ s.d_value }}</span></div>
        <div class="kd-item">信心 <span>{{ s.confidence }}%</span></div>
      </div>
      <div class="confidence-bar">
        <div class="confidence-fill" style="width:{{s.confidence}}%;background:{{cfg.color}};"></div>
      </div>
      <div class="ma-row">
        <span>MA5: <b>{{ s.ma5 }}</b></span>
        <span>MA10: <b>{{ s.ma10 }}</b></span>
        <span>MA20: <b>{{ s.ma20 }}</b></span>
      </div>

      {% if s.kd_history and s.kd_history.dates %}
      <div class="chart-wrap">
        <canvas id="chart_{{ loop.index }}_{{ cat|replace('必','must')|replace('買','buy')|replace('入','in')|replace('賣','sell')|replace('出','out')|replace('等待','wait') }}"></canvas>
      </div>
      {% endif %}

      {% if s.symbol in company_news and company_news[s.symbol] %}
      <div style="margin-top:.6rem;font-size:.77rem;border-top:1px solid #eee;padding-top:.45rem;">
        <b>相關新聞：</b>
        {% for n in company_news[s.symbol][:2] %}
        <div style="margin-top:.25rem;">
          <a href="{{ n.link }}" target="_blank" style="color:#1a73e8;text-decoration:none;">
            {{ n.title[:55] }}{% if n.title|length > 55 %}...{% endif %}
          </a>
        </div>
        {% endfor %}
      </div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
  {% endif %}
  {% endfor %}

</div>

<footer>
  本報告由自動化程式依技術分析產生，僅供參考，不構成投資建議。<br>
  資料來源：Yahoo Finance ｜ 分析時間：{{ generated_at }}
</footer>

</div><!-- /#main-body -->

<!-- ── Scripts ── -->
<script>
// ── 圖表 ────────────────────────────────────────
const chartData = {{ chart_data_json }};
chartData.forEach(function(item){
  const canvas = document.getElementById(item.id);
  if(!canvas || !item.data || !item.data.dates || !item.data.dates.length) return;
  new Chart(canvas,{
    type:'line',
    data:{
      labels: item.data.dates,
      datasets:[
        {label:'K值',data:item.data.k,borderColor:'#e67e00',backgroundColor:'transparent',
         borderWidth:1.5,pointRadius:0,tension:.3},
        {label:'D值',data:item.data.d,borderColor:'#0066cc',backgroundColor:'transparent',
         borderWidth:1.5,pointRadius:0,tension:.3}
      ]
    },
    options:{
      responsive:true,maintainAspectRatio:false,
      plugins:{
        legend:{display:true,position:'top',labels:{font:{size:10},boxWidth:14}},
        tooltip:{mode:'index',intersect:false}
      },
      scales:{
        x:{ticks:{maxTicksLimit:6,font:{size:9}},grid:{display:false}},
        y:{min:0,max:100,ticks:{stepSize:20,font:{size:9}},grid:{color:'rgba(0,0,0,.05)'}}
      },
      animation:{duration:400}
    }
  });
});

// ── 自選股管理 ────────────────────────────────────
const API = 'http://localhost:8899';

// 目前報告中已有的股票（從伺服器 config 取得，預設顯示此份報告的）
const reportStocks = {{ current_stocks_json }};

let pendingStocks = JSON.parse(localStorage.getItem('tw_pending_stocks') || '[]');

function renderStocks(configStocks){
  const list = document.getElementById('stocks-list');
  list.innerHTML = '';

  // 已分析的股票（本報告）
  configStocks.forEach(function(s){
    const tag = document.createElement('span');
    tag.className = 'stock-tag';
    tag.innerHTML = '<b>'+s.name+'</b>&nbsp;<span style="color:#888">'+s.symbol+'</span>'
      +'<span class="remove" title="移除" onclick="removeStock(\''+s.symbol+'\')">×</span>';
    list.appendChild(tag);
  });

  // 待加入（localStorage 中但尚未重新分析）
  pendingStocks.forEach(function(s){
    const tag = document.createElement('span');
    tag.className = 'stock-tag new-tag';
    tag.innerHTML = '＋<b>'+s.name+'</b>&nbsp;<span>'+s.symbol+'</span>'
      +'<span class="remove" title="取消" onclick="removePending(\''+s.symbol+'\')">×</span>';
    list.appendChild(tag);
  });

  const btn = document.getElementById('btn-run');
  btn.disabled = false;
}

function showMsg(text, type){
  const el = document.getElementById('manager-msg');
  el.textContent = text;
  el.className = type;
  setTimeout(function(){ el.className=''; el.style.display='none'; }, 4000);
}

function addStock(){
  const sym  = document.getElementById('inp-symbol').value.trim().toUpperCase();
  const name = document.getElementById('inp-name').value.trim();
  const ind  = document.getElementById('inp-industry').value;
  if(!sym || !name){ showMsg('請填入代號與公司名稱','err'); return; }

  const symbol = sym.includes('.') ? sym : sym+'.TW';
  const all = reportStocks.map(function(s){return s.symbol;})
    .concat(pendingStocks.map(function(s){return s.symbol;}));
  if(all.indexOf(symbol)!==-1){ showMsg(name+' 已在清單中','err'); return; }

  pendingStocks.push({name:name,symbol:symbol,industry:ind});
  localStorage.setItem('tw_pending_stocks', JSON.stringify(pendingStocks));
  document.getElementById('inp-symbol').value='';
  document.getElementById('inp-name').value='';
  renderStocks(reportStocks);
  showMsg('已加入 '+name+'，請點「重新分析」更新報告','ok');
}

function removePending(symbol){
  pendingStocks = pendingStocks.filter(function(s){return s.symbol!==symbol;});
  localStorage.setItem('tw_pending_stocks', JSON.stringify(pendingStocks));
  renderStocks(reportStocks);
}

function removeStock(symbol){
  fetch(API+'/api/remove-stock', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({symbol:symbol})
  }).then(function(r){ return r.json(); })
    .then(function(d){
      if(d.ok){ showMsg('已移除，點「重新分析」套用','info'); }
      else     { showMsg('移除失敗: '+d.error,'err'); }
    }).catch(function(){
      showMsg('伺服器未啟動，請執行 uv run server.py','err');
    });
}

function runAnalysis(){
  const btn = document.getElementById('btn-run');
  btn.disabled = true;
  btn.textContent = '分析中...';
  showMsg('正在重新分析，請稍候（約20秒）...','info');

  // 先把 pending stocks 推給伺服器
  const addPromises = pendingStocks.map(function(s){
    return fetch(API+'/api/add-stock',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify(s)
    }).then(function(r){return r.json();});
  });

  Promise.all(addPromises).then(function(){
    pendingStocks=[];
    localStorage.removeItem('tw_pending_stocks');
    return fetch(API+'/api/run',{method:'POST'});
  }).then(function(r){return r.json();})
    .then(function(d){
      if(d.ok){
        showMsg('分析完成！3秒後重新整理頁面...','ok');
        setTimeout(function(){ window.location.reload(); },3000);
      } else {
        btn.disabled=false; btn.textContent='🔄 重新分析';
        showMsg('執行失敗: '+d.error,'err');
      }
    }).catch(function(){
      btn.disabled=false; btn.textContent='🔄 重新分析';
      showMsg('⚠️ 請先執行 uv run server.py 啟動本機伺服器','err');
    });
}

// 初始化
(function(){
  if(typeof reportStocks !== 'undefined') renderStocks(reportStocks);
})();
</script>
</body>
</html>"""


def _sha256_hex(text: str) -> str:
    """Python 端計算 SHA-256（與前端 Web Crypto API 相同結果）"""
    import hashlib
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def generate_report(results: list, news: dict, config: dict, password: str = "") -> str:
    output_dir = config.get('output_dir', 'output')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'index.html')
    # 若未指定密碼，從 config 讀取；若無設定則不鎖定
    if not password:
        password = config.get('password', '')

    now = datetime.now()
    week_label = f"{now.year} 年第 {now.isocalendar()[1]} 週（{now.strftime('%m/%d')}）"
    generated_at = now.strftime('%Y-%m-%d %H:%M')

    cat_counts = {k: 0 for k in CATEGORY_CONFIG}
    for r in results:
        cat = r.get('category', '等待')
        if cat in cat_counts:
            cat_counts[cat] += 1

    # Chart.js 資料
    chart_data = []
    cat_idx = {}
    for cat in ['必買','買入','等待','賣出','必賣']:
        cat_idx[cat] = 0
    for s in results:
        cat = s.get('category', '等待')
        cat_idx[cat] = cat_idx.get(cat, 0) + 1
        slug = (cat.replace('必','must').replace('買','buy').replace('入','in')
                   .replace('賣','sell').replace('出','out').replace('等待','wait'))
        canvas_id = f"chart_{cat_idx[cat]}_{slug}"
        chart_data.append({"id": canvas_id, "data": s.get('kd_history', {}),
                           "color": CATEGORY_CONFIG.get(cat, {}).get('color', '#888')})

    # 目前設定的股票（給 JS 用）
    current_stocks = [{"name": c["name"], "symbol": c["symbol"], "industry": c["industry"]}
                      for c in config.get('companies', [])]

    password_hash = _sha256_hex(password) if password else ""

    tmpl = Template(HTML_TEMPLATE)
    html = tmpl.render(
        title               = config.get('report_title', '台股技術分析週報'),
        week_label          = week_label,
        generated_at        = generated_at,
        categories          = CATEGORY_CONFIG,
        cat_counts          = cat_counts,
        results             = results,
        market_news         = news.get('market', []),
        company_news        = news.get('company', {}),
        chart_data_json     = json.dumps(chart_data, ensure_ascii=False),
        current_stocks_json = json.dumps(current_stocks, ensure_ascii=False),
        password_hash       = password_hash,
    )

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path
