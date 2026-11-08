#!/usr/bin/env bash
set -euo pipefail

scan_roots=(.env.example apps packages services pyproject.toml package.json)
existing_roots=()
for scan_root in "${scan_roots[@]}"; do
  if [[ -e "$scan_root" ]]; then
    existing_roots+=("$scan_root")
  fi
done

if ((${#existing_roots[@]} == 0)); then
  echo "No dependency or environment manifests to scan."
  exit 0
fi

forbidden_pattern='OPENAI_API_KEY|GEMINI_API_KEY|ANTHROPIC_API_KEY|DEEP(L|L_API)_KEY|STRIPE_SECRET|api\.openai\.com|generativelanguage\.googleapis\.com|api\.deepl\.com'

if rg -n -i --hidden \
  -g '!node_modules/**' \
  -g '!dist/**' \
  -g '!build/**' \
  -g '!*.md' \
  "$forbidden_pattern" "${existing_roots[@]}"; then
  echo "Paid or metered service marker found. Review docs/free-only-policy.md."
  exit 1
fi

echo "Free-only policy scan passed."
