# -*- coding: utf-8 -*-
"""지금 이슈 — 내 PC에서 돌리는 실시간 서버 (속보 피드 1분, 나머지 3분 간격).

  python server.py            → http://localhost:8787
  python server.py --open     → 실행하면서 브라우저도 열기
  python server.py --lan      → 같은 와이파이의 휴대폰에서도 접속 허용
  python server.py --stop     → 켜져 있는 서버 끄기 (창 없이 백그라운드로 돌 때)
  python server.py --no-nudge → 클라우드판 수집 실행을 대신 걸어 주지 않기

pythonw 로 실행하면 창 없이 돌고, 기록은 data/server.log 에 남는다.
화면(web/)은 클라우드판과 똑같다 — 순위 데이터(data/issues.json, data/i/<이슈>.json)를
이 서버는 그때그때 만들어 주고, 클라우드판은 build.py 가 파일로 미리 만들어 둔다.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import feeds                                   # noqa: E402
from engine import Engine                      # noqa: E402
from sources import SOURCES                    # noqa: E402

WEB = os.path.join(HERE, "web")
DATA = os.path.join(HERE, "data")
STATE_FILE = os.path.join(DATA, "state.json")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8")}
ENGINE = Engine()
MORE_CACHE = {}                                # 이슈 이름 → (시각, 추가 기사)
HTTPD = None
QUIET = False                                  # 창 없이 돌 때는 일상적인 수집 기록을 남기지 않는다
# 주소창에 localhost 나 IP로 들어온 요청만 받는다 (다른 사이트가 이름을 속여 이 서버를 부르는 것 방지)
_HOST_OK = re.compile(r"^(localhost|\d{1,3}(\.\d{1,3}){3}|\[[0-9a-fA-F:]+\])(:\d+)?$")
_ISSUE_PATH = re.compile(r"^/data/i/(c[0-9a-f]{4,16})\.json$")


def log(*a, routine=False):
    if routine and QUIET:
        return
    print(time.strftime("%m-%d %H:%M:%S"), *a, flush=True)


# ── 수집 ──────────────────────────────────────────────────
def collect_due(pool):
    """확인할 때가 된 소스를 받아 엔진에 넣는다. 새 기사 수를 돌려준다."""
    now = time.time()
    due = [s for s in SOURCES if s.tier != "google" and now >= s.next_at]
    g = next((s for s in SOURCES if s.tier == "google" and now >= s.next_at), None)
    if g:
        due.append(g)                          # 구글은 한 번에 하나씩만
    if not due:
        return 0
    items = []
    for arts, trends in pool.map(feeds.fetch_safe, due):
        items.extend(arts)
        if trends is not None:
            ENGINE.set_trends(trends)
    return ENGINE.ingest(items)


def save_state():
    try:
        os.makedirs(DATA, exist_ok=True)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ENGINE.dump_state(), f, ensure_ascii=False)
        os.replace(tmp, STATE_FILE)
    except OSError as e:
        log("저장 실패:", e)


def load_state():
    for name in ("state.json", "articles.json"):       # articles.json 은 예전 형식
        try:
            with open(os.path.join(DATA, name), encoding="utf-8") as f:
                n = ENGINE.restore(json.load(f))
            ENGINE.recompute()
            return log(f"지난 실행에서 기사 {n}건 복원")
        except (OSError, ValueError):
            continue


def collector():
    pool = ThreadPoolExecutor(10)
    last_save = time.time()
    while True:
        try:
            n = collect_due(pool)
            if n or time.time() - ENGINE.updated > 40:
                ENGINE.recompute()
            if n:
                log(f"새 기사 {n}건 · 전체 {len(ENGINE.arts)}건 · 이슈 {len(ENGINE.ranked)}개",
                    routine=True)
            if time.time() - last_save > 300:
                save_state()
                last_save = time.time()
        except Exception as e:
            log("수집 오류:", repr(e))
        time.sleep(5)


# ── 클라우드판 깨우기 ─────────────────────────────────────
# GitHub 의 일정 실행은 늦거나 빠질 수 있다. 이 PC가 켜져 있는 동안은 여기서 간격을 지켜 준다:
# 마지막 수집 실행이 NUDGE_EVERY 초보다 오래됐으면 GitHub CLI(gh)로 실행을 건다.
# GitHub 일정이 제때 돌았으면 그 실행이 최근이므로 아무것도 하지 않는다.
NUDGE_EVERY = 300
WORKFLOW = "collect.yml"


def find_gh():
    return shutil.which("gh") or next(
        (p for p in (r"C:\Program Files\GitHub CLI\gh.exe",) if os.path.exists(p)), None)


def repo_slug():
    """.git/config 의 origin 주소에서 '계정/저장소'를 읽는다 (없으면 None)."""
    try:
        with open(os.path.join(HERE, ".git", "config"), encoding="utf-8") as f:
            m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?\s*$", f.read(), re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def run_gh(gh, args):
    r = subprocess.run([gh] + args, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=40, stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip()[:160])
    return r.stdout


def nudger(gh, slug):
    last_err, told = "", False
    while True:
        wait = 120
        try:
            runs = json.loads(run_gh(gh, ["run", "list", "-R", slug, "--workflow", WORKFLOW,
                                          "--limit", "1", "--json", "createdAt,status"]) or "[]")
            busy = bool(runs) and runs[0]["status"] != "completed"
            age = (time.time() - datetime.fromisoformat(
                runs[0]["createdAt"].replace("Z", "+00:00")).timestamp()) if runs else 1e9
            if busy:
                wait = 30                      # 지금 도는 실행이 끝나기를 기다린다
            elif age >= NUDGE_EVERY - 10:
                run_gh(gh, ["workflow", "run", WORKFLOW, "-R", slug])
                log("클라우드판 수집 실행을 걸었습니다", routine=told)
                told = True
                wait = NUDGE_EVERY
            else:
                wait = max(20, NUDGE_EVERY - age)
            last_err = ""
        except Exception as e:
            msg = str(e)[:160]
            if msg != last_err:                # 같은 오류를 계속 적지 않는다
                log("클라우드판 실행 걸기 실패:", msg)
                last_err = msg
        time.sleep(wait)


# ── 화면에 줄 데이터 ──────────────────────────────────────
def issues_payload():
    d = ENGINE.export()
    d["sources"] = {"ok": sum(1 for s in SOURCES if s.last_ok and not s.fails),
                    "total": len(SOURCES)}
    d["live"] = True                           # 이 서버가 있어야 되는 기능(추가 검색)을 화면에 알림
    d["every"] = "속보 피드는 1분, 나머지는 3분마다 확인"
    return d


def detail_payload(cid):
    d = ENGINE.detail(cid)
    return {k: v for k, v in d.items() if not k.startswith("_")} if d else None


def more_payload(cid, label):
    """직접 수집하지 않는 언론사 보도를 구글 뉴스 검색으로 보탠다."""
    d = ENGINE.detail(cid)
    label = (label or "")[:40]
    if d is None or not label:
        return {"more": []}
    hit = MORE_CACHE.get(label)
    if hit and time.time() - hit[0] < 300:
        extra = hit[1]
    else:
        try:
            extra = feeds.google_search(label)
        except Exception as e:
            log("추가 검색 실패:", repr(e)[:100])
            extra = []
        MORE_CACHE[label] = (time.time(), extra)
        if len(MORE_CACHE) > 200:
            for k in sorted(MORE_CACHE, key=lambda k: MORE_CACHE[k][0])[:100]:
                del MORE_CACHE[k]
    seen, out = set(d["_titles"]), []
    for a in sorted(extra, key=lambda a: -a["ts"]):
        norm = "".join(ch for ch in a["title"] if ch.isalnum()).lower()
        if norm in seen:
            continue
        seen.add(norm)
        out.append({"title": a["title"], "url": a["url"], "outlet": a["outlet"],
                    "ts": int(a["ts"]), "also": [], "lt": {}})
    return {"more": out[:20]}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _trusted(self):
        if _HOST_OK.match(self.headers.get("Host", "")):
            return True
        self._send(403, {"error": "forbidden host"})
        return False

    def do_GET(self):
        if not self._trusted():
            return
        u = urlparse(self.path)
        q = parse_qs(u.query)
        issue = _ISSUE_PATH.match(u.path)
        if u.path in STATIC:
            name, ctype = STATIC[u.path]
            try:
                with open(os.path.join(WEB, name), "rb") as f:
                    self._send(200, f.read(), ctype)
            except OSError:
                self._send(404, {"error": name + " 이 없습니다"})
        elif u.path == "/data/issues.json":
            self._send(200, issues_payload())
        elif issue:
            d = detail_payload(issue.group(1))
            self._send(200 if d else 404, d or {"error": "사라진 이슈입니다"})
        elif u.path == "/api/more":
            self._send(200, more_payload(q.get("id", [""])[0], q.get("q", [""])[0]))
        elif u.path == "/api/status":
            self._send(200, [{"name": s.name, "tier": s.tier, "items": s.items, "fails": s.fails,
                              "error": s.last_err, "last_ok": s.last_ok} for s in SOURCES])
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._trusted():
            return
        self.rfile.read(min(int(self.headers.get("Content-Length", "0") or 0), 20000))
        # JSON 으로 보낸 요청만 받는다 — 다른 웹페이지가 몰래 보내는 단순 요청은 이 형식을 못 쓴다
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self._send(415, {"error": "json only"})
        if urlparse(self.path).path != "/api/shutdown":
            return self._send(404, {"error": "not found"})
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            return self._send(403, {"error": "이 PC에서만 끌 수 있습니다"})
        self._send(200, {"ok": True})
        threading.Thread(target=HTTPD.shutdown, daemon=True).start()


class Server(ThreadingHTTPServer):
    allow_reuse_address = False                # 윈도우에서 같은 포트에 두 번 뜨는 일 방지
    daemon_threads = True


def running(port):
    """이 포트에서 지금 이슈가 이미 응답하는지."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=2) as r:
            return r.status == 200
    except (OSError, ValueError):
        return False


