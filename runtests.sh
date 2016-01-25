#!/usr/bin/env bash
py.test
pytest=$?
echo "pytest exit code: ${pytest}"
flake8 em2/ tests/
flake=$?
echo "flake exit code:  ${flake}"
exit $((${flake} + ${pytest}))
