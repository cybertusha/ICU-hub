#!/usr/bin/env bash
# ==============================================================================
# ICUGuardian — ONE-TIME AWS Cloud & DynamoDB Provisioning Script
# Zero-dependency pure-Python AWS SigV4 provisioner (no awscli or boto3 needed).
# ==============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================================================="
echo "  ICUGuardian — One-Time AWS Cloud & DynamoDB Setup (Option B)"
echo "=========================================================================="

read -rp "Enter your AWS Access Key ID: " INPUT_KEY_ID
read -rsp "Enter your AWS Secret Access Key: " INPUT_SECRET_KEY
echo ""
read -rp "Enter AWS Region [ap-south-1]: " INPUT_REGION
AWS_REGION="${INPUT_REGION:-ap-south-1}"

python3 "$ROOT_DIR/aws-cloud/aws_sigv4.py" "$INPUT_KEY_ID" "$INPUT_SECRET_KEY" "$AWS_REGION"
