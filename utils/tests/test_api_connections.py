"""Run with the API's Python dependencies: python -m unittest discover -s utils/tests -p test_api_connections.py."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import sqlalchemy

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('api_utils_test', ROOT / 'mysocialwatcher/api/utils.py')
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        api._reset_engines_after_fork()

    def test_threads_share_one_bounded_engine(self):
        barrier = threading.Barrier(8)
        def get_engine(_):
            barrier.wait()
            return api.db_engine(pw='test', host='localhost', port='5432', db='test')
        with patch.object(api.sqlalchemy, 'create_engine') as create:
            with ThreadPoolExecutor(max_workers=8) as executor:
                engines = list(executor.map(get_engine, range(8)))
            create.assert_called_once()
            self.assertTrue(all(e is engines[0] for e in engines))
            self.assertEqual(create.call_args.kwargs['pool_size'], 3)
            self.assertEqual(create.call_args.kwargs['max_overflow'], 0)
            self.assertTrue(create.call_args.kwargs['pool_pre_ping'])

    def test_child_reset_does_not_reuse_parent_engine(self):
        with patch.object(api.sqlalchemy, 'create_engine', side_effect=[object(), object()]):
            first = api.db_engine(pw='test', host='localhost', port='5432', db='test')
            api._reset_engines_after_fork()
            second = api.db_engine(pw='test', host='localhost', port='5432', db='test')
            self.assertIsNot(first, second)

    def test_connection_failure_is_structured_and_hides_details(self):
        @api.database_errors
        def failing():
            raise sqlalchemy.exc.OperationalError('secret SQL', {}, Exception('private details'))
        result = failing()
        self.assertEqual(result['status'], 503)
        self.assertNotIn('secret', str(result))
        self.assertNotIn('private', str(result))

    def test_json_preserves_apostrophes(self):
        value = {"citizenship": {"name": "Expats (Cote d'Ivoire)"}}
        result = api.check_args(
            {'valid': True, 'all_fields': json.dumps(value)},
            required=['valid', 'all_fields'],
        )
        self.assertEqual(result['status'], 200)
        sql_literal = result['args']['all_fields']
        stored_value = sql_literal[1:-1].replace("''", "'")
        self.assertEqual(json.loads(stored_value), value)

    def test_legacy_python_json_literal_is_normalized(self):
        legacy = "{'name': 'countries', 'values': ['PS'], 'location_types': None}"
        result = api.check_args(
            {'valid': True, 'geo_locations': legacy},
            required=['valid', 'geo_locations'],
        )
        self.assertEqual(result['status'], 200)
        sql_literal = result['args']['geo_locations']
        stored_value = sql_literal[1:-1].replace("''", "'")
        self.assertEqual(
            json.loads(stored_value),
            {'name': 'countries', 'values': ['PS'], 'location_types': None},
        )

    def test_write_returns_connections_and_reports_insert_result(self):
        import ast
        from unittest.mock import MagicMock
        tree = ast.parse((ROOT / 'mysocialwatcher/api/endpoints.py').read_text())
        write = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'write')
        for fail, rowcount, expected_status in (
            (False, 1, 200),
            (False, 0, 409),
            (True, 1, 503),
        ):
            engine = MagicMock()
            connection = engine.connect.return_value.__enter__.return_value
            connection.execute.return_value.rowcount = rowcount
            ns = dict(vars(api))
            ns.update(db_engine=lambda: engine,
                      check_args=lambda *a, **kw: {'status': 200, 'message': '', 'args': {
                          'token': 'test', 'collection': 'test', 'timestamp': '1700000000',
                          'table': 'facebook'}},
                      validate_token=lambda **kw: {'status': 200, 'contributor_id': 1})
            def register(**kw):
                if fail:
                    raise sqlalchemy.exc.OperationalError('', {}, Exception('offline'))
                return 1
            ns['register_collection'] = register
            exec(compile(ast.Module(body=[write], type_ignores=[]), '<write>', 'exec'), ns)
            result = ns['write']({})
            self.assertEqual(result['status'], expected_status)
            self.assertEqual(engine.connect.call_count, 2 if fail else 3)
            self.assertEqual(engine.connect.return_value.__exit__.call_count, engine.connect.call_count)
            self.assertEqual(connection.execute.call_count, 0 if fail else 1)
            if not fail:
                sql = connection.execute.call_args.args[0]
                self.assertIn('ON CONFLICT DO NOTHING', sql)

    def test_all_endpoint_connections_are_scoped(self):
        import ast
        tree = ast.parse((ROOT / 'mysocialwatcher/api/endpoints.py').read_text())
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == 'db']
        for call in calls:
            self.assertNotEqual(call.func.attr, 'dispose')
            if call.func.attr == 'connect':
                self.assertIsInstance(parents[call], ast.withitem)


if __name__ == '__main__':
    unittest.main()
