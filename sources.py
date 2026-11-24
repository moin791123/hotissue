# -*- coding: utf-8 -*-
"""수집할 뉴스 소스 목록.

tier
  fast   : 속보성 피드. 60초마다 확인
  normal : 일반 섹션 피드. 180초마다 확인
  google : 구글 뉴스/트렌드. 요청 제한이 있어 10분마다 하나씩 차례로 확인

cat 이 None 이면 기사 제목·주소로 분야를 추정한다.
"""
from dataclasses import dataclass, field

INTERVAL = {"fast": 60, "normal": 180, "google": 600}


@dataclass
class Source:
    name: str
    outlet: str          # 화면에 보일 언론사 이름 ("" 이면 피드 안의 출처를 사용)
    cat: str | None
    tier: str
    url: str
    kind: str = "rss"    # rss | gnews | trends
    top: bool = False    # 구글 뉴스 헤드라인처럼 '주요 뉴스'로 뽑힌 피드
    # 실행 중 상태
    next_at: float = 0.0
    fails: int = 0
    etag: str = ""
    modified: str = ""
    last_ok: float = 0.0
    last_err: str = ""
    seen_once: bool = False
    items: int = 0
    extra: dict = field(default_factory=dict)


def _g(topic):
    return f"https://news.google.com/rss/headlines/section/topic/{topic}?hl=ko&gl=KR&ceid=KR:ko"


