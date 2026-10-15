# -*- coding: utf-8 -*-
"""
퓨밍이 안전비서 문서 검색 엔진

주요 기능
- documents 폴더의 TXT 문서를 읽습니다.
- 한 TXT 파일에 여러 표준이 있으면 표준별로 분리합니다.
- 표준번호, 표준명, 조항, 본문을 검색합니다.
- 관련문서·첨부 목록에만 등장한 표준의 오검색을 방지합니다.
- 질문과 정확히 일치하는 문장을 우선 표시합니다.
- 클릭한 문장의 원문 위치를 찾기 위한 정보를 제공합니다.
"""

import html
import math
import os
import re


# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DOCUMENTS_DIR = os.path.join(
    BASE_DIR,
    "documents",
)

CHUNK_SIZE = 1800
CHUNK_OVERLAP = 180

MAX_SEARCH_RESULTS = 8
MAX_PER_STANDARD = 3
MAX_LOCAL_ANSWER_SOURCES = 4
MAX_UNITS_PER_SOURCE = 8

SOURCE_TYPE_INTERNAL = "internal"
SOURCE_TYPE_OFFICIAL_REFERENCE = "official_reference"

MAX_REFERENCE_SEARCH_RESULTS = 6
MAX_REFERENCE_ANSWER_SOURCES = 3
MAX_REFERENCE_UNITS_PER_SOURCE = 2
MAX_REFERENCE_EXCERPT_CHARS = 1400


# ============================================================
# 정규식
# ============================================================

STANDARD_CODE_PATTERN = re.compile(
    "[A-Z]{2,5}(?:-[A-Z0-9]{1,5}){1,4}"
)

REV_PATTERN = re.compile(
    "(?:rev[.]?[ ]*|r)([0-9]{1,3})",
    re.IGNORECASE,
)

ROOT_ARTICLE_PATTERN = re.compile(
    "^[0-9]{1,2}[.][ ]+[^ ]"
)

DEEP_ARTICLE_PATTERN = re.compile(
    "^[0-9]{1,2}(?:[.][0-9]{1,2}){1,5}[ ]*"
)

SUB_ITEM_PATTERN = re.compile(
    "^(?:[0-9]{1,2}[)]|[(][0-9]{1,2}[)]|[①-⑳])[ ]*"
)

LEADING_LIST_NUMBER_PATTERN = re.compile(
    "^[0-9]{1,2}[.)][ ]*"
)

# 정리본 안에서 표준·장을 구분하는 「번호. 제목」 머리글입니다.
SECTION_NUMBER_PATTERN = re.compile(
    "^([0-9]{1,3})[.][ ]+([^ ].*)$"
)

PAGE_OPEN_PATTERN = re.compile(
    "<page-([0-9]+)>",
    re.IGNORECASE,
)

PAGE_CLOSE_PATTERN = re.compile(
    "</page-[0-9]+>",
    re.IGNORECASE,
)

DOCUMENT_OPEN_PATTERN = re.compile(
    '<document[ ]+name="([^"]+)">',
    re.IGNORECASE,
)

DOCUMENT_CLOSE_PATTERN = re.compile(
    "</document>",
    re.IGNORECASE,
)

SOURCE_METADATA_PATTERN = re.compile(
    "(?is)<source-metadata>(.*?)</source-metadata>"
)

PAGE_HEADING_PATTERN = re.compile(
    "^\\[페이지[ ]+([0-9]+)\\]$"
)

REFERENCE_QUESTION_PREFIX_PATTERN = re.compile(
    "^(?:(?:Q|Ｑ)[ ]*[0-9]*[ ]*)?(?:질[ ]*의|질[ ]*문)[ ]*[:：]?[ ]*",
    re.IGNORECASE,
)

REFERENCE_ANSWER_PREFIX_PATTERN = re.compile(
    "^(?:(?:A|Ａ)[ ]*[0-9]*[ ]*)?(?:회[ ]*시|답[ ]*변)[ ]*[:：]?[ ]*",
    re.IGNORECASE,
)

IMPORTANCE_PATTERN = re.compile(
    "하여야|해야|금지|필수|반드시|이상|이하|초과|미만|"
    "준수|확인|점검|착용|측정|기준|의무|보고|승인|"
    "허가|즉시|중지|주기|보존|책임|대피|발령|"
    "교육|검토|기록|관리|계상|사용 가능|사용할 수"
)

DIVIDER_CHARS = set(
    "=-–—─━_~*#＝"
)

# 문서 마커를 표준 경계로 바꿀 때 사용하는 구분선입니다.
SECTION_DIVIDER_LINE = "=" * 80

# 표준 헤더가 제목과 표준번호로 줄바꿈되는 경우가 있어
# 구분선 사이의 이 줄 수까지 이어붙여 헤더로 읽습니다.
MAX_HEADER_LINES = 2


# ============================================================
# 검색 제외 설정
# ============================================================

# 표준번호 없는 통합 색인·정리 장을 표시할 때 쓰는 이름입니다.
UNNUMBERED_SECTION_LABEL = "정리본 통합 장"

# 챗봇 운영 지시만 담긴 장은 안전 근거가 아니라 검색에서 제외합니다.
CHATBOT_META_SECTION_TITLES = (
    "안전 챗봇 답변 생성 원칙",
    "작업상황별 챗봇 질의어 연결 사전",
    "챗봇 답변 시 근거문서 표기 예시",
)

REFERENCE_SECTION_MARKERS = (
    "관련문서",
    "관련 문서",
    "관련표준",
    "관련 표준",
    "별첨문서",
    "첨부",
    "서식no",
    "서식 no",
)

UNNECESSARY_DISPLAY_PREFIXES = (
    "관련문서",
    "관련 문서",
    "관련표준",
    "관련 표준",
    "별첨문서",
    "서식no",
    "서식 no",
    "총 0건",
)

REFERENCE_GENERIC_QUERY_TERMS = {
    "관련",
    "내용",
    "경우",
    "규정",
    "법령",
    "기준",
    "가능",
    "사용",
    "사용할",
    "구입비",
    "적용",
    "업무",
    "방법",
    "점검",
    "주기",
    "이상",
    "안전관리비",
    "산업안전보건관리비",
}

# 해당 키워드를 질문하지 않으면 문서 전체를 검색 결과에서 제외합니다.
CONDITIONAL_DOCUMENT_RULES = {
    # 일반 '안전관리자'와 법적 성격이 다른 전문 직책을 구분합니다.
    "PCR-M-131": (
        "소방",
        "화재",
        "소화",
        "방화",
        "스프링클러",
        "경보설비",
        "피난",
    ),

    "PCR-M-141": (
        "가스",
        "고압가스",
        "도시가스",
        "액화석유가스",
        "lpg",
        "lng",
    ),

    # 방사선 관련 질문이 아니면 방사선안전관리 규정을 제외합니다.
    "PCR-M-161": (
        "방사선",
        "방사선량",
        "방사성",
        "비파괴검사",
        "비파괴 검사",
    ),

    # 건강진단·보건 관련 질문이 아니면 건강진단관리 지침을 제외합니다.
    "PCI-00-0GN-201": (
        "건강진단",
        "건강 진단",
        "특수건강진단",
        "특수 건강진단",
        "일반건강진단",
        "배치전건강진단",
        "수시건강진단",
        "건강관리",
        "건강 관리",
        "유소견자",
        "직업병",
        "보건관리",
    ),
}


# ============================================================
# 불용어
# ============================================================

