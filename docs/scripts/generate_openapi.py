#!/usr/bin/env python3
"""
OpenAPI 仕様を生成するスクリプト

FastAPI アプリケーションから OpenAPI JSON を生成し、
docs/openapi.json に保存します。
"""

import json
import sys
from pathlib import Path

# プロジェクトルートを Python パスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.api.main import app


def generate_openapi_spec():
    """OpenAPI 仕様を生成"""
    openapi_schema = app.openapi()

    # 出力先
    output_path = project_root / "docs" / "openapi.json"

    # JSON として保存
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2, ensure_ascii=False)

    print(f"✅ OpenAPI specification generated: {output_path}")
    print(f"   Title: {openapi_schema['info']['title']}")
    print(f"   Version: {openapi_schema['info']['version']}")
    print(f"   Endpoints: {len(openapi_schema['paths'])} paths")


if __name__ == "__main__":
    generate_openapi_spec()
