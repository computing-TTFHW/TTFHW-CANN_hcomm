#!/usr/bin/env python3
import argparse
import html
import json
from pathlib import Path


def fmt_seconds(value):
    if value is None:
        return "-"
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    minutes = int(value // 60)
    seconds = value - minutes * 60
    if minutes > 0:
        return f"{minutes}m {seconds:.1f}s"
    return f"{seconds:.3f}s"


def esc(value):
    if value is None:
        return "-"
    return html.escape(str(value))


def render_kv_rows(mapping):
    rows = []
    for key, value in mapping.items():
        rows.append(
            f"<tr><th>{esc(key)}</th><td>{esc(value)}</td></tr>"
        )
    return "\n".join(rows)


def render_steps(steps, total_seconds):
    rows = []
    total = float(total_seconds or 0) or 1.0
    for step in steps:
        width = max(1.5, min(100.0, float(step.get("seconds", 0)) / total * 100.0))
        rows.append(
            "<tr>"
            f"<td>{esc(step.get('name'))}</td>"
            f"<td>{esc(step.get('status'))}</td>"
            f"<td>{fmt_seconds(step.get('seconds'))}</td>"
            f"<td><div class='bar-wrap'><div class='bar' style='width:{width:.2f}%'></div></div></td>"
            f"<td><code>{esc(step.get('command'))}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html(data, source_json):
    result = data.get("result", {})
    status = data.get("status", "-")
    status_class = "success" if status == "success" else "failed"
    summary_cards = [
        ("Metric", data.get("metric") or data.get("scenario")),
        ("Status", data.get("status")),
        ("Total", fmt_seconds(data.get("total_seconds") or data.get("ttfhw_seconds"))),
        ("First Run", fmt_seconds(result.get("first_run_seconds"))),
        ("Incremental", fmt_seconds(result.get("incremental_run_seconds"))),
        ("Execution", data.get("execution_mode")),
        ("Branch", data.get("git", {}).get("branch")),
        ("Dirty", data.get("git", {}).get("dirty")),
    ]
    cards_html = "\n".join(
        "<div class='card'>"
        f"<div class='card-label'>{esc(label)}</div>"
        f"<div class='card-value'>{esc(value)}</div>"
        "</div>"
        for label, value in summary_cards
    )

    env_table = render_kv_rows(data.get("environment", {}))
    git_table = render_kv_rows(data.get("git", {}))

    ccache = data.get("ccache", {})
    ccache_table = render_kv_rows(
        {
            "cache_hit_direct": ccache.get("cache_hit_direct", "-"),
            "cache_hit_preprocessed": ccache.get("cache_hit_preprocessed", "-"),
            "cache_miss": ccache.get("cache_miss", "-"),
            "hit_rate": ccache.get("hit_rate", "-"),
        }
    )

    raw_json = html.escape(json.dumps(data, indent=2, ensure_ascii=False))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HCOMM TTFHW View</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --panel: #fffaf0;
      --ink: #1e1d1b;
      --muted: #6b665e;
      --line: #d7ccba;
      --accent: #0f766e;
      --accent-2: #b45309;
      --fail: #b42318;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Source Sans 3", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(180,83,9,0.12), transparent 28%),
        radial-gradient(circle at left center, rgba(15,118,110,0.12), transparent 35%),
        var(--bg);
    }}
    .page {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    .lede {{
      margin: 10px 0 24px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .status {{
      display: inline-block;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(15,118,110,0.12);
      color: var(--accent);
    }}
    .status.failed {{
      background: rgba(180,35,24,0.12);
      color: var(--fail);
    }}
    .grid {{
      display: grid;
      gap: 16px;
    }}
    .cards {{
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      margin: 22px 0 28px;
    }}
    .card, .panel, .phase-card {{
      background: rgba(255,250,240,0.86);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 12px 32px rgba(30,29,27,0.05);
    }}
    .card {{
      padding: 16px;
      min-height: 104px;
    }}
    .card-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 10px;
    }}
    .card-value {{
      font-size: 24px;
      font-weight: 700;
      word-break: break-word;
    }}
    .two-col {{
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      margin-bottom: 18px;
    }}
    .panel {{
      padding: 18px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      width: 180px;
      color: var(--muted);
      font-weight: 600;
    }}
    .steps th, .steps td {{ width: auto; }}
    .steps thead th {{
      color: var(--ink);
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .bar-wrap {{
      width: 100%;
      min-width: 160px;
      height: 10px;
      border-radius: 999px;
      background: rgba(15,118,110,0.12);
      overflow: hidden;
    }}
    .bar {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      border-radius: 999px;
    }}
    code, pre {{
      font-family: "IBM Plex Mono", "SFMono-Regular", monospace;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: rgba(30,29,27,0.04);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 14px;
      max-height: 480px;
      overflow: auto;
    }}
    .muted {{ color: var(--muted); }}
    .path {{
      display: inline-block;
      margin-top: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      background: rgba(30,29,27,0.04);
      border: 1px solid var(--line);
      font-family: "IBM Plex Mono", monospace;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="status {status_class}">{esc(status)}</div>
    <h1>HCOMM TTFHW Visualization</h1>
    <p class="lede">
      Metric <strong>{esc(data.get("metric") or data.get("scenario"))}</strong> from <strong>{esc(data.get("started_at"))}</strong>
      to <strong>{esc(data.get("ended_at"))}</strong>. Source JSON:
      <span class="path">{esc(source_json)}</span>
    </p>

    <section class="grid cards">
      {cards_html}
    </section>

    <section class="grid two-col">
      <div class="panel">
        <h2>Environment</h2>
        <table>{env_table}</table>
      </div>
      <div class="panel">
        <h2>Git</h2>
        <table>{git_table}</table>
      </div>
    </section>

    <section class="panel" style="margin: 18px 0;">
      <h2>Steps</h2>
      <table class="steps">
        <thead>
          <tr>
            <th>Step</th>
            <th>Status</th>
            <th>Duration</th>
            <th>Share</th>
            <th>Command</th>
          </tr>
        </thead>
        <tbody>
          {render_steps(data.get("steps", []), data.get("total_seconds") or data.get("ttfhw_seconds"))}
        </tbody>
      </table>
    </section>

    <section class="grid two-col">
      <div class="panel">
        <h2>ccache</h2>
        <table>{ccache_table}</table>
        <h3 style="margin-top:16px;">After Incremental Run</h3>
        <pre>{esc(ccache.get("after_incremental_run", ccache.get("stats_after", "")))}</pre>
      </div>
      <div class="panel">
        <h2>Raw JSON</h2>
        <pre>{raw_json}</pre>
      </div>
    </section>
  </div>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="Render a TTFHW JSON file into a standalone HTML page.")
    parser.add_argument("json_path")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    json_path = Path(args.json_path).resolve()
    data = json.loads(json_path.read_text(encoding="utf-8"))

    if args.output:
        output_path = Path(args.output).resolve()
    else:
        root = json_path.parents[1]
        output_path = root / "visualizations" / f"{json_path.stem}.html"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(data, str(json_path)), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
