# -*- coding: utf-8 -*-
"""
퓨밍이 안전비서

주요 기능
- 사내 안전·환경 TXT 문서 검색
- 직원 개인 P-GPT API 사용
- KOSHA 법규·가이드·교육자료 검색
- 인사 및 일반 질문 응답
- 질문·답변 기록 저장
- 왼쪽 포스트잇 책갈피
- 책갈피 클릭 시 질문 위치로 이동
- 검색 문장 클릭 시 정확한 원문 위치 표시
- 산업현장 중심 안전뉴스 자동 수집 및 누적 저장
- 검색어 노란색 강조
- Ctrl+F 결과 내 검색 및 이전·다음 이동
- 글자 크기 조절
"""

import functools
import html
import os
import random
import re
import sys

from PySide6.QtCore import (
    QPoint,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
)

from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QRegion,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
)

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from document_engine import (
    DOCUMENTS_DIR,
    SOURCE_TYPE_OFFICIAL_REFERENCE,
    UNNUMBERED_SECTION_LABEL,
    build_answer_bundle,
    greeting_answer,
    is_greeting,
    load_documents_with_index,
    local_answer,
    looks_like_document_question,
    query_variants,
    search_documents,
    search_reference_documents,
)

from external_services import (
    DEFAULT_GATEWAY_URL,
    DEFAULT_MODEL_NAME,
    answer_general_question,
    app_settings,
    fetch_safety_news,
    load_configuration,
    remove_saved_keys,
    save_configuration,
    search_kosha,
    test_p_gpt,
)

from history_store import (
    clear_chat_history,
    clear_saved_news,
    count_saved_news,
    delete_chat_history,
    get_chat_history,
    init_databases,
    list_chat_history,
    list_saved_news,
    save_chat_history,
    save_news_items,
)


# ============================================================
# 기본 설정
# ============================================================

APP_NAME = "퓨밍이 안전비서"
HEADER_TITLE = "퓨밍이 안전비서"
ORGANIZATION_NAME = "POSCO FUTURE M"
SETTINGS_NAME = "PyumingSafetyAssistant"

APP_FONT_FAMILY = "NanumBarunGothic"
TITLE_FONT_FAMILY = "NanumBarunGothic"
SUBTITLE_FONT_FAMILY = "NanumBarunGothic"

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

ASSETS_DIR = os.path.join(
    BASE_DIR,
    "assets",
)

MASCOT_FILE_NAMES = [
    "pyuming_source.png",
    "pyuming.png",
    "mascot.png",
    "character.png",
]

PIXMAP_CACHE = {}

DEFAULT_CONTENT_FONT_SIZE = 17
MIN_CONTENT_FONT_SIZE = 13
MAX_CONTENT_FONT_SIZE = 26

BOOKMARK_WIDTH = 175
HISTORY_LOAD_LIMIT = 100
NEWS_PAGE_SIZE = 25
MAX_AI_CONTEXT_CHARS = 12000


# ============================================================
# 표시용 정규식
# ============================================================

CITATION_PATTERN = re.compile(
    re.escape("[근거")
    + "[ ]*([0-9]{1,2})"
    + re.escape("]")
)

HEADING_PATTERN = re.compile(
    "^(#{1,6})[ ]*(.+)$"
)

BULLET_PATTERN = re.compile(
    "^([-*•·])[ ]+(.+)$"
)

ORDERED_PATTERN = re.compile(
    "^([0-9]{1,2})[.)][ ]+(.+)$"
)

BOLD_PATTERN = re.compile(
    "[*][*](.+?)[*][*]"
)

CODE_PATTERN = re.compile(
    "`([^`]+)`"
)

TABLE_DIVIDER_PATTERN = re.compile(
    "^[ |:+-]+$"
)

ARTICLE_HEADING_PATTERN = re.compile(
    "^[0-9]{1,2}([.][0-9]{1,2}){0,5}[ ]+"
)


# ============================================================
# 공통 도구
# ============================================================

def safe_text(value):
    return html.escape(
        str(value or ""),
        quote=True,
    )


def compact_text(value):
    return " ".join(
        str(value or "").split()
    )


COMPACT_FACT_RULES = (
    {
        "key": "confined_space_oxygen",
        "title": "밀폐공간 적정 산소농도",
        "value": "18.0% 이상 ~ 23.5% 미만",
        "required_groups": (
            ("밀폐공간",),
            (
                "산소농도",
                "산소기준",
                "산소범위",
                "적정산소",
                "산소몇",
                "산소퍼센트",
            ),
        ),
        "excluded": (
            "측정방법",
            "측정위치",
            "측정주기",
            "측정횟수",
            "측정장비",
            "측정기",
            "감지기",
            "검지기",
            "경보",
            "설정",
            "교정",
            "점검",
            "기록",
            "환기",
            "조치",
            "대처",
            "어떻게",
            "진입",
            "들어가",
            "작업해도",
        ),
        "standard_numbers": (
            "PCI-00-0GN-208",
            "PCI-00-0GN-108",
        ),
        "source_pattern": (
            r"산소\s*:?[ ]*18(?:[.]0)?%\s*이상\s*23[.]5%\s*미만"
        ),
        "focus_text": "산소 18% 이상 23.5% 미만",
        "focus_heading": "3. 용어의 정의",
    },
    {
        "key": "toe_board_height",
        "title": "발끝막이판 높이",
        "value": "10cm 이상",
        "required_groups": (
            ("발끝막이판", "토보드", "toeboard"),
            ("높이", "기준", "규격", "얼마", "몇"),
        ),
        "excluded": (
            "생략",
            "예외",
            "바닥틈",
            "간격",
            "설치방법",
            "재질",
        ),
        "standard_numbers": (
            "PCI-00-0GN-110",
            "PCI-00-0GN-601",
        ),
        "source_pattern": (
            r"(?:발끝막이판[\s\S]{0,80}?높이\s*10\s*(?:cm|센티미터)\s*이상"
            r"|발끝막이판\s*:?[ ]*(?:높이\s*)?10\s*(?:cm|센티미터)\s*이상"
            r"|발끝막이판\s*100\s*mm\s*이상)"
        ),
        "focus_text": "높이 10cm 이상",
        "focus_heading": "6.2.3 발끝막이판",
    },
    {
        "key": "safety_rail_height",
        "title": "안전난간 상부 높이",
        "value": "90cm 이상",
        "required_groups": (
            ("안전난간",),
            ("높이", "기준", "규격", "얼마", "몇"),
        ),
        "excluded": (
            "중간난간",
            "간격",
            "하중",
            "발끝막이판",
            "생략",
            "예외",
        ),
        "standard_numbers": (
            "PCI-00-0GN-110",
            "PCI-00-0GN-601",
        ),
        "source_pattern": (
            r"(?:상부 난간대\s*:?[ ]*[^\n]{0,80}?90\s*cm\s*이상"
            r"|상부\s*90\s*cm\s*이상)"
        ),
        "focus_text": "상부 난간대 : 바닥·발판·경사로 표면에서 90cm 이상",
        "focus_heading": "6.2.2 높이·간격",
    },
    {
        "key": "work_permit_validity",
        "title": "안전작업허가 유효기간",
        "value": "당일 한정 · 최대 8시간",
        "required_groups": (
            ("안전작업허가", "작업허가"),
            ("유효기간", "허가기간", "몇시간"),
        ),
        "excluded": (
            "연장",
            "야간",
            "변경",
            "재승인",
            "재허가",
        ),
        "standard_numbers": (
            "PCI-00-0GN-108",
        ),
        "source_pattern": (
            r"당일 한정\s*8시간을 초과할 수 없다"
        ),
        "focus_text": "당일 한정 8시간을 초과할 수 없다",
        "focus_heading": "7. 허가서 유효기간",
    },
    {
        "key": "work_environment_interval",
        "title": "작업환경측정 기본 주기",
        "value": "반기 1회 이상",
        "required_groups": (
            ("작업환경측정",),
            ("주기", "횟수", "얼마나자주"),
        ),
        "excluded": (
            "신규",
            "변경",
            "초과",
            "예외",
            "연1회",
            "3개월",
        ),
        "standard_numbers": (
            "PCI-00-0GN-215",
            "PCR-M-101",
        ),
        "source_pattern": (
            r"(?:작업환경측정은\s*)?반기(?:별)?\s*1회 이상"
        ),
        "focus_text": "작업환경측정은 반기별 1회 이상 실시한다",
        "focus_heading": "10.1 작업환경측정",
    },
)


def normalized_question_text(question):
    return re.sub(
        r"[^0-9a-z가-힣%]+",
        "",
        str(question or "").lower(),
    )


def compact_fact_definition(question):
    """숫자 하나로 바로 답할 수 있는 짧은 기준 질문을 찾습니다."""
    text = normalized_question_text(
        question
    )

    for rule in COMPACT_FACT_RULES:
        if any(
            excluded in text
            for excluded in rule.get(
                "excluded",
                (),
            )
        ):
            continue

        if all(
            any(
                required in text
                for required in group
            )
            for group in rule[
                "required_groups"
            ]
        ):
            return rule

    return None


def is_confined_space_oxygen_question(question):
    rule = compact_fact_definition(
        question
    )

    return bool(
        rule
        and rule["key"]
        == "confined_space_oxygen"
    )


def find_compact_fact_source(
    question,
    sources,
):
    """핵심 수치가 실제로 적힌 사내 지침을 우선순위대로 고릅니다."""
    rule = compact_fact_definition(
        question
    )

    if rule is None:
        return None

    candidates = []

    for source_index, source in enumerate(
        sources or []
    ):
        if source.get(
            "source_type",
            "internal",
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE:
            continue

        source_text = str(
            source.get(
                "text",
                "",
            )
            or ""
        )

        match = re.search(
            rule["source_pattern"],
            source_text,
            flags=re.IGNORECASE,
        )

        if match is None:
            continue

        standard_number = str(
            source.get(
                "standard_number",
                "",
            )
            or ""
        )

        preferred_numbers = rule[
            "standard_numbers"
        ]

        try:
            priority = preferred_numbers.index(
                standard_number
            )
        except ValueError:
            priority = len(
                preferred_numbers
            )

        candidates.append((
            priority,
            -float(
                source.get(
                    "score",
                    0.0,
                )
                or 0.0
            ),
            source_index,
            source,
            rule["focus_text"],
        ))

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            item[0],
            item[1],
            item[2],
        )
    )

    (
        _,
        _,
        source_index,
        source,
        focus_text,
    ) = candidates[0]

    return {
        "source_index": source_index,
        "source": source,
        "focus_text": focus_text,
        "rule": rule,
    }


def compact_fact_history_answer(question):
    rule = compact_fact_definition(
        question
    )

    if rule is None:
        return ""

    return (
        "### "
        + rule["title"]
        + "\n\n**"
        + rule["value"]
        + "**"
    )


def render_compact_fact_answer(
    question,
    sources,
):
    """핵심 수치와 사내 지침 링크만 담은 큰 글씨 답변을 만듭니다."""
    selected = find_compact_fact_source(
        question,
        sources
    )

    if selected is None:
        return "", []

    source = selected["source"]
    rule = selected["rule"]
    standard_name = (
        source.get(
            "standard_name",
            "",
        )
        or "사내 안전보건 지침"
    )

    standard_number = (
        source.get(
            "standard_number",
            "",
        )
        or UNNUMBERED_SECTION_LABEL
    )

    html_content = (
        '<table width="100%" cellspacing="0" cellpadding="14" '
        'style="background-color:#EAF8F6; border:1px solid #A7DCD7;">'
        "<tr><td>"
        '<div style="color:#0C5E64; font-size:105%; font-weight:700; '
        'margin-bottom:9px;">'
        + safe_text(
            rule["title"]
        )
        + "</div>"
        '<div style="color:#102A49; font-size:165%; font-weight:700; '
        'line-height:1.25;">'
        + safe_text(
            rule["value"]
        )
        + "</div>"
        "</td></tr></table>"
        '<p style="margin:13px 0 0 2px;">'
        '<a href="sourceitem:0" style="color:#0C5E64; font-weight:700;">'
        + safe_text(
            standard_name
        )
        + " ("
        + safe_text(
            standard_number
        )
        + ") 보기</a></p>"
    )

    source_links = [{
        "source_index": selected[
            "source_index"
        ],
        "focus_text": selected[
            "focus_text"
        ],
        "focus_heading": rule[
            "focus_heading"
        ],
    }]

    return html_content, source_links


def find_confined_space_oxygen_source(sources):
    return find_compact_fact_source(
        "밀폐공간 산소농도",
        sources,
    )


def render_confined_space_oxygen_answer(sources):
    return render_compact_fact_answer(
        "밀폐공간 산소농도",
        sources,
    )


def header_font(
    family,
    style_name,
    pixel_size,
    fallback_weight,
):
    font = QFont(
        family
    )

    if family == "SeoulNamsan":
        font.setStyleName(
            style_name
        )

    font.setWeight(
        fallback_weight
    )

    font.setPixelSize(
        pixel_size
    )

    return font


def choose_font_family():
    global APP_FONT_FAMILY
    global TITLE_FONT_FAMILY
    global SUBTITLE_FONT_FAMILY

    font_files = (
        "NanumBarunGothic.ttf",
        "NanumBarunGothicBold.ttf",
        "SeoulNamsanL.ttf",
        "SeoulNamsanM.ttf",
    )

    for file_name in font_files:
        font_path = os.path.join(
            ASSETS_DIR,
            file_name,
        )

        if os.path.isfile(font_path):
            QFontDatabase.addApplicationFont(
                font_path
            )

    preferred_fonts = [
        "NanumBarunGothic",
        "나눔바른고딕",
        "Nanum Barun Gothic",
        "맑은 고딕",
        "Malgun Gothic",
    ]

    try:
        installed_fonts = set(
            QFontDatabase.families()
        )
    except Exception:
        installed_fonts = set()

    if "SeoulNamsan" in installed_fonts:
        TITLE_FONT_FAMILY = "SeoulNamsan"
        SUBTITLE_FONT_FAMILY = "SeoulNamsan"

    for family in preferred_fonts:
        if family in installed_fonts:
            APP_FONT_FAMILY = family
            return family

    APP_FONT_FAMILY = "Malgun Gothic"

    return APP_FONT_FAMILY


def normalize_gateway_for_display(value):
    gateway = str(
        value or ""
    ).strip()

    if not gateway:
        return DEFAULT_GATEWAY_URL

    if "aigpt.posco.net" in gateway.lower():
        return DEFAULT_GATEWAY_URL

    return gateway


# ============================================================
# 검색어 강조
# ============================================================

HIGHLIGHT_IGNORE_WORDS = {
    "알려줘",
    "알려주세요",
    "설명",
    "설명해줘",
    "설명해주세요",
    "내용",
    "기준",
    "절차",
    "관련",
    "검색",
    "무엇",
    "어떻게",
    "해주세요",
    "해줘",
    "되나요",
    "됩니까",
    "인가요",
    "궁금해",
    "궁금합니다",
}

HIGHLIGHT_SUFFIXES = [
    "알려주세요",
    "설명해주세요",
    "알려줘",
    "설명해줘",
    "해주세요",
    "해줘",
    "작업",
    "훈련",
    "기준",
    "절차",
    "내용",
    "관련",
]


