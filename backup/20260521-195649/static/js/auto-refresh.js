/**
 * admin 공통 자동 갱신 유틸 — 화면 깜빡임 없이 변경된 텍스트만 교체.
 *
 * 사용 예시 (dashboard.html 하단):
 *   AutoRefresh.register({
 *     interval: 60000,
 *     fetches: [
 *       { url: '/api/dashboard/summary',  apply: applyKpi   },
 *       { url: '/api/cloud/status',       apply: applyCloud },
 *       { url: '/api/s3/status',          apply: applyS3    },
 *       { url: '/api/dashboard/uploads',  apply: applyUploads },
 *     ],
 *   });
 *
 * - DOM 노드의 textContent / class / style.background 를 비교 후 다를 때만 갱신
 * - 페이지가 백그라운드 탭이면 폴링 중지 (visibilitychange 이벤트)
 * - 네트워크 에러는 console.warn 만 — 사용자 화면에 노출 X
 */
(function (global) {
    'use strict';

    function setText(id, value) {
        var el = document.getElementById(id);
        if (!el) return;
        var next = (value === null || value === undefined) ? '' : String(value);
        if (el.textContent !== next) el.textContent = next;
    }

    function setStyle(id, prop, value) {
        var el = document.getElementById(id);
        if (!el || value === null || value === undefined) return;
        if (el.style[prop] !== value) el.style[prop] = value;
    }

    function replaceTbody(id, rowsHtml) {
        var el = document.getElementById(id);
        if (!el) return;
        if (el.innerHTML !== rowsHtml) el.innerHTML = rowsHtml;
    }

    function escapeHtml(s) {
        if (s === null || s === undefined) return '';
        return String(s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function stampNow(id) {
        var el = document.getElementById(id);
        if (!el) return;
        var d = new Date();
        var hh = String(d.getHours()).padStart(2, '0');
        var mm = String(d.getMinutes()).padStart(2, '0');
        var ss = String(d.getSeconds()).padStart(2, '0');
        var next = '갱신: ' + hh + ':' + mm + ':' + ss;
        if (el.textContent !== next) el.textContent = next;
    }

    var AutoRefresh = {
        setText: setText,
        setStyle: setStyle,
        replaceTbody: replaceTbody,
        escapeHtml: escapeHtml,
        stampNow: stampNow,

        /**
         * SSE 구독 — Wearable 같은 서버 푸시용.
         *   AutoRefresh.subscribe('/stream/wearable', function(data) { ... })
         * - document.hidden 일 때 자동 disconnect, 복귀 시 재연결
         * - 네트워크 끊김은 브라우저가 자동 재연결 (EventSource 기본 동작)
         */
        subscribe: function (url, handler) {
            var es = null;
            function open() {
                if (es) return;
                es = new EventSource(url);
                es.onmessage = function (ev) {
                    try { handler(JSON.parse(ev.data)); } catch (_) {}
                };
            }
            function close() { if (es) { es.close(); es = null; } }
            document.addEventListener('visibilitychange', function () {
                if (document.hidden) close(); else open();
            });
            open();
        },

        register: function (config) {
            var fetches = config.fetches || [];
            var interval = config.interval || 60000;
            var timer = null;
            var inflight = false;

            function tick() {
                if (document.hidden || inflight) return;
                inflight = true;
                Promise.allSettled(fetches.map(function (f) {
                    return fetch(f.url, { credentials: 'same-origin' })
                        .then(function (r) { return r.ok ? r.json() : null; })
                        .then(function (data) { if (data !== null) f.apply(data); });
                })).then(function () { inflight = false; }, function () { inflight = false; });
            }

            function start() {
                if (timer) return;
                timer = setInterval(tick, interval);
            }
            function stop() { if (timer) { clearInterval(timer); timer = null; } }

            document.addEventListener('visibilitychange', function () {
                if (document.hidden) stop(); else { tick(); start(); }
            });
            tick();   // 페이지 로드 직후 1회 즉시 fetch — interval 첫 tick 까지 안 기다림
            start();
        },
    };

    global.AutoRefresh = AutoRefresh;
})(window);
