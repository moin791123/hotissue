# -*- coding: utf-8 -*-
"""기사 → 이슈 묶기 → 핫 순위 → 관심사 반영.

핵심 생각
  · 같은 사건을 여러 언론사가 짧은 시간 안에 쓰면 그게 핫이슈다.
  · 제목에서 뽑은 낱말로 기사끼리 묶고(희귀한 낱말일수록 가중),
    '최근에 몇 곳이 썼는가'로 점수를 매긴다. 시간이 지나면 점수는 반감한다.
"""
import hashlib
import math
import re
import threading
import time
from collections import Counter, defaultdict, deque

# ── 조정값 ────────────────────────────────────────────────
HALF_LIFE_MIN = 100.0     # 기사 한 건의 '뜨거움'이 절반이 되는 시간(분)
KEEP_HOURS = 36           # 이보다 오래된 기사는 버림
INGEST_HOURS = 24         # 처음 받을 때 이보다 오래된 기사는 무시
JOIN_THR = 0.30           # 기사가 기존 이슈에 붙는 유사도 기준
MERGE_THR = 0.46          # 이슈끼리 합쳐지는 유사도 기준
TOPIC_SHARE = 0.012       # 전체 기사 제목의 이 비율 넘게 오른 이름은 '큰 이슈'의 이름으로 본다
TOPIC_RATIO = 3.0         # 또는 묶음 하나당 기사 수가 이만큼 쏠린 이름
MAIN_SIZE = 20            # 종합 순위에 보여줄 개수

CAT_LABEL = {"society": "사회", "econ": "경제", "world": "국제", "it": "IT·과학",
             "politics": "정치", "ent": "연예", "sports": "스포츠"}
# 사회·경제를 앞세우고, 정치·연예·스포츠는 아주 뜨거운 것만 올라오게 한다
CAT_WEIGHT = {"society": 1.12, "econ": 1.12, "world": 1.05, "it": 0.9,
              "politics": 0.72, "ent": 0.6, "sports": 0.45}
CAT_CAP = {"politics": 2, "ent": 2, "sports": 1}

# ── 제목 다듬기 ───────────────────────────────────────────
COUNTRY = {"美": "미국", "中": "중국", "日": "일본", "韓": "한국", "北": "북한",
           "英": "영국", "獨": "독일", "佛": "프랑스", "露": "러시아", "印": "인도",
           "臺": "대만", "台": "대만", "伊": "이탈리아", "濠": "호주"}
_COUNTRY_RE = re.compile("[" + "".join(COUNTRY) + "]")
_TAG = re.compile(r"[\[\(<【〈]([^\]\)>】〉]{1,16})[\]\)>】〉]")
_LEAD_TAGS = re.compile(r"^\s*(?:[\[<【〈][^\]>】〉]{1,16}[\]>】〉]\s*)+")
_LEAD_PAREN = re.compile(r"^\s*\((?:속보|단독|종합|\d보|긴급|상보)\)\s*")
_TRAIL_TAGS = re.compile(
    r"(?:\s*[\[\(](?:종합\d?보?|상보|\d보|영상|포토|현장|르포|전문|속보|단독)[\]\)])+\s*$")
_SKIP_TAG = re.compile(
    r"포토|부고|인사|게시판|운세|사설|칼럼|^표$|그래픽|신간|알림|동정|화보|만평|기고|광고|"
    r"사진|모집|오피니언|시론|기자수첩|데스크|주간|일정|브리핑|방송소식|신상품|이벤트|AD")
_SKIP_TITLE = re.compile(r"다시보기|오늘의 운세|뉴스룸 모아보기|헤드라인$|^\s*\d+월 \d+일 ")
_BREAK_TAG = re.compile(r"속보|^[12]보$|긴급")     # '종합2보' 같은 정리 기사는 속보로 치지 않는다
_WORD = re.compile(r"[가-힣A-Za-z0-9一-鿿]+")
_HANJA = re.compile(r"[一-鿿]")

STOP = set("""
관련 대해 대한 위해 위한 통해 따라 오늘 내일 어제 올해 내년 작년 지난 이번 다음 최근 현재 당시 앞서
종합 속보 단독 포토 영상 인터뷰 사설 칼럼 기자 뉴스 특징주 무슨 어떻게 결국 다시 이제 아직 벌써 모두
가장 매우 정말 진짜 바로 계속 역시 또한 그리고 하지만 그러나 때문 가운데 사이 이후 이전 동안 까지
것으로 이라고 라고 이라며 라며 한다 했다 된다 됐다 있다 없다 한다고 했다고 밝혀 말해 나서 나선 나섰
있는 없는 하는 되는 같은 다른 어떤 모든 여러 각종 일부 전체 처음 마지막 최대 최고 최초 최악 역대
이유 상황 문제 결과 내용 입장 방침 계획 예정 전망 우려 논란 의혹 주장 발표 공개 확인 추진 검토 요구
에서 으로 에게 보다 부터 처럼 이런 저런 그런 이것 저것 그것 우리 그는 그가 이들 누구 무엇 어디 언제
한국 국내 정부 당국 업계 시장 세계 글로벌 사람 사람들 시민 국민 뉴스1 연합뉴스 뉴시스
향해 묻자 털어놔 도운 받아 받은 나온 나와 보니 끊고 놓고 두고 맞아 앞두고 이어 넘어 넘게 몰려
올라 내려 떨어져 꺼내자 않겠단 못하나 안해 아니다 그렇다 알고보니 했더니 됐나 되나 하나 이달 내달
다음달 이날 전날 오전 오후 새벽 밤새 하루 만에 만의 직전 직후 이상 이하 미만 가량 정도 수준 규모
the and for with from that this will has have are was not live score
""".split())
# 안보·재난 낱말 — 이런 이슈는 분야와 상관없이 앞세운다
URGENT = set("""
전쟁 공습 침공 교전 포격 폭격 미사일 도발 계엄 계엄령 테러 피격 핵실험 경계경보 공습경보
격추 기뢰 영공 군용기 선전포고 인질 쿠데타 지진 쓰나미 해일 산불 침몰 탈선 방사능 대지진
""".split())                       # '추락·폭발·붕괴'처럼 비유로도 흔히 쓰는 말은 일부러 뺐다
EDGE_STOP = set("등 및 또 더 첫 것 수 중 전 후 왜 속 위 뒤 앞 때 곳 채 듯 뿐 안 못 새 총 약 단 그 이 저 한 두 세 네".split())

