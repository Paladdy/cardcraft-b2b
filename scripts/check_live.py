"""Interactive real API check. Key stays in memory; results go to ignored output/."""
import getpass
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cardcraft.domain import AppError, Product, parse_json
from cardcraft.provider import OpenAIPlanner
from cardcraft.render import generate, markdown


def main():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        if not sys.stdin.isatty():
            print("Запустите в терминале для скрытого ввода ключа или задайте OPENAI_API_KEY.", file=sys.stderr)
            return 2
        key = getpass.getpass("OpenAI API key (ввод скрыт): ").strip()
    if not key:
        print("Ключ не введён.", file=sys.stderr)
        return 2
    print("Проверка двух примеров через OpenAI API. Вызовы расходуют лимит вашего API-аккаунта.")
    out = ROOT / "output/live"
    out.mkdir(parents=True, exist_ok=True)
    try:
        planner = OpenAIPlanner(api_key=key)
        for name in ("manometer", "demo-incomplete"):
            product = Product.from_dict(parse_json((ROOT / f"examples/input/{name}.json").read_bytes()))
            card = generate(product, planner)
            (out / f"{name}.json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (out / f"{name}.md").write_text(markdown(card), encoding="utf-8")
            print(f"OK {name}: mode={card['meta']['mode']}, SEO={card['quality']['description_chars']} символов")
        print(f"Результаты: {out}. Проверьте назначение, источники и предупреждения перед сдачей.")
        return 0
    except AppError as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    except OSError:
        print("Не удалось сохранить результаты в output/live.", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        return 130


if __name__ == "__main__":
    sys.exit(main())
