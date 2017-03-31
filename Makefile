.PHONY: install
install:
	pip install -U setuptools pip
	pip install -Ue .
	pip install -Ur tests/requirements.txt

.PHONY: isort
isort:
	isort -rc -w 120 em2
	isort -rc -w 120 tests

.PHONY: lint
lint:
	python setup.py check -rms
	flake8 --version
	flake8 em2/ tests/
	pytest em2 -p no:sugar -q --cache-clear

.PHONY: test
test:
	pytest --cov=em2 && coverage combine

.PHONY: testcov
testcov: lint
	pytest --cov=em2 --fast && (echo "building coverage html"; coverage combine; coverage html)

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	python setup.py clean