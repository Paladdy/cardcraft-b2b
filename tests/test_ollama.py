import io
import json
import unittest
from urllib.error import HTTPError, URLError
from cardcraft.domain import AppError, Product
from cardcraft.ollama import OllamaPlanner
from cardcraft.provider import DemoPlanner, make_planner


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.product = Product.from_dict({'name': 'X', 'specs': {'питание': '24 В'}})
        self.plan = DemoPlanner().plan(self.product)

    def response(self, plan=None, **extra):
        return io.BytesIO(json.dumps({'done': True, 'message': {'content': json.dumps(plan or self.plan)}, **extra}).encode())

    def test_local_request_no_key(self):
        def transport(request, timeout):
            self.assertEqual(request.full_url, 'http://127.0.0.1:11434/api/chat')
            self.assertNotIn('Authorization', request.headers)
            body = json.loads(request.data)
            self.assertFalse(body['stream'])
            self.assertEqual(body['format']['properties']['spec_order']['items']['enum'], ['s0'])
            self.assertEqual(timeout, 180)
            return self.response()
        self.assertEqual(OllamaPlanner(transport=transport).plan(self.product), self.plan)

    def test_missing_model(self):
        def transport(*a, **k):
            raise HTTPError('http://localhost', 404, 'not found', {}, None)
        with self.assertRaises(AppError) as ctx:
            OllamaPlanner(transport=transport).plan(self.product)
        self.assertEqual(ctx.exception.code, 'ollama_model_missing')

    def test_no_server(self):
        def transport(*a, **k):
            raise URLError('connection refused')
        with self.assertRaises(AppError) as ctx:
            OllamaPlanner(transport=transport).plan(self.product)
        self.assertEqual(ctx.exception.code, 'ollama_unavailable')

    def test_invalid_plan_rejected(self):
        with self.assertRaises(AppError):
            OllamaPlanner(transport=lambda *a, **k: self.response({**self.plan, 'spec_order': ['invented']})).plan(self.product)

    def test_incomplete(self):
        with self.assertRaises(AppError) as ctx:
            OllamaPlanner(transport=lambda *a, **k: self.response(done_reason='length')).plan(self.product)
        self.assertEqual(ctx.exception.code, 'incomplete_model_output')

    def test_invalid_response(self):
        for raw in (b'no', b'null', b'{"done":true,"message":{}}'):
            with self.subTest(raw=raw), self.assertRaises(AppError):
                OllamaPlanner(transport=lambda *a, **k: io.BytesIO(raw)).plan(self.product)

    def test_explicit_provider_and_cloud_guard(self):
        self.assertIsInstance(make_planner('ollama'), OllamaPlanner)
        with self.assertRaises(AppError):
            OllamaPlanner(model='model:cloud')