def build_highlight_terms(question):
    terms = set()

    for variant in query_variants(question):
        if len(variant) >= 2:
            terms.add(variant)

        words = re.findall(
            r"[0-9A-Za-z가-힣%]+",
            variant,
        )

        for word in words:
            cleaned = word.strip()

            if len(cleaned) < 2:
                continue

            if cleaned in HIGHLIGHT_IGNORE_WORDS:
                continue

            terms.add(cleaned)

            for suffix in HIGHLIGHT_SUFFIXES:
                if not cleaned.endswith(suffix):
                    continue

                stem = cleaned[:-len(suffix)].strip()

                if len(stem) >= 2:
                    terms.add(stem)

    return sorted(
        terms,
        key=len,
        reverse=True,
    )


def apply_search_highlights(
    browser,
    question,
):
    terms = build_highlight_terms(
        question
    )

    if not terms:
        browser.setExtraSelections([])
        return

    document = browser.document()
    selections = []
    occupied_ranges = []

    for term in terms:
        search_cursor = QTextCursor(
            document
        )

        search_cursor.movePosition(
            QTextCursor.MoveOperation.Start
        )

        while True:
            found_cursor = document.find(
                term,
                search_cursor,
            )

            if found_cursor.isNull():
                break

            start = found_cursor.selectionStart()
            end = found_cursor.selectionEnd()

            overlapped = False

            for used_start, used_end in occupied_ranges:
                if (
                    start < used_end
                    and end > used_start
                ):
                    overlapped = True
                    break

            if not overlapped:
                selection = QTextEdit.ExtraSelection()
                selection.cursor = found_cursor

                text_format = QTextCharFormat()

                text_format.setBackground(
                    QColor("#FFF176")
                )

                text_format.setForeground(
                    QColor("#3E2723")
                )

                text_format.setFontWeight(
                    700
                )

                selection.format = text_format

                selections.append(selection)

                occupied_ranges.append(
                    (
                        start,
                        end,
                    )
                )

            search_cursor.setPosition(
                end
            )

    browser.setExtraSelections(
        selections
    )


# ============================================================
# 마크다운 표시
# ============================================================

def render_inline_html(text):
    escaped = safe_text(text)

    escaped = CODE_PATTERN.sub(
        r"<code>\1</code>",
        escaped,
    )

    escaped = BOLD_PATTERN.sub(
        r"<b>\1</b>",
        escaped,
    )

    # AI가 근거 표시를 만들었더라도 화면에는 반복 표시하지 않습니다.
    escaped = CITATION_PATTERN.sub(
        "",
        escaped,
    )

    return escaped


def split_table_row(line):
    text = str(
        line or ""
    ).strip()

    if text.startswith("|"):
        text = text[1:]

    if text.endswith("|"):
        text = text[:-1]

    return [
        cell.strip()
        for cell in text.split("|")
    ]


def is_table_row(line):
    text = str(
        line or ""
    ).strip()

    if "|" not in text:
        return False

    return len(
        split_table_row(text)
    ) >= 2


def is_table_divider(line):
    text = str(
        line or ""
    ).strip()

    return (
        "-" in text
        and bool(
            TABLE_DIVIDER_PATTERN.match(
                text
            )
        )
    )


def render_table_html(rows):
    if not rows:
        return ""

    column_count = max(
        len(row)
        for row in rows
    )

    normalized_rows = []

    for row in rows:
        normalized_rows.append(
            row
            + [""] * (
                column_count
                - len(row)
            )
        )

    output = [
        '<table width="100%" border="1" cellspacing="0" cellpadding="8" '
        'style="border-collapse:collapse; border-color:#BCD0DA; '
        'margin:10px 0;">'
    ]

    for row_number, row in enumerate(
        normalized_rows
    ):
        output.append("<tr>")

        tag_name = (
            "th"
            if row_number == 0
            else "td"
        )

        background = (
            ' bgcolor="#E4F4F3"'
            if row_number == 0
            else ""
        )

        for cell in row:
            output.append(
                "<"
                + tag_name
                + background
                + ' align="left" valign="top">'
                + render_inline_html(cell)
                + "</"
                + tag_name
                + ">"
            )

        output.append("</tr>")

    output.append("</table>")

    return "".join(output)


def markdown_to_html(text):
    lines = str(
        text or ""
    ).replace(
        "\r\n",
        "\n",
    ).replace(
        "\r",
        "\n",
    ).split("\n")

    output = []
    table_rows = []
    list_tag = ""

    def close_list():
        nonlocal list_tag

        if list_tag:
            output.append(
                "</"
                + list_tag
                + ">"
            )

            list_tag = ""

    def close_table():
        nonlocal table_rows

        if table_rows:
            output.append(
                render_table_html(
                    table_rows
                )
            )

            table_rows = []

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped:
            close_list()
            close_table()

            output.append(
                '<div style="height:8px;"></div>'
            )
            continue

        if is_table_divider(
            stripped
        ):
            continue

        if is_table_row(
            stripped
        ):
            close_list()

            table_rows.append(
                split_table_row(
                    stripped
                )
            )

            continue

        close_table()

        heading_match = HEADING_PATTERN.match(
            stripped
        )

        if heading_match:
            close_list()

            markdown_level = len(
                heading_match.group(1)
            )

            html_level = (
                3
                if markdown_level <= 3
                else 4
            )

            output.append(
                "<h"
                + str(html_level)
                + ">"
                + render_inline_html(
                    heading_match.group(2)
                )
                + "</h"
                + str(html_level)
                + ">"
            )
            continue

        bullet_match = BULLET_PATTERN.match(
            stripped
        )

        ordered_match = ORDERED_PATTERN.match(
            stripped
        )

        if bullet_match or ordered_match:
            desired_tag = (
                "ul"
                if bullet_match
                else "ol"
            )

            item_text = (
                bullet_match.group(2)
                if bullet_match
                else ordered_match.group(2)
            )

            if list_tag != desired_tag:
                close_list()

                output.append(
                    "<"
                    + desired_tag
                    + ">"
                )

                list_tag = desired_tag

            output.append(
                "<li>"
                + render_inline_html(
                    item_text
                )
                + "</li>"
            )
            continue

        close_list()

        output.append(
            "<p>"
            + render_inline_html(
                stripped
            )
            + "</p>"
        )

    close_list()
    close_table()

    return "".join(output)


# ============================================================
# 사내 표준 검색 결과를 클릭 가능한 문장으로 변환
# ============================================================

def item_matches_question(text, question):
    value = compact_text(text).lower()

    return any(
        term.lower() in value
        for term in build_highlight_terms(question)
        if len(term) >= 2
    )


def concise_item_score(item):
    """표시할 때 제목 조각보다 실제 기준 문장을 우선합니다."""
    text = compact_text(
        item.get(
            "text",
            "",
        )
    )

    score = float(
        item.get(
            "score",
            0.0,
        )
        or 0.0
    )

    has_measurement = re.search(
        r"[0-9]+(?:[.][0-9]+)?\s*(?:mm|cm|m|%|ppm|시간|분|일|개월|년|회|kg|kN)",
        text,
        flags=re.IGNORECASE,
    )

    if has_measurement:
        score += 40

    if re.search(
        r"(?:이상|이하|미만|초과|이내|마다|한정|금지|실시|설치|유지)",
        text,
    ):
        score += 10

    if (
        len(text) < 28
        and has_measurement is None
    ):
        score -= 25

    return score


def render_internal_bundle(
    bundle,
    question="",
    item_mode="all",
    maximum_groups=None,
    maximum_items_per_group=None,
):
    if not bundle:
        return (
            "<h3>포스코퓨처엠 사내 표준 검색 결과</h3>"
            "<p>관련 사내 표준 근거를 찾지 못했습니다.</p>",
            [],
        )

    groups = bundle.get(
        "groups",
        [],
    )

    if not groups:
        return (
            "<h3>포스코퓨처엠 사내 표준 검색 결과</h3>"
            "<p>관련 사내 표준 근거를 찾지 못했습니다.</p>",
            [],
        )

    output = [
        "<h3>"
        + safe_text(
            bundle.get(
                "title",
                "포스코퓨처엠 사내 표준에서 확인한 내용",
            )
        )
        + "</h3>"
    ]

    source_links = []
    rendered_group_count = 0

    for group in groups:
        source_type = group.get(
            "source_type",
            "internal",
        )

        standard_name = (
            group.get(
                "standard_name",
                "",
            )
            or "표준명 미확인"
        )

        standard_number = (
            group.get(
                "standard_number",
                "",
            )
            or UNNUMBERED_SECTION_LABEL
        )

        selected_items = []

        for item in group.get(
            "items",
            [],
        ):
            matched = item_matches_question(
                item.get(
                    "text",
                    "",
                ),
                question,
            )

            if (
                item_mode == "highlighted"
                and not matched
            ):
                continue

            if (
                item_mode == "other"
                and matched
            ):
                continue

            selected_items.append(item)

        if not selected_items:
            continue

        if (
            maximum_groups is not None
            and rendered_group_count
            >= maximum_groups
        ):
            break

        if maximum_items_per_group is not None:
            selected_items = sorted(
                selected_items,
                key=concise_item_score,
                reverse=True,
            )[
                :maximum_items_per_group
            ]

        if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
            reference_metadata = [
                group.get(
                    "source_category",
                    "",
                ),
                group.get(
                    "publisher",
                    "",
                ),
                group.get(
                    "published_at",
                    "",
                ),
            ]

            reference_metadata = [
                safe_text(value)
                for value in reference_metadata
                if value
            ]

            heading_suffix = (
                " · ".join(
                    reference_metadata
                )
                or "공식 참고자료"
            )
        else:
            heading_suffix = safe_text(
                standard_number
            )

        output.append(
            "<h4>"
            + safe_text(standard_name)
            + " <span style='font-size:85%; color:#667985;'>("
            + heading_suffix
            + ")</span></h4>"
        )

        output.append(
            '<div style="margin:5px 0 12px 0;">'
        )

        for item in selected_items:
            link_number = len(
                source_links
            )

            source_links.append({
                "source_index": item.get(
                    "source_index",
                    0,
                ),
                "focus_text": item.get(
                    "focus_text",
                    "",
                ),
                "focus_heading": item.get(
                    "focus_heading",
                    "",
                ),
            })

            output.append(
                '<p style="margin:8px 0 12px 0;">'
                '<a href="sourceitem:'
                + str(link_number)
                + '" style="color:#17324B; text-decoration:none;">'
                + safe_text(
                    item.get(
                        "text",
                        "",
                    )
                ).replace(
                    "\n",
                    "<br>",
                )
                + "</a>"
                "</p>"
            )

        output.append("</div>")
        rendered_group_count += 1

    return (
        "".join(output),
        source_links,
    )


# ============================================================
# KOSHA 검색 결과 표시
# ============================================================

def select_visible_kosha_results(results, question):
    relevant = []
    other = []

    for item in results or []:
        searchable = " ".join([
            str(item.get("title", "")),
            str(item.get("content", "")),
            str(item.get("category", "")),
        ])

        if item_matches_question(
            searchable,
            question,
        ):
            relevant.append(item)
        else:
            other.append(item)

    # 형광펜 대상은 모두 처음부터 노출하고, 나머지는 최소한의
    # 제목만 보이는 요약 화면에 포함한 뒤 상세 영역으로 보냅니다.
    visible = relevant + other[:3]
    visible_ids = {
        id(item)
        for item in visible
    }

    hidden = [
        item
        for item in results or []
        if id(item) not in visible_ids
    ]

    return visible, hidden


CONCISE_QUERY_WORDS = {
    "기준",
    "규격",
    "높이",
    "주기",
    "기간",
    "횟수",
    "방법",
    "절차",
    "내용",
    "관련",
    "얼마",
    "몇",
    "알려줘",
    "알려주세요",
}


def concise_query_terms(question):
    terms = []

    for term in build_highlight_terms(
        question
    ):
        normalized = compact_text(
            term
        ).lower()

        if (
            len(normalized) < 2
            or normalized in CONCISE_QUERY_WORDS
            or " " in normalized
        ):
            continue

        if normalized not in terms:
            terms.append(normalized)

    return terms


def select_concise_kosha_results(
    results,
    question,
    maximum=1,
):
    """질문 핵심어가 실제로 들어간 법규·공단 자료만 짧게 고릅니다."""
    terms = concise_query_terms(
        question
    )

    ranked = []

    for order, item in enumerate(
        results or []
    ):
        title = compact_text(
            item.get(
                "title",
                "",
            )
        ).lower()

        content = compact_text(
            item.get(
                "content",
                "",
            )
        ).lower()

        title_hits = sum(
            1
            for term in terms
            if term in title
        )

        content_hits = sum(
            1
            for term in terms
            if term in content
        )

        if terms and not (
            title_hits
            or content_hits
        ):
            continue

        law_bonus = (
            100
            if item.get(
                "kind"
            ) == "law"
            else 0
        )

        ranked.append((
            law_bonus
            + title_hits * 20
            + content_hits * 8,
            -order,
            item,
        ))

    ranked.sort(
        key=lambda entry: (
            entry[0],
            entry[1],
        ),
        reverse=True,
    )

    return [
        entry[2]
        for entry in ranked[:maximum]
    ]


def concise_kosha_excerpt(
    item,
    question,
    maximum=280,
):
    content = str(
        item.get(
            "content",
            "",
        )
        or ""
    )

    if not content:
        return ""

    lines = [
        compact_text(line)
        for line in re.split(
            r"[\r\n]+",
            content,
        )
        if compact_text(line)
    ]

    if not lines:
        return ""

    terms = concise_query_terms(
        question
    )

    def line_score(line):
        lowered = line.lower()
        score = sum(
            len(term) * 3
            for term in terms
            if term in lowered
        )

        if re.search(
            r"[0-9]+(?:[.][0-9]+)?\s*(?:mm|cm|m|%|시간|회)",
            lowered,
        ):
            score += 8

        if "높이" in normalized_question_text(
            question
        ) and "높이" in lowered:
            score += 6

        return score

    best_line = max(
        lines,
        key=line_score,
    )

    if len(best_line) > maximum:
        best_line = (
            best_line[:maximum]
            + "…"
        )

    return best_line


def render_kosha_html(
    results,
    heading="관련 법규·안전보건공단 자료",
    question="",
):
    if not results:
        return ""

    output = [
        "<h3>"
        + safe_text(heading)
        + "</h3>",
    ]

    for item in results:
        kind = item.get(
            "kind",
            "",
        )

        if kind == "law":
            badge_color = "#DDEEFF"

        elif kind == "guide":
            badge_color = "#DFF5E3"

        else:
            badge_color = "#FFF0D9"

        category = safe_text(
            item.get(
                "category",
                "",
            )
        )

        title = safe_text(
            item.get(
                "title",
                "",
            )
        )

        content = concise_kosha_excerpt(
            item,
            question,
        )

        link = safe_text(
            item.get(
                "link",
                "",
            )
        )

        output.append(
            '<div style="margin:14px 0; padding:13px; '
            'border:1px solid #D7E1EA; border-radius:10px;">'
        )

        output.append(
            '<span style="background:'
            + badge_color
            + '; padding:4px 8px; font-weight:700;">'
            + category
            + "</span>"
        )

        output.append(
            "<p><b>"
            + title
            + "</b></p>"
        )

        if content:
            output.append(
                "<p>"
                + safe_text(content)
                + "</p>"
            )

        if link:
            if kind == "law":
                link_label = "법령 원문 보기"
            else:
                link_label = "공단 자료 보기"

            output.append(
                '<p><a href="'
                + link
                + '">'
                + link_label
                + "</a></p>"
            )

        output.append("</div>")

    output.append(
        '<p style="color:#687989;">'
        "※ 공단 API 검색 결과입니다. 링크에서 최신 원문을 확인하세요."
        "</p>"
    )

    return "".join(output)


