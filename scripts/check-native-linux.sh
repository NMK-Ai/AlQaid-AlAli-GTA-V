#!/usr/bin/env bash
set -euo pipefail
project=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$project/build/linux-tests"
for test in driving_state angle_servo longitudinal_actuator radar road_context; do
  g++ -std=c++17 -O1 -UNDEBUG "$project/native/test_$test.cpp" -o "$project/build/linux-tests/test_$test"
  "$project/build/linux-tests/test_$test"
done
echo 'All five native tests passed with Linux g++.'
