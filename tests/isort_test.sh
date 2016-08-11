#!/usr/bin/env bash
isort_result=$(isort -rc -w 120 --diff em2 && isort -rc -w 120 --diff tests)
if [[ $isort_result == *"changes"* ]] ; then
    printf "changes:\n $isort_result\n\nisort indicates there's an import order problem\n"
    exit 1
fi
exit 0
