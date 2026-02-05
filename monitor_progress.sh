#!/bin/bash

echo "===== Mining & Publishing Progress Monitor ====="
echo "Current time: $(date)"
echo ""

# Check published story count
PUBLISHED_COUNT=$(ls -la /home/computeruse/claude-3-7-news-monitor/docs/20260205/ | wc -l)
echo "Published stories: $PUBLISHED_COUNT"
echo ""

# Check mined items count by year
echo "Mined stories by year:"
find /home/computeruse/logs/multi_instance_20260205_120414/ -name "federal_register_results_*.txt" -exec wc -l {} \; | sort

# Check running processes
echo ""
echo "Running mining processes:"
ps aux | grep "rate_limited_register_miner" | grep -v grep | wc -l

echo ""
echo "Running batch publishers:"
ps aux | grep "systematic_batch_publisher" | grep -v grep | wc -l

# Check active batch publishers
echo ""
echo "Active batch publishers:"
ps aux | grep "systematic_batch_publisher" | grep -v grep

echo ""
echo "Recent errors:"
grep "ERROR" /home/computeruse/logs/multi_instance_20260205_120414/mining_*.log | tail -5