# ============================================================
# P-GPT에 전달할 사내 문서
# ============================================================

AI_SYSTEM_PROMPT = """
당신은 포스코퓨처엠의 30년차 안전·보건·환경관리자 관점으로 답변하는
안전환경 전문 비서입니다.

규칙:
1. 제공된 포스코퓨처엠 사내 표준, 공식 질의회시·해설, 법령·공단 자료를
   우선 근거로 사용하세요.
2. 산업안전보건법, 시행령, 시행규칙, 산업안전보건기준에 관한 규칙,
   중대재해 처벌 등에 관한 법률·시행령, 대기환경보전법, 물환경보전법,
   화학물질관리법 등 안전·환경 관계법령의 최신 기준을 준수하는 관점으로
   답하세요.
3. 법령·고시와 사내 표준이 다르면 최신 법령·고시·인허가 조건을 우선하고
   각각을 구분하여 설명하세요.
4. 질의회시·해설은 해당 사실관계와 발간 당시 기준의 행정해석·참고자료로
   소개하고, 사내 표준이나 최신 법령 그 자체처럼 표현하지 마세요.
5. 관련 질의회시가 있으면 핵심 답변 뒤에 자료명과 취지를 자연스럽게 덧붙이세요.
6. 제공자료에 없는 조문, 수치, 기한, 적용대상은 추측하지 말고 최신 법령
   원문과 관할기관 확인이 필요하다고 밝혀 주세요.
7. 한국어 존댓말을 사용하고 질문에 대한 직접 답을 첫 줄에 쓰세요.
8. 수치·높이·기간·주기처럼 단답이 가능한 질문은 핵심값 한 줄만 답하고,
   꼭 필요한 예외가 있을 때만 한 줄을 덧붙이세요. 문서 전체를 요약하지 마세요.
9. 설명형 질문도 핵심 문장 또는 목록 3개 이내로 답하세요. 절차는 1), 2), 3)
   형식으로 작성하되 질문하지 않은 배경·목적·유사 기준은 넣지 마세요.
10. 수치, 주기, 책임자, 보존년한을 빠뜨리지 말고 서로 다른 표준의 내용은
   구분하세요.
11. [근거 N] 표시는 작성하지 마세요.
""".strip()


def build_ai_context(results):
    output = []
    used_length = 0

    internal_results = [
        result
        for result in results
        if result.get(
            "source_type",
            "internal",
        ) != SOURCE_TYPE_OFFICIAL_REFERENCE
    ]

    reference_results = [
        result
        for result in results
        if result.get(
            "source_type",
            "internal",
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE
    ]

    ordered_results = (
        internal_results[:3]
        + reference_results[:3]
        + internal_results[3:]
        + reference_results[3:]
    )

    for number, result in enumerate(
        ordered_results,
        start=1,
    ):
        source_type = result.get(
            "source_type",
            "internal",
        )

        if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
            metadata_lines = [
                "자료유형: "
                + (
                    result.get(
                        "source_category",
                        "",
                    )
                    or "공식 참고자료"
                ),
                "자료명: "
                + (
                    result.get(
                        "standard_name",
                        "",
                    )
                    or "미확인"
                ),
                "발행기관: "
                + (
                    result.get(
                        "publisher",
                        "",
                    )
                    or "미확인"
                ),
                "발행·기준일: "
                + (
                    result.get(
                        "published_at",
                        "",
                    )
                    or "미확인"
                ),
                "PDF 페이지: "
                + str(
                    result.get(
                        "page",
                        "미확인",
                    )
                ),
            ]
        else:
            metadata_lines = [
                "자료유형: 포스코퓨처엠 사내 표준",
                "표준명: "
                + (
                    result.get(
                        "standard_name",
                        "",
                    )
                    or "미확인"
                ),
                "표준번호: "
                + (
                    result.get(
                        "standard_number",
                        "",
                    )
                    or "미확인"
                ),
                "조항: "
                + (
                    result.get(
                        "section",
                        "",
                    )
                    or "미확인"
                ),
            ]

        block = (
            "참고 문서 "
            + str(number)
            + "\n"
            + "\n".join(
                metadata_lines
            )
            + "\n본문:\n"
            + result.get(
                "text",
                "",
            )
        )

        remaining = (
            MAX_AI_CONTEXT_CHARS
            - used_length
        )

        if remaining <= 300:
            break

        block = block[:remaining]

        output.append(block)
        used_length += len(block)

    return "\n\n----------------\n\n".join(
        output
    )


def ask_ai_with_documents(
    question,
    results,
    legal_results=None,
):
    configuration = load_configuration()

    if not configuration["use_ai"]:
        return ""

    if not configuration["p_gpt_key"]:
        return ""

    legal_results = legal_results or []

    legal_notice = ""

    if legal_results:
        legal_notice = (
            "\n\n아래 법령·공단 검색자료도 함께 검토하세요. "
            "본문에 없는 내용은 최신 원문을 확인해야 한다고 안내하세요."
        )

    return answer_general_question(
        question=(
            "아래 제공 문서를 근거로 답하세요. 자료유형을 서로 구분하세요.\n\n"
            + build_ai_context(results)
            + legal_notice
            + "\n\n질문: "
            + question
        ),
        web_results=legal_results,
        system_prompt=AI_SYSTEM_PROMPT,
    )


# ============================================================
# KOSHA 검색어
# ============================================================

KOSHA_IGNORE_WORDS = {
    "알려줘",
    "알려주세요",
    "설명",
    "설명해줘",
    "해주세요",
    "해줘",
    "되나요",
    "됩니까",
    "인가요",
    "궁금해",
    "궁금합니다",
}


def make_kosha_keyword(question):
    text = compact_text(
        question
    )

    lowered = text.lower()

    # 문장형 질문도 KOSHA 검색이 잘 되도록
    # 핵심 안전보건 용어를 우선 추출합니다.
    topic_rules = [
        (
            (
                "발끝막이판",
                "발끝 막이판",
                "토보드",
                "toe board",
            ),
            "발끝막이판",
        ),
        (
            (
                "안전난간",
                "안전 난간",
            ),
            "안전난간",
        ),
        (
            (
                "밀폐공간",
                "밀폐 공간",
                "질식",
                "산소농도",
                "유해가스",
            ),
            "밀폐공간",
        ),
        (
            (
                "작업중지권",
                "작업중지",
                "작업 중지",
            ),
            "작업중지",
        ),
        (
            (
                "소방훈련",
                "소방 훈련",
                "화재훈련",
                "소화훈련",
                "대피훈련",
            ),
            "소방훈련",
        ),
        (
            (
                "안전관리비",
                "안전 관리비",
                "산업안전보건관리비",
            ),
            "산업안전보건관리비",
        ),
        (
            (
                "접지",
                "감전",
                "전기작업",
                "정전작업",
            ),
            "접지 전기작업",
        ),
        (
            (
                "화기작업",
                "화기 작업",
                "용접",
                "용단",
            ),
            "화기작업",
        ),
        (
            (
                "고소작업",
                "고소 작업",
                "추락",
                "안전대",
            ),
            "고소작업 추락",
        ),
        (
            (
                "위험성평가",
                "위험성 평가",
            ),
            "위험성평가",
        ),
        (
            (
                "중량물",
                "크레인",
                "양중",
                "경고표지",
                "안내표시",
                "취급주의",
                "중량물 표시",
                "중량물 표지",
            ),
            "중량물 경고표지",
        ),
    ]

    for trigger_words, search_word in topic_rules:
        for trigger in trigger_words:
            if trigger.lower() in lowered:
                return search_word

    words = re.findall(
        "[0-9A-Za-z가-힣]+",
        text,
    )

    ignore_words = {
        "알려줘",
        "알려주세요",
        "설명",
        "설명해줘",
        "해주세요",
        "해줘",
        "되나요",
        "됩니까",
        "인가요",
        "궁금해",
        "궁금해요",
        "궁금합니다",
        "대상",
        "무엇",
        "어떤",
        "관련",
        "내용",
    }

    selected = []

    for word in words:
        if word in ignore_words:
            continue

        if len(word) < 2:
            continue

        selected.append(
            word
        )

    if not selected:
        return text

    return " ".join(
        selected[:4]
    )


def make_kosha_keywords(question):
    """한 가지 표현에 의존하지 않도록 법령 검색어를 여러 형태로 만듭니다."""
    text = compact_text(question).lower()
    keywords = [
        make_kosha_keyword(question),
    ]

    if "중량물" in text or any(
        word in text
        for word in (
            "경고표지",
            "안내표시",
            "취급주의",
            "중량물 표시",
            "중량물 표지",
        )
    ):
        keywords.extend([
            "중량물 안내표시",
            "중량물 취급주의 표지",
            "중량물 표시",
            "중량물 무게중심 표시",
        ])

    unique = []

    for keyword in keywords:
        value = compact_text(keyword)

        if value and value.lower() not in {
            item.lower()
            for item in unique
        }:
            unique.append(value)

    return unique


def search_kosha_for_question(
    question,
    api_key,
    maximum=10,
):
    """동의어별 KOSHA 결과를 합쳐 법령·공단 자료 누락을 줄입니다."""
    combined = []
    seen = set()

    for keyword in make_kosha_keywords(question):
        try:
            results = search_kosha(
                keyword,
                api_key,
                maximum=maximum,
            )
        except Exception:
            raise

        for item in results:
            identity = (
                item.get("category", ""),
                item.get("title", ""),
                item.get("link", ""),
            )

            if identity in seen:
                continue

            seen.add(identity)
            combined.append(item)

    combined.sort(
        key=lambda item: (
            item.get("priority", 99),
            item.get("title", ""),
        )
    )

    return combined[:maximum]



# ============================================================
# 자동 높이 답변창
# ============================================================

class AutoHeightTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.last_height = 0

        self.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.document().documentLayout().documentSizeChanged.connect(
            self.update_document_height
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_document_height()

    def update_document_height(self, *args):
        del args

        width = self.viewport().width()

        if width > 0:
            self.document().setTextWidth(
                width
            )

        height = max(
            50,
            int(
                self.document().size().height()
            ) + 24,
        )

        if abs(
            height - self.last_height
        ) < 3:
            return

        self.last_height = height

        self.setFixedHeight(
            height
        )


class CollapsibleDetails(QWidget):
    expanded_changed = Signal(bool)

    def __init__(
        self,
        browser,
        label="상세 내용 펼쳐보기",
        parent=None,
    ):
        super().__init__(parent)

        self.browser = browser
        self.button = QPushButton(label)
        self.button.setObjectName("detailsButton")
        self.button.setCheckable(True)
        self.button.clicked.connect(self.toggle)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.button)
        layout.addWidget(self.browser)

        self.browser.setVisible(False)

    def toggle(self, checked):
        self.browser.setVisible(checked)

        if checked:
            self.button.setText("상세 내용 접기")
            QTimer.singleShot(
                50,
                self.browser.update_document_height,
            )
        else:
            self.button.setText("상세 내용 펼쳐보기")

        self.expanded_changed.emit(checked)


# ============================================================
# 캐릭터 이미지
# ============================================================

def draw_default_mascot(size):
    pixmap = QPixmap(
        size,
        size,
    )

    pixmap.fill(
        Qt.GlobalColor.transparent
    )

    painter = QPainter(pixmap)

    painter.setRenderHint(
        QPainter.RenderHint.Antialiasing
    )

    painter.setPen(
        Qt.PenStyle.NoPen
    )

    painter.setBrush(
        QColor("#F6DDB4")
    )

    painter.drawEllipse(
        int(size * 0.18),
        int(size * 0.28),
        int(size * 0.64),
        int(size * 0.58),
    )

    painter.setBrush(
        QColor("#FFC800")
    )

    painter.drawEllipse(
        int(size * 0.20),
        int(size * 0.14),
        int(size * 0.60),
        int(size * 0.34),
    )

    painter.setBrush(
        QColor("#4A3A24")
    )

    painter.drawEllipse(
        int(size * 0.36),
        int(size * 0.50),
        int(size * 0.07),
        int(size * 0.09),
    )

    painter.drawEllipse(
        int(size * 0.57),
        int(size * 0.50),
        int(size * 0.07),
        int(size * 0.09),
    )

    painter.end()

    return pixmap


def load_mascot_source_pixmap():
    if "source" in PIXMAP_CACHE:
        return PIXMAP_CACHE["source"]

    for file_name in MASCOT_FILE_NAMES:
        path = os.path.join(
            ASSETS_DIR,
            file_name,
        )

        if not os.path.isfile(path):
            continue

        pixmap = QPixmap(path)

        if pixmap.isNull():
            continue

        PIXMAP_CACHE["source"] = pixmap

        print(
            "[캐릭터 이미지] "
            + path
        )

        return pixmap

    fallback = draw_default_mascot(
        320
    )

    PIXMAP_CACHE["source"] = fallback

    return fallback


def mascot_pixmap(
    size,
    head_only=False,
):
    cache_key = (
        str(size)
        + "_"
        + str(head_only)
    )

    if cache_key in PIXMAP_CACHE:
        return PIXMAP_CACHE[
            cache_key
        ]

    source = load_mascot_source_pixmap()
    working = source

    if head_only:
        working = source.copy(
            0,
            0,
            source.width(),
            int(
                source.height()
                * 0.58
            ),
        )

    scaled = working.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    PIXMAP_CACHE[cache_key] = scaled

    return scaled


# ============================================================
# 원문에서 클릭한 위치 추출
# ============================================================

def is_heading_text(text):
    value = str(
        text or ""
    ).strip()

    if not value:
        return False

    if (
        value.startswith("[")
        and "]" in value[:100]
    ):
        return True

    if ARTICLE_HEADING_PATTERN.match(
        value
    ):
        return True

    return False


def build_source_excerpt(
    source_text,
    focus_text,
    focus_heading,
):
    lines = [
        line.rstrip()
        for line in str(
            source_text or ""
        ).splitlines()
    ]

    if not lines:
        return ""

    normalized_focus = compact_text(
        focus_text
    )

    focus_index = None

    if normalized_focus:
        focus_prefix = normalized_focus[:120]

        for index, line in enumerate(lines):
            normalized_line = compact_text(
                line
            )

            if not normalized_line:
                continue

            if (
                normalized_focus in normalized_line
                or focus_prefix in normalized_line
                or normalized_line in normalized_focus
            ):
                focus_index = index
                break

    if (
        focus_index is None
        and focus_heading
    ):
        normalized_heading = compact_text(
            focus_heading
        )

        for index, line in enumerate(lines):
            if normalized_heading in compact_text(
                line
            ):
                focus_index = index
                break

    if focus_index is None:
        for index, line in enumerate(lines):
            if line.strip():
                focus_index = index
                break

    if focus_index is None:
        return ""

    start_index = focus_index

    for index in range(
        focus_index,
        max(
            -1,
            focus_index - 18,
        ),
        -1,
    ):
        if is_heading_text(
            lines[index]
        ):
            start_index = index
            break

    end_index = min(
        len(lines),
        focus_index + 16,
    )

    # 다음 큰 조항이 나오면 거기에서 중단합니다.
    for index in range(
        focus_index + 1,
        min(
            len(lines),
            focus_index + 20,
        ),
    ):
        if (
            index > focus_index + 2
            and is_heading_text(
                lines[index]
            )
        ):
            end_index = index
            break

    excerpt = "\n".join(
        lines[
            start_index:
            end_index
        ]
    ).strip()

    return excerpt


# ============================================================
# 원문 근거 창
# ============================================================

class SourceDialog(QDialog):
    def __init__(
        self,
        source,
        question,
        focus_text,
        focus_heading,
        font_size,
        parent=None,
    ):
        super().__init__(parent)

        self.question = question
        self.focus_text = focus_text

        self.font_size = max(
            MIN_CONTENT_FONT_SIZE,
            font_size - 1,
        )

        standard_name = (
            source.get(
                "standard_name",
                "",
            )
            or "표준명 미확인"
        )

        standard_number = (
            source.get(
                "standard_number",
                "",
            )
            or UNNUMBERED_SECTION_LABEL
        )

        revision = (
            source.get(
                "revision",
                "",
            )
            or "미확인"
        )

        source_type = source.get(
            "source_type",
            "internal",
        )

        self.setWindowTitle(
            standard_name
        )

        self.resize(
            900,
            720,
        )

        root = QVBoxLayout(self)

        root.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        root.setSpacing(9)

        # 실제 지침서 제목을 가장 크게 표시합니다.
        title_label = QLabel(
            standard_name
        )

        title_label.setWordWrap(True)

        title_label.setStyleSheet(
            "font-size:"
            + str(self.font_size + 4)
            + "px;"
            "font-weight:700;"
            "color:#102A49;"
        )

        if source_type == SOURCE_TYPE_OFFICIAL_REFERENCE:
            metadata_parts = [
                source.get(
                    "source_category",
                    "",
                ),
                source.get(
                    "publisher",
                    "",
                ),
                source.get(
                    "published_at",
                    "",
                ),
            ]

            page_number = source.get(
                "page",
                "",
            )

            if page_number:
                metadata_parts.append(
                    "PDF "
                    + str(page_number)
                    + "쪽"
                )

            metadata_text = " · ".join(
                str(value)
                for value in metadata_parts
                if value
            )
        else:
            metadata_text = (
                standard_number
                + " · Rev. "
                + revision
            )

        metadata_label = QLabel(
            metadata_text
        )

        metadata_label.setWordWrap(True)

        metadata_label.setStyleSheet(
            "font-size:"
            + str(
                max(
                    self.font_size - 3,
                    11,
                )
            )
            + "px;"
            "color:#687989;"
        )

        if focus_heading:
            section_label = QLabel(
                focus_heading
            )

            section_label.setWordWrap(True)

            section_label.setStyleSheet(
                "font-size:"
                + str(self.font_size)
                + "px;"
                "font-weight:700;"
                "color:#0C5E64;"
                "background:#E7F7F5;"
                "border-radius:8px;"
                "padding:8px;"
            )
        else:
            section_label = None

        excerpt = build_source_excerpt(
            source.get(
                "text",
                "",
            ),
            focus_text,
            focus_heading,
        )

        self.browser = QTextBrowser()

        self.browser.setPlainText(
            excerpt
        )

        self.apply_font()

        apply_search_highlights(
            self.browser,
            question,
        )

        smaller_button = QPushButton(
            "가-"
        )

        larger_button = QPushButton(
            "가+"
        )

        copy_button = QPushButton(
            "원문 복사"
        )

        close_button = QPushButton(
            "닫기"
        )

        smaller_button.clicked.connect(
            lambda: self.change_font(-1)
        )

        larger_button.clicked.connect(
            lambda: self.change_font(1)
        )

        copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(
                excerpt
            )
        )

        close_button.clicked.connect(
            self.accept
        )

        button_layout = QHBoxLayout()

        button_layout.addWidget(
            smaller_button
        )

        button_layout.addWidget(
            larger_button
        )

        button_layout.addStretch()

        button_layout.addWidget(
            copy_button
        )

        button_layout.addWidget(
            close_button
        )

        root.addWidget(
            title_label
        )

        root.addWidget(
            metadata_label
        )

        if section_label is not None:
            root.addWidget(
                section_label
            )

        root.addWidget(
            self.browser,
            1,
        )

        root.addLayout(
            button_layout
        )

        self.setStyleSheet(
            """
            QDialog {
                background:#F5F7FA;
            }

            QTextBrowser {
                background:white;
                color:#1F344D;
                border:1px solid #D7E1EA;
                border-radius:12px;
                padding:15px;
            }

            QPushButton {
                background:#00A19C;
                color:white;
                border:none;
                border-radius:9px;
                padding:9px 18px;
                font-size:14px;
                font-weight:700;
            }

            QPushButton:hover {
                background:#008B87;
            }
            """
        )

        QTimer.singleShot(
            120,
            self.move_to_focus
        )

    def apply_font(self):
        self.browser.setFont(
            QFont(
                APP_FONT_FAMILY,
                self.font_size,
            )
        )

    def change_font(self, amount):
        self.font_size = max(
            MIN_CONTENT_FONT_SIZE,
            min(
                MAX_CONTENT_FONT_SIZE,
                self.font_size + amount,
            ),
        )

        self.apply_font()

        apply_search_highlights(
            self.browser,
            self.question,
        )

        self.move_to_focus()

    def move_to_focus(self):
        cursor = QTextCursor(
            self.browser.document()
        )

        if self.focus_text:
            cursor = self.browser.document().find(
                self.focus_text[:120]
            )

        if cursor.isNull():
            for term in build_highlight_terms(
                self.question
            ):
                cursor = self.browser.document().find(
                    term
                )

                if not cursor.isNull():
                    break

        if cursor.isNull():
            cursor = QTextCursor(
                self.browser.document()
            )

            cursor.movePosition(
                QTextCursor.MoveOperation.Start
            )

        self.browser.setTextCursor(
            cursor
        )

        self.browser.ensureCursorVisible()


