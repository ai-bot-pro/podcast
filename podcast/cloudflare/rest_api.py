import os
import json
import logging
import http.client
from typing import List

import typer
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(override=True)

app = typer.Typer()

_D1_ENV_KEYS = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_KEY")


def has_d1_env() -> bool:
    """True when Cloudflare D1 environment variables are configured."""
    return all(os.getenv(k) for k in _D1_ENV_KEYS)


def _missing_d1_keys(db_id: str = "") -> list[str]:
    missing = [k for k in _D1_ENV_KEYS if not os.getenv(k)]
    if not db_id:
        missing.append("PODCAST_D1_DB_ID (or db_id argument)")
    return missing


def _skip_result(reason: str) -> dict:
    return {"success": False, "skipped": True, "errors": [{"message": reason}], "result": []}


@app.command("d1_table_query")
def d1_table_query(db_id: str, sql: str, sql_params: List[str] = []) -> dict:
    """
    https://developers.cloudflare.com/api/operations/cloudflare-d1-query-database
    """
    if not has_d1_env() or not db_id:
        reason = f"D1 not configured (missing {', '.join(_missing_d1_keys(db_id))}); skipping query"
        logging.warning(reason)
        return _skip_result(reason)
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    api_key = os.getenv("CLOUDFLARE_API_KEY")

    payload = {
        "params": sql_params,
        "sql": sql,
    }
    body = json.dumps(payload)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    conn = http.client.HTTPSConnection("api.cloudflare.com")
    conn.request(
        "POST",
        f"/client/v4/accounts/{account_id}/d1/database/{db_id}/query",
        body,
        headers,
    )
    res = conn.getresponse()
    data = res.read().decode("utf-8")
    json_data = json.loads(data)
    logging.debug(f"body:{body}, db_id:{db_id}, query res:{json_data}")
    return json_data


@app.command("d1_db")
def d1_db(db_id: str) -> dict:
    """
    https://developers.cloudflare.com/api/operations/cloudflare-d1-get-database
    """
    if not has_d1_env() or not db_id:
        reason = f"D1 not configured (missing {', '.join(_missing_d1_keys(db_id))}); skipping query"
        logging.warning(reason)
        return _skip_result(reason)
    account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
    api_key = os.getenv("CLOUDFLARE_API_KEY")

    conn = http.client.HTTPSConnection("api.cloudflare.com")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    conn.request(
        "GET",
        f"/client/v4/accounts/{account_id}/d1/database/{db_id}",
        headers=headers,
    )

    res = conn.getresponse()
    data = res.read()

    data = res.read().decode("utf-8")
    json_data = json.loads(data)
    logging.info(f"get db_id:{db_id}, query res:{json_data}")
    return json_data


r"""
python -m podcast.cloudflare.rest_api d1_db <DB_ID>

python -m podcast.cloudflare.rest_api d1_table_query <DB_ID> \
    "select * from podcast limit 1"
"""
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(funcName)s - %(message)s",
        handlers=[logging.StreamHandler()],
    )
    app()
