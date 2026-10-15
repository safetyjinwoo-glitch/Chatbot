"""사내 표준 귀속 검증

문서 원문을 진본으로 삼아 색인이 귀속한 표준명·표준번호를 되짚습니다.
검사가 스스로 경계를 말하도록, 안 잰 것을 판정 옆에 함께 찍습니다.

실행: python verify_attribution.py
"""

import os
import re
import sys

from document_engine import (
    DOCUMENTS_DIR,
    SECTION_NUMBER_PATTERN,
    collect_divider_blocks,
    is_divider_line,
    load_documents_with_index,
    normalize_text,
    parse_standard_header,
)


# 원문에 실려 있는 문장과 그 문장이 속한 표준번호입니다.
# 진본은 문서 원문이고, 여기 적힌 것은 원문에서 읽어 세운 기대값입니다.
EXPECTED_ATTRIBUTIONS = (
    (
        "비상구조·인명구조는 공기호흡기를 사용할 수 있음",
        "",
        "지침 간 중복·상충 확인 필요사항",
    ),
    (
        "고용노동부장관의 허가 없이 제조 또는 사용할 수 없는 물질",
        "PCI-00-0GN-407",
        "허가대상 유해물질 취급 및 관리 지침",
    ),
    (
        "밀폐공간 작업 프로그램을 수립·시행하여",
        "PCI-00-0GN-208",
        "밀폐공간 작업 프로그램 운영 지침",
    ),
    (
        "임시건강진단 : 동일부서 유사질병 또는 직업병 유소견자 발생 시",
        "PCI-00-0GN-201",
        "건강진단관리 지침",
    ),
    (
        "소방안전관리자를 선임",
        "PCR-M-131",
        "소방안전관리 규정",
    ),
)


def read_document_lines(file_name):
    path = os.path.join(
        DOCUMENTS_DIR,
        file_name,
    )

    with open(
        path,
        encoding="utf-8",
    ) as handle:
        raw = handle.read()

    return normalize_text(
        raw
    ).splitlines()


def check_header_coverage(failures, skipped):
    """구분선 블록 중 경계로 인정되지 못한 것을 셉니다."""
    file_names = sorted([
        file_name
        for file_name in os.listdir(
            DOCUMENTS_DIR
        )
        if file_name.lower().endswith(".txt")
    ])

    for file_name in file_names:
        lines = read_document_lines(
            file_name
        )

        blocks = collect_divider_blocks(
            lines
        )

        if not blocks:
            skipped.append(
                file_name
                + ": 구분선 블록이 없어 헤더 인식 검사 대상이 아닙니다."
            )

            continue

        highest_number = 0
        unresolved = []

        for block in blocks:
            number_match = SECTION_NUMBER_PATTERN.match(
                block["text"]
            )

            has_header = (
                parse_standard_header(
                    block["text"]
                )
                is not None
            )

            if number_match is None:
                if not has_header:
                    unresolved.append(
                        block
                    )

                continue

            section_number = int(
                number_match.group(1)
            )

            if section_number <= highest_number:
                # 본문 안의 조항 번호이므로 경계가 아닙니다.
                continue

            highest_number = section_number

        for block in unresolved:
            # 번호도 표준번호도 없는 블록은 편 구분 표시 등 안내문입니다.
            skipped.append(
                file_name
                + " "
                + str(block["start"] + 2)
                + "행: 번호·표준번호가 없어 경계로 세지 않았습니다 — "
                + block["text"][:40]
            )


def check_expected_attributions(
    chunks,
    failures,
    skipped,
):
    for (
        needle,
        expected_code,
        expected_name,
    ) in EXPECTED_ATTRIBUTIONS:
        matched = [
            chunk
            for chunk in chunks
            if needle in chunk.get(
                "text",
                "",
            )
        ]

        if not matched:
            failures.append(
                "문장을 어느 조각에서도 찾지 못했습니다: "
                + needle
            )

            continue

        for chunk in matched:
            actual_code = chunk.get(
                "standard_number",
                "",
            )

            actual_name = chunk.get(
                "standard_name",
                "",
            )

            if (
                actual_code == expected_code
                and actual_name == expected_name
            ):
                continue

            failures.append(
                "귀속 불일치: "
                + needle
                + " → 기대 "
                + (expected_code or "(번호 없음)")
                + " "
                + expected_name
                + " / 실제 "
                + (actual_code or "(번호 없음)")
                + " "
                + actual_name
            )


def check_single_standard_domination(
    chunks,
    failures,
    skipped,
):
    """표준을 여러 건 실은 파일에서 한 표준이 과반을 먹으면 경계가 무너진 것입니다."""
    per_file = {}

    for chunk in chunks:
        file_name = chunk.get(
            "file_name",
            "",
        )

        key = (
            chunk.get(
                "standard_number",
                "",
            ),
            chunk.get(
                "standard_name",
                "",
            ),
        )

        counters = per_file.setdefault(
            file_name,
            {},
        )

        counters[key] = counters.get(
            key,
            0,
        ) + 1

    for file_name, counters in sorted(
        per_file.items()
    ):
        total = sum(
            counters.values()
        )

        key, largest = max(
            counters.items(),
            key=lambda item: item[1],
        )

        # 표준이 적게 실린 파일은 한 표준의 점유율이 높아도 정상입니다.
        standard_count = len(
            counters
        )

        if standard_count < 3:
            skipped.append(
                file_name
                + ": 표준 "
                + str(standard_count)
                + "건뿐이라 점유율 검사 대상이 아닙니다."
            )

            continue

        # 표준마다 분량이 달라 균등 분배는 기준이 되지 못합니다.
        # 경계가 무너지면 한 표준이 파일을 삼키므로 과반만 잡습니다.
        share = largest / total

        if share > 0.5:
            failures.append(
                file_name
                + ": 표준 "
                + str(standard_count)
                + "건 중 "
                + (key[1] or "(표준명 없음)")
                + " 하나가 조각 "
                + str(total)
                + "개의 "
                + str(round(share * 100))
                + "%를 차지합니다."
            )


def main():
    sys.stdout.reconfigure(
        encoding="utf-8"
    )

    chunks, _, errors = load_documents_with_index()

    failures = []
    skipped = []

    for error in errors:
        failures.append(
            "문서 적재 오류: "
            + error
        )

    check_header_coverage(
        failures,
        skipped,
    )

    check_expected_attributions(
        chunks,
        failures,
        skipped,
    )

    check_single_standard_domination(
        chunks,
        failures,
        skipped,
    )

    print()
    print(
        "검사 대상: 조각 "
        + str(len(chunks))
        + "개"
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

    print("  통과 — 위 「안 잰 것」 범위 밖에서 귀속 결함 없음")

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
