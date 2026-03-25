# 每日七点 — Daily News Brief

中文财经新闻简报自动生成器，抓取多源新闻 + 市场数据，AI 提炼后渲染为精美报纸风格图片。

![Python 3.9+](https://img.shields.io/badge/Python-3.9+-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)

## 效果预览

生成的简报是一张报纸风格的 PNG 图片，包含：

- 市场数据面板（指数、北向资金、板块涨跌、汇率商品）
- 政策动态 / 财经要闻 / 科技产业（含影响链分析、板块标注、信息确认度）
- AI 投资建议（策略倾向、看多/规避方向、风险提示）
- 关键时间节点日历
- 要点速览侧栏

## 5 层新闻源

| 层 | 来源 | 覆盖 |
|---|---|---|
| 政策层 | 人民网政治频道 RSS | 国务院/部委政策 |
| 市场层 | 财联社电报、东方财富快讯 | 实时市场快讯 |
| 宏观层 | 华尔街见闻 | 全球宏观 |
| 数据层 | 东方财富行情 API | 指数、北向资金、板块、汇率 |
| 情绪层 | 雪球热股 | 市场情绪 |

## 四种模式

| 模式 | 场景 | 特点 |
|------|------|------|
| `morning` | 早盘前 07:00 | 决策导向，关注开盘前要素 |
| `closing` | 收盘后 15:15 | 复盘导向，总结当日行情 |
| `weekly` | 周日 21:00 | 周报特刊，政策汇总+策略展望 |
| `review` | 周六 10:00 | 投资复盘，命中率验证+经验教训 |

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
```

### 配置环境变量

```bash
export AI_BASE_URL=https://api.openai.com/v1   # OpenAI 兼容 API 地址
export AI_API_KEY=sk-your-api-key               # API Key
export AI_MODEL=gpt-4o                          # 模型名称
```

支持任何 OpenAI 兼容 API（OpenAI、DeepSeek、本地 Ollama 等）。

### 运行

```bash
# 早盘简报（默认）
python3 scripts/generate_brief.py

# 收盘总结
python3 scripts/generate_brief.py --mode closing

# 周报特刊
python3 scripts/generate_brief.py --mode weekly

# 投资复盘（回溯 7 天）
python3 scripts/generate_review.py

# 指定输出路径
python3 scripts/generate_brief.py -o ~/Desktop/today.png
```

输出 PNG 路径会打印到 stdout：`PNG_PATH=/tmp/daily-news-brief/brief_morning_20260325_070000.png`

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `AI_BASE_URL` | `http://localhost:18258/v1` | OpenAI 兼容 API 地址 |
| `AI_API_KEY` | `123456` | API Key |
| `AI_MODEL` | `gpt-5.2` | 模型 ID |
| `OUTPUT_DIR` | `/tmp/daily-news-brief` | 输出目录 |
| `HISTORY_DIR` | `./history` | 历史存档目录 |

## 文件结构

```
daily-news-brief/
├── README.md
├── SKILL.md              # OpenClaw Agent Skill 描述
├── requirements.txt
├── scripts/
│   ├── fetch_news.py     # 5 层新闻源抓取 + 市场数据
│   ├── generate_brief.py # 每日简报 pipeline (AI + HTML + 截图 + 存档)
│   └── generate_review.py# 周度复盘报告 (命中率验证 + HTML + 截图)
├── history/              # 每日简报 JSON 存档（gitignored）
└── output/               # 生成的 HTML/PNG（gitignored）
```

## 作为 OpenClaw Skill 使用

本项目同时是一个 [OpenClaw](https://github.com/nicepkg/openclaw) Agent Skill。将整个目录放到 `~/.openclaw/workspace/skills/daily-news-brief/`，配置 cron 定时触发即可实现每日自动推送。

## 免责声明

⚠️ 所有内容（含"AI 投资建议"板块）均由 AI 自动生成，仅供学习参考，**不构成任何投资建议**。市场有风险，投资需谨慎，据此操作风险自担。

## License

[MIT](LICENSE)
