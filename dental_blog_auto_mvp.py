# ============================================
# dental_blog_auto_mvp.py
# 치과 블로그 자동 생성 MVP
# ============================================

"""
기능
1. 네이버 DataLab 트렌드 기반 키워드 자동 선택
2. Claude API로 블로그 글 생성
3. 의료광고 위험 표현 필터링
4. Unsplash 이미지 자동 삽입
5. Markdown 파일 저장
6. 주 2회 자동 실행

설치
pip install anthropic apscheduler python-dotenv requests gspread google-api-python-client

.env 파일 생성:
ANTHROPIC_API_KEY=your_api_key
UNSPLASH_ACCESS_KEY=your_unsplash_key
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret
GOOGLE_SHEET_ID=your_google_sheet_id

실행:
python dental_blog_auto_mvp.py
"""

import json
import os
import random
from datetime import datetime, timedelta

import gspread
import requests
from apscheduler.schedulers.blocking import BlockingScheduler
import anthropic
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ============================================
# 환경 설정
# ============================================

load_dotenv()

client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")
BLOG_DIR = os.path.join(POSTS_DIR, "blog")
META_DIR = os.path.join(POSTS_DIR, "meta")
HOOKS_DIR = os.path.join(POSTS_DIR, "hooks")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")


def _load_google_credentials(scopes):
    """구글 인증 정보 로드. 실패 시 None 반환."""
    _credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not _credentials_json:
        print("[구글 인증] GOOGLE_CREDENTIALS_JSON 환경변수 없음, 구글 연동 건너뜀")
        return None
    try:
        info = json.loads(_credentials_json)
    except json.JSONDecodeError:
        _credentials_json = _credentials_json.replace('\n', '\\n').replace('\\\\n', '\\n')
        try:
            info = json.loads(_credentials_json)
        except json.JSONDecodeError as e:
            print(f"[구글 인증] JSON 파싱 실패: {e}")
            return None
    return Credentials.from_service_account_info(info, scopes=scopes)

for d in [BLOG_DIR, META_DIR, HOOKS_DIR]:
    os.makedirs(d, exist_ok=True)

# ============================================
# 치과 키워드 DB
# ============================================

