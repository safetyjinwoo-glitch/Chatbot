# -*- coding: utf-8 -*-
"""
퓨밍이 안전비서 기록 저장소

저장 파일
- data/chat_history.db
- data/safety_news.db
"""

import hashlib
import json
import os
import re
import sqlite3

from datetime import datetime, timedelta, timezone


# ============================================================
# 기본 설정
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DATA_DIR = os.path.join(
    BASE_DIR,
    "data",
)

CHAT_DATABASE_PATH = os.path.join(
    DATA_DIR,
    "chat_history.db",
)

NEWS_DATABASE_PATH = os.path.join(
    DATA_DIR,
    "safety_news.db",
)

KST = timezone(
    timedelta(hours=9)
)

BOOKMARK_COLORS = [
    "#FFF1A8",
    "#FFD6A5",
    "#CAFFBF",
    "#BDE0FE",
    "#CDB4DB",
    "#FFC8DD",
    "#D8F3DC",
    "#FDE2E4",
]


# ============================================================
# 공통 함수
# ============================================================

def ensure_data_directory():
    try:
        os.makedirs(
            DATA_DIR,
            exist_ok=True,
        )
    except OSError as error:
        print(
            "[데이터 폴더 생성 실패] "
            + str(error)
        )


def now_kst():
    return datetime.now(KST)


def now_text():
    return now_kst().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def normalize_space(text):
    return " ".join(
        str(text or "").split()
    )


def safe_json_dumps(value):
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
        )
    except Exception:
        return "[]"


def safe_json_loads(value):
    try:
        result = json.loads(
            value or "[]"
        )

        if isinstance(result, list):
            return result

        return []

    except Exception:
        return []


def trim_question(
    question,
    maximum=38,
):
    text = normalize_space(question)

    if len(text) <= maximum:
        return text

    return (
        text[:maximum - 1]
        + "…"
    )


def normalize_news_title(title):
    return re.sub(
        "[^0-9A-Za-z가-힣]",
        "",
        str(title or ""),
    ).lower()


def make_news_key(
    title,
    link,
):
    normalized_link = str(
        link or ""
    ).strip().lower()

    normalized_title = normalize_news_title(
        title
    )

    source = (
        normalized_link
        if normalized_link
        else normalized_title
    )

    return hashlib.sha256(
        source.encode(
            "utf-8",
            errors="ignore",
        )
    ).hexdigest()


# ============================================================
# DB 연결
# ============================================================

def get_chat_connection():
    ensure_data_directory()

    connection = sqlite3.connect(
        CHAT_DATABASE_PATH,
        timeout=20,
    )

    connection.row_factory = sqlite3.Row

    return connection


def get_news_connection():
    ensure_data_directory()

    connection = sqlite3.connect(
        NEWS_DATABASE_PATH,
        timeout=20,
    )

    connection.row_factory = sqlite3.Row

    return connection


# ============================================================
# DB 초기화
# ============================================================

def init_chat_database():
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                bookmark_title TEXT NOT NULL,
                bookmark_color TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_chat_history_created_at
            ON chat_history(created_at DESC)
            """
        )

        connection.commit()

    finally:
        connection.close()


def init_news_database():
    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS safety_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_key TEXT NOT NULL UNIQUE,
                source TEXT,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                published TEXT,
                published_timestamp REAL DEFAULT 0,
                priority INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
            idx_safety_news_news_key
            ON safety_news(news_key)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_safety_news_published
            ON safety_news(
                published_timestamp DESC,
                id DESC
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_safety_news_priority
            ON safety_news(
                priority DESC,
                published_timestamp DESC
            )
            """
        )

        connection.commit()

    finally:
        connection.close()


def init_databases():
    ensure_data_directory()
    init_chat_database()
    init_news_database()


# ============================================================
# 출처 정보 정리
# ============================================================

def source_summary_list(sources):
    output = []
    seen = set()

    for source in sources or []:
        standard_number = str(
            source.get(
                "standard_number",
                "",
            )
            or ""
        ).strip()

        standard_name = str(
            source.get(
                "standard_name",
                "",
            )
            or source.get(
                "document_name",
                "",
            )
            or ""
        ).strip()

        revision = str(
            source.get(
                "revision",
                "",
            )
            or ""
        ).strip()

        section = str(
            source.get(
                "section",
                "",
            )
            or ""
        ).strip()

        file_name = str(
            source.get(
                "file_name",
                "",
            )
            or ""
        ).strip()

        source_key = (
            standard_number,
            standard_name,
            section,
            file_name,
        )

        if source_key in seen:
            continue

        seen.add(source_key)

        output.append({
            "standard_number": standard_number,
            "standard_name": standard_name,
            "revision": revision,
            "section": section,
            "file_name": file_name,
        })

    return output


# ============================================================
# 책갈피 색상
# ============================================================