STOPWORDS = {
    "그리고",
    "그러나",
    "또는",
    "하지만",
    "때문에",
    "위하여",
    "위한",
    "대한",
    "관한",
    "있는",
    "있다",
    "없다",
    "합니다",
    "해야",
    "하는",
    "무엇",
    "어떻게",
    "얼마",
    "알려줘",
    "알려",
    "주세요",
    "설명",
    "설명해줘",
    "설명해주세요",
    "의미",
    "경우",
    "때는",
    "관련",
    "대해",
    "대하여",
    "내용",
    "검색",
    "문의",
    "해줘",
    "해주세요",
    "되나요",
    "됩니까",
    "인가요",
    "있나요",
    "궁금해",
    "궁금합니다",
}


# ============================================================
# 안전·환경 개념어
# ============================================================

SAFETY_CONCEPTS = {
    "밀폐공간": [
        "밀폐공간",
        "밀폐 공간",
        "산소농도",
        "산소 농도",
        "적정공기",
        "질식",
        "유해가스",
        "밀폐공간감시인",
    ],
    "화기작업": [
        "화기작업",
        "화기 작업",
        "용접",
        "용단",
        "불티",
        "화재감시자",
        "방화포",
    ],
    "소방훈련": [
        "소방훈련",
        "소방 훈련",
        "화재훈련",
        "화재 훈련",
        "비상훈련",
        "비상 훈련",
        "대피훈련",
        "대피 훈련",
        "소화훈련",
        "소화 훈련",
    ],
    "고소작업": [
        "고소작업",
        "고소 작업",
        "안전대",
        "추락",
        "떨어짐",
        "작업발판",
        "비계",
        "개구부",
    ],
    "전기작업": [
        "정전작업",
        "정전 작업",
        "전기작업",
        "전기 작업",
        "검전",
        "활선",
        "전원차단",
        "전원 차단",
        "감전",
        "절연",
        "접지",
    ],
    "중량물": [
        "중량물",
        "크레인",
        "양중",
        "지게차",
        "작업반경",
        "작업 반경",
        "줄걸이",
        "중량물 표시",
        "중량물 표지",
        "경고표지",
        "안내표시",
        "취급주의 표지",
        "무게중심",
    ],
    "안전보호구": [
        "보호구",
        "안전모",
        "안전화",
        "보안경",
        "방한장갑",
        "방한 장갑",
        "안전장갑",
        "안전 장갑",
        "보호장갑",
        "보호 장갑",
        "방진마스크",
        "방독마스크",
    ],
    "안전관리비": [
        "안전관리비",
        "안전 관리비",
        "산업안전보건관리비",
        "산업안전보건 관리비",
        "계상",
        "사용가능",
        "사용 가능",
        "사용기준",
        "사용 기준",
    ],
    "작업중지권": [
        "작업중지권",
        "작업중지",
        "작업 중지",
        "급박한 위험",
    ],
    "TBM": [
        "tbm",
        "tool box meeting",
        "위험예지",
        "작업 전 회의",
    ],
    "ILS": [
        "ils",
        "isolation locking system",
        "에너지원 차단",
        "잠금",
    ],
    "안전교육": [
        "안전교육",
        "안전 교육",
        "안전보건교육",
        "안전보건 교육",
        "특별교육",
        "정기교육",
        "채용 시 교육",
        "출입자 교육",
    ],
    "위험성평가": [
        "위험성평가",
        "위험성 평가",
        "유해위험요인",
        "유해·위험요인",
        "감소대책",
        "허용 불가능",
        "작업안전분석",
        "jsa",
    ],
    "리스크기회": [
        "리스크",
        "기회",
        "심각도",
        "발생도",
        "영향도",
        "핵심 리스크",
    ],
    "환경영향평가": [
        "환경영향평가",
        "환경영향 평가",
        "환경측면",
        "중요등록부",
        "중요 환경측면",
        "환경영향",
    ],
    "법규준수": [
        "법규등록부",
        "준수평가",
        "준수 평가",
        "준수 의무",
        "법적 요구사항",
        "법규",
    ],
    "목표관리": [
        "세부목표",
        "추진계획",
        "경영방침",
        "성과측정",
    ],
    "의사소통": [
        "의사소통",
        "산업안전보건위원회",
        "안전신문고",
        "협의체",
        "민원",
    ],
    "문서관리": [
        "문서관리",
        "문서 관리",
        "제개정",
        "제·개정",
        "승인권자",
        "사규관리",
    ],
    "비상상황": [
        "비상상황",
        "비상 상황",
        "상황본부",
        "상황반",
        "비상근무",
        "a급",
        "b급",
        "c급",
    ],
    "풍수해": [
        "풍수해",
        "태풍",
        "호우",
        "대설",
        "지진",
        "침수",
    ],
    "누출대응": [
        "누출",
        "중화",
        "흡착포",
        "방재",
        "유해화학물질 누출",
    ],
    "응급처치": [
        "응급처치",
        "심폐소생",
        "aed",
        "지혈",
        "인공호흡",
        "화상",
    ],
    "내부심사": [
        "내부심사",
        "내부 심사",
        "심사원",
        "체크리스트",
        "중부적합",
        "경부적합",
        "권고사항",
    ],
    "경영검토": [
        "경영검토",
        "경영 검토",
        "특별 경영검토",
        "정기 경영검토",
    ],
    "시정조치": [
        "시정조치",
        "시정 조치",
        "예방조치",
        "부적합",
        "재발방지",
        "시정조치요구서",
    ],
    "재해조사": [
        "재해조사",
        "재해 조사",
        "재해속보",
        "trifr",
        "ltifr",
        "수평전개",
        "산업재해조사표",
    ],
    "방사선": [
        "방사선",
        "방사선안전",
        "방사선량",
        "비파괴검사",
        "비파괴 검사",
        "방사성",
    ],
}


# ============================================================
# 질문 유형
# ============================================================

GREETING_WORDS = (
    "안녕",
    "안녕하세요",
    "반가워",
    "반갑습니다",
    "좋은아침",
    "좋은 아침",
    "수고",
    "고마워",
    "감사합니다",
    "감사해요",
    "ㅎㅎ",
    "ㅋㅋ",
)

INTERNAL_DOCUMENT_WORDS = (
    "사내",
    "회사",
    "포스코퓨처엠",
    "규정",
    "프로세스",
    "지침",
    "표준",
    "절차",
    "책임",
    "권한",
    "보존",
    "주기",
    "교육시간",
    "교육 시간",
    "안전철칙",
    "작업허가",
    "작업중지권",
    "위험성평가",
    "재해조사",
    "경영검토",
    "내부심사",
    "안전관리비",
    "산업안전보건관리비",
    "산업안전보건법",
    "산업안전보건기준에 관한 규칙",
    "물질안전보건자료",
    "MSDS",
    "질의회시",
    "질의 회시",
    "중대재해처벌법",
    "중대재해 처벌법",
    "대기환경보전법",
    "물환경보전법",
    "화학물질관리법",
    "시행령",
    "시행규칙",
    "법령",
)


def is_greeting(question):
    text = compact_text(
        question
    ).lower()

    if not text:
        return False

    if len(text) > 30:
        return False

    for word in GREETING_WORDS:
        if word in text:
            return True

    return False


def greeting_answer(question):
    text = (
        question or ""
    ).strip()

    if (
        "고마" in text
        or "감사" in text
    ):
        return (
            "### 퓨밍이\n\n"
            "도움이 되었다니 기쁩니다.\n\n"
            "오늘도 안전하게 작업하세요!"
        )

    if "수고" in text:
        return (
            "### 퓨밍이\n\n"
            "감사합니다.\n\n"
            "안전하고 편안한 하루 보내세요!"
        )

    if (
        "ㅎㅎ" in text
        or "ㅋㅋ" in text
    ):
        return (
            "### 퓨밍이\n\n"
            "네, 함께 안전하게 일해요! 😊"
        )

    return (
        "### 안녕하세요!\n\n"
        "안전요정 퓨밍이입니다.\n\n"
        "사내 안전·환경 기준, 법규, 질의회시와 교육자료를 찾아드릴게요."
    )


