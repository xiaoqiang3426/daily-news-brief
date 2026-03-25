#!/usr/bin/env python3
"""
投资建议周度复盘报告
读取 history/ 中一周的简报存档，汇总所有看多/规避建议，
结合当前市场数据判断命中情况，生成独立的复盘报告（HTML + PNG）。
"""
import argparse
import html as html_lib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import fetch_all_market_data

AI_BASE_URL = os.environ.get("AI_BASE_URL", "http://localhost:18258/v1")
AI_API_KEY = os.environ.get("AI_API_KEY", "123456")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-5.2")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/daily-news-brief"))
HISTORY_DIR = Path(os.environ.get("HISTORY_DIR", str(Path(__file__).parent.parent / "history")))

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ─── 历史数据加载 ──────────────────────────────────────────

def load_week_briefs(end_date: datetime, days: int = 7) -> list[dict]:
    """加载最近 N 天的简报存档，按日期排序。"""
    briefs = []
    for i in range(days):
        d = end_date - timedelta(days=i)
        date_str = d.strftime("%Y%m%d")
        for mode in ("morning", "closing"):
            path = HISTORY_DIR / f"{mode}_{date_str}.json"
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                briefs.append(data)
    briefs.sort(key=lambda x: (x["date"], x["mode"]))
    return briefs


def extract_advice(briefs: list[dict]) -> list[dict]:
    """从所有简报中提取看多/规避建议。"""
    advice_list = []
    for b in briefs:
        date = b["date"]
        weekday = b["weekday"]
        mode = b["mode"]
        mode_cn = {"morning": "早盘", "closing": "收盘"}.get(mode, mode)
        sections = b.get("brief", {}).get("sections", [])
        for sec in sections:
            if not sec.get("bullish") and not sec.get("bearish"):
                continue
            risk_level = sec.get("risk_level", "")
            position = sec.get("position", "")
            for item in sec.get("bullish", []):
                advice_list.append({
                    "date": date,
                    "weekday": weekday,
                    "source": f"{date} {weekday} {mode_cn}",
                    "direction": "看多",
                    "content": item,
                    "risk_level": risk_level,
                    "position": position,
                    "verdict": None,
                })
            for item in sec.get("bearish", []):
                advice_list.append({
                    "date": date,
                    "weekday": weekday,
                    "source": f"{date} {weekday} {mode_cn}",
                    "direction": "规避",
                    "content": item,
                    "risk_level": risk_level,
                    "position": position,
                    "verdict": None,
                })
    return advice_list


# ─── AI 判定命中率 ──────────────────────────────────────────

REVIEW_PROMPT = """你是一位投资策略回顾分析师，负责对过去一周的投资建议做客观复盘。

你会收到：
1. 本周每日简报中给出的所有看多/规避建议
2. 当前最新的市场数据（指数、板块、北向资金等）

请对每条建议判定：
- **命中**：建议方向与实际走势基本一致（看多的涨了，规避的跌了或表现弱）
- **未命中**：建议方向与实际走势相反
- **待验证**：时间窗口尚未结束，或无法判断

同时给出整体周度总结。

请严格输出以下 JSON 格式：

```json
{
  "week_summary": "本周投资建议整体表现总结（100~150字）",
  "market_review": "本周市场回顾（100~150字，涨跌、风格、资金动向）",
  "hit_rate": {
    "total": 10,
    "hit": 6,
    "miss": 3,
    "pending": 1,
    "rate": "60%"
  },
  "verdicts": [
    {
      "index": 0,
      "verdict": "命中|未命中|待验证",
      "reason": "判定理由（30~50字）",
      "actual_performance": "实际表现概述"
    }
  ],
  "lessons": [
    "经验教训1",
    "经验教训2",
    "经验教训3"
  ],
  "next_week_adjustments": "基于本周复盘，下周策略调整建议（50~100字）"
}
```

规则：
- verdicts 的 index 对应建议列表的序号（从0开始）
- 判定要客观、有数据支撑
- 看多建议对应板块涨幅超过大盘即为命中
- 规避建议对应板块跑输大盘或下跌即为命中
- lessons 提炼 2~3 条关键经验教训
"""