# ============================================================
# API 설정 창
# ============================================================

class ApiSettingsDialog(QDialog):
    settings_saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        configuration = load_configuration()

        self.setWindowTitle(
            "개인 API 및 KOSHA 설정"
        )

        self.resize(
            660,
            455,
        )

        root = QVBoxLayout(self)

        root.setContentsMargins(
            22,
            20,
            22,
            20,
        )

        root.setSpacing(14)

        title = QLabel(
            "개인 API 및 안전보건공단 설정"
        )

        title.setStyleSheet(
            "font-size:21px;"
            "font-weight:700;"
            "color:#102A49;"
        )

        description = QLabel(
            "P-GPT는 일반 대화와 사내 문서 요약에 사용합니다.\n"
            "KOSHA API는 법규·가이드·교육자료 검색에 사용합니다."
        )

        description.setWordWrap(True)

        form = QFormLayout()
        form.setSpacing(11)

        gateway_value = normalize_gateway_for_display(
            configuration["gateway_url"]
        )

        self.gateway_input = QLineEdit(
            gateway_value
        )

        self.gateway_input.setPlaceholderText(
            DEFAULT_GATEWAY_URL
        )

        self.p_gpt_key_input = QLineEdit(
            configuration["p_gpt_key"]
        )

        self.p_gpt_key_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.p_gpt_key_input.setPlaceholderText(
            "직원 개인 P-GPT API 키"
        )

        self.model_input = QLineEdit(
            configuration["model_name"]
        )

        self.model_input.setPlaceholderText(
            DEFAULT_MODEL_NAME
        )

        self.kosha_key_input = QLineEdit(
            configuration["kosha_key"]
        )

        self.kosha_key_input.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        self.kosha_key_input.setPlaceholderText(
            "공공데이터포털 Decoding 인증키"
        )

        self.use_ai_checkbox = QCheckBox(
            "P-GPT 답변 정리 및 일반 대화 사용"
        )

        self.use_ai_checkbox.setChecked(
            configuration["use_ai"]
        )

        self.use_kosha_checkbox = QCheckBox(
            "KOSHA 법규·가이드·교육자료 검색"
        )

        self.use_kosha_checkbox.setChecked(
            configuration["use_kosha"]
        )

        form.addRow(
            "PAI 게이트웨이",
            self.gateway_input,
        )

        form.addRow(
            "P-GPT API 키",
            self.p_gpt_key_input,
        )

        form.addRow(
            "P-GPT 모델",
            self.model_input,
        )

        form.addRow(
            "KOSHA API 키",
            self.kosha_key_input,
        )

        form.addRow(
            "",
            self.use_ai_checkbox,
        )

        form.addRow(
            "",
            self.use_kosha_checkbox,
        )

        test_button = QPushButton(
            "P-GPT 연결 테스트"
        )

        delete_button = QPushButton(
            "저장 키 삭제"
        )

        cancel_button = QPushButton(
            "취소"
        )

        save_button = QPushButton(
            "저장"
        )

        test_button.clicked.connect(
            self.test_connection
        )

        delete_button.clicked.connect(
            self.delete_keys
        )

        cancel_button.clicked.connect(
            self.reject
        )

        save_button.clicked.connect(
            self.save_values
        )

        buttons = QHBoxLayout()

        buttons.addWidget(
            test_button
        )

        buttons.addWidget(
            delete_button
        )

        buttons.addStretch()

        buttons.addWidget(
            cancel_button
        )

        buttons.addWidget(
            save_button
        )

        root.addWidget(title)
        root.addWidget(description)
        root.addLayout(form)
        root.addStretch()
        root.addLayout(buttons)

        self.setStyleSheet(
            """
            QDialog {
                background:#F5F7FA;
            }

            QLineEdit {
                background:white;
                border:1px solid #C9D7E1;
                border-radius:8px;
                padding:9px;
                font-size:14px;
            }

            QCheckBox {
                color:#17324B;
                font-size:14px;
            }

            QPushButton {
                background:#00A19C;
                color:white;
                border:none;
                border-radius:9px;
                padding:9px 16px;
                font-size:13px;
                font-weight:700;
            }

            QPushButton:hover {
                background:#008B87;
            }
            """
        )

    def current_values(self):
        return {
            "gateway_url": (
                self.gateway_input.text().strip()
                or DEFAULT_GATEWAY_URL
            ),
            "p_gpt_key": (
                self.p_gpt_key_input.text().strip()
            ),
            "model_name": (
                self.model_input.text().strip()
                or DEFAULT_MODEL_NAME
            ),
            "kosha_key": (
                self.kosha_key_input.text().strip()
            ),
            "use_ai": (
                self.use_ai_checkbox.isChecked()
            ),
            "use_kosha": (
                self.use_kosha_checkbox.isChecked()
            ),
        }

    def test_connection(self):
        values = self.current_values()

        if not values["p_gpt_key"]:
            QMessageBox.warning(
                self,
                "연결 테스트",
                "P-GPT API 키를 입력해 주세요.",
            )
            return

        QApplication.setOverrideCursor(
            Qt.CursorShape.WaitCursor
        )

        try:
            answer = test_p_gpt(
                values["gateway_url"],
                values["p_gpt_key"],
                values["model_name"],
            )

            QMessageBox.information(
                self,
                "연결 성공",
                "P-GPT 연결에 성공했습니다.\n\n"
                + answer[:200],
            )

        except Exception as error:
            print(
                "[P-GPT 연결 테스트 실패] "
                + str(error)
            )

            QMessageBox.critical(
                self,
                "연결 실패",
                "P-GPT에 연결하지 못했습니다.\n\n"
                + str(error)[:900],
            )

        finally:
            QApplication.restoreOverrideCursor()

    def save_values(self):
        values = self.current_values()

        if (
            values["use_ai"]
            and not values["p_gpt_key"]
        ):
            QMessageBox.warning(
                self,
                "설정 확인",
                "P-GPT 사용 시 개인 API 키가 필요합니다.",
            )
            return

        if (
            values["use_kosha"]
            and not values["kosha_key"]
        ):
            QMessageBox.warning(
                self,
                "설정 확인",
                "KOSHA 검색 사용 시 공공데이터포털 키가 필요합니다.",
            )
            return

        save_configuration(
            values["gateway_url"],
            values["model_name"],
            values["use_ai"],
            values["use_kosha"],
            False,
            values["p_gpt_key"],
            values["kosha_key"],
            "",
            "",
        )

        self.settings_saved.emit()
        self.accept()

    def delete_keys(self):
        remove_saved_keys()

        self.p_gpt_key_input.clear()
        self.kosha_key_input.clear()

        self.use_ai_checkbox.setChecked(
            False
        )

        self.use_kosha_checkbox.setChecked(
            False
        )

        QMessageBox.information(
            self,
            "키 삭제",
            "저장된 개인 API 키를 삭제했습니다.",
        )


# ============================================================
# 질문 책갈피
# ============================================================

class BookmarkButton(QPushButton):
    selected = Signal(int)
    delete_requested = Signal(int)

    def __init__(
        self,
        history_id,
        title,
        color,
        parent=None,
    ):
        super().__init__(
            title,
            parent,
        )

        self.history_id = int(
            history_id
        )

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.setToolTip(
            title
        )

        self.setMinimumHeight(
            54
        )

        self.setMaximumWidth(
            BOOKMARK_WIDTH - 18
        )

        self.setStyleSheet(
            "QPushButton {"
            "background:"
            + color
            + ";"
            "color:#263238;"
            "border:none;"
            "border-left:7px solid rgba(0,0,0,35);"
            "border-radius:3px 11px 11px 3px;"
            "padding:8px;"
            "font-size:13px;"
            "font-weight:700;"
            "text-align:left;"
            "}"
            "QPushButton:hover {"
            "border:2px solid #00A19C;"
            "border-left:7px solid #00A19C;"
            "}"
        )

        self.clicked.connect(
            lambda: self.selected.emit(
                self.history_id
            )
        )

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        delete_action = menu.addAction(
            "이 질문 삭제"
        )

        selected_action = menu.exec(
            event.globalPos()
        )

        if selected_action == delete_action:
            self.delete_requested.emit(
                self.history_id
            )


# ============================================================
# 뉴스 수집 스레드
# ============================================================

class NewsRefreshWorker(QThread):
    completed = Signal(
        int,
        int,
        str,
    )

    def run(self):
        try:
            news_items = fetch_safety_news()

            result = save_news_items(
                news_items
            )

            self.completed.emit(
                result["inserted"],
                result["updated"],
                "",
            )

        except Exception as error:
            self.completed.emit(
                0,
                0,
                str(error),
            )


# ============================================================
# 누적 안전뉴스 창
# ============================================================