_VERB_END = re.compile(
    r"(하겠다|했지만|하지만|합니다|했다가|했는데|한다는|했다는|한다며|했다며|"
    r"했다|한다|하는|하고|하며|하면|해서|해야|하자|하라|했던|하기|하게|하지|하니|하다|"
    r"됐다|된다|되는|되고|되며|되면|돼야|되나|"
    r"시킨|시켜|시키는|스러운|스럽다)$")
_VERBISH = re.compile(
    r"(었다|았다|였다|겠다|는다|ㄴ다|렸다|린다|졌다|진다|났다|섰다|왔다|갔다|냈다|낸다|"
    r"줬다|준다|봤다|본다|랐다|렀다|뒀다|쳤다|친다|혔다|힌다|겼다|긴다|웠다|운다|"
    r"습니다|입니다|세요|어요|아요|네요|군요|나요|까요|"
    r"으며|면서|지만|는데|더니|도록|려고|려는|다는|라는|자는|냐는|다고|라고|자고|냐고)$")

PARTICLES = sorted("""
에서는 으로는 에게서 이라고 이라며 라면서 에서도 으로도 에게도 이라는 으로써 으로서
으로 에서 에게 한테 까지 부터 처럼 보다 이라 라고 라며 이다 에는 에도 와의 과의 로의 에의
이나 이란 이든 마다 조차 마저 밖에 로서 로써 께서 이며
은 는 이 가 을 를 의 에 로 와 과 도 만 서 께 엔 며
""".split(), key=len, reverse=True)
# 조사처럼 끝나지만 통째로 명사인 말 — 끝 글자를 떼지 않는다
_NOUN_TAIL = re.compile(
    r"(도로|보도|제도|속도|온도|지도|정도|의도|시도|반도|수도|태도|구도|한도|연도|년도|강도|"
    r"난이도|고도|습도|농도|밀도|빈도|각도|진도|인도|경기도|강원도|제주도|독도|울릉도|대마도|"
    r"완도|거제도|영종도|여의도|송도|연평도|백령도|"
    r"경로|진로|통로|선로|피로|원로|근로|항로|회로|기로|판로|대로|활로|"
    r"아이|사이|차이|나이|종이|놀이|높이|깊이|길이|고양이|호랑이|원숭이|어린이|젊은이|"
    r"평가|국가|물가|주가|유가|시가|원가|단가|분양가|최고가|최저가|공시가|매매가|전세가|호가|"
    r"작가|화가|전문가|투자가|휴가|추가|증가|허가|인가|참가|대가|"
    r"효과|결과|성과|사과|학과|통과|초과|경과|부과|전과|외과|내과|치과|안과|"
    r"문의|회의|논의|합의|동의|결의|정의|주의|상의|협의|심의|토의|항의|건의|발의|제의|"
    r"예의|고의|강의|창의|호의|악의|유의|임의|편의|불의|"
    r"경찰서|소방서|세무서|보고서|계약서|진술서|유서|비서|도서|문서|부서|질서|순서|증서|각서|"
    r"대만|불만|비만|자만|"
    r"한은|금은|수은|"
    r"사랑|자랑|명랑|이란|소란|요란|혼란|논란|반란|내란|계란|"
    r"기와|의와|"
    r"우에|상에)$")

