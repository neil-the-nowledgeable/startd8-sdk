"""FastAPI email service — port of email/email_server.rb (Step 3, bucket 3 handler)."""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Request
from openfeature import api
from openfeature.contrib.provider.flagd import FlagdProvider

logger = logging.getLogger("email")
app = FastAPI(title="OTel Demo Email (Python)")

CONFIRMATION_COUNTER = 0


def _init_flags() -> None:
    provider = FlagdProvider(
        host=os.environ.get("FLAGD_HOST", "localhost"),
        port=int(os.environ.get("FLAGD_PORT", "8013")),
    )
    api.set_provider(provider)


@app.on_event("startup")
def startup() -> None:
    logging.basicConfig(level=logging.INFO)
    _init_flags()


@app.post("/send_order_confirmation")
async def send_order_confirmation(request: Request) -> dict[str, str]:
    global CONFIRMATION_COUNTER
    body = await request.json()
    order = body.get("order") or {}
    order_id = order.get("order_id", "")
    email = order.get("email", "")

    synthetic = api.get_client().get_boolean_value("emailSyntheticFailure", default=False)
    if synthetic:
        logger.warning("emailSyntheticFailure flag enabled for order %s", order_id)

    CONFIRMATION_COUNTER += 1
    logger.info(
        "Order confirmation email sent order_id=%s email=%s txn=%s",
        order_id,
        email,
        uuid.uuid4(),
    )
    return {"status": "sent", "order_id": order_id}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("EMAIL_PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
