"""B1 offline evidence; this is NOT PostgreSQL/RLS runtime verification.

Run directly with python -I -S -B, without pytest discovery. Real service modules
and the unchanged organisation resolver execute against a filtering memory
client. Package startup, _common operations and the NAAC importer are replaced
with traps; no seed/import functions run. SQL checks compose source policies,
not a database. Selected updated legacy assertions execute via AST extraction;
the unrelated provisioning/seed tests and authenticated DB module never run.
"""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import sys
import types
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICES = ROOT / "emma_core" / "services"
MIGRATIONS = ROOT / "supabase" / "migrations"
ORG_X = "00000000-0000-4000-8000-000000000001"
ORG_Y = "00000000-0000-4000-8000-000000000002"
X1 = "00000000-0000-4000-8000-000000000101"
X2 = "00000000-0000-4000-8000-000000000102"
Y1 = "00000000-0000-4000-8000-000000000201"
NEW_SQL = "20261003000026_unapproved_global_dictionary_reads.sql"


def forbidden(*_args, **_kwargs):
    raise AssertionError("out-of-scope operation attempted")


class MemoryQuery:
    """Apply the actual query predicates to independent mixed-tenant rows."""
    def __init__(self, client, table):
        self.client, self.table = client, table
        self.filters = []
        self.columns = "*"
        self.sort_field = None
        self.or_expression = None

    def select(self, columns):
        self.columns = columns
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def or_(self, expression):
        # Model the former unsafe predicate too, so regression tests fail on
        # the old implementation for leaked results, not a missing mock method.
        match = re.fullmatch(
            r"org_id.eq.([^,]+),and\(org_id.is.null,facility_id.is.null\)", expression)
        if not match:
            raise AssertionError("unsupported query expression")
        self.or_expression = match.group(1)
        return self

    def order(self, field):
        self.sort_field = field
        return self

    def execute(self):
        rows = [dict(row) for row in self.client.tables[self.table]]
        for field, value in self.filters:
            rows = [r for r in rows if value is not None and r.get(field) == value]
        if self.or_expression is not None:
            rows = [r for r in rows if r.get("org_id") == self.or_expression or (
                r.get("org_id") is None and r.get("facility_id") is None)]
        if self.sort_field:
            rows.sort(key=lambda r: r[self.sort_field])
        if self.columns != "*":
            fields = self.columns.split(",")
            rows = [{field: r.get(field) for field in fields} for r in rows]
        return types.SimpleNamespace(data=rows)


class MemoryClient:
    def __init__(self):
        facilities = [
            {"id": X1, "org_id": ORG_X}, {"id": X2, "org_id": ORG_X},
            {"id": Y1, "org_id": ORG_Y},
        ]
        rows = []
        for label, org, facility, active in (
            ("global", None, None, True),
            ("y-shared", ORG_Y, None, True),
            ("x1", ORG_X, X1, True),
            ("x2", ORG_X, X2, True),
            ("x-shared", ORG_X, None, True),
            ("y1", ORG_Y, Y1, True),
            ("invalid-null-org", None, X1, True),
            ("x-inactive", ORG_X, X1, False),
            ("y-inactive", ORG_Y, Y1, False),
        ):
            rows.append({
                "id": label, "org_id": org, "facility_id": facility,
                "active": active, "code": label, "task_code": label,
                "task_name": "label-" + label,
            })
        self.tables = {
            "facilities": facilities,
            "task_definitions": [dict(r) for r in rows],
            "escort_locations": [dict(r) for r in rows],
        }
        self.queries = []

    def table(self, name):
        if name not in self.tables:
            raise AssertionError("unexpected table")
        query = MemoryQuery(self, name)
        self.queries.append(query)
        return query


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Read the pinned .py directly; importlib otherwise probes cached .pyc files.
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    parent, _, leaf = name.rpartition(".")
    setattr(sys.modules[parent], leaf, module)
    return module