def choose_bookmark_color():
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM chat_history
            """
        )

        row = cursor.fetchone()

        count = (
            int(row["count"])
            if row is not None
            else 0
        )

        return BOOKMARK_COLORS[
            count % len(BOOKMARK_COLORS)
        ]

    finally:
        connection.close()


# ============================================================
# 대화 기록 저장
# ============================================================

def save_chat_history(
    question,
    answer,
    sources=None,
    bookmark_color="",
):
    question_text = str(
        question or ""
    ).strip()

    answer_text = str(
        answer or ""
    ).strip()

    if not question_text:
        return None

    if not answer_text:
        answer_text = "저장된 답변이 없습니다."

    if bookmark_color:
        color = bookmark_color.strip()
    else:
        color = choose_bookmark_color()

    bookmark_title = trim_question(
        question_text
    )

    source_summaries = source_summary_list(
        sources or []
    )

    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO chat_history (
                question,
                answer,
                bookmark_title,
                bookmark_color,
                sources_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                question_text,
                answer_text,
                bookmark_title,
                color,
                safe_json_dumps(
                    source_summaries
                ),
                now_text(),
            ),
        )

        history_id = cursor.lastrowid

        connection.commit()

        return history_id

    except Exception as error:
        print(
            "[대화 기록 저장 실패] "
            + str(error)
        )

        return None

    finally:
        connection.close()


# ============================================================
# 대화 기록 변환 및 조회
# ============================================================

def row_to_chat_dictionary(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "bookmark_title": row["bookmark_title"],
        "bookmark_color": row["bookmark_color"],
        "sources": safe_json_loads(
            row["sources_json"]
        ),
        "created_at": row["created_at"],
    }


def get_chat_history(history_id):
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                question,
                answer,
                bookmark_title,
                bookmark_color,
                sources_json,
                created_at
            FROM chat_history
            WHERE id = ?
            """,
            (
                int(history_id),
            ),
        )

        return row_to_chat_dictionary(
            cursor.fetchone()
        )

    finally:
        connection.close()


def list_chat_history(
    limit=100,
    offset=0,
):
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                question,
                answer,
                bookmark_title,
                bookmark_color,
                sources_json,
                created_at
            FROM chat_history
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            (
                int(limit),
                int(offset),
            ),
        )

        return [
            row_to_chat_dictionary(row)
            for row in cursor.fetchall()
        ]

    finally:
        connection.close()


def search_chat_history(
    keyword,
    limit=100,
):
    search_word = str(
        keyword or ""
    ).strip()

    if not search_word:
        return list_chat_history(
            limit=limit
        )

    like_value = (
        "%"
        + search_word
        + "%"
    )

    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                question,
                answer,
                bookmark_title,
                bookmark_color,
                sources_json,
                created_at
            FROM chat_history
            WHERE question LIKE ?
               OR answer LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                like_value,
                like_value,
                int(limit),
            ),
        )

        return [
            row_to_chat_dictionary(row)
            for row in cursor.fetchall()
        ]

    finally:
        connection.close()


def count_chat_history():
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM chat_history
            """
        )

        row = cursor.fetchone()

        if row is None:
            return 0

        return int(
            row["count"]
        )

    finally:
        connection.close()


# ============================================================
# 대화 기록 삭제
# ============================================================

def delete_chat_history(history_id):
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM chat_history
            WHERE id = ?
            """,
            (
                int(history_id),
            ),
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def clear_chat_history():
    connection = get_chat_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM chat_history
            """
        )

        connection.commit()

    finally:
        connection.close()


# ============================================================
# 안전뉴스 저장
# ============================================================

def save_news_items(news_items):
    inserted_count = 0
    updated_count = 0

    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        for item in news_items or []:
            title = normalize_space(
                item.get(
                    "title",
                    "",
                )
            )

            if not title:
                continue

            link = str(
                item.get(
                    "link",
                    "",
                )
                or ""
            ).strip()

            news_key = make_news_key(
                title,
                link,
            )

            source = normalize_space(
                item.get(
                    "source",
                    "",
                )
            )

            description = normalize_space(
                item.get(
                    "description",
                    "",
                )
            )

            published = normalize_space(
                item.get(
                    "published",
                    "",
                )
            )

            try:
                published_timestamp = float(
                    item.get(
                        "published_timestamp",
                        0,
                    )
                    or 0
                )
            except Exception:
                published_timestamp = 0.0

            try:
                priority = int(
                    item.get(
                        "priority",
                        0,
                    )
                    or 0
                )
            except Exception:
                priority = 0

            cursor.execute(
                """
                SELECT id
                FROM safety_news
                WHERE news_key = ?
                """,
                (
                    news_key,
                ),
            )

            existing = cursor.fetchone()

            if existing is None:
                cursor.execute(
                    """
                    INSERT INTO safety_news (
                        news_key,
                        source,
                        title,
                        description,
                        link,
                        published,
                        published_timestamp,
                        priority,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        news_key,
                        source,
                        title,
                        description,
                        link,
                        published,
                        published_timestamp,
                        priority,
                        now_text(),
                    ),
                )

                inserted_count += 1

            else:
                cursor.execute(
                    """
                    UPDATE safety_news
                    SET
                        source = ?,
                        title = ?,
                        description = ?,
                        link = ?,
                        published = ?,
                        published_timestamp = ?,
                        priority = ?
                    WHERE news_key = ?
                    """,
                    (
                        source,
                        title,
                        description,
                        link,
                        published,
                        published_timestamp,
                        priority,
                        news_key,
                    ),
                )

                updated_count += 1

        connection.commit()

    except Exception as error:
        print(
            "[안전뉴스 저장 실패] "
            + str(error)
        )

    finally:
        connection.close()

    return {
        "inserted": inserted_count,
        "updated": updated_count,
    }