def looks_like_document_question(question):
    text = (
        question or ""
    ).lower()

    if STANDARD_CODE_PATTERN.search(
        text.upper()
    ):
        return True

    if detect_concepts(question):
        return True

    for word in INTERNAL_DOCUMENT_WORDS:
        if word.lower() in text:
            return True

    return False


# ============================================================
# 텍스트 정리
# ============================================================

def compact_text(text):
    return " ".join(
        (text or "").split()
    )


def build_source_label(number):
    return "[근거 " + str(number) + "]"


def normalize_code_token(text):
    return re.sub(
        "[^0-9a-z]",
        "",
        (text or "").lower(),
    )


def is_divider_line(line):
    text = (
        line or ""
    ).strip()

    if len(text) < 8:
        return False

    for character in text:
        if character not in DIVIDER_CHARS:
            return False

    return True


def starts_with_bracket_title(line):
    text = (
        line or ""
    ).strip()

    if not text.startswith("["):
        return False

    closing_position = text.find(
        "]"
    )

    return (
        1
        < closing_position
        <= 100
    )


def clean_title_number(title):
    text = (
        title or ""
    ).strip()

    text = LEADING_LIST_NUMBER_PATTERN.sub(
        "",
        text,
    )

    return text.strip(
        " -–—·"
    )


def normalize_text(raw):
    text = raw or ""

    text = text.replace(
        "\r\n",
        "\n",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    text = re.sub(
        "(?is)<script.*?</script>",
        " ",
        text,
    )

    text = re.sub(
        "(?is)<style.*?</style>",
        " ",
        text,
    )

    text = re.sub(
        "(?i)<br[ ]*/?>",
        "\n",
        text,
    )

    text = re.sub(
        "(?i)</p>",
        "\n\n",
        text,
    )

    text = re.sub(
        "(?i)</tr>",
        "\n",
        text,
    )

    text = re.sub(
        "(?i)</t[dh]>",
        " | ",
        text,
    )

    text = re.sub(
        "(?i)</table>",
        "\n\n",
        text,
    )

    text = PAGE_OPEN_PATTERN.sub(
        lambda match: (
            "\n[페이지 "
            + match.group(1)
            + "]\n"
        ),
        text,
    )

    text = PAGE_CLOSE_PATTERN.sub(
        "\n",
        text,
    )

    # 표준명과 표준번호가 함께 든 문서 마커는 표준 경계이므로
    # 구분선으로 감싸 split_standard_sections 가 헤더로 읽게 합니다.
    text = DOCUMENT_OPEN_PATTERN.sub(
        lambda match: (
            "\n"
            + SECTION_DIVIDER_LINE
            + "\n"
            + match.group(1)
            + "\n"
            + SECTION_DIVIDER_LINE
            + "\n"
        ),
        text,
    )

    text = DOCUMENT_CLOSE_PATTERN.sub(
        "\n",
        text,
    )

    text = re.sub(
        "<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(
        text
    )

    text = text.replace(
        "\u00a0",
        " ",
    )

    text = text.replace(
        "\t",
        "  ",
    )

    output = []

    for raw_line in text.split(
        "\n"
    ):
        line = raw_line.rstrip()

        if not line.strip():
            output.append("")
            continue

        indentation = (
            len(line)
            - len(
                line.lstrip(" ")
            )
        )

        body = re.sub(
            "[ ]{3,}",
            "  ",
            line.strip(),
        )

        output.append(
            " " * min(
                indentation,
                6,
            )
            + body
        )

    result = "\n".join(
        output
    )

    result = re.sub(
        "\n{3,}",
        "\n\n",
        result,
    )

    return result.strip()


# ============================================================
# 검색 토큰
# ============================================================

def tokenize(text):
    source = text or ""
    tokens = []

    for match in STANDARD_CODE_PATTERN.finditer(
        source.upper()
    ):
        standard_code = match.group(0)

        compact_code = normalize_code_token(
            standard_code
        )

        if compact_code:
            tokens.append(
                compact_code
            )

        for number in re.findall(
            "[0-9]{3}",
            standard_code,
        ):
            tokens.append(
                number
            )

    words = re.findall(
        "[0-9a-z가-힣]+",
        source.lower(),
    )

    for word in words:
        if len(word) < 2:
            continue

        if word in STOPWORDS:
            continue

        tokens.append(
            word
        )

        if (
            re.fullmatch(
                "[가-힣]+",
                word,
            )
            and len(word) >= 4
        ):
            for start in range(
                len(word) - 1
            ):
                tokens.append(
                    word[
                        start:
                        start + 2
                    ]
                )

            if len(word) >= 5:
                for start in range(
                    len(word) - 2
                ):
                    tokens.append(
                        word[
                            start:
                            start + 3
                        ]
                    )

    return tokens


def meaningful_query_words(question):
    output = []
    seen = set()

    for variant in query_variants(question):
        words = re.findall(
            "[0-9A-Za-z가-힣%]+",
            variant,
        )

        for word in words:
            lowered = word.lower()

            if len(lowered) < 2:
                continue

            if lowered in STOPWORDS:
                continue

            if lowered in seen:
                continue

            seen.add(lowered)
            output.append(lowered)

    return output


# 질문에서 표현이 달라도 같은 법적·안전보건 개념으로 검색되도록
# 동의어를 확장합니다. 원문에 없는 표현을 답변에 만들어 내는 것이 아니라,
# 색인 검색 후보와 화면 강조 대상만 넓히는 용도입니다.
QUERY_SYNONYM_GROUPS = (
    (
        (
            "중량물",
            "중량물 표지",
            "중량물 표시",
            "중량물 경고표지",
            "중량물 안내표시",
            "경고표지",
            "안내표시",
            "취급주의 표지",
        ),
        (
            "중량물",
            "중량물 표지",
            "중량물 표시",
            "경고표지",
            "안내표시",
            "취급주의 표지",
            "무게",
            "무게중심",
            "5kg",
        ),
    ),
)


def query_variants(question):
    text = compact_text(question)
    lowered = text.lower()
    variants = [text] if text else []

    for triggers, additions in QUERY_SYNONYM_GROUPS:
        if not any(
            trigger.lower() in lowered
            for trigger in triggers
        ):
            continue

        variants.extend(additions)

    unique = []

    for variant in variants:
        value = compact_text(variant)

        if value and value.lower() not in {
            item.lower()
            for item in unique
        }:
            unique.append(value)

    return unique


def detect_concepts(question):
    lowered = (
        question or ""
    ).lower()

    found = []

    for concept, keywords in SAFETY_CONCEPTS.items():
        for keyword in keywords:
            if keyword.lower() in lowered:
                found.append(
                    concept
                )
                break

    return found


def concept_matches(
    concept,
    text,
):
    lowered = (
        text or ""
    ).lower()

    for keyword in SAFETY_CONCEPTS.get(
        concept,
        [],
    ):
        if keyword.lower() in lowered:
            return True

    return False


# ============================================================
# 파일 읽기
# ============================================================

def read_text_file(
    path,
    errors,
):
    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp949",
        "euc-kr",
    ]

    for encoding in encodings:
        try:
            with open(
                path,
                "r",
                encoding=encoding,
            ) as handle:
                return handle.read()

        except UnicodeDecodeError:
            continue

        except OSError as error:
            errors.append(
                os.path.basename(path)
                + ": "
                + str(error)
            )

            return None

    errors.append(
        os.path.basename(path)
        + ": 글자 인코딩을 확인해 주세요."
    )

    return None


