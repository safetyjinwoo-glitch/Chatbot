# -*- coding: utf-8 -*-
"""
퓨밍이 안전비서 외부 서비스

기능
- 개인 P-GPT API 키 및 KOSHA API 키 저장
- PAI 로컬 게이트웨이를 통한 P-GPT 호출
- HTML 웹페이지가 AI 답변으로 출력되는 문제 차단
- 인사 및 일반 질문 P-GPT 답변
- KOSHA SmartSearch 법령·가이드·교육자료 검색
- 산업현장 사고·재해 중심 실시간 안전뉴스 수집
"""

import difflib
import html
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests
import urllib3

try:
    import keyring
except ImportError:
    keyring = None

from PySide6.QtCore import QSettings


# ============================================================
# 기본 설정
# ============================================================

APP_NAME = "퓨밍이 안전비서"
ORGANIZATION_NAME = "POSCO FUTURE M"
SETTINGS_NAME = "PyumingSafetyAssistant"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DEFAULT_GATEWAY_URL = (
    "http://127.0.0.1:18901/gpgpta01-gpt/"
)

DEFAULT_MODEL_NAME = "gpt-4o"

KOSHA_SEARCH_URL = (
    "https://apis.data.go.kr/"
    "B552468/srch/smartSearch"
)

KEYRING_SERVICE = (
    "POSCO_FUTURE_M_PYUMING"
)

P_GPT_KEY_ACCOUNT = (
    "PERSONAL_PGPT_API_KEY"
)

KOSHA_KEY_ACCOUNT = (
    "PERSONAL_KOSHA_API_KEY"
)

NAVER_CLIENT_ID_ACCOUNT = (
    "NAVER_CLIENT_ID"
)

NAVER_CLIENT_SECRET_ACCOUNT = (
    "NAVER_CLIENT_SECRET"
)

REQUEST_TIMEOUT = 20
P_GPT_TIMEOUT = 60
NEWS_MAX_AGE_DAYS = 30
MAX_NEWS_RESULTS = 100

KST = timezone(
    timedelta(hours=9)
)

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)


# ============================================================
# 산업현장 안전뉴스 기준
# ============================================================

SAFETY_NEWS_KEYWORDS = {
    "산업안전",
    "안전보건",
    "산업재해",
    "산재",
    "중대재해",
    "중대산업사고",
    "중대사고",
    "사망사고",
    "안전사고",
    "작업중지",
    "근로자",
    "작업자",
    "사업장",
    "작업장",
    "공사장",
    "공사현장",
    "건설공사",
    "지붕 공사",
    "태양광 공사",
    "공장",
    "건설현장",
    "산업현장",
    "제조업",
    "건설업",
    "협착",
    "끼임",
    "깔림",
    "매몰",
    "추락",
    "떨어짐",
    "붕괴",
    "전도",
    "충돌",
    "감전",
    "화재",
    "폭발",
    "질식",
    "중독",
    "누출",
    "화학사고",
    "유해화학물질",
    "밀폐공간",
    "용접",
    "크레인",
    "지게차",
    "중량물",
    "온열질환",
    "열사병",
    "안전관리",
    "안전점검",
    "위험성평가",
    "고용노동부",
    "안전보건공단",
}

DIRECT_SAFETY_NEWS_KEYWORDS = {
    "산업안전",
    "안전보건",
    "산업재해",
    "산재",
    "중대재해",
    "중대산업사고",
    "중대사고",
}

INDUSTRIAL_CONTEXT_NEWS_KEYWORDS = {
    "근로자",
    "노동자",
    "작업자",
    "작업 중",
    "작업중",
    "사업장",
    "작업장",
    "공사장",
    "공사현장",
    "건설공사",
    "지붕 공사",
    "태양광 공사",
    "공장",
    "건설현장",
    "산업현장",
    "제조업",
    "건설업",
    "생산라인",
    "생산설비",
    "기계설비",
}

SAFETY_MANAGEMENT_NEWS_KEYWORDS = {
    "안전관리",
    "안전점검",
    "위험성평가",
    "작업중지",
    "보호구",
    "안전조치",
    "재해예방",
    "사고예방",
}

INDUSTRIAL_INCIDENT_NEWS_KEYWORDS = {
    "사고",
    "사망",
    "화재",
    "협착",
    "끼임",
    "깔림",
    "매몰",
    "추락",
    "떨어짐",
    "붕괴",
    "전도",
    "충돌",
    "감전",
    "폭발",
    "질식",
    "중독",
    "누출",
}

STRONG_SAFETY_NEWS_KEYWORDS = {
    "산업안전",
    "안전보건",
    "중대재해",
    "중대산업사고",
    "사망",
    "산업재해",
    "산재",
    "사고",
    "협착",
    "끼임",
    "깔림",
    "매몰",
    "추락",
    "떨어짐",
    "붕괴",
    "전도",
    "감전",
    "화재",
    "폭발",
    "질식",
    "중독",
    "누출",
    "화학사고",
    "작업중지",
    "안전점검",
    "위험성평가",
}