CAT_URL = [
    ("econ", re.compile(r"/(economy|economic|money|stock|realestate|finance|biz|industry|market)", re.I)),
    ("society", re.compile(r"/(society|national|local|area)", re.I)),
    ("world", re.compile(r"/(international|world|global|inter)\b", re.I)),
    ("politics", re.compile(r"/(politics|politic)", re.I)),
    ("ent", re.compile(r"/(entertain|enter|star|celeb|culture/broadcast)", re.I)),
    ("sports", re.compile(r"/sports?", re.I)),
    ("it", re.compile(r"/(it|tech|science|digital)\b", re.I)),
]
CAT_WORDS = {
    "world": "미국 트럼프 중국 일본 러시아 우크라 우크라이나 이란 이스라엘 가자 하마스 전쟁 공습 휴전 "
             "나토 유엔 시진핑 푸틴 백악관 대만 북한 김정은 미사일 침공 폭격 교전 유럽 중동 영국 "
             "프랑스 독일 인도 다카이치 젤렌스키 네타냐후 후티 예멘 레바논 헤즈볼라 관세 외신 "
             "국방부 펜타곤 정상회담 테러 쿠데타 계엄령",
    "econ": "코스피 코스닥 증시 주가 환율 금리 한은 한국은행 부동산 아파트 분양 청약 수출 반도체 "
            "삼성전자 하이닉스 물가 유가 금융 은행 대출 실적 영업이익 매출 투자 비트코인 가상자산 "
            "엔비디아 주식 채권 연준 Fed 기준금리 전세 집값 공매도 상장 IPO 인수 합병 적자 흑자 "
            "소비자 최저임금 세금 증세 감세 국세청 공정위 금감원 금융위 기재부 원화 달러 무역",
    "society": "경찰 검찰 법원 재판 구속 사고 화재 사망 숨져 숨진 실종 폭행 살인 수능 학교 교사 "
               "학생 병원 의대 날씨 폭설 태풍 지진 호우 한파 폭염 파업 노조 징역 선고 기소 체포 "
               "피의자 피해자 범행 추락 붕괴 침수 산불 구조 응급 감염 식중독 교통사고 음주운전 "
               "마약 사기 보이스피싱 유출 해킹 리트 로스쿨 입시 대학 교육부 복지부 전세사기",
    "politics": "대통령 국회 민주당 국민의힘 여당 야당 총리 장관 의원 탄핵 대선 총선 지방선거 특검 "
                "국무회의 대통령실 청와대 원내대표 당대표 공천 여야 국정감사 청문회 개헌 법안 본회의 "
                "與 野 李 尹 조국혁신당 개혁신당 후보 선거 지지율 여론조사",
    "ent": "배우 가수 아이돌 드라마 영화 예능 컴백 열애 결혼 이혼 방송 콘서트 넷플릭스 BTS "
           "블랙핑크 뉴진스 소속사 앨범 음원 시청률 주연 출연 팬미팅 데뷔 유튜버 MC 개그맨 "
           "연예인 톱스타 박스오피스 결별 커플 교제 재혼 걸그룹 보이그룹 뮤지컬 하차 캐스팅 "
           "신곡 음반 팬덤 스타 래퍼 트로트 오디션 아나운서 방송인 근황 임신 득남 득녀",
    "sports": "축구 야구 농구 배구 골프 감독 선수 리그 월드컵 올림픽 손흥민 KBO MLB EPL 우승 "
              "결승 득점 홈런 이적 프로야구 프로축구 국가대표 패배 연승 연패 타자 투수 "
              "토트넘 이강인 김민재 오타니 챔피언스리그 PGA LPGA 테니스 UFC",
    "it": "AI 인공지능 챗GPT 오픈AI 구글 애플 아이폰 갤럭시 카카오 네이버 통신사 SKT KT "
          "클라우드 데이터센터 로봇 우주 누리호 위성 양자 플랫폼 메타 테슬라 자율주행",
}
_CAT_LOOKUP = {}
for _c, _ws in CAT_WORDS.items():
    for _w in _ws.split():
        _CAT_LOOKUP[_w.lower()] = _c
# 어느 날이나 흔한 말 — 이런 말 하나로 이슈를 한데 모으지 않고, 관심사로도 배우지 않는다
BLAND = set("""
서울 부산 대구 인천 광주 대전 울산 세종 경기 강원 충북 충남 전북 전남 경북 경남 제주 수도권 지방
삼성 현대 기업 회사 대표 회장 사장 직원 교수 박사 전문가 관계자 대통령실 위원회 위원장 협회
가격 인상 인하 상승 하락 급등 급락 확대 축소 강화 완화 지원 개최 선정 도입 시행 발생 조사 수사
이사회 복귀 추가 사건 사태 대책 방안 개선 협력 협약 체결 출시 공급 생산 판매 서비스 사업 산업
송치 혐의 연속 수상 제한 논의 확보 대상 예산 지분 시험 여성 남성 인사 지역 개발 기술 인재 불법
지정 결정 중단 보상 차단 피해 성과 대응 점검 신규 진입 가동 반발 미래 회복 제재 승진 임원 후보자
후보 신청 기소 선고 징역 구속영장 불구속 매수 매도 발언 유감 CEO ceo 없어 없이 국힘 민주 의장
청문회 간담회 기자회견 브리핑 회담 회동 방문 참석 출범 취임 사퇴 사임 해임 임명 지명 내정 영입
경찰 검찰 법원 재판 구속 사고 사망 숨져 숨진 대통령 국회 의원 장관 총리 여당 야당 여야 與 野
학교 학생 병원 감독 선수 배우 가수 방송 출연
""".split())
GENERIC = set(_CAT_LOOKUP) | STOP | BLAND
# 앞말에 붙여 한 낱말로 보지 않을 한 글자 말 (젠슨 황 → 젠슨황 은 붙이되, 삼성 측 → 삼성측 은 안 붙임)
_NO_COMPOUND = set("씨 측 군 양 명 건 원 내 외 간 쪽 선 대 급 발 차 권 형 식 적 성 화 력 감 율 률 비 료 "
                   "가 을 를 은 는 에 의 도 만 과 와 로 서 말 날 달 해 년 월 일 시 분 초 번 개 곳 편".split())
_HANGUL = re.compile(r"[가-힣]")


def pretty(word):
    """소문자로 바꿔 둔 영문 낱말을 보기 좋게."""
    if word.isascii():
        return word.upper() if len(word) <= 4 else word.capitalize()
    return word


# 받침 뒤에만 붙는 조사 / 받침 없는 말 뒤에만 붙는 조사 — 맞지 않으면 조사가 아니라 낱말의 일부다
_AFTER_BATCHIM = {"이", "은", "을", "과", "으로", "이라고", "이라며", "이라는", "이나", "이란",
                  "이든", "이며", "이다", "이라", "으로는", "으로도", "으로써", "으로서"}
_AFTER_VOWEL = {"가", "는", "를", "와", "라고", "라며", "라면서", "며", "로서", "로써"}


def _batchim(ch):
    """한글 글자의 받침 번호(없으면 0, ㄹ이면 8)."""
    return (ord(ch) - 0xAC00) % 28 if "가" <= ch <= "힣" else -1


