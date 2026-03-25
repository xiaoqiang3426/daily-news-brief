#!/usr/bin/env python3
"""
每日7点 — 中文新闻简报生成器 v2
支持三种模式：morning（早盘前简报）、closing（收盘总结）、weekly（周报特刊）
"""
import argparse
import html as html_lib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from fetch_news import fetch_all_news, fetch_all_market_data

AI_BASE_URL = os.environ.get("AI_BASE_URL", "http://localhost:18258/v1")
AI_API_KEY = os.environ.get("AI_API_KEY", "123456")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-5.2")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/tmp/daily-news-brief"))
HISTORY_DIR = Path(os.environ.get("HISTORY_DIR", str(Path(__file__).parent.parent / "history")))

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# ─── AI Prompts ───────────────────────────────────────────

MORNING_PROMPT = """你是一位资深财经新闻主编 + 投资策略师，负责每天早上 7 点为用户生成「决策导向」的新闻简报。

你会收到两部分信息：
1. 来自新华社、财联社、东方财富、华尔街见闻、雪球的实时新闻
2. 市场数据（指数行情、北向资金、板块涨跌、汇率商品）

请严格输出以下 JSON 格式，不要输出其他内容：

```json
{
  "title": "主标题（10~20字，抓住今天最核心的信号）",
  "summary": "导语（30~60字，提炼今日核心观点）",
  "market_comment": "市场数据点评（50~100字，解读指数/资金/汇率的关键变化，不要重复原始数字）",
  "sections": [
    {
      "heading": "政策动态",
      "items": [
        {
          "text": "新闻概括（25~50字）",
          "impact_chain": "影响链分析（如：某政策 → 利好/利空某行业 → 关注某类标的）",
          "tags": ["关联板块1", "关联板块2"],
          "confidence": "已证实|待确认|传闻"
        }
      ]
    },
    {
      "heading": "财经要闻",
      "items": [同上结构]
    },
    {
      "heading": "科技产业",
      "items": [同上结构]
    },
    {
      "heading": "AI投资建议",
      "risk_level": "防守|平衡|进攻",
      "position": "建议仓位百分比，如 50-60%",
      "style": "操作风格（如 防御+结构、均衡配置、积极进攻）",
      "bullish": ["看多方向1（含理由）", "看多方向2（含理由）"],
      "bearish": ["规避方向1（含理由）", "规避方向2（含理由）"],
      "risk_warning": "风险提示（50~80字）",
      "time_window": "关注时间窗口（如 下周一关注XX政策落地）",
      "watch_list": ["关注标的/板块1", "关注标的/板块2"]
    }
  ],
  "key_events": [
    {"time": "10:00", "event": "国家统计局发布XX数据", "impact": "可能影响方向"},
    {"time": "14:00", "event": "央行公开市场操作结果", "impact": "关注资金面"}
  ],
  "highlights": ["要点1（10~20字）", "要点2", "要点3", "要点4", "要点5"]
}
```

规则：
- 政策动态 2~3 条，优先国务院/央行/部委的重大政策，展开影响链
- 财经要闻 2~3 条，侧重市场事件和数据解读
- 科技产业 1~2 条，侧重产业趋势和投资关联
- AI投资建议必须结构化输出：risk_level、position、style、bullish、bearish、risk_warning、time_window
- bullish 和 bearish 各 2~3 条，每条包含板块/标的名称和理由
- key_events 列出当日（或近期）可能引发市场波动的时间节点，2~4 个
- 每条新闻必须标注 tags（关联板块）和 confidence（信息确认度）
- highlights 是 TL;DR 速览，5 条以内"""

CLOSING_PROMPT = """你是一位资深财经新闻主编 + 投资策略师，负责 A 股收盘后的复盘总结。

你会收到两部分信息：
1. 当日新闻（新华社、财联社、东方财富、华尔街见闻、雪球）
2. 市场数据（指数行情、北向资金、板块涨跌、汇率商品）

请严格输出以下 JSON 格式：

```json
{
  "title": "收盘标题（10~20字）",
  "summary": "今日市场一句话总结（30~60字）",
  "market_comment": "收盘行情深度点评（100~150字，包括大盘走势、量能变化、资金动向）",
  "sections": [
    {
      "heading": "今日复盘",
      "items": [
        {
          "text": "盘面关键事件/异动",
          "impact_chain": "原因分析 → 后续影响",
          "tags": ["板块"],
          "confidence": "已证实"
        }
      ]
    },
    {
      "heading": "盘后要闻",
      "items": [同上结构]
    },
    {
      "heading": "AI策略展望",
      "risk_level": "防守|平衡|进攻",
      "position": "明日建议仓位",
      "style": "操作风格",
      "bullish": ["明日看多方向1（含理由）", "明日看多方向2"],
      "bearish": ["明日规避方向1（含理由）", "明日规避方向2"],
      "risk_warning": "明日风险提示",
      "time_window": "明日关注时间窗口",
      "watch_list": ["明日关注方向"]
    }
  ],
  "key_events": [
    {"time": "09:30", "event": "关注事件", "impact": "影响"}
  ],
  "highlights": ["要点1", "要点2", "要点3"]
}
```

规则：
- 今日复盘 3~4 条，侧重异动板块和关键事件
- 盘后要闻 2~3 条，影响明日走势的重要消息
- AI策略展望必须结构化输出：risk_level、position、style、bullish、bearish、risk_warning、time_window
- key_events 列出明日关键时间节点"""

