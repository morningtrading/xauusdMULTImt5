"""
================================================================================
WEB DASHBOARD - Donchian Trading Engine (Port 8082)
================================================================================
Shows Donchian Channel values (upper/mid/lower) instead of EMAs.
================================================================================
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict
from pathlib import Path
from threading import Thread

try:
    from flask import Flask, render_template_string, jsonify, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

logger = logging.getLogger('DonchianDashboard')

app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Reference to engine instance
_engine = None

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Donchian Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a0a2e 0%, #1a0a3e 35%, #2d1b69 100%);
            min-height: 100vh; color: #e4e4e4; padding: 20px;
        }
        .header {
            text-align: center; padding: 20px; margin-bottom: 30px;
            background: rgba(255,255,255,0.05); border-radius: 15px;
        }
        .header h1 {
            font-size: 2.2em;
            background: linear-gradient(90deg, #ff6b35, #f7c948);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        }
        .header .status { font-size: 1.1em; color: #888; margin-top: 8px; }
        .status-dot {
            display: inline-block; width: 10px; height: 10px;
            border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite;
        }
        .status-on { background: #00ff88; }
        .status-off { background: #ff4444; }
        .market-open { color: #00ff88; font-weight: bold; }
        .market-closed { color: #ff4444; font-weight: bold; }
        .countdown { font-family: monospace; color: #ffaa00; font-size: 0.9em; }
        @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:0.5;} }
        .grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 20px; margin-bottom: 30px;
        }
        .card {
            background: rgba(255,255,255,0.06); border-radius: 14px;
            padding: 18px; border: 1px solid rgba(255,255,255,0.1);
        }
        .card h2 { font-size: 1.2em; margin-bottom: 12px; color: #f7c948; }
        .metric { display: flex; justify-content: space-between; padding: 6px 0;
                   border-bottom: 1px solid rgba(255,255,255,0.05); }
        .metric-label { color: #aaa; }
        .metric-value { font-weight: bold; }
        .positive { color: #00ff88; }
        .negative { color: #ff4444; }
        .neutral { color: #ffaa00; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px 10px; text-align: left;
                 border-bottom: 1px solid rgba(255,255,255,0.08); }
        th { color: #f7c948; font-size: 0.85em; text-transform: uppercase; }
        .channel-bar {
            height: 6px; background: rgba(255,255,255,0.1); border-radius: 3px;
            position: relative; margin: 4px 0;
        }
        .channel-pos {
            height: 6px; border-radius: 3px; position: absolute; top: 0;
        }
        .ch-upper { background: #ff6b35; }
        .ch-lower { background: #4ecdc4; }
        .btn {
            padding: 8px 16px; border: none; border-radius: 8px; cursor: pointer;
            font-size: 0.9em; margin: 4px; transition: all 0.2s;
        }
        .btn-green { background: #00aa55; color: white; }
        .btn-red { background: #cc3333; color: white; }
        .btn-yellow { background: #aa8800; color: white; }
        .btn:hover { opacity: 0.85; transform: scale(1.02); }
        #last-update { color: #666; font-size: 0.85em; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Donchian Channel Engine</h1>
        <div class="status">
            <span class="status-dot" id="status-dot"></span>
            <span id="status-text">Loading...</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span id="last-update"></span>
        </div>
        <!-- Daily P&L Banner -->
        <div style="margin-top:15px;padding:12px;background:rgba(255,255,255,0.08);border-radius:10px;">
            <div style="display:flex;justify-content:space-around;flex-wrap:wrap;gap:15px;">
                <div style="text-align:center;">
                    <div style="color:#aaa;font-size:0.85em;">Today's P&L</div>
                    <div id="daily-pnl" style="font-size:1.8em;font-weight:bold;" class="positive">$0.00</div>
                </div>
                <div style="text-align:center;">
                    <div style="color:#aaa;font-size:0.85em;">Trades</div>
                    <div id="trades-today" style="font-size:1.5em;font-weight:bold;color:#f7c948">0</div>
                </div>
                <div style="text-align:center;">
                    <div style="color:#aaa;font-size:0.85em;">Win Rate</div>
                    <div id="win-rate" style="font-size:1.5em;font-weight:bold;color:#ffaa00">0%</div>
                </div>
                <div style="text-align:center;">
                    <div style="color:#aaa;font-size:0.85em;">Winners/Losers</div>
                    <div id="win-loss" style="font-size:1.5em;font-weight:bold;"><span class="positive">0</span>/<span class="negative">0</span></div>
                </div>
            </div>
        </div>
        <div class="status" style="margin-top: 10px;">
            <span style="color:#aaa">MT5:</span> 
            <span class="status-dot" id="mt5-status-dot"></span>
            <span id="mt5-status-text">Checking...</span>
            <span style="color:#888;font-size:0.85em" id="mt5-account-info"></span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color:#aaa">Next Check:</span> <span class="countdown" id="mt5-countdown">--s</span>
        </div>
        <div class="status" style="margin-top: 10px;">
            <span style="color:#aaa">Direction:</span> <span id="trading-direction" style="font-weight:bold;color:#f7c948">BOTH</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color:#aaa">Market:</span> <span id="market-status">Checking...</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color:#aaa">Next Scan:</span> <span class="countdown" id="scan-countdown">--:--</span>
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <span style="color:#aaa">Chart Refresh:</span> <span class="countdown" id="chart-countdown">--:--</span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h2>Account</h2>
            <div id="account-info">Loading...</div>
        </div>
        <div class="card">
            <h2>Strategy</h2>
            <div id="strategy-info">Loading...</div>
        </div>
        <div class="card">
            <h2>Controls</h2>
            <div>
                <button class="btn btn-green" onclick="apiCall('/api/trade/enable')">Enable Trading</button>
                <button class="btn btn-red" onclick="apiCall('/api/trade/disable')">Disable Trading</button>
                <button class="btn btn-yellow" onclick="apiCall('/api/trade/freeze')">Freeze</button>
                <button class="btn btn-green" onclick="apiCall('/api/trade/unfreeze')">Unfreeze</button>
            </div>
            <div style="margin-top:10px">
                <button class="btn btn-yellow" onclick="apiCall('/api/direction', 'long')">Long Only</button>
                <button class="btn btn-yellow" onclick="apiCall('/api/direction', 'short')">Short Only</button>
                <button class="btn btn-yellow" onclick="apiCall('/api/direction', 'both')">Both</button>
            </div>
            <div style="margin-top:15px;border-top:1px solid rgba(255,255,255,0.1);padding-top:15px;">
                <button class="btn btn-red" onclick="closeAllPositions()" style="width:100%;font-weight:bold;">⚠ CLOSE ALL POSITIONS</button>
            </div>
        </div>
    </div>

    <div class="card" style="margin-bottom:20px">
        <h2>XAUUSD - Gold Chart with Donchian Channels</h2>
        <div style="margin-bottom:10px">
            <label style="color:#aaa">Bars: </label>
            <select id="chart-bars-gold" onchange="loadCharts()" style="padding:5px;border-radius:5px;background:#333;color:#fff;border:1px solid #555">
                <option value="50">50</option>
                <option value="100" selected>100</option>
                <option value="200">200</option>
                <option value="500">500</option>
            </select>
        </div>
        <div id="price-chart-gold" style="width:100%;height:450px;"></div>
    </div>

    <div class="card" style="margin-bottom:20px">
        <h2>XAGUSD - Silver Chart with Donchian Channels</h2>
        <div style="margin-bottom:10px">
            <label style="color:#aaa">Bars: </label>
            <select id="chart-bars-silver" onchange="loadCharts()" style="padding:5px;border-radius:5px;background:#333;color:#fff;border:1px solid #555">
                <option value="50">50</option>
                <option value="100" selected>100</option>
                <option value="200">200</option>
                <option value="500">500</option>
            </select>
        </div>
        <div id="price-chart-silver" style="width:100%;height:450px;"></div>
    </div>

    <div class="card" style="margin-bottom:20px">
        <h2>Donchian Channels &amp; Signals</h2>
        <table>
            <thead>
                <tr>
                    <th>Symbol</th><th>TF</th><th>Price</th><th>Upper</th><th>Mid</th><th>Lower</th>
                    <th>Width%</th><th>Signal</th><th>Strength</th>
                </tr>
            </thead>
            <tbody id="channels-table"></tbody>
        </table>
    </div>

    <div class="card" style="margin-bottom:20px">
        <h2>Open Positions</h2>
        <table>
            <thead>
                <tr><th>Symbol</th><th>Type</th><th>Volume</th><th>Entry</th><th>Current</th><th>Duration</th><th>P&L</th><th>P&L %</th></tr>
            </thead>
            <tbody id="positions-table"></tbody>
        </table>
    </div>

    <div class="card">
        <h2>Trade History (Last 20)</h2>
        <table>
            <thead>
                <tr><th>Time</th><th>Symbol</th><th>Type</th><th>Volume</th><th>Price</th><th>P&L</th></tr>
            </thead>
            <tbody id="history-table"></tbody>
        </table>
    </div>

    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script>
    function fmt(v, d) { return v != null ? Number(v).toFixed(d || 2) : '-'; }
    function cls(v) { return v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral'; }
    
    // Countdown timers
    let scanCountdown = 2;  // Status refresh every 2 seconds
    let chartCountdown = 120;  // Chart refresh every 120 seconds
    let mt5Countdown = 30;  // MT5 check countdown (updated from server)
    
    function updateCountdowns() {
        scanCountdown--;
        chartCountdown--;
        
        if (scanCountdown <= 0) scanCountdown = 2;
        if (chartCountdown <= 0) chartCountdown = 120;
        
        document.getElementById('scan-countdown').textContent = scanCountdown + 's';
        
        let chartMins = Math.floor(chartCountdown / 60);
        let chartSecs = chartCountdown % 60;
        document.getElementById('chart-countdown').textContent = 
            chartMins + ':' + (chartSecs < 10 ? '0' : '') + chartSecs;
    }
    
    function checkMarketStatus() {
        let now = new Date();
        let dayOfWeek = now.getUTCDay();  // 0=Sunday, 6=Saturday
        let hourUTC = now.getUTCHours();
        
        // XAUUSD trading hours: Sunday 22:00 UTC - Friday 22:00 UTC
        let isOpen = false;
        
        if (dayOfWeek === 0) {  // Sunday
            isOpen = hourUTC >= 22;
        } else if (dayOfWeek >= 1 && dayOfWeek <= 4) {  // Monday-Thursday
            isOpen = true;
        } else if (dayOfWeek === 5) {  // Friday
            isOpen = hourUTC < 22;
        } else if (dayOfWeek === 6) {  // Saturday
            isOpen = false;
        }
        
        let statusEl = document.getElementById('market-status');
        if (isOpen) {
            statusEl.innerHTML = '<span class="market-open">OPEN</span>';
        } else {
            statusEl.innerHTML = '<span class="market-closed">CLOSED</span>';
        }
    }

    function apiCall(url, data) {
        fetch(url, {method:'POST', headers:{'Content-Type':'application/json'},
                     body: data ? JSON.stringify({value:data}) : '{}'})
        .then(r=>r.json()).then(d=>console.log(d));
    }
    
    function closeAllPositions() {
        if (confirm('⚠️ Are you sure you want to CLOSE ALL POSITIONS? This cannot be undone!')) {
            fetch('/api/close_all', {method:'POST', headers:{'Content-Type':'application/json'}})
            .then(r=>r.json())
            .then(d => {
                alert('Result: Closed ' + (d.closed || 0) + ' positions. Failed: ' + (d.failed || 0));
                refresh();
            })
            .catch(e => alert('Error: ' + e));
        }
    }

    function refresh() {
        fetch('/api/status').then(r=>r.json()).then(data => {
            // Engine Status
            let eng = data.engine_status || {};
            let dot = document.getElementById('status-dot');
            let txt = document.getElementById('status-text');
            dot.className = 'status-dot ' + (eng.running ? 'status-on' : 'status-off');
            txt.textContent = eng.running ? 'RUNNING' : 'STOPPED';
            document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
            
            // MT5 Connection Status
            let conn = data.connection_status || {};
            let mt5Dot = document.getElementById('mt5-status-dot');
            let mt5Txt = document.getElementById('mt5-status-text');
            mt5Dot.className = 'status-dot ' + (conn.mt5_connected ? 'status-on' : 'status-off');
            mt5Txt.textContent = conn.mt5_status || 'Unknown';
            
            // MT5 Account Info
            let mt5Account = document.getElementById('mt5-account-info');
            if (conn.mt5_connected && conn.mt5_account) {
                let accountType = conn.is_demo ? 'DEMO' : 'LIVE';
                mt5Account.textContent = ' (' + accountType + ' - ' + conn.mt5_server + ')';
            } else {
                mt5Account.textContent = '';
            }
            
            // MT5 Check Countdown
            mt5Countdown = conn.next_check_seconds || 30;
            document.getElementById('mt5-countdown').textContent = mt5Countdown + 's';
            
            // Trading Direction
            let direction = (data.strategy_status || {}).direction || 'both';
            document.getElementById('trading-direction').textContent = direction.toUpperCase();
            
            // Daily P&L Banner
            let pnl = data.daily_pnl || {};
            let pnlEl = document.getElementById('daily-pnl');
            pnlEl.textContent = '$' + fmt(pnl.today);
            pnlEl.className = cls(pnl.today);
            document.getElementById('trades-today').textContent = pnl.trades_today || 0;
            document.getElementById('win-rate').textContent = fmt(pnl.win_rate, 1) + '%';
            document.getElementById('win-loss').innerHTML = 
                '<span class="positive">' + (pnl.winners || 0) + '</span>/<span class="negative">' + (pnl.losers || 0) + '</span>';

            // Account
            let acc = data.account_info || {};
            document.getElementById('account-info').innerHTML =
                '<div class="metric"><span class="metric-label">Balance</span><span class="metric-value">$'+fmt(acc.balance)+'</span></div>' +
                '<div class="metric"><span class="metric-label">Equity</span><span class="metric-value">$'+fmt(acc.equity)+'</span></div>' +
                '<div class="metric"><span class="metric-label">Margin</span><span class="metric-value">$'+fmt(acc.margin)+'</span></div>';

            // Strategy
            let strat = data.strategy_status || {};
            let symbolTFs = strat.symbol_timeframes || {};
            let tfDisplay = Object.keys(symbolTFs).length > 0 ? 
                Object.entries(symbolTFs).map(([sym, tf]) => sym + ':' + tf).join(', ') : '-';
            document.getElementById('strategy-info').innerHTML =
                '<div class="metric"><span class="metric-label">Type</span><span class="metric-value" style="color:#f7c948">DONCHIAN</span></div>' +
                '<div class="metric"><span class="metric-label">Period</span><span class="metric-value">'+fmt(strat.channel_period,0)+'</span></div>' +
                '<div class="metric"><span class="metric-label">Direction</span><span class="metric-value">'+(strat.direction||'-').toUpperCase()+'</span></div>' +
                '<div class="metric"><span class="metric-label">Timeframes</span><span class="metric-value" style="font-size:0.85em">'+tfDisplay+'</span></div>' +
                '<div class="metric"><span class="metric-label">Trading</span><span class="metric-value '+(strat.trading_enabled?'positive':'negative')+'">'+
                (strat.trading_enabled?'ENABLED':'DISABLED')+'</span></div>';

            // Channels
            let sigs = data.last_signals || {};
            let chans = data.channel_values || {};
            // Reuse symbolTFs from above
            let tbody = document.getElementById('channels-table');
            tbody.innerHTML = '';
            for (let sym in sigs) {
                let s = sigs[sym];
                let c = chans[sym] || {};
                let tf = symbolTFs[sym] || '-';
                let widthPct = c.lower > 0 ? ((c.upper - c.lower)/c.lower*100) : 0;
                let sigCls = (s.action=='BUY'||s.action=='EXIT_SHORT') ? 'positive' :
                             (s.action=='SELL'||s.action=='EXIT_LONG') ? 'negative' : '';
                tbody.innerHTML +=
                    '<tr><td><b>'+sym+'</b></td>' +
                    '<td style="color:#ffaa00"><b>'+tf+'</b></td>' +
                    '<td>'+fmt(s.price,5)+'</td>' +
                    '<td style="color:#ff6b35">'+fmt(c.upper,5)+'</td>' +
                    '<td style="color:#aaa">'+fmt(c.mid,5)+'</td>' +
                    '<td style="color:#4ecdc4">'+fmt(c.lower,5)+'</td>' +
                    '<td>'+fmt(widthPct,2)+'%</td>' +
                    '<td class="'+sigCls+'"><b>'+s.action+'</b></td>' +
                    '<td>'+fmt(s.strength,2)+'</td></tr>';
            }

            // Positions
            let pos = data.positions || [];
            let ptbody = document.getElementById('positions-table');
            ptbody.innerHTML = '';
            if (pos.length === 0) {
                ptbody.innerHTML = '<tr><td colspan="8" style="color:#666">No open positions</td></tr>';
            }
            for (let p of pos) {
                let duration = p.duration_hours || 0;
                let durStr = duration < 1 ? fmt(duration * 60, 0) + 'm' : fmt(duration, 1) + 'h';
                ptbody.innerHTML +=
                    '<tr><td><b>'+p.symbol+'</b></td><td>'+(p.type==0?'LONG':'SHORT')+'</td>' +
                    '<td>'+fmt(p.volume,2)+'</td><td>'+fmt(p.price_open,5)+'</td>' +
                    '<td>'+fmt(p.price_current,5)+'</td><td>'+durStr+'</td>' +
                    '<td class="'+cls(p.profit)+'">'+fmt(p.profit)+'</td>' +
                    '<td class="'+cls(p.pnl_percent)+'">'+fmt(p.pnl_percent,2)+'%</td></tr>';
            }
            
            // Trade History
            let history = data.trade_history || [];
            let htbody = document.getElementById('history-table');
            htbody.innerHTML = '';
            if (history.length === 0) {
                htbody.innerHTML = '<tr><td colspan="6" style="color:#666">No trade history</td></tr>';
            }
            for (let h of history) {
                let tradeType = h.type == 0 ? 'BUY' : 'SELL';
                let timeStr = new Date(h.time).toLocaleString();
                htbody.innerHTML +=
                    '<tr><td style="font-size:0.85em">'+timeStr+'</td>' +
                    '<td><b>'+h.symbol+'</b></td><td>'+tradeType+'</td>' +
                    '<td>'+fmt(h.volume,2)+'</td><td>'+fmt(h.price,5)+'</td>' +
                    '<td class="'+cls(h.profit)+'">'+fmt(h.profit)+'</td></tr>';
            }
        }).catch(e => console.error('Refresh error:', e));
    }

    function loadSingleChart(symbol, chartDivId, bars) {
        fetch('/api/chart_data/'+symbol+'?bars='+bars)
        .then(r=>r.json())
        .then(data => {
            if (!data.times || data.times.length === 0) {
                document.getElementById(chartDivId).innerHTML = '<div style="color:#888;padding:20px;text-align:center">No chart data available</div>';
                return;
            }
            
            // Candlestick trace
            let candlestick = {
                x: data.times,
                open: data.open,
                high: data.high,
                low: data.low,
                close: data.close,
                type: 'candlestick',
                name: symbol,
                increasing: {line: {color: '#00ff88'}},
                decreasing: {line: {color: '#ff4444'}}
            };
            
            // Upper channel
            let upperChannel = {
                x: data.times,
                y: data.upper,
                type: 'scatter',
                mode: 'lines',
                name: 'Upper Channel',
                line: {color: '#ff6b35', width: 2}
            };
            
            // Mid channel
            let midChannel = {
                x: data.times,
                y: data.mid,
                type: 'scatter',
                mode: 'lines',
                name: 'Mid Channel',
                line: {color: '#ffaa00', width: 1, dash: 'dot'}
            };
            
            // Lower channel
            let lowerChannel = {
                x: data.times,
                y: data.lower,
                type: 'scatter',
                mode: 'lines',
                name: 'Lower Channel',
                line: {color: '#4ecdc4', width: 2}
            };
            
            // Layout
            let layout = {
                title: {
                    text: symbol + ' - Donchian Channel (Period: ' + data.period + ', TF: ' + data.timeframe + ')',
                    font: {color: '#f7c948', size: 16}
                },
                xaxis: {
                    type: 'date',
                    gridcolor: 'rgba(255,255,255,0.1)',
                    color: '#aaa',
                    rangebreaks: [
                        {bounds: ['sat', 'mon']},  // Hide weekends
                    ]
                },
                yaxis: {
                    title: 'Price',
                    gridcolor: 'rgba(255,255,255,0.1)',
                    color: '#aaa'
                },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0.3)',
                font: {color: '#e4e4e4'},
                showlegend: true,
                legend: {
                    x: 0,
                    y: 1,
                    bgcolor: 'rgba(0,0,0,0.3)',
                    font: {color: '#e4e4e4'}
                },
                margin: {l: 50, r: 20, t: 50, b: 50}
            };
            
            let config = {
                responsive: true,
                displayModeBar: true,
                displaylogo: false
            };
            
            Plotly.newPlot(chartDivId, [candlestick, upperChannel, midChannel, lowerChannel], layout, config);
        })
        .catch(e => {
            console.error('Chart load error for ' + symbol + ':', e);
            document.getElementById(chartDivId).innerHTML = '<div style="color:#ff4444;padding:20px;text-align:center">Error loading chart</div>';
        });
    }
    
    function loadCharts() {
        let barsGold = document.getElementById('chart-bars-gold').value;
        let barsSilver = document.getElementById('chart-bars-silver').value;
        loadSingleChart('XAUUSD', 'price-chart-gold', barsGold);
        loadSingleChart('XAGUSD', 'price-chart-silver', barsSilver);
    }

    setInterval(refresh, 2000);  // Status refresh every 2 seconds
    setInterval(loadCharts, 120000);  // Chart refresh every 2 minutes
    setInterval(updateCountdowns, 1000);  // Update countdowns every second
    setInterval(checkMarketStatus, 30000);  // Check market status every 30 seconds
    
    refresh();
    loadCharts();
    updateCountdowns();
    checkMarketStatus();
    </script>
</body>
</html>
"""


