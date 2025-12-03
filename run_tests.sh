#!/bin/bash
# RAG Pipeline Test Runner
# Usage:
#   ./run_tests.sh              - Run all tests
#   ./run_tests.sh biography    - Run specific test
#   ./run_tests.sh --build      - Rebuild and run tests

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 RAG Pipeline Test Runner${NC}"
echo ""

# Parse arguments
BUILD_FLAG=""
TEST_FILTER=""

for arg in "$@"; do
    case $arg in
        --build)
            BUILD_FLAG="yes"
            ;;
        *)
            TEST_FILTER="$arg"
            ;;
    esac
done

# Check if required services are running
echo -e "${YELLOW}Checking if backend services are running...${NC}"

APP_RUNNING=$(docker ps --filter "name=vault_app" --filter "status=running" -q)
CELERY_RUNNING=$(docker ps --filter "name=vault_celery_worker" --filter "status=running" -q)

if [ -z "$APP_RUNNING" ]; then
    echo -e "${RED}❌ ERROR: vault_app is not running.${NC}"
    echo -e "${YELLOW}Please start the backend services first:${NC}"
    echo -e "${CYAN}  docker-compose up -d${NC}"
    exit 1
fi

if [ -z "$CELERY_RUNNING" ]; then
    echo -e "${RED}❌ ERROR: vault_celery_worker is not running.${NC}"
    echo -e "${YELLOW}Please start the backend services first:${NC}"
    echo -e "${CYAN}  docker-compose up -d${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Backend services are running.${NC}"
echo ""

# Build test container if needed
if [ -n "$BUILD_FLAG" ]; then
    echo -e "${YELLOW}Building test container...${NC}"
    docker-compose -f docker-compose.test.yml build test
fi

# Run tests
echo -e "${GREEN}Running tests...${NC}"
echo ""

if [ -n "$TEST_FILTER" ]; then
    # Run specific test
    docker-compose -f docker-compose.test.yml run --rm test pytest test_rag_pipeline.py -v --tb=short -k "$TEST_FILTER"
else
    # Run all tests
    docker-compose -f docker-compose.test.yml run --rm test
fi

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed.${NC}"
fi

exit $EXIT_CODE