def main():
    global HTTPD, QUIET
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--lan", action="store_true")
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--no-nudge", action="store_true")
    args = ap.parse_args()
    if sys.stdout is None:                     # pythonw: 창이 없으니 기록은 파일로
        os.makedirs(DATA, exist_ok=True)
        path = os.path.join(DATA, "server.log")
        if os.path.exists(path) and os.path.getsize(path) > 500_000:
            os.replace(path, path + ".old")
        sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)
        QUIET = True
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    url = f"http://localhost:{args.port}"
    if args.stop:
        if not running(args.port):
            return print("지금 이슈가 켜져 있지 않습니다.")
        req = urllib.request.Request(f"http://127.0.0.1:{args.port}/api/shutdown", data=b"{}",
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
        return print("지금 이슈를 껐습니다.")
    if running(args.port):                     # 이미 백그라운드로 켜져 있으면 페이지만 연다
        print(f"지금 이슈가 이미 켜져 있습니다 → {url}")
        if args.open:
            webbrowser.open(url)
        return
    host = "0.0.0.0" if args.lan else "127.0.0.1"
    HTTPD = Server((host, args.port), Handler)
    load_state()
    threading.Thread(target=collector, daemon=True).start()
    log(f"지금 이슈 실행 중 → {url}" + ("" if QUIET else "  (끄려면 이 창에서 Ctrl+C)"))
    gh, slug = find_gh(), repo_slug()
    if args.no_nudge:
        pass
    elif gh and slug:
        threading.Thread(target=nudger, args=(gh, slug), daemon=True).start()
        log(f"클라우드판({slug}) 수집을 {NUDGE_EVERY // 60}분 간격으로 지켜 줍니다")
    else:
        log("클라우드판 깨우기 꺼짐: " + ("GitHub CLI(gh)를 찾지 못함" if not gh else "GitHub 저장소가 아님"))
    if args.open:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    try:
        HTTPD.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        save_state()
        log("지금 이슈 종료")


if __name__ == "__main__":
    main()