def clean_nans(data):
    if isinstance(data, dict):
        return {k: clean_nans(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_nans(v) for v in data]
    elif isinstance(data, float):
        if data != data or data == float('inf') or data == float('-inf'):
            return None
    return data


@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/status')
def api_status():
    if _engine is None:
        return jsonify({'error': 'Engine not initialized'})
    with _engine.dashboard_lock:
        data = clean_nans(dict(_engine.dashboard_data))
    return jsonify(data)


@app.route('/api/trade/enable', methods=['POST'])
def trade_enable():
    if _engine:
        _engine.strategy.set_trading_enabled(True)
        _engine.trading_enabled = True
    return jsonify({'status': 'ok', 'trading': True})


@app.route('/api/trade/disable', methods=['POST'])
def trade_disable():
    if _engine:
        _engine.strategy.set_trading_enabled(False)
        _engine.trading_enabled = False
    return jsonify({'status': 'ok', 'trading': False})


@app.route('/api/trade/freeze', methods=['POST'])
def trade_freeze():
    if _engine:
        _engine.position_manager.trading_frozen = True
        _engine.position_manager.freeze_reason = "Manual freeze from dashboard"
    return jsonify({'status': 'ok', 'frozen': True})


@app.route('/api/trade/unfreeze', methods=['POST'])
def trade_unfreeze():
    if _engine:
        _engine.position_manager.trading_frozen = False
        _engine.position_manager.freeze_reason = None
    return jsonify({'status': 'ok', 'frozen': False})


@app.route('/api/direction', methods=['POST'])
def set_direction():
    data = request.get_json() or {}
    direction = data.get('value', 'both')
    if _engine:
        _engine.strategy.set_direction(direction)
        _engine.direction = direction
    return jsonify({'status': 'ok', 'direction': direction})


@app.route('/api/close_all', methods=['POST'])
def close_all():
    """Close all open positions (panic button)"""
    if _engine:
        result = _engine.close_all_positions()
        return jsonify(result)
    return jsonify({'success': False, 'error': 'Engine not initialized'})


@app.route('/api/chart_data/<symbol>')
def chart_data(symbol):
    """Get historical price data with Donchian channels for charting"""
    if _engine is None:
        return jsonify({'error': 'Engine not initialized'})
    
    try:
        # Get number of bars from query param
        bars_count = int(request.args.get('bars', 100))
        
        # Get symbol's timeframe and period
        timeframe = _engine._get_timeframe_for_symbol(symbol)
        period = _engine.strategy.get_symbol_settings(symbol)
        
        # Fetch historical data
        bars = _engine.mt5.get_rates(symbol, timeframe, bars_count + period)
        if not bars:
            return jsonify({'error': 'No data available', 'times': [], 'open': [], 'high': [], 'low': [], 'close': [], 'upper': [], 'mid': [], 'lower': [], 'period': period})
        
        # Filter out weekend bars and extract OHLC data
        filtered_bars = []
        for bar in bars:
            bar_time = bar['time']
            # Skip weekends (Saturday=5, Sunday=6)
            if hasattr(bar_time, 'weekday'):
                if bar_time.weekday() in [5, 6]:  # Saturday or Sunday
                    continue
            filtered_bars.append(bar)
        
        if not filtered_bars:
            return jsonify({'error': 'No trading data after filtering weekends', 'times': [], 'open': [], 'high': [], 'low': [], 'close': [], 'upper': [], 'mid': [], 'lower': [], 'period': period})
        
        times = [bar['time'].isoformat() if hasattr(bar['time'], 'isoformat') else str(bar['time']) for bar in filtered_bars]
        opens = [float(bar['open']) for bar in filtered_bars]
        highs = [float(bar['high']) for bar in filtered_bars]
        lows = [float(bar['low']) for bar in filtered_bars]
        closes = [float(bar['close']) for bar in filtered_bars]
        
        # Calculate Donchian channels on filtered data
        upper = []
        lower = []
        mid = []
        
        for i in range(len(filtered_bars)):
            if i < period:
                upper.append(None)
                lower.append(None)
                mid.append(None)
            else:
                # Look back 'period' bars for highest high and lowest low
                high_slice = highs[i-period:i]
                low_slice = lows[i-period:i]
                u = max(high_slice) if high_slice else None
                l = min(low_slice) if low_slice else None
                m = (u + l) / 2.0 if (u is not None and l is not None) else None
                upper.append(u)
                lower.append(l)
                mid.append(m)
        
        return jsonify({
            'times': times,
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'upper': upper,
            'mid': mid,
            'lower': lower,
            'period': period,
            'symbol': symbol,
            'timeframe': timeframe
        })
    except Exception as e:
        logger.error(f"Chart data error for {symbol}: {e}")
        return jsonify({'error': str(e), 'times': [], 'open': [], 'high': [], 'low': [], 'close': [], 'upper': [], 'mid': [], 'lower': [], 'period': 0})


def start_dashboard(engine):
    """Start the Flask dashboard server"""
    global _engine
    _engine = engine

    port = engine.config.get('dashboard', {}).get('port', 8082)
    host = engine.config.get('dashboard', {}).get('host', '0.0.0.0')

    logger.info(f"Starting Donchian Dashboard on {host}:{port}")
    app.run(host=host, port=port, debug=False, use_reloader=False)
