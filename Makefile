.PHONY: install lint typecheck test demo clean

install:
	python3 -m pip install -e ".[dev]"

lint:
	ruff check src/ tests/

typecheck:
	mypy src/ tests/

test:
	pytest -v

demo:
	python3 -m shorts_engine.cli --demo --out-dir build/demo_15s

clean:
	rm -rf build/ .pytest_cache/ .mypy_cache/ .ruff_cache/
