from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from research_ops import core  # noqa: E402


class ResearchOpsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        core.init_project(self.root)
        (self.root / "AGENTS.md").write_text("mandatory rules\n", encoding="utf-8")
        (self.root / "request.txt").write_text("exact user request\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_task(self, *, execute: bool = False, artifacts: list[str] | None = None) -> dict:
        return core.create_task(
            self.root,
            request_file="request.txt",
            objective="verify one bounded research task",
            role_id="R03",
            scope="TEST_SCOPE",
            method_fingerprint="METHOD-V1",
            allowed_actions=["read", "test"],
            forbidden_actions=["destructive write"],
            required_evidence=["command", "hash", "result"],
            success_criteria=["independent verification passes"],
            approved_artifact_ids=artifacts or [],
            execution_authorized=execute,
        )

    def acknowledge(self, task: dict) -> dict:
        return core.acknowledge_task(self.root, task["task_id"], agent_id="TEST-AGENT")

    def install_system_fixture(self) -> None:
        record_paths = [
            "01_목표",
            "02_상태",
            "03_방법",
            "04_근거",
            "05_데이터",
            "06_코드",
            "07_실행",
            "08_검증",
            "09_실패",
            "10_결정",
            "11_재현",
            "12_협업",
        ]
        for rel in record_paths:
            (self.root / rel).mkdir(parents=True, exist_ok=True)
        (self.root / "project.yaml").write_text('{"recovery":{"strict_status":"PASS"}}\n', encoding="utf-8")
        (self.root / "research_recovery.py").write_text("# harness\n", encoding="utf-8")
        skill = self.root / ".agents/skills/연구기록_전체복구/SKILL.md"
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("recovery skill\n", encoding="utf-8")
        (self.root / "12_협업/역할목록.yaml").write_text("roles: []\n", encoding="utf-8")
        (self.root / "12_협업/역할간_인계기록.jsonl").write_text("", encoding="utf-8")
        report = self.root / "08_검증/reports/연구기록복구/연구기록_복구감사.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "status": "PASS",
                    "strict": True,
                    "errors": [],
                    "counts": {
                        "sources_selected": 1,
                        "classifiable_events": 1,
                        "parse_failures": 0,
                        "unresolved_conflicts": 0,
                        "items_excluded_without_reason": 0,
                        "missing_documents": 0,
                    },
                    "coverage": {"raw_line_index": 1.0, "document_map": 1.0},
                }
            ),
            encoding="utf-8",
        )
        contracts = self.root / "00_research_ops/contracts"
        evidence = self.root / "00_research_ops/evidence"
        contracts.mkdir(parents=True, exist_ok=True)
        evidence.mkdir(parents=True, exist_ok=True)
        required = [
            {"path": "project.yaml", "kind": "file"},
            {"path": "research_recovery.py", "kind": "file"},
            {"path": ".agents/skills/연구기록_전체복구/SKILL.md", "kind": "file"},
            *({"path": rel, "kind": "directory"} for rel in record_paths),
            {"path": "08_검증/reports/연구기록복구/연구기록_복구감사.json", "kind": "file"},
            {"path": "12_협업/역할목록.yaml", "kind": "file"},
            {"path": "12_협업/역할간_인계기록.jsonl", "kind": "file"},
        ]
        (contracts / "RECORD_STRUCTURE_BINDING_V1.json").write_text(
            json.dumps(
                {
                    "schema": "RESEARCH_OPERATING_SYSTEM_RECORD_BINDING_V1",
                    "authority_hierarchy": ["00_research_ops", "V6_RECORD_STRUCTURE"],
                    "split_brain_record_store_forbidden": True,
                    "role_policy": {
                        "self_approval_forbidden": True,
                        "verification_role": "R04",
                        "independent_review_role": "R06",
                        "closing_evidence_must_bind_exact_task_id": True,
                    },
                    "required_record_paths": required,
                }
            ),
            encoding="utf-8",
        )
        (contracts / "GATE_CATALOG_V7.json").write_text(
            json.dumps(
                {
                    "gate_order": list(core.V7_GATE_ORDER),
                    "generic_gate_cannot_supply_domain_thresholds": True,
                    "domain_profile_required_for_scientific_run": True,
                    "gates": [{"gate_id": gate, "blocking": True} for gate in core.V7_GATE_ORDER],
                }
            ),
            encoding="utf-8",
        )
        (evidence / "V7_ARCHIVE_REVIEW.json").write_text(
            json.dumps(
                {
                    "status": "ACCEPTED_WITH_HARDENING_NOT_BLINDLY_INSTALLED",
                    "blind_extraction_performed": False,
                    "archive_code_executed": False,
                    "archive": {"sha256": "4331721fccfa8170d024c939fcdf1dd971f3786d25064c8db84e7da4da826c25"},
                    "accepted_concepts": ["gates"],
                    "rejected_direct_install_reasons": ["unsafe overwrite"],
                }
            ),
            encoding="utf-8",
        )

    def install_new_project_system_fixture(self) -> None:
        self.install_system_fixture()
        profile_path = self.root / "00_research_ops/PROJECT_PROFILE.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile.update(
            {
                "record_system_mode": "NEW_PROJECT_EMPTY",
                "new_project_initialization_evidence": "00_research_ops/evidence/NEW_PROJECT_INITIALIZATION.json",
                "portable_package_lineage_evidence": "00_research_ops/evidence/PORTABLE_PACKAGE_LINEAGE.json",
            }
        )
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        (self.root / "08_검증/reports/연구기록복구/연구기록_복구감사.json").unlink()
        (self.root / "00_research_ops/evidence/V7_ARCHIVE_REVIEW.json").unlink()
        (self.root / "00_research_ops/evidence/NEW_PROJECT_INITIALIZATION.json").write_text(
            json.dumps(
                {
                    "schema": "RESEARCH_NEW_PROJECT_INITIALIZATION_V1",
                    "status": "PASS",
                    "record_system_mode": "NEW_PROJECT_EMPTY",
                    "historical_recovery_claimed": False,
                    "scientific_validation_claimed": False,
                    "record_store_initialized": True,
                }
            ),
            encoding="utf-8",
        )
        (self.root / "00_research_ops/evidence/PORTABLE_PACKAGE_LINEAGE.json").write_text(
            json.dumps(
                {
                    "schema": "RESEARCH_PORTABLE_PACKAGE_LINEAGE_V1",
                    "status": "PASS",
                    "package_id": "research_ops_record_template_v1",
                    "project_specific_data_included": False,
                    "historical_run_data_included": False,
                }
            ),
            encoding="utf-8",
        )

    def test_missing_read_receipt_blocks_preflight(self) -> None:
        task = self.create_task()
        with self.assertRaisesRegex(core.OpsError, "READ_RECEIPT"):
            core.preflight(self.root, task["task_id"])

    def test_task_packet_preserves_exact_user_request_descriptor(self) -> None:
        task = self.create_task()
        self.assertEqual(task["user_instruction"], core.descriptor(self.root, "request.txt"))

    def test_user_instruction_mutation_blocks_acknowledgement(self) -> None:
        task = self.create_task()
        (self.root / "request.txt").write_text("changed request\n", encoding="utf-8")
        with self.assertRaisesRegex(core.OpsError, "differs"):
            self.acknowledge(task)

    def test_approved_artifact_is_pinned_and_mutation_blocks(self) -> None:
        (self.root / "model.json").write_text('{"version":1}\n', encoding="utf-8")
        core.register_artifact(
            self.root,
            logical_id="FINAL_MODEL",
            path="model.json",
            status="APPROVED",
            approved_by="USER",
            approval_basis="explicit approval EVT-1",
            allowed_uses=["TEST_SCOPE"],
            supersedes=None,
        )
        task = self.create_task(artifacts=["FINAL_MODEL"])
        self.acknowledge(task)
        (self.root / "model.json").write_text('{"version":2}\n', encoding="utf-8")
        with self.assertRaisesRegex(core.OpsError, "differs|substitution"):
            core.preflight(self.root, task["task_id"])


    def test_approved_artifact_requires_git_receipt_when_policy_enabled(self) -> None:
        policy_path = self.root / "00_research_ops/POLICY.json"
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy.setdefault("hard_rules", {})["approved_artifact_requires_git_promotion_checkpoint"] = True
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        (self.root / "model.json").write_text('{"version":1}\n', encoding="utf-8")
        with self.assertRaisesRegex(core.OpsError, "Git promotion receipt"):
            core.register_artifact(
                self.root,
                logical_id="FINAL_MODEL",
                path="model.json",
                status="APPROVED",
                approved_by="USER",
                approval_basis="explicit approval",
                allowed_uses=["TEST_SCOPE"],
                supersedes=None,
            )

    def test_unapproved_artifact_cannot_enter_task(self) -> None:
        with self.assertRaisesRegex(core.OpsError, "unavailable"):
            self.create_task(artifacts=["NOT_APPROVED"])

    def test_artifact_approved_for_another_scope_is_blocked(self) -> None:
        (self.root / "foreign.json").write_text('{"domain":"other"}\n', encoding="utf-8")
        core.register_artifact(
            self.root,
            logical_id="FOREIGN_RESULT",
            path="foreign.json",
            status="APPROVED",
            approved_by="USER",
            approval_basis="approved only for another task",
            allowed_uses=["OTHER_SCOPE"],
            supersedes=None,
        )
        with self.assertRaisesRegex(core.OpsError, "not authorized for this scope"):
            self.create_task(artifacts=["FOREIGN_RESULT"])

    def test_identical_failure_blocks_next_task_preflight(self) -> None:
        first = self.create_task()
        self.acknowledge(first)
        preflight = core.preflight(self.root, first["task_id"])
        core.record_failure(
            self.root,
            task_id=first["task_id"],
            signature="SAME_FAILURE",
            summary="same settings failed",
            evidence_paths=["request.txt"],
            correction_required="change method and verify",
        )
        second = self.create_task()
        self.acknowledge(second)
        with self.assertRaisesRegex(core.OpsError, "recurrence blockers"):
            core.preflight(self.root, second["task_id"])
        self.assertEqual(preflight["status"], "PASS")

    def test_repeated_failure_is_explicitly_marked(self) -> None:
        task = self.create_task()
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        first = core.record_failure(self.root, task_id=task["task_id"], signature="X", summary="x", evidence_paths=[], correction_required="fix")
        second = core.record_failure(self.root, task_id=task["task_id"], signature="X", summary="x again", evidence_paths=[], correction_required="fix")
        self.assertEqual(first["status"], "OPEN")
        self.assertEqual(second["status"], "RECURRENCE_BLOCKED")
        self.assertEqual(second["repeated_of"], first["failure_id"])

    def test_resolved_failure_does_not_poison_later_same_command_signature(self) -> None:
        task = self.create_task()
        failure_path = self.root / "failure.txt"
        failure_path.write_text("first", encoding="utf-8")
        first = core.record_failure(
            self.root,
            task_id=task["task_id"],
            signature="COMMAND_NONZERO_SAME_COMMAND",
            summary="first defect",
            evidence_paths=["failure.txt"],
            correction_required="fix first defect",
        )
        (self.root / "decision.json").write_text(json.dumps({"status": "APPROVED"}), encoding="utf-8")
        (self.root / "verification.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
        core.resolve_failure(
            self.root,
            failure_id=first["failure_id"],
            decision_file="decision.json",
            verification_file="verification.json",
            resolved_by="R04",
        )
        second = core.record_failure(
            self.root,
            task_id=task["task_id"],
            signature="COMMAND_NONZERO_SAME_COMMAND",
            summary="different later defect",
            evidence_paths=["failure.txt"],
            correction_required="fix later defect",
        )
        self.assertEqual(second["status"], "OPEN")
        self.assertIsNone(second["repeated_of"])
        self.assertEqual(core.strict_audit(self.root)["status"], "PASS")

    def test_execution_without_authority_is_blocked(self) -> None:
        task = self.create_task(execute=False)
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        with self.assertRaisesRegex(core.OpsError, "not authorized"):
            core.run_command(self.root, task["task_id"], [sys.executable, "-c", "print(1)"], command_source="DIRECT_USER_OR_APPROVED_PLAN_NOT_TRANSCRIPT")

    def test_transcript_command_source_is_blocked(self) -> None:
        task = self.create_task(execute=True)
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        with self.assertRaisesRegex(core.OpsError, "transcript"):
            core.run_command(self.root, task["task_id"], [sys.executable, "-c", "print(1)"], command_source="TRANSCRIPT")

    def test_authorized_command_captures_manifest(self) -> None:
        task = self.create_task(execute=True)
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        result = core.run_command(self.root, task["task_id"], [sys.executable, "-c", "print('ok')"], command_source="DIRECT_USER_OR_APPROVED_PLAN_NOT_TRANSCRIPT")
        self.assertTrue(result["success"])
        self.assertEqual(result["returncode"], 0)
        stdout_path = self.root / result["stdout"]["path"]
        self.assertEqual(stdout_path.read_bytes().strip(), b"ok")
        self.assertEqual(core.sha256_file(stdout_path), result["stdout"]["sha256"])

    def test_context_pack_contains_current_state_and_failures(self) -> None:
        task = self.create_task()
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        result = core.context_pack(self.root, task["task_id"])
        payload = core.load_json(self.root / result["path"])
        self.assertEqual(payload["task"]["task_id"], task["task_id"])
        self.assertIn("$research-operations-continuity", payload["startup_instruction"])
        self.assertEqual(payload["continuation_live_files"][0]["path"], "AGENTS.md")

    def test_context_pack_includes_completed_result(self) -> None:
        task = self.create_task()
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        (self.root / "verify.json").write_text(
            json.dumps({"schema": "RESEARCH_AUTOMATED_VERIFICATION_V1", "task_id": task["task_id"], "role_id": "R04", "status": "PASS"}),
            encoding="utf-8",
        )
        (self.root / "review.json").write_text(
            json.dumps({"schema": "RESEARCH_INDEPENDENT_REVIEW_V1", "task_id": task["task_id"], "role_id": "R06", "status": "PASS"}),
            encoding="utf-8",
        )
        core.close_task(
            self.root,
            task["task_id"],
            verification_file="verify.json",
            independent_review_file="review.json",
            claims=["bounded result"],
            evidence_paths=["request.txt"],
        )
        packed = core.context_pack(self.root, task["task_id"])
        payload = core.load_json(self.root / packed["path"])
        self.assertEqual(payload["derived_state"], "COMPLETE")
        self.assertEqual(payload["final_report"]["status"], "COMPLETE")

    def test_public_event_rejects_private_reasoning_fields(self) -> None:
        with self.assertRaisesRegex(core.OpsError, "private reasoning"):
            core._reject_private_reasoning({"private_reasoning": "secret"})

    def test_claim_without_evidence_is_blocked(self) -> None:
        task = self.create_task()
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        (self.root / "verify.json").write_text(
            json.dumps({"schema": "RESEARCH_AUTOMATED_VERIFICATION_V1", "task_id": task["task_id"], "role_id": "R04", "status": "PASS"}),
            encoding="utf-8",
        )
        (self.root / "review.json").write_text(
            json.dumps({"schema": "RESEARCH_INDEPENDENT_REVIEW_V1", "task_id": task["task_id"], "role_id": "R06", "status": "PASS"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(core.OpsError, "direct evidence"):
            core.close_task(self.root, task["task_id"], verification_file="verify.json", independent_review_file="review.json", claims=["done"], evidence_paths=[])

    def test_close_task_rejects_self_authored_or_unbound_pass_files(self) -> None:
        task = self.create_task()
        self.acknowledge(task)
        core.preflight(self.root, task["task_id"])
        (self.root / "verify.json").write_text(
            json.dumps({"schema": "RESEARCH_AUTOMATED_VERIFICATION_V1", "task_id": task["task_id"], "role_id": "R00", "status": "PASS"}),
            encoding="utf-8",
        )
        (self.root / "review.json").write_text(
            json.dumps({"schema": "RESEARCH_INDEPENDENT_REVIEW_V1", "task_id": task["task_id"], "role_id": "R06", "status": "PASS"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(core.OpsError, "role differs"):
            core.close_task(self.root, task["task_id"], verification_file="verify.json", independent_review_file="review.json", claims=[], evidence_paths=[])
        (self.root / "verify.json").write_text(
            json.dumps({"schema": "RESEARCH_AUTOMATED_VERIFICATION_V1", "task_id": "TASK-WRONG", "role_id": "R04", "status": "PASS"}),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(core.OpsError, "task binding differs"):
            core.close_task(self.root, task["task_id"], verification_file="verify.json", independent_review_file="review.json", claims=[], evidence_paths=[])

    def test_strict_audit_detects_no_errors_for_preregistered_task(self) -> None:
        self.create_task()
        result = core.strict_audit(self.root)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["task_count"], 1)

    def test_status_is_derived_from_evidence_not_mutable_label(self) -> None:
        task = self.create_task()
        self.assertEqual(core.status(self.root)["tasks"][0]["derived_state"], "PREREGISTERED")
        self.acknowledge(task)
        self.assertEqual(core.status(self.root)["tasks"][0]["derived_state"], "READ_ACKNOWLEDGED")
        core.preflight(self.root, task["task_id"])
        self.assertEqual(core.status(self.root)["tasks"][0]["derived_state"], "PREFLIGHT_PASS")

    def test_path_escape_is_blocked(self) -> None:
        outside = self.root.parent / "outside.txt"
        outside.write_text("x", encoding="utf-8")
        try:
            with self.assertRaisesRegex(core.OpsError, "escapes"):
                core.descriptor(self.root, "../outside.txt")
        finally:
            outside.unlink()

    def test_full_operating_system_over_record_structure_audit(self) -> None:
        self.install_system_fixture()
        result = core.research_system_audit(self.root)
        self.assertEqual(result["status"], "PASS", result)

    def test_new_empty_project_system_audit_passes_without_fake_recovery(self) -> None:
        self.install_new_project_system_fixture()
        result = core.research_system_audit(self.root)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["record_recovery"]["status"], "NOT_APPLICABLE_NEW_PROJECT")
        self.assertFalse(result["optimizer_authorized_by_this_audit"])

    def test_incremental_recovery_failure_keeps_active_chat_sync_false(self) -> None:
        self.install_system_fixture()
        core.append_jsonl(
            self.root / "00_research_ops/failures/failure_registry.jsonl",
            {
                "schema": "RESEARCH_FAILURE_EVENT_V1",
                "record_type": "FAILURE",
                "failure_id": "FAIL-RECOVERY-INCREMENTAL-BASE-MISSING",
                "task_id": "LEGACY-RECOVERED",
                "scope": "RESEARCH_HISTORY_INCREMENTAL_SYNC",
                "signature": "INCREMENTAL_EXTRACTION_REQUIRES_ONE_UNCHAINED_COMPLETE_BASE",
                "status": "OPEN",
            },
        )
        result = core.research_system_audit(self.root)
        self.assertEqual(result["status"], "PASS", result)
        self.assertFalse(result["record_recovery"]["active_chat_incremental_sync_complete"])
        self.assertEqual(result["authority_hierarchy"], "RESEARCH_OPERATING_SYSTEM_OVER_RECORD_STRUCTURE")
        self.assertFalse(result["optimizer_authorized_by_this_audit"])

    def test_gate_order_mutation_blocks_system_audit(self) -> None:
        self.install_system_fixture()
        path = self.root / core.V7_GATE_CATALOG_PATH
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["gate_order"] = list(reversed(payload["gate_order"]))
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = core.research_system_audit(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("SYS-002", {row["check_id"] for row in result["checks"] if row["status"] == "FAIL"})

    def test_recovery_coverage_mutation_blocks_system_audit(self) -> None:
        self.install_system_fixture()
        path = self.root / "08_검증/reports/연구기록복구/연구기록_복구감사.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["coverage"]["document_map"] = 0.99
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = core.research_system_audit(self.root)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("SYS-006", {row["check_id"] for row in result["checks"] if row["status"] == "FAIL"})

    def test_safe_archive_is_hashed_without_extraction(self) -> None:
        archive = self.root / "safe.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("template/README.md", "safe")
        result = core.audit_zip_archive(archive, expected_sha256=core.sha256_file(archive))
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["archive_extracted"])
        self.assertFalse(result["archive_code_executed"])
        self.assertEqual(result["entries"][0]["sha256"], core.sha256_bytes(b"safe"))

    def test_zip_path_traversal_is_rejected(self) -> None:
        archive = self.root / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "unsafe")
        result = core.audit_zip_archive(archive)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("unsafe" in error for error in result["errors"]))

    @unittest.skipUnless(sys.platform == "win32", "Windows FileMode.CreateNew fallback")
    def test_windows_create_new_fallback_and_collision(self) -> None:
        target = self.root / "fallback.bin"
        core._windows_create_new_fallback(target, b"exact")
        self.assertEqual(target.read_bytes(), b"exact")
        with self.assertRaises(core.OpsError):
            core._windows_create_new_fallback(target, b"replacement")


if __name__ == "__main__":
    unittest.main()