NEWS_EXCLUDE_KEYWORDS = {
    "연예",
    "야구",
    "축구",
    "골프",
    "공연",
    "영화",
    "드라마",
    "게임",
    "패션",
    "화장품",
    "맛집",
    "관광",
    "여행",
    "선거",
    "부동산",
    "코인",
    "주식 추천",
    "경품",
    "할인",
    "신제품 출시",
    "애플",
    "갤럭시",
}

WEAK_NEWS_KEYWORDS = {
    "캠페인",
    "행사",
    "세미나",
    "협약",
    "업무협약",
    "mou",
    "수상",
    "봉사",
    "홍보",
    "전시회",
}

GOOGLE_NEWS_QUERIES = [
    (
        "산업안전 OR 산업재해 OR 중대재해 "
        "OR 중대산업사고 OR 안전보건"
    ),
    (
        "(산업현장 OR 사업장 OR 공장 OR 건설현장) "
        "(화재 OR 사망 OR 사고)"
    ),
    (
        "(근로자 OR 작업자 OR 노동자) "
        "(사망 OR 사고 OR 화재)"
    ),
    (
        "(협착 OR 끼임 OR 깔림 OR 추락 OR 감전) "
        "(산업현장 OR 사업장 OR 공장 OR 건설현장)"
    ),
    (
        "(화재 OR 폭발 OR 질식 OR 화학물질 누출) "
        "(사업장 OR 공장 OR 작업장)"
    ),
    (
        "고용노동부 산업안전 OR 안전보건공단 산업재해"
    ),
]

SAFETY_RSS_FEEDS = [
    (
        "안전신문",
        "https://www.safetynews.co.kr/rss/allArticle.xml",
    ),
    (
        "세이프타임즈",
        "http://www.safetimes.co.kr/rss/allArticle.xml",
    ),
    (
        "매일안전신문",
        "https://www.idsn.co.kr/news/rss.php",
    ),
]


# ============================================================
# 설정 저장소
# ============================================================

def app_settings():
    return QSettings(
        ORGANIZATION_NAME,
        SETTINGS_NAME,
    )


def read_simple_secrets():
    """
    아래 파일에서 설정값을 읽습니다.

    - .streamlit/secrets.toml
    - secrets.toml

    지원 항목:
    - PGPT_API_KEY
    - PGPT_URL
    - PGPT_MODEL
    - KOSHA_API_KEY
    """

    values = {}

    paths = [
        os.path.join(
            BASE_DIR,
            ".streamlit",
            "secrets.toml",
        ),
        os.path.join(
            BASE_DIR,
            "secrets.toml",
        ),
    ]

    for path in paths:
        if not os.path.isfile(path):
            continue

        try:
            with open(
                path,
                "r",
                encoding="utf-8-sig",
            ) as handle:
                lines = handle.readlines()

        except OSError as error:
            print(
                "[secrets.toml 읽기 실패] "
                + str(error)
            )
            continue

        for raw_line in lines:
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if line.startswith("["):
                continue

            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1,
            )

            key = key.strip().upper()

            value = value.split(
                "#",
                1,
            )[0].strip()

            value = value.strip('"').strip("'")

            if key and value:
                values[key] = value

    return values


def value_to_bool(
    value,
    default=False,
):
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    return str(
        value
    ).strip().lower() in {
        "true",
        "1",
        "yes",
        "on",
    }


# ============================================================
# 개인 인증키 저장
# ============================================================

def fallback_setting_name(account):
    return (
        "fallback_"
        + account.lower()
    )


def save_secure_key(
    account,
    value,
):
    clean_value = (
        value or ""
    ).strip()

    if keyring is not None:
        try:
            if clean_value:
                keyring.set_password(
                    KEYRING_SERVICE,
                    account,
                    clean_value,
                )
            else:
                try:
                    keyring.delete_password(
                        KEYRING_SERVICE,
                        account,
                    )
                except Exception:
                    pass

            app_settings().remove(
                fallback_setting_name(
                    account
                )
            )

            return True

        except Exception as error:
            print(
                "[Windows 보안 저장 실패] "
                + str(error)
            )

    app_settings().setValue(
        fallback_setting_name(account),
        clean_value,
    )

    return False


def load_secure_key(account):
    if keyring is not None:
        try:
            value = keyring.get_password(
                KEYRING_SERVICE,
                account,
            )

            if value:
                return value.strip()

        except Exception as error:
            print(
                "[Windows 보안 키 읽기 실패] "
                + str(error)
            )

    value = app_settings().value(
        fallback_setting_name(account),
        "",
    )

    return str(
        value or ""
    ).strip()


def delete_secure_key(account):
    if keyring is not None:
        try:
            keyring.delete_password(
                KEYRING_SERVICE,
                account,
            )
        except Exception:
            pass

    app_settings().remove(
        fallback_setting_name(account)
    )


# ============================================================
# 게이트웨이 및 전체 설정
# ============================================================

