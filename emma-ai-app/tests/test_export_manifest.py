"""Offline only: python -I -S -B emma-ai-app/tests/test_export_manifest.py -v.

Direct execution avoids pytest plugins, conftest, and application startup.
Only the new source module and synthetic JSON configuration are loaded.
"""
from copy import deepcopy
import ast
import json
from pathlib import Path
import runpy
import unittest

APP = Path(__file__).resolve().parents[1]
MODULE = APP / "emma_core/exports/manifest.py"
API = runpy.run_path(str(MODULE))
validate = API["validate_naac_m3_17"]
validate_generic = API["validate_manifest"]
ManifestError = API["ManifestError"]
FIXTURE = APP / "emma_core/exports/templates/naac_m3_17.json"


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_exact_static_inventory(self):
        expected = ["更期代號註解", "代號及時數(old)", "代號及時數", "覆診地點代號",
                    "TAHDuty(week1)", "TAHDuty(week2)", "TAHDuty(week3)",
                    "TAHDuty(week4)", "TAHDuty(week5)", "TAHDuty(week6)",
                    "TAHDuty(hours)", "TAHDuty(PH&dayoff)", "TAHDuty(DO更次數)",
                    "TAHDuty(AP更)", "TAHDuty(C更男女)", "TAHDuty(N更男女)",
                    "TAHDuty(用膳代號)"]
        self.assertEqual([s["name"] for s in self.manifest["sheets"]], expected)
        self.assertEqual(validate(self.manifest).sheet_count, 17)

    def test_unknown_metadata_preserved_and_reported(self):
        before = deepcopy(self.manifest)
        result = validate(self.manifest)
        self.assertEqual(self.manifest, before)
        self.assertEqual(len(result.unresolved), 86)
        self.assertIn("sheets[1].print.included_by_default", result.unresolved)
        self.assertIn("sheets[0].calculation_status", result.unresolved)
        self.assertEqual(result.flagged, ())

    def test_missing_sheet_even_with_adjusted_count(self):
        self.manifest["sheets"].pop()
        self.manifest["sheet_count"] = 16
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_duplicate_or_extra_sheet(self):
        # No hypothetical eighteenth worksheet is invented.
        self.manifest["sheets"].append(deepcopy(self.manifest["sheets"][-1]))
        self.manifest["sheet_count"] = 18
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_renamed_sheet_rejected(self):
        self.manifest["sheets"][0]["name"] = "Renamed"
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_unique_extra_sheet_rejected_by_current_inventory(self):
        # Invalid input only, not a proposed or generated NAAC worksheet.
        extra = deepcopy(self.manifest["sheets"][-1])
        extra.update(id="invalid_extra", name="Invalid extra", order=18)
        self.manifest["sheets"].append(extra)
        self.manifest["sheet_count"] = 18
        self.assertEqual(validate_generic(self.manifest).sheet_count, 18)
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_reordered_sheets_even_with_renumbering(self):
        sheets = self.manifest["sheets"]
        sheets[0], sheets[1] = sheets[1], sheets[0]
        for index, sheet in enumerate(sheets, 1):
            sheet["order"] = index
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_duplicate_ids_and_case_insensitive_names(self):
        for field, value in (("id", "annotations"), ("name", "TAHDUTY(HOURS)")):
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][1][field] = value
                with self.assertRaises(ManifestError):
                    validate_generic(candidate)

    def test_count_is_exact_integer(self):
        for count in (True, 17.0, "17", 16, 18):
            with self.subTest(count=count):
                self.manifest["sheet_count"] = count
                with self.assertRaises(ManifestError):
                    validate(self.manifest)

    def test_schema_version_does_not_accept_bool(self):
        self.manifest["schema_version"] = True
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_unknown_fields_rejected_at_each_boundary(self):
        paths = [(), ("source",), ("cycle",), ("safety",), ("sheets", 0),
                 ("sheets", 0, "visibility"), ("sheets", 0, "print"),
                 ("sheets", 0, "print", "included_by_default")]
        for path in paths:
            with self.subTest(path=path):
                candidate = deepcopy(self.manifest)
                target = candidate
                for key in path:
                    target = target[key]
                target["unsupported"] = "do not execute"
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_tenant_authority_cannot_be_added(self):
        for field in ("facility_id", "org_id", "credentials", "database_url"):
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate[field] = "synthetic-test-value"
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_missing_fields_rejected(self):
        for field in self.manifest:
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                del candidate[field]
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_wrong_types_produce_manifest_errors(self):
        for bad in (None, [], "manifest", 42):
            with self.subTest(bad=bad):
                with self.assertRaises(ManifestError):
                    validate(bad)
        for field, bad in (("sheets", {}), ("source", []), ("cycle", None),
                           ("safety", "unsafe"), ("template_id", [])):
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate[field] = bad
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_unknown_and_incompatible_symbolic_references(self):
        for field, value in (("renderer", "unknown"), ("layout_id", "missing"),
                             ("layout_id", "naac_weekly"), ("renderer", "../module.py")):
            with self.subTest(field=field, value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0][field] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_shared_weekly_layout_is_allowed(self):
        weekly = self.manifest["sheets"][4:10]
        self.assertEqual({s["layout_id"] for s in weekly}, {"naac_weekly"})
        validate(self.manifest)

    def test_week_coverage_duplicates_and_wrong_types(self):
        for value in (1, 7, True, "2", None):
            with self.subTest(value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][5]["week_index"] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_nonweekly_sheet_cannot_have_week_index(self):
        self.manifest["sheets"][0]["week_index"] = 1
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_current_sheet_roles_are_pinned(self):
        self.manifest["sheets"][10]["renderer"] = "reference_table"
        self.manifest["sheets"][10]["layout_id"] = "naac_reference"
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_cycle_must_be_42_days_six_weeks_hong_kong(self):
        for field, value in (("days", 28), ("weeks", True), ("timezone", "UTC")):
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate["cycle"][field] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_no_silent_visibility_or_print_defaults(self):
        for field, value in (("visibility", "visible"), ("visibility", None)):
            with self.subTest(value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0][field] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)
        self.manifest["sheets"][0]["visibility"]["value"] = "visible"
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_hidden_metadata_is_flagged_not_applied(self):
        for visibility in ("hidden", "veryHidden"):
            with self.subTest(visibility=visibility):
                self.manifest["sheets"][0]["visibility"] = {"status": "confirmed", "value": visibility}
                result = validate(self.manifest)
                self.assertEqual(result.flagged, ("sheets[0].visibility",))

    def test_confirmed_print_boolean_does_not_accept_integer(self):
        self.manifest["sheets"][0]["print"]["included_by_default"] = {"status": "confirmed", "value": 1}
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_confirmed_metadata_success_and_remaining_unknowns(self):
        for included in (True, False):
            with self.subTest(included=included):
                candidate = deepcopy(self.manifest)
                candidate["cycle"]["first_weekday"] = {"status": "confirmed", "value": 1}
                candidate["sheets"][0]["visibility"] = {"status": "confirmed", "value": "visible"}
                candidate["sheets"][0]["print"]["included_by_default"] = {"status": "confirmed", "value": included}
                result = validate(candidate)
                self.assertEqual(len(result.unresolved), 83)
                self.assertNotIn("sheets[0].visibility", result.unresolved)
                self.assertEqual(result.flagged, ())

    def test_confirmed_weekday_boundaries(self):
        for value in range(1, 8):
            self.manifest["cycle"]["first_weekday"] = {"status": "confirmed", "value": value}
            validate(self.manifest)
        for value in (0, 8, True, 1.0, "1", None, []):
            with self.subTest(value=value):
                self.manifest["cycle"]["first_weekday"] = {"status": "confirmed", "value": value}
                with self.assertRaises(ManifestError):
                    validate(self.manifest)

    def test_nested_metadata_malformed_values(self):
        invalid = (None, [], {}, {"status": "unresolved"},
                   {"value": None}, {"status": [], "value": None},
                   {"status": "confirmed", "value": {}},
                   {"status": "unknown", "value": None})
        for value in invalid:
            with self.subTest(value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0]["visibility"] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_unresolved_calculations_cannot_be_marked_complete(self):
        for field in ("layout_status", "calculation_status"):
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0][field] = "confirmed"
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_formulas_and_conditional_rules_not_supported(self):
        for field in ("formula_specs", "conditional_rules"):
            for value in (["=SUM(A1:A2)"], {}, None):
                with self.subTest(field=field, value=value):
                    candidate = deepcopy(self.manifest)
                    candidate["sheets"][0][field] = value
                    with self.assertRaises(ManifestError):
                        validate(candidate)

    def test_formula_like_metadata_is_rejected(self):
        for value in ("=1+1", "+SUM(A1)", "-1+2", "@SUM(A1)", "\t=1", "\n=1", " =1"):
            with self.subTest(value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0]["purpose"] = value
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_invalid_excel_names(self):
        for value in ("bad/name", "bad[name]", "'bad", "bad'", "x" * 32, ""):
            with self.subTest(value=value):
                candidate = deepcopy(self.manifest)
                candidate["sheets"][0]["name"] = value
                with self.assertRaises(ManifestError):
                    validate_generic(candidate)

    def test_unsafe_policy_rejected(self):
        for field in self.manifest["safety"]:
            with self.subTest(field=field):
                candidate = deepcopy(self.manifest)
                candidate["safety"][field] = "allowed"
                with self.assertRaises(ManifestError):
                    validate(candidate)

    def test_real_data_or_operational_loading_declaration_rejected(self):
        self.manifest["data_classification"] = "real"
        with self.assertRaises(ManifestError):
            validate(self.manifest)
        self.manifest["data_classification"] = "synthetic_only"
        self.manifest["source"]["operational_content_loaded"] = True
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_generic_schema_is_separate_from_current_inventory(self):
        # Reuse one reference specification; no future NAAC sheet is invented.
        self.manifest["template_id"] = "synthetic-reference-test"
        self.manifest["sheets"] = self.manifest["sheets"][:1]
        self.manifest["sheet_count"] = 1
        self.assertEqual(validate_generic(self.manifest).sheet_count, 1)
        with self.assertRaises(ManifestError):
            validate(self.manifest)

    def test_error_does_not_echo_input(self):
        self.manifest["template_id"] = "=SYNTHETIC_UNTRUSTED_MARKER"
        with self.assertRaises(ManifestError) as caught:
            validate(self.manifest)
        self.assertNotIn("SYNTHETIC_UNTRUSTED_MARKER", str(caught.exception))

    def test_validator_imports_only_pure_standard_library_modules(self):
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imports |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        self.assertEqual(imports, {"__future__", "dataclasses", "re"})


if __name__ == "__main__":
    unittest.main()
