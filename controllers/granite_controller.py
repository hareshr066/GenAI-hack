import os
import requests
from fastapi import APIRouter, Query
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

HF_API_KEY = os.getenv("HF_API_KEY")
GRANITE_MODEL = os.getenv("GRANITE_MODEL", "ibm-granite/granite-13b-instruct")
HF_API_URL = f"https://api-inference.huggingface.co/models/{GRANITE_MODEL}"

headers = {"Authorization": f"Bearer {HF_API_KEY}"}

def query_granite(prompt: str, max_new_tokens=200):
    payload = {
        "inputs": prompt,
        "parameters": {"max_new_tokens": max_new_tokens}
    }
    response = requests.post(HF_API_URL, headers=headers, json=payload)
    response.raise_for_status()
    output = response.json()

    if isinstance(output, list) and "generated_text" in output[0]:
        return output[0]["generated_text"]
    return str(output)

@router.post("/granite")
def granite_generate(prompt: str = Query(..., description="Prompt for Granite Model")):
    try:
        result = query_granite(prompt)
        return {"result": result}
    except Exception as e:
        return {"error": str(e)}