def normalize_gateway_url(url):
    value = (
        url or ""
    ).strip()

    if not value:
        value = DEFAULT_GATEWAY_URL

    value = value.rstrip("/")

    lowered = value.lower()

    # 사내 ChatGPT 웹 주소가 입력된 경우
    # PAI 로컬 게이트웨이로 자동 교정합니다.
    if (
        "aigpt.posco.net" in lowered
        and "127.0.0.1" not in lowered
        and "localhost" not in lowered
    ):
        print(
            "[P-GPT 주소 자동 교정] "
            "PAI 로컬 게이트웨이를 사용합니다."
        )

        return DEFAULT_GATEWAY_URL.rstrip("/")

    return value


def load_configuration():
    settings = app_settings()
    secrets = read_simple_secrets()

    saved_gateway = str(
        settings.value(
            "gateway_url",
            "",
        )
        or ""
    ).strip()

    if saved_gateway:
        gateway_url = saved_gateway
    else:
        gateway_url = secrets.get(
            "PGPT_URL",
            DEFAULT_GATEWAY_URL,
        )

    model_name = str(
        settings.value(
            "model_name",
            secrets.get(
                "PGPT_MODEL",
                DEFAULT_MODEL_NAME,
            ),
        )
        or DEFAULT_MODEL_NAME
    ).strip()

    use_ai = value_to_bool(
        settings.value(
            "use_ai",
            False,
        ),
        default=False,
    )

    use_kosha = value_to_bool(
        settings.value(
            "use_kosha",
            True,
        ),
        default=True,
    )

    use_web_search = value_to_bool(
        settings.value(
            "use_web_search",
            False,
        ),
        default=False,
    )

    p_gpt_key = load_secure_key(
        P_GPT_KEY_ACCOUNT
    )

    if not p_gpt_key:
        p_gpt_key = secrets.get(
            "PGPT_API_KEY",
            "",
        ).strip()

    kosha_key = load_secure_key(
        KOSHA_KEY_ACCOUNT
    )

    if not kosha_key:
        kosha_key = secrets.get(
            "KOSHA_API_KEY",
            "",
        ).strip()

    naver_client_id = load_secure_key(
        NAVER_CLIENT_ID_ACCOUNT
    )

    naver_client_secret = load_secure_key(
        NAVER_CLIENT_SECRET_ACCOUNT
    )

    return {
        "gateway_url": normalize_gateway_url(
            gateway_url
        ),
        "model_name": model_name,
        "use_ai": use_ai,
        "use_kosha": use_kosha,
        "use_web_search": use_web_search,
        "p_gpt_key": p_gpt_key,
        "kosha_key": kosha_key,
        "naver_client_id": naver_client_id,
        "naver_client_secret": naver_client_secret,
    }


def save_configuration(
    gateway_url,
    model_name,
    use_ai,
    use_kosha,
    use_web_search=False,
    p_gpt_key="",
    kosha_key="",
    naver_client_id="",
    naver_client_secret="",
):
    """
    desktop_app.py의 기존 호출 형식과 호환되도록
    네이버 관련 인자도 유지합니다.
    """

    settings = app_settings()

    settings.setValue(
        "gateway_url",
        normalize_gateway_url(
            gateway_url
        ),
    )

    settings.setValue(
        "model_name",
        (
            model_name.strip()
            or DEFAULT_MODEL_NAME
        ),
    )

    settings.setValue(
        "use_ai",
        bool(use_ai),
    )

    settings.setValue(
        "use_kosha",
        bool(use_kosha),
    )

    settings.setValue(
        "use_web_search",
        bool(use_web_search),
    )

    save_secure_key(
        P_GPT_KEY_ACCOUNT,
        p_gpt_key,
    )

    save_secure_key(
        KOSHA_KEY_ACCOUNT,
        kosha_key,
    )

    if naver_client_id:
        save_secure_key(
            NAVER_CLIENT_ID_ACCOUNT,
            naver_client_id,
        )

    if naver_client_secret:
        save_secure_key(
            NAVER_CLIENT_SECRET_ACCOUNT,
            naver_client_secret,
        )


def remove_saved_keys():
    accounts = [
        P_GPT_KEY_ACCOUNT,
        KOSHA_KEY_ACCOUNT,
        NAVER_CLIENT_ID_ACCOUNT,
        NAVER_CLIENT_SECRET_ACCOUNT,
    ]

    for account in accounts:
        delete_secure_key(
            account
        )

    settings = app_settings()

    settings.setValue(
        "use_ai",
        False,
    )

    settings.setValue(
        "use_kosha",
        False,
    )

    settings.setValue(
        "use_web_search",
        False,
    )

    settings.setValue(
        "gateway_url",
        DEFAULT_GATEWAY_URL.rstrip("/"),
    )


# ============================================================
# 문자 인코딩 및 HTML 응답 차단
# ============================================================

def repair_mojibake(text):
    value = str(
        text or ""
    )

    if not value:
        return ""

    suspicious = (
        "Ã",
        "Â",
        "ê",
        "ë",
        "ì",
        "í",
        "ð",
        "�",
    )

    if not any(
        marker in value
        for marker in suspicious
    ):
        return value

    try:
        repaired = value.encode(
            "latin-1"
        ).decode(
            "utf-8"
        )

        if repaired:
            return repaired

    except Exception:
        pass

    return value