class NewsDialog(QDialog):
    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.worker = None
        self.visible_count = NEWS_PAGE_SIZE
        self.loading_more = False

        self.setWindowTitle(
            "실시간 산업안전 뉴스"
        )

        self.resize(
            860,
            740,
        )

        root = QVBoxLayout(self)

        root.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        root.setSpacing(
            10
        )

        title = QLabel(
            "실시간 산업안전 뉴스"
        )

        title.setStyleSheet(
            "font-size:22px;"
            "font-weight:700;"
            "color:#102A49;"
        )

        self.status_label = QLabel(
            "저장된 뉴스를 불러오는 중입니다."
        )

        self.status_label.setStyleSheet(
            "font-size:13px;"
            "color:#687989;"
        )

        self.browser = QTextBrowser()

        self.browser.setOpenLinks(
            False
        )

        self.browser.setOpenExternalLinks(
            False
        )

        self.browser.anchorClicked.connect(
            self.open_link
        )

        self.browser.verticalScrollBar().valueChanged.connect(
            self.check_scroll_bottom
        )

        refresh_button = QPushButton(
            "최신 뉴스 다시 수집"
        )

        clear_button = QPushButton(
            "뉴스 기록 삭제"
        )

        close_button = QPushButton(
            "닫기"
        )

        refresh_button.clicked.connect(
            self.start_news_refresh
        )

        clear_button.clicked.connect(
            self.clear_news
        )

        close_button.clicked.connect(
            self.accept
        )

        bottom = QHBoxLayout()

        bottom.addWidget(
            refresh_button
        )

        bottom.addWidget(
            clear_button
        )

        bottom.addStretch()

        bottom.addWidget(
            close_button
        )

        root.addWidget(title)
        root.addWidget(
            self.status_label
        )
        root.addWidget(
            self.browser,
            1,
        )
        root.addLayout(bottom)

        self.setStyleSheet(
            """
            QDialog {
                background:#F5F7FA;
            }

            QTextBrowser {
                background:#F7F9FB;
                border:1px solid #D7E1EA;
                border-radius:12px;
                padding:14px;
                font-size:16px;
                color:#1D324C;
            }

            QPushButton {
                background:#00A19C;
                color:white;
                border:none;
                border-radius:9px;
                padding:9px 16px;
                font-size:14px;
                font-weight:700;
            }

            QPushButton:hover {
                background:#008B87;
            }
            """
        )

        # 저장된 뉴스를 먼저 표시한 후 자동으로 최신 뉴스를 수집합니다.
        self.refresh_display()

        QTimer.singleShot(
            250,
            self.start_news_refresh,
        )

    def news_cards_html(self, items):
        if not items:
            return (
                "<div style='padding:25px;'>"
                "<h3>저장된 산업안전 뉴스가 없습니다.</h3>"
                "<p>최신 뉴스를 자동 수집하고 있습니다.</p>"
                "</div>"
            )

        colors = [
            "#E8F4FD",
            "#E7F7F0",
            "#FFF3DE",
            "#F3EAFB",
            "#FFE9ED",
        ]

        output = []

        for index, item in enumerate(
            items
        ):
            title = safe_text(
                item.get(
                    "title",
                    "",
                )
            )

            source = safe_text(
                item.get(
                    "source",
                    "",
                )
            )

            published = safe_text(
                item.get(
                    "published",
                    "",
                )
            )

            link = safe_text(
                item.get(
                    "link",
                    "",
                )
            )

            color = colors[
                index % len(colors)
            ]

            output.append(
                '<div style="'
                'background:'
                + color
                + ";"
                'border:1px solid #D5E0E7;'
                'border-radius:12px;'
                'padding:14px 16px;'
                'margin:10px 2px;'
                '">'
            )

            if link:
                output.append(
                    '<a href="'
                    + link
                    + '" style="'
                    'font-size:17px;'
                    'font-weight:700;'
                    'color:#143C50;'
                    'text-decoration:none;'
                    '">'
                    + title
                    + "</a>"
                )
            else:
                output.append(
                    '<span style="'
                    'font-size:17px;'
                    'font-weight:700;'
                    'color:#143C50;'
                    '">'
                    + title
                    + "</span>"
                )

            output.append(
                '<div style="'
                'margin-top:7px;'
                'font-size:12px;'
                'color:#6C7B87;'
                '">'
                + source
                + (
                    " · "
                    + published
                    if published
                    else ""
                )
                + "</div>"
            )

            output.append(
                "</div>"
            )

        return "".join(
            output
        )

    def refresh_display(
        self,
        preserve_position=False,
    ):
        scroll_bar = (
            self.browser.verticalScrollBar()
        )

        previous_value = (
            scroll_bar.value()
        )

        total_count = (
            count_saved_news()
        )

        items = list_saved_news(
            limit=self.visible_count,
            offset=0,
        )

        self.status_label.setText(
            "누적 "
            + str(total_count)
            + "건 · 현재 "
            + str(len(items))
            + "건 표시"
        )

        self.browser.setHtml(
            self.news_cards_html(
                items
            )
        )

        if preserve_position:
            QTimer.singleShot(
                50,
                lambda value=previous_value:
                self.browser.verticalScrollBar().setValue(
                    value
                ),
            )
        else:
            self.browser.moveCursor(
                QTextCursor.MoveOperation.Start
            )

    def check_scroll_bottom(
        self,
        value,
    ):
        if self.loading_more:
            return

        scroll_bar = (
            self.browser.verticalScrollBar()
        )

        if (
            value
            < scroll_bar.maximum() - 80
        ):
            return

        total_count = count_saved_news()

        if self.visible_count >= total_count:
            return

        self.loading_more = True

        self.visible_count += (
            NEWS_PAGE_SIZE
        )

        self.refresh_display(
            preserve_position=True,
        )

        self.loading_more = False

    def start_news_refresh(self):
        if (
            self.worker is not None
            and self.worker.isRunning()
        ):
            return

        self.status_label.setText(
            "최신 산업안전 뉴스를 자동 수집하고 있습니다..."
        )

        self.worker = NewsRefreshWorker()

        self.worker.completed.connect(
            self.news_refresh_completed
        )

        self.worker.start()

    def news_refresh_completed(
        self,
        inserted,
        updated,
        error,
    ):
        if error:
            print(
                "[안전뉴스 수집 오류] "
                + error
            )

            self.status_label.setText(
                "일부 뉴스 수집에 실패했습니다. "
                "저장된 뉴스는 계속 볼 수 있습니다."
            )
        else:
            self.status_label.setText(
                "새 기사 "
                + str(inserted)
                + "건 추가 · 기존 기사 "
                + str(updated)
                + "건 확인"
            )

        self.refresh_display()

    def open_link(self, url):
        value = url.toString().strip()

        if value.startswith(
            ("http://", "https://")
        ):
            QDesktopServices.openUrl(
                QUrl(value)
            )

    def clear_news(self):
        result = QMessageBox.question(
            self,
            "뉴스 기록 삭제",
            "누적된 안전뉴스를 모두 삭제하시겠습니까?",
        )

        if (
            result
            != QMessageBox.StandardButton.Yes
        ):
            return

        clear_saved_news()

        self.visible_count = (
            NEWS_PAGE_SIZE
        )

        self.refresh_display()


# ============================================================
# 질문 처리 스레드
# ============================================================

class SearchWorker(QThread):
    completed = Signal(
        str,
        list,
        list,
        bool,
    )

    def __init__(
        self,
        question,
        chunks,
        index,
    ):
        super().__init__()

        self.question = question
        self.chunks = chunks
        self.index = index

    def run(self):
        question = (
            self.question.strip()
        )

        if is_greeting(
            question
        ):
            self.completed.emit(
                greeting_answer(
                    question
                ),
                [],
                [],
                False,
            )
            return

        configuration = (
            load_configuration()
        )

        internal_results = []
        reference_results = []

        try:
            internal_results = search_documents(
                question,
                self.chunks,
                self.index,
            )

        except Exception as error:
            print(
                "[사내 문서 검색 오류] "
                + str(error)
            )

        try:
            reference_results = search_reference_documents(
                question,
                self.chunks,
                self.index,
            )

        except Exception as error:
            print(
                "[질의회시·공식 자료 검색 오류] "
                + str(error)
            )

        document_results = (
            internal_results
            + reference_results
        )

        document_question = (
            looks_like_document_question(
                question
            )
            or bool(document_results)
        )

        if document_question:
            kosha_results = []

            if (
                configuration["use_kosha"]
                and configuration["kosha_key"]
            ):
                try:
                    kosha_results = search_kosha_for_question(
                        question,
                        configuration[
                            "kosha_key"
                        ],
                        maximum=10,
                    )

                except Exception as error:
                    print(
                        "[KOSHA 검색 오류] "
                        + str(error)
                    )

            if document_results:
                compact_answer = compact_fact_history_answer(
                    question
                )

                if (
                    compact_answer
                    and find_compact_fact_source(
                        question,
                        document_results,
                    ) is not None
                ):
                    self.completed.emit(
                        compact_answer,
                        document_results,
                        kosha_results,
                        True,
                    )
                    return

                ai_answer = ""

                if (
                    configuration["use_ai"]
                    and configuration["p_gpt_key"]
                ):
                    try:
                        ai_answer = ask_ai_with_documents(
                            question,
                            document_results,
                            kosha_results,
                        )

                    except Exception as error:
                        print(
                            "[P-GPT 문서 답변 실패] "
                            + str(error)
                        )

                if not ai_answer:
                    ai_answer = ""

                self.completed.emit(
                    ai_answer,
                    document_results,
                    kosha_results,
                    True,
                )
                return

            # 문서 질문이지만 사내 자료가 없을 때도
            # P-GPT가 설정되어 있으면 일반 답변을 시도합니다.
            try:
                general_answer = (
                    answer_general_question(
                        question,
                        kosha_results,
                    )
                )
            except Exception as error:
                print(
                    "[P-GPT 일반 답변 실패] "
                    + str(error)
                )

                general_answer = ""

            if not general_answer:
                general_answer = (
                    "### 안내\n\n"
                    "사내 문서에서 직접 관련된 내용을 찾지 못했습니다.\n\n"
                    "아래 안전보건공단 자료가 있으면 함께 확인해 주세요."
                )

            self.completed.emit(
                general_answer,
                [],
                kosha_results,
                bool(kosha_results),
            )
            return

        # 일반 질문은 P-GPT로 바로 전달합니다.
        try:
            general_answer = (
                answer_general_question(
                    question,
                    [],
                )
            )

        except Exception as error:
            print(
                "[P-GPT 일반 질문 실패] "
                + str(error)
            )

            general_answer = ""

        if not general_answer:
            general_answer = (
                "### 안내\n\n"
                "일반 질문에 답하려면 개인 API 설정에서 "
                "P-GPT 사용을 켜고 연결 테스트를 완료해 주세요."
            )

        self.completed.emit(
            general_answer,
            [],
            [],
            False,
        )


# ============================================================
# 채팅창
# ============================================================

# 사내 표준에서 답이 확인된 단답형 질문만 예시로 둡니다.
# 새 예시를 넣기 전에 verify_example_questions.py 로 답이 나오는지 잽니다.
EXAMPLE_QUESTIONS = (
    "밀폐공간 산소농도",
    "발끝막이판 높이 기준",
    "안전작업허가 유효기간",
    "안전난간 높이 기준",
    "작업환경측정 주기",
)