KEYWORDS = [
    # 관리
    {"keyword": "사랑니 발치 후 음식", "category": "관리", "seasons": []},
    {"keyword": "스케일링 후 식사", "category": "관리", "seasons": []},
    {"keyword": "치아 미백 후 관리", "category": "관리", "seasons": []},
    {"keyword": "임플란트 관리 방법", "category": "관리", "seasons": []},
    {"keyword": "교정 중 칫솔질", "category": "관리", "seasons": []},
    {"keyword": "발치 후 지혈 방법", "category": "관리", "seasons": []},
    {"keyword": "치실 사용법", "category": "관리", "seasons": []},
    {"keyword": "전동칫솔 올바른 사용법", "category": "관리", "seasons": []},
    {"keyword": "틀니 세척 방법", "category": "관리", "seasons": []},

    # 증상
    {"keyword": "이가 시린 이유", "category": "증상", "seasons": ["12", "1", "2"]},  # 겨울 - 찬 바람
    {"keyword": "충치 초기 증상", "category": "증상", "seasons": []},
    {"keyword": "잇몸 붓는 이유", "category": "증상", "seasons": []},
    {"keyword": "이가 흔들리는 이유", "category": "증상", "seasons": []},
    {"keyword": "입냄새 원인", "category": "증상", "seasons": []},
    {"keyword": "이 시림 치료", "category": "증상", "seasons": ["12", "1", "2"]},
    {"keyword": "턱 통증 원인", "category": "증상", "seasons": []},
    {"keyword": "잇몸 출혈 원인", "category": "증상", "seasons": []},
    {"keyword": "치아 깨짐 대처", "category": "증상", "seasons": []},

    # 시술
    {"keyword": "임플란트 통증 기간", "category": "시술", "seasons": []},
    {"keyword": "신경치료 통증", "category": "시술", "seasons": []},
    {"keyword": "스케일링 주기", "category": "시술", "seasons": ["3", "9"]},  # 봄·가을 정기검진
    {"keyword": "치아 미백 종류", "category": "시술", "seasons": ["5", "6"]},  # 봄·여름 미용 관심
    {"keyword": "임플란트 수술 과정", "category": "시술", "seasons": []},
    {"keyword": "잇몸 치료 종류", "category": "시술", "seasons": []},
    {"keyword": "사랑니 발치 과정", "category": "시술", "seasons": []},
    {"keyword": "라미네이트 치료", "category": "시술", "seasons": ["5", "6"]},  # 봄·여름 미용 관심

    # 교정
    {"keyword": "교정 유지장치 세척", "category": "교정", "seasons": []},
    {"keyword": "투명교정 장단점", "category": "교정", "seasons": ["2", "3"]},  # 새학기
    {"keyword": "치아교정 음식 제한", "category": "교정", "seasons": []},
    {"keyword": "교정 기간 단축 방법", "category": "교정", "seasons": []},
    {"keyword": "교정 후 유지장치 기간", "category": "교정", "seasons": []},

    # 소아·청소년
    {"keyword": "어린이 충치 예방", "category": "소아", "seasons": ["7", "8"]},  # 여름방학
    {"keyword": "실란트 치료 대상", "category": "소아", "seasons": ["7", "8"]},  # 여름방학
    {"keyword": "아이 첫 치과 방문 시기", "category": "소아", "seasons": []},

    # 노인·특수
    {"keyword": "임플란트 나이 제한", "category": "노인", "seasons": []},
    {"keyword": "틀니 vs 임플란트 비교", "category": "노인", "seasons": []},
    {"keyword": "노인 구강 건강 관리", "category": "노인", "seasons": []},

    # 계절 특화
    {"keyword": "명절 음식 치아 주의", "category": "계절", "seasons": ["1", "9"]},   # 설·추석
    {"keyword": "여름 냉음료 치아 시림", "category": "계절", "seasons": ["6", "7", "8"]},
    {"keyword": "겨울 치아 시림 예방", "category": "계절", "seasons": ["11", "12", "1"]},
    {"keyword": "새학기 교정 시작 시기", "category": "계절", "seasons": ["2", "3"]},

    # 로컬 — 위례·거여·문정 + 인근 (송파구 일대)
    {"keyword": "위례 치과 스케일링", "category": "로컬", "seasons": [], "local": True, "area": "위례"},
    {"keyword": "위례 임플란트 비용", "category": "로컬", "seasons": [], "local": True, "area": "위례"},
    {"keyword": "위례 사랑니 발치", "category": "로컬", "seasons": [], "local": True, "area": "위례"},
    {"keyword": "거여 치과 추천", "category": "로컬", "seasons": [], "local": True, "area": "거여"},
    {"keyword": "거여 충치 치료", "category": "로컬", "seasons": [], "local": True, "area": "거여"},
    {"keyword": "문정 치과 교정", "category": "로컬", "seasons": [], "local": True, "area": "문정"},
    {"keyword": "문정 임플란트", "category": "로컬", "seasons": [], "local": True, "area": "문정"},
    {"keyword": "송파 스케일링 잘하는 곳", "category": "로컬", "seasons": [], "local": True, "area": "송파"},
    {"keyword": "송파 신경치료", "category": "로컬", "seasons": [], "local": True, "area": "송파"},
    {"keyword": "장지 치과", "category": "로컬", "seasons": [], "local": True, "area": "장지"},
    {"keyword": "복정 치과 임플란트", "category": "로컬", "seasons": [], "local": True, "area": "복정"},
    {"keyword": "마천 치과 교정", "category": "로컬", "seasons": [], "local": True, "area": "마천"},
    {"keyword": "오금 치과 충치", "category": "로컬", "seasons": [], "local": True, "area": "오금"},
    {"keyword": "가락 치과 스케일링", "category": "로컬", "seasons": [], "local": True, "area": "가락"},
]

# ============================================
# 의료광고 위험 표현 필터
# ============================================

BANNED_WORDS = {
    "완치": "개선",
    "100%": "개인 상태에 따라 다를 수 있음",
    "최고의": "도움이 될 수 있는",
    "부작용 없음": "부작용 가능성은 상담이 필요함",
    "무통": "통증 감소를 고려한",
    "절대": "상황에 따라",
}

# AI 생성 시 발생하는 오타 교정
TYPO_CORRECTIONS = {
    "스케알링": "스케일링",
    "임플란틀": "임플란트",
    "사랑이": "사랑니",
}

