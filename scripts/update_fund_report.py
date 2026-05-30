from __future__ import annotations

import html
import json
import re
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "funds.json"
HISTORY_PATH = ROOT / "data" / "history.json"
REPORT_PATH = ROOT / "report.html"
DOCS_REPORT_PATH = ROOT / "docs" / "index.html"
SOURCE_NAME = "天天基金 / 东方财富基金估值接口"
SOURCE_URL = "https://fundgz.1234567.com.cn/js/{code}.js"
BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def load_funds() -> list[dict[str, str]]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing fund config: {CONFIG_PATH}")

    funds = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(funds, list) or not funds:
        raise ValueError("data/funds.json must contain at least one fund entry.")

    normalized = []
    for item in funds:
        code = str(item.get("code", "")).strip()
        if not re.fullmatch(r"\d{6}", code):
            raise ValueError(f"Invalid fund code in data/funds.json: {code!r}")
        normalized.append({"code": code, "label": str(item.get("label", "")).strip()})
    return normalized


def fetch_fund(code: str) -> dict[str, Any]:
    url = SOURCE_URL.format(code=code) + f"?rt={int(time.time() * 1000)}"
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 fund-report-bot",
            "Referer": "https://fund.eastmoney.com/",
        },
    )

    with urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8", errors="replace")

    match = re.search(r"jsonpgz\((\{.*\})\);?", body)
    if not match:
        raise ValueError(f"Unexpected response for fund {code}: {body[:120]}")

    return json.loads(match.group(1))