def strip_particle(w):
    """낱말 끝의 어미·조사를 떼어 기본꼴에 가깝게."""
    if not w or not ("가" <= w[-1] <= "힣"):
        return w.lower()
    m = _VERB_END.search(w)
    if m and m.start() >= 2:
        return w[: m.start()]
    if _NOUN_TAIL.search(w):
        return w
    for p in PARTICLES:
        if w.endswith(p) and len(w) - len(p) >= 2:
            b = _batchim(w[-len(p) - 1])
            if b < 0:
                continue
            if p in _AFTER_BATCHIM and b == 0:
                continue
            if p in _AFTER_VOWEL and b != 0:
                continue
            if p in ("로", "로의") and b not in (0, 8):
                continue
            return w[: -len(p)]
    return w


def is_token(w):
    if w in STOP:
        return False
    if len(w) == 1:
        return bool(_HANJA.match(w))
    if w[0].isdigit():
        return False
    if _VERBISH.search(w) or _VERB_END.search(w):
        return False
    return True


def split_words(title):
    s = _COUNTRY_RE.sub(lambda m: " " + COUNTRY[m.group()] + " ", title)
    s = re.sub(r"([一-鿿])(?=[가-힣A-Za-z])", r"\1 ", s)
    s = re.sub(r"([가-힣])(?=[一-鿿])", r"\1 ", s)
    return [strip_particle(w) for w in _WORD.findall(s)]


def analyze_title(raw):
    """제목 → (보여줄 제목, 속보?, 단독?, 건너뛸 글?)"""
    tags = _TAG.findall(raw)
    skip = any(_SKIP_TAG.search(t) for t in tags) or bool(_SKIP_TITLE.search(raw))
    breaking = any(_BREAK_TAG.search(t.strip()) for t in tags) or bool(re.match(r"\s*속보[\s:·]", raw))
    exclusive = any("단독" in t for t in tags)
    shown = _LEAD_TAGS.sub("", raw)
    shown = _LEAD_PAREN.sub("", shown)
    shown = _TRAIL_TAGS.sub("", shown)
    shown = re.sub(r"^\s*속보[\s:·]+", "", shown).strip(" -|·")
    return shown or raw, breaking, exclusive, skip


def infer_cat(title_words, url):
    for cat, rx in CAT_URL:
        if rx.search(url):
            return cat
    votes = Counter()
    for w in title_words:
        c = _CAT_LOOKUP.get(w.lower())
        if c:
            votes[c] += 1
    return votes.most_common(1)[0][0] if votes else "society"


class Article:
    __slots__ = ("id", "url", "raw", "title", "outlet", "okey", "ts", "cat", "catw",
                 "breaking", "exclusive", "top", "tokens", "words", "cid", "tnorm")


class Cluster:
    __slots__ = ("id", "aids", "tok", "core", "norm", "dirty")

    def __init__(self, cid):
        self.id = cid
        self.aids = []
        self.tok = Counter()
        self.core = {}
        self.norm = 1.0
        self.dirty = True


