.PHONY: check lint demo

lint:
	python3 -m py_compile money_tracker/*.py tests/*.py demo.py sample_data/*.py

check: lint
	python3 tests/test_core.py
	python3 tests/test_adapters.py

demo:
	python3 demo.py
