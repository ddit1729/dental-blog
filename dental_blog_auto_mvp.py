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
pip install anthropic apscheduler python-dotenv requests

.env 파일 생성:
ANTHROPIC_API_KEY=your_api_key
UNSPLASH_ACCESS_KEY=your_unsplash_key
NAVER_CLIENT_ID=your_client_id
NAVER_CLIENT_SECRET=your_client_secret

실행:
python dental_blog_auto_mvp.py
"""

import json
import os
import random
from datetime import datetime, timedelta

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
import anthropic
from dotenv import load_dotenv

# ============================================
# 환경 설정
# ============================================

load_dotenv()

client = anthropic.Anthropic(
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTS_DIR = os.path.join(BASE_DIR, "posts")

if not os.path.exists(POSTS_DIR):
    os.makedirs(POSTS_DIR)

# ============================================
# 치과 키워드 DB
# ============================================

KEYWORDS = [
    {
        "keyword": "사랑니 발치 후 음식",
        "category": "관리"
    },
    {
        "keyword": "임플란트 통증 기간",
        "category": "시술"
    },
    {
        "keyword": "이가 시린 이유",
        "category": "증상"
    },
    {
        "keyword": "스케일링 후 식사",
        "category": "관리"
    },
    {
        "keyword": "충치 초기 증상",
        "category": "증상"
    },
    {
        "keyword": "교정 유지장치 세척",
        "category": "교정"
    },
    {
        "keyword": "신경치료 통증",
        "category": "시술"
    },
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

def select_keyword():
    """네이버 트렌드 기반으로 검색량 높은 키워드 선택. 실패 시 랜덤 선택."""

    scores = get_naver_trend_scores()

    if scores:
        best_keyword_name = max(scores, key=scores.get)
        best_score = scores[best_keyword_name]
        print(f"[트렌드 Top] {best_keyword_name} (점수: {best_score:.1f})")

        for kw in KEYWORDS:
            if kw["keyword"] == best_keyword_name:
                return kw

    print("[DataLab 실패] 랜덤 키워드 선택")
    return random.choice(KEYWORDS)

# ============================================
# Claude 블로그 생성
# ============================================

def load_recent_posts(n=2):
    """posts/ 폴더에서 참고예시*.md 전부 + 최근 자동생성 글 n개 읽기"""

    if not os.path.exists(POSTS_DIR):
        return []

    all_files = [f for f in os.listdir(POSTS_DIR) if f.endswith(".md")]

    # 참고예시로 시작하는 파일 전부
    reference_files = [f for f in all_files if f.startswith("참고예시")]

    # 나머지 최근 n개
    recent_files = sorted(
        [f for f in all_files if not f.startswith("참고예시")],
        reverse=True
    )[:n]

    posts = []
    for filename in reference_files + recent_files:
        filepath = os.path.join(POSTS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            posts.append(f.read())

    return posts


def generate_blog_post(keyword_data):

    keyword = keyword_data["keyword"]

    recent_posts = load_recent_posts(n=2)

    if recent_posts:
        reference_section = "\n\n참고 예시 (아래 글들의 문체와 구성 방식을 참고해서 써줘):\n"
        for i, post in enumerate(recent_posts, 1):
            reference_section += f"\n--- 예시 {i} ---\n{post[:1500]}\n"
    else:
        reference_section = ""

    prompt = f"""
너는 한국 치과 블로그 전문 작가다.

주제:
"{keyword}"

조건:
- 네이버 블로그 스타일
- 환자 눈높이 설명
- 과장 금지
- 광고 느낌 금지
- 의료광고법 위반 표현 금지
- 자연스러운 한국어
- 1800자 이상
- 소제목 포함
- FAQ 3개 포함
- 마크다운 형식
- 제목부터 작성

구조:
1. 제목
2. 도입부
3. 원인/설명
4. 관리 방법
5. 주의사항
6. FAQ
7. 마무리
{reference_section}"""

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


def insert_images_after_subheadings(content):
    """## 소제목마다 이미지 검색 후 소제목 바로 아래에 삽입 (중복 없음)"""

    lines = content.split("\n")
    result = []
    used_urls = set()

    for line in lines:
        result.append(line)

        if line.startswith("## "):
            heading_text = line[3:].strip()
            english_query = translate_heading_to_english(heading_text)
            print(f"[소제목 번역] {heading_text} → {english_query}")
            image_md = fetch_unsplash_image(english_query, used_urls)
            if image_md:
                result.append("")
                result.append(image_md)

    return "\n".join(result)

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

def save_markdown(keyword, content):

    date_str = datetime.now().strftime("%Y-%m-%d")

    safe_keyword = keyword.replace(" ", "-")

    filename = f"{date_str}-{safe_keyword}.md"

    filepath = os.path.join(POSTS_DIR, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[저장 완료] {filepath}")

# ============================================
# 전체 작업 실행
# ============================================

def run_blog_generation():

    print("=" * 50)
    print("치과 블로그 자동 생성 시작")
    print("=" * 50)

    keyword_data = select_keyword()

    print(f"[선택 키워드] {keyword_data['keyword']}")

    content = generate_blog_post(keyword_data)

    filtered_content = apply_medical_filter(content)

    final_content = insert_images_after_subheadings(filtered_content)

    save_markdown(
        keyword_data["keyword"],
        final_content
    )

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

    print("치과 블로그 자동 생성기 실행 중...")
    print("매주 월/목 오전 9시에 자동 생성됩니다.")

    # 테스트용 즉시 실행
    run_blog_generation()

    # 스케줄러 시작
    scheduler.start()
