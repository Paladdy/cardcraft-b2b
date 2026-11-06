"""Source-specific editorial copy. Guidance is phrased as questions, never specs."""
import re

COPY_VERSION = "source-editorial-v2"
# Explanations describe what to check, not unprovided properties of the instrument.
GUIDANCE = {
    "диапазон измерений": (
        "Сопоставьте этот диапазон с границами измеряемой величины в вашей задаче. Условия работы за его пределами в исходных данных не подтверждены.",
        "Какой диапазон нужен в вашей точке измерения?"),
    "класс точности": (
        "При выборе ориентируйтесь на требование к точности в техническом задании. Допустимую погрешность для конкретных условий следует сверить с паспортом; здесь она не пересчитывается.",
        "Соответствует ли указанный класс точности требованиям вашей задачи?"),
    "присоединение": (
        "Перед заказом сверьте обозначение присоединения с ответной частью на объекте. Одного совпадения названия прибора недостаточно для подтверждения монтажа.",
        "Какое присоединение предусмотрено на объекте?"),
    "диаметр корпуса": (
        "Сравните этот размер с доступным местом установки. Остальные габариты и требования к размещению нужно проверить по монтажному чертежу.",
        "Достаточно ли места для корпуса и подключения прибора?"),
    "питание": (
        "Сверьте указанное питание с доступным источником на месте установки. Потребляемый ток и схему подключения необходимо уточнить отдельно, если они не приведены в документации.",
        "Какой источник питания доступен на месте установки?"),
    "интерфейс": (
        "При интеграции сравните обозначение интерфейса с требованиями принимающего оборудования. Настройки обмена и совместимость необходимо подтвердить отдельно.",
        "С каким оборудованием и по какому интерфейсу должен работать прибор?"),
    "тип корпуса": (
        "Сопоставьте указанное исполнение с требованиями к размещению. Защитные свойства корпуса следует подтверждать отдельными данными, а не выводить из его названия.",
        "Какие требования к исполнению корпуса заданы для места установки?"),
}


def key(label):
    return label.casefold().strip()


def audience(purpose):
    if purpose:
        match = re.fullmatch(r"Прибор предназначен для (.+?)[.!…]*", purpose["text"], re.DOTALL)
        if match:
            task = match.group(1).rstrip(".!…")
            return f"Для специалистов, подбирающих прибор для {task}. Применимость к конкретному объекту требует проверки."
    return "Конкретная аудитория не определена: уточните назначение и место применения прибора."


def compose(product, ordered, purpose, missing, angle):
    """Fit whole sourced paragraphs; never cut a technical value to meet SEO length."""
    blocks, refs = [], []
    def add(text, sources=()):
        if len("\n\n".join(blocks + [text])) <= 1200:
            blocks.append(text)
            refs.extend(sources)
            return True
        return False

    intro = product.name + ". " + (f"Производитель — {product.manufacturer}." if product.manufacturer
                                       else "Производитель: данных нет.")
    intro_refs = [{"source": "/name", "text": product.name}]
    if product.manufacturer:
        intro_refs.append({"source": "/manufacturer", "text": product.manufacturer})
    add(intro, intro_refs)
    if purpose:
        add("Назначение из описания: «" + purpose["text"] + "».",
            [{"source": "/description", "text": purpose["text"]}])
    else:
        add("Назначение не подтверждено исходным описанием. До выбора исполнения нужно уточнить, какую задачу должен решать прибор.")

    covered = []
    for f in ordered:
        label = f["label"][:1].upper() + f["label"][1:]
        guidance = GUIDANCE.get(key(f["label"]))
        text = f"{label} — {f['value']}."
        if guidance:
            text += " " + guidance[0]
        if add(text, [{"source": f["source"], "text": f["value"]}]):
            covered.append(f["id"])
        if len("\n\n".join(blocks)) >= 1000:
            break

    missing_labels = [k for k in dict.fromkeys(list(product.specs) + list(product.required_specs))
                      if not product.specs.get(k)]
    if missing_labels:
        names = ", ".join(missing_labels[:4])
        add(f"Для завершения подбора нужно уточнить: {names}. Эти параметры не подтверждены исходными данными и не должны считаться согласованными при заказе.")

    # Only used when available source-specific paragraphs cannot reach the brief's minimum.
    fallbacks = [
        "При запросе предложения передайте поставщику название изделия и значения из списка характеристик. Так можно согласовать конкретное исполнение, а не только товар с похожим обозначением.",
        "Если прибор подбирается для замены, приложите обозначение установленного изделия и требования к подключению. Взаимозаменяемость должна быть подтверждена отдельно до согласования заказа.",
        "Проверьте полноту документации: для окончательного выбора нужны сведения об условиях эксплуатации и ограничениях применения. Отсутствие этих сведений в карточке не подтверждает пригодность прибора для любых условий.",
        "В заявке отделите обязательные параметры от пожеланий. По каждому неподтверждённому пункту запросите ответ поставщика, чтобы сохранить согласованные требования вместе с предложением.",
        "Перед оформлением заказа уточните комплект поставки и нужные сопроводительные документы. Наличие, цену и сроки подтвердите при запросе предложения, чтобы опираться на актуальные условия поставки.",
    ]
    fallback_count = 0
    for text in fallbacks:
        if len("\n\n".join(blocks)) >= 800:
            break
        if add(text):
            fallback_count += 1

    questions = []
    for f in ordered:
        guidance = GUIDANCE.get(key(f["label"]))
        if guidance and guidance[1] not in questions:
            questions.append(guidance[1])
    questions.extend(f"Какое значение требуется для поля «{label}»?" for label in missing_labels)
    if not product.manufacturer:
        questions.insert(0, "Кто производитель и каково точное обозначение исполнения?")
    if not purpose:
        questions.insert(0, "Какую величину и в каких условиях должен измерять прибор?")
    if product.description.rstrip().endswith(("...", "…")):
        questions.append("Можно ли получить полный паспорт вместо обрывающегося описания?")
    if not questions:
        questions.append("Какие требования к применению нужно подтвердить перед заказом?")
    actions = {
        "selection": "Начните подбор с параметров ниже; ответы на вопросы помогут согласовать исполнение.",
        "procurement": "Перенесите подтверждённые параметры в заявку и запросите ответы на вопросы до согласования предложения.",
        "replacement": "Сравните параметры ниже с установленным прибором; запросите подтверждение взаимозаменяемости.",
    }
    commercial = {
        "audience": audience(purpose),
        "audience_source": "/description" if purpose and audience(purpose).startswith("Для специалистов,") else None,
        "task": purpose["text"] if purpose else "Назначение и решаемая задача: данных нет либо требуется уточнение.",
        "task_source": "/description" if purpose else None,
        "selection_basis": [{"label": f["label"], "value": f["value"], "source": f["source"]} for f in ordered[:4]],
        "questions": questions,
        "next_step": actions[angle],
    }
    return "\n\n".join(blocks), refs, commercial, {
        "copy_version": COPY_VERSION, "specific_spec_paragraphs": len(covered),
        "general_paragraphs": fallback_count,
    }
