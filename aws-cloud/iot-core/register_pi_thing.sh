#!/usr/bin/env bash
# AWS IoT Core Provisioning Script for Raspberry Pi Gateway
# Registers IoT Thing, generates X.509 device certificates, attaches IoT policy,
# and downloads Amazon Root CA 1 into raspberry-pi-gateway/certs/.

set -euo pipefail

THING_NAME="${1:-ICU-PI-001}"
POLICY_NAME="ICU_GatewayDevicePolicy"
CERTS_OUT="../../raspberry-pi-gateway/certs"

mkdir -p "$CERTS_OUT"

echo "1. Creating AWS IoT Thing: $THING_NAME"
aws iot create-thing --thing-name "$THING_NAME" --attribute-payload '{"attributes":{"role":"icu-gateway","bed":"ICU-01"}}'

echo "2. Generating X.509 Certificate and Private Key..."
CERT_ARN=$(aws iot create-keys-and-certificate \
  --set-as-active \
  --certificate-pem-outfile "$CERTS_OUT/device.pem.crt" \
  --public-key-outfile "$CERTS_OUT/public.pem.key" \
  --private-key-outfile "$CERTS_OUT/private.pem.key" \
  --query 'certificateArn' --output text)

echo "3. Downloading Amazon Root CA 1..."
curl -sS https://www.amazontrust.com/repository/AmazonRootCA1.pem -o "$CERTS_OUT/AmazonRootCA1.pem"

echo "4. Creating & Attaching IoT Policy ($POLICY_NAME)..."
aws iot create-policy --policy-name "$POLICY_NAME" --policy-document file://iot_policy.json || true
aws iot attach-policy --policy-name "$POLICY_NAME" --target "$CERT_ARN"
aws iot attach-thing-principal --thing-name "$THING_NAME" --principal "$CERT_ARN"

IOT_ENDPOINT=$(aws iot describe-endpoint --endpoint-type iot:Data-ATS --query 'endpointAddress' --output text)
echo "================================================================="
echo "AWS IoT Core Thing '$THING_NAME' configured successfully!"
echo "Certificates saved to: $CERTS_OUT"
echo "AWS_IOT_ENDPOINT=$IOT_ENDPOINT"
echo "================================================================="