class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.arts = {}                    # id → Article
        self.by_url = {}
        self.by_title = {}                # (언론사, 제목) → id
        self.df = Counter()               # 낱말이 나온 기사 수
        self.clusters = {}
        self.tok2c = defaultdict(set)     # 낱말 → 이슈 id들
        self.alias = {}                   # 합쳐진 이슈의 옛 id → 새 id
        self.trends = []
        self.trends_src = []
        self.flash = []
        self.ranked = []
        self.hist = deque(maxlen=40)      # (시각, {이슈 id: 순위})
        self.version = 0
        self.updated = 0.0

    # ── 낱말 가중치 ───────────────────────────────────────
    def idf(self, t):
        return math.log((len(self.arts) + 20.0) / (self.df.get(t, 0) + 1.0))

    # ── 기사 받기 ─────────────────────────────────────────
    def ingest(self, items, now=None):
        now = now or time.time()
        with self.lock:
            fresh = []
            for it in items:
                a = self._make(it, now)
                if a is not None:
                    fresh.append(a)
            for a in fresh:
                for t in a.tokens:
                    self.df[t] += 1
            fresh.sort(key=lambda x: x.ts)
            for a in fresh:
                self._assign(a)
            return len(fresh)

    def _make(self, it, now):
        url, raw = it["url"], it["title"]
        if now - it["ts"] > INGEST_HOURS * 3600:
            return None
        old = self.by_url.get(url)
        outlet = it.get("outlet") or "기타"
        okey = outlet.replace(" 뉴스", "").replace(" ", "").lower()
        tnorm = "".join(_WORD.findall(raw)).lower()
        if old is None:
            old = self.by_title.get((okey, tnorm))
        if old is not None:
            a = self.arts.get(old)
            if a is not None:
                if it.get("cat") and a.catw < 2:
                    a.cat, a.catw = it["cat"], 2
                if it.get("top"):
                    a.top = True
            return None
        shown, breaking, exclusive, skip = analyze_title(raw)
        if skip or len(shown) < 8 or len(_HANGUL.findall(shown)) < 4:
            return None
        words = split_words(shown)
        toks = [w for w in words if is_token(w)]
        if len(toks) < 2:
            return None
        # '젠슨 황'과 '젠슨황'처럼 띄어쓰기만 다른 이름이 같은 낱말로 잡히도록
        for x, y in zip(words, words[1:]):
            if (len(y) == 1 and "가" <= y <= "힣" and y not in EDGE_STOP
                    and y not in _NO_COMPOUND and not x.isascii() and is_token(x)):
                toks.append(x + y)
        tokens = frozenset(toks)
        a = Article()
        a.id = hashlib.sha1(url.encode("utf-8", "replace")).hexdigest()[:10]
        if a.id in self.arts:
            return None
        a.url, a.raw, a.title, a.outlet, a.okey = url, raw, shown, outlet, okey
        a.ts = it["ts"]
        if it.get("cat"):
            a.cat, a.catw = it["cat"], 2
        else:
            a.cat, a.catw = infer_cat(words, url), 1
        a.breaking, a.exclusive, a.top = breaking, exclusive, bool(it.get("top"))
        a.tokens, a.words, a.cid, a.tnorm = tokens, words, None, tnorm
        self.arts[a.id] = a
        self.by_url[url] = a.id
        self.by_title[(okey, tnorm)] = a.id
        return a

    # ── 이슈 묶기 ─────────────────────────────────────────
    def _core(self, c):
        if c.dirty:
            n = len(c.aids)
            scored = sorted(((cnt / n * self.idf(t), t) for t, cnt in c.tok.items()),
                            reverse=True)[:14]
            c.core = {t: w for w, t in scored if w > 0}
            c.norm = math.sqrt(sum(w * w for w in c.core.values())) or 1.0
            c.dirty = False
        return c.core

    def _assign(self, a):
        cand = Counter()
        for t in a.tokens:
            for cid in self.tok2c.get(t, ()):
                cand[cid] += 1
        w = {t: self.idf(t) for t in a.tokens}
        an = math.sqrt(sum(v * v for v in w.values())) or 1.0
        best, best_s = None, 0.0
        for cid, shared in cand.items():
            if shared < 2:
                continue
            c = self.clusters[cid]
            core = self._core(c)
            dot, k = 0.0, 0
            for t, v in w.items():
                cw = core.get(t)
                if cw:
                    dot += v * cw
                    k += 1
            if k < 2:
                continue
            s = dot / (an * c.norm)
            if s > best_s:
                best, best_s = c, s
        if best is None or best_s < JOIN_THR:
            best = Cluster("c" + a.id)
            self.clusters[best.id] = best
        self._add(best, a)

    def _add(self, c, a):
        c.aids.append(a.id)
        a.cid = c.id
        for t in a.tokens:
            c.tok[t] += 1
            self.tok2c[t].add(c.id)
        c.dirty = True

    def _merge_pass(self, now):
        act = []
        for c in self.clusters.values():
            if len(c.aids) >= 2:
                c.dirty = True               # idf가 변했으니 다시 계산
                self._core(c)
                act.append(c)
        index = defaultdict(list)
        for c in act:
            for t in list(c.core)[:6]:
                index[t].append(c.id)
        pairs = Counter()
        for t, ids in index.items():
            if len(ids) > 40:
                continue
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pairs[(ids[i], ids[j])] += 1
        merged = 0
        for (x, y), shared in sorted(pairs.items(), key=lambda p: -p[1]):
            if shared < 2:
                break
            cx, cy = self.clusters.get(self._resolve(x)), self.clusters.get(self._resolve(y))
            if cx is None or cy is None or cx is cy:
                continue
            a, b = self._core(cx), self._core(cy)
            dot = sum(v * b[t] for t, v in a.items() if t in b)
            if dot / (cx.norm * cy.norm) < MERGE_THR:
                continue
            big, small = (cx, cy) if len(cx.aids) >= len(cy.aids) else (cy, cx)
            self._merge(big, small)
            merged += 1
        return merged + self._topic_merge()

    def _merge(self, big, small):
        for aid in small.aids:
            big.aids.append(aid)
            self.arts[aid].cid = big.id
        for t, cnt in small.tok.items():
            big.tok[t] += cnt
            self.tok2c[t].discard(small.id)
            self.tok2c[t].add(big.id)
        big.dirty = True
        self.alias[small.id] = big.id
        del self.clusters[small.id]

    def _topic_merge(self):
        """한 인물·사건 이름이 갑자기 쏟아질 때, 갈래로 흩어진 묶음을 하나의 큰 이슈로 모은다.

        평소 흔한 말(경찰, 트럼프…)은 수많은 서로 다른 묶음에 흩어져 있지만,
        터진 이슈의 이름(예: 특정 인물)은 기사 수에 비해 묶음 수가 적다 — 그 쏠림을 본다.
        """
        total = len(self.arts)
        big, mid = max(25, TOPIC_SHARE * total), max(12, TOPIC_SHARE * total / 2)
        cand = []
        for t, df in self.df.items():
            if df < mid or t in GENERIC or len(t) < 2:
                continue
            cids = self.tok2c.get(t)
            if not cids or len(cids) < 2:
                continue
            # 기사 100건 중 1건 넘게 제목에 오른 이름이거나, 그 절반이라도 몇 묶음에 쏠려 있으면 후보
            if df >= big or df / len(cids) >= TOPIC_RATIO:
                cand.append((df, t))
        merged = 0
        for _, t in sorted(cand, reverse=True)[:25]:
            dom = []
            for cid in list(self.tok2c.get(t, ())):
                c = self.clusters.get(cid)
                if c is not None and c.tok.get(t, 0) / len(c.aids) >= 0.5:
                    dom.append(c)
            if len(dom) < 2:
                continue
            dom.sort(key=lambda c: -len(c.aids))
            hub = dom[0]
            if len(hub.aids) < 3:
                continue
            for c in dom[1:]:
                # 이름 하나만 같아서는 부족 — 다른 낱말도 하나는 겹쳐야 같은 이슈로 본다
                n, hn = len(c.aids), len(hub.aids)
                if any(cnt / n >= 0.3 and hub.tok.get(u, 0) >= max(2, 0.06 * hn)
                       and not u.startswith(t) and not t.startswith(u)
                       for u, cnt in c.tok.items()):
                    self._merge(hub, c)
                    merged += 1
        return merged

    def debug_topics(self):
        rows = []
        for t, df in self.df.items():
            cids = self.tok2c.get(t)
            if df >= 10 and cids:
                rows.append((round(df / len(cids), 2), df, len(cids), t, t in GENERIC))
        return sorted(rows, reverse=True)[:40]

    def _resolve(self, cid):
        seen = 0
        while cid in self.alias and seen < 20:
            cid = self.alias[cid]
            seen += 1
        return cid

    def _expire(self, now):
        cut = now - KEEP_HOURS * 3600
        dead = [a for a in self.arts.values() if a.ts < cut]
        for a in dead:
            del self.arts[a.id]
            self.by_url.pop(a.url, None)
            self.by_title.pop((a.okey, a.tnorm), None)
            for t in a.tokens:
                self.df[t] -= 1
                if self.df[t] <= 0:
                    del self.df[t]
            c = self.clusters.get(a.cid)
            if c is None:
                continue
            c.aids.remove(a.id)
            for t in a.tokens:
                c.tok[t] -= 1
                if c.tok[t] <= 0:
                    del c.tok[t]
                    self.tok2c[t].discard(c.id)
            c.dirty = True
            if not c.aids:
                del self.clusters[c.id]
        if len(self.alias) > 5000:
            self.alias = {k: v for k, v in self.alias.items() if v in self.clusters}

    # ── 순위 계산 ─────────────────────────────────────────
    def set_trends(self, trends):
        with self.lock:
            out = []
            for t in trends:
                words = [w for w in split_words(t["keyword"]) if len(w) >= 2]
                if words:
                    out.append({"keyword": t["keyword"], "words": words,
                                "flat": t["keyword"].replace(" ", "").lower()})
            self.trends = out
            self.trends_src = [{"keyword": t["keyword"]} for t in trends]

    def recompute(self, now=None):
        now = now or time.time()
        with self.lock:
            self._expire(now)
            self._merge_pass(now)
            ranked = []
            for c in self.clusters.values():
                if len(c.aids) < 2:
                    continue
                issue = self._score(c, now)
                if issue:
                    ranked.append(issue)
            ranked.sort(key=lambda i: -i["hot"] * CAT_WEIGHT[i["cat"]])
            ranks = {i["id"]: n + 1 for n, i in enumerate(ranked[:60])}
            # 10분쯤 전 순위와 비교해 오르내림 표시
            old = None
            for ts, snap in self.hist:
                if 240 <= now - ts <= 900:
                    old = snap
            for i in ranked[:60]:
                if old is None:
                    i["change"], i["isNew"] = None, False
                else:
                    prev = old.get(i["id"])
                    if prev is None:
                        i["change"], i["isNew"] = None, True
                    else:
                        i["change"], i["isNew"] = prev - ranks[i["id"]], False
            if not self.hist or now - self.hist[-1][0] >= 55:
                self.hist.append((now, ranks))
            # 순위에 오르기 전이라도 바로 보이도록: 최근 2시간 안에 '속보'로 올라온 글(이슈당 하나)
            flash, seen = [], set()
            for a in sorted((a for a in self.arts.values() if a.breaking and now - a.ts <= 7200),
                            key=lambda a: -a.ts):
                if a.cid in seen:
                    continue
                seen.add(a.cid)
                flash.append({"id": a.id, "title": a.title, "url": a.url, "outlet": a.outlet,
                              "ts": a.ts, "cid": a.cid, "urgent": bool(a.tokens & URGENT)})
                if len(flash) >= 5:
                    break
            self.flash = flash
            self.ranked = ranked
            self.updated = now
            self.version += 1

    def _score(self, c, now):
        arts = [self.arts[x] for x in c.aids]
        per, vol = {}, 0.0
        brk = top = False
        recent = set()
        cats = Counter()
        latest = first = arts[0].ts
        for a in arts:
            age = max(0.0, now - a.ts) / 60.0
            w = 0.5 ** (age / HALF_LIFE_MIN)
            vol += w
            if w > per.get(a.okey, 0.0):
                per[a.okey] = w
            if a.breaking and age <= 120:
                brk = True
            if a.top and age <= 300:
                top = True
            if age <= 25:
                recent.add(a.okey)
            cats[a.cat] += a.catw
            latest = max(latest, a.ts)
            first = min(first, a.ts)
        outlets = len(per)
        if outlets < 2:
            return None
        base = sum(per.values())
        hot = base + 0.2 * (vol - base)
        if hot < 0.05:
            return None
        if brk:
            hot *= 1.4
        if top:
            hot *= 1.2
        core = self._core(c)
        n = len(arts)
        shares = sorted(((c.tok[t] / n, t) for t in core), reverse=True)
        label = self._label(c, arts)
        trend = False
        flat = label.replace(" ", "").lower()
        for t in self.trends:
            if t["flat"] in flat or all(c.tok.get(w, 0) / n >= 0.3 for w in t["words"]):
                trend = True
                break
        if trend:
            hot *= 1.3
        rising = len(recent) >= 3 and (now - first <= 5400 or len(recent) >= 0.5 * outlets)
        if rising:
            hot *= 1.15
        cat = cats.most_common(1)[0][0]
        urgent = any(c.tok.get(w, 0) / n >= 0.3 for w in URGENT if w in c.tok)
        if urgent:
            hot *= 1.25
            if cat == "politics":
                cat = "world"                 # 안보 이슈는 정치 몫 제한에 걸리지 않게
        head = self._headline(arts, core, now)
        return {
            "id": c.id, "label": label, "headline": head.title, "cat": cat,
            "outlets": outlets, "count": n, "latest": latest, "first": first,
            "breaking": brk, "rising": rising, "trend": trend, "exclusive": head.exclusive,
            "urgent": urgent,
            "hot": round(hot, 3), "eligible": outlets >= 3 or (brk and outlets >= 2),
            "_core": [(t, s) for s, t in shares if s >= 0.25][:8],
            "_ts": sorted((a.ts for a in arts), reverse=True),
        }

    def _label(self, c, arts):
        """이슈 이름: 묶음 안에서 가장 널리 쓰인 낱말(또는 늘 붙어 다니는 두 낱말) 하나둘."""
        n = len(arts)
        uni, bi, pos = Counter(), Counter(), defaultdict(float)
        for a in arts:
            w, seen = a.words, set()
            for i, x in enumerate(w):
                if x not in a.tokens:
                    continue
                at = i / max(1, len(w))
                if x not in seen:
                    seen.add(x)
                    uni[x] += 1
                    pos[x] += at
                if i + 1 < len(w):
                    y = w[i + 1]
                    ok = y in a.tokens or (len(y) == 1 and "가" <= y <= "힣" and y not in EDGE_STOP)
                    g = x + " " + y
                    if ok and g not in seen:
                        seen.add(g)
                        bi[g] += 1
                        pos[g] += at

        def rare(t):
            return math.sqrt(max(0.3, self.idf(t)))

        def early(key, cnt):                  # 제목 앞쪽에 오는 말(대개 주어)을 조금 더 친다
            return 1.25 - 0.5 * (pos[key] / cnt)

        units = [(cnt / n * rare(t) * early(t, cnt), t, cnt) for t, cnt in uni.items()]
        pairs = []
        for g, cnt in bi.items():
            x, y = g.split(" ")
            if cnt >= 2 and cnt >= 0.6 * uni[x] and cnt >= 0.6 * uni.get(y, cnt):
                r = (rare(x) + rare(y)) / 2 if y in uni else rare(x)
                pairs.append((cnt / n * r * 1.3 * early(g, cnt), g, cnt))
        units.sort(reverse=True)
        pairs.sort(reverse=True)
        if not units:
            return arts[0].title[:14]
        _, u1, c1 = units[0]
        for s, g, cnt in pairs:               # 대표 낱말이 늘 붙어 다니는 짝이 있으면 함께
            if u1 in g.split(" ") and cnt >= 0.6 * c1:
                u1, c1 = g, cnt
                break
        else:
            if pairs and pairs[0][0] > units[0][0]:
                _, u1, c1 = pairs[0]
        used = set(u1.split(" "))
        flat1 = u1.replace(" ", "")
        second = None
        for s, u2, c2 in sorted(units[:10] + pairs[:6], reverse=True):
            if c2 < 2 or c2 / n < 0.4 or used & set(u2.split(" ")):
                continue
            flat2 = u2.replace(" ", "")
            if flat2 in flat1 or flat1 in flat2:
                continue
            if len(u1) + len(u2) + 1 > 17:
                continue
            second = u2
            break
        parts = [u1]
        if second:
            parts = [u1, second] if pos[u1] / c1 <= pos[second] / (uni.get(second) or bi[second]) \
                else [second, u1]
        return " ".join(pretty(w) for p in parts for w in p.split(" "))

    def _headline(self, arts, core, now):
        """가장 최근 소식을 대표 제목으로. 너무 동떨어진 제목은 피한다."""
        by_new = sorted(arts, key=lambda a: -a.ts)
        pool = by_new[: max(3, len(arts) * 2 // 5)]

        def fit(a):
            s = sum(core.get(t, 0.0) for t in a.tokens)
            if a.breaking:
                s *= 1.15
            if len(a.title) > 44:
                s *= 0.85
            return s
        return max(pool, key=fit)

    # ── 화면용 데이터 ─────────────────────────────────────
    def export(self, limit=260):
        """브라우저가 받아 가는 순위 데이터.

        관심사 반영과 분야별 몫 나누기(정치·연예는 일부만)는 화면 쪽에서 한다.
        그래야 서버 없이 정적 파일만으로도(GitHub Pages) 사람마다 다른 순위를 보여줄 수 있다.
        """
        with self.lock:
            items = {}
            for i in self.ranked[:limit]:
                items[i["id"]] = {
                    "label": i["label"], "headline": i["headline"], "cat": i["cat"],
                    "outlets": i["outlets"], "count": i["count"],
                    "latest": int(i["latest"]), "first": int(i["first"]),
                    "breaking": i["breaking"], "rising": i["rising"], "trend": i["trend"],
                    "urgent": i["urgent"], "hot": i["hot"], "eligible": i["eligible"],
                    "change": i.get("change"), "isNew": i.get("isNew", False),
                    "core": [[t, round(s, 2)] for t, s in i["_core"]],
                    "ts": [int(t) for t in i["_ts"][:30]],
                }
            alias = {}
            for old in self.alias:
                new = self._resolve(old)
                if new in items:
                    alias[old] = new
            return {
                "updated": int(self.updated), "order": list(items), "items": items, "alias": alias,
                "flash": [dict(f, ts=int(f["ts"])) for f in self.flash],
                "trends": [t["keyword"] for t in self.trends if _HANGUL.search(t["keyword"])][:10],
                "articles": len(self.arts),
                "catLabels": CAT_LABEL, "catWeight": CAT_WEIGHT, "catCap": CAT_CAP,
                "mainSize": MAIN_SIZE,
            }

    def main_order(self):
        """관심사 없이 본 기본 종합 순위 (점검용 — 화면의 계산과 같은 규칙)."""
        with self.lock:
            issues = sorted(self.ranked, key=lambda i: -i["hot"] * CAT_WEIGHT[i["cat"]])
        main, used = [], Counter()
        for i in issues:
            if not i["eligible"]:
                continue
            cap = CAT_CAP.get(i["cat"])
            if cap is not None and used[i["cat"]] >= cap:
                continue
            used[i["cat"]] += 1
            main.append(i)
            if len(main) >= MAIN_SIZE:
                break
        for cat in ("politics", "ent"):
            if used[cat] or len(main) < MAIN_SIZE:
                continue
            best = next((i for i in issues if i["cat"] == cat and i["eligible"]
                         and i["outlets"] >= 5), None)
            if best:
                main[-1] = best
                main.sort(key=lambda i: -i["hot"] * CAT_WEIGHT[i["cat"]])
        return main

    def detail(self, cid):
        """이슈 하나의 관련 뉴스. '_'로 시작하는 항목은 내부용이라 화면으로 내보내지 않는다."""
        with self.lock:
            cid = self._resolve(cid)
            c = self.clusters.get(cid)
            if c is None:
                return None
            arts = sorted((self.arts[x] for x in c.aids), key=lambda a: -a.ts)
            core = self._core(c)
            n = len(arts)
            mine = {t for t in core if c.tok[t] / n >= 0.3}
            related = []
            for i in self.ranked[:150]:
                if i["id"] == cid:
                    continue
                shared = [t for t, s in i["_core"] if t in mine and s >= 0.3]
                if shared:
                    strength = sum(self.idf(t) for t in shared)
                    related.append((strength, i["id"], i["label"], i["headline"]))
            related.sort(reverse=True)
            cats = Counter()
            for a in arts:
                cats[a.cat] += a.catw
            known = next((i for i in self.ranked if i["id"] == cid), None)
            keys = [t for _, t in sorted(((c.tok[t] / n, t) for t in core
                                         if c.tok[t] / n >= 0.2), reverse=True)]
            # '젠슨'이 있으면 붙여 쓴 '젠슨황'은 같은 말이므로 한 번만
            keys = [k for k in keys if not any(k != j and k.startswith(j) and len(k) - len(j) == 1
                                               for j in keys)][:6]
            # 이 이슈의 여러 기사에 함께 나오는 낱말만 관심사로 배운다 (한 기사에만 쓰인 말은 잡음)
            common = {t for t, cnt in c.tok.items() if cnt >= 2 and cnt / n >= 0.2}
            # 같은 통신 기사를 여러 곳이 그대로 실은 것은 한 줄로 접는다
            shown = []
            for a in arts:
                twin = None
                for s in shown[-80:]:
                    both = len(a.tokens & s["_tok"])
                    if both and both / len(a.tokens | s["_tok"]) >= 0.75:
                        twin = s
                        break
                if twin:
                    if a.outlet != twin["outlet"] and a.outlet not in twin["also"]:
                        twin["also"].append(a.outlet)
                    continue
                words = [w for w in dict.fromkeys(a.words)
                         if w in a.tokens and (w in common or n < 3)]
                shown.append({"id": a.id, "title": a.title, "url": a.url, "outlet": a.outlet,
                              "ts": int(a.ts), "breaking": a.breaking, "exclusive": a.exclusive,
                              "also": [], "lt": self.learn_weights(words), "_tok": a.tokens})
                if len(shown) >= 60:
                    break
            for s in shown:
                del s["_tok"]
            return {
                "id": cid,
                "label": known["label"] if known else self._label(c, arts),
                "outlets": len({a.okey for a in arts}),
                "count": n,
                "keywords": keys,
                "learn": self.learn_weights(keys[:5]),
                "cat": known["cat"] if known else cats.most_common(1)[0][0],
                "articles": shown,
                "related": [{"id": r[1], "label": r[2], "headline": r[3]} for r in related[:5]],
                "_titles": {a.tnorm for a in arts},
            }

    @staticmethod
    def learn_weights(tokens):
        """관심사로 배울 낱말 → 반영 비율. 밋밋한 말은 빼고, 폭넓은 말(트럼프·코스피…)은 절반만."""
        out = {}
        for t in tokens:
            if t in BLAND or t in STOP or len(t) < 2:
                continue
            out[t] = 0.5 if t in _CAT_LOOKUP else 1.0
        return out

    # ── 저장/복원 ─────────────────────────────────────────
    def dump_state(self):
        """다음 실행이 이어받을 상태: 기사와 그 기사가 속한 이슈, 순위 기록."""
        with self.lock:
            return {
                "v": 2,
                "articles": [{"title": a.raw, "url": a.url, "outlet": a.outlet, "ts": a.ts,
                              "cat": a.cat if a.catw >= 2 else None, "top": a.top, "cid": a.cid}
                             for a in self.arts.values()],
                "alias": {k: v for k, v in self.alias.items() if v in self.clusters},
                "hist": [[ts, ranks] for ts, ranks in self.hist][-12:],
                "trends": self.trends_src,
            }

    def restore(self, state, now=None):
        """dump_state 로 남긴 상태를 되살린다. 이슈 id가 그대로 유지돼 순위 변동·'새 기사' 표시가 이어진다."""
        now = now or time.time()
        if isinstance(state, list):            # 예전 형식(기사 목록만)
            state = {"articles": state}
        with self.lock:
            fresh = []
            for it in state.get("articles", []):
                a = self._make(it, now)
                if a is not None:
                    fresh.append((a, it.get("cid")))
            for a, _ in fresh:
                for t in a.tokens:
                    self.df[t] += 1
            fresh.sort(key=lambda p: p[0].ts)
            for a, cid in fresh:
                if cid:
                    c = self.clusters.get(cid)
                    if c is None:
                        c = self.clusters[cid] = Cluster(cid)
                    self._add(c, a)
                else:
                    self._assign(a)
            for k, v in state.get("alias", {}).items():
                if v in self.clusters and k not in self.clusters:
                    self.alias[k] = v
            for ts, ranks in state.get("hist", []):
                self.hist.append((ts, ranks))
            if state.get("trends"):
                self.set_trends(state["trends"])
            return len(fresh)
