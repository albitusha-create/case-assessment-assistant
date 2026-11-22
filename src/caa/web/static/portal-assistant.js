/*
 * Case Assessment Assistant panel for the agency portal's assessment form.
 *
 * The portal hosts this script on its form page. It adds "Check with assistant"
 * under each section the assistant may review, sends the worker's current text
 * to our API, and shows the results under the field: rule checks, QA checklist
 * findings with their sources, and facts from the case documents the worker can
 * insert. It never saves or submits the form; the worker does that.
 *
 * Plain JavaScript, no build step. Model output is shown with textContent only.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var caseId = script && script.dataset.caseId;
  if (!caseId) return;
  var base = "/api/assist/cases/" + encodeURIComponent(caseId) + "/sections/";

  var css = [
    ".caa-bar{display:flex;align-items:center;gap:8px;margin-top:4px;font:13px/1.4 'Segoe UI',system-ui,-apple-system,Arial,sans-serif}",
    ".caa-btn{font:inherit;font-weight:600;color:#fff;background:#0f6cbd;border:1px solid #0f6cbd;border-radius:4px;padding:3px 10px;cursor:pointer}",
    ".caa-btn:hover{background:#115ea3}.caa-btn[disabled]{opacity:.6;cursor:default}",
    ".caa-btn-sec{color:#1f2328;background:#fff;border-color:#d0d7de;font-weight:400;padding:1px 8px}",
    ".caa-btn-sec:hover{background:#eef1f4}",
    ".caa-tag{font-size:11px;font-weight:600;color:#57606a;letter-spacing:.02em}",
    ".caa-status{color:#57606a}.caa-stale{color:#8a5300}",
    ".caa-panel{margin-top:6px;border:1px solid #d0d7de;border-left:3px solid #0f6cbd;border-radius:4px;background:#fff;color:#1f2328;font:13px/1.45 'Segoe UI',system-ui,-apple-system,Arial,sans-serif}",
    ".caa-head{display:flex;justify-content:space-between;gap:8px;padding:6px 10px;border-bottom:1px solid #e4e7eb;background:#f6f7f9}",
    ".caa-head b{font-weight:600}.caa-head span{color:#57606a;font-size:12px}",
    ".caa-sec{padding:6px 10px}.caa-sec+.caa-sec{border-top:1px solid #e4e7eb}",
    ".caa-sec h4{margin:0 0 4px;font-size:12px;font-weight:600;color:#57606a;text-transform:uppercase;letter-spacing:.03em}",
    ".caa-item{display:grid;grid-template-columns:64px 1fr;gap:8px;padding:3px 0}",
    ".caa-res{font-size:12px;font-weight:600}",
    ".caa-pass{color:#0e7a0d}.caa-review{color:#8a5300}.caa-fail{color:#b42318}",
    ".caa-kind{color:#6e7781;font-size:12px}",
    ".caa-item ul{margin:2px 0 0;padding-left:16px}",
    ".caa-src{font-size:12px;color:#57606a}.caa-src a{color:#0f6cbd}",
    ".caa-sug{display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start;padding:4px 0}",
    ".caa-sug+.caa-sug{border-top:1px dashed #e4e7eb}",
    ".caa-empty{color:#57606a}",
    ".caa-err{color:#b42318}"
  ].join("\n");
  var style = document.createElement("style");
  style.textContent = css;
  document.head.appendChild(style);

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function docLabel(docId) {
    var words = docId.split("-").filter(function (w) { return !/^\d+$/.test(w); }).join(" ");
    return words ? words.charAt(0).toUpperCase() + words.slice(1) : docId;
  }

  function sourceLinks(sources) {
    var wrap = el("div", "caa-src");
    if (!sources.length) return null;
    wrap.appendChild(document.createTextNode("Source: "));
    sources.forEach(function (s, i) {
      if (i) wrap.appendChild(document.createTextNode("; "));
      var a = el("a", "", docLabel(s.doc_id) + ", p. " + s.page);
      a.href = "/portal/cases/" + encodeURIComponent(caseId) + "/documents/" +
        encodeURIComponent(s.doc_id) + "#page=" + s.page;
      a.target = "_blank";
      a.rel = "noopener";
      wrap.appendChild(a);
    });
    return wrap;
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(body)
    });
  }

  function render(panel, data, textarea, section) {
    panel.replaceChildren();
    var open = data.results.filter(function (r) { return !r.passed; }).length;
    var head = el("div", "caa-head");
    head.appendChild(el("b", "", "Assistant check: " + section.title));
    head.appendChild(el("span", "", open ? open + " to review. Advice only; you decide." :
      "Nothing to review. Advice only; you decide."));
    panel.appendChild(head);

    var checks = el("div", "caa-sec");
    checks.appendChild(el("h4", "", "QA checklist"));
    data.results.forEach(function (r) {
      var row = el("div", "caa-item");
      var cls = r.passed ? "caa-pass" : (r.severity === "blocking" ? "caa-fail" : "caa-review");
      row.appendChild(el("div", "caa-res " + cls, r.passed ? "Pass" : "Review"));
      var body = el("div");
      body.appendChild(document.createTextNode(r.description + " "));
      body.appendChild(el("span", "caa-kind", r.checked_by === "rule" ? "(rule in code)" : "(AI reviewer)"));
      if (r.findings.length) {
        var ul = el("ul");
        r.findings.forEach(function (f) {
          var li = el("li", "", f.text);
          var src = sourceLinks(f.sources);
          if (src) li.appendChild(src);
          ul.appendChild(li);
        });
        body.appendChild(ul);
      }
      row.appendChild(body);
      checks.appendChild(row);
    });
    panel.appendChild(checks);

    var sug = el("div", "caa-sec");
    sug.appendChild(el("h4", "", "From the case documents, not in your text yet"));
    if (!data.suggestions.length) {
      sug.appendChild(el("div", "caa-empty", "No missing facts found for this section."));
    }
    data.suggestions.forEach(function (s) {
      var row = el("div", "caa-sug");
      var body = el("div", "", s.text);
      body.appendChild(sourceLinks([s.source]));
      var btn = el("button", "caa-btn caa-btn-sec", "Insert");
      btn.type = "button";
      btn.addEventListener("click", function () {
        var current = textarea.value.replace(/\s+$/, "");
        textarea.value = current ? current + " " + s.text : s.text;
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        btn.disabled = true;
        btn.textContent = "Inserted";
        post(base + encodeURIComponent(section.id) + "/inserted",
          { doc_id: s.source.doc_id, page: s.source.page }).catch(function () {});
      });
      row.appendChild(body);
      row.appendChild(btn);
      sug.appendChild(row);
    });
    panel.appendChild(sug);
  }

  function attach(section) {
    var textarea = document.querySelector('textarea[name="domain_' + section.id + '"]');
    if (!textarea || textarea.closest("fieldset[disabled]")) return;
    var bar = el("div", "caa-bar");
    var btn = el("button", "caa-btn", "Check with assistant");
    btn.type = "button";
    var status = el("span", "caa-status");
    bar.appendChild(btn);
    bar.appendChild(el("span", "caa-tag", "CASE ASSESSMENT ASSISTANT"));
    bar.appendChild(status);
    var panel = el("div", "caa-panel");
    panel.hidden = true;
    textarea.insertAdjacentElement("afterend", bar);
    bar.insertAdjacentElement("afterend", panel);
    var checkedText = null;

    textarea.addEventListener("input", function () {
      if (checkedText !== null && textarea.value !== checkedText) {
        status.className = "caa-stale";
        status.textContent = "Text changed since the last check.";
      }
    });

    btn.addEventListener("click", function () {
      btn.disabled = true;
      status.className = "caa-status";
      status.textContent = "Checking against this case's documents...";
      var sent = textarea.value;
      post(base + encodeURIComponent(section.id) + "/check", { text: sent })
        .then(function (r) {
          return r.json().then(function (body) {
            if (!r.ok) throw new Error(body.detail || "The assistant could not check this section.");
            return body;
          });
        })
        .then(function (data) {
          checkedText = sent;
          status.textContent = "";
          render(panel, data, textarea, section);
          panel.hidden = false;
        })
        .catch(function (err) {
          status.className = "caa-err";
          status.textContent = String(err.message || err);
        })
        .finally(function () { btn.disabled = false; });
    });
  }

  fetch("/api/assist/cases/" + encodeURIComponent(caseId) + "/sections", {
    headers: { "Accept": "application/json" },
    credentials: "same-origin"
  })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (data) { if (data) data.sections.forEach(attach); })
    .catch(function () { /* The portal form works the same without the assistant. */ });
})();