SOURCES = [
    # ── 속보성 ──────────────────────────────────────────────
    Source("연합 최신", "연합뉴스", None, "fast", "https://www.yna.co.kr/rss/news.xml"),
    Source("SBS 속보", "SBS", None, "fast", "https://news.sbs.co.kr/news/newsflashRssFeed.do?plink=RSSREADER"),
    Source("뉴시스 속보", "뉴시스", None, "fast", "https://www.newsis.com/RSS/sokbo.xml"),
    Source("매경 헤드라인", "매일경제", None, "fast", "https://www.mk.co.kr/rss/30000001/"),
    Source("연합뉴스TV", "연합뉴스TV", None, "fast", "https://www.yonhapnewstv.co.kr/browse/feed/"),

    # ── 연합뉴스 ────────────────────────────────────────────
    Source("연합 경제", "연합뉴스", "econ", "normal", "https://www.yna.co.kr/rss/economy.xml"),
    Source("연합 사회", "연합뉴스", "society", "normal", "https://www.yna.co.kr/rss/society.xml"),
    Source("연합 국제", "연합뉴스", "world", "normal", "https://www.yna.co.kr/rss/international.xml"),
    Source("연합 정치", "연합뉴스", "politics", "normal", "https://www.yna.co.kr/rss/politics.xml"),
    Source("연합 연예", "연합뉴스", "ent", "normal", "https://www.yna.co.kr/rss/entertainment.xml"),
    Source("연합 스포츠", "연합뉴스", "sports", "normal", "https://www.yna.co.kr/rss/sports.xml"),

    # ── 방송 ────────────────────────────────────────────────
    Source("SBS 경제", "SBS", "econ", "normal", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=02&plink=RSSREADER"),
    Source("SBS 사회", "SBS", "society", "normal", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=03&plink=RSSREADER"),
    Source("SBS 국제", "SBS", "world", "normal", "https://news.sbs.co.kr/news/SectionRssFeed.do?sectionId=07&plink=RSSREADER"),

    # ── 통신·경제지 ─────────────────────────────────────────
    Source("뉴시스 경제", "뉴시스", "econ", "normal", "https://www.newsis.com/RSS/economy.xml"),
    Source("뉴시스 사회", "뉴시스", "society", "normal", "https://www.newsis.com/RSS/society.xml"),
    Source("뉴시스 국제", "뉴시스", "world", "normal", "https://www.newsis.com/RSS/international.xml"),
    Source("뉴시스 정치", "뉴시스", "politics", "normal", "https://www.newsis.com/RSS/politics.xml"),
    Source("매경 경제", "매일경제", "econ", "normal", "https://www.mk.co.kr/rss/30100041/"),
    Source("매경 사회", "매일경제", "society", "normal", "https://www.mk.co.kr/rss/50400012/"),
    Source("매경 국제", "매일경제", "world", "normal", "https://www.mk.co.kr/rss/30300018/"),
    Source("매경 정치", "매일경제", "politics", "normal", "https://www.mk.co.kr/rss/30200030/"),
    Source("머니투데이", "머니투데이", None, "normal", "https://rss.mt.co.kr/mt_news.xml"),
    Source("이데일리", "이데일리", None, "normal", "http://rss.edaily.co.kr/edaily_news.xml"),
    Source("파이낸셜뉴스", "파이낸셜뉴스", None, "normal", "https://www.fnnews.com/rss/r20/fn_realnews_all.xml"),
    Source("아시아경제", "아시아경제", None, "normal", "https://www.asiae.co.kr/rss/all.htm"),
    Source("헤럴드경제", "헤럴드경제", None, "normal", "https://biz.heraldcorp.com/rss/google/newsAll"),

    # ── 종합일간지 ──────────────────────────────────────────
    Source("조선 전체", "조선일보", None, "normal", "https://www.chosun.com/arc/outboundfeeds/rss/?outputType=xml"),
    Source("조선 경제", "조선일보", "econ", "normal", "https://www.chosun.com/arc/outboundfeeds/rss/category/economy/?outputType=xml"),
    Source("조선 사회", "조선일보", "society", "normal", "https://www.chosun.com/arc/outboundfeeds/rss/category/national/?outputType=xml"),
    Source("조선 국제", "조선일보", "world", "normal", "https://www.chosun.com/arc/outboundfeeds/rss/category/international/?outputType=xml"),
    Source("조선 정치", "조선일보", "politics", "normal", "https://www.chosun.com/arc/outboundfeeds/rss/category/politics/?outputType=xml"),
    Source("동아 전체", "동아일보", None, "normal", "https://rss.donga.com/total.xml"),
    Source("동아 경제", "동아일보", "econ", "normal", "https://rss.donga.com/economy.xml"),
    Source("동아 사회", "동아일보", "society", "normal", "https://rss.donga.com/national.xml"),
    Source("동아 국제", "동아일보", "world", "normal", "https://rss.donga.com/international.xml"),
    Source("동아 정치", "동아일보", "politics", "normal", "https://rss.donga.com/politics.xml"),
    Source("한겨레 전체", "한겨레", None, "normal", "https://www.hani.co.kr/rss/"),
    Source("한겨레 사회", "한겨레", "society", "normal", "https://www.hani.co.kr/rss/society/"),
    Source("한겨레 경제", "한겨레", "econ", "normal", "https://www.hani.co.kr/rss/economy/"),
    Source("경향 전체", "경향신문", None, "normal", "https://www.khan.co.kr/rss/rssdata/total_news.xml"),
    Source("경향 사회", "경향신문", "society", "normal", "https://www.khan.co.kr/rss/rssdata/society_news.xml"),
    Source("경향 경제", "경향신문", "econ", "normal", "https://www.khan.co.kr/rss/rssdata/economy_news.xml"),
    Source("노컷뉴스", "노컷뉴스", None, "normal", "https://rss.nocutnews.co.kr/nocutnews.xml"),
    Source("세계일보", "세계일보", None, "normal", "https://www.segye.com/Articles/RSSList/segye_recent.xml"),
    Source("서울신문", "서울신문", None, "normal", "https://www.seoul.co.kr/xml/rss/rss_top.xml"),
    Source("오마이뉴스", "오마이뉴스", None, "normal", "https://rss.ohmynews.com/rss/ohmynews.xml"),

    # ── 구글 뉴스 (주요 뉴스 선정 신호 + 직접 피드가 없는 언론사 보강) ──
    Source("구글 헤드라인", "", None, "google", "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko", kind="gnews", top=True),
    Source("구글 세계", "", "world", "google", _g("WORLD"), kind="gnews", top=True),
    Source("구글 경제", "", "econ", "google", _g("BUSINESS"), kind="gnews", top=True),
    Source("구글 국내", "", None, "google", _g("NATION"), kind="gnews", top=True),
    Source("구글 연예", "", "ent", "google", _g("ENTERTAINMENT"), kind="gnews"),
    Source("구글 트렌드", "", None, "google", "https://trends.google.com/trending/rss?geo=KR", kind="trends"),
]
