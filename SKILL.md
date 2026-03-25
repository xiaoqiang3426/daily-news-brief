# 每日七点 — Daily News Brief v2

中文财经新闻简报，支持早盘前简报、收盘总结、周报特刊三种模式。

## 功能

- **5层新闻源**：新华社（政策层）、财联社+东方财富（市场层）、华尔街见闻（宏观层）、东方财富行情API（数据层）、雪球（情绪层）
- **5大板块**：市场概览（数据面板）、政策动态、财经要闻、科技产业、AI投资建议
- **增强功能**：板块关联标注、影响链分析、信息确认度、风险声明、策略倾向指示器

## 四种模式

| 模式 | 推送时间 | 特点 |
|------|----------|------|
| `morning` | 每日 07:00 | 决策导向，关注开盘前要素 |
| `closing` | 每日 15:15 | 复盘导向，总结当日行情 |
| `weekly` | 周日 21:00 | 周报特刊，政策汇总+策略展望 |
| `review` | 周六 10:00 | 投资复盘，命中率验证+经验教训 |

## 执行

```bash
cd ~/.openclaw/workspace/skills/daily-news-brief

# 早盘前简报（默认）
python3 scripts/generate_brief.py --mode morning

# 收盘总结
python3 scripts/generate_brief.py --mode closing

# 周报特刊
python3 scripts/generate_brief.py --mode weekly

# 指定输出路径
python3 scripts/generate_brief.py --mode morning -o /tmp/daily7_latest.png
```

脚本输出 `PNG_PATH=<路径>` 到 stdout，将图片通过 QQ 发给用户：

```
<qqimg>/tmp/daily-news-brief/brief_morning_YYYYMMDD_HHMMSS.png</qqimg>
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| AI_BASE_URL | http://localhost:18258/v1 | OpenAI 兼容 API |
| AI_API_KEY | 123456 | API Key |
| AI_MODEL | gpt-5.2 | 模型 ID |
| OUTPUT_DIR | /tmp/daily-news-brief | 输出目录 |

## 依赖

- Python 3.9+
- requests
- playwright + chromium (`pip3 install playwright && python3 -m playwright install chromium`)

## 投资复盘报告

独立的周度投资建议复盘，核心功能：

- 从 `history/` 目录加载一周内的每日简报存档
- 提取所有看多/规避建议，逐条 AI 判定命中/未命中/待验证
- 计算命中率，生成环形图可视化
- 包含市场回顾、经验教训、下周策略调整

```bash
# 周度复盘（默认回溯7天）
python3 scripts/generate_review.py

# 指定回溯天数
python3 scripts/generate_review.py --days 5

# 指定结束日期
python3 scripts/generate_review.py --end-date 20260322
```

## 历史存档

每日简报生成时自动存档到 `history/` 目录（JSON 格式），供周度复盘回溯使用。

存档文件命名：`{mode}_{YYYYMMDD}.json`（如 `morning_20260323.json`）

## 文件结构

```
skills/daily-news-brief/
├── SKILL.md
├── scripts/
│   ├── fetch_news.py        # 5层新闻源抓取 + 市场数据
│   ├── generate_brief.py    # 每日简报 pipeline (AI + HTML + 截图 + 存档)
│   └── generate_review.py   # 周度复盘报告 (命中率验证 + HTML + 截图)
├── history/                  # 每日简报 JSON 存档
└── output/                   # 生成的 HTML/PNG
```
