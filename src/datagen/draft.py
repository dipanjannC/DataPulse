from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
 
import boto3
import botocore

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
 
MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
REGION = os.getenv("AWS_REGION", "us-east-1")
 
 
class BedrockClient:
    def __init__(self, model_id: str = MODEL_ID, region_name: str = REGION) -> None:
        self.model_id = model_id
        self.client = boto3.client("bedrock-runtime", region_name=region_name)
 
    def invoke(self, body: Any, model_id: Optional[str] = None) -> Dict[str, Any]:
        """Invoke the model with a raw body (dict or str)."""
        if isinstance(body, (dict, list)):
            body_bytes = json.dumps(body).encode()
        elif isinstance(body, str):
            body_bytes = body.encode()
        else:
            body_bytes = bytes(body)
 
        try:
            response = self.client.invoke_model(
                modelId=model_id or self.model_id,
                contentType="application/json",
                accept="application/json",
                body=body_bytes,
            )
            raw = response["body"].read()
            text = raw.decode("utf-8", errors="ignore")
            try:
                return json.loads(text)
            except Exception:
                return {"raw": text}
            

        except botocore.exceptions.BotoCoreError:
            logger.exception("invoke_model failed")
            raise
 
    def text(self, prompt: str, max_tokens: int = 1024, temperature: float = 0.0) -> Dict[str, Any]:
        """Send a simple text prompt using the Messages API format."""
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        return self.invoke(payload)
 
 
if __name__ == "__main__":
    logging.basicConfig(level="INFO")
    client = BedrockClient()
    resp = client.text("Write a friendly greeting.")
    print(resp)