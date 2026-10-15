"""첨부한 공식 참고자료가 대표 질의로 검색되는지 검증합니다.

실행: python verify_reference_search.py
"""

import sys

from document_engine import (
    SOURCE_TYPE_OFFICIAL_REFERENCE,
    build_answer_bundle,
    load_documents_with_index,
    search_documents,
    search_reference_documents,
)


CASES = (
    (
        "반기 1회 이상 점검 주기는 어떻게 되나요?",
        "06_참고_중대재해처벌법",
    ),
    (
        "물질안전보건자료 개정 주기가 별도로 정해져 있나요?",
        "07_참고_물질안전보건자료",
    ),
    (
        "고정식 수직사다리 등받이울 설치 기준",
        "08_참고_산업안전보건",
    ),
    (
        "에어백 조끼 구입비를 산업안전보건관리비로 사용할 수 있나요?",
        "09_참고_건설업_산업안전보건관리비_해설",
    ),
    (
        "총공사금액 2천만 원 이상 산업안전보건관리비 적용범위",
        "10_참고_건설업_산업안전보건관리비_계상",
    ),
)


def main():
    sys.stdout.reconfigure(
        encoding="utf-8"
    )

    chunks, index, errors = load_documents_with_index()

    from desktop_app import render_internal_bundle

    failures = list(
        errors
    )

    reference_chunks = [
        chunk
        for chunk in chunks
        if chunk.get(
            "source_type"
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE
    ]

    if not reference_chunks:
        failures.append(
            "공식 참고자료 조각이 하나도 적재되지 않았습니다."
        )

    internal_probe = search_documents(
        "밀폐공간 적정공기 기준",
        chunks,
        index,
    )

    if any(
        result.get(
            "source_type"
        ) == SOURCE_TYPE_OFFICIAL_REFERENCE
        for result in internal_probe
    ):
        failures.append(
            "기존 사내 표준 검색에 공식 참고자료가 섞였습니다."
        )

    for question, expected_prefix in CASES:
        results = search_reference_documents(
            question,
            chunks,
            index,
        )

        matching_results = [
            result
            for result in results
            if result.get(
                "file_name",
                "",
            ).startswith(
                expected_prefix
            )
        ]

        bundle = build_answer_bundle(
            question,
            results,
        )

        if not matching_results:
            failures.append(
                question
                + ": 기대 자료를 검색하지 못했습니다."
            )

            print(
                "  실패  "
                + question
            )
            continue

        if not bundle.get(
            "reference_groups"
        ):
            failures.append(
                question
                + ": 검색 결과에서 표시할 질의회시 문장을 만들지 못했습니다."
            )

            print(
                "  실패  "
                + question
                + " → 표시 문장 없음"
            )
            continue

        reference_html, source_links = render_internal_bundle(
            {
                "title": bundle.get(
                    "reference_title",
                    "",
                ),
                "groups": bundle.get(
                    "reference_groups",
                    [],
                ),
            },
            question,
            "all",
        )

        if (
            not source_links
            or "관련 질의회시·공식 자료" not in reference_html
            or "정리본 통합 장" in reference_html
        ):
            failures.append(
                question
                + ": 공식 참고자료 화면 표시 형식이 올바르지 않습니다."
            )

            print(
                "  실패  "
                + question
                + " → 화면 표시 오류"
            )
            continue

        first_result = matching_results[0]

        print(
            "  통과  "
            + question
            + " → "
            + first_result.get(
                "standard_name",
                "",
            )
            + " PDF "
            + str(
                first_result.get(
                    "page",
                    "?",
                )
            )
            + "쪽"
        )

    print()
    print("[판정]")

    if failures:
        for failure in failures:
            print(
                "  실패 — "
                + failure
            )

        return 1

    print(
        "  통과 — 공식 참고자료 5종의 대표 검색과 분리 표시 정상"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
