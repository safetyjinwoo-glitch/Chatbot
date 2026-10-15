"""예시 질문 검증

화면에 걸어둔 단답형 예시 질문이 실제로 사내 표준에서 근거를 찾아내는지
그리고 그 근거가 질문에 맞는 표준에서 나오는지 잽니다.

진본은 desktop_app.EXAMPLE_QUESTIONS 이고, 여기서는 그것을 불러 씁니다.

실행: python verify_example_questions.py
"""

import sys

from document_engine import (
    build_answer_bundle,
    document_is_allowed,
    load_documents_with_index,
    search_documents,
)


# 예시 질문마다 근거가 나와야 하는 표준번호입니다.
# 답이 여러 표준에 걸쳐도 되지만 이 표준은 반드시 들어야 합니다.
REQUIRED_STANDARD_BY_QUESTION = {
    "밀폐공간 산소농도": "PCI-00-0GN-208",
    "발끝막이판 높이 기준": "PCI-00-0GN-110",
    "안전작업허가 유효기간": "PCI-00-0GN-108",
    "안전난간 높이 기준": "PCI-00-0GN-110",
    "작업환경측정 주기": "PCI-00-0GN-215",
}


def load_example_questions():
    """화면이 쓰는 목록을 그대로 불러옵니다."""
    # Qt 위젯을 만들지 않고 상수만 읽습니다.
    from desktop_app import EXAMPLE_QUESTIONS

    return list(
        EXAMPLE_QUESTIONS
    )


def answer_standards(
    question,
    chunks,
    index,
):
    results = [
        result
        for result in search_documents(
            question,
            chunks,
            index,
        )
        if document_is_allowed(
            question,
            result,
        )
    ]

    bundle = build_answer_bundle(
        question,
        results,
    )

    return bundle["groups"]


def check_compact_fact_answers(
    chunks,
    index,
    failures,
):
    from desktop_app import (
        compact_fact_definition,
        find_compact_fact_source,
        make_kosha_keywords,
        render_compact_fact_answer,
    )

    compact_questions = (
        (
            "밀폐공간 산소농도",
            "18.0% 이상 ~ 23.5% 미만",
            "PCI-00-0GN-208",
        ),
        (
            "발끝막이판 높이 기준",
            "10cm 이상",
            "PCI-00-0GN-110",
        ),
        (
            "안전난간 높이 기준",
            "90cm 이상",
            "PCI-00-0GN-110",
        ),
        (
            "안전작업허가 유효기간",
            "당일 한정 · 최대 8시간",
            "PCI-00-0GN-108",
        ),
        (
            "작업환경측정 주기",
            "반기 1회 이상",
            "PCR-M-101",
        ),
    )

    for question, expected_value, expected_standard in compact_questions:
        if compact_fact_definition(
            question
        ) is None:
            failures.append(
                question
                + ": 단답형 기준 질문으로 인식하지 못했습니다."
            )
            continue

        sources = search_documents(
            question,
            chunks,
            index,
        )

        selected = find_compact_fact_source(
            question,
            sources
        )

        html, links = render_compact_fact_answer(
            question,
            sources
        )

        if selected is None:
            failures.append(
                question
                + ": 핵심값이 적힌 원문을 찾지 못했습니다."
            )
            continue

        if selected["source"].get(
            "standard_number"
        ) != expected_standard:
            failures.append(
                question
                + ": 기대 사내 표준 "
                + expected_standard
                + "을 우선 연결하지 못했습니다."
            )

        if (
            expected_value not in html
            or len(links) != 1
        ):
            failures.append(
                question
                + ": 핵심 수치와 지침 링크만 표시되지 않았습니다."
            )

    detailed_questions = (
        "밀폐공간 산소농도 측정방법",
        "발끝막이판 생략 예외",
        "안전작업허가 연장 방법",
        "작업환경측정 주기 예외",
    )

    for detailed_question in detailed_questions:
        if compact_fact_definition(
            detailed_question
        ) is not None:
            failures.append(
                detailed_question
                + ": 상세 질문까지 단답형으로 잘못 분류했습니다."
            )

    if make_kosha_keywords(
        "발끝막이판 높이 기준"
    )[0] != "발끝막이판":
        failures.append(
            "발끝막이판 질문의 공단 API 검색어가 정확하지 않습니다."
        )


def main():
    sys.stdout.reconfigure(
        encoding="utf-8"
    )

    questions = load_example_questions()

    chunks, index, errors = load_documents_with_index()

    failures = []
    skipped = []

    for error in errors:
        failures.append(
            "문서 적재 오류: "
            + error
        )

    print()

    for question in questions:
        groups = answer_standards(
            question,
            chunks,
            index,
        )

        if not groups:
            failures.append(
                question
                + ": 근거를 하나도 찾지 못했습니다."
            )

            print(
                "  실패  "
                + question
                + "  → 근거 없음"
            )

            continue

        found_codes = [
            group["standard_number"]
            for group in groups
        ]

        required = REQUIRED_STANDARD_BY_QUESTION.get(
            question
        )

        if required is None:
            skipped.append(
                question
                + ": 기대 표준을 정해두지 않아 근거 유무만 확인했습니다."
            )

            print(
                "  확인  "
                + question
                + "  → "
                + str(len(groups))
                + "개 표준"
            )

            continue

        if required not in found_codes:
            failures.append(
                question
                + ": 기대 표준 "
                + required
                + " 가 근거에 없습니다 — 실제 "
                + ", ".join(
                    code or "(번호 없음)"
                    for code in found_codes
                )
            )

            print(
                "  실패  "
                + question
                + "  → "
                + required
                + " 없음"
            )

            continue

        print(
            "  통과  "
            + question
            + "  → "
            + required
            + " 포함, 표준 "
            + str(len(groups))
            + "개"
        )

    # 화면 목록과 기대표가 어긋나면 검사가 헛돌므로 함께 잡습니다.
    for question in questions:
        if question not in REQUIRED_STANDARD_BY_QUESTION:
            failures.append(
                question
                + ": 화면에 걸렸는데 기대 표준이 정해지지 않았습니다."
            )

    for question in REQUIRED_STANDARD_BY_QUESTION:
        if question not in questions:
            failures.append(
                question
                + ": 기대 표준만 남고 화면 목록에서 빠졌습니다."
            )

    check_compact_fact_answers(
        chunks,
        index,
        failures,
    )

    print()
    print("[안 잰 것]")

    if not skipped:
        print("  없음")
    else:
        for note in skipped:
            print("  · " + note)

    print()
    print("[판정]")

    if failures:
        for failure in failures:
            print("  실패 — " + failure)

        print()
        print(
            "실패 "
            + str(len(failures))
            + "건"
        )

        return 1

    print(
        "  통과 — 예시 질문 "
        + str(len(questions))
        + "건 모두 기대 표준에서 근거를 찾았습니다"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
