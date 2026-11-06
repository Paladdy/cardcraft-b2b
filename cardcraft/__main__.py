import argparse
import json
import sys
from pathlib import Path

from .domain import AppError, MAX_INPUT_BYTES, Product, parse_json
from .provider import make_planner
from .render import generate, markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description="Cardcraft — проверяемые черновики товарных карточек")
    parser.add_argument("input", nargs="?", help="Путь к JSON; '-' для stdin")
    parser.add_argument("--demo", action="store_true", help="Явный режим без LLM API")
    parser.add_argument("--provider", choices=("openai", "ollama"), default="openai")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--output", "-o", type=Path)
    parser.add_argument("--serve", action="store_true", help="Локальный HTTP API на 127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)
    try:
        if args.serve:
            from .server import serve
            serve(args.port, args.demo, args.provider)
            return 0
        if not args.input:
            parser.error("укажите input или --serve")
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        else:
            with open(args.input, "rb") as stream:
                raw = stream.read(MAX_INPUT_BYTES + 1)
        product = Product.from_dict(parse_json(raw))
        planner = make_planner(args.provider, args.demo)
        card = generate(product, planner)
        output = markdown(card) if args.format == "markdown" else json.dumps(card, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(output, encoding="utf-8")
        else:
            sys.stdout.write(output)
        return 0
    except AppError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError:
        print('{"error":{"code":"io_error","message":"Не удалось прочитать или записать файл либо открыть порт."}}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