def load_history() -> list[dict[str, Any]]:
    if not HISTORY_PATH.exists():
        return []
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def save_history(history: list[dict[str, Any]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def pct_value(item: dict[str, Any]) -> float:
    try:
        return float(item.get("change_percent", 0))
    except (TypeError, ValueError):
        return 0.0


def class_for_change(value: float) -> str:
    if value > 0:
        return "gain"
    if value < 0:
        return "loss"
    return "flat"


def render_report(history: list[dict[str, Any]]) -> str:
    latest = history[-1] if history else None
    latest_rows = latest.get("funds", []) if latest else []
    sorted_latest = sorted(latest_rows, key=pct_value, reverse=True)
    best = sorted_latest[0] if sorted_latest else None
    worst = sorted_latest[-1] if sorted_latest else None

    def summary_card(title: str, item: dict[str, Any] | None) -> str:
        if not item:
            return f"<article><span>{html.escape(title)}</span><strong>--</strong><small>暂无数据</small></article>"
        pct = pct_value(item)
        klass = class_for_change(pct)
        return (
            f"<article><span>{html.escape(title)}</span>"
            f"<strong>{html.escape(item['name'])}</strong>"
            f"<small class=\"{klass}\">{pct:+.2f}%</small></article>"
        )

    sections = []
    for day in reversed(history):
        rows = []
        for item in sorted(day.get("funds", []), key=pct_value, reverse=True):
            pct = pct_value(item)
            klass = class_for_change(pct)
            rows.append(
                "<tr>"
                f"<td>{html.escape(item['code'])}</td>"
                f"<td>{html.escape(item['name'])}</td>"
                f"<td>{html.escape(str(item.get('net_value', '')))}</td>"
                f"<td>{html.escape(str(item.get('estimated_value', '')))}</td>"
                f"<td class=\"{klass}\">{pct:+.2f}%</td>"
                f"<td>{html.escape(str(item.get('net_value_date', '')))}</td>"
                f"<td>{html.escape(str(item.get('quote_time', '')))}</td>"
                "</tr>"
            )

        sections.append(
            f"""
            <section class="day">
              <div class="day-title">
                <h2>{html.escape(day['date'])}</h2>
                <p>北京时间 {html.escape(day['generated_at'])} 更新，成功 {day['success_count']} 支，失败 {day['failed_count']} 支。</p>
              </div>
              <div class="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>代码</th>
                      <th>基金名称</th>
                      <th>单位净值</th>
                      <th>估算净值</th>
                      <th>估算涨跌幅</th>
                      <th>净值日期</th>
                      <th>估值时间</th>
                    </tr>
                  </thead>
                  <tbody>{''.join(rows)}</tbody>
                </table>
              </div>
            </section>
            """
        )

        if day.get("errors"):
            errors = "".join(
                f"<li>{html.escape(error['code'])}: {html.escape(error['message'])}</li>"
                for error in day["errors"]
            )
            sections.append(f"<details><summary>本次未成功项目</summary><ul>{errors}</ul></details>")

    generated = datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M:%S")
    latest_date = html.escape(latest["date"]) if latest else "暂无"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>基金涨跌日报</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --line: #d9dee7;
      --gain: #c2410c;
      --loss: #047857;
      --flat: #475467;
      --accent: #1d4ed8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--text);
      background: var(--bg);
    }}
    header {{
      padding: 36px min(5vw, 56px) 24px;
      background: #ffffff;
      border-bottom: 1px solid var(--line);
    }}
    h1, h2, p {{ margin: 0; }}
    h1 {{ font-size: clamp(28px, 4vw, 46px); font-weight: 720; letter-spacing: 0; }}
    header p {{ margin-top: 10px; color: var(--muted); line-height: 1.7; }}
    main {{ width: min(1180px, calc(100% - 28px)); margin: 24px auto 48px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 18px; }}
    article, .day, details {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    article {{ padding: 16px; min-height: 110px; }}
    article span, article small {{ display: block; color: var(--muted); }}
    article strong {{ display: block; margin: 12px 0 6px; font-size: 20px; line-height: 1.25; }}
    .day {{ margin-top: 16px; overflow: hidden; }}
    .day-title {{ padding: 18px 18px 14px; border-bottom: 1px solid var(--line); }}
    .day-title h2 {{ font-size: 22px; }}
    .day-title p {{ margin-top: 6px; color: var(--muted); }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 780px; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }}
    th {{ color: var(--muted); font-size: 13px; font-weight: 650; background: #fbfcfe; }}
    tr:last-child td {{ border-bottom: 0; }}
    .gain {{ color: var(--gain); font-weight: 700; }}
    .loss {{ color: var(--loss); font-weight: 700; }}
    .flat {{ color: var(--flat); font-weight: 700; }}
    details {{ margin-top: 12px; padding: 14px 18px; color: var(--muted); }}
    a {{ color: var(--accent); }}
    @media (max-width: 760px) {{
      header {{ padding: 28px 16px 20px; }}
      main {{ width: calc(100% - 20px); margin-top: 14px; }}
      .cards {{ grid-template-columns: 1fr; }}
      article {{ min-height: auto; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>基金涨跌日报</h1>
    <p>最新记录：{latest_date}。数据来自 <a href="https://fund.eastmoney.com/" rel="noreferrer">{SOURCE_NAME}</a>，页面生成时间：北京时间 {html.escape(generated)}。</p>
  </header>
  <main>
    <div class="cards">
      {summary_card("最新涨幅最高", best)}
      {summary_card("最新跌幅最大", worst)}
      <article><span>历史记录</span><strong>{len(history)} 天</strong><small>同一网页持续追加</small></article>
    </div>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def main() -> int:
    run_at = datetime.now(BEIJING_TZ)
    funds = load_funds()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for fund in funds:
        code = fund["code"]
        try:
            data = fetch_fund(code)
            rows.append(
                {
                    "code": code,
                    "name": data.get("name") or fund.get("label") or code,
                    "net_value": data.get("dwjz", ""),
                    "estimated_value": data.get("gsz", ""),
                    "change_percent": data.get("gszzl", "0"),
                    "net_value_date": data.get("jzrq", ""),
                    "quote_time": data.get("gztime", ""),
                    "source": SOURCE_URL.format(code=code),
                }
            )
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors.append({"code": code, "message": str(exc)})

    if not rows:
        raise RuntimeError("No fund data could be fetched. Report was not updated.")

    history = load_history()
    day_record = {
        "date": run_at.strftime("%Y-%m-%d"),
        "generated_at": run_at.strftime("%Y-%m-%d %H:%M:%S"),
        "source_name": SOURCE_NAME,
        "source_home": "https://fund.eastmoney.com/",
        "success_count": len(rows),
        "failed_count": len(errors),
        "funds": rows,
        "errors": errors,
    }

    history = [item for item in history if item.get("date") != day_record["date"]]
    history.append(day_record)
    history.sort(key=lambda item: item.get("date", ""))

    save_history(history)
    html_text = render_report(history)
    REPORT_PATH.write_text(html_text, encoding="utf-8")
    DOCS_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_REPORT_PATH.write_text(html_text, encoding="utf-8")

    print(f"Updated {REPORT_PATH}")
    print(f"Updated {DOCS_REPORT_PATH}")
    print(f"Added record date: {day_record['date']}")
    if errors:
        print(f"Warning: {len(errors)} fund(s) failed.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
