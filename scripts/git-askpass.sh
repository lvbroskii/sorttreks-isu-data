#!/usr/bin/env bash
# Token stays in the step environment; no credential URL, stored token or shell tracing.
case "$1" in
  *Username*) printf '%s\n' x-access-token ;;
  *Password*) printf '%s\n' "$GH_TOKEN" ;;
  *) exit 1 ;;
esac
