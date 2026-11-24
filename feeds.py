# -*- coding: utf-8 -*-
"""RSS/Atom 피드를 받아 기사 목록으로 바꾼다. 표준 라이브러리만 사용."""
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from sources import INTERVAL, Source

KST = timezone(timedelta(hours=9))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")
TIMEOUT = 12


class NotModified(Exception):
    pass


def http_get(url, etag="", modified=""):
    """(본문 bytes, etag, last-modified) 를 돌려준다. 바뀐 게 없으면 NotModified."""
    headers = {
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read(), r.headers.get("ETag", ""), r.headers.get("Last-Modified", "")
    except urllib.error.HTTPError as e:
        if e.code == 304:
            raise NotModified() from None
        raise


def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _to_root(raw):
    m = re.match(rb'\s*<\?xml[^>]*encoding=["\']([\w-]+)["\']', raw[:300])
    enc = m.group(1).decode("ascii", "replace").lower() if m else "utf-8"
    try:
        text = raw.decode(enc, errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")
    text = text.lstrip("﻿ \r\n\t")
    text = re.sub(r"^<\?xml[^>]*\?>", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return ET.fromstring(text)


def parse_date(s):
    """여러 언론사의 제각각인 날짜 표기를 epoch 초로. 못 읽으면 None."""
    s = (s or "").strip()
    if not s:
        return None
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        t = s.replace("Z", "+00:00")
        if "T" not in t:
            t = t.replace(" ", "T", 1)
        try:
            dt = datetime.fromisoformat(t)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.timestamp()
        except ValueError:
            pass
    t = re.sub(r",(?=\S)", ", ", s)                      # "Tue,24 Nov" → "Tue, 24 Nov"
    t = re.sub(r"([+-]\d{2}):(\d{2})$", r"\1\2", t)      # "+09:00" → "+0900"
    try:
        dt = parsedate_to_datetime(t)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.timestamp()
    except (TypeError, ValueError, IndexError):
        return None


def _clean(s):
    s = html.unescape(html.unescape(s or ""))
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _fix_ts(ts, now):
    """시간대가 잘못 표기된 피드(한국 시각을 GMT로 적는 곳) 보정."""
    if ts is None:
        return None
    if ts > now + 600:
        ts -= 9 * 3600
        if ts > now + 600:
            return now
    return min(ts, now)


def parse_feed(raw, src, now=None):
    """기사 dict 목록과 (트렌드 피드라면) 급상승 검색어 목록을 돌려준다."""
    now = now or time.time()
    root = _to_root(raw)
    arts, trends = [], []
    idx = 0
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        f, news = {}, []
        for ch in el:
            name = _local(ch.tag)
            if name == "news_item":
                news.append({_local(x.tag): _clean(x.text) for x in ch})
            elif name == "link":
                href = (ch.text or "").strip() or ch.attrib.get("href", "")
                if href and "link" not in f:
                    f["link"] = href
            elif name in ("title", "pubDate", "date", "published", "updated",
                          "source", "approx_traffic"):
                if name not in f:
                    f[name] = (ch.text or "").strip()
        title = _clean(f.get("title"))
        ts = _fix_ts(parse_date(f.get("pubDate") or f.get("date") or
                                f.get("published") or f.get("updated")), now)

        if src.kind == "trends":
            if title:
                trends.append({"keyword": title, "traffic": f.get("approx_traffic", ""),
                               "ts": ts or now})
            for n in news:
                t, u = n.get("news_item_title"), n.get("news_item_url")
                if t and u:
                    arts.append({"title": t, "url": u, "ts": ts or now,
                                 "outlet": n.get("news_item_source") or "기타",
                                 "cat": None, "top": False, "dated": ts is not None})
            continue

        link = f.get("link", "")
        if not title or not link.startswith(("http://", "https://")):
            continue
        outlet = src.outlet
        if src.kind == "gnews":
            outlet = _clean(f.get("source")) or "기타"
            suffix = " - " + outlet
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        dated = ts is not None
        if not dated:
            # 날짜가 없는 피드: 처음 받을 때는 순서대로 과거로 흩고, 이후 새 글은 지금 시각
            ts = now if src.seen_once else now - 5400 - idx * 360
        arts.append({"title": title, "url": link, "ts": ts, "outlet": outlet,
                     "cat": src.cat, "top": src.top, "dated": dated})
        idx += 1
    return arts, trends


def fetch_source(src, now=None):
    """소스 하나를 받아 파싱. (기사목록, 트렌드목록) — 변화 없으면 ([], None)."""
    now = now or time.time()
    try:
        raw, etag, modified = http_get(src.url, src.etag, src.modified)
    except NotModified:
        src.last_ok, src.fails, src.last_err = now, 0, ""
        return [], None
    arts, trends = parse_feed(raw, src, now)
    src.etag, src.modified = etag, modified
    src.last_ok, src.fails, src.last_err = now, 0, ""
    src.seen_once = True
    src.items = len(arts)
    return arts, (trends if src.kind == "trends" else None)


def fetch_safe(src, now=None):
    """fetch_source 와 같지만 실패해도 예외를 내지 않고, 다음 확인 시각을 정해 둔다."""
    now = now or time.time()
    try:
        arts, trends = fetch_source(src, now)
        src.next_at = now + INTERVAL[src.tier]
        return arts, trends
    except Exception as e:                     # 한 곳이 실패해도 나머지는 계속
        src.fails += 1
        src.last_err = f"{type(e).__name__}: {e}"[:120]
        src.next_at = now + min(INTERVAL[src.tier] * 2 ** src.fails, 1800)
        return [], None


def google_search(query, now=None):
    """구글 뉴스 검색 RSS로 관련 기사를 더 찾는다 (최근 하루)."""
    q = urllib.parse.quote(f"{query} when:1d")
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    src = Source("검색", "", None, "google", url, kind="gnews")
    raw, _, _ = http_get(url)
    arts, _ = parse_feed(raw, src, now)
    return arts
