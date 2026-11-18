"""MCP server exposing a Payments Detective lookup as a tool.

Runs over stdio so any MCP host — Claude Desktop, ``scripts/mcp_agent.py``,
or anything else speaking MCP — can attach to it as a subprocess and decide
when to look up a merchant's live KYC/risk profile instead of always
retrieving from the static SOP knowledge base.
"""

from __future__ import annotations

import os
from pathlib import Path

# Resolve relative paths (.env, etc.) against the repo root regardless of the
# cwd the MCP host launches this process from.
os.chdir(Path(__file__).resolve().parents[2])

import httpx
from mcp.server import MCPServer

from app.config import settings

server = MCPServer(
    name="mychatbot-payments-detective",
    instructions=(
        "Tool for looking up a merchant's KYC/risk profile from the internal "
        "Payments Detective service, for cases that need live account data "
        "rather than static SOP text."
    ),
)


@server.tool()
def get_merchant_kyc_details(account_id: str) -> dict:
    """Fetch a merchant's KYC/risk profile from Payments Detective.

    Use this when the user asks about a specific account's KYC/risk status,
    business details, or review history by account_id.
    """
    if not account_id.strip().isdigit():
        return {"error": {"code": "invalid_account_id", "message": "account_id must be numeric"}}

    if not settings.payments_detective_cookie:
        return {
            "error": {
                "code": "auth_not_configured",
                "message": "PAYMENTS_DETECTIVE_COOKIE is not set in .env",
            }
        }

    headers = {"Cookie": settings.payments_detective_cookie}
    if settings.payments_detective_zcsrf_token:
        headers["x-zcsrf-token"] = settings.payments_detective_zcsrf_token

    try:
        with httpx.Client(
            base_url=settings.payments_detective_base_url,
            timeout=settings.payments_detective_timeout,
            verify=settings.payments_detective_verify_ssl,
        ) as c:
            resp = c.get("/kyc/merchant/details", params={"account_id": account_id}, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        try:
            return e.response.json()
        except ValueError:
            return {
                "error": {
                    "code": "http_error",
                    "status": e.response.status_code,
                    "message": e.response.text[:500],
                }
            }
    except httpx.HTTPError as e:
        return {"error": {"code": "connection_error", "message": str(e)}}


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
