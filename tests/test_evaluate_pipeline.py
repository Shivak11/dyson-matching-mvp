"""Offline checks for full-denominator and three-outcome pipeline scoring."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("evaluator", Path(__file__).resolve().parents[1] / "tools/evaluate_pipeline.py")
e = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e)


def source(image_id, labels, role="labelled_single"):
    return {"image_id": image_id, "labels": labels, "evaluation_role": role}


def decision(status="match", product="a", confidence=95):
    return {"status": status, "product": product if status == "match" else None, "confidence": confidence,
            "top_two": ["a", "b"], "evidence": ["Visible control"], "missing_evidence": [], "contradictions": [], "retake": None}


def result(image_id="one", instance_id="1", answer=None, candidates=None, checks=None, model="one", variant="bundle"):
    return {"image_id": image_id, "instance_id": instance_id, "model": model, "variant": variant,
            "decision": answer or decision(), "candidates": ["a", "b"] if candidates is None else candidates,
            "candidate_checks": checks or []}


def check(product, outcome):
    return {"product": product, "outcome": outcome, "evidence": []}


class PipelineEvaluatorTests(unittest.TestCase):
    def test_omitted_rows_and_detection_miss_remain_in_denominator(self):
        rows = [source("one", ["a"]), source("two", ["a"]), source("three", ["outside"])]
        results = [result(), result("two", None, decision("not_sure", confidence=0), candidates=[])]
        group = e.evaluate(rows, results, ["a", "b"])["groups"][0]
        self.assertEqual(group["metrics"]["single_photo_count"], 3)
        self.assertEqual(group["metrics"]["correct_total"], 1)
        self.assertEqual(group["metrics"]["not_sure_count"], 2)
        self.assertEqual(group["missing_result_image_ids"], ["three"])
        self.assertEqual(group["retrieval"]["catalogue_single_recall"], .5)
        self.assertEqual(group["detection"]["explicit_detection_miss_photo_count"], 1)
        self.assertEqual(group["detection"]["instance_count_deficit"], 2)
        self.assertIsNotNone(group["subset_warning"])

    def test_empty_results_preserve_declared_denominators(self):
        summary = e.evaluate([source("one", ["a"])], [], ["a", "b"])
        self.assertEqual(summary["single_photo_count"], 1)
        self.assertEqual(summary["groups"], [])

    def test_multibox_conflicts_and_unresolved_objects_abstain(self):
        rows = [source("one", ["a"])]
        for second in [decision(product="b"), decision("not_sure"), decision("not_in_catalogue")]:
            group = e.evaluate(rows, [result(), result(instance_id="2", answer=second)], ["a", "b"])["groups"][0]
            self.assertEqual(group["metrics"]["not_sure_count"], 1)
            self.assertEqual(group["metrics"]["accepted_count"], 0)
        same = e.evaluate(rows, [result(), result(instance_id="2", answer=decision(confidence=80))], ["a", "b"])["groups"][0]
        self.assertEqual(same["per_photo"][0]["confidence"], 80)
        self.assertEqual(same["metrics"]["correct_total"], 1)

    def test_multi_photo_scored_as_set_without_box_identity_claim(self):
        rows = [source("P059", ["a", "b"], "labelled_multi")]
        results = [result("P059", "right", decision(product="a")), result("P059", "left", decision(product="b"))]
        group = e.evaluate(rows, results, ["a", "b"])["groups"][0]
        multi = group["multi_photo_results"][0]
        self.assertEqual(group["metrics"]["single_photo_count"], 0)
        self.assertTrue(multi["correct_resolved_identity_set"])
        self.assertIsNone(multi["identity_to_box_accuracy"])
        results.append(result("P059", "third", decision("not_sure")))
        multi = e.evaluate(rows, results, ["a", "b"])["groups"][0]["multi_photo_results"][0]
        self.assertTrue(multi["identity_set_exact"])
        self.assertFalse(multi["correct_resolved_identity_set"])

    def test_three_way_verification_denominators_and_unchecked_exclusion(self):
        rows = [source("one", ["a"]), source("two", ["a"]), source("three", ["outside"])]
        results = [result(checks=[check("a", "confirmed"), check("b", "insufficient_evidence")]),
                   result("two", checks=[check("a", "insufficient_evidence"), check("b", "contradicted")]),
                   result("three", checks=[check("a", "confirmed")])]
        verification = e.evaluate(rows, results, ["a", "b"])["groups"][0]["verification"]
        self.assertEqual(verification["evaluated_pair_count"], 5)
        self.assertEqual(verification["positive_pair_count"], 2)
        self.assertEqual(verification["negative_pair_count"], 3)
        self.assertEqual(verification["positive_abstention"], 1)
        self.assertEqual(verification["negative_abstention"], 1)
        self.assertEqual(verification["positive_resolved_coverage"], .5)
        self.assertAlmostEqual(verification["negative_resolved_coverage"], 2/3)
        self.assertAlmostEqual(verification["false_accept_rate_all_negative_pairs"], 1/3)
        self.assertEqual(verification["false_accept_rate_resolved_negative_pairs"], .5)

    def test_unchecked_object_cannot_establish_photo_wide_contradiction(self):
        rows = [source("one", ["a"])]
        first = result(checks=[check("a", "contradicted")])
        second = result(instance_id="2", checks=[check("b", "contradicted")])
        verification = e.evaluate(rows, [first, second], ["a", "b"])["groups"][0]["verification"]
        self.assertEqual(verification["positive_abstention"], 1)
        self.assertEqual(verification["negative_abstention"], 1)
        second["candidate_checks"].append(check("a", "confirmed"))
        verification = e.evaluate(rows, [first, second], ["a", "b"])["groups"][0]["verification"]
        self.assertEqual(verification["true_accept"], 1)

    def test_combine_requires_independent_agreement_and_keeps_lower_confidence(self):
        agreed = e.combine_decisions(decision(confidence=99), decision(confidence=81))
        self.assertEqual(agreed["confidence"], 81)
        self.assertEqual(len(agreed["evidence"]), 2)
        disagreed = e.combine_decisions(decision(product="a"), decision(product="b"))
        self.assertEqual(disagreed["status"], "not_sure")
        self.assertEqual(disagreed["top_two"], ["a", "b"])
        self.assertTrue(disagreed["contradictions"])
        outside = e.combine_decisions(decision("not_in_catalogue"), decision("not_in_catalogue"))
        self.assertEqual(outside["status"], "not_in_catalogue")
        mixed = e.combine_decisions(decision(), decision("not_sure"))
        self.assertEqual(mixed["status"], "not_sure")

    def test_confident_wrong_matches_and_rejections_both_visible(self):
        rows = [source("one", ["a"]), source("two", ["a"]), source("three", ["outside"])]
        results = [result(answer=decision(product="b")), result("two", answer=decision("not_in_catalogue")),
                   result("three", answer=decision("not_in_catalogue"))]
        metrics = e.evaluate(rows, results, ["a", "b"])["groups"][0]["metrics"]
        self.assertEqual(metrics["correct_total"], 1)
        self.assertEqual(metrics["wrong_accepted_count"], 1)
        self.assertEqual(metrics["confidently_wrong_count"], 2)
        self.assertEqual(metrics["confidently_wrong_accepted_count"], 1)
        self.assertEqual(metrics["confidently_wrong_rejection_count"], 1)
        self.assertEqual(metrics["false_catalogue_rejection_count"], 1)
        self.assertEqual(metrics["accepted_precision"], 0)
        self.assertEqual(metrics["resolved_coverage"], 1)

    def test_groups_do_not_share_coverage_and_demo_is_excluded(self):
        rows = [source("one", ["a"]), source("two", ["a"])]
        results = [result(), result("two"), result(model="second"), result("demo")]
        summary = e.evaluate(rows, results, ["a", "b"])
        self.assertEqual(summary["ignored_image_ids"], ["demo"])
        first, second = summary["groups"]
        self.assertIsNone(first["subset_warning"])
        self.assertEqual(second["metrics"]["not_sure_count"], 1)
        self.assertEqual(second["observed_subset_accuracy"], 1)
        self.assertEqual(second["metrics"]["accuracy"], .5)

    def test_missing_detected_object_result_keeps_single_and_multi_incomplete(self):
        rows = [source("single", ["a"]), source("multi", ["a", "b"], "labelled_multi")]
        detections = {name: [{"instance_id": "1"}, {"instance_id": "2"}] for name in ("single", "multi")}
        results = [result("single", "1", checks=[check("a", "contradicted")]),
                   result("multi", "1", checks=[check("a", "confirmed"), check("b", "contradicted")])]
        group = e.evaluate(rows, results, ["a", "b"], detections)["groups"][0]
        self.assertEqual(group["metrics"]["not_sure_count"], 1)
        self.assertEqual(group["metrics"]["accepted_count"], 0)
        self.assertEqual(group["missing_instance_result_count"], 2)
        self.assertEqual(group["complete_photo_count"], 0)
        self.assertEqual(group["saved_photo_count"], 2)
        self.assertIsNotNone(group["subset_warning"])
        self.assertEqual(group["per_photo"][0]["missing_instance_result_ids"], ["2"])
        self.assertTrue(group["multi_photo_results"][0]["unresolved"])
        self.assertFalse(group["multi_photo_results"][0]["result_complete"])
        self.assertFalse(group["multi_photo_results"][0]["correct_resolved_identity_set"])
        self.assertEqual(group["verification"]["false_reject"], 0)
        self.assertEqual(group["verification"]["positive_abstention"], 2)
        self.assertEqual(group["verification"]["true_accept"], 1)
        self.assertEqual(group["detection"]["per_photo"][0]["detected_instance_count"], 2)

    def test_missing_third_object_prevents_resolved_multi_set_even_when_labels_match(self):
        rows = [source("multi", ["a", "b"], "labelled_multi")]
        detections = {"multi": [{"instance_id": str(i)} for i in (1, 2, 3)]}
        results = [result("multi", "1"), result("multi", "2", decision(product="b"))]
        multi = e.evaluate(rows, results, ["a", "b"], detections)["groups"][0]["multi_photo_results"][0]
        self.assertTrue(multi["identity_set_exact"])
        self.assertFalse(multi["correct_resolved_identity_set"])
        self.assertEqual(multi["missing_instance_result_ids"], ["3"])

    def test_empty_detection_stays_miss_and_unknown_detection_record_is_incomplete(self):
        rows = [source("one", ["a"]), source("two", ["a"])]
        results = [result("one", None, decision("not_sure")), result("two")]
        group = e.evaluate(rows, results, ["a", "b"], {"one": []})["groups"][0]
        self.assertEqual(group["metrics"]["not_sure_count"], 2)
        self.assertEqual(group["detection"]["explicit_detection_miss_photo_count"], 1)
        self.assertEqual(group["missing_detection_record_photo_count"], 1)
        self.assertEqual(group["complete_photo_count"], 1)
        with self.assertRaises(ValueError):
            e.evaluate(rows, [result()], ["a", "b"], {"one": []})

    def test_invalid_or_duplicate_results_are_rejected(self):
        rows = [source("one", ["a"])]
        invalid = [result(checks=[check("unknown", "confirmed")]),
                   result(answer=decision(product="unknown")),
                   result(answer=decision(confidence=float("nan"))),
                   result(instance_id=None),
                   result(checks=[check("a", "confirmed"), check("a", "contradicted")])]
        for value in invalid:
            with self.assertRaises(ValueError):
                e.evaluate(rows, [value], ["a", "b"])
        with self.assertRaises(ValueError):
            e.evaluate(rows, [result(), result()], ["a", "b"])

    def test_explicit_extra_expected_candidate_is_evaluated_not_retrieved(self):
        row = result(candidates=["b"], checks=[check("a", "confirmed")])
        row["supplied_candidates"] = ["a", "b"]
        group = e.evaluate([source("one", ["a"])], [row], ["a", "b"])["groups"][0]
        self.assertEqual(group["retrieval"]["catalogue_single_recall"], 0)
        self.assertEqual(group["verification"]["true_accept"], 1)


if __name__ == "__main__":
    unittest.main()
