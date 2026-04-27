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


def step_by_name(data, name):
    for step in data.get("steps", []):
        if step.get("name") == name:
            return step
    return {}


def render_steps(steps):
    rows = []
    for step in steps:
        rows.append(
            "<tr>"
            f"<td>{esc(step.get('name'))}</td>"
            f"<td><span class='pill {esc(step.get('status'))}'>{esc(step.get('status'))}</span></td>"
            f"<td>{fmt_seconds(step.get('seconds'))}</td>"
            f"<td><code>{esc(step.get('command'))}</code></td>"
            "</tr>"
        )
    return "\n".join(rows)


def run_card(title, step, seconds, command, empty_text):
    status = step.get("status") or ("not-run" if seconds is None else "-")
    return f"""
      <article class="run-card">
        <div class="run-top">
          <span class="run-title">{esc(title)}</span>
          <span class="pill {esc(status)}">{esc(status)}</span>
        </div>
        <div class="duration">{fmt_seconds(seconds)}</div>
        <div class="command"><code>{esc(command if seconds is not None else empty_text)}</code></div>
      </article>
    """


def render_failure_analysis(data):
    analysis = data.get("failure_analysis")
    if not analysis:
        failure = data.get("error")
        if not failure:
            return ""
        return f"""
    <section id="failure-analysis" class="panel failure">
      <h2>Failure</h2>
      <p>{esc(failure)}</p>
    </section>
        """

    evidence = "".join(f"<li>{esc(item)}</li>" for item in analysis.get("evidence", []))
    return f"""
    <section id="failure-analysis" class="panel failure">
      <h2>Failure Analysis</h2>
      <table>
        <tbody>
          <tr><th>Category</th><td>{esc(analysis.get("category"))}</td></tr>
          <tr><th>Summary</th><td>{esc(analysis.get("summary"))}</td></tr>
          <tr><th>Failed step</th><td>{esc(analysis.get("failed_step"))}</td></tr>
          <tr><th>Failed command</th><td><code>{esc(analysis.get("failed_command"))}</code></td></tr>
          <tr><th>Return code</th><td>{esc(analysis.get("returncode"))}</td></tr>
          <tr><th>Impact</th><td>{esc(analysis.get("impact"))}</td></tr>
          <tr><th>Next step</th><td>{esc(analysis.get("recommended_next_step"))}</td></tr>
        </tbody>
      </table>
      <h3>Evidence</h3>
      <ul>{evidence}</ul>
    </section>
    """


def render_html(data, source_json):
    result = data.get("result", {})
    metric = data.get("metric") or data.get("scenario")
    status = data.get("status", "-")
    status_class = "success" if status == "success" else "failed"
    command = data.get("command", "")
    first_step = step_by_name(data, "first_run")
    incremental_step = step_by_name(data, "incremental_run")
    first_seconds = result.get("first_run_seconds")
    incremental_seconds = result.get("incremental_run_seconds")
    ccache = data.get("ccache", {})
    raw_json = html.escape(json.dumps(data, indent=2, ensure_ascii=False))
    failure_analysis = render_failure_analysis(data)

    comparison = ""
    if first_seconds is not None and incremental_seconds is not None and first_seconds:
        ratio = first_seconds / incremental_seconds if incremental_seconds else None
        saved = first_seconds - incremental_seconds
        comparison = f"""
          <section class="panel compare">
            <h2>Run Comparison</h2>
            <div class="compare-grid">
              <div>
                <span class="label">Delta</span>
                <strong>{fmt_seconds(saved)}</strong>
              </div>
              <div>
                <span class="label">Speedup</span>
                <strong>{ratio:.1f}x</strong>
              </div>
            </div>
          </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(metric)} - HCOMM TTFHW</title>
  <style>
    :root {{
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #202124;
      --muted: #5f6368;
      --line: #dadce0;
      --accent: #0b6bcb;
      --ok: #137333;
      --fail: #b3261e;
      --warn: #8a5a00;
    }}

    * {{ box-sizing: border-box; }}

    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}

    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 40px 20px 56px;
    }}

    h1 {{
      margin: 12px 0 8px;
      font-size: 34px;
      line-height: 1.2;
    }}

    h2 {{
      margin: 0 0 16px;
      font-size: 20px;
    }}

    .lede {{
      margin: 0 0 24px;
      color: var(--muted);
      line-height: 1.5;
    }}

    .pill {{
      display: inline-block;
      padding: 4px 9px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}

    .success {{ color: var(--ok); background: #e6f4ea; }}
    .failed {{ color: var(--fail); background: #fce8e6; }}
    .not-run {{ color: var(--warn); background: #fef7e0; }}

    .runs {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
      margin: 24px 0 16px;
    }}

    .run-card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}

    .run-card {{
      padding: 22px;
    }}

    .run-top {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 24px;
    }}

    .run-title {{
      color: var(--muted);
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
    }}

    .duration {{
      margin-bottom: 14px;
      font-size: 42px;
      font-weight: 800;
      line-height: 1;
    }}

    .command {{
      color: var(--muted);
      font-size: 14px;
      word-break: break-word;
    }}

    code, pre {{
      font-family: "SFMono-Regular", Consolas, monospace;
    }}

    .panel {{
      margin-top: 16px;
      padding: 20px;
    }}

    .compare-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
    }}

    .compare-grid .label {{
      display: block;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 13px;
      text-transform: uppercase;
    }}

    .compare-grid strong {{
      font-size: 28px;
    }}

    .failure {{
      border-color: #f4b4ae;
      background: #fff7f6;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}

    th, td {{
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}

    th {{
      color: var(--muted);
      font-weight: 700;
    }}

    details {{
      margin-top: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px 18px;
    }}

    summary {{
      cursor: pointer;
      font-weight: 700;
    }}

    pre {{
      max-height: 520px;
      overflow: auto;
      white-space: pre-wrap;
      word-break: break-word;
      color: #303134;
      background: #f1f3f4;
      border-radius: 6px;
      padding: 14px;
    }}
  </style>
</head>
<body>
  <main>
    <span class="pill {status_class}">{esc(status)}</span>
    <h1>{esc(metric)}</h1>
    <p class="lede">
      Fixed TTFHW command: <code>{esc(command)}</code><br>
      Source JSON: <code>{esc(source_json)}</code>
    </p>

    {failure_analysis}

    <section class="runs" aria-label="first and incremental run comparison">
      {run_card("First Execution", first_step, first_seconds, command, "not executed")}
      {run_card("Second Incremental Execution", incremental_step, incremental_seconds, command, "not executed because first execution failed")}
    </section>

    {comparison}

    <section class="panel">
      <h2>ccache Summary</h2>
      <table>
        <tbody>
          <tr><th>Direct hits</th><td>{esc(ccache.get("cache_hit_direct", "-"))}</td></tr>
          <tr><th>Preprocessed hits</th><td>{esc(ccache.get("cache_hit_preprocessed", "-"))}</td></tr>
          <tr><th>Misses</th><td>{esc(ccache.get("cache_miss", "-"))}</td></tr>
          <tr><th>Hit rate</th><td>{esc(ccache.get("hit_rate", "-"))}</td></tr>
        </tbody>
      </table>
    </section>

    <details>
      <summary>Execution Steps</summary>
      <table>
        <thead>
          <tr><th>Step</th><th>Status</th><th>Duration</th><th>Command</th></tr>
        </thead>
        <tbody>
          {render_steps(data.get("steps", []))}
        </tbody>
      </table>
    </details>

    <details>
      <summary>Raw JSON</summary>
      <pre>{raw_json}</pre>
    </details>
  </main>
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
