"""Local black-box acceptance checks. Never calls a paid API or publishes files."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/verification"
OUT.mkdir(parents=True, exist_ok=True)
checks = []


def check(label, condition, detail=""):
    checks.append({"check": label, "status": "pass" if condition else "fail", "detail": detail})


def cli(*args, stdin=None):
    env = dict(os.environ)
    env.pop("OPENAI_API_KEY", None)
    return subprocess.run([sys.executable, "-m", "cardcraft", *args], input=stdin,
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=15)


def resolve(document, pointer):
    for key in pointer.split("/")[1:]:
        document = document[key.replace("~1", "/").replace("~0", "~")]
    return document


for path in sorted((ROOT / "examples/input").glob("*.json")):
    name = path.stem
    source = json.loads(path.read_text(encoding="utf-8"))
    run = cli(str(path), "--demo")
    check(name + ": CLI JSON", run.returncode == 0, run.stderr)
    if run.returncode:
        continue
    card = json.loads(run.stdout)
    (OUT / (name + ".json")).write_text(run.stdout, encoding="utf-8")
    title, description = len(card["seo_title"]), len(card["seo_description"])
    check(name + ": SEO title", 0 < title <= 70, str(title))
    check(name + ": SEO description", 800 <= description <= 1200, str(description))
    queries = card["search_queries"]
    check(name + ": search queries", 3 <= len(queries) <= 5 and len(queries) == len(set(queries)), str(len(queries)))
    check(name + ": technical source pointers", all(
        resolve(source, item["source"]).strip() == item["value"]
        for item in card["characteristics"] if item["source"]))
    expected = {k: v.strip() for k, v in source["specs"].items() if v and v.strip()}
    actual = {x["label"]: x["value"] for x in card["characteristics"] if x["source"]}
    check(name + ": all supplied specs retained", expected == actual)
    check(name + ": evidence grounded in input", all(
        item["text"] in resolve(source, item["source"]) for item in card["evidence"]))
    commercial = card["commercial"]
    check(name + ": commercial source", bool(commercial["audience"]) and bool(commercial["next_step"])
          and (commercial["task_source"] is None or commercial["task"] in source["description"]))
    check(name + ": draft and demo labels", card["meta"]["mode"] == "demo"
          and card["quality"]["status"] == "needs_review")
    check(name + ": committed JSON reproducible", card == json.loads(
        (ROOT / "examples/output" / (name + ".json")).read_text(encoding="utf-8")))
    md = cli(str(path), "--demo", "--format", "markdown", "-o", str(OUT / (name + ".md")))
    check(name + ": Markdown file export", md.returncode == 0 and not md.stdout)
    check(name + ": committed Markdown reproducible", (OUT / (name + ".md")).read_text(encoding="utf-8") ==
          (ROOT / "examples/output" / (name + ".md")).read_text(encoding="utf-8"))

invalid = [("broken JSON", "{", "invalid_json"),
           ("empty object", "{}", "missing_name"),
           ("blank name", '{"name":"  "}', "missing_name"),
           ("wrong root", "[]", "invalid_input"),
           ("duplicate key", '{"name":"X","name":"Y"}', "invalid_json"),
           ("unitless numeric spec", '{"name":"X","specs":{"power":24}}', "invalid_input"),
           ("oversized body", " " * 65537, "input_too_large")]
for label, raw, code in invalid:
    run = cli("-", "--demo", stdin=raw)
    check(label, run.returncode == 2 and not run.stdout
          and json.loads(run.stderr)["error"]["code"] == code)

minimal = cli("-", "--demo", stdin='{"name":"X","required_specs":["питание"]}')
card = json.loads(minimal.stdout)
check("missing data explicit", any(x["label"] == "питание" and x["value"] == "данных нет"
      for x in card["characteristics"]) and "/specs/питание" in {x["field"] for x in card["missing_fields"]})
run = cli("examples/input/manometer.json")
check("live without key fails, no silent demo", run.returncode == 2 and not run.stdout
      and json.loads(run.stderr)["error"]["code"] == "missing_api_key")

tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()
check("no tracked .env secrets file", all(Path(p).name == ".env.example" or not Path(p).name.startswith(".env")
      for p in tracked))
ignored = subprocess.run(["git", "check-ignore", ".env", ".env.local"], cwd=ROOT, capture_output=True, text=True)
check("secret files ignored", set(ignored.stdout.splitlines()) == {".env", ".env.local"})
for doc in ("README.md", "docs/decisions.md", "docs/submission.md", "docs/demo.md"):
    check("documentation: " + doc, (ROOT / doc).is_file() and (ROOT / doc).stat().st_size > 0)

report = {"checks": checks, "passed": sum(x["status"] == "pass" for x in checks),
          "failed": sum(x["status"] == "fail" for x in checks),
          "limitations": ["Offline checks only; no live LLM validation.",
                          "Second product is synthetic; not supplied by employer.",
                          "Content quality requires human review."]}
(OUT / "acceptance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
for item in checks:
    print(item["status"].upper() + " " + item["check"] + (": " + item["detail"] if item["detail"] else ""))
print(f"\n{report['passed']} passed; {report['failed']} failed. Live LLM: NOT CHECKED.")
sys.exit(bool(report["failed"]))
