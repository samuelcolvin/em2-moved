.DEFAULT_GOAL := all

.PHONY: install
install:
	pip install -U setuptools pip
	pip install -Ur tests/requirements.txt
	pip install -Ue .

.PHONY: isort
isort:
	isort -rc em2
	isort -rc tests

.PHONY: lint
lint:
	python setup.py check -rms
	flake8 --version
	flake8 em2/ tests/
	pytest em2 -p no:sugar -q

.PHONY: test
test:
	pytest --cov=em2

.PHONY: testcov
testcov:
	pytest --cov=em2 && (echo "building coverage html"; coverage html)

.PHONY: all
all: testcov lint

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