class ChatWindow(QMainWindow):
    settings_requested = Signal()
    news_requested = Signal()

    def __init__(
        self,
        chunks,
        index,
        errors,
    ):
        super().__init__()

        self.chunks = chunks
        self.index = index
        self.errors = errors

        self.worker = None
        self.loading_widget = None
        self.allow_close = False

        self.current_question = ""
        self.current_question_widget = None

        self.answer_browsers = []
        self.bookmark_buttons = {}
        self.history_widgets = {}

        self.find_matches = []
        self.current_find_match = -1

        self.settings = app_settings()

        saved_size = self.settings.value(
            "content_font_size",
            DEFAULT_CONTENT_FONT_SIZE,
        )

        try:
            self.content_font_size = int(
                saved_size
            )
        except Exception:
            self.content_font_size = (
                DEFAULT_CONTENT_FONT_SIZE
            )

        self.content_font_size = max(
            MIN_CONTENT_FONT_SIZE,
            min(
                MAX_CONTENT_FONT_SIZE,
                self.content_font_size,
            ),
        )

        self.setWindowTitle(
            APP_NAME
        )

        self.setWindowIcon(
            QIcon(
                mascot_pixmap(
                    128,
                    True,
                )
            )
        )

        self.resize(
            980,
            850,
        )

        self.setMinimumSize(
            760,
            650,
        )

        self.build_ui()
        self.setup_shortcuts()
        self.apply_style()
        self.place_bottom_right()
        self.load_bookmarks()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self):
        central = QWidget()

        central.setObjectName(
            "centralWidget"
        )

        root = QVBoxLayout(
            central
        )

        root.setContentsMargins(
            12,
            10,
            12,
            10,
        )

        root.setSpacing(
            8
        )

        header = QFrame()

        header.setObjectName(
            "headerFrame"
        )

        header_layout = QHBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            14,
            6,
            14,
            6,
        )

        header_layout.setSpacing(
            10
        )

        icon = QLabel()

        icon.setPixmap(
            mascot_pixmap(
                106,
                False,
            )
        )

        icon.setFixedSize(
            106,
            106,
        )

        icon.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        title_layout = QVBoxLayout()

        title_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        title_layout.setSpacing(
            5
        )

        title_label = QLabel(
            HEADER_TITLE
        )

        title_label.setObjectName(
            "headerTitle"
        )

        title_label.setFont(
            header_font(
                TITLE_FONT_FAMILY,
                "M",
                30,
                QFont.Weight.Bold,
            )
        )

        title_label.setWordWrap(
            True
        )

        title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        subtitle_label = QLabel(
            "포스코퓨처엠 사내 표준과 안전보건 법규·자료를 함께 찾아드립니다."
        )

        subtitle_label.setObjectName(
            "headerSubtitle"
        )

        subtitle_label.setFont(
            header_font(
                SUBTITLE_FONT_FAMILY,
                "M",
                20,
                QFont.Weight.Bold,
            )
        )

        subtitle_label.setWordWrap(
            True
        )

        subtitle_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        title_layout.addStretch()

        title_layout.addWidget(
            title_label
        )

        title_layout.addWidget(
            subtitle_label
        )

        title_layout.addStretch()

        control_layout = QVBoxLayout()

        control_layout.setSpacing(
            4
        )

        control_layout.addStretch()

        self.news_button = QPushButton(
            "실시간 안전뉴스"
        )

        self.news_button.setObjectName(
            "newsButton"
        )

        self.news_button.clicked.connect(
            self.news_requested.emit
        )

        font_layout = QHBoxLayout()

        font_layout.setSpacing(
            5
        )

        self.smaller_button = QPushButton(
            "가-"
        )

        self.smaller_button.setObjectName(
            "fontButton"
        )

        self.font_size_label = QLabel(
            str(
                self.content_font_size
            )
        )

        self.font_size_label.setObjectName(
            "fontSizeLabel"
        )

        self.font_size_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.font_size_label.setMinimumWidth(
            30
        )

        self.larger_button = QPushButton(
            "가+"
        )

        self.larger_button.setObjectName(
            "fontButton"
        )

        self.smaller_button.clicked.connect(
            lambda: self.change_font_size(-1)
        )

        self.larger_button.clicked.connect(
            lambda: self.change_font_size(1)
        )

        font_layout.addWidget(
            self.smaller_button
        )

        font_layout.addWidget(
            self.font_size_label
        )

        font_layout.addWidget(
            self.larger_button
        )

        self.settings_button = QPushButton(
            "개인 API 설정"
        )

        self.settings_button.setObjectName(
            "settingsButton"
        )

        self.settings_button.clicked.connect(
            self.settings_requested.emit
        )

        control_layout.addWidget(
            self.news_button
        )

        control_layout.addLayout(
            font_layout
        )

        control_layout.addWidget(
            self.settings_button
        )

        control_layout.addStretch()

        header_layout.addWidget(
            icon
        )

        header_layout.addLayout(
            title_layout,
            1,
        )

        header_layout.addLayout(
            control_layout
        )

        root.addWidget(
            header
        )

        content_layout = QHBoxLayout()

        content_layout.setSpacing(
            10
        )

        # 질문 책갈피
        bookmark_frame = QFrame()

        bookmark_frame.setObjectName(
            "bookmarkFrame"
        )

        bookmark_frame.setFixedWidth(
            BOOKMARK_WIDTH
        )

        bookmark_layout = QVBoxLayout(
            bookmark_frame
        )

        bookmark_layout.setContentsMargins(
            8,
            10,
            8,
            10,
        )

        bookmark_title = QLabel(
            "질문 책갈피"
        )

        bookmark_title.setObjectName(
            "bookmarkTitle"
        )

        bookmark_layout.addWidget(
            bookmark_title
        )

        self.bookmark_scroll = QScrollArea()

        self.bookmark_scroll.setWidgetResizable(
            True
        )

        self.bookmark_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.bookmark_container = QWidget()

        self.bookmark_list_layout = QVBoxLayout(
            self.bookmark_container
        )

        self.bookmark_list_layout.setContentsMargins(
            0,
            2,
            0,
            2,
        )

        self.bookmark_list_layout.setSpacing(
            8
        )

        self.bookmark_list_layout.addStretch(
            1
        )

        self.bookmark_scroll.setWidget(
            self.bookmark_container
        )

        clear_history_button = QPushButton(
            "기록 전체 삭제"
        )

        clear_history_button.setObjectName(
            "clearHistoryButton"
        )

        clear_history_button.clicked.connect(
            self.clear_history
        )

        bookmark_layout.addWidget(
            self.bookmark_scroll,
            1,
        )

        bookmark_layout.addWidget(
            clear_history_button
        )

        # 채팅 영역
        chat_panel = QWidget()

        chat_layout = QVBoxLayout(
            chat_panel
        )

        chat_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        chat_layout.setSpacing(
            10
        )

        self.find_frame = QFrame()

        self.find_frame.setObjectName(
            "findFrame"
        )

        find_layout = QHBoxLayout(
            self.find_frame
        )

        find_layout.setContentsMargins(
            10,
            6,
            8,
            6,
        )

        find_layout.setSpacing(
            6
        )

        find_label = QLabel(
            "결과에서 찾기"
        )

        find_label.setObjectName(
            "findLabel"
        )

        self.find_input = QLineEdit()

        self.find_input.setObjectName(
            "findInput"
        )

        self.find_input.setPlaceholderText(
            "찾을 단어를 입력하세요"
        )

        self.find_input.setClearButtonEnabled(
            True
        )

        self.find_count_label = QLabel(
            "0 / 0"
        )

        self.find_count_label.setObjectName(
            "findCount"
        )

        self.find_previous_button = QPushButton(
            "이전"
        )

        self.find_previous_button.setObjectName(
            "findButton"
        )

        self.find_previous_button.setEnabled(
            False
        )

        self.find_previous_button.setToolTip(
            "이전 일치 항목 (Shift+F3)"
        )

        self.find_next_button = QPushButton(
            "다음"
        )

        self.find_next_button.setObjectName(
            "findButton"
        )

        self.find_next_button.setEnabled(
            False
        )

        self.find_next_button.setToolTip(
            "다음 일치 항목 (Enter 또는 F3)"
        )

        self.find_close_button = QPushButton(
            "닫기"
        )

        self.find_close_button.setObjectName(
            "findCloseButton"
        )

        self.find_close_button.setToolTip(
            "검색 닫기 (Esc)"
        )

        self.find_input.textChanged.connect(
            self.update_find_matches
        )

        self.find_input.returnPressed.connect(
            self.find_next
        )

        self.find_previous_button.clicked.connect(
            self.find_previous
        )

        self.find_next_button.clicked.connect(
            self.find_next
        )

        self.find_close_button.clicked.connect(
            self.close_find_bar
        )

        find_layout.addWidget(
            find_label
        )

        find_layout.addWidget(
            self.find_input,
            1,
        )

        find_layout.addWidget(
            self.find_count_label
        )

        find_layout.addWidget(
            self.find_previous_button
        )

        find_layout.addWidget(
            self.find_next_button
        )

        find_layout.addWidget(
            self.find_close_button
        )

        self.find_frame.setVisible(
            False
        )

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(
            True
        )

        self.scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.container = QWidget()

        self.messages = QVBoxLayout(
            self.container
        )

        self.messages.setContentsMargins(
            2,
            2,
            2,
            2,
        )

        self.messages.setSpacing(
            14
        )

        self.messages.addStretch(
            1
        )

        self.scroll.setWidget(
            self.container
        )

        example_frame = self.build_example_questions()

        input_frame = QFrame()

        input_frame.setObjectName(
            "inputFrame"
        )

        input_layout = QHBoxLayout(
            input_frame
        )

        input_layout.setContentsMargins(
            12,
            9,
            10,
            9,
        )

        self.question_input = QLineEdit()

        self.question_input.setPlaceholderText(
            "궁금한 내용을 짧게 입력해 주세요. 예) 밀폐공간 산소농도"
        )

        self.send_button = QPushButton(
            "질문"
        )

        self.question_input.returnPressed.connect(
            self.send_question
        )

        self.send_button.clicked.connect(
            self.send_question
        )

        input_layout.addWidget(
            self.question_input,
            1,
        )

        input_layout.addWidget(
            self.send_button
        )

        chat_layout.addWidget(
            self.find_frame
        )

        chat_layout.addWidget(
            self.scroll,
            1,
        )

        chat_layout.addWidget(
            example_frame
        )

        chat_layout.addWidget(
            input_frame
        )

        content_layout.addWidget(
            bookmark_frame
        )

        content_layout.addWidget(
            chat_panel,
            1,
        )

        root.addLayout(
            content_layout,
            1,
        )

        self.setCentralWidget(
            central
        )

        self.add_simple_answer(
            "### 안녕하세요! 포스코퓨처엠 안전요정 퓨밍이예요.\n\n"
            "사내 표준에서 근거를 찾아드려요. "
            "아래처럼 **찾는 항목만 짧게** 물어보시면 가장 정확해요.\n\n"
            "- 밀폐공간 산소농도\n"
            "- 발끝막이판 높이 기준\n"
            "- 안전작업허가 유효기간",
            "",
            move_to_top=False,
        )

    def setup_shortcuts(self):
        self.find_shortcut = QShortcut(
            QKeySequence("Ctrl+F"),
            self,
        )

        self.find_shortcut.activated.connect(
            self.open_find_bar
        )

        self.find_next_shortcut = QShortcut(
            QKeySequence("F3"),
            self,
        )

        self.find_next_shortcut.activated.connect(
            self.find_next
        )

        self.find_previous_shortcut = QShortcut(
            QKeySequence("Shift+F3"),
            self,
        )

        self.find_previous_shortcut.activated.connect(
            self.find_previous
        )

        self.find_close_shortcut = QShortcut(
            QKeySequence("Escape"),
            self,
        )

        self.find_close_shortcut.activated.connect(
            self.close_find_bar
        )

    def open_find_bar(self):
        self.find_frame.setVisible(
            True
        )

        self.find_input.setFocus()
        self.find_input.selectAll()

        self.update_find_matches(
            self.find_input.text()
        )

    def close_find_bar(self):
        if self.find_frame.isHidden():
            return

        self.find_frame.setVisible(
            False
        )

        self.find_matches = []
        self.current_find_match = -1
        self.find_count_label.setText(
            "0 / 0"
        )

        self.restore_question_highlights()
        self.question_input.setFocus()

    def restore_question_highlights(self):
        for item in self.answer_browsers:
            browser = item.get(
                "browser"
            )

            if browser is None:
                continue

            try:
                apply_search_highlights(
                    browser,
                    item.get(
                        "question",
                        "",
                    ),
                )
            except RuntimeError:
                continue

    def update_find_matches(
        self,
        value,
    ):
        query = str(
            value or ""
        ).strip()

        self.find_matches = []
        self.current_find_match = -1
        self.restore_question_highlights()

        if not query:
            self.find_count_label.setText(
                "0 / 0"
            )
            self.find_previous_button.setEnabled(
                False
            )
            self.find_next_button.setEnabled(
                False
            )
            return

        for item in self.answer_browsers:
            browser = item.get(
                "browser"
            )

            if browser is None:
                continue

            try:
                document = browser.document()
            except RuntimeError:
                continue

            search_cursor = QTextCursor(
                document
            )

            search_cursor.movePosition(
                QTextCursor.MoveOperation.Start
            )

            while True:
                found_cursor = document.find(
                    query,
                    search_cursor,
                )

                if found_cursor.isNull():
                    break

                self.find_matches.append({
                    "item": item,
                    "start": found_cursor.selectionStart(),
                    "end": found_cursor.selectionEnd(),
                })

                search_cursor.setPosition(
                    found_cursor.selectionEnd()
                )

        has_matches = bool(
            self.find_matches
        )

        self.find_previous_button.setEnabled(
            has_matches
        )

        self.find_next_button.setEnabled(
            has_matches
        )

        if not has_matches:
            self.find_count_label.setText(
                "0 / 0"
            )
            return

        self.show_find_match(
            0
        )

    def apply_find_highlights(self):
        self.restore_question_highlights()

        selections_by_browser = {}

        for match_index, match in enumerate(
            self.find_matches
        ):
            item = match["item"]
            browser = item.get(
                "browser"
            )

            if browser is None:
                continue

            try:
                cursor = QTextCursor(
                    browser.document()
                )
            except RuntimeError:
                continue

            cursor.setPosition(
                match["start"]
            )

            cursor.setPosition(
                match["end"],
                QTextCursor.MoveMode.KeepAnchor,
            )

            selection = QTextEdit.ExtraSelection()
            selection.cursor = cursor

            text_format = QTextCharFormat()

            if match_index == self.current_find_match:
                text_format.setBackground(
                    QColor("#FFB74D")
                )
                text_format.setForeground(
                    QColor("#2D1B00")
                )
                text_format.setFontWeight(
                    700
                )
            else:
                text_format.setBackground(
                    QColor("#B3E5FC")
                )
                text_format.setForeground(
                    QColor("#17324B")
                )

            selection.format = text_format

            selections_by_browser.setdefault(
                browser,
                [],
            ).append(
                selection
            )

        for item in self.answer_browsers:
            browser = item.get(
                "browser"
            )

            if browser is None:
                continue

            try:
                existing = list(
                    browser.extraSelections()
                )

                browser.setExtraSelections(
                    existing
                    + selections_by_browser.get(
                        browser,
                        [],
                    )
                )
            except RuntimeError:
                continue

    def show_find_match(
        self,
        match_index,
    ):
        if not self.find_matches:
            return

        self.current_find_match = (
            match_index
            % len(self.find_matches)
        )

        self.find_count_label.setText(
            str(self.current_find_match + 1)
            + " / "
            + str(len(self.find_matches))
        )

        self.apply_find_highlights()

        match = self.find_matches[
            self.current_find_match
        ]

        item = match["item"]
        browser = item.get(
            "browser"
        )

        details = item.get(
            "details"
        )

        if (
            details is not None
            and not details.button.isChecked()
        ):
            details.button.setChecked(
                True
            )
            details.toggle(
                True
            )

        cursor = QTextCursor(
            browser.document()
        )

        cursor.setPosition(
            match["start"]
        )

        cursor.setPosition(
            match["end"],
            QTextCursor.MoveMode.KeepAnchor,
        )

        browser.setTextCursor(
            cursor
        )

        QTimer.singleShot(
            80,
            lambda target=browser,
            target_cursor=cursor:
            self.scroll_to_find_cursor(
                target,
                target_cursor,
            ),
        )

    def scroll_to_find_cursor(
        self,
        browser,
        cursor,
    ):
        try:
            cursor_position = browser.cursorRect(
                cursor
            ).topLeft()

            position = browser.viewport().mapTo(
                self.container,
                cursor_position,
            )
        except RuntimeError:
            return

        scroll_bar = self.scroll.verticalScrollBar()

        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                position.y()
                - 80,
            )
        )

    def find_next(self):
        if self.find_frame.isHidden():
            self.open_find_bar()
            return

        if not self.find_matches:
            return

        self.show_find_match(
            self.current_find_match
            + 1
        )

    def find_previous(self):
        if self.find_frame.isHidden():
            self.open_find_bar()
            return

        if not self.find_matches:
            return

        self.show_find_match(
            self.current_find_match
            - 1
        )

    def refresh_find_after_content_change(self):
        if self.find_frame.isHidden():
            return

        if not self.find_input.text().strip():
            return

        QTimer.singleShot(
            0,
            lambda: self.update_find_matches(
                self.find_input.text()
            ),
        )

    # --------------------------------------------------------
    # 예시 질문
    # --------------------------------------------------------

    def build_example_questions(self):
        """단답형 질문을 눌러 바로 물어볼 수 있게 합니다."""
        frame = QFrame()

        frame.setObjectName(
            "exampleFrame"
        )

        layout = QHBoxLayout(
            frame
        )

        layout.setContentsMargins(
            2,
            0,
            2,
            0,
        )

        layout.setSpacing(
            6
        )

        label = QLabel(
            "이렇게 물어보세요"
        )

        label.setObjectName(
            "exampleLabel"
        )

        layout.addWidget(
            label
        )

        for question in EXAMPLE_QUESTIONS:
            button = QPushButton(
                question
            )

            button.setObjectName(
                "exampleButton"
            )

            button.setCursor(
                Qt.CursorShape.PointingHandCursor
            )

            button.clicked.connect(
                functools.partial(
                    self.ask_example_question,
                    question,
                )
            )

            layout.addWidget(
                button
            )

        layout.addStretch(
            1
        )

        return frame

    def ask_example_question(
        self,
        question,
    ):
        self.question_input.setText(
            question
        )

        self.send_question()

    # --------------------------------------------------------
    # 스타일
    # --------------------------------------------------------

    def apply_style(self):
        self.setStyleSheet(
            """
            QWidget#centralWidget {
                background:#F2F5F8;
            }

            QFrame#headerFrame {
                background:#E7F7F5;
                border:1px solid #C8EAE7;
                border-radius:18px;
            }

            QLabel#headerTitle {
                color:#10304A;
            }

            QLabel#headerSubtitle {
                color:#345568;
            }

            QFrame#bookmarkFrame {
                background:#EDF2F5;
                border:1px solid #D6E0E7;
                border-radius:13px;
            }

            QLabel#bookmarkTitle {
                color:#334E60;
                font-size:15px;
                font-weight:700;
            }

            QPushButton#clearHistoryButton {
                background:#8598A6;
                color:white;
                border:none;
                border-radius:8px;
                padding:7px;
                font-size:12px;
                font-weight:700;
            }

            QLabel#fontSizeLabel {
                color:#0C5E64;
                font-size:14px;
                font-weight:700;
                min-width:28px;
            }

            QPushButton#fontButton {
                color:#006A70;
                background:white;
                border:1px solid #B8DDDA;
                border-radius:8px;
                padding:7px 11px;
                font-size:14px;
                font-weight:700;
            }

            QPushButton#newsButton {
                color:white;
                background:#F28C28;
                border:none;
                border-radius:8px;
                padding:8px 11px;
                font-size:13px;
                font-weight:700;
            }

            QPushButton#settingsButton {
                color:white;
                background:#557789;
                border:none;
                border-radius:8px;
                padding:8px 11px;
                font-size:13px;
                font-weight:700;
            }

            QPushButton#detailsButton {
                color:#0C5E64;
                background:#E7F7F5;
                border:1px solid #B8DDDA;
                border-radius:8px;
                padding:8px 12px;
                font-size:13px;
                font-weight:700;
            }

            QPushButton#detailsButton:hover {
                background:#D5F0ED;
            }

            QFrame#exampleFrame {
                background:transparent;
                border:none;
            }

            QLabel#exampleLabel {
                color:#687989;
                font-size:12px;
                font-weight:700;
                padding-right:2px;
            }

            QPushButton#exampleButton {
                color:#17324B;
                background:#EDF3F8;
                border:1px solid #D7E1EA;
                border-radius:13px;
                padding:5px 11px;
                font-size:12px;
                font-weight:500;
            }

            QPushButton#exampleButton:hover {
                color:#0C5E64;
                background:#E7F7F5;
                border:1px solid #B8DDDA;
            }

            QFrame#findFrame {
                background:#F8FBFD;
                border:1px solid #C9D8E3;
                border-radius:11px;
            }

            QLabel#findLabel {
                color:#334E60;
                font-size:13px;
                font-weight:700;
                padding:0 4px;
            }

            QLineEdit#findInput {
                color:#17324B;
                background:white;
                border:1px solid #C9D8E3;
                border-radius:7px;
                padding:6px 9px;
                font-size:14px;
            }

            QLabel#findCount {
                color:#567080;
                font-size:12px;
                min-width:45px;
                padding:0 3px;
            }

            QPushButton#findButton,
            QPushButton#findCloseButton {
                background:#557789;
                color:white;
                border:none;
                border-radius:7px;
                padding:6px 10px;
                font-size:12px;
                font-weight:700;
            }

            QPushButton#findButton:disabled {
                background:#B8C4CC;
                color:#F5F7F8;
            }

            QPushButton#findCloseButton {
                background:#8598A6;
            }

            QFrame#inputFrame {
                background:white;
                border:1px solid #D7E1EA;
                border-radius:16px;
            }

            QLineEdit {
                color:#17324B;
                background:transparent;
                border:none;
                padding:10px;
                font-size:17px;
            }

            QPushButton {
                background:#00A19C;
                color:white;
                border:none;
                border-radius:9px;
                padding:9px 16px;
                font-size:14px;
                font-weight:700;
            }

            QPushButton:hover {
                background:#008B87;
            }

            QFrame#answerCard {
                background:white;
                border:1px solid #DCE5ED;
                border-radius:16px;
            }

            QFrame#userCard {
                background:#BFEAE6;
                border:2px solid #84CDC7;
                border-radius:16px;
            }

            QLabel#userText {
                color:#0B3840;
                font-size:19px;
                font-weight:700;
            }

            QLabel#hintText {
                color:#657887;
                font-size:13px;
            }
            """
        )

    def answer_style_sheet(self):
        size = self.content_font_size

        return (
            "body {"
            "font-family:'"
            + APP_FONT_FAMILY
            + "';"
            "font-size:"
            + str(size)
            + "px;"
            "color:#1D324C;"
            "}"
            "p {"
            "margin-top:7px;"
            "margin-bottom:13px;"
            "line-height:1.62;"
            "}"
            "h3 {"
            "font-size:"
            + str(size + 1)
            + "px;"
            "color:#102A49;"
            "font-weight:700;"
            "margin-top:14px;"
            "margin-bottom:10px;"
            "}"
            "h4 {"
            "font-size:"
            + str(size)
            + "px;"
            "color:#0C5E64;"
            "font-weight:700;"
            "margin-top:13px;"
            "margin-bottom:8px;"
            "}"
            "li {"
            "margin-top:5px;"
            "margin-bottom:10px;"
            "line-height:1.62;"
            "}"
            "a {"
            "color:#17324B;"
            "font-weight:500;"
            "text-decoration:none;"
            "}"
        )

    def place_bottom_right(self):
        screen = QApplication.primaryScreen()

        if screen is None:
            return

        area = screen.availableGeometry()

        self.move(
            area.right()
            - self.width()
            - 100,
            area.bottom()
            - self.height()
            - 20,
        )

    def change_font_size(self, amount):
        self.content_font_size = max(
            MIN_CONTENT_FONT_SIZE,
            min(
                MAX_CONTENT_FONT_SIZE,
                self.content_font_size
                + amount,
            ),
        )

        self.font_size_label.setText(
            str(self.content_font_size)
        )

        self.settings.setValue(
            "content_font_size",
            self.content_font_size,
        )

        for item in self.answer_browsers:
            browser = item["browser"]

            browser.document().setDefaultStyleSheet(
                self.answer_style_sheet()
            )

            browser.setHtml(
                item["html"]
            )

            apply_search_highlights(
                browser,
                item["question"],
            )

            QTimer.singleShot(
                40,
                browser.update_document_height,
            )

        self.refresh_find_after_content_change()

    # --------------------------------------------------------
    # 스크롤 및 메시지
    # --------------------------------------------------------

    def insert_message(
        self,
        widget,
        move_to_top=False,
    ):
        self.messages.insertWidget(
            self.messages.count() - 1,
            widget,
        )

        if move_to_top:
            QTimer.singleShot(
                180,
                lambda target=widget:
                self.scroll_to_widget(target),
            )

            QTimer.singleShot(
                450,
                lambda target=widget:
                self.scroll_to_widget(target),
            )
        else:
            QTimer.singleShot(
                80,
                self.scroll_bottom,
            )

    def scroll_to_widget(self, widget):
        if widget is None:
            return

        position = widget.mapTo(
            self.container,
            QPoint(0, 0),
        )

        scroll_bar = (
            self.scroll.verticalScrollBar()
        )

        scroll_bar.setValue(
            max(
                scroll_bar.minimum(),
                position.y() - 8,
            )
        )

    def scroll_to_expanded(self, widget, expanded):
        if not expanded or widget is None:
            return

        QTimer.singleShot(
            80,
            lambda target=widget:
            self.scroll_to_widget(target),
        )

        QTimer.singleShot(
            260,
            lambda target=widget:
            self.scroll_to_widget(target),
        )

    def scroll_bottom(self):
        scroll_bar = (
            self.scroll.verticalScrollBar()
        )

        scroll_bar.setValue(
            scroll_bar.maximum()
        )

    def add_user_message(
        self,
        text,
        move_to_top=False,
    ):
        row = QWidget()

        row_layout = QHBoxLayout(
            row
        )

        row_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        card = QFrame()

        card.setObjectName(
            "userCard"
        )

        card_layout = QVBoxLayout(
            card
        )

        card_layout.setContentsMargins(
            16,
            13,
            16,
            13,
        )

        label = QLabel(
            text
        )

        label.setObjectName(
            "userText"
        )

        label.setWordWrap(
            True
        )

        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        card_layout.addWidget(
            label
        )

        row_layout.addStretch()

        row_layout.addWidget(
            card,
            5,
        )

        self.insert_message(
            row,
            move_to_top,
        )

        return row

    def create_answer_browser(
        self,
        complete_html,
        question,
    ):
        browser = AutoHeightTextBrowser()

        browser.document().setDefaultStyleSheet(
            self.answer_style_sheet()
        )

        browser.setHtml(
            complete_html
        )

        apply_search_highlights(
            browser,
            question,
        )

        return browser

    def add_simple_answer(
        self,
        text,
        question,
        move_to_top=True,
    ):
        frame = QFrame()

        frame.setObjectName(
            "answerCard"
        )

        frame_layout = QVBoxLayout(
            frame
        )

        frame_layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        complete_html = (
            "<body>"
            + markdown_to_html(
                text
            )
            + "</body>"
        )

        browser = self.create_answer_browser(
            complete_html,
            question,
        )

        browser.anchorClicked.connect(
            self.open_external_link
        )

        frame_layout.addWidget(
            browser
        )

        self.answer_browsers.append({
            "browser": browser,
            "html": complete_html,
            "question": question,
        })

        self.insert_message(
            frame,
            move_to_top,
        )

        QTimer.singleShot(
            40,
            browser.update_document_height,
        )

        self.refresh_find_after_content_change()

        return frame

    def add_search_answer(
        self,
        ai_answer,
        sources,
        kosha_results,
        question,
        move_to_top=True,
    ):
        frame = QFrame()

        frame.setObjectName(
            "answerCard"
        )

        frame_layout = QVBoxLayout(
            frame
        )

        frame_layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        bundle = build_answer_bundle(
            question,
            sources,
        )

        bundle["title"] = "사내 기준"
        bundle["reference_title"] = "공식 참고자료"

        def add_browser(
            html_content,
            anchor_handler=None,
        ):
            browser = self.create_answer_browser(
                "<body>"
                + html_content
                + "</body>",
                question,
            )

            if anchor_handler is not None:
                browser.anchorClicked.connect(
                    anchor_handler
                )

            frame_layout.addWidget(
                browser
            )

            self.answer_browsers.append({
                "browser": browser,
                "html": (
                    "<body>"
                    + html_content
                    + "</body>"
                ),
                "question": question,
            })

            QTimer.singleShot(
                40,
                browser.update_document_height,
            )

            return browser

        if compact_fact_definition(
            question
        ) is not None:
            (
                compact_html,
                compact_source_links,
            ) = render_compact_fact_answer(
                question,
                sources
            )

            if compact_source_links:
                add_browser(
                    compact_html,
                    lambda url,
                    source_list=sources,
                    link_list=compact_source_links,
                    search_question=question:
                    self.handle_search_link(
                        url,
                        source_list,
                        link_list,
                        search_question,
                    ),
                )

                concise_laws = select_concise_kosha_results(
                    kosha_results,
                    question,
                    maximum=1,
                )

                if concise_laws:
                    add_browser(
                        render_kosha_html(
                            concise_laws,
                            "관련 법규",
                            question,
                        ),
                        self.open_external_link,
                    )

                self.insert_message(
                    frame,
                    move_to_top,
                )

                self.refresh_find_after_content_change()

                return frame

        if ai_answer:
            add_browser(
                "<h3>퓨밍이 답변</h3>"
                + markdown_to_html(
                    ai_answer
                ),
                self.open_external_link,
            )

        (
            internal_html,
            source_links,
        ) = render_internal_bundle(
            bundle,
            question,
            "highlighted",
            maximum_groups=1,
            maximum_items_per_group=2,
        )

        if not source_links:
            internal_html, source_links = render_internal_bundle(
                bundle,
                question,
                "all",
                maximum_groups=1,
                maximum_items_per_group=2,
            )

        if source_links:
            add_browser(
                internal_html,
                lambda url,
                source_list=sources,
                link_list=source_links,
                search_question=question:
                self.handle_search_link(
                    url,
                    source_list,
                    link_list,
                    search_question,
                ),
            )

        reference_bundle = {
            "title": bundle.get(
                "reference_title",
                "관련 질의회시·공식 자료에서 함께 확인한 내용",
            ),
            "groups": bundle.get(
                "reference_groups",
                [],
            ),
        }

        reference_html, reference_links = render_internal_bundle(
            reference_bundle,
            question,
            "highlighted",
            maximum_groups=1,
            maximum_items_per_group=1,
        )

        if not reference_links:
            reference_html, reference_links = render_internal_bundle(
                reference_bundle,
                question,
                "all",
                maximum_groups=1,
                maximum_items_per_group=1,
            )

        reference_notice = (
            '<p style="color:#687989; margin-top:12px;">'
            "※ 적용 전 최신 원문을 확인하세요.</p>"
        )

        if reference_links:
            add_browser(
                reference_html
                + reference_notice,
                lambda url,
                source_list=sources,
                link_list=reference_links,
                search_question=question:
                self.handle_search_link(
                    url,
                    source_list,
                    link_list,
                    search_question,
                ),
            )

        visible_laws = select_concise_kosha_results(
            kosha_results,
            question,
            maximum=1,
        )

        if visible_laws:
            add_browser(
                render_kosha_html(
                    visible_laws,
                    "관련 법규·공단 자료",
                    question,
                ),
                self.open_external_link,
            )

        self.insert_message(
            frame,
            move_to_top,
        )

        self.refresh_find_after_content_change()

        return frame

    def show_loading(self):
        label = QLabel(
            "퓨밍이가 자료를 찾고 있어요..."
        )

        label.setStyleSheet(
            "background:white;"
            "padding:16px;"
            "border-radius:14px;"
            "font-size:15px;"
            "color:#5E7383;"
        )

        self.loading_widget = label

        self.insert_message(
            label,
            move_to_top=False,
        )

    def remove_loading(self):
        if self.loading_widget is None:
            return

        self.loading_widget.setParent(
            None
        )

        self.loading_widget.deleteLater()

        self.loading_widget = None

    # --------------------------------------------------------
    # 링크
    # --------------------------------------------------------

    def open_external_link(self, url):
        value = url.toString().strip()

        if value.startswith(
            (
                "http://",
                "https://",
            )
        ):
            QDesktopServices.openUrl(
                QUrl(value)
            )

    def handle_search_link(
        self,
        url,
        sources,
        source_links,
        question,
    ):
        value = url.toString().strip()

        if value.startswith(
            "sourceitem:"
        ):
            number_text = value.replace(
                "sourceitem:",
                "",
                1,
            )

            if not number_text.isdigit():
                return

            link_index = int(
                number_text
            )

            if not (
                0
                <= link_index
                < len(source_links)
            ):
                return

            link_information = (
                source_links[
                    link_index
                ]
            )

            source_index = (
                link_information.get(
                    "source_index",
                    0,
                )
            )

            if not (
                0
                <= source_index
                < len(sources)
            ):
                return

            source = sources[
                source_index
            ]

            SourceDialog(
                source,
                question,
                link_information.get(
                    "focus_text",
                    "",
                ),
                link_information.get(
                    "focus_heading",
                    "",
                ),
                self.content_font_size,
                self,
            ).exec()

            return

        self.open_external_link(
            url
        )

    # --------------------------------------------------------
    # 책갈피
    # --------------------------------------------------------

    def clear_bookmark_widgets(self):
        while (
            self.bookmark_list_layout.count()
            > 1
        ):
            item = (
                self.bookmark_list_layout
                .takeAt(0)
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self.bookmark_buttons.clear()

    def load_bookmarks(self):
        self.clear_bookmark_widgets()

        history_items = list_chat_history(
            limit=HISTORY_LOAD_LIMIT
        )

        for history in history_items:
            button = BookmarkButton(
                history["id"],
                history["bookmark_title"],
                history["bookmark_color"],
            )

            button.selected.connect(
                self.open_history_item
            )

            button.delete_requested.connect(
                self.delete_history_item
            )

            self.bookmark_list_layout.insertWidget(
                self.bookmark_list_layout.count() - 1,
                button,
            )

            self.bookmark_buttons[
                history["id"]
            ] = button

    def add_bookmark(
        self,
        history_id,
    ):
        history = get_chat_history(
            history_id
        )

        if history is None:
            return

        if history_id in self.bookmark_buttons:
            return

        button = BookmarkButton(
            history["id"],
            history["bookmark_title"],
            history["bookmark_color"],
        )

        button.selected.connect(
            self.open_history_item
        )

        button.delete_requested.connect(
            self.delete_history_item
        )

        self.bookmark_list_layout.insertWidget(
            0,
            button,
        )

        self.bookmark_buttons[
            history_id
        ] = button

    def open_history_item(
        self,
        history_id,
    ):
        existing_widget = (
            self.history_widgets.get(
                history_id
            )
        )

        if existing_widget is not None:
            # 질문 카드가 화면 맨 위로 오도록 이동합니다.
            self.scroll_to_widget(
                existing_widget
            )
            return

        history = get_chat_history(
            history_id
        )

        if history is None:
            return

        question_widget = self.add_user_message(
            history["question"],
            move_to_top=False,
        )

        self.add_simple_answer(
            history["answer"],
            history["question"],
            move_to_top=False,
        )

        self.history_widgets[
            history_id
        ] = question_widget

        QTimer.singleShot(
            180,
            lambda target=question_widget:
            self.scroll_to_widget(
                target
            ),
        )

        QTimer.singleShot(
            400,
            lambda target=question_widget:
            self.scroll_to_widget(
                target
            ),
        )

    def delete_history_item(
        self,
        history_id,
    ):
        result = QMessageBox.question(
            self,
            "질문 기록 삭제",
            "선택한 질문 기록을 삭제하시겠습니까?",
        )

        if (
            result
            != QMessageBox.StandardButton.Yes
        ):
            return

        delete_chat_history(
            history_id
        )

        self.load_bookmarks()

    def clear_history(self):
        result = QMessageBox.question(
            self,
            "전체 기록 삭제",
            "저장된 질문과 답변 기록을 모두 삭제하시겠습니까?",
        )

        if (
            result
            != QMessageBox.StandardButton.Yes
        ):
            return

        clear_chat_history()

        self.history_widgets.clear()
        self.load_bookmarks()

    # --------------------------------------------------------
    # 질문 처리
    # --------------------------------------------------------

    def send_question(self):
        if (
            self.worker is not None
            and self.worker.isRunning()
        ):
            return

        question = (
            self.question_input.text()
            .strip()
        )

        if not question:
            return

        self.current_question = question

        self.question_input.clear()

        self.current_question_widget = (
            self.add_user_message(
                question,
                move_to_top=False,
            )
        )

        self.show_loading()

        self.question_input.setEnabled(
            False
        )

        self.send_button.setEnabled(
            False
        )

        self.worker = SearchWorker(
            question,
            self.chunks,
            self.index,
        )

        self.worker.completed.connect(
            self.handle_completed
        )

        self.worker.finished.connect(
            self.handle_worker_finished
        )

        self.worker.start()

    def handle_completed(
        self,
        answer,
        sources,
        kosha_results,
        document_mode,
    ):
        self.remove_loading()

        if document_mode:
            answer_widget = (
                self.add_search_answer(
                    answer,
                    sources,
                    kosha_results,
                    self.current_question,
                    move_to_top=True,
                )
            )
        else:
            answer_widget = (
                self.add_simple_answer(
                    answer,
                    self.current_question,
                    move_to_top=True,
                )
            )

        del answer_widget

        history_id = save_chat_history(
            self.current_question,
            answer,
            sources,
        )

        if (
            history_id is not None
            and self.current_question_widget is not None
        ):
            self.history_widgets[
                history_id
            ] = self.current_question_widget

            self.add_bookmark(
                history_id
            )

        self.question_input.setEnabled(
            True
        )

        self.send_button.setEnabled(
            True
        )

        self.question_input.setFocus()

    def handle_worker_finished(self):
        self.question_input.setEnabled(
            True
        )

        self.send_button.setEnabled(
            True
        )

        if self.loading_widget is not None:
            self.remove_loading()

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.hide()


# ============================================================
# 말풍선과 캐릭터
# ============================================================

SPEECH_BUBBLE_WIDTH = 180
SPEECH_BUBBLE_HEIGHT = 96
SPEECH_BUBBLE_GAP = 4
SPEECH_BUBBLE_SCREEN_MARGIN = 8

MASCOT_MESSAGES = [
    "안전하세요!",
    "오늘도 안전하세요!",
    "내 일터 안전하게,\n내일 더 행복하게",
    "무사히 출근해서,\n당연히 퇴근하기",
    "빠름보다 바름,\n안전한 선택",
    "실천하는 안전수칙,\n실현되는 안전일터",
    "위험은 공유하고\n안전은 실천하자",
    "위험을 보는 것이\n안전의 시작입니다.",
    "모든 사고는\n예방할 수 있습니다!",
    "안전하지 않으면\nSTOP!",
    "지적확인과\n정지 5초 생활화",
    "작업중지권을\n용기 있게 사용해 주세요.",
    "작업 전 5분 점검이\n하루 안전을 지킵니다.",
    "모르면 묻고,\n위험하면 멈추세요.",
    "보호구는 선택이 아니라\n약속입니다.",
    "안전한 작업은\n올바른 준비에서 시작됩니다.",
    "작은 위험도\n그냥 지나치지 마세요.",
    "내가 지킨 안전수칙이\n동료의 생명을 지킵니다.",
    "정리정돈은\n가장 기본적인 안전활동입니다.",
    "서두르지 말고\n순서대로 안전하게!",
    "위험요인은\n발견 즉시 알리고\n개선하세요.",
    "작업 전 설비와 보호구를\n꼭 확인하세요.",
    "안전은 확인하고 또 확인하는\n습관입니다.",
    "불안전하면\n작업을 시작하지 마세요.",
    "작업계획과 현장 상태가\n같은지 확인하세요.",
    "오늘의 안전점검이\n내일의 사고를 막습니다.",
    "동료의 안전까지 살피는\n우리가 됩시다.",
    "잠깐의 방심이\n큰 사고로 이어질 수 있습니다.",
    "안전수칙 준수가\n최고의 작업능률입니다.",
    "위험성평가,\n현장에서 함께 실천하세요.",
    "아차사고를 공유하면\n큰 사고를 예방할 수 있습니다.",
    "안전은 비용이 아니라\n가장 중요한 가치입니다.",
    "작업 종료 후에도\n주변 위험을 확인하세요.",
    "건강한 일터는\n안전한 행동에서 시작됩니다.",
]


class SpeechBubble(QWidget):
    def __init__(self):
        super().__init__()

        self.setFixedSize(
            SPEECH_BUBBLE_WIDTH,
            SPEECH_BUBBLE_HEIGHT,
        )

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        root = QVBoxLayout(self)

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        frame = QFrame()

        frame.setStyleSheet(
            "QFrame {"
            "background:white;"
            "border:2px solid #00A19C;"
            "border-radius:16px;"
            "}"
        )

        layout = QVBoxLayout(frame)

        layout.setContentsMargins(
            14,
            10,
            14,
            10,
        )

        self.label = QLabel("")

        self.label.setWordWrap(True)

        self.label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.label.setStyleSheet(
            "font-size:14px;"
            "font-weight:700;"
            "color:#10304A;"
            "border:none;"
            "padding:0;"
        )

        layout.addWidget(
            self.label
        )

        root.addWidget(
            frame
        )

        self.timer = QTimer(self)

        self.timer.setSingleShot(
            True
        )

        self.timer.timeout.connect(
            self.hide
        )

    def show_message(
        self,
        text,
        anchor,
        visual_top=None,
    ):
        self.label.setText(text)

        hat_top = (
            visual_top
            if visual_top is not None
            else anchor.top()
        )

        target_x = (
            anchor.center().x()
            - self.width() // 2
        )

        target_y = (
            hat_top
            - self.height()
            - SPEECH_BUBBLE_GAP
        )

        screen = QApplication.screenAt(
            anchor.center()
        )

        if screen is None:
            screen = QApplication.primaryScreen()

        if screen is not None:
            area = screen.availableGeometry()
            margin = SPEECH_BUBBLE_SCREEN_MARGIN

            minimum_x = area.left() + margin
            maximum_x = max(
                minimum_x,
                area.right()
                - self.width()
                - margin
                + 1,
            )

            minimum_y = area.top() + margin
            maximum_y = max(
                minimum_y,
                area.bottom()
                - self.height()
                - margin
                + 1,
            )

            if target_y < minimum_y:
                left_x = (
                    anchor.left()
                    - self.width()
                    - SPEECH_BUBBLE_GAP
                )

                right_x = (
                    anchor.right()
                    + SPEECH_BUBBLE_GAP
                    + 1
                )

                if left_x >= minimum_x:
                    target_x = left_x
                elif right_x <= maximum_x:
                    target_x = right_x
                else:
                    target_x = max(
                        minimum_x,
                        min(
                            target_x,
                            maximum_x,
                        ),
                    )

                target_y = max(
                    minimum_y,
                    min(
                        hat_top,
                        maximum_y,
                    ),
                )
            else:
                target_x = max(
                    minimum_x,
                    min(
                        target_x,
                        maximum_x,
                    ),
                )

                target_y = min(
                    target_y,
                    maximum_y,
                )

        self.move(
            target_x,
            target_y,
        )

        self.show()
        self.raise_()

        self.timer.start(
            5000
        )


class MascotWidget(QWidget):
    activated = Signal()
    settings_requested = Signal()
    news_requested = Signal()
    hide_requested = Signal()

    def __init__(self):
        super().__init__()

        self.setFixedSize(
            126,
            170,
        )

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        self.pixmap = mascot_pixmap(
            164
        )

        self.pixmap_x = (
            self.width()
            - self.pixmap.width()
        ) // 2

        self.pixmap_y = (
            self.height()
            - self.pixmap.height()
        ) // 2

        visible_bounds = QRegion(
            self.pixmap.mask()
        ).boundingRect()

        self.visual_top_offset = (
            self.pixmap_y
            + max(
                0,
                visible_bounds.top(),
            )
        )

        self.bubble = SpeechBubble()

        self.drag_offset = None
        self.dragging = False
        self.last_message = ""

        self.setToolTip(
            "클릭: 안전 메시지\n"
            "더블클릭: 안전비서 열기\n"
            "우클릭: 메뉴"
        )

    def paintEvent(self, event):
        del event

        painter = QPainter(self)

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        painter.drawPixmap(
            self.pixmap_x,
            self.pixmap_y,
            self.pixmap,
        )

        painter.end()

    def show_context_menu(
        self,
        global_position,
    ):
        menu = QMenu(self)

        open_action = menu.addAction(
            "안전비서 열기"
        )

        settings_action = menu.addAction(
            "개인 API 설정"
        )

        news_action = menu.addAction(
            "실시간 안전뉴스"
        )

        menu.addSeparator()

        hide_action = menu.addAction(
            "퓨밍이 숨기기"
        )

        selected_action = menu.exec(
            global_position
        )

        if selected_action == open_action:
            self.activated.emit()

        elif selected_action == settings_action:
            self.settings_requested.emit()

        elif selected_action == news_action:
            self.news_requested.emit()

        elif selected_action == hide_action:
            self.hide_requested.emit()

    def mousePressEvent(self, event):
        if (
            event.button()
            == Qt.MouseButton.RightButton
        ):
            self.show_context_menu(
                event.globalPosition().toPoint()
            )
            return

        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):
            self.drag_offset = (
                event.globalPosition().toPoint()
                - self.frameGeometry().topLeft()
            )

            self.dragging = False

    def mouseMoveEvent(self, event):
        if self.drag_offset is None:
            return

        if not (
            event.buttons()
            & Qt.MouseButton.LeftButton
        ):
            return

        self.dragging = True
        self.bubble.hide()

        self.move(
            event.globalPosition().toPoint()
            - self.drag_offset
        )

    def mouseReleaseEvent(self, event):
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            return

        if not self.dragging:
            candidates = [
                message
                for message in MASCOT_MESSAGES
                if message != self.last_message
            ]

            message = random.choice(
                candidates
                or MASCOT_MESSAGES
            )

            self.last_message = message

            anchor = self.frameGeometry()

            self.bubble.show_message(
                message,
                anchor,
                anchor.top()
                + self.visual_top_offset,
            )

        self.drag_offset = None
        self.dragging = False

    def mouseDoubleClickEvent(self, event):
        if (
            event.button()
            == Qt.MouseButton.LeftButton
        ):
            self.bubble.hide()
            self.activated.emit()

    def place_bottom_right(self):
        screen = QApplication.primaryScreen()

        if screen is None:
            return

        area = screen.availableGeometry()

        self.move(
            area.right()
            - self.width()
            - 14,
            area.bottom()
            - self.height()
            - 10,
        )