WEEKLY_PROMPT = """你是一位资深财经主编，负责周末/假期的周报特刊。

你会收到本周累计的新闻和市场数据。

请严格输出以下 JSON 格式：

```json
{
  "title": "本周标题",
  "summary": "本周市场一句话总结",
  "market_comment": "本周行情回顾（150~200字）",
  "sections": [
    {
      "heading": "本周政策汇总",
      "items": [{"text": "...", "impact_chain": "...", "tags": [...], "confidence": "..."}]
    },
    {
      "heading": "行业资金周度变化",
      "items": [同上]
    },
    {
      "heading": "下周关键事件日历",
      "items": [同上]
    },
    {
      "heading": "AI周度策略展望",
      "risk_level": "防守|平衡|进攻",
      "position": "下周建议仓位",
      "style": "操作风格",
      "bullish": ["下周看多方向1", "下周看多方向2"],
      "bearish": ["下周规避方向1", "下周规避方向2"],
      "risk_warning": "下周风险提示",
      "time_window": "下周关键时间窗口",
      "watch_list": ["下周关注"]
    }
  ],
  "key_events": [
    {"time": "周一", "event": "关注事件", "impact": "影响"}
  ],
  "highlights": ["本周要点1", "本周要点2", "本周要点3"]
}
```"""


def get_prompt(mode: str) -> str:
    return {"morning": MORNING_PROMPT, "closing": CLOSING_PROMPT, "weekly": WEEKLY_PROMPT}[mode]


def get_subtitle(mode: str) -> str:
    return {"morning": "早盘前简报", "closing": "收盘总结", "weekly": "周报特刊"}[mode]


# ─── AI 调用 ──────────────────────────────────────────────

def call_ai(news_data: dict, market_data: dict, mode: str) -> dict:
    import requests

    news_text = ""
    for source, items in news_data.items():
        news_text += f"\n## {source}\n"
        for item in items[:12]:
            line = f"- {item['title']}"
            if item.get("desc"):
                line += f"（{item['desc'][:80]}）"
            news_text += line + "\n"

    market_text = "\n## 市场数据\n"
    for idx in market_data.get("indices", []):
        market_text += f"- {idx['name']}: {idx['price']} ({idx['change_pct']})\n"

    nb = market_data.get("northbound")
    if nb:
        market_text += f"- 北向资金: 沪股通 {nb['hgt']:.1f}亿 | 深股通 {nb['sgt']:.1f}亿 | 合计 {nb['total']:.1f}亿\n"

    if market_data.get("top_sectors"):
        market_text += "- 涨幅前5板块: " + ", ".join(
            f"{s['name']}({'+' if s['change_pct']>0 else ''}{s['change_pct']}%)" for s in market_data["top_sectors"]
        ) + "\n"
    if market_data.get("bottom_sectors"):
        market_text += "- 跌幅前5板块: " + ", ".join(
            f"{s['name']}({s['change_pct']}%)" for s in market_data["bottom_sectors"]
        ) + "\n"

    for fc in market_data.get("forex_commodities", []):
        sign = "+" if fc["change_pct"] > 0 else ""
        market_text += f"- {fc['name']}: {fc['price']} ({sign}{fc['change_pct']}%)\n"

    if market_data.get("sector_flow"):
        market_text += "- 板块主力资金: " + " | ".join(
            s["title"] for s in market_data["sector_flow"][:5]
        ) + "\n"

    prompt = get_prompt(mode)
    today_str = datetime.now().strftime("%Y年%m月%d日")

    resp = requests.post(
        f"{AI_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"今天是 {today_str}，以下是原始数据：\n{news_text}\n{market_text}"},
            ],
            "temperature": 0.7,
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