# ============================================
# 네이버 DataLab 트렌드 조회
# ============================================

def get_naver_trend_scores():
    """네이버 DataLab 검색어 트렌드 API로 키워드별 최근 1주 평균 검색량 조회"""

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")

    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)

    # DataLab API 제한: keywordGroups 최대 5개
    sampled = random.sample(KEYWORDS, min(5, len(KEYWORDS)))
    keyword_groups = [
        {"groupName": kw["keyword"], "keywords": [kw["keyword"]]}
        for kw in sampled
    ]

    body = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "date",
        "keywordGroups": keyword_groups,
    }

    try:
        response = requests.post(
            "https://openapi.naver.com/v1/datalab/search",
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
                "Content-Type": "application/json",
            },
            data=json.dumps(body),
            timeout=10
        )
        data = response.json()
        results = data.get("results", [])

        scores = {}
        for result in results:
            keyword = result["title"]
            values = result.get("data", [])
            avg_ratio = sum(v["ratio"] for v in values) / len(values) if values else 0
            scores[keyword] = avg_ratio

        return scores

    except Exception as e:
        print(f"[DataLab 오류] {e}")
        return {}


# ============================================
# 키워드 선택
# ============================================

def get_recently_used_keywords(limit=15):
    """최근 limit개 게시글에서 사용된 키워드 목록 반환"""

    if not os.path.exists(BLOG_DIR):
        return set()

    files = sorted(
        [f for f in os.listdir(BLOG_DIR) if f.endswith(".txt")],
        reverse=True
    )[:limit]

    used = set()
    for filename in files:
        # 파일명에서 키워드 추출: YYYY-MM-DD-키워드.md → 키워드
        name = filename[len("YYYY-MM-DD-"):].replace("-", " ").replace(".md", "")
        # 날짜 부분(11자) 제거
        name = filename[11:].replace("-", " ").replace(".md", "")
        used.add(name)

    return used


def get_seasonal_keywords():
    """현재 월 기준으로 계절 태그가 맞는 키워드 반환"""
    current_month = str(datetime.now().month)
    return [kw for kw in KEYWORDS if current_month in kw.get("seasons", [])]


def select_keyword():
    """키워드 선택 우선순위:
    1. 계절 키워드 + 네이버 트렌드 점수 높은 것
    2. 계절 키워드 중 미사용 랜덤
    3. 전체 키워드 중 트렌드 점수 높은 것
    4. 전체 미사용 키워드 중 랜덤
    5. 전체 랜덤
    """

    recently_used = get_recently_used_keywords(limit=15)
    scores = get_naver_trend_scores()
    seasonal = get_seasonal_keywords()
    seasonal_names = {kw["keyword"] for kw in seasonal}

    def pick_by_score(candidates):
        """candidates 중 트렌드 점수 높은 미사용 키워드 반환"""
        available = [kw for kw in candidates if kw["keyword"] not in recently_used]
        if scores and available:
            scored = [(kw, scores.get(kw["keyword"], 0)) for kw in available]
            scored.sort(key=lambda x: x[1], reverse=True)
            best_kw, best_score = scored[0]
            if best_score > 0:
                print(f"[트렌드 선택] {best_kw['keyword']} (점수: {best_score:.1f})")
                return best_kw
        return None

    # 1. 계절 키워드 + 트렌드
    if seasonal:
        result = pick_by_score(seasonal)
        if result:
            return result

        # 2. 계절 키워드 중 미사용 랜덤
        available_seasonal = [kw for kw in seasonal if kw["keyword"] not in recently_used]
        if available_seasonal:
            chosen = random.choice(available_seasonal)
            print(f"[계절 랜덤] {chosen['keyword']}")
            return chosen

    # 3. 전체 키워드 + 트렌드
    result = pick_by_score(KEYWORDS)
    if result:
        return result

    # 4. 전체 미사용 랜덤
    available = [kw for kw in KEYWORDS if kw["keyword"] not in recently_used]
    if available:
        chosen = random.choice(available)
        print(f"[미사용 랜덤] {chosen['keyword']}")
        return chosen

    # 5. 전체 랜덤
    print("[전체 랜덤] 모든 키워드 최근 사용됨")
    return random.choice(KEYWORDS)

