#!/usr/bin/env bash
py.test --cov=em2 tests/
pytest=$?
echo "pytest exit code: ${pytest}"
flake8 --max-line-length 120 em2/ tests/
flake=$?
echo "flake exit code:  ${flake}"
exit $((${flake} + ${pytest}))
