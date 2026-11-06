import json
from pathlib import Path
import unittest
from cardcraft.domain import Product
from cardcraft.provider import DemoPlanner
from cardcraft.render import generate, markdown

ROOT = Path(__file__).resolve().parents[1]


class EditorialTests(unittest.TestCase):
    def card(self, name):
        return generate(Product.from_dict(json.loads((ROOT / f'examples/input/{name}.json').read_text())), DemoPlanner())

    def test_product_specific_audiences_and_questions(self):
        pressure = self.card('manometer')
        temperature = self.card('demo-incomplete')
        self.assertIn('избыточного давления', pressure['commercial']['audience'])
        self.assertIn('температуры в учебном стенде', temperature['commercial']['audience'])
        self.assertNotEqual(pressure['commercial']['questions'], temperature['commercial']['questions'])
        self.assertTrue(any('присоединение' in x for x in pressure['commercial']['questions']))
        self.assertTrue(any('интерфейс' in x for x in temperature['commercial']['questions']))

    def test_pressure_copy_uses_no_general_padding(self):
        card = self.card('manometer')
        self.assertEqual(card['meta']['editorial']['general_paragraphs'], 0)
        self.assertEqual(card['meta']['editorial']['specific_spec_paragraphs'], 4)
        for item in card['commercial']['selection_basis']:
            self.assertIn(item['value'], card['seo_description'])
            self.assertTrue(item['source'].startswith('/specs/'))
        self.assertIn('0–1,6 МПа', card['seo_title'])
        self.assertTrue(any('0–1,6 МПа' in x for x in card['search_queries']))

    def test_unknown_purpose_does_not_invent_industry(self):
        card = generate(Product.from_dict({'name': 'X', 'description': 'Материал корпуса указан в паспорте.'}), DemoPlanner())
        self.assertIsNone(card['commercial']['audience_source'])
        self.assertIn('не определена', card['commercial']['audience'])
        self.assertTrue(any('Мало предметных данных' in x for x in card['warnings']))

    def test_reviewed_spec_not_promoted(self):
        p = Product.from_dict({'name': 'X', 'specs': {'диапазон измерений': '999 МПа'},
                               'description': 'Прибор предназначен для измерения давления.'})
        class Planner(DemoPlanner):
            def plan(self, product):
                return {**super().plan(product), 'review_ids': ['s0']}
        c = generate(p, Planner())
        self.assertNotIn('999', c['seo_title'])
        self.assertNotIn('999', c['seo_description'])
        self.assertEqual(c['commercial']['selection_basis'], [])
        self.assertEqual(c['characteristics'][0]['value'], '999 МПа')
        self.assertTrue(c['review_items'])

    def test_purpose_does_not_become_false_audience(self):
        p = Product.from_dict({'name': 'X', 'description': 'Прибор не предназначен для измерения давления.'})
        class Planner(DemoPlanner):
            def plan(self, product):
                return {**super().plan(product), 'purpose_id': 'd0'}
        c = generate(p, Planner())
        self.assertIsNone(c['commercial']['audience_source'])

    def test_markdown_has_manager_questions(self):
        c = self.card('manometer')
        self.assertIn('Вопросы заказчику', markdown(c))
        self.assertIn('На что опереться', markdown(c))