def decode_response_text(response):
    content = (
        response.content
        or b""
    )

    if not content:
        return ""

    encodings = [
        "utf-8",
        response.encoding,
        response.apparent_encoding,
        "cp949",
        "euc-kr",
    ]

    tried = set()

    for encoding in encodings:
        if not encoding:
            continue

        encoding_name = str(
            encoding
        ).lower()

        if encoding_name in tried:
            continue

        tried.add(
            encoding_name
        )

        try:
            decoded = content.decode(
                encoding
            )

            return repair_mojibake(
                decoded
            )

        except Exception:
            continue

    return content.decode(
        "utf-8",
        errors="replace",
    )


def looks_like_html(text):
    value = (
        text or ""
    ).lstrip().lower()

    markers = (
        "<!doctype html",
        "<html",
        "<head",
        "<body",
        "<title>",
        "<script",
    )

    return any(
        value.startswith(marker)
        or marker in value[:800]
        for marker in markers
    )


def readable_http_error(
    status_code,
    response_text,
):
    text = repair_mojibake(
        response_text
    )

    if looks_like_html(text):
        return (
            "HTTP "
            + str(status_code)
            + " - API 대신 웹 화면이 반환되었습니다."
        )

    text = re.sub(
        "[ \t]+",
        " ",
        text,
    )

    if len(text) > 400:
        text = text[:400] + "…"

    return (
        "HTTP "
        + str(status_code)
        + " - "
        + text
    )


# ============================================================
# P-GPT 게이트웨이
# ============================================================

def gateway_endpoint_candidates(
    gateway_url,
):
    base = normalize_gateway_url(
        gateway_url
    )

    lowered = base.lower()
    candidates = []

    if lowered.endswith(
        "/chat/completions"
    ):
        candidates.append(base)

    elif lowered.endswith("/v1"):
        candidates.append(
            base + "/chat/completions"
        )

    else:
        candidates.extend([
            base + "/v1/chat/completions",
            base + "/chat/completions",
        ])

    unique = []

    for endpoint in candidates:
        if endpoint not in unique:
            unique.append(endpoint)

    return unique


def gateway_header_candidates(api_key):
    key = (
        api_key or ""
    ).strip()

    return [
        (
            "Authorization Bearer",
            {
                "Authorization": (
                    "Bearer " + key
                ),
                "Content-Type": (
                    "application/json; charset=utf-8"
                ),
                "Accept": "application/json",
            },
        ),
        (
            "X-API-Key",
            {
                "X-API-Key": key,
                "Content-Type": (
                    "application/json; charset=utf-8"
                ),
                "Accept": "application/json",
            },
        ),
        (
            "api-key",
            {
                "api-key": key,
                "Content-Type": (
                    "application/json; charset=utf-8"
                ),
                "Accept": "application/json",
            },
        ),
    ]


def extract_answer(data):
    if isinstance(data, str):
        text = repair_mojibake(
            data
        ).strip()

        if looks_like_html(text):
            return ""

        return text

    if isinstance(data, list):
        for item in data:
            answer = extract_answer(
                item
            )

            if answer:
                return answer

        return ""

    if not isinstance(data, dict):
        return ""

    choices = data.get(
        "choices"
    )

    if (
        isinstance(choices, list)
        and choices
    ):
        first = choices[0]

        if isinstance(first, dict):
            message = first.get(
                "message"
            )

            if isinstance(message, dict):
                answer = extract_answer(
                    message.get(
                        "content"
                    )
                )

                if answer:
                    return answer

            answer = extract_answer(
                first.get(
                    "text"
                )
            )

            if answer:
                return answer

    for key in (
        "answer",
        "content",
        "result",
        "message",
        "output",
        "text",
        "data",
        "response",
    ):
        if key not in data:
            continue

        answer = extract_answer(
            data.get(key)
        )

        if answer:
            return answer

    return ""


def parse_p_gpt_response(response):
    response_text = decode_response_text(
        response
    )

    if looks_like_html(
        response_text
    ):
        raise RuntimeError(
            "P-GPT API 대신 웹 화면이 반환되었습니다. "
            "PAI 로컬 게이트웨이가 실행 중인지 확인해 주세요."
        )

    if response.status_code != 200:
        raise RuntimeError(
            readable_http_error(
                response.status_code,
                response_text,
            )
        )

    data = None

    try:
        data = json.loads(
            response_text
        )
    except Exception:
        data = None

    # SSE 응답 지원
    if (
        data is None
        and "data:" in response_text
    ):
        collected = []

        for line in response_text.splitlines():
            stripped = line.strip()

            if not stripped.startswith(
                "data:"
            ):
                continue

            value = stripped[
                len("data:"):
            ].strip()

            if not value:
                continue

            if value == "[DONE]":
                continue

            try:
                event_data = json.loads(
                    value
                )

                answer = extract_answer(
                    event_data
                )

                if answer:
                    collected.append(
                        answer
                    )

            except Exception:
                if not looks_like_html(
                    value
                ):
                    collected.append(
                        value
                    )

        answer = "".join(
            collected
        ).strip()

        if answer:
            return answer

    if data is None:
        data = response_text

    answer = extract_answer(
        data
    )

    if not answer:
        raise RuntimeError(
            "P-GPT 응답에서 답변 내용을 찾지 못했습니다."
        )

    return answer