# ============================================
# Claude 블로그 생성
# ============================================

def load_reference_posts():
    """posts/ 루트의 참고예시*.md 전부 읽기 (문체·구성 참고용)"""

    posts = []
    if os.path.exists(POSTS_DIR):
        ref_files = sorted(
            [f for f in os.listdir(POSTS_DIR) if f.startswith("참고예시") and f.endswith(".md")]
        )
        for filename in ref_files:
            with open(os.path.join(POSTS_DIR, filename), "r", encoding="utf-8") as f:
                posts.append(f.read())
    return posts


def load_recent_post_titles(n=10):
    """posts/blog/ 최근 n개 파일명에서 소재(키워드) 추출 (중복 소재 방지용)"""

    if not os.path.exists(BLOG_DIR):
        return []
    recent_files = sorted(
        [f for f in os.listdir(BLOG_DIR) if f.endswith(".txt")],
        reverse=True
    )[:n]
    # 파일명 YYYY-MM-DD-키워드.txt → 키워드
    titles = [f[11:].replace("-", " ").replace(".txt", "") for f in recent_files]
    return titles


def generate_hooks(keyword):
    """hook-generator 스킬: 주제 하나로 훅 6개 생성"""
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""
다음 치과 블로그 주제로 네이버 블로그 첫 문장(훅) 6개를 만들어줘.

주제: {keyword}

조건:
- 각 훅은 2줄 이내
- 클릭하고 싶게 만드는 문장
- 광고 느낌 없이 환자 공감형으로
- 번호 붙여서 6개만 출력

예시 형태:
1. 스케일링 받고 나서 밥을 바로 먹어도 될까요?
   많은 분들이 헷갈려하는 부분, 오늘 정리해드릴게요.
"""
        }]
    )
    hooks = response.content[0].text.strip()
    print(f"[훅 생성 완료]\n{hooks}")
    return hooks


def generate_blog_post(keyword_data, hooks=""):

    keyword = keyword_data["keyword"]
    is_local = keyword_data.get("local", False)
    area = keyword_data.get("area", "")

    ref_posts = load_reference_posts()
    recent_titles = load_recent_post_titles(n=10)

    if ref_posts:
        reference_section = "\n\n[문체·구성 참고 예시] 아래 글들의 말투와 구성 방식만 참고해서 써줘 (내용은 따라 쓰지 말 것):\n"
        for i, post in enumerate(ref_posts, 1):
            reference_section += f"\n--- 예시 {i} ---\n{post[:1500]}\n"
    else:
        reference_section = ""

    if recent_titles:
        recent_section = "\n\n[최근 다룬 소재] 아래 주제들은 이미 작성했으니 내용이 겹치지 않게 참고만 해줘:\n"
        recent_section += "\n".join(f"- {t}" for t in recent_titles)
    else:
        recent_section = ""

    hook_section = f"\n\n[도입부 훅 참고] 아래 훅 중 하나를 골라 도입부 첫 문장으로 활용해줘:\n{hooks}\n" if hooks else ""

    local_section = ""
    if is_local and area:
        local_section = f"""
[로컬 SEO 조건]
- 글 전체에서 "{area}" 지역명을 3~5회 자연스럽게 언급 (억지스럽지 않게)
- 도입부나 마무리에 "{area}" 인근 주민이 공감할 수 있는 상황 묘사 포함
- 지역 특성과 연결되는 내용 가능하면 포함 (예: 출퇴근, 주거 환경 등)
"""

    prompt = f"""
너는 한국 치과 블로그 전문 작가다.
SEO(네이버·구글 검색 노출)와 GEO(ChatGPT·Perplexity 등 AI 검색 인용) 둘 다 최적화된 글을 써야 한다.

주제:
"{keyword}"