def call_ai_review(advice_list: list[dict], market_data: dict) -> dict:
    import requests

    advice_text = "\n## 本周投资建议清单\n"
    for i, a in enumerate(advice_list):
        advice_text += f"\n[{i}] {a['source']} | {a['direction']} | {a['content']}"

    market_text = "\n## 当前市场数据\n"
    for idx in market_data.get("indices", []):
        market_text += f"- {idx['name']}: {idx['price']} ({idx['change_pct']})\n"

    nb = market_data.get("northbound")
    if nb:
        market_text += f"- 北向资金: 沪 {nb['hgt']:.1f}亿 | 深 {nb['sgt']:.1f}亿 | 合计 {nb['total']:.1f}亿\n"
        if nb.get("total_5d") is not None:
            market_text += f"- 北向近5日累计: {nb['total_5d']:.1f}亿\n"

    if market_data.get("top_sectors"):
        market_text += "- 本周涨幅前板块: " + ", ".join(
            f"{s['name']}({'+' if s['change_pct']>0 else ''}{s['change_pct']}%)" for s in market_data["top_sectors"]
        ) + "\n"
    if market_data.get("bottom_sectors"):
        market_text += "- 本周跌幅前板块: " + ", ".join(
            f"{s['name']}({s['change_pct']}%)" for s in market_data["bottom_sectors"]
        ) + "\n"

    week_changes = market_data.get("week_changes", {})
    if week_changes:
        market_text += "- 指数周涨跌: " + " | ".join(
            f"{k} {'+' if v>0 else ''}{v}%" for k, v in week_changes.items()
        ) + "\n"

    for fc in market_data.get("forex_commodities", []):
        sign = "+" if fc["change_pct"] > 0 else ""
        market_text += f"- {fc['name']}: {fc['price']} ({sign}{fc['change_pct']}%)\n"

    resp = requests.post(
        f"{AI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": REVIEW_PROMPT},
                {"role": "user", "content": f"以下是本周的投资建议和市场数据：\n{advice_text}\n{market_text}"},
            ],
            "temperature": 0.3,
        },
        timeout=300,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]

    start = content.find("{")
    end = content.rfind("}") + 1
    if start >= 0 and end > start:
        content = content[start:end]

    return json.loads(content)


# ─── HTML 渲染 ─────────────────────────────────────────────

def esc(text: Any) -> str:
    return html_lib.escape(str(text), quote=True)