def build_html(payload: dict, market_data: dict, mode: str) -> str:
    today = datetime.now()
    paper_names = {"morning": "每日7点", "closing": "每日复盘", "weekly": "周报特刊"}
    paper_name = paper_names.get(mode, "每日7点")
    subtitle = get_subtitle(mode)
    date_text = today.strftime("%Y年%m月%d日") + " · " + WEEKDAY_CN[today.weekday()]
    title = payload.get("title", "今日要闻")
    summary = payload.get("summary", "")
    market_comment = payload.get("market_comment", "")
    highlights = payload.get("highlights", [])[:6]
    sections = payload.get("sections", [])[:6]
    risk_level = ""
    watch_list = []

    # 提取投资建议的风险等级和关注列表
    for sec in sections:
        if sec.get("risk_level"):
            risk_level = sec["risk_level"]
        if sec.get("watch_list"):
            watch_list = sec["watch_list"]

    # ── 市场数据面板 HTML ──
    market_panel_html = _build_market_panel(market_data, risk_level)

    # ── 要点速览 ──
    highlights_html = ""
    if highlights:
        items_html = "".join(f"<li>{esc(h)}</li>" for h in highlights)
        highlights_html = f"""
        <aside class="float-rail">
          <section class="side-box content-card">
            <h3>要点速览</h3>
            <ul>{items_html}</ul>
          </section>
          {_build_watchlist_html(watch_list)}
        </aside>"""

    # ── 各板块 ──
    sections_html = ""

    if market_comment:
        sections_html += f"""
        <section class="section-card content-card market-comment-section">
          <h2>市场概览</h2>
          <p class="market-comment">{esc(market_comment)}</p>
        </section>"""

    for sec in sections:
        heading = esc(sec.get("heading", ""))
        body = sec.get("body", "")
        items = sec.get("items", [])
        risk = sec.get("risk_level", "")
        bullish = sec.get("bullish", [])
        bearish = sec.get("bearish", [])

        inner_html = ""

        if risk and (bullish or bearish):
            inner_html += _build_advice_card(sec)
        else:
            if risk:
                risk_cls = {"防守": "risk-defense", "平衡": "risk-balance", "进攻": "risk-offense"}.get(risk, "risk-balance")
                inner_html += f'<div class="risk-badge {risk_cls}">{esc(risk)}</div>'

            if body:
                paragraphs = [p.strip() for p in body.split("\n") if p.strip()]
                inner_html += "".join(f"<p>{esc(p)}</p>" for p in paragraphs)

            if items:
                inner_html += "<ul class='news-items'>"
                for item in items[:6]:
                    text = esc(item.get("text", ""))
                    impact = item.get("impact_chain", "")
                    tags = item.get("tags", [])
                    confidence = item.get("confidence", "")

                    tags_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags[:4])
                    confidence_cls = {"已证实": "conf-confirmed", "待确认": "conf-pending", "传闻": "conf-rumor"}.get(confidence, "conf-pending")
                    conf_html = f'<span class="confidence {confidence_cls}">{esc(confidence)}</span>' if confidence else ""
                    impact_html = f'<div class="impact-chain">→ {esc(impact)}</div>' if impact else ""

                    inner_html += f"""<li>
                        <div class="news-text">{text} {conf_html}</div>
                        {impact_html}
                        <div class="news-tags">{tags_html}</div>
                    </li>"""
                inner_html += "</ul>"

        sections_html += f"""
        <section class="section-card content-card">
          <h2>{heading}</h2>
          {inner_html}
        </section>"""

    # 关键时间节点
    key_events = payload.get("key_events", [])
    if key_events:
        sections_html += _build_key_events_html(key_events)

    summary_html = f'<div class="summary">{esc(summary)}</div>' if summary else ""
    has_rail = " has-rail" if highlights else ""

    footer_note = "数据来源：新华社 · 财联社 · 东方财富 · 华尔街见闻 · 雪球 | 以上内容由 AI 生成，不构成投资建议，据此操作风险自担"

    return _render_full_html(
        paper_name=paper_name, subtitle=subtitle, date_text=date_text,
        title=title, summary_html=summary_html, market_panel_html=market_panel_html,
        highlights_html=highlights_html, sections_html=sections_html,
        has_rail=has_rail, footer_note=footer_note,
    )


