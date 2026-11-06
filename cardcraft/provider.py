"""Small injectable REST client, with bounded retries and no secret-bearing logs."""
import json
from http.client import HTTPException
import os
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .domain import AppError, parse_json, validate_plan
from .prompts import SCHEMA, messages


class OpenAIPlanner:
    mode = "live"

    def __init__(self, api_key=None, model=None, transport=urlopen, sleep=time.sleep):
        self.key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        self.transport, self.sleep = transport, sleep
        if not self.key.strip():
            raise AppError("missing_api_key", "Задайте OPENAI_API_KEY или явно включите --demo.", 503)

    def plan(self, product):
        body = {"model": self.model, "messages": messages(product),
                "max_completion_tokens": 2000,
                "response_format": {"type": "json_schema", "json_schema": {
                    "name": "product_editorial_plan", "strict": True, "schema": SCHEMA}}}
        request = Request("https://api.openai.com/v1/chat/completions",
                          data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json"}, method="POST")
        for attempt in range(3):
            try:
                with self.transport(request, timeout=30) as response:
                    raw = response.read(65537)
                break
            except HTTPError as error:
                status = error.code
                error.close()
                if status in (429, 500, 502, 503, 504) and attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                if status in (401, 403):
                    raise AppError("api_auth", "LLM API отклонил доступ: проверьте ключ и права модели.", 502) from None
                raise AppError("api_unavailable", f"LLM API недоступен (HTTP {status}). Повторите позже.", 503) from None
            except (URLError, TimeoutError, socket.timeout, OSError, HTTPException):
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise AppError("api_timeout", "Не удалось связаться с LLM API после трёх попыток.", 503) from None
        try:
            payload = parse_json(raw)
            choice = payload["choices"][0]
            if choice["message"].get("refusal"):
                raise AppError("model_refusal", "Модель отказалась обрабатывать эти данные.", 422)
            if choice.get("finish_reason") != "stop":
                raise AppError("incomplete_model_output", "Ответ модели не завершён. Карточка не создана.", 502)
            plan = parse_json(choice["message"]["content"].encode("utf-8"))
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            raise AppError("invalid_model_output", "LLM API вернул неожиданный формат ответа.", 502) from None
        except AppError as error:
            if error.code in ("invalid_json", "input_too_large"):
                raise AppError("invalid_model_output", "LLM API вернул некорректный JSON.", 502) from None
            raise
        return validate_plan(plan, product)


class DemoPlanner:
    """Explicit offline fixture, never a fallback after a failed real API request."""
    mode = "demo"
    model = "offline-fixture"

    def plan(self, product):
        purpose = next((x["id"] for x in product.excerpts()
                        if re.match(r"Прибор предназначен для ", x["text"])), None)
        return {"spec_order": [f["id"] for f in product.facts()], "purpose_id": purpose,
                "review_ids": [], "angle": "selection"}