class B1SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = ("emma_core", "emma_core.services", "emma_core.importers",
                 "emma_core.services._common", "emma_core.importers.naac")
        stubs = {}
        for name in names:
            module = types.ModuleType(name)
            module.__path__ = []
            stubs[name] = module
        for name in ("assignments_for_shifts", "now_iso", "to_min"):
            setattr(stubs["emma_core.services._common"], name, forbidden)
        stubs["emma_core.importers.naac"].load_escort_locations = forbidden
        stubs["emma_core.importers"].naac = stubs["emma_core.importers.naac"]
        stubs["emma_core"].services = stubs["emma_core.services"]
        cls.modules = patch.dict(sys.modules, stubs)
        cls.modules.start()
        cls.addClassCleanup(cls.modules.stop)
        cls.org = load_module("emma_core.services.organisations", SERVICES / "organisations.py")
        cls.tasks = load_module("emma_core.services.tasks", SERVICES / "tasks.py")
        cls.escort = load_module("emma_core.services.escort", SERVICES / "escort.py")

    def setUp(self):
        self.org._ORG_BY_FACILITY.clear()
        self.client = MemoryClient()

    def calls(self):
        return (
            ("task_definitions", self.tasks, self.tasks.task_definitions_by_label),
            ("escort_locations", self.escort, self.escort.list_locations),
        )

    def ids(self, result):
        rows = result.values() if isinstance(result, dict) else result
        return {r["id"] for r in rows}

    def test_org_x_access_includes_x1_x2_and_shared_only(self):
        for table, _, call in self.calls():
            for facility in (X1, X2):
                with self.subTest(table=table, facility=facility):
                    self.assertEqual(self.ids(call(self.client, facility)), {"x1", "x2", "x-shared"})

    def test_org_y_access_is_bidirectionally_isolated(self):
        for table, _, call in self.calls():
            with self.subTest(table=table):
                self.assertEqual(self.ids(call(self.client, Y1)), {"y1", "y-shared"})

    def test_only_global_and_invalid_rows_returns_empty(self):
        for table, _, call in self.calls():
            self.client.tables[table] = [
                r for r in self.client.tables[table] if r["org_id"] is None]
            with self.subTest(table=table):
                self.assertEqual(self.ids(call(self.client, X1)), set())

    def test_foreign_rows_remain_denied_when_no_own_dictionary_exists(self):
        for table, _, call in self.calls():
            self.client.tables[table] = [
                r for r in self.client.tables[table] if r["org_id"] != ORG_X]
            with self.subTest(table=table):
                self.assertEqual(self.ids(call(self.client, X1)), set())

    def test_service_queries_use_org_equality_and_active(self):
        for table, _, call in self.calls():
            call(self.client, X1)
            query = [q for q in self.client.queries if q.table == table][-1]
            self.assertEqual(query.filters, [("org_id", ORG_X), ("active", True)])
            self.assertIsNone(query.or_expression)

    def test_escort_include_inactive_never_expands_org_scope(self):
        rows = self.escort.list_locations(self.client, X1, include_inactive=True)
        self.assertEqual(self.ids(rows), {"x1", "x2", "x-shared", "x-inactive"})
        self.assertEqual([r["code"] for r in rows], sorted(r["code"] for r in rows))

    def test_task_labels_and_codes_resolve_to_same_row(self):
        rows = self.tasks.task_definitions_by_label(self.client, X1)
        for label in ("x1", "x2", "x-shared"):
            self.assertIs(rows[label], rows["label-" + label])
        self.assertEqual(len(rows), 6)

    def test_global_label_cannot_shadow_own_label(self):
        global_row = self.client.tables["task_definitions"][0]
        global_row.update(task_code="x1", task_name="label-x1")
        self.assertEqual(self.tasks.task_definitions_by_label(self.client, X1)["x1"]["id"], "x1")

    def test_invalid_facility_scope_fails_before_any_query(self):
        for _, _, call in self.calls():
            for value in (None, "", " ", "null", "invalid", 42, {}, ORG_X + ",org_id.is.null"):
                with self.subTest(call=call.__name__, value=value):
                    client = MemoryClient()
                    with self.assertRaisesRegex(ValueError, "valid facility and organisation scope"):
                        call(client, value)
                    self.assertEqual(client.queries, [])

    def test_unknown_facility_fails_before_dictionary_query(self):
        self.client.tables["facilities"] = [r for r in self.client.tables["facilities"] if r["id"] != X1]
        for _, _, call in self.calls():
            with self.assertRaises(ValueError):
                call(self.client, X1)
        self.assertTrue(all(q.table == "facilities" for q in self.client.queries))

    def test_missing_org_mapping_fails_closed(self):
        self.client.tables["facilities"][0]["org_id"] = None
        for _, _, call in self.calls():
            with self.assertRaises(ValueError):
                call(self.client, X1)
        self.assertTrue(all(q.table == "facilities" for q in self.client.queries))

    def test_invalid_resolved_org_never_reaches_dictionary_query(self):
        for _, module, call in self.calls():
            for value in (None, "", "null", "invalid", 42, {}, ORG_X + ",org_id.is.null"):
                with self.subTest(call=call.__name__, value=value):
                    client = MemoryClient()
                    with patch.object(module, "org_id_for", return_value=value):
                        with self.assertRaisesRegex(ValueError, "valid facility and organisation scope"):
                            call(client, X1)
                    self.assertEqual(client.queries, [])

    def test_resolver_failure_propagates_without_fallback(self):
        for _, module, call in self.calls():
            client = MemoryClient()
            with patch.object(module, "org_id_for", side_effect=RuntimeError("synthetic resolver failure")):
                with self.assertRaisesRegex(RuntimeError, "synthetic resolver failure"):
                    call(client, X1)
            self.assertEqual(client.queries, [])

    def test_memory_client_applies_filters_and_models_old_leak(self):
        old = (self.client.table("task_definitions").select("*")
               .or_(f"org_id.eq.{ORG_X},and(org_id.is.null,facility_id.is.null)")
               .eq("active", True).execute().data)
        self.assertIn("global", self.ids(old))
        filtered = (self.client.table("task_definitions").select("*")
                    .eq("org_id", ORG_X).eq("active", True).execute().data)
        self.assertEqual(self.ids(filtered), {"x1", "x2", "x-shared"})

    def test_updated_legacy_query_assertions(self):
        # Execute exact selected source definitions, without importing pytest,
        # provisioning helpers, environment handling or application startup.
        source = ast.parse((ROOT / "tests" / "test_m1_trial_offline.py").read_text(encoding="utf-8"))
        selected = []
        wanted = {"RecordingQuery", "RecordingClient",
                  "test_service_role_dictionary_queries_deny_unapproved_global_rows"}
        for node in source.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in wanted:
                node.decorator_list = []
                selected.append(node)
        self.assertEqual(len(selected), 3)
        namespace = {"SimpleNamespace": types.SimpleNamespace}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "<selected B1 assertions>", "exec"), namespace)
        for module_name, function in (("tasks", "task_definitions_by_label"), ("escort", "list_locations")):
            with patch.object(getattr(self, module_name), "org_id_for") as resolver:
                monkeypatch = types.SimpleNamespace(
                    setattr=lambda module, name, replacement: setattr(module, name, replacement))
                namespace["test_service_role_dictionary_queries_deny_unapproved_global_rows"](
                    monkeypatch, module_name, function)

    def test_updated_legacy_effective_policy_assertion(self):
        source = ast.parse((ROOT / "tests" / "test_m1_trial_offline.py").read_text(encoding="utf-8"))
        node = next(n for n in source.body if isinstance(n, ast.FunctionDef) and
                    n.name == "test_rls_policy_does_not_treat_every_facility_null_row_as_global")
        namespace = {"ROOT": ROOT, "MIGRATION": MIGRATIONS / "20261001000024_tenant_dictionary_boundary.sql"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<selected policy assertion>", "exec"), namespace)
        namespace[node.name]()

    def test_effective_read_and_for_all_policies_have_no_global_branch(self):
        # Restricted source inventory, NOT a SQL parser or RLS execution.
        policies = {}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8").lower())
            for statement in sql.split(";"):
                statement = " ".join(statement.split())
                match = re.match(
                    r"(drop policy if exists|create policy) (\w+) on (?:public\.)?"
                    r"(task_definitions|escort_locations)\b(.*)", statement)
                if not match:
                    continue
                verb, name, table, rest = match.groups()
                key = (table, name)
                if verb.startswith("drop"):
                    policies.pop(key, None)
                else:
                    policies[key] = rest
        self.assertEqual(set(policies), {
            (table, table + suffix)
            for table in ("task_definitions", "escort_locations") for suffix in ("_read", "_write")
        })
        for (table, name), statement in policies.items():
            with self.subTest(table=table, policy=name):
                self.assertIn("org_id = public.current_org_id()", statement)
                self.assertNotIn(" or ", statement)
                self.assertNotIn("facility_id is null", statement)
                if name.endswith("_read"):
                    self.assertEqual(statement.strip(),
                        "for select to authenticated using (org_id is not null and org_id = public.current_org_id())")
                else:
                    self.assertIn("for all to authenticated", statement)
                    self.assertIn("with check (org_id = public.current_org_id())", statement)

    def test_migration_is_read_policy_only_and_transactional(self):
        text = (MIGRATIONS / NEW_SQL).read_text(encoding="utf-8")
        sql = re.sub(r"--[^\n]*", "", text.lower())
        statements = [" ".join(s.split()) for s in sql.split(";") if s.strip()]
        self.assertEqual(len(statements), 6)
        self.assertEqual(statements[0], "begin")
        self.assertEqual(statements[-1], "commit")
        self.assertEqual(sum(s.startswith("drop policy") for s in statements), 2)
        self.assertEqual(sum(s.startswith("create policy") for s in statements), 2)
        self.assertNotRegex(sql, r"\b(insert|update|delete|truncate|grant|revoke|function)\b")
        self.assertIn("NOT TESTED", text)

    def test_all_six_changed_files_have_valid_python_or_bounded_sql(self):
        paths = [SERVICES / "tasks.py", SERVICES / "escort.py",
                 ROOT / "tests" / "test_m1_trial_offline.py",
                 ROOT / "tests" / "test_m1_dictionary_isolation_db.py",
                 pathlib.Path(__file__)]
        for path in paths:
            with self.subTest(path=path.name):
                compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_runtime_spec_has_no_client_or_credential_loader(self):
        source = (ROOT / "tests" / "test_m1_dictionary_isolation_db.py").read_text(encoding="utf-8")
        self.assertIn("NOT TESTED", source)
        tree = ast.parse(source)
        imported = [
            node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("emma_core.config", imported)
        self.assertNotIn("emma_core.db", imported)
        self.assertNotIn("supabase", imported)
        self.assertNotIn("pytest.skip", source)
        self.assertNotIn("super.naac@", source)


def install_offline_guard():
    allowed_sources = {
        SERVICES / "tasks.py", SERVICES / "escort.py", SERVICES / "organisations.py",
        ROOT / "tests" / "test_m1_trial_offline.py",
        ROOT / "tests" / "test_m1_dictionary_isolation_db.py", pathlib.Path(__file__),
    }
    allowed_sources.update(MIGRATIONS.glob("*.sql"))
    allowed_sources = {p.resolve() for p in allowed_sources}
    stdlib = pathlib.Path(sys.base_prefix).resolve() / "Lib"

    def audit(event, args):
        if event.startswith(("socket.", "subprocess.", "winreg.")) or event in {
            "os.system", "os.exec", "os.spawn", "os.posix_spawn",
        }:
            raise AssertionError("offline runner blocked network/process/registry access")
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = pathlib.Path(args[0]).resolve()
            mode = args[1]
            flags = args[2]
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or (
                isinstance(flags, int) and flags & 3):
                raise AssertionError("offline runner blocked a file write")
            if path not in allowed_sources and not path.is_relative_to(stdlib):
                raise AssertionError("offline runner blocked an unapproved file read")
        if event == "import" and args[0].startswith((
            "supabase", "postgrest", "dotenv", "boto", "api.",
            "emma_core.config", "emma_core.db",
        )):
            raise AssertionError("offline runner blocked application/credential imports")
    sys.addaudithook(audit)


if __name__ == "__main__":
    install_offline_guard()
    unittest.main()