def _build_market_panel(market_data: dict, risk_level: str) -> str:
    if not market_data or not market_data.get("indices"):
        return ""

    week_changes = market_data.get("week_changes", {})
    name_to_week = {"上证指数": "上证", "深证成指": "深证", "创业板指": "创业板"}

    indices_html = ""
    for idx in market_data.get("indices", [])[:7]:
        pct = idx.get("change_pct", "0%")
        num = float(str(pct).replace("%", "").replace("+", ""))
        cls = "up" if num > 0 else ("down" if num < 0 else "flat")
        arrow = "&#9650;" if num > 0 else ("&#9660;" if num < 0 else "&#9644;")

        week_key = name_to_week.get(idx["name"], "")
        week_pct = week_changes.get(week_key)
        week_html = ""
        if week_pct is not None:
            w_cls = "up" if week_pct > 0 else ("down" if week_pct < 0 else "flat")
            w_sign = "+" if week_pct > 0 else ""
            week_html = f'<div class="idx-week {w_cls}">周 {w_sign}{week_pct}%</div>'

        indices_html += f"""
        <div class="idx-item {cls}">
          <div class="idx-name">{esc(idx['name'])}</div>
          <div class="idx-price">{arrow} {idx['price']}</div>
          <div class="idx-pct">{esc(pct)}</div>
          {week_html}
        </div>"""

    nb = market_data.get("northbound")
    nb_html = ""
    if nb:
        total = nb["total"]
        nb_cls = "up" if total > 0 else "down"
        nb_arrow = "&#9650;" if total > 0 else "&#9660;"
        nb_5d = nb.get("total_5d")
        nb_5d_html = ""
        if nb_5d is not None:
            nb_5d_cls = "up" if nb_5d > 0 else "down"
            nb_5d_html = f' <span class="nb-5d {nb_5d_cls}">| 近5日累计 {nb_5d:+.1f}亿</span>'
        nb_html = f"""
        <div class="nb-row">
          <span class="nb-label">{nb_arrow} 北向资金</span>
          <span class="nb-val {nb_cls}">沪 {nb['hgt']:+.1f}亿 | 深 {nb['sgt']:+.1f}亿 | 合计 {nb['total']:+.1f}亿</span>
          {nb_5d_html}
        </div>"""

    sectors_html = ""
    top = market_data.get("top_sectors", [])[:5]
    bottom = market_data.get("bottom_sectors", [])[:5]
    if top or bottom:
        top_items = " ".join(f'<span class="sector up">&#9650; {esc(s["name"])} +{s["change_pct"]}%</span>' for s in top)
        bottom_items = " ".join(f'<span class="sector down">&#9660; {esc(s["name"])} {s["change_pct"]}%</span>' for s in bottom)
        sectors_html = f"""
        <div class="sector-row">
          <div class="sector-group"><span class="sector-label">涨</span>{top_items}</div>
          <div class="sector-group"><span class="sector-label">跌</span>{bottom_items}</div>
        </div>"""

    fx_html = ""
    for fc in market_data.get("forex_commodities", []):
        sign = "+" if fc["change_pct"] > 0 else ""
        cls = "up" if fc["change_pct"] > 0 else "down"
        arrow = "&#9650;" if fc["change_pct"] > 0 else "&#9660;"
        fx_html += f'<span class="fx-item {cls}">{arrow} {esc(fc["name"])} {fc["price"]} ({sign}{fc["change_pct"]}%)</span> '

    risk_html = ""
    if risk_level:
        risk_cls = {"防守": "risk-defense", "平衡": "risk-balance", "进攻": "risk-offense"}.get(risk_level, "risk-balance")
        risk_html = f'<div class="risk-indicator {risk_cls}">今日策略：{esc(risk_level)}</div>'

    return f"""
    <div class="market-panel">
      <div class="panel-header">
        <span class="panel-title">市场数据</span>
        {risk_html}
      </div>
      <div class="idx-grid">{indices_html}</div>
      {nb_html}
      {sectors_html}
      <div class="fx-row">{fx_html}</div>
    </div>"""


