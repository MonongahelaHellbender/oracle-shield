#!/usr/bin/env python3
"""oracle-shield web UI — a tiny local page: type claims, get verdicts + an honest coverage report.

No web framework. Standard library only; reuses the oracle_shield engine (so still just needs sympy).

    python oracle_web.py            # local only, open http://localhost:8000
    python oracle_web.py --lan      # also reachable from your phone on the same wifi

Type one claim per line in the box and click Check. Each claim is routed to a sound oracle and you get
SUPPORTED / REFUTED / DEFERRED plus the coverage denominator most evals hide.
"""
import html
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

from oracle_shield import report, SUPPORTED, REFUTED, DEFERRED

PORT = 8000

EXAMPLE = "\n".join([
    "Is 561 prime?",
    "Is 2147483647 prime?",
    "sqrt(2)+sqrt(3) = sqrt(5+2*sqrt(6))",
    "n^5 ≡ n (mod 5)",
    "evidence: observational_study claim: causes",
    "This model is safe to deploy.",
])

_BADGE = {
    SUPPORTED: ("✓ SUPPORTED", "#1a7f37", "#dafbe1"),
    REFUTED:   ("✗ REFUTED",   "#cf222e", "#ffebe9"),
    DEFERRED:  ("· DEFERRED",  "#57606a", "#eaeef2"),
}

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>oracle-shield</title>
<style>
  :root {{ font-family: -apple-system, system-ui, sans-serif; }}
  body {{ max-width: 820px; margin: 2rem auto; padding: 0 1rem; color: #1f2328; }}
  h1 {{ margin-bottom: .2rem; }}
  p.sub {{ color: #57606a; margin-top: 0; }}
  textarea {{ width: 100%; min-height: 150px; font: 14px/1.5 ui-monospace, Menlo, monospace;
             padding: .7rem; border: 1px solid #d0d7de; border-radius: 8px; box-sizing: border-box; }}
  button {{ margin-top: .6rem; padding: .55rem 1.3rem; font-size: 15px; font-weight: 600; color: #fff;
           background: #1f6feb; border: 0; border-radius: 8px; cursor: pointer; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1.4rem; }}
  td, th {{ text-align: left; padding: .5rem .6rem; border-bottom: 1px solid #eaeef2; vertical-align: top; }}
  th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .04em; color: #57606a; }}
  .badge {{ display: inline-block; padding: .1rem .5rem; border-radius: 6px; font-size: 12px;
           font-weight: 700; white-space: nowrap; }}
  .claim {{ font: 13px ui-monospace, Menlo, monospace; }}
  .why {{ color: #57606a; font-size: 12px; }}
  .cov {{ margin-top: 1.4rem; padding: .9rem 1.1rem; background: #f6f8fa; border: 1px solid #d0d7de;
         border-radius: 8px; font-size: 14px; }}
  .cov b {{ font-size: 22px; }}
  .foot {{ margin-top: 2rem; color: #8b949e; font-size: 12px; }}
</style></head>
<body>
  <h1>oracle-shield</h1>
  <p class="sub">Route a claim to a sound oracle &mdash; get a verdict, its trust basis, and an honest
     coverage report. One claim per line.</p>
  <form method="post">
    <textarea name="claims" placeholder="One claim per line...">{claims}</textarea><br>
    <button type="submit">Check</button>
  </form>
  {results}
  <p class="foot">Trust lives in the oracles; the router is untrusted &mdash; a misroute or an unknown claim
     becomes DEFERRED, never a wrong verdict. Coverage measured on the input as given.</p>
</body></html>"""


def render_results(claims):
    rep = report(claims)
    rows = []
    for r in rep["records"]:
        label, fg, bg = _BADGE[r["verdict"]]
        lane = html.escape(r["oracle"]) if r["covered"] else "uncovered"
        why = html.escape(r["why"]) if r["covered"] else "no oracle covers this"
        rows.append(
            f'<tr><td><span class="badge" style="color:{fg};background:{bg}">{label}</span></td>'
            f'<td class="claim">{html.escape(str(r["claim"]))}</td>'
            f'<td>{lane}<div class="why">{why}</div></td></tr>'
        )
    n, c = rep["n_claims"], rep["checkable"]
    pct = f"{rep['checkable_fraction'] * 100:.0f}%"
    cov = (
        f'<div class="cov"><b>{c}/{n}</b> checkable ({pct}) &mdash; '
        f'{rep["adjudicated"]} got a definite verdict, '
        f'{n - c} uncovered (the shield\'s holes, counted honestly).</div>'
    )
    table = (
        '<table><tr><th>verdict</th><th>claim</th><th>oracle &amp; basis</th></tr>'
        + "".join(rows) + "</table>"
    )
    return cov + table


class Handler(BaseHTTPRequestHandler):
    def _send(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def do_GET(self):
        self._send(PAGE.format(claims=html.escape(EXAMPLE), results=""))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        text = parse_qs(raw).get("claims", [""])[0]
        claims = [ln.strip() for ln in text.splitlines() if ln.strip()]
        results = render_results(claims) if claims else ""
        self._send(PAGE.format(claims=html.escape(text), results=results))

    def log_message(self, *_):  # quiet console
        pass


if __name__ == "__main__":
    host = "0.0.0.0" if "--lan" in sys.argv else "127.0.0.1"
    server = HTTPServer((host, PORT), Handler)
    where = f"http://localhost:{PORT}" if host == "127.0.0.1" else f"http://<your-mac-ip>:{PORT}"
    print(f"oracle-shield web UI running at {where}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
