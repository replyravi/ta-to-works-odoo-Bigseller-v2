// ==UserScript==
// @name         BigSeller → Odoo Auto Sync
// @namespace    https://github.com/replyravi/ta-to-works-odoo-Bigseller-v1
// @version      2.2.0
// @description  Fetches ALL BigSeller orders (all statuses, all pages) and pushes to Odoo via JSON-RPC with detailed logging
// @author       RSS (Ravi Singh)
// @match        https://www.bigseller.com/*
// @match        https://bigseller.com/*
// @grant        GM.xmlHttpRequest
// @connect      *
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    // ╔══════════════════════════════════════════════════╗
    // ║  CONFIGURATION — Edit these 4 values            ║
    // ╚══════════════════════════════════════════════════╝
    const ODOO_URL    = 'https://tatov16.odoo.com';
    const ODOO_DB     = 'v-odoo-bkk-tato16-production-8065494';
    const ODOO_USER   = 'bigseller@ta-to.com';
    const ODOO_APIKEY = 'NjEUG5yxJFGw8DE';
    // ────────────────────────────────────────────────────
    const SYNC_INTERVAL_MS = 60 * 1000;
    const ORDER_STATUSES   = ['new', 'shipped', 'completed', 'canceled'];
    const MAX_PAGES        = 300;
    const BATCH_SIZE       = 50;

    let syncInProgress = false;
    let cachedUid = null;

    function log(msg) { console.log('[Odoo Sync] ' + msg); }
    function warn(msg) { console.warn('[Odoo Sync] ' + msg); }

    // ── Floating status badge ──────────────────────────
    const badge = document.createElement('div');
    badge.id = 'odoo-sync-badge';
    Object.assign(badge.style, {
        position: 'fixed', bottom: '20px', right: '20px', zIndex: '99999',
        background: '#2c3e50', color: '#ecf0f1',
        padding: '10px 18px', borderRadius: '10px',
        fontSize: '13px', fontFamily: 'Arial, sans-serif',
        boxShadow: '0 4px 14px rgba(0,0,0,0.35)', cursor: 'pointer',
        transition: 'background 0.3s, transform 0.15s',
        userSelect: 'none',
    });
    badge.title = 'Click to sync now';
    badge.addEventListener('mouseenter', function () { badge.style.transform = 'scale(1.05)'; });
    badge.addEventListener('mouseleave', function () { badge.style.transform = 'scale(1)'; });
    document.body.appendChild(badge);

    function ui(text, bg) {
        badge.textContent = text;
        badge.style.background = bg || '#2c3e50';
    }
    ui('\u23F3 Odoo Sync: starting\u2026');

    // ── JSON-RPC helper ──
    function jsonRpc(url, method, params) {
        return new Promise(function (resolve, reject) {
            GM.xmlHttpRequest({
                method: 'POST',
                url: url,
                headers: { 'Content-Type': 'application/json' },
                data: JSON.stringify({
                    jsonrpc: '2.0',
                    method: method,
                    id: Date.now(),
                    params: params,
                }),
                timeout: 300000,
                onload: function (r) {
                    try {
                        var resp = JSON.parse(r.responseText);
                        if (resp.error) {
                            var msg = (resp.error.data && resp.error.data.message)
                                   || resp.error.message
                                   || JSON.stringify(resp.error);
                            reject(new Error(msg));
                        } else {
                            resolve(resp.result);
                        }
                    } catch (_) {
                        reject(new Error('Bad response from Odoo (' + r.status + ')'));
                    }
                },
                onerror: function () { reject(new Error('Cannot reach Odoo at ' + ODOO_URL)); },
                ontimeout: function () { reject(new Error('Odoo request timed out')); },
            });
        });
    }

    async function odooLogin() {
        if (cachedUid) return cachedUid;
        log('Authenticating as ' + ODOO_USER + '...');
        var uid = await jsonRpc(ODOO_URL + '/jsonrpc', 'call', {
            service: 'common',
            method: 'login',
            args: [ODOO_DB, ODOO_USER, ODOO_APIKEY],
        });
        if (!uid) throw new Error('Login failed — check ODOO_USER and ODOO_APIKEY');
        log('Authenticated. uid=' + uid);
        cachedUid = uid;
        return uid;
    }

    async function odooCall(model, method, args, kwargs) {
        var uid = await odooLogin();
        return jsonRpc(ODOO_URL + '/jsonrpc', 'call', {
            service: 'object',
            method: 'execute_kw',
            args: [ODOO_DB, uid, ODOO_APIKEY, model, method, args || [], kwargs || {}],
        });
    }

    // ── Fetch a single page from BigSeller ──
    async function fetchPage(status, pageNo) {
        var resp = await fetch('/api/v1/order/new/pageList.json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'clienttype': '1' },
            body: JSON.stringify({
                status: status,
                searchType: 'orderNo',
                pageNo: pageNo,
                allOrder: false,
                historyOrder: 0,
                packState: '',
                desc: 1,
                orderBy: 'shipTime',
            }),
        });
        var text = await resp.text();
        try {
            return JSON.parse(text);
        } catch (_) {
            warn('Non-JSON response for status=' + status + ' page=' + pageNo);
            return { data: { page: { rows: [], totalSize: 0 } } };
        }
    }

    // ── Extract shop ID from shopName like "MyShop(12345)" ──
    function extractShopId(shopName) {
        var m = (shopName || '').match(/\((\d+)\)\s*$/);
        return m ? m[1] : '';
    }

    // ── Fetch ALL pages for a status + log each order ──
    async function fetchAllPages(status, statusLabel) {
        var firstPage = await fetchPage(status, 1);
        var pageData = ((firstPage.data || {}).page || {});
        var rows = pageData.rows || [];
        var totalSize = pageData.totalSize || 0;

        log(status + ': page 1 returned ' + rows.length + ' orders, totalSize=' + totalSize);

        if (rows.length) {
            logOrders(rows, status);
        }

        if (!rows.length || rows.length >= totalSize) return rows;

        var totalPages = Math.ceil(totalSize / rows.length);
        var pagesToFetch = Math.min(totalPages, MAX_PAGES);

        for (var p = 2; p <= pagesToFetch; p++) {
            ui('\u23F3 ' + statusLabel + ' pg ' + p + '/' + pagesToFetch + ' (' + rows.length + ' so far)', '#f39c12');
            var nextPage = await fetchPage(status, p);
            var nextRows = (((nextPage.data || {}).page || {}).rows) || [];
            if (!nextRows.length) break;
            logOrders(nextRows, status);
            rows = rows.concat(nextRows);
        }
        log(status + ': TOTAL fetched = ' + rows.length + ' orders');
        return rows;
    }

    // ── Log order details to console ──
    function logOrders(rows, status) {
        var shops = {};
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            var orderId = r.platformOrderId || r.id || '?';
            var shop = r.shopName || '?';
            var shopId = extractShopId(shop);
            var state = r.state || status;
            var platform = r.viewPlatfrom || r.platform || '?';
            shops[shop] = (shops[shop] || 0) + 1;
            log('  [' + status + '] #' + orderId + ' | shop=' + shop + ' | shopId=' + shopId + ' | state=' + state + ' | platform=' + platform);
        }
        var shopSummary = [];
        for (var s in shops) { shopSummary.push(s + ':' + shops[s]); }
        log('  Shop breakdown: ' + shopSummary.join(', '));
    }

    // ── Push a batch of orders to Odoo ──
    async function pushBatch(rows, batchNum, totalBatches) {
        var wrapper = { code: 0, data: { page: { rows: rows, totalSize: rows.length } } };
        var jsonStr = JSON.stringify(wrapper);
        log('Pushing batch ' + batchNum + '/' + totalBatches + ' (' + rows.length + ' orders, ' + Math.round(jsonStr.length / 1024) + ' KB)');
        var wizardId = await odooCall('bigseller.json.import', 'create', [{ json_data: jsonStr }]);
        var result = await odooCall('bigseller.json.import', 'action_import', [[wizardId]]);
        return result;
    }

    // ── Parse Odoo result ──
    function parseSyncResult(result) {
        if (!result || typeof result !== 'object') {
            return { message: 'Sync complete (no details)', ok: true };
        }
        var params = result.params || {};
        var message = params.message || '';
        if (result.domain) {
            var ids = [];
            for (var i = 0; i < (result.domain || []).length; i++) {
                var cond = result.domain[i];
                if (Array.isArray(cond) && cond[0] === 'id' && cond[1] === 'in') {
                    ids = cond[2] || [];
                }
            }
            return { message: '+' + ids.length + ' created', created: ids.length, ok: true };
        }
        if (message) {
            return { message: message, ok: params.type !== 'danger' };
        }
        return { message: 'Sync complete', ok: true };
    }

    // ── Main sync loop ─────────────────────────────────
    async function doSync() {
        if (syncInProgress) return;
        syncInProgress = true;
        var startTime = Date.now();
        ui('\u23F3 Syncing\u2026', '#f39c12');
        log('=== SYNC STARTED at ' + new Date().toLocaleTimeString() + ' ===');

        try {
            var allRows = [];
            for (var i = 0; i < ORDER_STATUSES.length; i++) {
                var label = ORDER_STATUSES[i] + ' (' + (i + 1) + '/' + ORDER_STATUSES.length + ')';
                ui('\u23F3 Fetching ' + label + '\u2026', '#f39c12');
                var rows = await fetchAllPages(ORDER_STATUSES[i], label);
                allRows = allRows.concat(rows);
            }

            log('--- FETCH COMPLETE: ' + allRows.length + ' total orders across all statuses ---');

            if (allRows.length === 0) {
                ui('\u2705 No orders found | ' + ts(), '#27ae60');
                log('=== SYNC ENDED (no orders) ===');
                syncInProgress = false;
                return;
            }

            var totalBatches = Math.ceil(allRows.length / BATCH_SIZE);
            var totalCreated = 0;
            var totalMessages = [];
            log('Splitting into ' + totalBatches + ' batches of up to ' + BATCH_SIZE + ' orders each');

            for (var b = 0; b < totalBatches; b++) {
                var chunk = allRows.slice(b * BATCH_SIZE, (b + 1) * BATCH_SIZE);
                ui('\u23F3 Pushing batch ' + (b + 1) + '/' + totalBatches + ' (' + chunk.length + ' orders)\u2026', '#f39c12');
                try {
                    var rawResult = await pushBatch(chunk, b + 1, totalBatches);
                    var info = parseSyncResult(rawResult);
                    log('Batch ' + (b + 1) + ' result: ' + info.message);
                    totalMessages.push(info.message);
                    if (info.created) totalCreated += info.created;
                } catch (batchErr) {
                    warn('Batch ' + (b + 1) + ' FAILED: ' + batchErr.message);
                    totalMessages.push('batch ' + (b + 1) + ' error');
                }
            }

            var elapsed = Math.round((Date.now() - startTime) / 1000);
            var summary = allRows.length + ' orders in ' + elapsed + 's';
            if (totalCreated) summary = '+' + totalCreated + ' new | ' + summary;
            ui('\u2705 ' + summary + ' | ' + ts(), '#27ae60');
            log('=== SYNC COMPLETE: ' + summary + ' ===');
            log('Batch results: ' + totalMessages.join(' | '));

        } catch (err) {
            if (err.message && err.message.indexOf('Login failed') >= 0) {
                cachedUid = null;
            }
            ui('\u274C ' + err.message, '#e74c3c');
            console.error('[Odoo Sync] SYNC FAILED:', err);
        }

        syncInProgress = false;
    }

    function ts() {
        return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    badge.addEventListener('click', doSync);

    if (ODOO_APIKEY === 'PASTE_YOUR_ODOO_PASSWORD_HERE') {
        ui('\u26A0\uFE0F Set ODOO_APIKEY (password) in script!', '#e74c3c');
    } else {
        doSync();
        setInterval(doSync, SYNC_INTERVAL_MS);
    }
})();
