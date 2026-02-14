#!/usr/bin/env python3
"""
承認ワークフローデータベース初期化スクリプト

既存のデータベースに承認ワークフローのテーブルを追加します。
"""

import asyncio
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import aiosqlite


async def init_approval_tables(db_path: str):
    """
    承認ワークフローのテーブルを初期化

    Args:
        db_path: SQLite データベースファイルパス
    """
    print(f"Initializing approval workflow tables in: {db_path}")

    async with aiosqlite.connect(db_path) as db:
        # SQLファイルの読み込み
        schema_file = project_root / "docs" / "database" / "approval-schema.sql"
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_file}")

        sql_content = schema_file.read_text()

        # SQL文を実行（複数のステートメントを分割して実行）
        await db.executescript(sql_content)
        await db.commit()

        # テーブルが作成されたか確認
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'approval_%'"
        ) as cursor:
            tables = await cursor.fetchall()

        print("\n✅ Successfully created approval workflow tables:")
        for table in tables:
            print(f"   - {table[0]}")

        # サンプルデータが投入されたか確認
        async with db.execute("SELECT COUNT(*) FROM approval_policies") as cursor:
            policy_count = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM approval_requests") as cursor:
            request_count = (await cursor.fetchone())[0]

        print(f"\n✅ Initial data:")
        print(f"   - approval_policies: {policy_count} records")
        print(f"   - approval_requests: {request_count} sample records")

    print("\n✅ Database initialization completed successfully!")


async def main():
    """メイン関数"""
    db_path = project_root / "data" / "dev" / "database.db"

    if not db_path.exists():
        print(f"❌ Database file not found: {db_path}")
        print("Please create the main database first.")
        sys.exit(1)

    try:
        await init_approval_tables(str(db_path))
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
