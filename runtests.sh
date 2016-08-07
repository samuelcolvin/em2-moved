#!/usr/bin/env bash
#
# Simple wrapper to run tests fast, collect coverage and check linting
#
py.test --cov=em2 --fast
pytest=$?
if [ $pytest == 0 ] ; then
    echo building coverage html
    coverage html
fi
echo "pytest exit code: ${pytest}"
flake8 em2/ tests/
flake=$?
echo "flake8 exit code: ${flake}"
exit $((${flake} + ${pytest}))