def parse_source_metadata(
    raw_text,
    fallback_title,
):
    metadata = {
        "source_type": SOURCE_TYPE_INTERNAL,
        "source_category": "사내 표준",
        "source_title": fallback_title,
        "publisher": "포스코퓨처엠",
        "published_at": "",
        "original_file": "",
    }

    match = SOURCE_METADATA_PATTERN.search(
        raw_text or ""
    )

    if match is None:
        return (
            metadata,
            raw_text or "",
        )

    supported_keys = {
        "type": "source_type",
        "category": "source_category",
        "title": "source_title",
        "publisher": "publisher",
        "published_at": "published_at",
        "original_file": "original_file",
    }

    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()

        if "=" not in line:
            continue

        key, value = line.split(
            "=",
            1,
        )

        metadata_key = supported_keys.get(
            key.strip().lower()
        )

        if metadata_key is None:
            continue

        cleaned_value = value.strip()

        if cleaned_value:
            metadata[metadata_key] = (
                cleaned_value
            )

    cleaned_text = SOURCE_METADATA_PATTERN.sub(
        "",
        raw_text or "",
        count=1,
    )

    return (
        metadata,
        cleaned_text,
    )


def parse_file_metadata(
    file_name,
):
    base_name = os.path.splitext(
        os.path.basename(
            file_name
        )
    )[0]

    document_name = base_name.replace(
        "_",
        " ",
    )

    document_name = re.sub(
        "^[ ]*[0-9]{1,3}[ ]+",
        "",
        document_name,
    )

    document_name = re.sub(
        "[ ]+[0-9]{1,2}[ ]*$",
        "",
        document_name,
    )

    document_name = re.sub(
        "[ ]{2,}",
        " ",
        document_name,
    ).strip(
        " -·"
    )

    code_match = STANDARD_CODE_PATTERN.search(
        base_name.upper()
    )

    revision_match = REV_PATTERN.search(
        base_name
    )

    standard_number = (
        code_match.group(0)
        if code_match
        else ""
    )

    revision = (
        revision_match.group(1)
        if revision_match
        else ""
    )

    return (
        document_name or base_name,
        standard_number,
        revision,
    )


# ============================================================
# 표준 제목 및 표준별 분리
# ============================================================

def parse_standard_header(line):
    text = (
        line or ""
    ).strip()

    if not text:
        return None

    if len(text) > 180:
        return None

    code_match = STANDARD_CODE_PATTERN.search(
        text.upper()
    )

    if not code_match:
        return None

    revision_match = REV_PATTERN.search(
        text
    )

    if not revision_match:
        return None

    standard_code = code_match.group(0)

    code_position = text.upper().find(
        standard_code
    )

    if code_position <= 0:
        return None

    title = text[
        :code_position
    ].strip()

    title = title.rstrip(
        "([（, "
    )

    title = clean_title_number(
        title
    )

    if len(title) > 100:
        return None

    if len(
        re.findall(
            "[가-힣]",
            title,
        )
    ) < 2:
        return None

    blocked_prefixes = (
        "관련문서",
        "관련 문서",
        "관련표준",
        "관련 표준",
        "별첨문서",
        "첨부",
        "서식",
    )

    if title.startswith(
        blocked_prefixes
    ):
        return None

    return {
        "title": title,
        "code": standard_code,
        "revision": (
            revision_match.group(1)
        ),
    }


def strip_divider_lines(text):
    output = []

    for line in (
        text or ""
    ).splitlines():
        if is_divider_line(
            line
        ):
            continue

        output.append(
            line
        )

    result = "\n".join(
        output
    )

    result = re.sub(
        "\n{3,}",
        "\n\n",
        result,
    )

    return result.strip()


def infer_single_document_metadata(
    text,
    file_title,
    file_code,
    file_revision,
):
    document_name = file_title
    standard_number = file_code
    revision = file_revision

    for line in (
        text or ""
    ).splitlines():
        stripped = line.strip()

        if stripped.startswith(
            "표준명 "
        ):
            value = stripped[
                len("표준명 "):
            ].strip()

            if ">" in value:
                value = value.split(
                    ">"
                )[-1].strip()

            if value:
                document_name = value

        elif stripped.startswith(
            "표준번호 "
        ):
            code_match = STANDARD_CODE_PATTERN.search(
                stripped.upper()
            )

            revision_match = REV_PATTERN.search(
                stripped
            )

            if code_match:
                standard_number = (
                    code_match.group(0)
                )

            if revision_match:
                revision = (
                    revision_match.group(1)
                )

    return (
        document_name,
        standard_number,
        revision,
    )


def collect_divider_blocks(lines):
    """구분선 사이의 짧은 블록을 헤더 후보로 모읍니다."""
    divider_positions = [
        position
        for position, line in enumerate(
            lines
        )
        if is_divider_line(
            line
        )
    ]

    blocks = []

    for index, opening in enumerate(
        divider_positions
    ):
        if index + 1 >= len(
            divider_positions
        ):
            break

        closing = divider_positions[
            index + 1
        ]

        content_lines = [
            lines[inner].strip()
            for inner in range(
                opening + 1,
                closing,
            )
            if lines[inner].strip()
        ]

        if not content_lines:
            continue

        if len(content_lines) > MAX_HEADER_LINES:
            continue

        blocks.append({
            "start": opening,
            "end": closing,
            "text": " ".join(
                content_lines
            ),
        })

    return blocks


def split_standard_sections(
    text,
    file_title,
    file_code,
    file_revision,
):
    lines = (
        text or ""
    ).splitlines()

    candidates = []
    highest_number = 0

    for block in collect_divider_blocks(
        lines
    ):
        number_match = SECTION_NUMBER_PATTERN.match(
            block["text"]
        )

        if number_match is None:
            section_number = None
        else:
            section_number = int(
                number_match.group(1)
            )

        # 정리본은 표준·장을 1부터 오름차순으로 붙이므로
        # 번호가 되돌아가면 본문 안의 조항 번호입니다.
        if (
            section_number is not None
            and section_number <= highest_number
        ):
            continue

        header = parse_standard_header(
            block["text"]
        )

        if header is None:
            if number_match is None:
                continue

            # 표준번호가 없는 장도 앞 표준에 섞이지 않게 경계로 둡니다.
            header = {
                "title": clean_title_number(
                    number_match.group(2)
                ),
                "code": "",
                "revision": "",
            }

        if section_number is not None:
            highest_number = section_number

        candidates.append(
            (
                block["end"],
                header,
            )
        )

    if not candidates:
        (
            name,
            code,
            revision,
        ) = infer_single_document_metadata(
            text,
            file_title,
            file_code,
            file_revision,
        )

        return [{
            "title": name,
            "code": code,
            "revision": revision,
            "text": strip_divider_lines(
                text
            ),
        }]

    unique_candidates = candidates

    positions = [
        position
        for position, header
        in unique_candidates
    ]

    boundaries = (
        positions[1:]
        + [len(lines)]
    )

    sections = []

    for index, candidate in enumerate(
        unique_candidates
    ):
        position, header = candidate

        body = "\n".join(
            lines[
                position:
                boundaries[index]
            ]
        )

        body = strip_divider_lines(
            body
        )

        if not body:
            continue

        sections.append({
            "title": header["title"],
            "code": header["code"],
            "revision": header["revision"],
            "text": body,
        })

    return sections


# ============================================================
# 조항 및 문서 조각
# ============================================================

