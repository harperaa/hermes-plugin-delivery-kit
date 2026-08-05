/**
 * Delivery Kit — Hermes Dashboard Plugin
 *
 * Meeting Analysis: connect Fireflies.ai (default) or import transcripts
 * from any tool, analyze each meeting with the host LLM, and roll insights,
 * sentiment, client satisfaction, and lessons learned into one delivery
 * dashboard. Connect buttons live at the top; each modal carries key
 * instructions and stores the key straight into the env.
 *
 * Plain IIFE, no build step. window.__HERMES_PLUGIN_SDK__ for React.
 */
(function () {
  "use strict";

  var SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  // -------------------------------------------------------------------------
  // Ambient FX (standalone installs; yields when the acvc bundle is present)
  // -------------------------------------------------------------------------
  (function ambientBackground() {
    var ROUTES = { "/delivery": 1 };
    var canvas = null, tintEl = null, raf = 0, stars = null;
    var pointer = { x: 0, y: 0 }, eased = { x: 0, y: 0 };
    var theme = { r: 20, g: 184, b: 166 }, fore = { r: 230, g: 230, b: 240 };
    var lightTheme = false, moteBase = 255, dpr = 1;
    var probeCanvas = null;

    function parseColor(col, fallback) {
      if (!probeCanvas) { probeCanvas = document.createElement("canvas"); probeCanvas.width = probeCanvas.height = 1; }
      var x = probeCanvas.getContext("2d", { willReadFrequently: true });
      x.fillStyle = fallback; x.fillStyle = col;
      x.clearRect(0, 0, 1, 1); x.fillRect(0, 0, 1, 1);
      var d = x.getImageData(0, 0, 1, 1).data;
      return { r: d[0], g: d[1], b: d[2] };
    }
    function resolveVar(name, fallback) {
      var probe = document.createElement("span");
      probe.style.color = "var(" + name + ", " + fallback + ")";
      probe.style.display = "none";
      document.body.appendChild(probe);
      var col = getComputedStyle(probe).color;
      probe.remove();
      return parseColor(col, fallback);
    }
    function refreshPalette() {
      theme = resolveVar("--color-primary", "#14b8a6");
      fore = parseColor(getComputedStyle(document.body).color, "#e6e6f0");
      var card = resolveVar("--color-card", "#16162a");
      var lum = 0.2126 * card.r + 0.7152 * card.g + 0.0722 * card.b;
      lightTheme = lum > 140;
      moteBase = lightTheme ? 0 : 255;
    }
    function effectsOff() {
      try { return localStorage.getItem("vcl-effects-off") === "1"; }
      catch (e) { return false; }
    }
    function resize() {
      if (!canvas) return;
      dpr = window.devicePixelRatio || 1;
      canvas.width = window.innerWidth * dpr;
      canvas.height = window.innerHeight * dpr;
    }
    function onMove(e) {
      pointer.x = (e.clientX / window.innerWidth - 0.5) * 2;
      pointer.y = (e.clientY / window.innerHeight - 0.5) * 2;
    }
    function frame(t) {
      if (!canvas) return;
      var ctx = canvas.getContext("2d");
      var w = canvas.width, hgt = canvas.height;
      if (effectsOff()) { ctx.clearRect(0, 0, w, hgt); raf = requestAnimationFrame(frame); return; }
      eased.x += (pointer.x - eased.x) * 0.03;
      eased.y += (pointer.y - eased.y) * 0.03;
      ctx.clearRect(0, 0, w, hgt);
      var lx = (0.5 + 0.34 * Math.sin(t * 0.000041)) * w;
      var ly = (0.42 + 0.30 * Math.sin(t * 0.000029 + 1.7)) * hgt;
      var lr = Math.max(w, hgt) * 0.42;
      var glow = ctx.createRadialGradient(lx, ly, 0, lx, ly, lr);
      glow.addColorStop(0, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0.34)");
      glow.addColorStop(0.55, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0.13)");
      glow.addColorStop(1, "rgba(" + theme.r + "," + theme.g + "," + theme.b + ",0)");
      ctx.fillStyle = glow; ctx.fillRect(0, 0, w, hgt);
      var l2x = (0.5 - 0.38 * Math.sin(t * 0.000033 + 0.6)) * w;
      var l2y = (0.55 + 0.28 * Math.cos(t * 0.000047)) * hgt;
      var g2 = ctx.createRadialGradient(l2x, l2y, 0, l2x, l2y, lr * 0.7);
      g2.addColorStop(0, "rgba(" + fore.r + "," + fore.g + "," + fore.b + "," + (lightTheme ? 0.09 : 0.13) + ")");
      g2.addColorStop(1, "rgba(" + fore.r + "," + fore.g + "," + fore.b + ",0)");
      ctx.fillStyle = g2; ctx.fillRect(0, 0, w, hgt);
      for (var i = 0; i < stars.length; i++) {
        var st = stars[i];
        st.x += 0.000012 * (0.3 + st.depth);
        st.y -= 0.0000048 * (0.3 + st.depth);
        if (st.x > 1.02) st.x = -0.02;
        if (st.y < -0.02) st.y = 1.02;
        var px = (st.x + eased.x * 0.012 * st.depth) * w;
        var py = (st.y + eased.y * 0.012 * st.depth) * hgt;
        var a = (0.10 + 0.16 * st.depth) *
          (0.7 + 0.3 * Math.sin(t * 0.00045 * st.twinkle + st.phase));
        var base = st.themed ? theme : fore;
        var cr = Math.round(base.r * 0.45 + moteBase * 0.55);
        var cg = Math.round(base.g * 0.45 + moteBase * 0.55);
        var cb = Math.round(base.b * 0.45 + moteBase * 0.55);
        ctx.beginPath();
        ctx.fillStyle = "rgba(" + cr + "," + cg + "," + cb + "," + a + ")";
        ctx.arc(px, py, (0.5 + st.depth * 0.9) * dpr, 0, Math.PI * 2);
        ctx.fill();
      }
      raf = requestAnimationFrame(frame);
    }
    function mount() {
      if (canvas) return;
      stars = [];
      for (var i = 0; i < 140; i++) {
        stars.push({ x: Math.random(), y: Math.random(),
          depth: 0.35 + Math.random() * 0.65,
          phase: Math.random() * Math.PI * 2,
          twinkle: 0.4 + Math.random() * 0.8,
          themed: Math.random() < 0.45 });
      }
      tintEl = document.createElement("div");
      tintEl.className = "dk-ambient-tint";
      canvas = document.createElement("canvas");
      canvas.className = "dk-ambient-canvas";
      canvas.style.opacity = "0.95";
      document.body.appendChild(tintEl);
      document.body.appendChild(canvas);
      refreshPalette(); resize();
      window.addEventListener("resize", resize);
      window.addEventListener("mousemove", onMove);
      raf = requestAnimationFrame(frame);
    }
    function unmount() {
      if (!canvas) return;
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      canvas.remove(); tintEl.remove();
      canvas = null; tintEl = null;
    }
    function check() {
      var acvcOwns = !!document.getElementById("acvc-sidebar-order");
      if (ROUTES[window.location.pathname] && !acvcOwns) mount(); else unmount();
    }
    try {
      new MutationObserver(function () { refreshPalette(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style", "data-theme"] });
    } catch (e) {}
    setInterval(refreshPalette, 3000);
    window.addEventListener("popstate", check);
    setInterval(check, 800);
    check();
  })();

  var React = SDK.React;
  var h = React.createElement;
  var hooks = SDK.hooks;
  var useState = hooks.useState;
  var useEffect = hooks.useEffect;
  var useCallback = hooks.useCallback;
  var useRef = hooks.useRef;

  var API = "/api/plugins/delivery-kit";

  function api(path, options) {
    return SDK.fetchJSON(API + path, options);
  }

  function postJSON(path, body) {
    return api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  }

  var MUTED = "var(--color-muted-foreground, #9aa0b4)";

  function fmtWhen(ts) {
    if (!ts) return "";
    return new Date(ts * 1000).toLocaleDateString(undefined,
      { month: "short", day: "numeric", year: "numeric" });
  }

  function sentimentColor(score) {
    if (score >= 0.35) return "#22c55e";
    if (score >= 0) return "#eab308";
    return "#ef4444";
  }

  // Piecewise scale (Allen-tuned for contrast):
  //   0-60   reds -> orange
  //   60-80  orange -> yellow
  //   80-100 greens, light -> dark
  function scaleColor(t) {
    t = Math.max(0, Math.min(1, t));
    if (t < 0.5) {
      return "hsl(0, 78%, 46%)";                  // below 50: red, full stop
    }
    if (t < 0.6) {
      var h0 = ((t - 0.5) / 0.1) * 30;            // 50-60: red -> orange
      return "hsl(" + Math.round(h0) + ", 78%, 46%)";
    }
    if (t < 0.8) {
      var h1 = 30 + ((t - 0.6) / 0.2) * 25;       // orange -> 55 yellow
      return "hsl(" + Math.round(h1) + ", 82%, 44%)";
    }
    var l = 45 - ((t - 0.8) / 0.2) * 19;          // light green -> dark green
    return "hsl(125, 62%, " + Math.round(l) + "%)";
  }
  function sentimentPct(score) {          // -1..1 -> 0..100
    return Math.round(((Number(score) + 1) / 2) * 100);
  }
  function sentimentFace(score) {
    var v = Number(score);
    if (v > 0.6) return "😄";
    if (v > 0.2) return "🙂";
    if (v > -0.2) return "😐";
    if (v > -0.6) return "🙁";
    return "😠";
  }
  // analysis list items are {text, quote}; pre-evidence analyses stored plain strings
  function itemText(x) { return typeof x === "string" ? x : (x && x.text) || ""; }
  function itemQuote(x) { return (x && typeof x === "object" && x.quote) || ""; }

  // -------------------------------------------------------------------------
  // Evidence modal — full transcript with the supporting quote(s) highlighted
  // -------------------------------------------------------------------------
  function EvidenceModal(props) {
    var ev = props.ev;                // {meetingId, meetingTitle, quotes, label}
    var txSt = useState(null);
    var tx = txSt[0], setTx = txSt[1];
    var metaSt = useState(null);      // fetched meeting row (heldAt etc.)
    var meta = metaSt[0], setMeta = metaSt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var boxRef = useRef(null);

    useEffect(function () {
      var alive = true;
      api("/meeting/" + encodeURIComponent(ev.meetingId))
        .then(function (d) {
          if (!alive) return;
          setMeta(d);
          setTx(d.transcript || "");
        })
        .catch(function (e) { if (alive) setErr(String((e && e.message) || e)); });
      return function () { alive = false; };
    }, [ev.meetingId]);

    function ranges(text, quotes) {
      var lower = text.toLowerCase();
      var out = [];
      (quotes || []).forEach(function (qq) {
        var needle = String(qq || "").trim().toLowerCase();
        if (needle.length < 8) return;
        var found = false, at = 0;
        while ((at = lower.indexOf(needle, at)) !== -1) {
          out.push([at, at + needle.length]); found = true;
          at += needle.length;
        }
        if (!found) {
          // quote spans transcript lines (each line carries a [ts] Speaker:
          // prefix) — match its sentences individually instead
          (needle.match(/[^.?!]+[.?!]*/g) || []).forEach(function (frag) {
            frag = frag.trim();
            if (frag.length < 20) return;
            var fp = 0;
            while ((fp = lower.indexOf(frag, fp)) !== -1) {
              out.push([fp, fp + frag.length]); found = true;
              fp += frag.length;
            }
          });
        }
        if (!found && needle.length > 40) {   // last resort: the quote's head
          var p = lower.indexOf(needle.slice(0, 40));
          if (p !== -1) out.push([p, p + 40]);
        }
      });
      out.sort(function (a, b) { return a[0] - b[0]; });
      var merged = [];
      out.forEach(function (r) {
        var last = merged[merged.length - 1];
        if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
        else merged.push([r[0], r[1]]);
      });
      return merged;
    }

    var rs = tx != null ? ranges(tx, ev.quotes) : [];

    useEffect(function () {
      if (tx == null || !boxRef.current) return;
      var pre = boxRef.current.querySelector(".dk-transcript");
      var mark = pre && pre.querySelector(".dk-ev-mark");
      if (pre && mark) pre.scrollTop = Math.max(0, mark.offsetTop - pre.clientHeight / 3);
    }, [tx]);

    var body;
    if (err) body = h("div", { className: "dk-err" }, err);
    else if (tx == null) body = h("div", { style: { color: MUTED, fontSize: 13 } },
      "Loading transcript…");
    else {
      var parts = [], pos = 0;
      rs.forEach(function (r, i) {
        if (r[0] > pos) parts.push(tx.slice(pos, r[0]));
        parts.push(h("mark", { key: "m" + i, className: "dk-ev-mark" },
          tx.slice(r[0], r[1])));
        pos = r[1];
      });
      parts.push(tx.slice(pos));
      body = h(React.Fragment, null,
        (ev.quotes || []).filter(Boolean).length && !rs.length
          ? h("div", { style: { color: MUTED, fontSize: 12, margin: "0 0 8px" } },
              "Couldn't locate the quote verbatim in the transcript — showing it " +
              "above and the full transcript below.")
          : null,
        h("pre", { className: "dk-transcript" }, parts));
    }

    return h("div", { className: "dk-modal", onClick: function (e) {
          if (e.target === e.currentTarget) props.onClose();
        } },
      h("div", { className: "dk-modal-box", style: { maxWidth: 780 }, ref: boxRef },
        h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 2 } },
          "📜 " + ev.meetingTitle),
        meta && (meta.heldAt || meta.createdAt)
          ? h("div", { style: { color: MUTED, fontSize: 12, marginBottom: 2 } },
              "🕐 " + new Date((meta.heldAt || meta.createdAt) * 1000)
                .toLocaleString(undefined,
                  { weekday: "short", month: "short", day: "numeric",
                    year: "numeric", hour: "numeric", minute: "2-digit" }) +
              (meta.durationMin
                ? " · " + Math.round(meta.durationMin) + " min"
                : ""))
          : null,
        ev.label
          ? h("div", { style: { color: MUTED, fontSize: 12.5, marginBottom: 8 } },
              ev.label)
          : null,
        (ev.quotes || []).filter(Boolean).map(function (qq, i) {
          return h("blockquote", { key: i, className: "dk-ev-quote" }, "“" + qq + "”");
        }),
        body,
        h("div", { className: "dk-modal-row" },
          h("button", { className: "dk-btn", onClick: props.onClose }, "Close"))));
  }

  // -------------------------------------------------------------------------
  // Connect bar — provider buttons at the top; modal stores the key inline
  // -------------------------------------------------------------------------
  function ConnectBar(props) {
    var openSt = useState(null);       // provider object or null
    var open = openSt[0], setOpen = openSt[1];
    var keySt = useState("");
    var keyVal = keySt[0], setKeyVal = keySt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];

    function save() {
      if (!keyVal.trim() || busy) return;
      setBusy(true); setErr(null);
      postJSON("/connect", { provider: open.id, apiKey: keyVal.trim() })
        .then(function (r) {
          props.onState(r.state);
          setOpen(null); setKeyVal("");
        })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    return h("div", null,
      h("div", { className: "dk-connectbar" },
        h("span", { style: { fontSize: 12.5, color: MUTED, fontWeight: 700 } }, "Connect:"),
        props.providers.map(function (p) {
          return h("button", {
            key: p.id,
            className: "dk-provider" + (p.connected ? " dk-provider-on" : "") +
              (p.default ? " dk-provider-default" : ""),
            title: p.connected ? p.label + " connected"
              : "Connect " + p.label + " — instructions inside",
            onClick: function () { setErr(null); setKeyVal(""); setOpen(p); },
          }, (p.connected ? "✓ " : "") + p.label);
        })),
      open
        ? h("div", { className: "dk-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setOpen(null);
            } },
            h("div", { className: "dk-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 8 } },
                "Connect " + open.label),
              h("pre", { className: "dk-instructions" }, open.instructions),
              h("a", { className: "dk-link", href: open.url, target: "_blank",
                       rel: "noreferrer" }, "Open " + open.label + " ↗"),
              open.env
                ? h("div", { style: { marginTop: 12 } },
                    h("input", {
                      className: "dk-input", type: "password",
                      placeholder: open.label + " API key",
                      value: keyVal, autoFocus: true,
                      onChange: function (e) { setKeyVal(e.target.value); },
                      onKeyDown: function (e) { if (e.key === "Enter") save(); },
                    }),
                    err ? h("div", { className: "dk-err" }, err) : null,
                    h("div", { className: "dk-modal-row" },
                      h("button", { className: "dk-btn",
                                    onClick: function () { setOpen(null); } }, "Cancel"),
                      h("button", { className: "dk-btn dk-btn-primary",
                                    disabled: busy || !keyVal.trim(),
                                    onClick: save },
                        busy ? "Saving…" : "Save key")))
                : h("div", { className: "dk-modal-row", style: { marginTop: 12 } },
                    h("button", { className: "dk-btn",
                                  onClick: function () { setOpen(null); } }, "Close"),
                    h("button", { className: "dk-btn dk-btn-primary",
                                  onClick: function () { setOpen(null); props.onImport(); } },
                      "Open Import"))))
        : null);
  }

  // -------------------------------------------------------------------------
  // Trend chart — satisfaction bars + sentiment line, inline SVG
  // -------------------------------------------------------------------------
  function TrendChart(props) {
    var pts = props.trend || [];
    if (pts.length < 2) return null;
    var W = 640, H = 120, pad = 6;
    var n = pts.length;
    var bw = (W - pad * 2) / n;
    var bars = pts.map(function (p, i) {
      if (p.satisfaction == null) return null;
      var bh = Math.max(2, (p.satisfaction / 10) * (H - pad * 2));
      return h("rect", {
        key: "b" + i,
        x: pad + i * bw + bw * 0.15, y: H - pad - bh,
        width: bw * 0.7, height: bh, rx: 2,
        fill: "var(--color-primary, #14b8a6)", opacity: 0.35,
      }, h("title", null, p.title + " — satisfaction " + p.satisfaction + "/10"));
    });
    var line = pts.map(function (p, i) {
      var x = pad + i * bw + bw / 2;
      var y = H / 2 - p.sentiment * (H / 2 - pad);
      return (i === 0 ? "M" : "L") + x.toFixed(1) + "," + y.toFixed(1);
    }).join(" ");
    var dots = pts.map(function (p, i) {
      var x = pad + i * bw + bw / 2;
      var y = H / 2 - p.sentiment * (H / 2 - pad);
      return h("circle", { key: "d" + i, cx: x, cy: y, r: 3,
                           fill: sentimentColor(p.sentiment) },
        h("title", null, p.title + " — sentiment " + p.sentiment.toFixed(2)));
    });
    return h("div", { className: "dk-card" },
      h("div", { style: { fontWeight: 800, marginBottom: 6 } }, "📈 Delivery trend"),
      h("div", { style: { color: MUTED, fontSize: 12, marginBottom: 8 } },
        "bars = client satisfaction (0–10) · line = sentiment (−1…+1) · oldest → newest"),
      h("svg", { viewBox: "0 0 " + W + " " + H, className: "dk-trend" },
        h("line", { x1: pad, y1: H / 2, x2: W - pad, y2: H / 2,
                    stroke: "currentColor", opacity: 0.15 }),
        bars,
        h("path", { d: line, fill: "none", stroke: "currentColor",
                    strokeWidth: 1.5, opacity: 0.7 }),
        dots));
  }

  // -------------------------------------------------------------------------
  // Dashboard tab
  // -------------------------------------------------------------------------
  function DashboardTab(props) {
    var d = props.dashboard || {};
    var qSt = useState("");
    var q = qSt[0], setQ = qSt[1];
    function hit(it) {
      if (!q.trim()) return true;
      var needle = q.trim().toLowerCase();
      return it.text.toLowerCase().indexOf(needle) !== -1 ||
        it.meeting.toLowerCase().indexOf(needle) !== -1;
    }
    if (!d.analyzed) {
      return h("div", { className: "dk-card", style: { color: MUTED, fontSize: 13.5 } },
        d.total
          ? "Meetings are in — hit Analyze on the Meetings tab to build the dashboard."
          : "No meetings yet. Connect Fireflies above and Sync, or Import a transcript.");
    }
    function stat(label, value, sub, color) {
      return h("div", { className: "dk-stat" },
        h("div", { className: "dk-stat-n", style: color ? { color: color } : null }, value),
        h("div", { className: "dk-stat-l" }, label),
        sub ? h("div", { className: "dk-stat-s" }, sub) : null);
    }
    function bucket(title, icon, items, cls) {
      items = (items || []).filter(hit);
      if (!items.length) return null;
      return h("div", { className: "dk-card" },
        h("div", { style: { fontWeight: 800, marginBottom: 8 } }, icon + " " + title),
        h("ul", { className: "dk-list " + (cls || "") },
          items.map(function (it, i) {
            var clickable = props.onEvidence && it.meetingId;
            return h("li", {
                key: i,
                className: clickable ? "dk-ev-item" : null,
                title: clickable ? "Show the supporting transcript excerpt" : null,
                onClick: clickable ? function () {
                  props.onEvidence({ meetingId: it.meetingId, meetingTitle: it.meeting,
                    quotes: it.quote ? [it.quote] : [],
                    label: title.replace(/ —.*$/, "") + ": " + it.text });
                } : null,
              },
              it.text,
              h("span", { className: "dk-attrib" },
                " — " + it.meeting + (it.heldAt ? " · " + fmtWhen(it.heldAt) : "")));
          })));
    }
    return h("div", null,
      h("input", {
        className: "dk-input dk-search", type: "search", value: q,
        placeholder: "🔎 Filter the dashboard — keyword or meeting title…",
        style: { marginBottom: 12 },
        onChange: function (e) { setQ(e.target.value); },
      }),
      h("div", { className: "dk-stats" },
        stat("meetings analyzed", d.analyzed + " / " + d.total),
        d.avgSatisfaction != null
          ? stat("avg client satisfaction", d.avgSatisfaction.toFixed(1) + " / 10",
              d.satisfactionMeetings + " client/sales meeting(s)",
              scaleColor(d.avgSatisfaction / 10))
          : stat("client satisfaction", "n/a", "no client meetings analyzed"),
        stat("avg sentiment", sentimentPct(d.avgSentiment) + "%",
          d.avgSentiment >= 0.35 ? "positive" : d.avgSentiment >= 0 ? "neutral" : "negative",
          scaleColor(sentimentPct(d.avgSentiment) / 100)),
        stat("latest meeting",
          d.latestSatisfaction != null ? d.latestSatisfaction.toFixed(0) + " / 10"
            : sentimentPct(d.latestSentiment) + "%",
          "sentiment " + sentimentPct(d.latestSentiment) + "%",
          scaleColor(sentimentPct(d.latestSentiment) / 100))),
      h(TrendChart, { trend: d.trend }),
      bucket("Risks heard", "⚠️", d.risks, "dk-risks"),
      bucket("Lessons learned", "🎓", d.lessons),
      bucket("Insights", "💡", d.insights));
  }

  // -------------------------------------------------------------------------
  // Meetings tab
  // -------------------------------------------------------------------------
  function AnalysisView(props) {
    var a = props.analysis;
    function evClick(quotes, label) {
      if (!props.onEvidence || !props.meetingId) return null;
      return function (e) {
        e.stopPropagation();
        props.onEvidence({ meetingId: props.meetingId,
          meetingTitle: props.meetingTitle, quotes: quotes, label: label });
      };
    }
    function list(title, items) {
      if (!items || !items.length) return null;
      return h("div", { style: { marginTop: 8 } },
        h("div", { style: { fontSize: 11.5, fontWeight: 700, color: MUTED,
                            textTransform: "uppercase", letterSpacing: "0.06em" } }, title),
        h("ul", { className: "dk-list" }, items.map(function (x, i) {
          var quote = itemQuote(x);
          var onEv = evClick(quote ? [quote] : [], title + ": " + itemText(x));
          return h("li", {
            key: i,
            className: onEv ? "dk-ev-item" : null,
            title: onEv ? (quote ? "Show the supporting transcript excerpt"
                                 : "Show the transcript") : null,
            onClick: onEv,
          }, itemText(x));
        })));
    }
    var badgeEv = evClick(a.sentimentQuotes || [],
      "Sentiment evidence — " + a.sentimentLabel + " · " +
      sentimentPct(a.sentimentScore) + "%");
    return h("div", { className: "dk-analysis" },
      h("div", { style: { display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 6 } },
        a.meetingType
          ? h("span", { className: "dk-chip dk-chip-type" }, a.meetingType)
          : null,
        h("span", { className: "dk-chip dk-chip-fill" + (badgeEv ? " dk-ev-item" : ""),
                    title: badgeEv ? "Show the transcript lines behind this score" : null,
                    onClick: badgeEv,
                    style: { background: scaleColor(sentimentPct(a.sentimentScore) / 100),
                             borderColor: scaleColor(sentimentPct(a.sentimentScore) / 100) } },
          sentimentFace(a.sentimentScore) + " sentiment " + a.sentimentLabel +
          " · " + sentimentPct(a.sentimentScore) + "%")),
      h("p", { style: { margin: "6px 0", fontSize: 13.5 } }, a.overview),
      h("p", { style: { margin: "6px 0", fontSize: 12.5, color: MUTED } },
        a.satisfactionRationale),
      list("Strengths", a.strengths),
      list("Weaknesses", a.weaknesses),
      list("Insights", a.insights),
      list("Lessons learned", a.lessons),
      list("Action items", a.actionItems),
      list("Risks", a.risks));
  }

  function fmtHour(hh) {
    hh = Number(hh) || 0;
    if (hh === 0) return "12 AM";
    if (hh < 12) return hh + " AM";
    if (hh === 12) return "12 PM";
    return (hh - 12) + " PM";
  }
  var FREQS = [[30, "every 30 min"], [60, "hourly"], [120, "every 2 hours"],
               [180, "every 3 hours"], [240, "every 4 hours"]];
  function freqLabel(mins) {
    mins = Number(mins) || 60;
    if (mins === 30) return "every 30m";
    if (mins === 60) return "hourly";
    return "every " + (mins / 60) + "h";
  }

  function AutosyncModal(props) {
    var a = props.autosync || {};
    var enSt = useState(a.enabled !== false);
    var en = enSt[0], setEn = enSt[1];
    var freqSt = useState(a.frequencyMinutes || 60);
    var freq = freqSt[0], setFreq = freqSt[1];
    var startSt = useState(a.startHour == null ? 8 : a.startHour);
    var start = startSt[0], setStart = startSt[1];
    var endSt = useState(a.endHour == null ? 19 : a.endHour);
    var end = endSt[0], setEnd = endSt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];

    function save() {
      setBusy(true); setErr(null);
      postJSON("/autosync", {
        enabled: en,
        frequencyMinutes: Number(freq),
        startHour: Number(start),
        endHour: Number(end),
        tzOffsetMinutes: new Date().getTimezoneOffset(),
      })
        .then(function () { return api("/state"); })
        .then(function (d) { props.onState(d); props.onClose(); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    function hourSelect(value, setter) {
      var opts = [];
      for (var hh = 0; hh < 24; hh++) {
        opts.push(h("option", { key: hh, value: hh }, fmtHour(hh)));
      }
      return h("select", {
        className: "dk-input", style: { width: "auto" }, value: value,
        onChange: function (e) { setter(Number(e.target.value)); },
      }, opts);
    }

    var swapped = Number(end) < Number(start);
    return h("div", { className: "dk-modal", onClick: function (e) {
          if (e.target === e.currentTarget) props.onClose();
        } },
      h("div", { className: "dk-modal-box" },
        h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 6 } },
          "⏰ Auto-sync schedule"),
        h("div", { style: { color: MUTED, fontSize: 12.5, marginBottom: 12 } },
          "Pulls new transcripts from every connected provider on a schedule, " +
          "in your timezone. No LLM cost — analysis stays manual."),
        h("div", { style: { display: "flex", alignItems: "center", gap: 10,
                            marginBottom: 12 } },
          h("button", {
              className: "dk-tab" + (en ? " dk-tab-on" : ""),
              onClick: function () { setEn(!en); },
            }, en ? "● Enabled" : "○ Disabled")),
        h("div", { style: { display: "flex", alignItems: "center", gap: 8,
                            flexWrap: "wrap", marginBottom: 10 } },
          h("span", { style: { fontSize: 13, fontWeight: 700 } }, "Frequency"),
          h("select", {
              className: "dk-input", style: { width: "auto" }, value: freq,
              onChange: function (e) { setFreq(Number(e.target.value)); },
            },
            FREQS.map(function (f) {
              return h("option", { key: f[0], value: f[0] }, f[1]);
            }))),
        h("div", { style: { display: "flex", alignItems: "center", gap: 8,
                            flexWrap: "wrap" } },
          h("span", { style: { fontSize: 13, fontWeight: 700 } }, "Between"),
          hourSelect(start, setStart),
          h("span", { style: { color: MUTED } }, "and"),
          hourSelect(end, setEnd),
          h("span", { style: { color: MUTED, fontSize: 12 } }, "your time")),
        swapped
          ? h("div", { style: { color: MUTED, fontSize: 12, marginTop: 8 } },
              "End is before start — the window will be treated as " +
              fmtHour(end) + "–" + fmtHour(start) + ".")
          : null,
        err ? h("div", { className: "dk-err" }, err) : null,
        h("div", { className: "dk-modal-row" },
          h("button", { className: "dk-btn", onClick: props.onClose }, "Cancel"),
          h("button", { className: "dk-btn dk-btn-primary", disabled: busy,
                        onClick: save }, busy ? "Saving…" : "Save"))));
  }

  function SyncBar(props) {
    var busySt = useState(null);
    var busy = busySt[0], setBusy = busySt[1];
    var noticeSt = useState(null);
    var notice = noticeSt[0], setNotice = noticeSt[1];

    var syncable = (props.providers || []).filter(function (p) {
      return p.canSync && p.connected;
    });
    var anySyncable = (props.providers || []).some(function (p) { return p.canSync; });

    function sync(providerId) {
      setBusy("sync"); setNotice(null);
      postJSON("/sync", { provider: providerId })
        .then(function (r) {
          props.onState(r.state);
          setNotice("Synced " + r.fetched + " meeting(s) from " + r.provider +
            ", " + r.new + " new.");
        })
        .catch(function (e) { setNotice(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }

    function analyzeAll() {
      setBusy("all"); setNotice(null);
      postJSON("/analyze-all", {})
        .then(function (r) { props.onState(r.state); })
        .catch(function (e) { setNotice(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }

    function stopBatch() {
      postJSON("/analyze-all/stop", {})
        .then(function () { api("/state").then(props.onState); })
        .catch(function () {});
    }

    var auto = props.autosync || {};
    var autoOpenSt = useState(false);
    var autoOpen = autoOpenSt[0], setAutoOpen = autoOpenSt[1];

    var unanalyzed = (props.meetings || []).filter(function (m) {
      return !m.hasAnalysis;
    }).length;
    var batch = props.batch || {};
    var batchRunning = !!batch.running;

    return h("div", { className: "dk-card", style: { display: "flex", gap: 10,
               alignItems: "center", flexWrap: "wrap", marginBottom: 16 } },
      syncable.length
        ? syncable.map(function (p) {
            return h("button", { key: p.id, className: "dk-btn dk-btn-primary",
                          disabled: busy !== null,
                          title: "Pull latest transcripts from " + p.label,
                          onClick: function () { sync(p.id); } },
              busy === "sync" ? "Syncing…" : "⟳ Sync " + p.label);
          })
        : h("button", { className: "dk-btn dk-btn-primary", disabled: true,
              title: anySyncable
                ? "Connect a provider above (Fireflies, Fathom, Grain, tl;dv) to sync"
                : "" },
            "⟳ Sync"),
      h("button", { className: "dk-btn", disabled: busy !== null,
                    onClick: props.onImport }, "＋ Import transcript"),
      unanalyzed > 0 && !batchRunning
        ? h("button", { className: "dk-btn", disabled: busy !== null,
                        onClick: analyzeAll },
            busy === "all" ? "Starting…" : "✨ Analyze all (" + unanalyzed + ")")
        : null,
      batchRunning
        ? h(React.Fragment, null,
            h("span", { className: "dk-batch" },
              h("span", { className: "dk-spin" }, "◐"),
              batch.cancelRequested
                ? " Stopping after the current meeting…"
                : " Analyzing " + ((batch.done || 0) + 1) + "/" + batch.total +
                  (batch.current ? " — " + batch.current : "") +
                  " · safe to leave or refresh"),
            batch.cancelRequested ? null : h("button", {
              className: "dk-btn", style: { fontSize: 12 },
              title: "Stop after the meeting currently being analyzed",
              onClick: stopBatch,
            }, "⏹ Stop"))
        : null,
      !batchRunning && batch.cancelled
        ? h("span", { style: { color: MUTED, fontSize: 12.5 } },
            "Stopped at " + batch.done + "/" + batch.total + ".")
        : null,
      !batchRunning && !batch.cancelled && batch.finishedAt && (batch.failed || 0) > 0
        ? h("span", { style: { color: "#f87171", fontSize: 12.5 } },
            "Last run: " + batch.failed + " of " + batch.total + " failed — retry with ✨")
        : null,
      h("span", { style: { flex: 1 } }),
      h("button", {
          className: "dk-tab" + (auto.enabled ? " dk-tab-on" : ""),
          style: { fontSize: 12 },
          title: "Auto-sync settings — schedule, time range, frequency" +
            (auto.lastRun
              ? " · last run " + new Date(auto.lastRun * 1000).toLocaleString()
              : ""),
          onClick: function () { setAutoOpen(true); },
        }, "⏰ Auto-sync " + (auto.enabled
          ? freqLabel(auto.frequencyMinutes) + " · " +
            fmtHour(auto.startHour == null ? 8 : auto.startHour) + "–" +
            fmtHour(auto.endHour == null ? 19 : auto.endHour)
          : "off")),
      notice ? h("span", { style: { color: MUTED, fontSize: 12.5 } }, notice) : null,
      autoOpen
        ? h(AutosyncModal, { autosync: auto, onState: props.onState,
                             onClose: function () { setAutoOpen(false); } })
        : null);
  }

  function MeetingsTab(props) {
    var busySt = useState(null);      // meeting id being analyzed, or "sync"/"all"
    var busy = busySt[0], setBusy = busySt[1];
    var noticeSt = useState(null);
    var notice = noticeSt[0], setNotice = noticeSt[1];
    var expandSt = useState(null);
    var expanded = expandSt[0], setExpanded = expandSt[1];

    function analyzeOne(id) {
      setBusy(id); setNotice(null);
      return postJSON("/analyze", { meetingId: id })
        .then(function (r) { props.onState(r.state); setExpanded(id); })
        .catch(function (e) { setNotice(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); });
    }

    var filterSt = useState(null);        // "strengths" | "weaknesses" | "risks"
    var filter = filterSt[0], setFilter = filterSt[1];
    var batch = props.batch || {};
    var batchRunning = !!batch.running;
    var typeSt = useState(null);          // "client"|"sales"|"internal"|"other"
    var typeFilter = typeSt[0], setTypeFilter = typeSt[1];
    var TYPES = [["client", "🏢 Client"], ["sales", "💼 Sales"],
                 ["internal", "👥 Internal"], ["other", "▫️ Other"]];
    function mType(m) {
      return (m.analysis && m.analysis.meetingType) || null;
    }
    function matchesType(m) {
      return !typeFilter || mType(m) === typeFilter;
    }
    var qSt = useState("");
    var q = qSt[0], setQ = qSt[1];
    var idsSt = useState(null);           // server-matched ids (incl. transcripts)
    var matchIds = idsSt[0], setMatchIds = idsSt[1];
    var qTimer = useRef(null);

    function runSearch(text) {
      setQ(text);
      setPage(0);
      if (qTimer.current) window.clearTimeout(qTimer.current);
      if (!text.trim()) { setMatchIds(null); return; }
      qTimer.current = window.setTimeout(function () {
        api("/search?q=" + encodeURIComponent(text.trim()))
          .then(function (d) { setMatchIds(d.ids); })
          .catch(function () { setMatchIds(null); });
      }, 250);
    }

    var CATS = [
      ["strengths", "💪 Strengths"],
      ["weaknesses", "📉 Weaknesses"],
      ["risks", "🚨 Risks"],
    ];
    function matchesSearch(m) {
      if (!q.trim()) return true;
      if (matchIds) return matchIds.indexOf(m.id) !== -1;
      var needle = q.trim().toLowerCase();
      return (m.title || "").toLowerCase().indexOf(needle) !== -1 ||
        JSON.stringify(m.analysis || {}).toLowerCase().indexOf(needle) !== -1;
    }

    function catItems(key) {
      var out = [];
      props.meetings.filter(function (m) {
        return matchesSearch(m) && matchesType(m);
      }).forEach(function (m) {
        ((m.analysis && m.analysis[key]) || []).forEach(function (item) {
          out.push({ text: itemText(item), quote: itemQuote(item),
                     meetingId: m.id, meeting: m.title,
                     heldAt: m.heldAt || m.createdAt });
        });
      });
      return out;
    }

    var pageSt = useState(0);
    var page = pageSt[0], setPage = pageSt[1];
    var sizeSt = useState(25);
    var pageSize = sizeSt[0], setPageSize = sizeSt[1];
    var pullSt = useState(null);          // "more30" | "all" confirm modal
    var pullConfirm = pullSt[0], setPullConfirm = pullSt[1];
    var pullingSt = useState(false);
    var pulling = pullingSt[0], setPulling = pullingSt[1];

    function runPull(mode) {
      setPullConfirm(null); setPulling(true); setNotice(null);
      postJSON("/sync-extended", { mode: mode })
        .then(function (r) {
          props.onState(r.state);
          setNotice("Pulled " + r.fetched + " meeting(s), " + r.new +
            " new — auto-analysis " + (r.new ? "started." : "not needed."));
        })
        .catch(function (e) { setNotice(String((e && e.message) || e)); })
        .finally(function () { setPulling(false); });
    }

    var redoSt = useState(null);          // meeting being redone
    var redoFor = redoSt[0], setRedoFor = redoSt[1];
    var fbSt = useState("");
    var feedbackText = fbSt[0], setFeedbackText = fbSt[1];

    function redo() {
      var id = redoFor.id;
      setBusy(id); setRedoFor(null);
      postJSON("/analyze", { meetingId: id, feedback: feedbackText })
        .then(function (r) { props.onState(r.state); setExpanded(id); })
        .catch(function (e) { setNotice(String((e && e.message) || e)); })
        .finally(function () { setBusy(null); setFeedbackText(""); });
    }


    var filterBar = h(React.Fragment, null,
      h("div", { className: "dk-filterbar" },
        h("input", {
          className: "dk-input dk-search", type: "search", value: q,
          placeholder: "🔎 Search meetings — title, transcript, analysis…",
          onChange: function (e) { runSearch(e.target.value); },
        })),
      h("div", { className: "dk-filterbar" },
      TYPES.map(function (t) {
        var n = props.meetings.filter(function (m) { return mType(m) === t[0]; }).length;
        if (!n) return null;
        return h("button", {
          key: "t" + t[0],
          className: "dk-tab" + (typeFilter === t[0] ? " dk-tab-on" : ""),
          title: "Show only " + t[0] + " meetings",
          onClick: function () {
            setTypeFilter(typeFilter === t[0] ? null : t[0]);
            setPage(0);
          },
        }, t[1] + " (" + n + ")");
      }),
      h("span", { className: "dk-fdiv" }),
      CATS.map(function (c) {
        var n = catItems(c[0]).length;
        return h("button", {
          key: c[0],
          className: "dk-tab" + (filter === c[0] ? " dk-tab-on" : ""),
          title: filter === c[0] ? "Back to the meeting list"
            : "One view of every " + c[0].replace(/s$/, "") + " across all meetings",
          onClick: function () { setFilter(filter === c[0] ? null : c[0]); },
        }, c[1] + (n ? " (" + n + ")" : ""));
      }),
      filter
        ? h("button", { className: "dk-btn", style: { fontSize: 12 },
                        onClick: function () { setFilter(null); } }, "✕ clear")
        : null));

    if (filter) {
      var items = catItems(filter);
      var preCat = props.meetings.filter(function (m) {
        return m.analysis && m.analysis[filter] === undefined;
      }).length;
      var label = CATS.filter(function (c) { return c[0] === filter; })[0][1];
      return h("div", null,
        filterBar,
        h("div", { className: "dk-card" },
          h("div", { style: { fontWeight: 800, marginBottom: 8 } },
            label + " — across every analyzed meeting"),
          items.length === 0
            ? h("div", { style: { color: MUTED, fontSize: 13.5 } },
                "Nothing captured in this category yet.")
            : h("ul", { className: "dk-list" + (filter === "risks" ? " dk-risks" : "") },
                items.map(function (it, i) {
                  var onEv = props.onEvidence ? function () {
                    props.onEvidence({ meetingId: it.meetingId,
                      meetingTitle: it.meeting,
                      quotes: it.quote ? [it.quote] : [],
                      label: label + ": " + it.text });
                  } : null;
                  return h("li", {
                      key: i,
                      className: onEv ? "dk-ev-item" : null,
                      title: onEv ? "Show the supporting transcript excerpt" : null,
                      onClick: onEv,
                    },
                    it.text,
                    h("span", { className: "dk-attrib" },
                      " — " + it.meeting +
                      (it.heldAt ? " · " + fmtWhen(it.heldAt) : "")));
                })),
          preCat > 0
            ? h("div", { style: { color: MUTED, fontSize: 12.5, marginTop: 10 } },
                preCat + " meeting(s) were analyzed before " + filter +
                " tracking existed — hit ↻ Redo on them to extract.")
            : null));
    }

    return h("div", null,
      filterBar,
      props.meetings.length === 0
        ? h("div", { className: "dk-card", style: { color: MUTED, fontSize: 13.5 } },
            "No meetings yet — Sync a provider or Import a transcript.")
        : props.meetings.filter(function (m) {
            return matchesSearch(m) && matchesType(m);
          }).length === 0
        ? h("div", { className: "dk-card", style: { color: MUTED, fontSize: 13.5 } },
            "No meetings match the current filters.")
        : (function () {
            var filtered = props.meetings.filter(function (m) {
              return matchesSearch(m) && matchesType(m);
            });
            var curPage = Math.min(page,
              Math.max(0, Math.ceil(filtered.length / pageSize) - 1));
            return filtered.slice(curPage * pageSize,
                                  (curPage + 1) * pageSize);
          })().map(function (m) {
            var isOpen = expanded === m.id;
            return h("div", { key: m.id, className: "dk-card dk-meeting" },
              h("div", { className: "dk-meeting-head",
                         onClick: function () { setExpanded(isOpen ? null : m.id); } },
                h("span", { className: "dk-chev" + (isOpen ? " dk-chev-open" : "") }, "▸"),
                h("span", { style: { fontWeight: 700, flex: 1 } }, m.title),
                m.analysis
                  ? h(React.Fragment, null,
                      m.analysis.meetingType
                        ? h("span", { className: "dk-chip dk-chip-type" },
                            m.analysis.meetingType)
                        : null,
                      h("span", { className: "dk-chip dk-chip-fill dk-ev-item",
                          title: "Client sentiment " +
                            sentimentPct(m.analysis.sentimentScore) +
                            "% — click for the transcript evidence",
                          onClick: function (e) {
                            e.stopPropagation();
                            if (props.onEvidence) props.onEvidence({
                              meetingId: m.id, meetingTitle: m.title,
                              quotes: (m.analysis.sentimentQuotes) || [],
                              label: "Sentiment evidence — " +
                                (m.analysis.sentimentLabel || "") + " · " +
                                sentimentPct(m.analysis.sentimentScore) + "%" });
                          },
                          style: {
                            background: scaleColor(sentimentPct(m.analysis.sentimentScore) / 100),
                            borderColor: scaleColor(sentimentPct(m.analysis.sentimentScore) / 100) } },
                        sentimentFace(m.analysis.sentimentScore) + " " +
                        sentimentPct(m.analysis.sentimentScore) + "%"),
                      h("button", { className: "dk-btn", style: { fontSize: 12 },
                          disabled: busy !== null || batchRunning,
                          title: "Re-analyze — optionally tell the analyst what to fix",
                          onClick: function (e) {
                            e.stopPropagation();
                            setFeedbackText(""); setRedoFor(m);
                          } },
                        busy === m.id ? "Redoing…" : "↻ Redo"))
                  : h("button", { className: "dk-btn", style: { fontSize: 12 },
                        disabled: busy !== null || batchRunning,
                        onClick: function (e) { e.stopPropagation(); analyzeOne(m.id); } },
                      busy === m.id ? "Analyzing…" : "✨ Analyze"),
                h("span", { style: { color: MUTED, fontSize: 12 } },
                  (m.provider === "import" ? "imported" : m.provider) +
                  (m.heldAt ? " · " + fmtWhen(m.heldAt) : "") +
                  (m.durationMin ? " · " + Math.round(m.durationMin) + "m" : ""))),
              isOpen && m.analysis
                ? h(AnalysisView, { analysis: m.analysis, meetingId: m.id,
                    meetingTitle: m.title, onEvidence: props.onEvidence })
                : null,
              isOpen && !m.analysis
                ? h("div", { style: { color: MUTED, fontSize: 13, marginTop: 6 } },
                    "Not analyzed yet — hit ✨ Analyze.")
                : null);
          }),
      (function () {
        var filtered = props.meetings.filter(function (m) {
          return matchesSearch(m) && matchesType(m);
        });
        var total = filtered.length;
        var curPage = Math.min(page,
          Math.max(0, Math.ceil(total / pageSize) - 1));
        return h("div", { className: "dk-pagination" },
          total > pageSize
            ? h(React.Fragment, null,
                h("button", { className: "dk-btn",
                    disabled: curPage === 0,
                    onClick: function () { setPage(curPage - 1); } },
                  "Previous"),
                h("span", { style: { color: MUTED, fontSize: 12.5 } },
                  (total ? curPage * pageSize + 1 : 0) + "–" +
                  Math.min((curPage + 1) * pageSize, total) +
                  " of " + total),
                h("button", { className: "dk-btn",
                    disabled: (curPage + 1) * pageSize >= total,
                    onClick: function () { setPage(curPage + 1); } },
                  "Next"),
                h("select", { className: "dk-input",
                    style: { width: "auto" },
                    value: String(pageSize),
                    onChange: function (e) {
                      setPageSize(Number(e.target.value)); setPage(0);
                    } },
                  [10, 25, 50].map(function (n) {
                    return h("option", { key: n, value: String(n) },
                      n + " / page");
                  })))
            : null,
          h("span", { style: { flex: 1 } }),
          h("button", { className: "dk-btn", disabled: pulling,
              title: "Fetch the 30 days before your oldest synced meeting",
              onClick: function () { setPullConfirm("more30"); } },
            pulling ? "Pulling…" : "⟲ Pull 30 more days"),
          h("button", { className: "dk-btn", disabled: pulling,
              title: "Fetch your entire Fireflies history",
              onClick: function () { setPullConfirm("all"); } },
            "Pull ALL transcripts"));
      })(),
      pullConfirm
        ? h("div", { className: "dk-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setPullConfirm(null);
            } },
            h("div", { className: "dk-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15,
                  marginBottom: 8 } },
                pullConfirm === "all"
                  ? "Pull your ENTIRE transcript history?"
                  : "Pull 30 more days of transcripts?"),
              h("div", { style: { fontSize: 13, lineHeight: 1.6,
                  marginBottom: 6 } },
                pullConfirm === "all"
                  ? "This fetches every Fireflies meeting older than your " +
                    "current oldest — potentially hundreds."
                  : "This fetches the 30 days before your oldest synced " +
                    "meeting."),
              h("div", { className: "dk-err", style: { marginTop: 0 } },
                "⚠ Every new transcript is AUTO-ANALYZED with your " +
                "connected LLM. Each analysis burns real tokens — roughly " +
                "50–100K per meeting depending on length" +
                (pullConfirm === "all"
                  ? ", so a large history can add up to serious spend."
                  : ".")),
              h("div", { className: "dk-modal-row" },
                h("button", { className: "dk-btn",
                    onClick: function () { setPullConfirm(null); } },
                  "Cancel"),
                h("button", { className: "dk-btn dk-btn-primary",
                    onClick: function () { runPull(pullConfirm); } },
                  pullConfirm === "all"
                    ? "Pull everything & analyze"
                    : "Pull 30 days & analyze"))))
        : null,
      redoFor
        ? h("div", { className: "dk-modal", onClick: function (e) {
              if (e.target === e.currentTarget) setRedoFor(null);
            } },
            h("div", { className: "dk-modal-box" },
              h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 6 } },
                "Re-analyze: " + redoFor.title),
              h("div", { style: { color: MUTED, fontSize: 12.5, marginBottom: 10 } },
                "Optional — tell the analyst what to fix or focus on. Leave " +
                "blank for a fresh pass."),
              h("textarea", {
                className: "dk-input", rows: 3, autoFocus: true,
                placeholder: "e.g. the satisfaction score felt too high — weigh the pricing pushback more",
                value: feedbackText,
                onChange: function (e) { setFeedbackText(e.target.value); },
              }),
              h("div", { className: "dk-modal-row" },
                h("button", { className: "dk-btn",
                              onClick: function () { setRedoFor(null); } }, "Cancel"),
                h("button", { className: "dk-btn dk-btn-primary", onClick: redo },
                  "↻ Re-analyze"))))
        : null);
  }

  // -------------------------------------------------------------------------
  // Import modal
  // -------------------------------------------------------------------------
  function ImportModal(props) {
    var titleSt = useState("");
    var title = titleSt[0], setTitle = titleSt[1];
    var textSt = useState("");
    var text = textSt[0], setText = textSt[1];
    var busySt = useState(false);
    var busy = busySt[0], setBusy = busySt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];

    function save() {
      if (!title.trim() || !text.trim() || busy) return;
      setBusy(true); setErr(null);
      postJSON("/import", { title: title.trim(), transcript: text })
        .then(function (r) { props.onState(r.state); props.onClose(); })
        .catch(function (e) { setErr(String((e && e.message) || e)); })
        .finally(function () { setBusy(false); });
    }

    return h("div", { className: "dk-modal", onClick: function (e) {
          if (e.target === e.currentTarget) props.onClose();
        } },
      h("div", { className: "dk-modal-box", style: { maxWidth: 560 } },
        h("div", { style: { fontWeight: 800, fontSize: 15, marginBottom: 8 } },
          "Import a meeting transcript"),
        h("div", { style: { color: MUTED, fontSize: 12.5, marginBottom: 10 } },
          "Paste from any tool — Otter, Zoom, Fathom exports, or plain notes."),
        h("input", {
          className: "dk-input", placeholder: "Meeting title (e.g. Acme kickoff — Aug 4)",
          value: title, autoFocus: true,
          onChange: function (e) { setTitle(e.target.value); } }),
        h("textarea", {
          className: "dk-input", rows: 10, style: { marginTop: 8 },
          placeholder: "Paste the transcript or detailed notes here…",
          value: text,
          onChange: function (e) { setText(e.target.value); } }),
        err ? h("div", { className: "dk-err" }, err) : null,
        h("div", { className: "dk-modal-row" },
          h("button", { className: "dk-btn", onClick: props.onClose }, "Cancel"),
          h("button", { className: "dk-btn dk-btn-primary",
                        disabled: busy || !title.trim() || !text.trim(),
                        onClick: save }, busy ? "Importing…" : "Import"))));
  }

  // -------------------------------------------------------------------------
  // Page
  // -------------------------------------------------------------------------
  function DeliveryKitPage() {
    var stSt = useState(null);
    var st = stSt[0], setSt = stSt[1];
    var errSt = useState(null);
    var err = errSt[0], setErr = errSt[1];
    var tabSt = useState(function () {
      try { return localStorage.getItem("dk-tab") || "dashboard"; }
      catch (e) { return "dashboard"; }
    });
    var tab = tabSt[0], setTab = tabSt[1];
    function pickTab(t) {
      setTab(t);
      try { localStorage.setItem("dk-tab", t); } catch (e) {}
    }
    var importSt = useState(false);
    var showImport = importSt[0], setShowImport = importSt[1];
    var evSt = useState(null);        // {meetingId, meetingTitle, quotes, label}
    var evidence = evSt[0], setEvidence = evSt[1];

    var refresh = useCallback(function () {
      return api("/state")
        .then(function (d) { setSt(d); setErr(null); })
        .catch(function (e) { setErr(String((e && e.message) || e)); });
    }, []);
    useEffect(function () { refresh(); }, [refresh]);
    // keep the hourly auto-sync window (8:00-19:00) on the viewer's clock —
    // registers the cron job on first visit, re-aims it after DST shifts
    useEffect(function () {
      postJSON("/autosync", { tzOffsetMinutes: new Date().getTimezoneOffset() })
        .then(function (r) {
          setSt(function (prev) {
            return prev ? Object.assign({}, prev, { autosync: r.autosync }) : prev;
          });
        })
        .catch(function () {});
    }, []);
    var batchRunning = !!(st && st.batch && st.batch.running);
    useEffect(function () {
      if (!batchRunning) return undefined;
      var id = window.setInterval(refresh, 5000);
      return function () { window.clearInterval(id); };
    }, [refresh, batchRunning]);

    if (!st) {
      return h("div", { className: "dk-page" },
        h("div", { style: { color: MUTED, padding: 40 } }, err || "Loading…"));
    }

    return h("div", { className: "dk-page" },
      h("div", { className: "dk-inner" },
        h("div", { style: { marginBottom: 14 } },
          h("div", { style: { fontSize: 13, letterSpacing: 1.5, color: MUTED,
                              textTransform: "uppercase" } }, "AI Cyber Value Creator™"),
          h("h1", { style: { fontSize: 30, margin: "4px 0 6px", fontWeight: 800 } },
            "📦 Delivery Kit")),
        h("div", { className: "dk-tabs" },
          [["dashboard", "Delivery Dashboard"], ["meetings", "Meeting Analysis"]]
            .map(function (t) {
              return h("button", {
                key: t[0],
                className: "dk-pagetab" + (tab === t[0] ? " dk-pagetab-active" : ""),
                onClick: function () { pickTab(t[0]); },
              }, t[1]);
            })),
        err ? h("div", { className: "dk-err" }, err) : null,
        tab === "dashboard"
          ? h(DashboardTab, { dashboard: st.dashboard, onEvidence: setEvidence })
          : h(React.Fragment, null,
              h(ConnectBar, { providers: st.providers, onState: setSt,
                              onImport: function () { setShowImport(true); } }),
              h(SyncBar, { providers: st.providers, meetings: st.meetings,
                           batch: st.batch, autosync: st.autosync, onState: setSt,
                           onImport: function () { setShowImport(true); } }),
              h(MeetingsTab, { meetings: st.meetings, providers: st.providers,
                               batch: st.batch,
                               onState: setSt,
                               onEvidence: setEvidence,
                               onImport: function () { setShowImport(true); } })),
        showImport
          ? h(ImportModal, { onState: setSt,
                             onClose: function () { setShowImport(false); } })
          : null,
        evidence
          ? h(EvidenceModal, { ev: evidence,
                               onClose: function () { setEvidence(null); } })
          : null));
  }

  window.__HERMES_PLUGINS__.register("delivery-kit", DeliveryKitPage);
})();
