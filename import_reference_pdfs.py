# -*- coding: utf-8 -*-
"""공식 질의회시·고시 PDF를 검색용 UTF-8 텍스트로 변환합니다.

실행 예:
    python import_reference_pdfs.py
    python import_reference_pdfs.py --source-dir C:\\자료 --documents-dir .\\documents
"""

import argparse
import re
import sys
import unicodedata

from pathlib import Path

from pypdf import PdfReader


REFERENCE_DOCUMENTS = (
    {
        "input_name": "중대재해처벌법 중대산업재해 질의회시집(26년6월)_배포.pdf",
        "output_name": "06_참고_중대재해처벌법_중대산업재해_질의회시집_2026-06.txt",
        "category": "질의회시",
        "title": "중대재해처벌법 중대산업재해 질의회시집",
        "publisher": "고용노동부",
        "published_at": "2026. 6.",
    },
    {
        "input_name": "MSDS Q&A 2023년 개정판(최종) (1).pdf",
        "output_name": "07_참고_물질안전보건자료_MSDS_Q&A_2023.txt",
        "category": "Q&A",
        "title": "물질안전보건자료(MSDS) Q&A 2023년 개정판",
        "publisher": "고용노동부 산업안전보건본부",
        "published_at": "2023. 9.",
    },
    {
        "input_name": "산압언전보건법 질의회시집(2022.5.).pdf",
        "output_name": "08_참고_산업안전보건_질의회시집_2022-05.txt",
        "category": "질의회시",
        "title": "산업안전보건 질의회시집",
        "publisher": "고용노동부",
        "published_at": "2022. 5.",
    },
    {
        "input_name": "건설업 산업안전 보건관리비 해설 및 질의회시집(최종).pdf",
        "output_name": "09_참고_건설업_산업안전보건관리비_해설_및_질의회시집_2025-06.txt",
        "category": "해설·질의회시",
        "title": "건설업 산업안전보건관리비 해설 및 질의회시집",
        "publisher": "고용노동부",
        "published_at": "2025. 6.",
    },
    {
        "input_name": "건설업 산업안전보건관리비 계상 및 사용기준(고용노동부고시)(제2025-11호)(20250212).pdf",
        "output_name": "10_참고_건설업_산업안전보건관리비_계상_및_사용기준_고시_2025-11호.txt",
        "category": "고용노동부 고시",
        "title": "건설업 산업안전보건관리비 계상 및 사용기준",
        "publisher": "고용노동부",
        "published_at": "2025. 2. 12.",
    },
)


def clean_extracted_text(text):
    output = []

    for character in unicodedata.normalize(
        "NFC",
        text or "",
    ):
        if character in "\n\t":
            output.append(character)
            continue

        category = unicodedata.category(
            character
        )

        if category == "Co":
            output.append(" • ")
            continue

        if category.startswith("C"):
            output.append(" ")
            continue

        output.append(character)

    lines = []

    for raw_line in "".join(
        output
    ).splitlines():
        line = re.sub(
            "[ \\t]{2,}",
            " ",
            raw_line,
        ).strip()

        lines.append(line)

    cleaned = "\n".join(
        lines
    )

    cleaned = re.sub(
        "\n{3,}",
        "\n\n",
        cleaned,
    )

    return cleaned.strip()


def build_search_text(
    source_path,
    document,
):
    reader = PdfReader(
        str(source_path)
    )

    metadata = (
        "<source-metadata>\n"
        "type=official_reference\n"
        "category="
        + document["category"]
        + "\n"
        "title="
        + document["title"]
        + "\n"
        "publisher="
        + document["publisher"]
        + "\n"
        "published_at="
        + document["published_at"]
        + "\n"
        "original_file="
        + document["input_name"]
        + "\n</source-metadata>"
    )

    pages = [metadata]

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        page_text = clean_extracted_text(
            page.extract_text() or ""
        )

        if not page_text:
            continue

        pages.append(
            "<page-"
            + str(page_number)
            + ">\n"
            + page_text
            + "\n</page-"
            + str(page_number)
            + ">"
        )

    return (
        "\n\n".join(
            pages
        ).strip()
        + "\n"
    )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "공식 PDF 5종을 챗봇 검색용 텍스트로 변환합니다."
        )
    )

    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.home() / "Downloads",
        help="원본 PDF가 있는 폴더",
    )

    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=(
            Path(__file__).resolve().parent
            / "documents"
        ),
        help="검색용 TXT를 저장할 documents 폴더",
    )

    return parser.parse_args()


def main():
    if hasattr(
        sys.stdout,
        "reconfigure",
    ):
        sys.stdout.reconfigure(
            encoding="utf-8"
        )

    arguments = parse_arguments()

    missing = [
        document["input_name"]
        for document in REFERENCE_DOCUMENTS
        if not (
            arguments.source_dir
            / document["input_name"]
        ).is_file()
    ]

    if missing:
        for file_name in missing:
            print(
                "[누락] "
                + file_name
            )

        return 1

    arguments.documents_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    for document in REFERENCE_DOCUMENTS:
        source_path = (
            arguments.source_dir
            / document["input_name"]
        )

        output_path = (
            arguments.documents_dir
            / document["output_name"]
        )

        search_text = build_search_text(
            source_path,
            document,
        )

        output_path.write_text(
            search_text,
            encoding="utf-8",
        )

        print(
            "[완료] "
            + output_path.name
            + " ("
            + format(
                len(search_text),
                ",",
            )
            + "자)"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