[SEO 조건]
- 제목, 첫 문단, 소제목에 핵심 키워드를 자연스럽게 배치
- 연관 검색어 2~3개를 본문 안에 자연스럽게 녹여서 사용 (예: 주제가 "스케일링"이면 "치석 제거", "잇몸 관리", "구강 위생" 등)
- 네이버 블로그 스타일, 자연스러운 한국어
- 1800자 이상
- 소제목 포함, 리스트·단계별 설명 활용
- 체류시간을 높이는 흥미로운 도입부
{local_section}
[GEO 조건]
- 도입부 바로 다음에 핵심 답변을 2~3문장으로 먼저 요약 (AI가 인용하기 좋은 형태)
- 구체적인 숫자·기간 포함 (예: "2시간", "3~5일", "하루 2회")
- FAQ는 반드시 "Q: ... / A: ..." 형태로 직접 답변 3개
- 사실 기반 서술, 신뢰할 수 있는 말투
- 비교가 필요한 주제(예: 치료 방법 선택, 증상 단계 구분 등)에서는 표(마크다운 테이블) 사용

[공통 조건]
- 치과를 전혀 모르는 일반인도 쉽게 이해할 수 있는 말투
- 전문 의학 용어는 반드시 쉬운 말로 풀어서 설명
- 친근하고 편한 문체, 짧고 읽기 쉬운 문장
- 과장 금지, 광고 느낌 금지, 의료광고법 위반 표현 금지
- 마크다운 형식, 제목부터 작성

제목 작성 규칙:
- 키워드를 제목 앞쪽에 배치
- 정보형 우선, 질문형은 자연스러울 때만 허용
- 20자 이내
- 광고 느낌 없이 환자 눈높이로
- 친근하고 실용적인 정보 제공 느낌
- 예시: '미백 시술 전에 알아두면 좋은 것들', '스케일링 후 식사, 이렇게 하세요', '사랑니 발치 후 회복 기간 정리'

구조:
1. 제목 (위 규칙 적용)
2. 도입부 (공감 가는 일상적 상황)
3. 핵심 요약 (2~3문장, AI 인용용)
4. 원인/설명 (쉬운 말로)
5. 관리 방법 (구체적 수치 포함, 단계별 리스트)
6. 주의사항
7. FAQ (Q/A 형식, 3개)
8. 마무리
{hook_section}{reference_section}{recent_section}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        system="너는 의료광고법을 준수하는 치과 블로그 전문 작가다."
    )

    content = response.content[0].text

    return content

# ============================================
# Unsplash 이미지 검색
# ============================================

def fetch_unsplash_image(query, used_urls):
    """영문 쿼리로 Unsplash 이미지 검색 후 마크다운 반환 (중복 제외)"""

    access_key = os.getenv("UNSPLASH_ACCESS_KEY")

    try:
        response = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": 10,
                "orientation": "landscape",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10
        )
        data = response.json()
        results = data.get("results", [])

        for photo in results:
            image_url = photo["urls"]["regular"]
            if image_url in used_urls:
                continue
            used_urls.add(image_url)
            alt_text = photo.get("alt_description") or query
            credit_name = photo["user"]["name"]
            credit_link = photo["user"]["links"]["html"]
            markdown_image = (
                f"![{alt_text}]({image_url})\n"
                f"*Photo by [{credit_name}]({credit_link}) on Unsplash*\n\n"
            )
            print(f"[이미지 삽입] {query} → {image_url}")
            return markdown_image

    except Exception as e:
        print(f"[이미지 오류] {e}")

    return ""


def translate_heading_to_english(heading_text):
    """소제목 한국어 → Unsplash 영문 검색 쿼리 변환"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=30,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Translate this Korean dental blog heading into a specific English Unsplash search query "
                    f"(2-4 words, no explanation, no punctuation). "
                    f"Focus on the concrete subject or action in the heading, not just 'dental'. "
                    f"Examples: '도입부' → 'healthy smile', '주의사항' → 'caution warning sign', "
                    f"'사랑니 발치' → 'tooth extraction', '음식 섭취' → 'soft food eating', "
                    f"'FAQ' → 'questions answers':\n{heading_text}"
                )
            }
        ]
    )

    return response.content[0].text.strip()


def append_images_at_end(content, keyword, count=4):
    """글 마지막에 관련 이미지 count장 추가 (중복 없음)"""

    used_urls = set()
    images = []

    # 키워드를 영문으로 번역해서 이미지 검색 쿼리 생성
    base_queries = [
        keyword,
        f"{keyword} dental care",
        "oral health teeth",
        "dental clinic patient",
        "healthy teeth smile",
        "dentist treatment",
    ]

    for query_kr in base_queries:
        if len(images) >= count:
            break
        english_query = translate_heading_to_english(query_kr)
        print(f"[이미지 검색] {query_kr} → {english_query}")
        image_md = fetch_unsplash_image(english_query, used_urls)
        if image_md:
            images.append(image_md)

    if images:
        footer = "\n\n---\n\n## 관련 사진\n\n" + "\n".join(images)
        return content + footer

    return content

# ============================================
# 메타 디스크립션 생성
# ============================================

def generate_meta_description(keyword, content):
    """본문 기반으로 네이버·구글 검색 결과에 노출될 메타 디스크립션 생성 (140자 이내)"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[
            {
                "role": "user",
                "content": (
                    f"아래 치과 블로그 글의 메타 디스크립션을 작성해줘.\n"
                    f"조건: 키워드 '{keyword}' 포함, 140자 이내, 한 문장, 광고 느낌 없이 궁금증을 유발하는 문체.\n"
                    f"설명 없이 메타 디스크립션 텍스트만 출력.\n\n"
                    f"본문 앞부분:\n{content[:800]}"
                )
            }
        ]
    )

    return response.content[0].text.strip()