def call_p_gpt(
    messages,
    gateway_url,
    api_key,
    model_name,
    timeout=P_GPT_TIMEOUT,
):
    key = (
        api_key or ""
    ).strip()

    if not key:
        raise RuntimeError(
            "개인 P-GPT API 키가 없습니다."
        )

    payloads = [
        {
            "model": (
                model_name
                or DEFAULT_MODEL_NAME
            ),
            "stream": False,
            "temperature": 0.2,
            "messages": messages,
        },
        {
            "model": (
                model_name
                or DEFAULT_MODEL_NAME
            ),
            "stream": False,
            "messages": messages,
        },
    ]

    session = requests.Session()

    # 127.0.0.1 로컬 게이트웨이는 프록시를 사용하지 않습니다.
    session.trust_env = False

    errors = []

    for endpoint in gateway_endpoint_candidates(
        gateway_url
    ):
        for (
            header_name,
            headers,
        ) in gateway_header_candidates(
            key
        ):
            for payload in payloads:
                try:
                    response = session.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=timeout,
                    )

                    answer = parse_p_gpt_response(
                        response
                    )

                    print(
                        "[P-GPT 연결 성공] "
                        + endpoint
                        + " / "
                        + header_name
                    )

                    return answer

                except Exception as error:
                    errors.append(
                        endpoint
                        + " / "
                        + header_name
                        + " / "
                        + repair_mojibake(
                            str(error)
                        )[:200]
                    )

    raise RuntimeError(
        "P-GPT 연결 실패\n"
        + "\n".join(
            errors[-5:]
        )
    )


def test_p_gpt(
    gateway_url,
    api_key,
    model_name,
):
    messages = [
        {
            "role": "system",
            "content": (
                "연결 시험입니다. "
                "반드시 연결 성공이라고만 답하세요."
            ),
        },
        {
            "role": "user",
            "content": "연결 확인",
        },
    ]

    return call_p_gpt(
        messages,
        gateway_url,
        api_key,
        model_name,
        timeout=30,
    )


# ============================================================
# 일반 질문 답변
# ============================================================

GENERAL_CHAT_SYSTEM_PROMPT = """
당신은 포스코퓨처엠의 30년차 안전·보건·환경관리자 관점으로 답변하는
안전환경 전문 비서입니다.

규칙:
1. 인사에는 밝고 짧게 답하고, 일반 질문에는 핵심 위주로 답하세요.
2. 안전·보건·환경 질문은 산업안전보건법, 산업안전보건법 시행령·시행규칙,
   산업안전보건기준에 관한 규칙, 중대재해 처벌 등에 관한 법률·시행령,
   대기환경보전법, 물환경보전법, 화학물질관리법 및 관련 하위법령·고시를
   우선 확인하는 기준으로 답하세요.
3. 법령과 사내 기준이 다르면 최신 법령과 인허가 조건을 우선하고,
   사내 기준은 법령을 충족하는 범위에서 구분하여 설명하세요.
4. 제공된 법령·공단·사내 자료가 있으면 그 자료를 우선 근거로 사용하세요.
   자료에 없는 조문·수치·기한은 추측하지 말고 최신 원문 확인이 필요하다고
   명확히 밝혀 주세요.
5. 답변은 현장 적용에 도움이 되도록 위험요인, 준수사항, 확인·기록 방법을
   구분하고 한국어 존댓말로 작성하세요.
6. 회사 내부정보를 알고 있다고 가정하지 마세요.
""".strip()


