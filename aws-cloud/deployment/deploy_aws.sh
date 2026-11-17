#!/usr/bin/env bash
# End-to-End AWS Cloud Deployment Script (`aws-cloud/deployment/deploy_aws.sh`)
set -euo pipefail

STACK_NAME="${STACK_NAME:-icu-monitor-pro-stack}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo "================================================================="
echo "Deploying ICUGuardian AWS Cloud Stack ($STACK_NAME in $AWS_REGION)"
echo "================================================================="

echo "1. Validating DynamoDB Schema Definitions..."
python3 ../dynamodb/provision_dynamodb.py

if command -v sam >/dev/null 2>&1; then
  echo "2. Building & Deploying AWS SAM Stack..."
  sam build --template-file ../../infrastructure/infrastructure-as-code/template.yaml
  sam deploy --stack-name "$STACK_NAME" --region "$AWS_REGION" --resolve-s3 --capabilities CAPABILITY_IAM
else
  echo "Note: AWS SAM CLI not installed locally. Use 'aws cloudformation deploy' or run the local Cloud Backend Server."
fi
