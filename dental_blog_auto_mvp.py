# ============================================
# dental_blog_auto_mvp.py
# 치과 블로그 자동 생성 MVP
# ============================================

"""
기능
1. 치과 키워드 자동 선택
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

실행:
python dental_blog_auto_mvp.py
"""

import os
import random
from datetime import datetime

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

POSTS_DIR = "posts"

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

# ============================================
# 키워드 선택
# ============================================

def select_keyword():
    return random.choice(KEYWORDS)

# ============================================
# Claude 블로그 생성
# ============================================

def generate_blog_post(keyword_data):

    keyword = keyword_data["keyword"]

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
"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
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

def fetch_unsplash_image(query):
    """영문 쿼리로 Unsplash 이미지 검색 후 마크다운 반환"""

    access_key = os.getenv("UNSPLASH_ACCESS_KEY")

    try:
        response = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": query,
                "per_page": 1,
                "orientation": "landscape",
            },
            headers={"Authorization": f"Client-ID {access_key}"},
            timeout=10
        )
        data = response.json()
        results = data.get("results", [])

        if results:
            photo = results[0]
            image_url = photo["urls"]["regular"]
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
                    f"Translate this Korean dental blog heading into a short English search query "
                    f"for Unsplash (2-4 words only, no explanation, no punctuation):\n{heading_text}"
                )
            }
        ]
    )

    return response.content[0].text.strip()


def insert_images_after_subheadings(content):
    """## 소제목마다 이미지 검색 후 소제목 바로 아래에 삽입"""

    lines = content.split("\n")
    result = []

    for line in lines:
        result.append(line)

        if line.startswith("## "):
            heading_text = line[3:].strip()
            english_query = translate_heading_to_english(heading_text)
            print(f"[소제목 번역] {heading_text} → {english_query}")
            image_md = fetch_unsplash_image(english_query)
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