def _build_advice_card(sec: dict) -> str:
    risk = sec.get("risk_level", "平衡")
    position = sec.get("position", "")
    style = sec.get("style", "")
    bullish = sec.get("bullish", [])
    bearish = sec.get("bearish", [])
    risk_warning = sec.get("risk_warning", "")
    time_window = sec.get("time_window", "")

    risk_cls = {"防守": "risk-defense", "平衡": "risk-balance", "进攻": "risk-offense"}.get(risk, "risk-balance")
    risk_emoji = {"防守": "&#128737;", "平衡": "&#9878;&#65039;", "进攻": "&#9889;"}.get(risk, "&#9878;&#65039;")

    header_html = f"""
    <div class="advice-header">
      <div class="advice-strategy {risk_cls}">
        <span class="advice-emoji">{risk_emoji}</span>
        <span class="advice-risk-label">策略倾向：{esc(risk)}</span>
      </div>
      <div class="advice-meta">"""
    if position:
        header_html += f'<span class="advice-position">建议仓位：{esc(position)}</span>'
    if style:
        header_html += f'<span class="advice-style">{esc(style)}</span>'
    header_html += "</div></div>"

    bull_html = ""
    if bullish:
        bull_items = "".join(f"<li>&#9650; {esc(b)}</li>" for b in bullish[:4])
        bull_html = f'<div class="advice-section advice-bull"><h4>看多方向</h4><ul>{bull_items}</ul></div>'

    bear_html = ""
    if bearish:
        bear_items = "".join(f"<li>&#9660; {esc(b)}</li>" for b in bearish[:4])
        bear_html = f'<div class="advice-section advice-bear"><h4>规避方向</h4><ul>{bear_items}</ul></div>'

    warn_html = ""
    if risk_warning:
        warn_html = f'<div class="advice-warning">&#9888;&#65039; {esc(risk_warning)}</div>'

    tw_html = ""
    if time_window:
        tw_html = f'<div class="advice-timewindow">&#128337; {esc(time_window)}</div>'

    return f"""
    <div class="advice-card">
      {header_html}
      <div class="advice-body">
        {bull_html}
        {bear_html}
      </div>
      {warn_html}
      {tw_html}
    </div>"""


def _build_key_events_html(events: list) -> str:
    items_html = ""
    for ev in events[:6]:
        t = esc(ev.get("time", ""))
        e = esc(ev.get("event", ""))
        impact = ev.get("impact", "")
        impact_html = f'<span class="ke-impact">— {esc(impact)}</span>' if impact else ""
        items_html += f"""
        <div class="ke-item">
          <span class="ke-time">{t}</span>
          <span class="ke-event">{e} {impact_html}</span>
        </div>"""
    return f"""
    <section class="section-card content-card key-events-section">
      <h2>&#128337; 关键时间节点</h2>
      <div class="ke-list">{items_html}</div>
    </section>"""


def _build_watchlist_html(watch_list: list) -> str:
    if not watch_list:
        return ""
    items = "".join(f"<li>{esc(w)}</li>" for w in watch_list[:6])
    return f"""
    <section class="side-box content-card watchlist">
      <h3>关注清单</h3>
      <ul>{items}</ul>
    </section>"""


