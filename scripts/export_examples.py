"""Reproduce the committed demo artifacts from the repository root."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cardcraft.domain import Product, parse_json
from cardcraft.provider import DemoPlanner
from cardcraft.render import generate, markdown

for source in sorted((ROOT / "examples/input").glob("*.json")):
    card = generate(Product.from_dict(parse_json(source.read_bytes())), DemoPlanner())
    target = ROOT / "examples/output" / source.stem
    target.parent.mkdir(parents=True, exist_ok=True)
    target.with_suffix(".json").write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target.with_suffix(".md").write_text(markdown(card), encoding="utf-8")
    print(f"{source.stem}: {card['quality']['description_chars']} characters, mode=demo")
