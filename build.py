# -*- coding: utf-8 -*-
"""지금 이슈 — 한 번 수집해 정적 사이트로 내보낸다 (클라우드판: GitHub Actions 가 주기적으로 실행).

  python build.py --out _site --state https://<계정>.github.io/<저장소>/state.json.gz
  python build.py --print 20                  → 수집만 하고 순위를 콘솔에 출력(점검용)

서버가 계속 떠 있지 않으므로, 직전 실행이 남긴 state.json.gz 를 받아 이어서 계산한다.
(기사 묶음과 이슈 id, 순위 기록이 이어져야 ▲▼·NEW·'새 기사' 표시가 유지된다.)
"""
import argparse
import gzip
import json
import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import feeds                                   # noqa: E402
from engine import CAT_LABEL, Engine           # noqa: E402
from sources import SOURCES                    # noqa: E402

GOOGLE_EVERY = 540        # 구글 뉴스/트렌드는 요청 제한이 있어 9분에 한 번만


def load_state(src):
    """직전 상태를 읽는다. 없거나(첫 실행) 못 읽으면 빈 상태로 시작."""
    if not src:
        return {}
    try:
        if src.startswith(("http://", "https://")):
            raw = feeds.http_get(src)[0]
        else:
            with open(src, "rb") as f:
                raw = f.read()
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        state = json.loads(raw.decode("utf-8"))
        return state if isinstance(state, dict) else {"articles": state}
    except Exception as e:
        print(f"이전 상태 없음 → 새로 시작 ({type(e).__name__}: {str(e)[:80]})")
        return {}


def collect(eng, state, now):
    """모든 소스를 한 번씩 받는다. 구글 쪽은 차례로, 드물게."""
    warm = bool(state.get("articles"))
    saved = state.get("feeds", {})
    for s in SOURCES:
        s.seen_once = warm
        if warm and s.name in saved:
            s.etag, s.modified = saved[s.name]
    items = []
    with ThreadPoolExecutor(12) as pool:
        for arts, _ in pool.map(feeds.fetch_safe, [s for s in SOURCES if s.tier != "google"]):
            items.extend(arts)
    google_at = state.get("google_at", 0)
    if now - google_at >= GOOGLE_EVERY:
        for s in (s for s in SOURCES if s.tier == "google"):
            arts, trends = feeds.fetch_safe(s)
            items.extend(arts)
            if trends is not None:
                eng.set_trends(trends)
            time.sleep(1.2)
        google_at = now
    return items, google_at


def write_json(path, obj):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def write_site(eng, out, state_extra, every):
    web = os.path.join(HERE, "web")
    os.makedirs(os.path.join(out, "data", "i"), exist_ok=True)
    for name in os.listdir(web):
        shutil.copy2(os.path.join(web, name), os.path.join(out, name))
    data = eng.export()
    tried = [s for s in SOURCES if s.last_ok or s.fails]
    data["sources"] = {"ok": sum(1 for s in tried if not s.fails), "total": len(tried)}
    data["every"] = every
    write_json(os.path.join(out, "data", "issues.json"), data)
    for cid in data["items"]:
        d = eng.detail(cid)
        if d:
            write_json(os.path.join(out, "data", "i", cid + ".json"),
                       {k: v for k, v in d.items() if not k.startswith("_")})
    state = eng.dump_state()
    state.update(state_extra)
    with gzip.open(os.path.join(out, "state.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, separators=(",", ":"))
    open(os.path.join(out, ".nojekyll"), "w").close()
    return len(data["items"])


def print_ranking(eng, n, now):
    for rank, i in enumerate(eng.main_order()[:n], 1):
        flags = " ".join(f for f, on in (("속보", i["breaking"]), ("긴급", i["urgent"]),
                                         ("급상승", i["rising"])) if on)
        print(f"{rank:2d}. [{CAT_LABEL[i['cat']]}] {i['label']} — {i['outlets']}곳/{i['count']}건 "
              f"· {int((now - i['latest']) / 60)}분 전 {flags}\n    {i['headline']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--state", default="")
    ap.add_argument("--print", type=int, default=0, dest="show")
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--every", default="5분마다 갱신 (GitHub 사정에 따라 더 늦어질 수 있음)")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    t0 = now = time.time()
    eng = Engine()
    state = load_state(args.state)
    restored = eng.restore(state, now) if state else 0
    items, google_at = ([], state.get("google_at", 0)) if args.no_fetch else collect(eng, state, now)
    fresh = eng.ingest(items, now)
    eng.recompute(now)
    print(f"이어받은 기사 {restored}건 + 새 기사 {fresh}건 → 이슈 {len(eng.ranked)}개 "
          f"({time.time() - t0:.1f}초)")
    for s in SOURCES:
        if s.fails:
            print(f"  수집 실패: {s.name} — {s.last_err}")
    if args.show:
        print_ranking(eng, args.show, now)
    if args.out:
        extra = {"google_at": google_at,
                 "feeds": {s.name: [s.etag, s.modified] for s in SOURCES if s.etag or s.modified}}
        n = write_site(eng, args.out, extra, args.every)
        print(f"{args.out} 에 이슈 {n}개 내보냄")


if __name__ == "__main__":
    main()
