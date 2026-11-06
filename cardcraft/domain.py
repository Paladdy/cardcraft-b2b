"""Input validation and the trust boundary for model-produced plans."""
from dataclasses import dataclass
import json
import re

MAX_INPUT_BYTES = 64 * 1024


class AppError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code, self.status = code, status


def parse_json(raw):
    if len(raw) > MAX_INPUT_BYTES:
        raise AppError("input_too_large", "JSON должен быть не больше 64 КБ.", 413)
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise AppError("invalid_json", f"Повторяющийся ключ JSON: {key}", 400)
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise AppError("invalid_json", "Некорректный JSON: проверьте кодировку UTF-8, кавычки и запятые.", 400) from None


def clean(value, field, limit):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AppError("invalid_input", f"{field}: ожидается строка или null.")
    value = value.strip()
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise AppError("invalid_input", f"{field}: управляющие символы недопустимы.")
    if len(value) > limit:
        raise AppError("invalid_input", f"{field}: максимум {limit} символов.")
    return value


def pointer(key):
    return "/specs/" + key.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True)
class Product:
    name: str
    manufacturer: str
    specs: dict
    description: str
    required_specs: tuple

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise AppError("invalid_input", "Ожидается один JSON-объект товара.")
        allowed = {"name", "manufacturer", "specs", "description", "required_specs"}
        if set(data) - allowed:
            raise AppError("invalid_input", "Неизвестные поля: " + ", ".join(sorted(set(data) - allowed)))
        name = clean(data.get("name"), "name", 240)
        if not name:
            raise AppError("missing_name", "Укажите name: без названия нельзя сформировать карточку.")
        specs = data.get("specs", {})
        if specs is None:
            specs = {}
        if not isinstance(specs, dict) or len(specs) > 40:
            raise AppError("invalid_input", "specs: ожидается объект, не более 40 характеристик.")
        normalized = {}
        for key, value in specs.items():
            label = clean(key, "specs.key", 100)
            if not label or label in normalized:
                raise AppError("invalid_input", "Названия характеристик должны быть непустыми и уникальными.")
            # Keep original keys so JSON pointers resolve against the input.
            if key != label:
                raise AppError("invalid_input", "Уберите пробелы по краям названий характеристик.")
            normalized[key] = clean(value, f"specs.{key}", 300)
        required = data.get("required_specs", [])
        if not isinstance(required, list) or len(required) > 40:
            raise AppError("invalid_input", "required_specs: ожидается список до 40 названий.")
        required = tuple(clean(x, "required_specs", 100) for x in required)
        if any(not x for x in required) or len(set(required)) != len(required):
            raise AppError("invalid_input", "required_specs: названия должны быть непустыми и уникальными.")
        return cls(name, clean(data.get("manufacturer"), "manufacturer", 160), normalized,
                   clean(data.get("description"), "description", 12000), required)

    def facts(self):
        return [{"id": f"s{i}", "label": k, "value": v, "source": pointer(k)}
                for i, (k, v) in enumerate(self.specs.items()) if v]

    def excerpts(self):
        # Decimal dots are not sentence separators. No arbitrary substring slicing.
        chunks = re.split(r"(?<=[.!?])\s+|[\r\n]+", self.description)
        return [{"id": f"d{i}", "text": s.strip(), "source": "/description"}
                for i, s in enumerate(chunks) if 15 <= len(s.strip()) <= 320]


def validate_plan(plan, product):
    """Only opaque source IDs and fixed enums cross from the LLM into rendering."""
    keys = {"spec_order", "purpose_id", "review_ids", "angle"}
    if not isinstance(plan, dict) or set(plan) != keys:
        raise AppError("invalid_model_output", "Модель вернула неверную структуру плана.", 502)
    ids = [x["id"] for x in product.facts()]
    order = plan["spec_order"]
    if (not isinstance(order, list) or any(not isinstance(x, str) for x in order)
            or len(order) != len(ids) or set(order) != set(ids)):
        raise AppError("invalid_model_output", "Модель пропустила, повторила или добавила характеристику.", 502)
    excerpts = {x["id"] for x in product.excerpts()}
    purpose = plan["purpose_id"]
    if purpose is not None and (not isinstance(purpose, str) or purpose not in excerpts):
        raise AppError("invalid_model_output", "Модель сослалась на отсутствующий фрагмент описания.", 502)
    review = plan["review_ids"]
    if (not isinstance(review, list) or any(not isinstance(x, str) for x in review)
            or len(set(review)) != len(review) or not set(review) <= set(ids) | excerpts):
        raise AppError("invalid_model_output", "Модель вернула неверные ссылки для проверки.", 502)
    if plan["angle"] not in ("selection", "procurement", "replacement"):
        raise AppError("invalid_model_output", "Неизвестный сценарий карточки.", 502)
    return plan