# ============================================
# 금지 표현 필터
# ============================================

def apply_medical_filter(text):

    for banned, replacement in BANNED_WORDS.items():
        text = text.replace(banned, replacement)

    for typo, correction in TYPO_CORRECTIONS.items():
        text = text.replace(typo, correction)

    return text

# ============================================
# 파일 저장
# ============================================

def wrap_for_mobile(text):
    """마침표·느낌표·물음표 기준으로 줄바꿈 (문장 중간 끊김 없음)"""
    import re
    if not text.strip():
        return text
    # 문장 부호 뒤에서 분리 (부호는 앞 문장에 붙임)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    return "\n".join(s.strip() for s in sentences if s.strip())


def convert_to_plain_text(content):
    """마크다운 → 네이버 블로그용 일반 텍스트 변환"""

    import re

    lines = content.split("\n")
    result = []

    for line in lines:
        # 제목(#) → 대괄호 소제목으로 (줄바꿈 제외)
        if line.startswith("# "):
            result.append(line[2:].strip())
            result.append("")
        elif line.startswith("## "):
            result.append("")
            result.append(f"[ {line[3:].strip()} ]")
            result.append("")
        elif line.startswith("### "):
            result.append(f"▶ {line[4:].strip()}")
        # 마크다운 이미지 → URL만 남기기 (줄바꿈 제외)
        elif line.startswith("!["):
            match = re.search(r'\!\[.*?\]\((.*?)\)', line)
            if match:
                result.append(match.group(1))
                result.append("")
        # 크레딧 줄 제거
        elif line.startswith("*Photo by "):
            continue
        # 구분선 제거
        elif line.strip() == "---":
            result.append("")
        # 표(|로 시작) → 줄바꿈 제외
        elif line.strip().startswith("|"):
            line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            result.append(line)
        # 일반 본문 → 마크다운 제거 후 15자 줄바꿈
        else:
            line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
            line = re.sub(r'\*(.*?)\*', r'\1', line)
            line = re.sub(r'`(.*?)`', r'\1', line)
            if line.strip():
                result.append(wrap_for_mobile(line.strip()))
            else:
                result.append("")

    # 연속 빈줄 최대 2개로 제한 (모바일 가독성)
    final = []
    blank_count = 0
    for line in result:
        if line.strip() == "":
            blank_count += 1
            if blank_count <= 2:
                final.append("")
        else:
            blank_count = 0
            final.append(line)

    return "\n".join(final).strip()


def save_post(keyword, content):

    date_str = datetime.now().strftime("%Y-%m-%d")

    safe_keyword = keyword.replace(" ", "-")

    filename = f"{date_str}-{safe_keyword}.txt"

    filepath = os.path.join(BLOG_DIR, filename)
    meta_filepath = os.path.join(META_DIR, filename)

    meta_description = generate_meta_description(keyword, content)
    print(f"[메타 디스크립션] {meta_description}")

    plain_text = convert_to_plain_text(content)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(plain_text)

    with open(meta_filepath, "w", encoding="utf-8") as f:
        f.write(meta_description)

    print(f"[저장 완료] {filepath}")
    print(f"[메타 저장 완료] {meta_filepath}")