def answer_general_question(
    question,
    web_results=None,
    system_prompt=None,
):
    configuration = load_configuration()

    if not (
        configuration["use_ai"]
        and configuration["p_gpt_key"]
    ):
        return ""

    web_results = (
        web_results or []
    )

    search_context = []

    for number, item in enumerate(
        web_results[:5],
        start=1,
    ):
        content = (
            item.get(
                "content",
                "",
            )
            or item.get(
                "description",
                "",
            )
        )

        search_context.append(
            str(number)
            + ". "
            + item.get(
                "category",
                "",
            )
            + " | "
            + item.get(
                "title",
                "",
            )
            + "\n"
            + content
            + "\n"
            + item.get(
                "link",
                "",
            )
        )

    if search_context:
        user_content = (
            "질문: "
            + question
            + "\n\n검색 결과:\n"
            + "\n\n".join(
                search_context
            )
            + "\n\n위 검색 결과를 참고하여 짧고 정확하게 답하세요."
        )
    else:
        user_content = (
            "질문: "
            + question
        )

    messages = [
        {
            "role": "system",
            "content": (
                system_prompt
                or GENERAL_CHAT_SYSTEM_PROMPT
            ),
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

    return call_p_gpt(
        messages,
        configuration["gateway_url"],
        configuration["p_gpt_key"],
        configuration["model_name"],
    )


# ============================================================
# KOSHA 검색
# ============================================================

KOSHA_CATEGORY_INFO = {
    "8": {
        "name": "중대재해 처벌 등에 관한 법률",
        "priority": 1,
    },
    "9": {
        "name": "중대재해 처벌 등에 관한 법률 시행령",
        "priority": 2,
    },
    "1": {
        "name": "산업안전보건법",
        "priority": 3,
    },
    "2": {
        "name": "산업안전보건법 시행령",
        "priority": 4,
    },
    "3": {
        "name": "산업안전보건법 시행규칙",
        "priority": 5,
    },
    "4": {
        "name": "산업안전보건기준에 관한 규칙",
        "priority": 6,
    },
    "11": {
        "name": "유해·위험작업의 취업 제한에 관한 규칙",
        "priority": 7,
    },
    "5": {
        "name": "고시·훈령·예규",
        "priority": 8,
    },
}


def clean_html_text(value):
    text = html.unescape(
        str(value or "")
    )

    text = re.sub(
        "<[^>]+>",
        " ",
        text,
    )

    text = re.sub(
        "[ \t]{2,}",
        " ",
        text,
    )

    text = re.sub(
        "\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def build_law_link(
    category_id,
    title,
):
    information = KOSHA_CATEGORY_INFO.get(
        category_id,
        {},
    )

    law_name = information.get(
        "name",
        "",
    )

    if category_id == "5":
        return (
            "https://www.law.go.kr/"
            "admRulSc.do?menuId=5&subMenuId=41&query="
            + urllib.parse.quote(
                title
            )
        )

    article_match = re.search(
        "제([0-9]+)조(?:의([0-9]+))?",
        title,
    )

    if article_match:
        article_number = article_match.group(1)
        branch_number = article_match.group(2)

        suffix = (
            "제"
            + article_number
            + "조"
        )

        if branch_number:
            suffix += (
                "의"
                + branch_number
            )

        raw_url = (
            "https://www.law.go.kr/법령/"
            + law_name
            + "/"
            + suffix
        )

    else:
        raw_url = (
            "https://www.law.go.kr/법령/"
            + law_name
        )

    return urllib.parse.quote(
        raw_url,
        safe=":/",
    )


def extract_kosha_items(body):
    items = body.get(
        "items",
        {},
    )

    if isinstance(items, dict):
        item_list = items.get(
            "item",
            [],
        )

    elif isinstance(items, list):
        item_list = items

    else:
        item_list = []

    if isinstance(item_list, dict):
        item_list = [
            item_list
        ]

    return item_list


def search_kosha(
    keyword,
    api_key,
    maximum=10,
):
    key = (
        api_key or ""
    ).strip()

    if not key:
        return []

    parameters = {
        "serviceKey": key,
        "pageNo": "1",
        "numOfRows": "50",
        "searchValue": keyword,
        "category": "0",
        "dataType": "JSON",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64)"
        ),
        "Accept": "application/json",
    }

    response = requests.get(
        KOSHA_SEARCH_URL,
        params=parameters,
        headers=headers,
        verify=False,
        timeout=REQUEST_TIMEOUT,
    )

    response_text = decode_response_text(
        response
    ).strip()

    if response.status_code != 200:
        raise RuntimeError(
            readable_http_error(
                response.status_code,
                response_text,
            )
        )

    if response_text.startswith("<"):
        authentication_match = re.search(
            "<returnAuthMsg>(.*?)</returnAuthMsg>",
            response_text,
        )

        if authentication_match:
            raise RuntimeError(
                repair_mojibake(
                    authentication_match.group(1)
                )
            )

        raise RuntimeError(
            "KOSHA API가 XML 오류를 반환했습니다."
        )

    data = json.loads(
        response_text
    )

    body = data.get(
        "response",
        {},
    ).get(
        "body",
        {},
    )

    results = []

    for item in extract_kosha_items(
        body
    ):
        category_id = str(
            item.get(
                "category",
                "",
            )
        )

        title = clean_html_text(
            item.get(
                "title",
                "",
            )
        )

        content = clean_html_text(
            item.get(
                "highlight_content",
                "",
            )
            or item.get(
                "content",
                "",
            )
        )

        if category_id in KOSHA_CATEGORY_INFO:
            information = (
                KOSHA_CATEGORY_INFO[
                    category_id
                ]
            )

            results.append({
                "kind": "law",
                "category": information["name"],
                "title": (
                    title
                    or information["name"]
                ),
                "content": content,
                "link": build_law_link(
                    category_id,
                    title,
                ),
                "priority": information["priority"],
            })

        elif category_id == "7":
            results.append({
                "kind": "guide",
                "category": "KOSHA GUIDE",
                "title": title,
                "content": content,
                "link": (
                    "https://portal.kosha.or.kr/"
                    "archive/resources/tech-support/search/all"
                    "?page=1&rowsPerPage=10"
                ),
                "priority": 20,
            })

        elif category_id == "6":
            file_path = item.get(
                "filepath",
                "",
            )

            if isinstance(
                file_path,
                list,
            ):
                file_path = (
                    file_path[0]
                    if file_path
                    else ""
                )

            results.append({
                "kind": "media",
                "category": (
                    item.get(
                        "media_style",
                        "안전보건 미디어",
                    )
                    or "안전보건 미디어"
                ),
                "title": title,
                "content": content,
                "link": str(
                    file_path or ""
                ),
                "priority": 30,
            })

    results.sort(
        key=lambda item: (
            item.get(
                "priority",
                99,
            ),
            item.get(
                "title",
                "",
            ),
        )
    )

    return results[:maximum]