def build_review_html(
    review: dict, advice_list: list[dict], market_data: dict, week_range: str
) -> str:
    hit_rate = review.get("hit_rate", {})
    verdicts = {v["index"]: v for v in review.get("verdicts", [])}
    lessons = review.get("lessons", [])
    week_summary = review.get("week_summary", "")
    market_review = review.get("market_review", "")
    next_week = review.get("next_week_adjustments", "")

    total = hit_rate.get("total", 0)
    hit = hit_rate.get("hit", 0)
    miss = hit_rate.get("miss", 0)
    pending = hit_rate.get("pending", 0)
    rate = hit_rate.get("rate", "N/A")

    # 命中率环形图 SVG
    hit_pct = (hit / total * 100) if total > 0 else 0
    miss_pct = (miss / total * 100) if total > 0 else 0
    pending_pct = (pending / total * 100) if total > 0 else 0
    ring_svg = _build_ring_svg(hit_pct, miss_pct, pending_pct)

    # 指数面板
    indices_html = ""
    for idx in market_data.get("indices", [])[:7]:
        pct = idx.get("change_pct", "0%")
        num = float(str(pct).replace("%", "").replace("+", ""))
        cls = "up" if num > 0 else ("down" if num < 0 else "flat")
        arrow = "&#9650;" if num > 0 else ("&#9660;" if num < 0 else "&#9644;")
        indices_html += f"""
        <div class="idx-item {cls}">
          <div class="idx-name">{esc(idx['name'])}</div>
          <div class="idx-price">{arrow} {idx['price']}</div>
          <div class="idx-pct">{esc(pct)}</div>
        </div>"""

    # 建议逐条卡片
    advice_cards_html = ""
    for i, a in enumerate(advice_list):
        v = verdicts.get(i, {})
        verdict = v.get("verdict", "待验证")
        reason = v.get("reason", "")
        actual = v.get("actual_performance", "")

        verdict_cls = {
            "命中": "verdict-hit",
            "未命中": "verdict-miss",
            "待验证": "verdict-pending",
        }.get(verdict, "verdict-pending")
        verdict_icon = {"命中": "&#10004;", "未命中": "&#10008;", "待验证": "&#8943;"}.get(verdict, "?")
        dir_cls = "dir-bull" if a["direction"] == "看多" else "dir-bear"

        advice_cards_html += f"""
        <div class="advice-row {verdict_cls}">
          <div class="advice-left">
            <span class="advice-date">{esc(a['source'])}</span>
            <span class="advice-dir {dir_cls}">{esc(a['direction'])}</span>
          </div>
          <div class="advice-content">{esc(a['content'])}</div>
          <div class="advice-verdict-row">
            <span class="verdict-badge {verdict_cls}">{verdict_icon} {esc(verdict)}</span>
            <span class="verdict-reason">{esc(reason)}</span>
          </div>
          {'<div class="advice-actual">' + esc(actual) + '</div>' if actual else ''}
        </div>"""

    # 经验教训
    lessons_html = ""
    if lessons:
        items = "".join(f"<li>{esc(l)}</li>" for l in lessons)
        lessons_html = f"<ul>{items}</ul>"

    now = datetime.now()
    date_text = now.strftime("%Y年%m月%d日") + " · " + WEEKDAY_CN[now.weekday()]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>投资复盘 {week_range}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&display=swap');
    :root {{
      --paper: #f6f1e6; --ink: #141414; --muted: #5d5a53; --line: #1d1d1d;
      --soft-line: #c8beb0; --accent: #6d28d9; --card: rgba(255,255,255,0.28);
      --green: #16a34a; --red: #dc2626; --amber: #d97706;
      --hit: #16a34a; --miss: #dc2626; --pending: #9ca3af;
    }}
    * {{ box-sizing: border-box; }}
    html, body {{ margin: 0; padding: 0; background: #ddd5c9; color: var(--ink); }}
    body {{
      font-family: "Noto Serif SC", "Source Han Serif SC", "PingFang SC", serif;
      display: flex; justify-content: center; padding: 24px 0;
    }}
    .page {{
      width: 1080px;
      background: linear-gradient(180deg, #f9f5ec 0%, var(--paper) 100%);
      box-shadow: 0 12px 40px rgba(0,0,0,0.12);
      padding: 48px 52px 36px; position: relative; overflow: hidden;
    }}
    .page::before {{
      content: ""; position: absolute; inset: 0; pointer-events: none;
      background-image: radial-gradient(rgba(0,0,0,0.028) 0.8px, transparent 0.8px);
      background-size: 7px 7px; opacity: 0.6;
    }}

    .topbar {{
      position: relative; z-index: 1;
      display: flex; justify-content: space-between; align-items: end;
      border-top: 6px solid var(--accent); border-bottom: 2px solid var(--line);
      padding: 14px 0 12px; margin-bottom: 26px;
    }}
    .paper-name {{ font-size: 52px; font-weight: 900; letter-spacing: 4px; line-height: 1; color: var(--accent); }}
    .paper-subtitle {{ font-size: 20px; color: var(--muted); margin-left: 12px; letter-spacing: 2px; }}
    .issue {{ font-size: 20px; color: var(--muted); white-space: nowrap; text-align: right; line-height: 1.4; }}

    .hero {{ position: relative; z-index: 1; margin-bottom: 24px; }}
    .hero h1 {{ margin: 0; font-size: 42px; line-height: 1.2; font-weight: 900; }}
    .hero .week-range {{ font-size: 22px; color: var(--muted); margin-top: 8px; }}

    /* 命中率面板 */
    .hitrate-panel {{
      position: relative; z-index: 1; display: flex; gap: 32px; align-items: center;
      padding: 24px 32px; margin-bottom: 24px;
      background: rgba(109,40,217,0.04); border: 1.5px solid rgba(109,40,217,0.2); border-radius: 8px;
    }}
    .hitrate-ring {{ flex-shrink: 0; }}
    .hitrate-stats {{ flex: 1; }}
    .hitrate-title {{ font-size: 24px; font-weight: 900; color: var(--accent); margin-bottom: 12px; letter-spacing: 2px; }}
    .hitrate-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
    .stat-box {{ text-align: center; padding: 10px 0; }}
    .stat-num {{ font-size: 36px; font-weight: 900; line-height: 1; }}
    .stat-label {{ font-size: 14px; color: var(--muted); margin-top: 4px; }}
    .stat-hit .stat-num {{ color: var(--hit); }}
    .stat-miss .stat-num {{ color: var(--miss); }}
    .stat-pending .stat-num {{ color: var(--pending); }}
    .stat-total .stat-num {{ color: var(--ink); }}

    /* 市场面板 */
    .market-panel {{
      position: relative; z-index: 1; margin-bottom: 24px; padding: 16px 20px;
      background: rgba(20,20,20,0.04); border: 1.5px solid var(--soft-line); border-radius: 4px;
    }}
    .panel-title {{ font-size: 18px; font-weight: 900; letter-spacing: 2px; color: var(--accent); margin-bottom: 12px; }}
    .idx-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }}
    .idx-item {{ text-align: center; padding: 6px 4px; border-radius: 3px; background: rgba(255,255,255,0.5); }}
    .idx-name {{ font-size: 13px; color: var(--muted); }}
    .idx-price {{ font-size: 16px; font-weight: 700; }}
    .idx-pct {{ font-size: 14px; font-weight: 700; }}
    .idx-item.up .idx-price, .idx-item.up .idx-pct {{ color: var(--red); }}
    .idx-item.down .idx-price, .idx-item.down .idx-pct {{ color: var(--green); }}

    /* 总结区 */
    .section {{ position: relative; z-index: 1; margin-bottom: 24px; }}
    .section::before {{
      content: ""; display: block; height: 2px; width: 100%;
      background: var(--line); margin-bottom: 16px;
    }}
    .section h2 {{ margin: 0 0 12px; font-size: 28px; font-weight: 900; color: var(--accent); letter-spacing: 2px; }}
    .section p {{ font-size: 20px; line-height: 1.8; color: var(--ink); text-align: justify; margin: 0 0 12px; }}
    .section .muted {{ color: var(--muted); font-style: italic; }}

    /* 建议逐条 */
    .advice-row {{
      padding: 16px 20px; margin-bottom: 12px; border-radius: 6px;
      border-left: 5px solid var(--pending); background: rgba(255,255,255,0.4);
    }}
    .advice-row.verdict-hit {{ border-left-color: var(--hit); background: rgba(22,163,74,0.04); }}
    .advice-row.verdict-miss {{ border-left-color: var(--miss); background: rgba(220,38,38,0.04); }}
    .advice-row.verdict-pending {{ border-left-color: var(--pending); }}

    .advice-left {{ display: flex; gap: 12px; align-items: center; margin-bottom: 6px; }}
    .advice-date {{ font-size: 14px; color: var(--muted); }}
    .advice-dir {{
      font-size: 13px; font-weight: 700; padding: 2px 8px; border-radius: 3px;
    }}
    .dir-bull {{ background: #fee2e2; color: #991b1b; }}
    .dir-bear {{ background: #dcfce7; color: #166534; }}
    .advice-content {{ font-size: 19px; line-height: 1.7; margin-bottom: 8px; }}
    .advice-verdict-row {{ display: flex; gap: 12px; align-items: center; }}
    .verdict-badge {{
      font-size: 14px; font-weight: 700; padding: 3px 10px; border-radius: 3px;
      white-space: nowrap;
    }}
    .verdict-badge.verdict-hit {{ background: #dcfce7; color: #166534; }}
    .verdict-badge.verdict-miss {{ background: #fee2e2; color: #991b1b; }}
    .verdict-badge.verdict-pending {{ background: #f3f4f6; color: #6b7280; }}
    .verdict-reason {{ font-size: 16px; color: var(--muted); line-height: 1.5; }}
    .advice-actual {{
      font-size: 15px; color: var(--muted); margin-top: 6px;
      padding: 6px 12px; background: rgba(0,0,0,0.03); border-radius: 3px;
    }}

    /* 经验教训 */
    .lessons ul {{ margin: 0; padding-left: 24px; }}
    .lessons li {{ font-size: 20px; line-height: 1.8; margin-bottom: 8px; }}

    /* 底部 */
    .footer {{
      position: relative; z-index: 1; margin-top: 32px; padding-top: 14px;
      border-top: 2px solid var(--line);
    }}
    .footer-main {{ display: flex; justify-content: space-between; font-size: 15px; color: var(--muted); }}
    .stamp {{
      display: inline-flex; align-items: center; gap: 8px;
      font-size: 15px; font-weight: 800; letter-spacing: 1px; color: var(--accent);
    }}
    .stamp::before {{ content: ""; width: 10px; height: 10px; border-radius: 999px; background: var(--accent); display: inline-block; }}
    .disclaimer {{
      margin-top: 10px; font-size: 13px; color: #9ca3af; line-height: 1.5;
      padding: 8px 12px; background: rgba(0,0,0,0.03); border-radius: 3px;
    }}
  </style>
</head>
<body>
  <article class="page">
    <header class="topbar">
      <div>
        <span class="paper-name">投资复盘</span>
        <span class="paper-subtitle">周度报告</span>
      </div>
      <div class="issue">{esc(date_text)}</div>
    </header>

    <section class="hero">
      <h1>本周投资建议命中率：{esc(rate)}</h1>
      <div class="week-range">复盘周期：{esc(week_range)}</div>
    </section>

    <div class="hitrate-panel">
      <div class="hitrate-ring">{ring_svg}</div>
      <div class="hitrate-stats">
        <div class="hitrate-title">命中率统计</div>
        <div class="hitrate-grid">
          <div class="stat-box stat-total">
            <div class="stat-num">{total}</div>
            <div class="stat-label">总建议数</div>
          </div>
          <div class="stat-box stat-hit">
            <div class="stat-num">{hit}</div>
            <div class="stat-label">命中</div>
          </div>
          <div class="stat-box stat-miss">
            <div class="stat-num">{miss}</div>
            <div class="stat-label">未命中</div>
          </div>
          <div class="stat-box stat-pending">
            <div class="stat-num">{pending}</div>
            <div class="stat-label">待验证</div>
          </div>
        </div>
      </div>
    </div>

    <div class="market-panel">
      <div class="panel-title">市场数据</div>
      <div class="idx-grid">{indices_html}</div>
    </div>

    <section class="section">
      <h2>市场回顾</h2>
      <p>{esc(market_review)}</p>
    </section>

    <section class="section">
      <h2>总结</h2>
      <p>{esc(week_summary)}</p>
    </section>

    <section class="section">
      <h2>逐条复盘</h2>
      {advice_cards_html}
    </section>

    <section class="section lessons">
      <h2>经验教训</h2>
      {lessons_html}
    </section>

    <section class="section">
      <h2>下周策略调整</h2>
      <p>{esc(next_week)}</p>
    </section>

    <footer class="footer">
      <div class="footer-main">
        <div>数据来源：东方财富 · 新华社 · 财联社 | AI 复盘，仅供参考</div>
        <div class="stamp">投资复盘</div>
      </div>
      <div class="disclaimer">&#9888;&#65039; 免责声明：以上所有内容均由 AI 自动生成，仅供学习参考，不构成任何投资建议。市场有风险，投资需谨慎。</div>
    </footer>
  </article>
</body>
</html>"""


def _build_ring_svg(hit_pct: float, miss_pct: float, pending_pct: float) -> str:
    """生成命中率环形图 SVG。"""
    r = 60
    cx, cy = 75, 75
    circumference = 2 * 3.14159 * r

    hit_len = circumference * hit_pct / 100
    miss_len = circumference * miss_pct / 100
    pending_len = circumference * pending_pct / 100

    hit_offset = 0
    miss_offset = -hit_len
    pending_offset = -(hit_len + miss_len)

    rate_text = f"{hit_pct:.0f}%" if hit_pct > 0 else "N/A"

    return f"""<svg width="150" height="150" viewBox="0 0 150 150">
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e5e7eb" stroke-width="16"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#16a34a" stroke-width="16"
        stroke-dasharray="{hit_len} {circumference - hit_len}"
        stroke-dashoffset="{hit_offset}" transform="rotate(-90 {cx} {cy})"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#dc2626" stroke-width="16"
        stroke-dasharray="{miss_len} {circumference - miss_len}"
        stroke-dashoffset="{miss_offset}" transform="rotate(-90 {cx} {cy})"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#9ca3af" stroke-width="16"
        stroke-dasharray="{pending_len} {circumference - pending_len}"
        stroke-dashoffset="{pending_offset}" transform="rotate(-90 {cx} {cy})"/>
      <text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="central"
        font-size="28" font-weight="900" fill="#141414" font-family="Noto Serif SC, serif">{rate_text}</text>
    </svg>"""


# ─── 截图 ─────────────────────────────────────────────────

def screenshot_html(html_path: Path, png_path: Path) -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright not installed", file=sys.stderr)
        return False

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1242, "height": 800})
        page.goto(f"file://{html_path.resolve()}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)

        article = page.query_selector("article.page")
        if article:
            article.screenshot(path=str(png_path))
        else:
            page.screenshot(path=str(png_path), full_page=True)

        browser.close()
    return png_path.exists()


# ─── 主入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="投资建议周度复盘")
    parser.add_argument("--days", type=int, default=7, help="回溯天数（默认7天）")
    parser.add_argument("--end-date", help="结束日期 YYYYMMDD（默认今天）")
    parser.add_argument("-o", "--output", help="PNG output path")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    end_date = datetime.strptime(args.end_date, "%Y%m%d") if args.end_date else datetime.now()
    start_date = end_date - timedelta(days=args.days - 1)
    week_range = f"{start_date.strftime('%m.%d')} ~ {end_date.strftime('%m.%d')}"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    print(f"📊 投资复盘：{week_range}（{args.days}天）")

    print("1/4 加载历史简报...")
    briefs = load_week_briefs(end_date, args.days)
    if not briefs:
        print("[ERROR] 没有找到历史简报数据", file=sys.stderr)
        print(f"   检查目录: {HISTORY_DIR}", file=sys.stderr)
        sys.exit(1)
    print(f"   找到 {len(briefs)} 份简报")

    advice_list = extract_advice(briefs)
    print(f"   提取 {len(advice_list)} 条投资建议")
    if not advice_list:
        print("[ERROR] 没有提取到投资建议", file=sys.stderr)
        sys.exit(1)

    print("2/4 抓取最新市场数据...")
    market_data = fetch_all_market_data()

    print("3/4 AI 复盘分析...")
    review = call_ai_review(advice_list, market_data)

    review_path = OUTPUT_DIR / f"review_{ts}.json"
    review_data = {
        "week_range": week_range,
        "advice_list": advice_list,
        "review": review,
    }
    review_path.write_text(json.dumps(review_data, ensure_ascii=False, indent=2), encoding="utf-8")

    print("4/4 渲染 HTML + 截图...")
    html_content = build_review_html(review, advice_list, market_data, week_range)
    html_path = OUTPUT_DIR / f"review_{ts}.html"
    html_path.write_text(html_content, encoding="utf-8")

    png_path = Path(args.output) if args.output else OUTPUT_DIR / f"review_{ts}.png"
    ok = screenshot_html(html_path, png_path)
    if ok:
        size_kb = png_path.stat().st_size / 1024
        print(f"✅ 完成！PNG: {png_path} ({size_kb:.0f}KB)")
    else:
        print("[ERROR] 截图失败", file=sys.stderr)
        sys.exit(2)

    print(f"\nPNG_PATH={png_path}")
    return str(png_path)


if __name__ == "__main__":
    main()
