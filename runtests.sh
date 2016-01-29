#!/usr/bin/env bash
py.test --cov=em2
pytest=$?
echo "pytest exit code: ${pytest}"
flake8 em2/ tests/
flake=$?
echo "flake8 exit code: ${flake}"
exit $((${flake} + ${pytest}))