# ============================================================
# 일반 웹검색 호환 함수
# ============================================================

def search_general_web(
    keyword,
    maximum=5,
):
    """
    최종 UI에서는 네이버 키 입력란을 제거했으므로
    기본적으로 빈 결과를 반환합니다.

    함수명은 desktop_app.py와의 호환을 위해 유지합니다.
    """

    del keyword
    del maximum

    return []


# ============================================================
# 뉴스 날짜 처리
# ============================================================

def now_kst():
    return datetime.now(
        KST
    )


def clean_news_text(value):
    text = clean_html_text(
        value
    )

    text = re.sub(
        "[\r\n]+",
        " ",
        text,
    )

    text = re.sub(
        "[ ]{2,}",
        " ",
        text,
    )

    return text.strip()


def parse_news_datetime(value):
    text = (
        value or ""
    ).strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=KST
            )

        return parsed.astimezone(
            KST
        )

    except Exception:
        pass

    try:
        parsed = parsedate_to_datetime(
            text
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            KST
        )

    except Exception:
        pass

    date_formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y.%m.%d %H:%M",
        "%Y.%m.%d",
    ]

    for date_format in date_formats:
        try:
            parsed = datetime.strptime(
                text[:19],
                date_format,
            )

            return parsed.replace(
                tzinfo=KST
            )

        except Exception:
            continue

    return None


def is_recent_news_date(
    published_datetime,
):
    if published_datetime is None:
        return False

    current = now_kst()

    earliest = (
        current
        - timedelta(
            days=NEWS_MAX_AGE_DAYS
        )
    )

    latest = (
        current
        + timedelta(
            minutes=10
        )
    )

    return (
        earliest
        <= published_datetime
        <= latest
    )


# ============================================================
# 뉴스 관련성
# ============================================================

def is_relevant_safety_news(
    title,
    description="",
):
    combined = (
        str(title or "")
        + " "
        + str(description or "")
    ).lower()

    has_direct_keyword = any(
        keyword.lower() in combined
        for keyword in DIRECT_SAFETY_NEWS_KEYWORDS
    )

    has_industrial_context = any(
        keyword.lower() in combined
        for keyword in INDUSTRIAL_CONTEXT_NEWS_KEYWORDS
    )

    has_incident_keyword = any(
        keyword.lower() in combined
        for keyword in INDUSTRIAL_INCIDENT_NEWS_KEYWORDS
    )

    has_safety_management_keyword = any(
        keyword.lower() in combined
        for keyword in SAFETY_MANAGEMENT_NEWS_KEYWORDS
    )

    is_industrial_incident = (
        has_industrial_context
        and has_incident_keyword
    )

    if not (
        has_direct_keyword
        or is_industrial_incident
        or (
            has_safety_management_keyword
            and has_industrial_context
        )
    ):
        return False

    has_strong_keyword = any(
        keyword.lower() in combined
        for keyword in STRONG_SAFETY_NEWS_KEYWORDS
    )

    has_excluded_keyword = any(
        keyword.lower() in combined
        for keyword in NEWS_EXCLUDE_KEYWORDS
    )

    if (
        has_excluded_keyword
        and not has_direct_keyword
    ):
        return False

    has_weak_keyword = any(
        keyword.lower() in combined
        for keyword in WEAK_NEWS_KEYWORDS
    )

    if (
        has_weak_keyword
        and not (
            has_direct_keyword
            or has_strong_keyword
        )
    ):
        return False

    return True


def news_priority_score(
    title,
    description="",
):
    combined = (
        str(title or "")
        + " "
        + str(description or "")
    ).lower()

    weights = {
        "중대재해": 15,
        "중대산업사고": 15,
        "산업안전": 13,
        "안전보건": 11,
        "사망": 14,
        "산업재해": 12,
        "산재": 10,
        "사고": 8,
        "협착": 11,
        "끼임": 11,
        "추락": 11,
        "떨어짐": 11,
        "감전": 11,
        "폭발": 11,
        "질식": 11,
        "중독": 10,
        "화재": 9,
        "붕괴": 10,
        "매몰": 10,
        "누출": 9,
        "건설현장": 6,
        "산업현장": 6,
        "사업장": 5,
        "공장": 5,
        "작업장": 5,
        "근로자": 5,
        "작업자": 5,
        "안전점검": 5,
        "위험성평가": 5,
        "고용노동부": 3,
        "안전보건공단": 3,
    }

    score = 0

    for keyword, weight in weights.items():
        if keyword in combined:
            score += weight

    if any(
        keyword.lower() in combined
        for keyword in NEWS_EXCLUDE_KEYWORDS
    ):
        score -= 20

    return score


