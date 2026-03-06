.PHONY: test test-e2e lint security-check coverage clean build-frontend help

## デフォルトターゲット
help:
	@echo "使用可能なターゲット:"
	@echo "  make test            - ユニット/統合テストを実行"
	@echo "  make test-e2e        - E2Eテストを実行"
	@echo "  make lint            - コードフォーマット・Lint チェック"
	@echo "  make security-check  - セキュリティチェック (bandit + shell=True 検出)"
	@echo "  make coverage        - カバレッジレポート生成 (80%以上で合格)"
	@echo "  make build-frontend  - frontend/dev/ → frontend/prod/ へ全HTMLをコピー"
	@echo "  make clean           - __pycache__ と *.pyc を削除"

## ユニット/統合テスト
test:
	pytest tests/ --ignore=tests/e2e -q --tb=short

## E2Eテスト
test-e2e:
	pytest -c pytest-e2e.ini

## コードフォーマット・Lint
lint:
	black --check backend/
	flake8 backend/

## セキュリティチェック
security-check:
	bandit -r backend/ -ll
	@if grep -r "shell=True" backend/ --include="*.py" 2>/dev/null | grep -v '^\s*#' | grep -v '#.*shell=True' | grep "shell=True"; then \
		echo "❌ ERROR: shell=True detected in backend/"; \
		exit 1; \
	else \
		echo "✅ No shell=True found"; \
	fi

## カバレッジレポート生成
coverage:
	pytest tests/ --ignore=tests/e2e --cov=backend --cov-report=html --cov-report=term-missing --cov-fail-under=80

## frontend/dev/ → frontend/prod/ へ全HTMLをコピー
build-frontend:
	cp frontend/dev/*.html frontend/prod/
	@echo "✅ frontend/prod/ を frontend/dev/ から更新しました"

## キャッシュ削除
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	rm -rf htmlcov/ .pytest_cache/ 2>/dev/null || true
