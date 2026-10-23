/*
 * CivicGraph embeddable chatbot widget.
 *
 * Usage on any website (municipal pages, intranets):
 *
 *   <script
 *     src="http://your-portal-host/embed.js"
 *     data-api-base="http://your-api-host:8000"
 *     data-title="City Assistant"
 *     data-accent="#1a4274"
 *     data-greeting="Ask me about municipal by-laws."
 *   ></script>
 *
 * All configuration is optional; defaults suit local development.
 * The widget renders inside a shadow root so host-page CSS cannot break it.
 */
(function () {
  "use strict";

  var script =
    document.currentScript ||
    (function () {
      var s = document.getElementsByTagName("script");
      return s[s.length - 1];
    })();
  var ds = (script && script.dataset) || {};
  var API_BASE = ds.apiBase || "http://localhost:8000";
  var TITLE = ds.title || "City Assistant";
  var ACCENT = ds.accent || "#1a4274";
  var GREETING =
    ds.greeting ||
    "Ask me anything about municipal by-laws. Every answer cites the exact section in force.";

  var SVG_CHAT =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z"/></svg>';
  var SVG_CLOSE =
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
  var SVG_SEND =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/></svg>';

  var host = document.createElement("div");
  host.id = "civic-embed-root";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });

  var style = document.createElement("style");
  style.textContent =
    ":host{all:initial}" +
    "*{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif}" +
    ".bubble{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:0;color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(0,0,0,.28);z-index:2147483000;transition:transform .15s ease}" +
    ".bubble:hover{transform:scale(1.06)}" +
    ".panel{position:fixed;right:20px;bottom:88px;width:380px;max-width:calc(100vw - 40px);height:540px;max-height:calc(100vh - 120px);background:#fff;border-radius:14px;box-shadow:0 24px 64px rgba(0,0,0,.30);display:flex;flex-direction:column;overflow:hidden;z-index:2147483000}" +
    ".panel[hidden]{display:none}" +
    ".head{padding:12px 16px;color:#fff}.head h2{margin:0;font-size:14px;font-weight:600}.head p{margin:2px 0 0;font-size:11px;opacity:.85}" +
    ".msgs{flex:1;overflow-y:auto;background:#f8fafc;padding:14px;display:flex;flex-direction:column;gap:10px}" +
    ".msg{max-width:88%;padding:8px 12px;border-radius:14px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}" +
    ".msg.user{align-self:flex-end;background:" + ACCENT + ";color:#fff;border-bottom-right-radius:4px}" +
    ".msg.bot{align-self:flex-start;background:#fff;border:1px solid #e2e8f0;color:#1e293b;border-bottom-left-radius:4px}" +
    ".notice{margin-top:8px;padding:8px;border:1px solid #fcd34d;background:#fffbeb;color:#78350f;border-radius:8px;font-size:12px}" +
    ".cites{margin-top:6px;font-size:11px;color:#64748b}.cites a{color:#1f4f8b;text-decoration:underline}" +
    ".form{display:flex;gap:8px;padding:10px;border-top:1px solid #e2e8f0;background:#fff}" +
    ".form input{flex:1;border:1px solid #cbd5e1;border-radius:8px;padding:8px 10px;font-size:13px;outline:none}" +
    ".form input:focus{border-color:" + ACCENT + ";box-shadow:0 0 0 3px rgba(26,66,116,.12)}" +
    ".form button{border:0;border-radius:8px;background:" + ACCENT + ";color:#fff;padding:8px 12px;cursor:pointer;display:flex;align-items:center}" +
    ".form button:disabled{opacity:.5;cursor:default}" +
    ".foot{padding:4px 0 8px;text-align:center;font-size:10px;color:#94a3b8;background:#fff}";
  root.appendChild(style);

  var bubble = document.createElement("button");
  bubble.className = "bubble";
  bubble.style.background = ACCENT;
  bubble.setAttribute("aria-label", "Open assistant");
  bubble.innerHTML = SVG_CHAT;
  root.appendChild(bubble);

  var panel = document.createElement("div");
  panel.className = "panel";
  panel.hidden = true;
  panel.innerHTML =
    '<div class="head" style="background:' + ACCENT + '"><h2></h2><p>Cited answers from the municipal code</p></div>' +
    '<div class="msgs" role="log" aria-live="polite"></div>' +
    '<form class="form"><input type="text" maxlength="2000" placeholder="Ask about a by-law..." aria-label="Your question"/><button type="submit" aria-label="Send">' + SVG_SEND + "</button></form>" +
    '<div class="foot">Informational only - not legal advice.</div>';
  root.appendChild(panel);
  panel.querySelector(".head h2").textContent = TITLE;

  var msgs = panel.querySelector(".msgs");
  var form = panel.querySelector(".form");
  var input = panel.querySelector("input");
  var sendBtn = form.querySelector("button");
  var history = [];
  var greeted = false;
  var busy = false;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function addUser(text) {
    msgs.appendChild(el("div", "msg user", text));
    msgs.scrollTop = msgs.scrollHeight;
  }

  function addBot() {
    var m = el("div", "msg bot", "");
    var content = el("div", "bot-content", "");
    var wm = el("div", "bot-watermark", "CIVICGRAPH");
    wm.style.cssText = "text-align:right;font-size:9px;color:#cbd5e1;font-weight:600;letter-spacing:0.05em;margin-top:4px;";
    m.appendChild(content);
    m.appendChild(wm);
    msgs.appendChild(m);
    msgs.scrollTop = msgs.scrollHeight;
    return m;
  }

  function renderCitations(container, sources) {
    if (!sources || !sources.length) return;
    var box = el("div", "cites");
    sources.forEach(function (s) {
      var line = el("div", null, s.instrument.title + ", s. " + s.article.number + " ");
      if (s.url) {
        var a = document.createElement("a");
        a.href = s.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "source";
        line.appendChild(a);
      }
      box.appendChild(line);
    });
    container.appendChild(box);
    msgs.scrollTop = msgs.scrollHeight;
  }

  function setBusy(v) {
    busy = v;
    sendBtn.disabled = v;
  }

  function ask(question) {
    addUser(question);
    var bot = addBot();
    var noticeBox = null;
    setBusy(true);

    var payload = JSON.stringify({
      question: question,
      locale: (navigator.language || "en").slice(0, 2),
      history: history.slice(-6),
    });

    fetch(API_BASE + "/v1/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
    })
      .then(function (res) {
        if (!res.ok || !res.body) throw new Error("unavailable");
        var reader = res.body.getReader();
        var dec = new TextDecoder();
        var buf = "";
        var eventName = "";

        function handle(data) {
          if (eventName === "token" && data.text) {
            var c = bot.querySelector(".bot-content") || bot;
            c.textContent = (c.textContent + data.text).replace(/(?:\[|【)\s*\d{1,3}\s*(?:\]|】)/g, "");
            msgs.scrollTop = msgs.scrollHeight;
          } else if (eventName === "notice" && data.text) {
            noticeBox = el("div", "notice", data.text);
            bot.appendChild(noticeBox);
          } else if (eventName === "citations") {
            renderCitations(bot, data.sources || []);
          }
        }

        function pump() {
          return reader.read().then(function (r) {
            if (r.done) return;
            buf += dec.decode(r.value, { stream: true });
            var sep;
            while ((sep = buf.indexOf("\n\n")) !== -1) {
              var block = buf.slice(0, sep);
              buf = buf.slice(sep + 2);
              eventName = "";
              var dataLine = "";
              block.split("\n").forEach(function (line) {
                if (line.indexOf("event: ") === 0) eventName = line.slice(7).trim();
                else if (line.indexOf("data: ") === 0) dataLine = line;
              });
              if (dataLine) {
                try {
                  handle(JSON.parse(dataLine.slice(6)));
                } catch (e) {
                  /* skip malformed frame */
                }
              }
            }
            return pump();
          });
        }

        return pump();
      })
      .catch(function () {
        bot.textContent = "";
        bot.appendChild(
          el("div", "notice", "The assistant is temporarily unavailable. Please retry shortly.")
        );
      })
      .then(function () {
        setBusy(false);
        input.focus();
        history.push({ role: "user", content: question });
        history.push({ role: "assistant", content: bot.textContent });
        if (history.length > 12) history.splice(0, history.length - 12);
      });
  }

  function setOpen(v) {
    panel.hidden = !v;
    bubble.setAttribute("aria-label", v ? "Close assistant" : "Open assistant");
    bubble.innerHTML = v ? SVG_CLOSE : SVG_CHAT;
    if (v) {
      if (!greeted) {
        addBot().textContent = GREETING;
        greeted = true;
      }
      input.focus();
    }
  }

  bubble.addEventListener("click", function () {
    setOpen(panel.hidden);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") setOpen(false);
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = input.value.trim();
    if (q.length < 3 || busy) return;
    input.value = "";
    ask(q);
  });
})();