def is_article_heading(line):
    text = (
        line or ""
    ).strip()

    if not text:
        return False

    if starts_with_bracket_title(
        text
    ):
        return True

    if ROOT_ARTICLE_PATTERN.match(
        text
    ):
        return True

    return False


def guess_section(text):
    for line in (
        text or ""
    ).splitlines():
        stripped = line.strip()

        if not stripped:
            continue

        if len(stripped) > 100:
            continue

        if starts_with_bracket_title(
            stripped
        ):
            return stripped

        if ROOT_ARTICLE_PATTERN.match(
            stripped
        ):
            return stripped

        if DEEP_ARTICLE_PATTERN.match(
            stripped
        ):
            return stripped

    return ""


def guess_page_number(
    text,
    fallback,
):
    for line in (
        text or ""
    ).splitlines():
        match = PAGE_HEADING_PATTERN.match(
            line.strip()
        )

        if match is not None:
            return int(
                match.group(1)
            )

    return fallback


def split_article_blocks(text):
    blocks = []
    current = []

    for line in (
        text or ""
    ).splitlines():
        stripped = line.strip()

        if (
            is_article_heading(
                stripped
            )
            and current
        ):
            block = "\n".join(
                current
            ).strip()

            if block:
                blocks.append(
                    block
                )

            current = [line]
        else:
            current.append(
                line
            )

    if current:
        block = "\n".join(
            current
        ).strip()

        if block:
            blocks.append(
                block
            )

    return blocks


def split_long_text(text):
    parts = []
    start = 0

    step = max(
        1,
        CHUNK_SIZE
        - CHUNK_OVERLAP,
    )

    while start < len(text):
        parts.append(
            text[
                start:
                start + CHUNK_SIZE
            ]
        )

        start += step

    return parts


def split_into_chunks(text):
    article_blocks = split_article_blocks(
        text
    )

    pieces = []

    for block in article_blocks:
        if len(block) <= CHUNK_SIZE:
            pieces.append(
                block
            )
        else:
            pieces.extend(
                split_long_text(
                    block
                )
            )

    chunks = []
    current = ""

    for piece in pieces:
        if current:
            candidate = (
                current
                + "\n\n"
                + piece
            )
        else:
            candidate = piece

        if len(candidate) <= CHUNK_SIZE:
            current = candidate
            continue

        if current:
            chunks.append(
                current
            )

        current = piece

    if current:
        chunks.append(
            current
        )

    return [
        chunk.strip()
        for chunk in chunks
        if chunk.strip()
    ]


def split_reference_pages(text):
    source = (
        text or ""
    ).strip()

    if not source:
        return []

    page_starts = [
        match.start()
        for match in re.finditer(
            "(?m)^\\[페이지[ ]+[0-9]+\\]$",
            source,
        )
    ]

    if not page_starts:
        return split_into_chunks(
            source
        )

    page_ends = (
        page_starts[1:]
        + [len(source)]
    )

    chunks = []

    for start, end in zip(
        page_starts,
        page_ends,
    ):
        page_text = source[
            start:end
        ].strip()

        if len(page_text) <= CHUNK_SIZE:
            chunks.append(
                page_text
            )
            continue

        heading = page_text.splitlines()[0]

        for piece in split_long_text(
            page_text
        ):
            if not piece.startswith(
                heading
            ):
                piece = (
                    heading
                    + "\n"
                    + piece
                )

            chunks.append(
                piece
            )

    return chunks


# ============================================================
# 색인 생성
# ============================================================

def build_index(chunks):
    index = {}

    for position, chunk in enumerate(
        chunks
    ):
        unique_tokens = set(
            chunk.get(
                "tokens",
                [],
            )
        )

        for token in unique_tokens:
            if token not in index:
                index[token] = []

            index[token].append(
                position
            )

    return index


