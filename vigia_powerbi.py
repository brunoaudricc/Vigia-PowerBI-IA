import json
import os
import time

import pandas as pd
import requests
import urllib3

BRIDGE_DIR = os.getenv("BRIDGE_DIR", "./bridge")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
VERIFY_SSL = os.getenv("VERIFY_SSL", "true").lower() == "true"

if not VERIFY_SSL:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

OPENROUTER_MODELS = [
    "nvidia/nemotron-3.5-lightning:free",
    "minimax/minimax-m3.1-flash:free",
    "thinkingmachines/inkling-small:free",
]

MAX_PAYLOAD_CHARS = 80000
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

REQUEST_FILE = os.path.join(BRIDGE_DIR, "requisicao.json")
RESPONSE_FILE = os.path.join(BRIDGE_DIR, "resposta.txt")
OPTIONAL_PARQUET_FILE = os.path.join(BRIDGE_DIR, "base_completa.parquet")


def build_headers():
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://powerbi.microsoft.com",
        "X-Title": "PowerBI-AI-Analyst",
    }


def prepare_hybrid_dataset(records, max_chars=MAX_PAYLOAD_CHARS):
    """Gera estatísticas numéricas, contagens por categoria e uma amostra em CSV."""
    if os.path.exists(OPTIONAL_PARQUET_FILE):
        print("Reading full dataset from local parquet file.")
        df = pd.read_parquet(OPTIONAL_PARQUET_FILE)
    else:
        if not records or not isinstance(records, list):
            return "Empty dataset."
        df = pd.DataFrame(records)

    df = df[[c for c in df.columns if not str(c).startswith("__PowerApps")]]

    if df.empty:
        return "Dataset is empty after cleanup."

    sections = [
        f"Total records in dataset: {len(df)} rows",
        f"Table columns: {', '.join(map(str, df.columns))}\n",
    ]

    numeric_cols = df.select_dtypes(include=["number"]).columns
    if len(numeric_cols) > 0:
        sections.append("Numeric statistics (100% of dataset):")
        sections.append(
            df[numeric_cols].agg(["count", "sum", "mean", "min", "max"]).round(2).to_string()
        )
        sections.append("")

    text_cols = df.select_dtypes(include=["object", "string", "category"]).columns
    if len(text_cols) > 0:
        sections.append("Exact value counts per column (100% of dataset):")
        for col in text_cols:
            clean_series = df[col].dropna().astype(str)
            # Evita agrupar colunas de texto livre com alta cardinalidade
            if clean_series.nunique() < (len(df) * 0.85):
                value_counts = clean_series.value_counts()
                if len(value_counts) <= 60:
                    sections.append(
                        f"- {col} ({len(value_counts)} items): "
                        f"{json.dumps(value_counts.to_dict(), ensure_ascii=False)}"
                    )
                else:
                    top_items = value_counts.head(25).to_dict()
                    bottom_items = value_counts.tail(25).to_dict()
                    sections.append(
                        f"- {col} (top 25 most frequent): {json.dumps(top_items, ensure_ascii=False)}"
                    )
                    sections.append(
                        f"- {col} (bottom 25 least frequent): {json.dumps(bottom_items, ensure_ascii=False)}"
                    )
        sections.append("")

    sections.append("Table records in CSV:")
    df_csv = df.copy()
    for col in df_csv.select_dtypes(include=["object", "string"]).columns:
        df_csv[col] = df_csv[col].astype(str).str.replace("\n", " ").str.slice(0, 100)

    sections.append(df_csv.to_csv(index=False))
    payload_text = "\n".join(sections)

    if len(payload_text) > max_chars:
        payload_text = (
            payload_text[:max_chars]
            + "\n... [CSV table truncated to stay within payload limit]"
        )

    return payload_text


def call_openrouter(dataset_summary, question):
    """Envia o resumo da base e a pergunta para o OpenRouter e retorna texto."""
    if not OPENROUTER_API_KEY:
        return "Error: OPENROUTER_API_KEY environment variable is not set."

    payload = {
        "models": OPENROUTER_MODELS,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a data analyst integrated with Power BI. "
                    "You received numeric statistics, exact category counts for 100% "
                    "of the filtered dataset, and CSV records. "
                    "Answer in the same language as the question, directly and concisely, "
                    "using the exact numbers provided."
                ),
            },
            {
                "role": "user",
                "content": f"{dataset_summary}\n\nQuestion: {question}",
            },
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }

    response = requests.post(
        OPENROUTER_URL,
        headers=build_headers(),
        json=payload,
        timeout=60,
        verify=VERIFY_SSL,
    )

    if response.status_code != 200:
        return f"OpenRouter error ({response.status_code}): {response.text}"

    data = response.json()
    model_used = data.get("model", "OpenRouter")
    message = data.get("choices", [{}])[0].get("message", {})

    ai_text = message.get("content")
    if not ai_text:
        ai_text = message.get("reasoning") or message.get("reasoning_content")

    if ai_text and str(ai_text).strip():
        print(f"Answered by model: {model_used}")
        return str(ai_text).strip()

    return f"Model {model_used} returned an empty response. Please try again."


def watch_folder():
    if not OPENROUTER_API_KEY:
        print("Warning: set OPENROUTER_API_KEY before sending questions.")

    print(f"Watching folder: {os.path.abspath(BRIDGE_DIR)}")

    last_modified = 0
    if os.path.exists(REQUEST_FILE):
        last_modified = os.path.getmtime(REQUEST_FILE)

    while True:
        try:
            if os.path.exists(REQUEST_FILE):
                current_modified = os.path.getmtime(REQUEST_FILE)

                if current_modified != last_modified:
                    last_modified = current_modified
                    print("\nNew question detected.")

                    # Aguarda o término da escrita pelo cliente de sincronização
                    time.sleep(0.3)

                    with open(REQUEST_FILE, "r", encoding="utf-8") as f:
                        content = json.load(f)

                    question = content.get("pergunta", "")
                    records = content.get("dados", [])

                    print(f"Question: {question}")
                    print(f"Rows received: {len(records)}")

                    dataset_summary = prepare_hybrid_dataset(records)
                    ai_text = call_openrouter(dataset_summary, question)

                    with open(RESPONSE_FILE, "w", encoding="utf-8") as f:
                        f.write(str(ai_text))

                    print("Response written to resposta.txt.")

        except Exception as exc:
            print(f"Error processing request: {exc}")

        time.sleep(0.5)


if __name__ == "__main__":
    watch_folder()
