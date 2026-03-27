#!/bin/bash
# ============================================================
#  Dukon API — Newman Test Runner
#  Требования: node >= 18, newman, newman-reporter-htmlextra
#  Установка:
#    npm install -g newman newman-reporter-htmlextra
# ============================================================

set -e

COLLECTION="dukon_postman_collection_v2.json"
BASE_URL="${BASE_URL:-http://localhost:8000/api/v1}"
ROOT_URL="${ROOT_URL:-http://localhost:8000}"
REPORT_DIR="./reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$REPORT_DIR"

echo "======================================================"
echo "  Dukon API Test Suite"
echo "  Base URL : $BASE_URL"
echo "  Root URL : $ROOT_URL"
echo "  Time     : $(date)"
echo "======================================================"

# ── Функция запуска конкретной папки ──────────────────────
run_folder() {
  local FOLDER="$1"
  local LABEL="$2"
  echo ""
  echo ">>> Running: $LABEL"
  newman run "$COLLECTION" \
    --folder "$FOLDER" \
    --env-var "base_url=$BASE_URL" \
    --env-var "root_url=$ROOT_URL" \
    --timeout-request 10000 \
    --reporters cli,htmlextra \
    --reporter-htmlextra-export "$REPORT_DIR/${TIMESTAMP}_${LABEL// /_}.html" \
    --reporter-cli-no-assertions \
    --bail \
    2>&1 || true
}

# ── Функция для Race Condition (много итераций) ───────────
run_race_condition() {
  local FOLDER="$1"
  local ITERATIONS="${2:-10}"
  echo ""
  echo ">>> Race Condition: $FOLDER ($ITERATIONS iterations, delay=0)"
  newman run "$COLLECTION" \
    --folder "$FOLDER" \
    --env-var "base_url=$BASE_URL" \
    --env-var "root_url=$ROOT_URL" \
    --iteration-count "$ITERATIONS" \
    --delay-request 0 \
    --timeout-request 15000 \
    --reporters cli,htmlextra \
    --reporter-htmlextra-export "$REPORT_DIR/${TIMESTAMP}_race_${FOLDER// /_}.html" \
    2>&1 || true
}

# ══════════════════════════════════════════════════════════
#  РЕЖИМ ЗАПУСКА
# ══════════════════════════════════════════════════════════
MODE="${1:-full}"

case "$MODE" in

  health)
    echo "Mode: Health check only"
    run_folder "🏥 Health" "health"
    ;;

  auth)
    echo "Mode: Auth + Profile flow"
    run_folder "🔐 Auth — Accounts" "auth"
    run_folder "👤 Profile" "profile"
    ;;

  smoke)
    echo "Mode: Smoke test (happy path only)"
    # Использует папку 🔑 Smoke Login вместо полного Auth flow
    # Prerequisite: python manage.py create_smoke_data
    newman run "$COLLECTION" \
      --env-var "base_url=$BASE_URL" \
      --env-var "root_url=$ROOT_URL" \
      --folder "🏥 Health" \
      --folder "🔑 Smoke Login" \
      --folder "🏪 Stores" \
      --folder "📦 Products" \
      --folder "🛒 Orders" \
      --folder "👷 Employees" \
      --timeout-request 10000 \
      --reporters cli,htmlextra \
      --reporter-htmlextra-export "$REPORT_DIR/${TIMESTAMP}_smoke.html"
    ;;

  edge)
    echo "Mode: Edge cases only"
    run_folder "🧪 Edge Cases" "edge_cases"
    ;;

  security)
    echo "Mode: Security tests only"
    run_folder "🔒 Security Tests" "security"
    ;;

  race)
    echo "Mode: Race condition tests"
    echo ""
    echo "⚠️  Убедись что в БД ProductModel.quantity = 1 перед запуском RC-1"
    echo "⚠️  Убедись что промокод PROMO2025 не использован перед RC-3"
    echo ""
    run_race_condition "⚡ Race Condition Tests" 10
    ;;

  full)
    echo "Mode: Full test suite"
    echo ""

    # 1. Health
    run_folder "🏥 Health" "01_health"

    # 2. Smoke login (saved tokens propagate to all subsequent folders)
    run_folder "🔑 Smoke Login" "02_smoke_login"

    # 3. Profile (uses token from smoke login)
    run_folder "👤 Profile" "03_profile"

    # 4. Core entities
    run_folder "🏪 Stores" "04_stores"
    run_folder "📦 Products" "05_products"
    run_folder "🛒 Orders" "06_orders"
    run_folder "👷 Employees" "07_employees"

    # 5. Notifications & misc
    run_folder "🔔 Notifications" "08_notifications"
    run_folder "🌍 CountryAPI" "09_countryapi"

    # 6. Edge cases
    run_folder "🧪 Edge Cases" "10_edge_cases"

    # 7. Security
    run_folder "🔒 Security Tests" "11_security"

    # 8. Race conditions (last, separate iterations)
    echo ""
    echo "⚠️  Race condition tests — run manually with: $0 race"
    echo "    (требует подготовки данных в БД)"
    ;;

  *)
    echo "Использование: $0 [health|auth|smoke|edge|security|race|full]"
    echo ""
    echo "  health   — только health-check endpoints"
    echo "  auth     — auth + profile flow (требует реального WhatsApp)"
    echo "  smoke    — happy path (smoke login→stores→products→orders)"
    echo "             Prerequisite: python manage.py create_smoke_data"
    echo "  edge     — все edge cases"
    echo "  security — security тесты (IDOR, brute force, enumeration)"
    echo "  race     — race condition тесты (10 параллельных итераций)"
    echo "  full     — всё (кроме race, его запускай отдельно)"
    exit 1
    ;;
esac

echo ""
echo "======================================================"
echo "  Отчёты сохранены в: $REPORT_DIR/"
echo "  Открой HTML отчёт в браузере для деталей"
echo "======================================================"
