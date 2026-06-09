"""The flight-recorder page: one self-contained HTML file, no dependencies.

The generator replaces ``__MARROW_TRACE_JSON__`` with the trace JSON (or
``null`` for the standalone drop-zone build served from the docs site). All
trace content is rendered through ``textContent`` — tool results and error
messages are untrusted input and must never reach ``innerHTML``.
"""

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marrow Flight Recorder</title>
<style>
  :root {
    --bg: #14181f; --panel: #1c232e; --panel-2: #232c39; --line: #2c3645;
    --text: #e8edf4; --dim: #93a1b3; --blue: #4f86ff; --blue-deep: #1657f0;
    --green: #34c98e; --amber: #f0b341; --red: #f06a5e; --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  .wrap { max-width: 1080px; margin: 0 auto; padding: 0 20px 70px; }
  header {
    display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap;
    padding: 26px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 24px;
  }
  .mark { font-weight: 800; font-size: 19px; letter-spacing: -0.02em; }
  .mark .dot { display: inline-block; width: 11px; height: 11px; background: var(--blue-deep);
    margin-right: 8px; clip-path: polygon(50% 0, 100% 25%, 100% 75%, 50% 100%, 0 75%, 0 25%); }
  .sub { color: var(--dim); font-size: 13px; text-transform: uppercase; letter-spacing: 0.14em; }
  .spacer { flex: 1; }
  .pill { display: inline-block; padding: 2px 11px; border-radius: 999px; font-size: 12.5px;
    font-weight: 650; border: 1px solid transparent; }
  .pill.ok   { color: var(--green); border-color: var(--green); background: rgba(52,201,142,.09); }
  .pill.warn { color: var(--amber); border-color: var(--amber); background: rgba(240,179,65,.09); }
  .pill.bad  { color: var(--red);   border-color: var(--red);   background: rgba(240,106,94,.09); }
  .pill.info { color: var(--blue);  border-color: var(--blue);  background: rgba(79,134,255,.09); }
  .meta { color: var(--dim); font-size: 13px; font-family: var(--mono); }
  h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.13em; color: var(--dim);
    margin: 30px 0 12px; font-weight: 700; }
  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
  .card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 13px 15px; }
  .card .v { font-size: 22px; font-weight: 750; font-variant-numeric: tabular-nums; }
  .card .l { color: var(--dim); font-size: 12px; margin-top: 2px; }
  table { width: 100%; border-collapse: collapse; background: var(--panel);
    border: 1px solid var(--line); border-radius: 10px; overflow: hidden; font-size: 13.5px; }
  th { text-align: left; color: var(--dim); font-weight: 650; font-size: 12px;
    text-transform: uppercase; letter-spacing: 0.08em; padding: 9px 13px; background: var(--panel-2); }
  td { padding: 8px 13px; border-top: 1px solid var(--line); vertical-align: top; }
  td.mono, .mono { font-family: var(--mono); font-size: 12.5px; }
  details { margin: 2px 0; }
  summary { cursor: pointer; color: var(--blue); font-size: 12.5px; }
  pre { white-space: pre-wrap; word-break: break-word; background: var(--bg);
    border: 1px solid var(--line); border-radius: 7px; padding: 9px 11px; margin: 6px 0 2px;
    font-family: var(--mono); font-size: 12px; color: var(--text); max-height: 260px; overflow: auto; }
  .bar { height: 7px; background: var(--panel-2); border-radius: 99px; overflow: hidden; margin-top: 7px; }
  .bar > i { display: block; height: 100%; background: var(--blue); border-radius: 99px; }
  .bar > i.hot { background: var(--amber); }
  .timeline { list-style: none; margin: 0; padding: 0; border-left: 2px solid var(--line); }
  .timeline li { position: relative; padding: 5px 0 5px 22px; font-size: 13.5px; }
  .timeline li::before { content: ""; position: absolute; left: -6px; top: 12px; width: 10px;
    height: 10px; border-radius: 99px; background: var(--dim); }
  .timeline li.ev-ok::before { background: var(--green); }
  .timeline li.ev-warn::before { background: var(--amber); }
  .timeline li.ev-bad::before { background: var(--red); }
  .timeline li.ev-info::before { background: var(--blue); }
  .timeline .et { font-family: var(--mono); font-weight: 650; margin-right: 8px; }
  .timeline .ed { color: var(--dim); font-family: var(--mono); font-size: 12px; }
  .empty { color: var(--dim); font-size: 13.5px; padding: 14px;
    background: var(--panel); border: 1px dashed var(--line); border-radius: 10px; }
  footer { margin-top: 44px; color: var(--dim); font-size: 12.5px; border-top: 1px solid var(--line);
    padding-top: 14px; }
  footer a { color: var(--blue); text-decoration: none; }
  #drop { margin: 60px auto; max-width: 560px; text-align: center; padding: 56px 30px;
    border: 2px dashed var(--line); border-radius: 14px; color: var(--dim); }
  #drop.hover { border-color: var(--blue); color: var(--text); }
  #drop h1 { font-size: 21px; color: var(--text); margin: 0 0 8px; }
  #drop input { display: none; }
  #drop .btn { display: inline-block; margin-top: 16px; padding: 8px 20px; border-radius: 8px;
    background: var(--blue-deep); color: #fff; font-weight: 650; cursor: pointer; }
  .hidden { display: none; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <span class="mark"><span class="dot"></span>Marrow</span>
    <span class="sub">Flight Recorder</span>
    <span class="spacer"></span>
    <span id="status" class="pill info hidden"></span>
    <span id="traceid" class="meta"></span>
  </header>

  <div id="drop" class="hidden">
    <h1>Open a Marrow trace</h1>
    <p>Drop an <span class="mono">ExecutionTrace</span> or gateway trace JSON here,<br>
       or pick a file. Everything renders locally — nothing is uploaded.</p>
    <label class="btn">Choose trace file<input id="file" type="file" accept=".json,application/json"></label>
  </div>

  <main id="report" class="hidden">
    <div id="headline" class="meta" style="margin-bottom:18px"></div>
    <section><div id="stats" class="cards"></div></section>
    <section id="sec-budget"><h2>Budget</h2><div id="budget" class="cards"></div></section>
    <section id="sec-policies"><h2>Policy decisions</h2><div id="policies"></div></section>
    <section id="sec-tools"><h2>Tool calls</h2><div id="tools"></div></section>
    <section id="sec-providers"><h2>Provider calls</h2><div id="providers"></div></section>
    <section id="sec-events"><h2>Timeline</h2><ul id="events" class="timeline"></ul></section>
    <section id="sec-errors"><h2>Errors</h2><div id="errors"></div></section>
  </main>

  <footer>Recorded by <a href="https://github.com/bencrooks-dev/marrow">Marrow</a> —
    the native runtime and compiler that runs an agent. Traces are evidence: every
    provider call, tool call, policy decision, and budget tick.</footer>
</div>

<script>
window.MARROW_TRACE = __MARROW_TRACE_JSON__;
(function () {
  "use strict";
  var $ = function (sel) { return document.querySelector(sel); };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function statusClass(s) {
    if (s === "completed") return "ok";
    if (s === "error") return "bad";
    if (s === "running") return "info";
    return "warn"; // denied / over_budget / exhausted / upstream_exited
  }

  function fmtMs(ms) {
    if (ms == null) return "—";
    if (ms < 1000) return ms + " ms";
    return (ms / 1000).toFixed(2) + " s";
  }

  function table(headers, rows) {
    if (!rows.length) return el("div", "empty", "none recorded");
    var t = el("table"), thead = el("thead"), tr = el("tr");
    headers.forEach(function (h) { tr.appendChild(el("th", null, h)); });
    thead.appendChild(tr); t.appendChild(thead);
    var tbody = el("tbody");
    rows.forEach(function (cells) {
      var r = el("tr");
      cells.forEach(function (c) {
        var td = el("td");
        if (c && c.nodeType) td.appendChild(c); else { td.textContent = c == null ? "" : c; td.className = "mono"; }
        r.appendChild(td);
      });
      tbody.appendChild(r);
    });
    t.appendChild(tbody);
    return t;
  }

  function pill(text, cls) { return el("span", "pill " + cls, text); }

  function expandable(label, content) {
    var d = el("details"), s = el("summary", null, label), p = el("pre", null, content || "");
    d.appendChild(s); d.appendChild(p);
    return d;
  }

  function statCard(value, label) {
    var c = el("div", "card");
    c.appendChild(el("div", "v", value));
    c.appendChild(el("div", "l", label));
    return c;
  }

  function budgetCard(label, used, limit) {
    var c = el("div", "card");
    var shown = limit == null ? String(used) : used + " / " + limit;
    c.appendChild(el("div", "v", shown));
    c.appendChild(el("div", "l", label));
    if (limit != null && limit > 0) {
      var frac = Math.min(1, used / limit);
      var bar = el("div", "bar"), fill = el("i", frac >= 0.85 ? "hot" : null);
      fill.style.width = (frac * 100).toFixed(1) + "%";
      bar.appendChild(fill); c.appendChild(bar);
    }
    return c;
  }

  function eventClass(type) {
    if (/denied|rejected|invalid|exceeded|budget_block/.test(type)) return "ev-warn";
    if (/error|exited/.test(type)) return "ev-bad";
    if (/called|completed|listed|initialized|forwarded/.test(type)) return "ev-ok";
    return "ev-info";
  }

  function render(t) {
    $("#report").classList.remove("hidden");
    $("#drop").classList.add("hidden");
    var gateway = typeof t.schema === "string" && t.schema.indexOf("marrow.gateway_trace") === 0;

    var status = $("#status");
    status.classList.remove("hidden");
    status.className = "pill " + statusClass(t.final_status);
    status.textContent = t.final_status || "unknown";
    $("#traceid").textContent = t.trace_id || "";

    var dur = (t.completed_at != null && t.started_at != null) ? t.completed_at - t.started_at : null;
    var bits = [];
    if (gateway) {
      bits.push("gateway: " + (t.gateway || ""));
      var up = t.upstream || {};
      if (up.server_info) bits.push("upstream: " + up.server_info.name + " " + (up.server_info.version || ""));
      if (up.protocol_version) bits.push("mcp " + up.protocol_version);
    } else {
      if (t.runtime_plan_id) bits.push("plan: " + t.runtime_plan_id);
      if (t.input != null) bits.push("input: " + JSON.stringify(t.input));
    }
    if (t.started_at) bits.push(new Date(t.started_at).toISOString());
    if (dur != null) bits.push("duration " + fmtMs(dur));
    $("#headline").textContent = bits.join("   ·   ");

    var stats = $("#stats");
    var tools = t.tool_calls || [], pols = t.policy_decisions || [], errs = t.errors || [];
    if (gateway) {
      var used = (t.budget && t.budget.used) || {};
      stats.appendChild(statCard(used.calls != null ? used.calls : tools.length, "tool calls allowed"));
      stats.appendChild(statCard(used.denied || 0, "calls denied"));
      stats.appendChild(statCard((t.tools_visible || []).length, "tools visible"));
      stats.appendChild(statCard((t.tools_hidden || []).length, "tools hidden"));
      stats.appendChild(statCard(errs.length, "errors"));
    } else {
      var u = t.budget_usage || {};
      stats.appendChild(statCard(u.steps != null ? u.steps : "—", "steps"));
      stats.appendChild(statCard(u.total_tokens != null ? u.total_tokens : "—", "tokens"));
      stats.appendChild(statCard(u.cost_usd != null ? "$" + u.cost_usd : "—", "cost"));
      stats.appendChild(statCard(tools.length, "tool calls"));
      stats.appendChild(statCard(pols.length, "policy decisions"));
      stats.appendChild(statCard(errs.length, "errors"));
    }

    var budget = $("#budget");
    if (gateway && t.budget) {
      var lim = t.budget.limits || {}, us = t.budget.used || {};
      budget.appendChild(budgetCard("calls", us.calls || 0, lim.max_calls));
      budget.appendChild(budgetCard("wall clock (ms)", us.elapsed_ms || 0, lim.max_wall_ms));
    } else if (!gateway && t.budget_usage) {
      var bu = t.budget_usage;
      budget.appendChild(budgetCard("steps", bu.steps || 0, null));
      budget.appendChild(budgetCard("prompt tokens", bu.prompt_tokens || 0, null));
      budget.appendChild(budgetCard("completion tokens", bu.completion_tokens || 0, null));
      budget.appendChild(budgetCard("cost (usd)", bu.cost_usd || 0, null));
    } else {
      $("#sec-budget").classList.add("hidden");
    }

    $("#policies").appendChild(table(
      ["action", "decision", "outcome", "flags"],
      pols.map(function (d) {
        var flags = [];
        if (d.approval_required) flags.push("approval");
        if (d.evidence_required) flags.push("evidence");
        return [d.action, d.decision,
          pill(d.allowed ? "allowed" : "blocked", d.allowed ? "ok" : "bad"),
          flags.join(", ")];
      })
    ));

    $("#tools").appendChild(table(
      gateway ? ["tool", "outcome", "elapsed", "detail"] : ["tool", "outcome", "detail"],
      tools.map(function (c) {
        var detail = el("div");
        if (c.arguments) detail.appendChild(expandable("arguments", c.arguments));
        if (c.result) detail.appendChild(expandable("result", c.result));
        var row = [c.tool, pill(c.ok ? "ok" : "failed", c.ok ? "ok" : "bad")];
        if (gateway) row.push(fmtMs(c.elapsed_ms));
        row.push(detail);
        return row;
      })
    ));

    var provs = t.provider_calls || [];
    if (gateway || !provs.length) {
      if (!provs.length) $("#sec-providers").classList.add("hidden");
    }
    if (provs.length) {
      $("#providers").appendChild(table(
        ["agent", "provider", "model", "prompt tokens", "completion tokens"],
        provs.map(function (p) {
          return [p.agent, p.provider, p.model, p.prompt_tokens, p.completion_tokens];
        })
      ));
    }

    var evs = t.events || [];
    var list = $("#events");
    if (!evs.length) {
      $("#sec-events").classList.add("hidden");
    }
    evs.forEach(function (e) {
      var li = el("li", eventClass(e.type || ""));
      li.appendChild(el("span", "et", e.type || "event"));
      var extra = Object.keys(e).filter(function (k) { return k !== "type"; })
        .map(function (k) { return k + "=" + e[k]; }).join("  ");
      li.appendChild(el("span", "ed", extra));
      list.appendChild(li);
    });

    if (!errs.length) {
      $("#sec-errors").classList.add("hidden");
    } else {
      $("#errors").appendChild(table(
        ["kind", "message"],
        errs.map(function (e) { return [e.kind || e.agent || "", e.message || ""]; })
      ));
    }
  }

  function initDrop() {
    var drop = $("#drop");
    drop.classList.remove("hidden");
    function load(file) {
      var reader = new FileReader();
      reader.onload = function () {
        try { render(JSON.parse(reader.result)); }
        catch (err) { alert("Not a valid Marrow trace: " + err.message); }
      };
      reader.readAsText(file);
    }
    drop.addEventListener("dragover", function (e) { e.preventDefault(); drop.classList.add("hover"); });
    drop.addEventListener("dragleave", function () { drop.classList.remove("hover"); });
    drop.addEventListener("drop", function (e) {
      e.preventDefault(); drop.classList.remove("hover");
      if (e.dataTransfer.files.length) load(e.dataTransfer.files[0]);
    });
    $("#file").addEventListener("change", function (e) {
      if (e.target.files.length) load(e.target.files[0]);
    });
  }

  if (window.MARROW_TRACE) render(window.MARROW_TRACE); else initDrop();
})();
</script>
</body>
</html>
"""
