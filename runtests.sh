#!/usr/bin/env bash
py.test --cov=em2
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
