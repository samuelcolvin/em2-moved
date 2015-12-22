#!/usr/bin/env bash
flake8 --max-line-length 120 em2/ tests/
flake=$?
echo "flake exit code:  ${flake}"
exit ${flake}