# ============================================================
# 프로그램 본체
# ============================================================

class DesktopAssistant:
    def __init__(self):
        self.app = QApplication(
            sys.argv
        )

        self.app.setQuitOnLastWindowClosed(
            False
        )

        self.app.setApplicationName(
            APP_NAME
        )

        self.app.setOrganizationName(
            ORGANIZATION_NAME
        )

        font_family = choose_font_family()

        self.app.setFont(
            QFont(
                font_family,
                11,
            )
        )

        print(
            "[글꼴] "
            + font_family
        )

        init_databases()

        (
            self.chunks,
            self.index,
            self.errors,
        ) = load_documents_with_index(
            DOCUMENTS_DIR
        )

        for error in self.errors:
            print(
                "[문서 알림] "
                + error
            )

        self.window = ChatWindow(
            self.chunks,
            self.index,
            self.errors,
        )

        self.window.settings_requested.connect(
            self.open_settings
        )

        self.window.news_requested.connect(
            self.open_news
        )

        self.mascot = MascotWidget()

        self.mascot.place_bottom_right()

        self.mascot.activated.connect(
            self.show_window
        )

        self.mascot.settings_requested.connect(
            self.open_settings
        )

        self.mascot.news_requested.connect(
            self.open_news
        )

        self.mascot.hide_requested.connect(
            self.mascot.hide
        )

        self.tray = QSystemTrayIcon(
            QIcon(
                mascot_pixmap(
                    128,
                    True,
                )
            ),
            self.app,
        )

        tray_menu = QMenu()

        open_action = tray_menu.addAction(
            "안전비서 열기"
        )

        settings_action = tray_menu.addAction(
            "개인 API 설정"
        )

        news_action = tray_menu.addAction(
            "실시간 안전뉴스"
        )

        mascot_action = tray_menu.addAction(
            "퓨밍이 표시"
        )

        reload_action = tray_menu.addAction(
            "문서 다시 읽기"
        )

        tray_menu.addSeparator()

        quit_action = tray_menu.addAction(
            "종료"
        )

        open_action.triggered.connect(
            self.show_window
        )

        settings_action.triggered.connect(
            self.open_settings
        )

        news_action.triggered.connect(
            self.open_news
        )

        mascot_action.triggered.connect(
            self.show_mascot
        )

        reload_action.triggered.connect(
            self.reload_documents
        )

        quit_action.triggered.connect(
            self.quit_application
        )

        self.tray.setContextMenu(
            tray_menu
        )

        self.tray.setToolTip(
            APP_NAME
        )

        self.tray.show()

        self.mascot.show()
        self.window.hide()

        self.news_dialog = None

    def show_window(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

        self.window.question_input.setFocus()

    def show_mascot(self):
        self.mascot.place_bottom_right()
        self.mascot.show()
        self.mascot.raise_()

    def open_settings(self):
        dialog = ApiSettingsDialog(
            self.window
        )

        dialog.exec()

    def open_news(self):
        self.news_dialog = NewsDialog(
            self.window
        )

        self.news_dialog.exec()

    def reload_documents(self):
        (
            self.chunks,
            self.index,
            self.errors,
        ) = load_documents_with_index(
            DOCUMENTS_DIR
        )

        self.window.chunks = self.chunks
        self.window.index = self.index
        self.window.errors = self.errors

        self.tray.showMessage(
            APP_NAME,
            "문서를 다시 읽었습니다.\n"
            + "조각 "
            + str(len(self.chunks))
            + "개",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def quit_application(self):
        if (
            self.window.worker is not None
            and self.window.worker.isRunning()
        ):
            self.tray.showMessage(
                APP_NAME,
                "검색 중입니다. 잠시 후 종료해 주세요.",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )
            return

        self.window.allow_close = True
        self.window.close()

        self.mascot.bubble.hide()
        self.mascot.close()

        self.tray.hide()
        self.app.quit()

    def run(self):
        return self.app.exec()


def main():
    assistant = DesktopAssistant()

    sys.exit(
        assistant.run()
    )


if __name__ == "__main__":
    main()