def _render_full_html(**kw) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(kw['title'])}</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700;900&display=swap');
    :root {{
      --paper: #f6f1e6; --ink: #141414; --muted: #5d5a53; --line: #1d1d1d;
      --soft-line: #c8beb0; --accent: #c0392b; --card: rgba(255,255,255,0.28);
      --rail-width: 31%; --rail-gap: 24px;
      --green: #16a34a; --red: #dc2626; --amber: #d97706;
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
      background-image: radial-gradient(rgba(0,0,0,0.028) 0.8px, transparent 0.8px),
        linear-gradient(rgba(255,255,255,0.18), rgba(0,0,0,0));
      background-size: 7px 7px, 100% 100%; opacity: 0.6;
    }}

    /* ── 顶栏 ── */
    .topbar {{
      position: relative; z-index: 1;
      display: flex; justify-content: space-between; align-items: end; gap: 20px;
      border-top: 6px solid var(--accent); border-bottom: 2px solid var(--line);
      padding: 14px 0 12px; margin-bottom: 26px;
    }}
    .paper-name {{ font-size: 60px; font-weight: 900; letter-spacing: 6px; line-height: 1; color: var(--accent); }}
    .paper-subtitle {{ font-size: 22px; color: var(--muted); margin-left: 16px; letter-spacing: 2px; }}
    .issue {{ font-size: 22px; color: var(--muted); white-space: nowrap; text-align: right; line-height: 1.4; }}

    /* ── 标题 ── */
    .hero {{ position: relative; z-index: 1; margin-bottom: 20px; }}
    .hero h1 {{ margin: 0; font-size: 54px; line-height: 1.15; font-weight: 900; letter-spacing: 1px; }}
    .summary {{
      margin-top: 16px; font-size: 23px; line-height: 1.75; color: var(--muted);
      border-left: 6px solid var(--accent); padding-left: 18px;
    }}

    /* ── 市场数据面板 ── */
    .market-panel {{
      position: relative; z-index: 1; margin-bottom: 24px; padding: 20px 24px;
      background: rgba(20,20,20,0.04); border: 1.5px solid var(--soft-line); border-radius: 4px;
    }}
    .panel-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }}
    .panel-title {{ font-size: 20px; font-weight: 900; letter-spacing: 2px; color: var(--accent); }}
    .risk-indicator {{
      font-size: 16px; font-weight: 700; padding: 4px 14px; border-radius: 3px; letter-spacing: 1px;
    }}
    .risk-defense {{ background: #dbeafe; color: #1d4ed8; }}
    .risk-balance {{ background: #fef3c7; color: #92400e; }}
    .risk-offense {{ background: #fee2e2; color: #991b1b; }}

    .idx-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin-bottom: 12px; }}
    .idx-item {{ text-align: center; padding: 8px 4px; border-radius: 3px; background: rgba(255,255,255,0.5); }}
    .idx-name {{ font-size: 14px; color: var(--muted); margin-bottom: 2px; }}
    .idx-price {{ font-size: 18px; font-weight: 700; }}
    .idx-pct {{ font-size: 15px; font-weight: 700; }}
    .idx-item.up .idx-price, .idx-item.up .idx-pct {{ color: var(--red); }}
    .idx-item.down .idx-price, .idx-item.down .idx-pct {{ color: var(--green); }}
    .idx-item.flat .idx-price, .idx-item.flat .idx-pct {{ color: var(--muted); }}

    .idx-week {{ font-size: 12px; color: var(--muted); margin-top: 2px; }}
    .idx-week.up {{ color: var(--red); }}
    .idx-week.down {{ color: var(--green); }}

    .nb-row {{ font-size: 16px; margin-bottom: 10px; padding: 6px 0; border-bottom: 1px dashed var(--soft-line); }}
    .nb-5d {{ font-size: 14px; font-weight: 700; }}
    .nb-5d.up {{ color: var(--red); }}
    .nb-5d.down {{ color: var(--green); }}
    .nb-label {{ font-weight: 700; margin-right: 12px; }}
    .nb-val.up {{ color: var(--red); font-weight: 700; }}
    .nb-val.down {{ color: var(--green); font-weight: 700; }}

    .sector-row {{ margin-bottom: 10px; }}
    .sector-group {{ margin-bottom: 6px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
    .sector-label {{ font-size: 14px; font-weight: 900; padding: 2px 8px; border-radius: 2px; color: #fff; min-width: 24px; text-align: center; }}
    .sector-group:first-child .sector-label {{ background: var(--red); }}
    .sector-group:last-child .sector-label {{ background: var(--green); }}
    .sector {{ font-size: 14px; padding: 2px 8px; border-radius: 2px; background: rgba(255,255,255,0.6); }}
    .sector.up {{ color: var(--red); }}
    .sector.down {{ color: var(--green); }}

    .fx-row {{ font-size: 15px; display: flex; flex-wrap: wrap; gap: 16px; }}
    .fx-item.up {{ color: var(--red); }}
    .fx-item.down {{ color: var(--green); }}

    /* ── 内容区 ── */
    .story-wrap {{ position: relative; z-index: 1; }}
    .float-rail {{
      float: right; width: var(--rail-width); min-width: 290px;
      margin: 14px 0 18px var(--rail-gap); display: flex; flex-direction: column; gap: 16px;
    }}
    .story-main {{ min-width: 0; }}
    .story-main::after {{ content: ""; display: block; clear: both; }}
    .content-card {{ width: 100%; }}

    .section-card {{ border-top: none; padding-top: 16px; min-width: 0; clear: left; position: relative; width: 100%; }}
    .section-card::before {{
      content: ""; display: block; height: 2px; width: 100%;
      background: var(--line); margin-bottom: 16px;
    }}
    .story-wrap.has-rail .section-card::before {{ width: calc(100% - var(--rail-width) - var(--rail-gap)); }}
    .story-wrap.has-rail .section-card.after-rail::before {{ width: 100%; }}
    .market-comment-section::before {{ background: var(--accent); height: 3px; }}

    .section-card h2 {{ margin: 0 0 12px; font-size: 30px; line-height: 1.2; font-weight: 900; color: var(--accent); letter-spacing: 2px; }}
    .section-card p {{ margin: 0 0 12px; font-size: 21px; line-height: 1.8; text-align: justify; }}
    .market-comment {{ font-style: italic; color: var(--muted); }}

    .risk-badge {{
      display: inline-block; font-size: 16px; font-weight: 700; padding: 4px 14px;
      border-radius: 3px; margin-bottom: 12px; letter-spacing: 1px;
    }}

    .news-items {{ margin: 8px 0 0; padding: 0; list-style: none; }}
    .news-items li {{ margin: 0 0 16px; padding: 0 0 14px; border-bottom: 1px dashed var(--soft-line); }}
    .news-items li:last-child {{ border-bottom: none; margin-bottom: 0; padding-bottom: 0; }}
    .news-text {{ font-size: 21px; line-height: 1.7; font-weight: 500; }}
    .impact-chain {{
      font-size: 18px; line-height: 1.6; color: var(--muted); margin-top: 4px;
      padding-left: 16px; border-left: 3px solid var(--amber);
    }}
    .news-tags {{ margin-top: 6px; display: flex; flex-wrap: wrap; gap: 6px; }}
    .tag {{
      font-size: 13px; padding: 2px 10px; border-radius: 2px;
      background: rgba(192,57,43,0.08); color: var(--accent); font-weight: 600;
    }}
    .confidence {{
      font-size: 13px; padding: 1px 8px; border-radius: 2px; margin-left: 8px;
      font-weight: 600; vertical-align: middle;
    }}
    .conf-confirmed {{ background: #dcfce7; color: #166534; }}
    .conf-pending {{ background: #fef9c3; color: #854d0e; }}
    .conf-rumor {{ background: #fee2e2; color: #991b1b; }}

    /* ── AI投资建议卡片 ── */
    .advice-card {{
      background: rgba(255,255,255,0.45); border: 1.5px solid var(--soft-line);
      border-radius: 6px; padding: 20px 24px; margin-top: 4px;
    }}
    .advice-header {{ margin-bottom: 16px; }}
    .advice-strategy {{
      display: inline-flex; align-items: center; gap: 8px;
      font-size: 20px; font-weight: 900; padding: 6px 16px; border-radius: 4px;
      margin-bottom: 8px;
    }}
    .advice-emoji {{ font-size: 22px; }}
    .advice-meta {{ display: flex; gap: 16px; font-size: 16px; color: var(--muted); margin-top: 6px; }}
    .advice-position {{ font-weight: 700; }}
    .advice-style {{ font-style: italic; }}
    .advice-body {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 14px; }}
    .advice-section h4 {{ margin: 0 0 8px; font-size: 17px; font-weight: 900; letter-spacing: 1px; }}
    .advice-bull h4 {{ color: var(--red); }}
    .advice-bear h4 {{ color: var(--green); }}
    .advice-section ul {{ margin: 0; padding-left: 0; list-style: none; }}
    .advice-section li {{ font-size: 18px; line-height: 1.7; margin-bottom: 4px; padding-left: 4px; }}
    .advice-bull li {{ color: #991b1b; }}
    .advice-bear li {{ color: #166534; }}
    .advice-warning {{
      font-size: 17px; line-height: 1.6; padding: 10px 14px;
      background: #fef3c7; border-left: 4px solid var(--amber); border-radius: 3px;
      margin-bottom: 8px; color: #78350f;
    }}
    .advice-timewindow {{
      font-size: 16px; color: var(--muted); line-height: 1.5;
    }}

    /* ── 关键时间节点 ── */
    .key-events-section h2 {{ font-size: 26px; }}
    .ke-list {{ display: flex; flex-direction: column; gap: 8px; }}
    .ke-item {{
      display: flex; align-items: baseline; gap: 12px; font-size: 18px;
      padding: 6px 0; border-bottom: 1px dashed var(--soft-line);
    }}
    .ke-item:last-child {{ border-bottom: none; }}
    .ke-time {{
      font-weight: 900; color: var(--accent); min-width: 70px; white-space: nowrap;
    }}
    .ke-event {{ line-height: 1.6; }}
    .ke-impact {{ color: var(--muted); font-size: 16px; }}

    /* ── 侧栏 ── */
    .side-box {{ border: 2px solid var(--line); background: var(--card); padding: 18px 20px; min-width: 0; }}
    .side-box h3 {{ margin: 0 0 14px; font-size: 22px; font-weight: 900; letter-spacing: 2px; color: var(--accent); }}
    .side-box ul {{ margin: 0; padding-left: 22px; }}
    .side-box li {{ margin: 0 0 10px; font-size: 19px; line-height: 1.6; }}
    .watchlist {{ border-color: var(--accent); }}
    .watchlist h3 {{ color: var(--ink); }}

    /* ── 底部 ── */
    .footer {{
      position: relative; z-index: 1; margin-top: 32px; padding-top: 14px;
      border-top: 2px solid var(--line);
    }}
    .footer-main {{ display: flex; justify-content: space-between; gap: 16px; font-size: 16px; color: var(--muted); }}
    .stamp {{
      display: inline-flex; align-items: center; gap: 8px;
      font-size: 16px; font-weight: 800; letter-spacing: 1px; color: var(--accent);
    }}
    .stamp::before {{ content: ""; width: 12px; height: 12px; border-radius: 999px; background: var(--accent); display: inline-block; }}
    .disclaimer {{
      margin-top: 12px; font-size: 13px; color: #9ca3af; line-height: 1.5;
      padding: 8px 12px; background: rgba(0,0,0,0.03); border-radius: 3px;
    }}
  </style>
</head>
<body>
  <article class="page">
    <header class="topbar">
      <div><span class="paper-name">{esc(kw['paper_name'])}</span><span class="paper-subtitle">{esc(kw['subtitle'])}</span></div>
      <div class="issue">{esc(kw['date_text'])}</div>
    </header>

    <section class="hero">
      <h1>{esc(kw['title'])}</h1>
      {kw['summary_html']}
    </section>

    {kw['market_panel_html']}

    <section class="story-wrap{kw['has_rail']}" id="story-wrap">
      {kw['highlights_html']}
      <div class="story-main" id="story-main">
        {kw['sections_html']}
      </div>
    </section>
    <script>
      (() => {{
        const wrap = document.getElementById('story-wrap');
        const rail = wrap?.querySelector('.float-rail');
        const sections = Array.from(wrap?.querySelectorAll('.section-card') || []);
        if (!wrap || !rail || !sections.length) return;
        const apply = () => {{
          const railBottom = rail.offsetTop + rail.offsetHeight;
          for (const sec of sections) {{
            if (sec.offsetTop >= railBottom - 8) sec.classList.add('after-rail');
            else sec.classList.remove('after-rail');
          }}
        }};
        if (document.fonts && document.fonts.ready) document.fonts.ready.then(apply);
        else apply();
      }})();
    </script>

    <footer class="footer">
      <div class="footer-main">
        <div>{esc(kw['footer_note'].split('|')[0].strip())}</div>
        <div class="stamp">{esc(kw["paper_name"])}</div>
      </div>
      <div class="disclaimer">⚠️ 免责声明：以上所有内容（含"AI投资建议"板块）均由人工智能自动生成，仅供参考，不构成任何投资建议。市场有风险，投资需谨慎，据此操作风险自担。信息确认度标注仅供参考，请以官方渠道为准。</div>
    </footer>
  </article>
</body>
</html>"""


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


# ─── 历史存档 ─────────────────────────────────────────────

def archive_brief(brief: dict, market_data: dict, mode: str, now: datetime):
    """将简报 JSON 存档到 history/ 目录，供周度复盘回溯。"""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    date_str = now.strftime("%Y%m%d")
    archive = {
        "date": now.strftime("%Y-%m-%d"),
        "weekday": WEEKDAY_CN[now.weekday()],
        "mode": mode,
        "brief": brief,
        "market_snapshot": {
            "indices": market_data.get("indices", []),
            "northbound": market_data.get("northbound"),
            "top_sectors": market_data.get("top_sectors", [])[:5],
            "bottom_sectors": market_data.get("bottom_sectors", [])[:5],
            "forex_commodities": market_data.get("forex_commodities", []),
        },
    }
    path = HISTORY_DIR / f"{mode}_{date_str}.json"
    path.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   📁 存档: {path}")


# ─── 主入口 ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="每日7点新闻简报")
    parser.add_argument("--mode", choices=["morning", "closing", "weekly"], default="morning")
    parser.add_argument("-o", "--output", help="PNG output path")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    ts = now.strftime("%Y%m%d_%H%M%S")
    mode = args.mode

    print(f"📰 模式: {mode} ({get_subtitle(mode)})")

    print("1/4 抓取新闻...")
    news_data = fetch_all_news()
    total = sum(len(v) for v in news_data.values())
    for src, items in news_data.items():
        print(f"   {src}: {len(items)} 条")
    print(f"   共 {total} 条")

    if total == 0:
        print("[ERROR] 没有抓到任何新闻", file=sys.stderr)
        sys.exit(1)

    print("2/4 抓取市场数据...")
    market_data = fetch_all_market_data()
    print(f"   指数: {len(market_data.get('indices', []))} | 板块: {len(market_data.get('top_sectors', []))}/{len(market_data.get('bottom_sectors', []))}")

    print("3/4 AI 提炼中...")
    brief = call_ai(news_data, market_data, mode)

    json_path = OUTPUT_DIR / f"brief_{mode}_{ts}.json"
    json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")

    # 存档到 history/ 供周度复盘使用
    archive_brief(brief, market_data, mode, now)

    print("4/4 渲染 HTML + 截图...")
    html_content = build_html(brief, market_data, mode)
    html_path = OUTPUT_DIR / f"brief_{mode}_{ts}.html"
    html_path.write_text(html_content, encoding="utf-8")

    png_path = Path(args.output) if args.output else OUTPUT_DIR / f"brief_{mode}_{ts}.png"
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