# ============================================
# 구글 독스 저장
# ============================================

def create_google_doc(keyword, plain_text):
    """구글 독스에 블로그 글 저장 후 공유 링크 반환"""

    import traceback

    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = _load_google_credentials(scopes)
    if not creds:
        return ""

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    try:
        doc = docs_service.documents().create(
            body={"title": keyword}
        ).execute()
    except Exception as e:
        print(f"[구글 독스 오류] 문서 생성 실패: {e}")
        print(traceback.format_exc())
        return ""

    doc_id = doc["documentId"]

    try:
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={
                "requests": [
                    {
                        "insertText": {
                            "location": {"index": 1},
                            "text": plain_text,
                        }
                    }
                ]
            }
        ).execute()
    except Exception as e:
        print(f"[구글 독스 오류] 내용 삽입 실패: {e}")
        print(traceback.format_exc())

    try:
        drive_service.permissions().create(
            fileId=doc_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()
    except Exception as e:
        print(f"[구글 독스 오류] 공유 설정 실패: {e}")
        print(traceback.format_exc())

    doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"[구글 독스] 저장 완료: {doc_url}")
    return doc_url


# ============================================
# 구글 시트 성과 기록
# ============================================

def log_to_sheets(keyword_data, filename, doc_url=""):
    """글 생성 정보를 구글 시트에 한 행으로 기록"""

    if not GOOGLE_SHEET_ID:
        print("[구글 시트] GOOGLE_SHEET_ID 미설정, 건너뜀")
        return

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = _load_google_credentials(scopes)
        if not creds:
            return
        gc = gspread.authorize(creds)
        sheet = gc.open_by_key(GOOGLE_SHEET_ID).sheet1

        # 헤더 확인 및 최신 형식으로 업데이트
        HEADERS = ["날짜", "키워드", "카테고리", "파일명", "구글독스링크"]
        first_row = sheet.row_values(1)
        if first_row != HEADERS:
            if not first_row:
                sheet.insert_row(HEADERS, index=1)
            else:
                sheet.update("A1", [HEADERS])

        row = [
            datetime.now().strftime("%Y-%m-%d"),
            keyword_data["keyword"],
            keyword_data.get("category", ""),
            filename,
            doc_url,
        ]
        sheet.append_row(row)
        print(f"[구글 시트] 기록 완료: {keyword_data['keyword']}")

    except Exception as e:
        print(f"[구글 시트 오류] {e}")


# ============================================
# 전체 작업 실행
# ============================================

def run_blog_generation():

    print("=" * 50)
    print("치과 블로그 자동 생성 시작")
    print("=" * 50)

    keyword_data = select_keyword()

    print(f"[선택 키워드] {keyword_data['keyword']}")

    hooks = generate_hooks(keyword_data["keyword"])

    content = generate_blog_post(keyword_data, hooks=hooks)

    filtered_content = apply_medical_filter(content)

    final_content = append_images_at_end(filtered_content, keyword_data["keyword"], count=4)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}-{keyword_data['keyword'].replace(' ', '-')}.txt"

    save_post(keyword_data["keyword"], final_content)

    hooks_filepath = os.path.join(HOOKS_DIR, filename)
    with open(hooks_filepath, "w", encoding="utf-8") as f:
        f.write(hooks)
    print(f"[훅 저장 완료] {hooks_filepath}")

    log_to_sheets(keyword_data, filename, doc_url="")

    print("[완료] 블로그 글 생성 완료")

# ============================================
# 스케줄 설정
# ============================================

scheduler = BlockingScheduler()

# 월요일 오전 9시
scheduler.add_job(
    run_blog_generation,
    "cron",
    day_of_week="mon",
    hour=9,
    minute=0
)

# 목요일 오전 9시
scheduler.add_job(
    run_blog_generation,
    "cron",
    day_of_week="thu",
    hour=9,
    minute=0
)

# ============================================
# 실행
# ============================================

if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        # GitHub Actions: 한 번만 실행
        print("블로그 글 1회 생성 시작...")
        run_blog_generation()
    else:
        # 로컬: 스케줄러로 실행
        print("치과 블로그 자동 생성기 실행 중...")
        print("매주 월/목 오전 9시에 자동 생성됩니다.")
        run_blog_generation()
        scheduler.start()