# ============================================================
# 안전뉴스 조회
# ============================================================

def row_to_news_dictionary(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "news_key": row["news_key"],
        "source": row["source"] or "",
        "title": row["title"] or "",
        "description": row["description"] or "",
        "link": row["link"] or "",
        "published": row["published"] or "",
        "published_timestamp": (
            row["published_timestamp"]
            or 0
        ),
        "priority": row["priority"] or 0,
        "created_at": row["created_at"] or "",
    }


def list_saved_news(
    limit=30,
    offset=0,
    keyword="",
):
    search_word = str(
        keyword or ""
    ).strip()

    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        if search_word:
            like_value = (
                "%"
                + search_word
                + "%"
            )

            cursor.execute(
                """
                SELECT
                    id,
                    news_key,
                    source,
                    title,
                    description,
                    link,
                    published,
                    published_timestamp,
                    priority,
                    created_at
                FROM safety_news
                WHERE title LIKE ?
                   OR description LIKE ?
                   OR source LIKE ?
                ORDER BY
                    published_timestamp DESC,
                    priority DESC,
                    id DESC
                LIMIT ? OFFSET ?
                """,
                (
                    like_value,
                    like_value,
                    like_value,
                    int(limit),
                    int(offset),
                ),
            )

        else:
            cursor.execute(
                """
                SELECT
                    id,
                    news_key,
                    source,
                    title,
                    description,
                    link,
                    published,
                    published_timestamp,
                    priority,
                    created_at
                FROM safety_news
                ORDER BY
                    published_timestamp DESC,
                    priority DESC,
                    id DESC
                LIMIT ? OFFSET ?
                """,
                (
                    int(limit),
                    int(offset),
                ),
            )

        return [
            row_to_news_dictionary(row)
            for row in cursor.fetchall()
        ]

    finally:
        connection.close()


def count_saved_news(keyword=""):
    search_word = str(
        keyword or ""
    ).strip()

    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        if search_word:
            like_value = (
                "%"
                + search_word
                + "%"
            )

            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM safety_news
                WHERE title LIKE ?
                   OR description LIKE ?
                   OR source LIKE ?
                """,
                (
                    like_value,
                    like_value,
                    like_value,
                ),
            )

        else:
            cursor.execute(
                """
                SELECT COUNT(*) AS count
                FROM safety_news
                """
            )

        row = cursor.fetchone()

        if row is None:
            return 0

        return int(
            row["count"]
        )

    finally:
        connection.close()


# ============================================================
# 안전뉴스 삭제
# ============================================================

def delete_saved_news(news_id):
    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM safety_news
            WHERE id = ?
            """,
            (
                int(news_id),
            ),
        )

        connection.commit()

        return cursor.rowcount > 0

    finally:
        connection.close()


def clear_saved_news():
    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM safety_news
            """
        )

        connection.commit()

    finally:
        connection.close()


# ============================================================
# 오래된 뉴스 정리
# ============================================================

def delete_news_older_than(days=365):
    cutoff = (
        now_kst()
        - timedelta(
            days=int(days)
        )
    ).timestamp()

    connection = get_news_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            DELETE FROM safety_news
            WHERE published_timestamp > 0
              AND published_timestamp < ?
            """,
            (
                cutoff,
            ),
        )

        deleted_count = cursor.rowcount

        connection.commit()

        return deleted_count

    finally:
        connection.close()


# ============================================================
# DB 통계
# ============================================================

def database_statistics():
    return {
        "chat_count": count_chat_history(),
        "news_count": count_saved_news(),
        "chat_database": CHAT_DATABASE_PATH,
        "news_database": NEWS_DATABASE_PATH,
    }


# ============================================================
# 직접 실행 시 DB 생성 확인
# ============================================================

def main():
    init_databases()

    statistics = database_statistics()

    print(
        "[대화 기록] "
        + str(
            statistics["chat_count"]
        )
        + "건"
    )

    print(
        "[안전뉴스] "
        + str(
            statistics["news_count"]
        )
        + "건"
    )

    print(
        "[대화 DB] "
        + statistics["chat_database"]
    )

    print(
        "[뉴스 DB] "
        + statistics["news_database"]
    )


if __name__ == "__main__":
    main()
