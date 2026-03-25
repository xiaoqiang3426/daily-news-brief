#!/usr/bin/env python3
"""
新闻抓取模块 — 5层新闻源体系
1. 政策层：新华社
2. 市场层：财联社电报、东方财富
3. 宏观层：华尔街见闻
4. 数据层：AKShare (指数、北向资金、板块涨跌)
5. 情绪层：雪球热帖
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from typing import Any

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
TIMEOUT = 20


# ─── 政策层 ────────────────────────────────────────────────

def fetch_people_politics() -> list[dict[str, str]]:
    """人民网政治频道 RSS"""
    import xml.etree.ElementTree as ET
    resp = requests.get(
        "http://www.people.com.cn/rss/politics.xml",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        desc = item.findtext("description", "")
        if title and not title.startswith("学习") and "足迹" not in title:
            items.append({
                "title": title,
                "url": link,
                "source": "人民网",
                "desc": re.sub(r"<[^>]+>", "", desc or "")[:120],
            })
    return items[:20]


def fetch_thepaper() -> list[dict[str, str]]:
    """澎湃新闻热门"""
    resp = requests.get(
        "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("hotNews", []):
        items.append({
            "title": k.get("name", ""),
            "url": f"https://www.thepaper.cn/newsDetail_forward_{k.get('contId', '')}",
            "source": "澎湃新闻",
        })
    return items[:20]


# ─── 市场层 ────────────────────────────────────────────────

def _cls_sign(params: dict[str, str]) -> str:
    sp = urllib.parse.urlencode(sorted(params.items()))
    sha1 = hashlib.sha1(sp.encode()).hexdigest()
    return hashlib.md5(sha1.encode()).hexdigest()


def fetch_cls() -> list[dict[str, str]]:
    """财联社电报（实时快讯）"""
    base_params = {"appName": "CailianpressWeb", "os": "web", "sv": "7.7.5"}
    sign = _cls_sign(base_params)
    base_params["sign"] = sign
    resp = requests.get(
        "https://www.cls.cn/nodeapi/updateTelegraphList",
        params=base_params,
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("roll_data", []):
        if k.get("is_ad"):
            continue
        items.append({
            "title": k.get("title") or k.get("brief", ""),
            "url": f"https://www.cls.cn/detail/{k.get('id', '')}",
            "source": "财联社",
        })
    return items[:30]


EM_HEADERS = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}


def fetch_eastmoney() -> list[dict[str, str]]:
    """东方财富 — 财经要闻"""
    resp = requests.get(
        "https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
        params={
            "client": "web",
            "biz": "web_home_flash",
            "fastColumn": "",
            "sortEnd": "",
            "pageSize": "30",
            "req_trace": str(int(time.time() * 1000)),
        },
        headers=EM_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("fastNewsList", []):
        items.append({
            "title": k.get("title", ""),
            "url": k.get("url", ""),
            "source": "东方财富",
            "desc": k.get("summary", ""),
        })
    return items[:30]


def fetch_eastmoney_hotstock() -> list[dict[str, str]]:
    """东方财富 — 板块资金流向"""
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": "1",
                "pz": "10",
                "po": "1",
                "np": "1",
                "fltt": "2",
                "invt": "2",
                "fid": "f62",
                "fs": "m:90+t:2",
                "fields": "f12,f14,f2,f3,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87",
            },
            headers=EM_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        items = []
        for k in data.get("data", {}).get("diff", []):
            name = k.get("f14", "")
            change_pct = k.get("f3", 0)
            main_flow = k.get("f62", 0)
            sign = "+" if change_pct > 0 else ""
            flow_yi = main_flow / 100000000
            flow_sign = "+" if flow_yi > 0 else ""
            items.append({
                "title": f"{name} {sign}{change_pct}% 主力净流入{flow_sign}{flow_yi:.1f}亿",
                "source": "东方财富-板块",
                "url": "",
            })
        return items[:10]
    except Exception as e:
        print(f"[WARN] eastmoney hotstock failed: {e}", file=sys.stderr)
        return []


# ─── 宏观层 ────────────────────────────────────────────────

def fetch_wallstreetcn() -> list[dict[str, str]]:
    """华尔街见闻 — 实时快讯"""
    resp = requests.get(
        "https://api-one-wscn.awtmt.com/apiv1/content/lives",
        params={"channel": "global-channel", "limit": "30"},
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("items", []):
        title = k.get("title") or k.get("content_text", "")
        title = re.sub(r"<[^>]+>", "", title)[:120]
        items.append({
            "title": title,
            "url": f"https://wallstreetcn.com/live/{k.get('id', '')}",
            "source": "华尔街见闻",
        })
    return items[:30]


# ─── 数据层 ────────────────────────────────────────────────

def fetch_market_data() -> dict[str, Any]:
    """通过东方财富接口获取市场行情数据"""
    result = {
        "indices": [],
        "northbound": None,
        "top_sectors": [],
        "bottom_sectors": [],
        "forex_commodities": [],
    }

    # 主要指数
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": "2",
                "fields": "f2,f3,f4,f12,f14",
                "secids": "1.000001,0.399001,0.399006,2.HSI,100.NDX,100.SPX,100.DJIA",
            },
            headers=EM_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        for k in (data.get("data") or {}).get("diff", []):
            name = k.get("f14", "")
            price = k.get("f2", 0)
            change_pct = k.get("f3", 0)
            change_val = k.get("f4", 0)
            sign = "+" if change_pct > 0 else ""
            result["indices"].append({
                "name": name,
                "price": price,
                "change_pct": f"{sign}{change_pct}%",
                "change_val": change_val,
            })
    except Exception as e:
        print(f"[WARN] indices failed: {e}", file=sys.stderr)

    # 北向资金 — 实时接口
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/kamt/get",
            params={"fields1": "f1,f2,f3,f4", "fields2": "f51,f52,f53,f54,f55,f56"},
            headers=EM_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        d = data.get("data") or {}
        hk2sh = d.get("hk2sh", {})
        hk2sz = d.get("hk2sz", {})
        hgt = hk2sh.get("dayNetAmtIn", 0) / 10000
        sgt = hk2sz.get("dayNetAmtIn", 0) / 10000
        result["northbound"] = {
            "date": hk2sh.get("date2", hk2sh.get("date", "")),
            "hgt": hgt,
            "sgt": sgt,
            "total": hgt + sgt,
        }
    except Exception as e:
        print(f"[WARN] northbound failed: {e}", file=sys.stderr)

    # 板块涨幅 TOP5 / BOTTOM5
    try:
        for _direction, po_val, key in [("top", "1", "top_sectors"), ("bottom", "0", "bottom_sectors")]:
            resp = requests.get(
                "https://push2.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": "1", "pz": "5", "po": po_val, "np": "1",
                    "fltt": "2", "invt": "2", "fid": "f3",
                    "fs": "m:90+t:2",
                    "fields": "f2,f3,f12,f14",
                },
                headers=EM_HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            for k in (data.get("data") or {}).get("diff", []):
                result[key].append({
                    "name": k.get("f14", ""),
                    "change_pct": k.get("f3", 0),
                })
    except Exception as e:
        print(f"[WARN] sectors failed: {e}", file=sys.stderr)

    # 汇率和商品
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params={
                "fltt": "2",
                "fields": "f2,f3,f4,f12,f14",
                "secids": "133.USDCNH,101.GC00Y",
            },
            headers=EM_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        name_map = {"USDCNH": "美元/离岸人民币", "GC00Y": "COMEX黄金"}
        for k in (data.get("data") or {}).get("diff", []):
            code = k.get("f12", "")
            if code in name_map:
                result["forex_commodities"].append({
                    "name": name_map[code],
                    "price": k.get("f2", 0),
                    "change_pct": k.get("f3", 0),
                })
    except Exception as e:
        print(f"[WARN] forex failed: {e}", file=sys.stderr)

    # 北向资金近5日累计
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/kamt/get",
            params={"fields1": "f1,f2,f3,f4", "fields2": "f51,f52,f53,f54,f55,f56"},
            headers=EM_HEADERS,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        d = resp.json().get("data") or {}
        days_sh = d.get("hk2sh", {}).get("netBuyDayList", [])
        days_sz = d.get("hk2sz", {}).get("netBuyDayList", [])
        nb_5d = 0
        for i in range(min(5, len(days_sh))):
            sh_val = days_sh[i].get("dayNetAmtIn", 0) if i < len(days_sh) else 0
            sz_val = days_sz[i].get("dayNetAmtIn", 0) if i < len(days_sz) else 0
            nb_5d += (sh_val + sz_val) / 10000
        if result.get("northbound"):
            result["northbound"]["total_5d"] = round(nb_5d, 2)
    except Exception as e:
        print(f"[WARN] northbound 5d failed: {e}", file=sys.stderr)

    # 指数周涨跌（本周累计）
    try:
        week_indices = {}
        for secid, name in [("1.000001", "上证"), ("0.399001", "深证"), ("0.399006", "创业板")]:
            time.sleep(0.5)
            resp = requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get",
                params={
                    "secid": secid,
                    "fields1": "f1,f2,f3,f4,f5",
                    "fields2": "f51,f52,f53,f54,f55,f56",
                    "klt": "101",
                    "fqt": "0",
                    "beg": "0",
                    "end": "20500101",
                    "lmt": "6",
                },
                headers=EM_HEADERS,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            klines = (resp.json().get("data") or {}).get("klines", [])
            if len(klines) >= 2:
                monday_open = float(klines[-5].split(",")[1]) if len(klines) >= 5 else float(klines[0].split(",")[1])
                latest_close = float(klines[-1].split(",")[2])
                week_pct = round((latest_close - monday_open) / monday_open * 100, 2)
                week_indices[name] = week_pct
        result["week_changes"] = week_indices
    except Exception as e:
        print(f"[WARN] week changes failed: {e}", file=sys.stderr)

    # 原油 — 新浪财经接口
    try:
        resp = requests.get(
            "https://hq.sinajs.cn/list=hf_CL",
            headers={"User-Agent": UA, "Referer": "https://finance.sina.com.cn/"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        line = resp.text.strip()
        if "=" in line:
            parts = line.split('"')[1].split(",")
            if len(parts) >= 4:
                price = float(parts[0])
                prev_close = float(parts[7]) if len(parts) > 7 else price
                pct = round((price - prev_close) / prev_close * 100, 2) if prev_close else 0
                result["forex_commodities"].append({
                    "name": "WTI原油",
                    "price": price,
                    "change_pct": pct,
                })
    except Exception as e:
        print(f"[WARN] forex failed: {e}", file=sys.stderr)

    return result


# ─── 情绪层 ────────────────────────────────────────────────

def fetch_xueqiu() -> list[dict[str, str]]:
    """雪球热帖"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    r1 = session.get("https://xueqiu.com/hq", timeout=TIMEOUT)
    r1.raise_for_status()

    resp = session.get(
        "https://stock.xueqiu.com/v5/stock/hot_stock/list.json",
        params={"size": "20", "_type": "10", "type": "10"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("items", []):
        if k.get("ad"):
            continue
        pct = k.get("percent", 0)
        sign = "+" if pct > 0 else ""
        items.append({
            "title": f"{k.get('name', '')} ({sign}{pct}%)",
            "url": f"https://xueqiu.com/s/{k.get('code', '')}",
            "source": "雪球",
        })
    return items[:20]


# ─── 汇总 ────────────────────────────────────────────────

NEWS_SOURCES = {
    "people": fetch_people_politics,
    "thepaper": fetch_thepaper,
    "cls": fetch_cls,
    "eastmoney": fetch_eastmoney,
    "wallstreetcn": fetch_wallstreetcn,
    "xueqiu": fetch_xueqiu,
}


def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    result = {}
    for name, fn in NEWS_SOURCES.items():
        try:
            result[name] = fn()
        except Exception as e:
            print(f"[WARN] {name} failed: {e}", file=sys.stderr)
            result[name] = []
    return result


def fetch_all_market_data() -> dict[str, Any]:
    try:
        data = fetch_market_data()
        sector_data = fetch_eastmoney_hotstock()
        data["sector_flow"] = sector_data
        return data
    except Exception as e:
        print(f"[WARN] market data failed: {e}", file=sys.stderr)
        return {}


if __name__ == "__main__":
    print("=== 新闻源测试 ===")
    news = fetch_all_news()
    total = sum(len(v) for v in news.values())
    for src, items in news.items():
        print(f"  {src}: {len(items)} 条")
    print(f"  Total: {total}")

    print("\n=== 市场数据测试 ===")
    mdata = fetch_all_market_data()
    print(f"  指数: {len(mdata.get('indices', []))} 个")
    print(f"  北向资金: {mdata.get('northbound')}")
    print(f"  涨幅TOP5: {len(mdata.get('top_sectors', []))}")
    print(f"  跌幅TOP5: {len(mdata.get('bottom_sectors', []))}")
    print(f"  板块资金: {len(mdata.get('sector_flow', []))}")
    print(f"  汇率商品: {len(mdata.get('forex_commodities', []))}")
