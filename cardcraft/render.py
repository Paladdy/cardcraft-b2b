"""Deterministic copy with exact source values and measurable output contracts."""
import hashlib
import json
import re
from dataclasses import asdict

from .domain import AppError, pointer, validate_plan
from .prompts import PROMPT_VERSION
from .editorial import compose

NO_DATA = "данных нет"


def shorten_title(name, manufacturer):
    full = name + (" — " + manufacturer if manufacturer else "")
    if len(full) <= 70:
        return full, False
    if len(name) <= 70:
        return name, False
    # Do not silently pretend that a shortened model designation is exact.
    return name[:69].rstrip() + "…", True


def generate(product, planner):
    plan = validate_plan(planner.plan(product), product)
    facts = {f["id"]: f for f in product.facts()}
    excerpts = {f["id"]: f for f in product.excerpts()}
    warnings = []
    missing = []
    for field, value in (("manufacturer", product.manufacturer), ("description", product.description)):
        if not value:
            missing.append({"field": "/" + field, "message": NO_DATA})
    if not product.specs:
        missing.append({"field": "/specs", "message": "Характеристики не предоставлены."})
    labels = list(product.specs) + [x for x in product.required_specs if x not in product.specs]
    for key in labels:
        if not product.specs.get(key):
            missing.append({"field": pointer(key), "message": NO_DATA})
    characteristics = [dict(label=facts[i]["label"], value=facts[i]["value"],
                            source=facts[i]["source"]) for i in plan["spec_order"]]
    characteristics += [{"label": k, "value": NO_DATA, "source": None}
                        for k in labels if not product.specs.get(k)]
    if not characteristics:
        characteristics = [{"label": "Характеристики", "value": NO_DATA, "source": None}]
    title, shortened = shorten_title(product.name, product.manufacturer)
    headline_fact = next((facts[i] for i in plan["spec_order"]
                          if facts[i]["label"].casefold() == "диапазон измерений"
                          and i not in plan["review_ids"]), None)
    if headline_fact:
        candidate = product.name + " — " + headline_fact["value"]
        if len(candidate) <= 70:
            title = candidate
            if product.manufacturer and len(title + " | " + product.manufacturer) <= 70:
                title += " | " + product.manufacturer
    if shortened:
        warnings.append("Название длиннее лимита SEO: заголовок сокращён. Проверьте обозначение модели.")
    if missing:
        warnings.append("Есть пропуски во входных данных: уточните поля из missing_fields.")
    if product.description and not product.excerpts():
        warnings.append("Описание не содержит фрагмента допустимой длины; назначение не извлечено.")
    if product.description.rstrip().endswith(("...", "…")):
        warnings.append("Исходное описание обрывается многоточием: запросите полный текст паспорта.")
    purpose = excerpts.get(plan["purpose_id"])
    if purpose and plan["purpose_id"] in plan["review_ids"]:
        purpose = None
    review = [{"source": (facts.get(i) or excerpts[i])["source"],
               "text": (facts[i]["label"] + ": " + facts[i]["value"]) if i in facts else excerpts[i]["text"],
               "message": "Модель отметила фрагмент для проверки. Сверьте с первоисточником."}
              for i in plan["review_ids"]]
    if review:
        warnings.append("Модель обнаружила возможное противоречие или подозрительный фрагмент; нужна проверка.")
    ordered = [facts[i] for i in plan["spec_order"] if i not in plan["review_ids"]]
    description, references, commercial, editorial = compose(
        product, ordered, purpose, missing, plan["angle"])
    if not 800 <= len(description) <= 1200:
        raise AppError("render_failed", "Не удалось соблюсти длину SEO-описания без обрезки данных.", 422)
    evidence = [{"field": "seo_title", "source": "/name", "text": product.name}]
    if product.manufacturer and product.manufacturer in title:
        evidence.append({"field": "seo_title", "source": "/manufacturer", "text": product.manufacturer})
    if headline_fact and headline_fact["value"] in title:
        evidence.append({"field": "seo_title", "source": headline_fact["source"], "text": headline_fact["value"]})
    evidence.extend({"field": "seo_description", **r} for r in references)
    queries = [product.name, f"{product.name} характеристики", f"{product.name} купить"]
    if product.manufacturer and product.manufacturer.casefold() not in product.name.casefold():
        queries.append(f"{product.name} {product.manufacturer}")
    if headline_fact:
        queries.append(product.name + " " + headline_fact["value"])
    queries = list(dict.fromkeys(queries))
    if editorial["general_paragraphs"] >= 2:
        warnings.append("Мало предметных данных: часть SEO-текста посвящена вопросам подбора. Дополните паспорт перед публикацией.")
    if not purpose:
        warnings.append("Назначение не подтверждено выбранным фрагментом; уточните его для commercial-блока.")
    if planner.mode == "demo":
        warnings.append("Демонстрационный режим: реальный LLM API не вызывался.")
    fingerprint = hashlib.sha256(json.dumps(asdict(product), ensure_ascii=False,
                                            sort_keys=True).encode()).hexdigest()
    return {
        "seo_title": title, "seo_description": description,
        "characteristics": characteristics, "search_queries": queries,
        "commercial": commercial, "missing_fields": missing, "review_items": review,
        "warnings": warnings, "evidence": evidence,
        "quality": {"status": "needs_review", "title_chars": len(title),
                    "description_chars": len(description), "query_count": len(queries),
                    "length_checks_passed": len(title) <= 70 and 800 <= len(description) <= 1200},
        "meta": {"mode": planner.mode, "model": planner.model,
                 "prompt_version": getattr(planner, "prompt_version", PROMPT_VERSION), "source_sha256": fingerprint,
                 "editorial": editorial,
                 "editorial_plan": plan},
    }


def escape(text):
    # Export source text as text, not executable HTML or active Markdown links/images.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", text).replace("\n", " ")


def markdown(card):
    q = card["quality"]
    lines = ["# " + escape(card["seo_title"]), "",
             f"Черновик · {card['meta']['mode']} · требуется проверка редактора", "",
             f"SEO: заголовок {q['title_chars']}/70; описание {q['description_chars']}/800–1200 символов.",
             "", "## SEO-описание", ""]
    lines.extend(escape(p) + "\n" for p in card["seo_description"].split("\n\n"))
    lines.extend(["## Характеристики", ""])
    lines.extend(f"- **{escape(x['label'])}:** {escape(x['value'])}" for x in card["characteristics"])
    lines.extend(["", "## Поисковые запросы", ""])
    lines.extend("- " + escape(x) for x in card["search_queries"])
    lines.extend(["", "## Для менеджера", ""])
    lines.extend(escape(card["commercial"][k]) + "\n" for k in ("audience", "task", "next_step"))
    lines.extend(["**На что опереться при подборе**", ""])
    lines.extend(f"- {escape(x['label'])}: {escape(x['value'])}" for x in card["commercial"]["selection_basis"])
    lines.extend(["", "**Вопросы заказчику**", ""])
    lines.extend("- " + escape(x) for x in card["commercial"]["questions"])
    lines.extend(["", "## Перед публикацией", ""])
    lines.extend("- " + escape(x) for x in card["warnings"])
    lines.extend("- " + escape(x["field"] + ": " + x["message"]) for x in card["missing_fields"])
    lines.extend("- Проверить: " + escape(x["text"]) for x in card["review_items"])
    lines.extend(["", "## Источники технических значений", ""])
    lines.extend("- " + escape(x["label"] + ": " + (x["source"] or "данных нет"))
                 for x in card["characteristics"])
    return "\n".join(lines) + "\n"