# ============================================================
# RSS 뉴스 파싱
# ============================================================

def rss_item_text(
    item,
    tag_names,
):
    for tag_name in tag_names:
        value = item.findtext(
            tag_name,
            default="",
        )

        if value:
            return value

    return ""


def parse_rss_items(
    xml_bytes,
    source_name,
    maximum=20,
):
    root = ET.fromstring(
        xml_bytes
    )

    item_elements = root.findall(
        ".//item"
    )

    if not item_elements:
        item_elements = root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )

    results = []

    for item in item_elements:
        title = clean_news_text(
            rss_item_text(
                item,
                [
                    "title",
                    "{http://www.w3.org/2005/Atom}title",
                ],
            )
        )

        description = clean_news_text(
            rss_item_text(
                item,
                [
                    "description",
                    "summary",
                    "{http://www.w3.org/2005/Atom}summary",
                    (
                        "{http://purl.org/rss/1.0/"
                        "modules/content/}encoded"
                    ),
                ],
            )
        )

        link = rss_item_text(
            item,
            [
                "link",
            ],
        ).strip()

        if not link:
            atom_link = item.find(
                "{http://www.w3.org/2005/Atom}link"
            )

            if atom_link is not None:
                link = str(
                    atom_link.attrib.get(
                        "href",
                        "",
                    )
                    or ""
                ).strip()

        raw_date = rss_item_text(
            item,
            [
                "pubDate",
                "published",
                "updated",
                "{http://purl.org/dc/elements/1.1/}date",
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ],
        )

        published_datetime = parse_news_datetime(
            raw_date
        )

        if not is_recent_news_date(
            published_datetime
        ):
            continue

        if not is_relevant_safety_news(
            title,
            description,
        ):
            continue

        results.append({
            "source": source_name,
            "title": title,
            "description": description,
            "link": link,
            "published": (
                published_datetime.strftime(
                    "%Y-%m-%d %H:%M"
                )
            ),
            "published_timestamp": (
                published_datetime.timestamp()
            ),
            "priority": news_priority_score(
                title,
                description,
            ),
        })

        if len(results) >= maximum:
            break

    return results


def fetch_rss(
    source_name,
    url,
    maximum=20,
    verify=True,
):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/122.0 Safari/537.36"
        ),
        "Accept": (
            "application/rss+xml,"
            "application/xml,"
            "text/xml,*/*"
        ),
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=15,
        verify=verify,
    )

    response.raise_for_status()

    return parse_rss_items(
        response.content,
        source_name,
        maximum,
    )


def fetch_google_safety_news():
    results = []

    for query in GOOGLE_NEWS_QUERIES:
        encoded_query = urllib.parse.quote(
            query
        )

        url = (
            "https://news.google.com/rss/search"
            "?q="
            + encoded_query
            + "&hl=ko&gl=KR&ceid=KR:ko"
        )

        try:
            results.extend(
                fetch_rss(
                    "Google 뉴스",
                    url,
                    maximum=25,
                    verify=False,
                )
            )

        except Exception as error:
            print(
                "[Google 안전뉴스 오류] "
                + str(error)
            )

    return results


# ============================================================
# 뉴스 중복 제거
# ============================================================

def normalize_news_title(title):
    return re.sub(
        "[^0-9A-Za-z가-힣]",
        "",
        title or "",
    ).lower()


def titles_are_similar(
    first_title,
    second_title,
):
    first = normalize_news_title(
        first_title
    )

    second = normalize_news_title(
        second_title
    )

    if not first or not second:
        return False

    if first == second:
        return True

    similarity = difflib.SequenceMatcher(
        None,
        first,
        second,
    ).ratio()

    return similarity >= 0.82


def remove_duplicate_news(items):
    unique = []

    for item in items:
        duplicated = False

        for existing in unique:
            same_link = (
                item.get("link")
                and item.get("link")
                == existing.get("link")
            )

            similar_title = titles_are_similar(
                item.get(
                    "title",
                    "",
                ),
                existing.get(
                    "title",
                    "",
                ),
            )

            if same_link or similar_title:
                duplicated = True
                break

        if not duplicated:
            unique.append(
                item
            )

    return unique


# ============================================================
# 실시간 산업안전 뉴스 수집
# ============================================================

def fetch_safety_news(
    maximum=MAX_NEWS_RESULTS,
):
    results = []

    results.extend(
        fetch_google_safety_news()
    )

    for source_name, url in SAFETY_RSS_FEEDS:
        try:
            results.extend(
                fetch_rss(
                    source_name,
                    url,
                    maximum=20,
                    verify=False,
                )
            )

        except Exception as error:
            print(
                "["
                + source_name
                + " 오류] "
                + str(error)
            )

    results = remove_duplicate_news(
        results
    )

    results.sort(
        key=lambda item: (
            item.get(
                "priority",
                0,
            ),
            item.get(
                "published_timestamp",
                0,
            ),
        ),
        reverse=True,
    )

    return results[:maximum]
