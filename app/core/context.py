# app/core/context.py
from contextvars import ContextVar
import uuid

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

def get_request_id() -> str:
    ctx_val = request_id_ctx.get()
    return ctx_val if ctx_val else str(uuid.uuid4())