def load_documents_with_index(
    documents_dir=DOCUMENTS_DIR,
):
    chunks = []
    errors = []

    if not os.path.isdir(
        documents_dir
    ):
        errors.append(
            "documents 폴더를 찾지 못했습니다."
        )

        return (
            chunks,
            {},
            errors,
        )

    file_names = sorted([
        file_name
        for file_name in os.listdir(
            documents_dir
        )
        if file_name.lower().endswith(
            ".txt"
        )
    ])

    if not file_names:
        errors.append(
            "documents 폴더에 TXT 문서가 없습니다."
        )

    for file_name in file_names:
        file_path = os.path.join(
            documents_dir,
            file_name,
        )

        raw_text = read_text_file(
            file_path,
            errors,
        )

        if raw_text is None:
            continue

        (
            file_title,
            file_code,
            file_revision,
        ) = parse_file_metadata(
            file_name
        )

        (
            source_metadata,
            raw_text,
        ) = parse_source_metadata(
            raw_text,
            file_title,
        )

        file_title = source_metadata.get(
            "source_title",
            file_title,
        ) or file_title

        normalized_text = normalize_text(
            raw_text
        )

        if not normalized_text:
            errors.append(
                file_name
                + ": 문서 내용이 비어 있습니다."
            )

            continue
        if source_metadata.get(
            "source_type"
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE:
            sections = [{
                "title": file_title,
                "code": "",
                "revision": "",
                "text": normalized_text,
            }]
        else:
            sections = split_standard_sections(
                normalized_text,
                file_title,
                file_code,
                file_revision,
            )

        for section in sections:
            standard_name = (
                section.get(
                    "title",
                    "",
                )
                or file_title
                or file_name
            )

            standard_number = (
                section.get(
                    "code",
                    "",
                )
                or file_code
                or ""
            )

            revision = (
                section.get(
                    "revision",
                    "",
                )
                or file_revision
                or ""
            )

            section_text = (
                section.get(
                    "text",
                    "",
                )
                or ""
            ).strip()

            if not section_text:
                continue

            if source_metadata.get(
                "source_type"
            ) == SOURCE_TYPE_OFFICIAL_REFERENCE:
                pieces = split_reference_pages(
                    section_text
                )
            else:
                pieces = split_into_chunks(
                    section_text
                )

            if not pieces:
                pieces = [
                    section_text
                ]

            for order, piece in enumerate(
                pieces,
                start=1,
            ):
                token_source = (
                    standard_name
                    + " "
                    + standard_number
                    + " "
                    + piece
                )

                chunks.append({
                    "document_name": standard_name,
                    "standard_name": standard_name,
                    "file_name": file_name,
                    "standard_number": standard_number,
                    "revision": revision,
                    "source_type": source_metadata.get(
                        "source_type",
                        SOURCE_TYPE_INTERNAL,
                    ),
                    "source_category": source_metadata.get(
                        "source_category",
                        "사내 표준",
                    ),
                    "publisher": source_metadata.get(
                        "publisher",
                        "",
                    ),
                    "published_at": source_metadata.get(
                        "published_at",
                        "",
                    ),
                    "original_file": source_metadata.get(
                        "original_file",
                        "",
                    ),
                    "page": guess_page_number(
                        piece,
                        order,
                    ),
                    "section": guess_section(
                        piece
                    ),
                    "text": piece,
                    "tokens": tokenize(
                        token_source
                    ),
                })

    index = build_index(
        chunks
    )

    standard_keys = set()
    reference_keys = set()

    for chunk in chunks:
        if chunk.get(
            "source_type",
            SOURCE_TYPE_INTERNAL,
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE:
            reference_keys.add(
                chunk.get(
                    "file_name",
                    "",
                )
            )
            continue

        standard_number = (
            chunk.get(
                "standard_number",
                "",
            )
        )

        if standard_number:
            standard_key = standard_number
        else:
            standard_key = (
                chunk.get(
                    "file_name",
                    "",
                )
                + "|"
                + chunk.get(
                    "standard_name",
                    "",
                )
            )

        standard_keys.add(
            standard_key
        )

    print(
        "[문서 분석] 파일 "
        + str(len(file_names))
        + "개 / 사내 표준 "
        + str(len(standard_keys))
        + "건 / 공식 참고자료 "
        + str(len(reference_keys))
        + "종 / 조각 "
        + str(len(chunks))
        + "개"
    )

    return (
        chunks,
        index,
        errors,
    )


# ============================================================
# 검색 제외 및 감점
# ============================================================

def document_is_allowed(
    question,
    chunk,
):
    standard_number = (
        chunk.get(
            "standard_number",
            "",
        )
        or ""
    ).upper()

    standard_name = (
        chunk.get(
            "standard_name",
            "",
        )
        or ""
    )

    # 챗봇 운영 지시 장은 안전 기준이 아니므로 근거로 쓰지 않습니다.
    if standard_name in CHATBOT_META_SECTION_TITLES:
        return False

    lowered_question = (
        question or ""
    ).lower()

    for (
        code,
        required_words,
    ) in CONDITIONAL_DOCUMENT_RULES.items():
        if standard_number != code:
            continue

        found_required_word = any(
            word.lower() in lowered_question
            for word in required_words
        )

        if not found_required_word:
            return False

    return True


def is_reference_only_unit(unit):
    text = (
        unit or ""
    ).strip()

    lowered = text.lower()

    if text.startswith(
        UNNECESSARY_DISPLAY_PREFIXES
    ):
        return True

    if len(text) <= 150:
        for marker in REFERENCE_SECTION_MARKERS:
            if marker in lowered:
                return True

    return False


def reference_section_penalty(chunk):
    section = (
        chunk.get(
            "section",
            "",
        )
        or ""
    ).lower()

    body = (
        chunk.get(
            "text",
            "",
        )
        or ""
    ).lower()

    penalty = 0.0

    for marker in REFERENCE_SECTION_MARKERS:
        if marker in section:
            penalty += 18.0

    lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
    ]

    if not lines:
        return penalty

    reference_count = 0

    for line in lines:
        if line.startswith(
            UNNECESSARY_DISPLAY_PREFIXES
        ):
            reference_count += 1
            continue

        if (
            STANDARD_CODE_PATTERN.search(
                line.upper()
            )
            and len(line) < 120
        ):
            reference_count += 1

    if (
        len(lines) <= 12
        and reference_count
        >= max(
            2,
            len(lines) // 2,
        )
    ):
        penalty += 12.0

    return penalty


def official_reference_penalty(chunk):
    if chunk.get(
        "source_type",
        SOURCE_TYPE_INTERNAL,
    ) != SOURCE_TYPE_OFFICIAL_REFERENCE:
        return 0.0

    body = chunk.get(
        "text",
        "",
    ) or ""

    lines = [
        compact_text(line)
        for line in body.splitlines()
        if compact_text(line)
    ]

    lowered = body.lower()
    penalty = 0.0

    if (
        "contents" in lowered
        or re.search(
            "(?:차[ ]*례|목[ ]*차)",
            body,
        )
    ):
        penalty += 100.0

    dotted_lines = sum(
        1
        for line in lines
        if re.search(
            "(?:[·.]{5,}|…{3,})",
            line,
        )
    )

    if dotted_lines >= 3:
        penalty += min(
            120.0,
            dotted_lines * 12.0,
        )

    return penalty


def normalize_reference_query_term(term):
    value = re.sub(
        "[^0-9a-z가-힣]",
        "",
        (term or "").lower(),
    )

    value = re.sub(
        "(?:으로|에서|에게|부터|까지|처럼|보다|이라|라고|"
        "이나|거나|은|는|이|가|을|를|의|에|와|과|도|로)$",
        "",
        value,
    )

    return value


def reference_has_query_evidence(
    question,
    chunk,
):
    if chunk.get(
        "source_type",
        SOURCE_TYPE_INTERNAL,
    ) != SOURCE_TYPE_OFFICIAL_REFERENCE:
        return True

    terms = []

    for word in meaningful_query_words(
        question
    ):
        term = normalize_reference_query_term(
            word
        )

        if len(term) < 2:
            continue

        if term in REFERENCE_GENERIC_QUERY_TERMS:
            continue

        if term not in terms:
            terms.append(
                term
            )

    if not terms:
        terms = [
            normalize_reference_query_term(
                word
            )
            for word in meaningful_query_words(
                question
            )
        ]

        terms = [
            term
            for term in terms
            if len(term) >= 2
        ]

    if not terms:
        return False

    body = re.sub(
        "[ ]+",
        "",
        compact_text(
            chunk.get(
                "text",
                "",
            )
        ).lower(),
    )

    matched_count = sum(
        1
        for term in terms
        if term in body
    )

    required_count = min(
        2,
        len(terms),
    )

    return matched_count >= required_count


# ============================================================
# 검색 점수 계산
# ============================================================

def exact_phrase_bonus(
    question,
    text,
):
    target_text = (
        text or ""
    ).lower()

    score = 0.0

    variants = query_variants(question)

    for index, variant in enumerate(variants):
        query_text = variant.lower()

        if len(query_text) < 3:
            continue

        if query_text not in target_text:
            continue

        score += 40.0 if index == 0 else 22.0

    query_words = meaningful_query_words(
        question
    )

    matched_word_count = 0

    for word in query_words:
        if word not in target_text:
            continue

        matched_word_count += 1

        if len(word) >= 6:
            score += 10.0

        elif len(word) >= 4:
            score += 6.0

        elif len(word) >= 3:
            score += 3.5

        else:
            score += 1.0

    if matched_word_count >= 2:
        score += (
            matched_word_count
            * 6.0
        )

    return score


def search_documents(
    question,
    chunks,
    index,
    limit=MAX_SEARCH_RESULTS,
    source_types=None,
):
    if not chunks:
        return []

    if source_types is None:
        allowed_source_types = {
            SOURCE_TYPE_INTERNAL,
        }
    elif isinstance(
        source_types,
        str,
    ):
        allowed_source_types = {
            source_types,
        }
    else:
        allowed_source_types = set(
            source_types
        )

    eligible_positions = {
        position
        for position, chunk in enumerate(
            chunks
        )
        if chunk.get(
            "source_type",
            SOURCE_TYPE_INTERNAL,
        ) in allowed_source_types
    }

    if not eligible_positions:
        return []

    question_tokens = set(
        tokenize(
            " ".join(
                query_variants(question)
            )
        )
    )

    total_count = len(
        eligible_positions
    )

    scores = {}

    for token in question_tokens:
        positions = [
            position
            for position in index.get(
                token,
                [],
            )
            if position in eligible_positions
        ]

        if not positions:
            continue

        weight = math.log(
            1.0
            + total_count
            / len(positions)
        )

        for position in positions:
            scores[position] = (
                scores.get(
                    position,
                    0.0,
                )
                + weight
            )

    concepts = detect_concepts(
        question
    )

    requested_codes = set()

    for match in STANDARD_CODE_PATTERN.finditer(
        (
            question or ""
        ).upper()
    ):
        requested_codes.add(
            normalize_code_token(
                match.group(0)
            )
        )

    requested_numbers = set(
        re.findall(
            "[0-9]{3}",
            question or "",
        )
    )

    for position, chunk in enumerate(
        chunks
    ):
        if position not in eligible_positions:
            scores.pop(
                position,
                None,
            )
            continue

        if not reference_has_query_evidence(
            question,
            chunk,
        ):
            scores.pop(
                position,
                None,
            )
            continue

        if not document_is_allowed(
            question,
            chunk,
        ):
            scores.pop(
                position,
                None,
            )
            continue

        body = chunk.get(
            "text",
            "",
        )

        standard_name = chunk.get(
            "standard_name",
            "",
        )

        standard_number = chunk.get(
            "standard_number",
            "",
        )

        compact_code = normalize_code_token(
            standard_number
        )

        score = scores.get(
            position,
            0.0,
        )

        score += exact_phrase_bonus(
            question,
            body,
        )

        for concept in concepts:
            if concept_matches(
                concept,
                body,
            ):
                score += 6.0

        for requested_code in requested_codes:
            if (
                requested_code
                and compact_code
                and (
                    requested_code in compact_code
                    or compact_code in requested_code
                )
            ):
                score += 40.0

        for number in requested_numbers:
            if (
                compact_code
                and compact_code.endswith(
                    number
                )
            ):
                score += 12.0

        name_overlap = len(
            question_tokens
            & set(
                tokenize(
                    standard_name
                )
            )
        )

        score += min(
            name_overlap * 3.5,
            14.0,
        )

        score -= reference_section_penalty(
            chunk
        )

        score -= official_reference_penalty(
            chunk
        )

        if score > 0:
            scores[position] = score
        else:
            scores.pop(
                position,
                None,
            )

    if not scores:
        return []

    ranked = sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    best_score = ranked[0][1]

    minimum_score = max(
        3.0,
        best_score * 0.30,
    )

    results = []
    standard_counts = {}

    for position, score in ranked:
        if score < minimum_score:
            continue

        chunk = chunks[
            position
        ]

        if not document_is_allowed(
            question,
            chunk,
        ):
            continue

        standard_key = (
            chunk.get(
                "standard_number",
                "",
            )
            or (
                chunk.get(
                    "file_name",
                    "",
                )
                + "|"
                + chunk.get(
                    "standard_name",
                    "",
                )
            )
        )

        count = standard_counts.get(
            standard_key,
            0,
        )

        if count >= MAX_PER_STANDARD:
            continue

        result = dict(
            chunk
        )

        result["score"] = round(
            score,
            3,
        )

        results.append(
            result
        )

        standard_counts[
            standard_key
        ] = count + 1

        if len(results) >= limit:
            break

    return results


def search_reference_documents(
    question,
    chunks,
    index,
    limit=MAX_REFERENCE_SEARCH_RESULTS,
):
    return search_documents(
        question,
        chunks,
        index,
        limit=limit,
        source_types=(
            SOURCE_TYPE_OFFICIAL_REFERENCE,
        ),
    )


# ============================================================
# 검색 단위 생성
# ============================================================

def split_search_units(text):
    source = (
        text or ""
    ).strip()

    if not source:
        return []

    source = source.replace(
        " · ",
        "\n",
    )

    source = source.replace(
        " ● ",
        "\n",
    )

    source = re.sub(
        " +(?=[0-9]{1,2}(?:[.][0-9]{1,2}){1,5}[ ])",
        "\n",
        source,
    )

    source = re.sub(
        " +(?=[0-9]{1,2}[)][ ])",
        "\n",
        source,
    )

    source = re.sub(
        " +(?=[(][0-9]{1,2}[)][ ])",
        "\n",
        source,
    )

    units = []

    for raw_line in source.splitlines():
        line = compact_text(
            raw_line
        )

        if not line:
            continue

        if is_reference_only_unit(
            line
        ):
            continue

        if len(line) <= 520:
            units.append(
                line
            )
            continue

        start = 0

        while start < len(line):
            end = min(
                start + 450,
                len(line),
            )

            if end < len(line):
                split_position = line.rfind(
                    " ",
                    start,
                    end,
                )

                if (
                    split_position
                    > start + 120
                ):
                    end = split_position

            fragment = line[
                start:end
            ].strip()

            if fragment:
                units.append(
                    fragment
                )

            start = end

    return units


def score_unit(
    question,
    question_tokens,
    concepts,
    unit,
):
    unit_tokens = set(
        tokenize(
            unit
        )
    )

    score = len(
        question_tokens
        & unit_tokens
    ) * 3.0

    score += exact_phrase_bonus(
        question,
        unit,
    )

    for concept in concepts:
        if concept_matches(
            concept,
            unit,
        ):
            score += 5.0

    if IMPORTANCE_PATTERN.search(
        unit
    ):
        score += 1.0

    if DEEP_ARTICLE_PATTERN.match(
        unit
    ):
        score += 1.5

    return score


def find_nearest_heading(
    units,
    position,
):
    for previous_position in range(
        position,
        -1,
        -1,
    ):
        value = units[
            previous_position
        ]

        if starts_with_bracket_title(
            value
        ):
            return value

        if ROOT_ARTICLE_PATTERN.match(
            value
        ):
            return value

        if DEEP_ARTICLE_PATTERN.match(
            value
        ):
            return value

    return ""


def extract_relevant_units(
    question,
    text,
    maximum=MAX_UNITS_PER_SOURCE,
):
    question_tokens = set(
        tokenize(
            " ".join(
                query_variants(question)
            )
        )
    )

    concepts = detect_concepts(
        question
    )

    units = split_search_units(
        text
    )

    scored_units = []

    for position, unit in enumerate(
        units
    ):
        score = score_unit(
            question,
            question_tokens,
            concepts,
            unit,
        )

        if score <= 2.0:
            continue

        scored_units.append({
            "score": score,
            "position": position,
            "text": unit,
            "heading": find_nearest_heading(
                units,
                position,
            ),
        })

    # 질문과 정확히 일치하는 문장이 가장 먼저 표시됩니다.
    scored_units.sort(
        key=lambda item: (
            item["score"],
            -item["position"],
        ),
        reverse=True,
    )

    selected = []
    seen = set()

    for item in scored_units:
        duplicate_key = compact_text(
            item["text"]
        )[:400]

        if duplicate_key in seen:
            continue

        seen.add(
            duplicate_key
        )

        selected.append(
            item
        )

        if len(selected) >= maximum:
            break

    return selected


def reference_line_kind(line):
    value = compact_text(
        line
    )

    if REFERENCE_QUESTION_PREFIX_PATTERN.match(
        value
    ):
        return "question"

    if REFERENCE_ANSWER_PREFIX_PATTERN.match(
        value
    ):
        return "answer"

    return ""


def split_reference_blocks(text):
    blocks = []
    current_lines = []
    current_heading = ""
    page_heading = ""

    for raw_line in (
        text or ""
    ).splitlines():
        line = compact_text(
            raw_line
        )

        if not line:
            continue

        if PAGE_HEADING_PATTERN.match(
            line
        ):
            page_heading = line
            continue

        kind = reference_line_kind(
            line
        )

        if kind == "question":
            if current_lines:
                blocks.append({
                    "heading": current_heading,
                    "lines": current_lines,
                })

            current_lines = [line]
            current_heading = page_heading
            continue

        if current_lines:
            current_lines.append(
                line
            )

    if current_lines:
        blocks.append({
            "heading": current_heading,
            "lines": current_lines,
        })

    return blocks


def format_reference_block(lines):
    question_lines = []
    answer_lines = []
    current_target = question_lines

    for line in lines:
        kind = reference_line_kind(
            line
        )

        if kind == "question":
            current_target = question_lines
            value = REFERENCE_QUESTION_PREFIX_PATTERN.sub(
                "",
                line,
                count=1,
            )

        elif kind == "answer":
            current_target = answer_lines
            value = REFERENCE_ANSWER_PREFIX_PATTERN.sub(
                "",
                line,
                count=1,
            )

        else:
            value = line

        if value:
            current_target.append(
                value
            )

    question_text = compact_text(
        " ".join(
            question_lines
        )
    )

    answer_text = compact_text(
        " ".join(
            answer_lines
        )
    )

    output = []

    if question_text:
        output.append(
            "질의: "
            + question_text
        )

    if answer_text:
        output.append(
            "회시·답변: "
            + answer_text
        )

    formatted = "\n".join(
        output
    )

    if len(formatted) > MAX_REFERENCE_EXCERPT_CHARS:
        formatted = (
            formatted[
                :MAX_REFERENCE_EXCERPT_CHARS
            ].rstrip()
            + "…"
        )

    return formatted


def extract_reference_units(
    question,
    text,
    maximum=MAX_REFERENCE_UNITS_PER_SOURCE,
):
    question_tokens = set(
        tokenize(
            " ".join(
                query_variants(question)
            )
        )
    )

    concepts = detect_concepts(
        question
    )

    candidates = []

    for block in split_reference_blocks(
        text
    ):
        formatted = format_reference_block(
            block.get(
                "lines",
                [],
            )
        )

        if not formatted:
            continue

        score = score_unit(
            question,
            question_tokens,
            concepts,
            formatted,
        )

        if score <= 2.0:
            continue

        focus_text = max(
            block.get(
                "lines",
                [formatted],
            ),
            key=lambda line: score_unit(
                question,
                question_tokens,
                concepts,
                line,
            ),
        )

        candidates.append({
            "score": score,
            "text": formatted,
            "focus_text": focus_text,
            "heading": block.get(
                "heading",
                "",
            ),
        })

    if not candidates:
        for item in extract_relevant_units(
            question,
            text,
            maximum=maximum,
        ):
            candidates.append({
                "score": item.get(
                    "score",
                    0.0,
                ),
                "text": item.get(
                    "text",
                    "",
                ),
                "focus_text": item.get(
                    "text",
                    "",
                ),
                "heading": item.get(
                    "heading",
                    "",
                ),
            })

    candidates.sort(
        key=lambda item: item.get(
            "score",
            0.0,
        ),
        reverse=True,
    )

    return candidates[:maximum]


# ============================================================
# 클릭 가능한 답변 묶음 생성
# ============================================================

def build_answer_bundle(
    question,
    results,
):
    bundle = {
        "title": "포스코퓨처엠 사내 표준에서 확인한 내용",
        "groups": [],
        "reference_title": "관련 질의회시·공식 자료에서 함께 확인한 내용",
        "reference_groups": [],
    }

    used_texts = set()
    group_dictionaries = {
        SOURCE_TYPE_INTERNAL: {},
        SOURCE_TYPE_OFFICIAL_REFERENCE: {},
    }

    for source_index, result in enumerate(
        results
    ):
        if not document_is_allowed(
            question,
            result,
        ):
            continue

        source_type = result.get(
            "source_type",
            SOURCE_TYPE_INTERNAL,
        )

        if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
            extracted_units = extract_reference_units(
                question,
                result.get(
                    "text",
                    "",
                ),
            )
            target_groups = bundle[
                "reference_groups"
            ]
        else:
            extracted_units = extract_relevant_units(
                question,
                result.get(
                    "text",
                    "",
                ),
            )
            target_groups = bundle[
                "groups"
            ]

        if not extracted_units:
            continue

        standard_name = (
            result.get(
                "standard_name",
                "",
            )
            or "표준명 미확인"
        )

        standard_number = (
            result.get(
                "standard_number",
                "",
            )
            or UNNUMBERED_SECTION_LABEL
        )

        revision = (
            result.get(
                "revision",
                "",
            )
            or ""
        )

        if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
            group_key = (
                result.get(
                    "file_name",
                    "",
                )
                + "|"
                + standard_name
            )
        else:
            group_key = (
                standard_number
                + "|"
                + standard_name
            )

        group_dictionary = group_dictionaries.setdefault(
            source_type,
            {},
        )

        if group_key not in group_dictionary:
            group = {
                "standard_name": standard_name,
                "standard_number": standard_number,
                "revision": revision,
                "source_type": source_type,
                "source_category": result.get(
                    "source_category",
                    "",
                ),
                "publisher": result.get(
                    "publisher",
                    "",
                ),
                "published_at": result.get(
                    "published_at",
                    "",
                ),
                "best_score": 0.0,
                "items": [],
            }

            group_dictionary[
                group_key
            ] = group

            target_groups.append(
                group
            )

        group = group_dictionary[
            group_key
        ]

        for extracted in extracted_units:
            if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
                unit_text = (
                    extracted.get(
                        "text",
                        "",
                    )
                    or ""
                ).strip()
            else:
                unit_text = compact_text(
                    extracted["text"]
                )

            duplicate_key = (
                source_type
                + "|"
                + group_key
                + "|"
                + unit_text[:400]
            )

            if duplicate_key in used_texts:
                continue

            used_texts.add(
                duplicate_key
            )

            item_score = float(
                extracted.get(
                    "score",
                    0.0,
                )
            )

            group["best_score"] = max(
                group["best_score"],
                item_score,
            )

            group["items"].append({
                "text": unit_text,
                "score": item_score,
                "source_index": source_index,
                "focus_text": (
                    extracted.get(
                        "focus_text",
                        "",
                    )
                    or unit_text
                ),
                "focus_heading": (
                    extracted.get(
                        "heading",
                        "",
                    )
                    or result.get(
                        "section",
                        "",
                    )
                ),
            })

    for group_key, maximum in (
        (
            "groups",
            MAX_LOCAL_ANSWER_SOURCES,
        ),
        (
            "reference_groups",
            MAX_REFERENCE_ANSWER_SOURCES,
        ),
    ):
        for group in bundle[group_key]:
            group["items"].sort(
                key=lambda item: item["score"],
                reverse=True,
            )

            if group_key == "reference_groups":
                group["items"] = group[
                    "items"
                ][:MAX_REFERENCE_UNITS_PER_SOURCE]

        bundle[group_key].sort(
            key=lambda group: group["best_score"],
            reverse=True,
        )

        bundle[group_key] = bundle[
            group_key
        ][:maximum]

    return bundle


# ============================================================
# 텍스트 형식 로컬 답변
# ============================================================

def local_answer(
    question,
    results,
):
    bundle = build_answer_bundle(
        question,
        results,
    )

    if not (
        bundle["groups"]
        or bundle["reference_groups"]
    ):
        return (
            "### 확인 결과\n\n"
            "질문과 직접 관련된 문서 문장을 찾지 못했습니다."
        )

    output = []

    if bundle["groups"]:
        output.extend([
            "### "
            + bundle["title"],
            "",
        ])

        for group in bundle["groups"]:
            output.extend([
                "#### "
                + group["standard_name"]
                + " ("
                + group["standard_number"]
                + ")",
                "",
            ])

            for item in group["items"]:
                output.extend([
                    "- "
                    + item["text"],
                    "",
                ])

    if bundle["reference_groups"]:
        output.extend([
            "### "
            + bundle["reference_title"],
            "",
        ])

        for group in bundle[
            "reference_groups"
        ]:
            output.extend([
                "#### "
                + group["standard_name"],
                "",
            ])

            for item in group["items"]:
                output.extend([
                    "- "
                    + item["text"].replace(
                        "\n",
                        "\n  ",
                    ),
                    "",
                ])

        output.extend([
            "※ 질의회시·해설은 발간 당시의 사실관계와 법령을 전제로 한 참고자료입니다. "
            "실제 적용 전 최신 법령·고시와 관할기관 해석을 확인해 주세요.",
            "",
        ])

    return "\n".join(
        output
    ).strip()
