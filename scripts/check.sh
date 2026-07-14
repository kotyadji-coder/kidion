#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-${CHECK_MODE:-task}}"
CHECK_TIMEOUT="${CHECK_TIMEOUT:-600}"
GIT_STATUS_TIMEOUT="${GIT_STATUS_TIMEOUT:-10}"

case "$MODE" in
  quick|task|full)
    ;;
  *)
    echo "Usage: CHECK_MODE=quick|task|full ./scripts/check.sh"
    exit 2
    ;;
esac

run_timed() {
  local title="$1"
  shift
  echo
  echo "== $title =="
  if command -v timeout >/dev/null 2>&1; then
    timeout "$CHECK_TIMEOUT" "$@"
  else
    "$@"
  fi
}

npm_has_script() {
  npm run | grep -qE "^[[:space:]]*$1($|[[:space:]])"
}

python_cmd() {
  if [ -x ./.venv/bin/python ] && ./.venv/bin/python -m pytest --version >/dev/null 2>&1; then
    printf '%s\n' "./.venv/bin/python"
  elif [ -x ./venv/bin/python ] && ./venv/bin/python -m pytest --version >/dev/null 2>&1; then
    printf '%s\n' "./venv/bin/python"
  elif command -v python3 >/dev/null 2>&1 && python3 -m pytest --version >/dev/null 2>&1; then
    printf '%s\n' "python3"
  else
    return 1
  fi
}

echo "== Git status =="
if command -v timeout >/dev/null 2>&1; then
  timeout "$GIT_STATUS_TIMEOUT" git status --short || echo "git status skipped or timed out"
else
  git status --short || true
fi
echo "== Check mode: $MODE =="

if [ -f package.json ]; then
  echo "== Node project checks =="
  if [ "$MODE" = "quick" ]; then
    if npm_has_script "test:quick"; then run_timed "npm test:quick" npm run test:quick; fi
    if npm_has_script "lint:quick"; then run_timed "npm lint:quick" npm run lint:quick; fi
  else
    if npm_has_script "lint"; then run_timed "npm lint" npm run lint; fi
    if npm_has_script "typecheck"; then run_timed "npm typecheck" npm run typecheck; fi
    if npm_has_script "test"; then run_timed "npm test" npm run test; fi
    if [ "$MODE" = "full" ] && npm_has_script "build"; then run_timed "npm build" npm run build; fi
  fi
fi

if [ -f pyproject.toml ] || [ -f pytest.ini ] || [ -d tests ]; then
  echo "== Python project checks =="
  export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}."
  if [ "$MODE" = "quick" ] && [ -z "${PYTEST_TARGETS:-}" ]; then
    echo "No PYTEST_TARGETS set; skipping broad pytest in quick mode"
  elif py=$(python_cmd); then
    if [ "$MODE" = "quick" ]; then
      if [ -n "${PYTEST_TARGETS:-}" ]; then
        run_timed "pytest quick targets" "$py" -m pytest -q -x ${PYTEST_TARGETS}
      fi
    else
      run_timed "pytest" "$py" -m pytest -q
    fi
  else
    echo "pytest not found; skipping Python tests"
  fi
fi

if [ -x ./tools/check.sh ] && [ "$MODE" != "quick" ]; then
  echo "== Project tools/check.sh =="
  run_timed "tools/check.sh" ./tools/check.sh
fi

echo "== Check finished =="
