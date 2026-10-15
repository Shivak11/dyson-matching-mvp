"""Score saved pipeline decisions against source labels without calling a model."""
import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {"match", "not_sure", "not_in_catalogue"}
OUTCOMES = {"confirmed", "contradicted", "insufficient_evidence"}
MISS_IDS = {None, "", "none", "missed", "detection_miss"}


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def _strings(value):
    if isinstance(value, str):
        return [value] if value else []
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        raise ValueError("Decision evidence and alternatives must be strings or lists of strings")
    return value


def _decision(value):
    if not isinstance(value, dict) or value.get("status") not in STATUSES:
        raise ValueError("Invalid decision status")
    confidence = value.get("confidence", 0)
    if isinstance(confidence, bool) or not isinstance(confidence, (float, int)) or not math.isfinite(confidence) or not 0 <= confidence <= 100:
        raise ValueError("Confidence must be a finite number from 0 to 100")
    product = value.get("product")
    if value["status"] == "match" and (not isinstance(product, str) or not product):
        raise ValueError("A match must name a product")
    if value["status"] != "match" and product is not None:
        raise ValueError("Only a match may name a product")
    return {"status": value["status"], "product": product, "confidence": confidence,
            **{key: _strings(value.get(key, [])) for key in
               ("top_two", "evidence", "missing_evidence", "contradictions")},
            "retake": value.get("retake")}


def _unsure(reason, decisions=()):
    choices = []
    for decision in decisions:
        choices.extend(([decision["product"]] if decision["product"] else []) + decision["top_two"])
    return {"status": "not_sure", "product": None, "confidence": 0,
            "top_two": list(dict.fromkeys(choices))[:2],
            "evidence": [item for decision in decisions for item in decision["evidence"]],
            "missing_evidence": [reason] + [item for decision in decisions for item in decision["missing_evidence"]],
            "contradictions": [item for decision in decisions for item in decision["contradictions"]],
            "retake": next((decision["retake"] for decision in decisions if decision["retake"]), None)}


def combine_decisions(first, second):
    """Accept only independent agreement, retaining the lower reported confidence."""
    first, second = _decision(first), _decision(second)
    if first["status"] == second["status"] and first["product"] == second["product"] and first["status"] != "not_sure":
        return {"status": first["status"], "product": first["product"],
                "confidence": min(first["confidence"], second["confidence"]),
                "top_two": list(dict.fromkeys(first["top_two"] + second["top_two"]))[:2],
                **{key: first[key] + second[key] for key in ("evidence", "missing_evidence", "contradictions")},
                "retake": first["retake"] or second["retake"]}
    answer = _unsure("Independent checks did not agree on a resolved answer.", (first, second))
    if (first["status"], first["product"]) != (second["status"], second["product"]):
        answer["contradictions"].append(
            f"First check: {first['status']} {first['product']}; second check: {second['status']} {second['product']}.")
    return answer


def _is_miss(result):
    return result.get("detection_missed", False) or result.get("instance_id") in MISS_IDS


def _aggregate(instances):
    if not instances:
        return _unsure("No pipeline result was saved for this photo.")
    decisions = [_decision(item["decision"]) for item in instances]
    if any(_is_miss(item) for item in instances):
        return _unsure("No product instance was detected.", decisions)
    statuses = {item["status"] for item in decisions}
    products = {item["product"] for item in decisions if item["status"] == "match"}
    if statuses == {"not_in_catalogue"} or statuses == {"match"} and len(products) == 1:
        answer = decisions[0]
        for decision in decisions[1:]:
            answer = combine_decisions(answer, decision)
        return answer
    return _unsure("Detected objects did not give one consistent resolved identity.", decisions)


def _verification(photo_rows, grouped):
    counts = Counter()
    pairs = []
    for row in photo_rows:
        instances = grouped.get(row["image_id"], [])
        checks_by_product = defaultdict(list)
        for instance in instances:
            for check in instance.get("candidate_checks", []):
                checks_by_product[check["product"]].append(check["outcome"])
        for product, outcomes in sorted(checks_by_product.items()):
            complete = len(outcomes) == len(instances) and all(not _is_miss(item) for item in instances)
            outcome = ("confirmed" if "confirmed" in outcomes else "contradicted"
                       if complete and all(x == "contradicted" for x in outcomes)
                       else "insufficient_evidence")
            positive = product in row["labels"]
            key = {True: {"confirmed": "true_accept", "contradicted": "false_reject", "insufficient_evidence": "positive_abstention"},
                   False: {"confirmed": "false_accept", "contradicted": "true_reject", "insufficient_evidence": "negative_abstention"}}[positive][outcome]
            counts[key] += 1
            pairs.append({"image_id": row["image_id"], "expected_product": product,
                          "source_positive": positive, "outcome": outcome,
                          "checked_instance_count": len(outcomes), "result_instance_count": len(instances),
                          "complete_instance_coverage": complete})
    result = {key: counts[key] for key in ("true_accept", "false_accept", "true_reject", "false_reject", "positive_abstention", "negative_abstention")}
    positive = result["true_accept"] + result["false_reject"] + result["positive_abstention"]
    negative = result["false_accept"] + result["true_reject"] + result["negative_abstention"]
    positive_resolved = positive - result["positive_abstention"]
    negative_resolved = negative - result["negative_abstention"]
    result.update({"evaluated_pair_count": len(pairs), "positive_pair_count": positive, "negative_pair_count": negative,
                   "positive_resolved_coverage": _rate(positive_resolved, positive),
                   "negative_resolved_coverage": _rate(negative_resolved, negative),
                   "false_accept_rate_all_negative_pairs": _rate(result["false_accept"], negative),
                   "false_reject_rate_all_positive_pairs": _rate(result["false_reject"], positive),
                   "false_accept_rate_resolved_negative_pairs": _rate(result["false_accept"], negative_resolved),
                   "false_reject_rate_resolved_positive_pairs": _rate(result["false_reject"], positive_resolved),
                   "pairs": pairs,
                   "scope": "Only supplied, actually checked candidate-photo pairs. Unchecked candidates are excluded; incomplete instance coverage cannot establish contradiction."})
    return result


def evaluate(rows, results, catalogue_order):
    """Keep the full labelled denominator for every observed model/variant group."""
    catalogue = set(catalogue_order)
    if not catalogue or len(catalogue) != len(catalogue_order):
        raise ValueError("Catalogue must contain unique product IDs")
    if not isinstance(rows, list) or not isinstance(results, list):
        raise ValueError("Manifest and results must be lists")
    rows = [row for row in rows if row.get("evaluation_role") in {"labelled_single", "labelled_multi"}]
    row_by_id = {row["image_id"]: row for row in rows}
    if len(row_by_id) != len(rows):
        raise ValueError("Manifest image IDs must be unique")
    for row in rows:
        if not row.get("labels") or len(set(row["labels"])) != len(row["labels"]):
            raise ValueError("Source labels must be nonempty and unique")
        if row["evaluation_role"] == "labelled_single" and len(row["labels"]) != 1:
            raise ValueError("Single-photo rows must have exactly one source label")
    singles = [row for row in rows if row["evaluation_role"] == "labelled_single"]
    multis = [row for row in rows if row["evaluation_role"] == "labelled_multi"]
    groups = defaultdict(lambda: defaultdict(list))
    seen, ignored = set(), set()
    for item in results:
        if item["image_id"] not in row_by_id:
            ignored.add(item["image_id"])
            continue
        key = (item["model"], item["variant"], item["image_id"], item.get("instance_id"))
        if key in seen:
            raise ValueError(f"Duplicate result for {key}")
        seen.add(key)
        decision = _decision(item["decision"])
        if decision["product"] and decision["product"] not in catalogue:
            raise ValueError("Matched product is not a catalogue ID")
        if _is_miss(item) and decision["status"] != "not_sure":
            raise ValueError("A missing detection must remain not sure")
        candidates = item.get("candidates", [])
        supplied = item.get("supplied_candidates", candidates)
        if not isinstance(candidates, list) or not isinstance(supplied, list) or any(x not in catalogue for x in candidates + supplied):
            raise ValueError("Candidates must be catalogue IDs")
        checked = set()
        for check in item.get("candidate_checks", []):
            if check.get("product") not in supplied or check.get("outcome") not in OUTCOMES or check["product"] in checked:
                raise ValueError("Candidate checks must be unique, valid and actually supplied")
            checked.add(check["product"])
        groups[(item["model"], item["variant"])][item["image_id"]].append(item)
    output = {"labelled_photo_count": len(rows), "single_photo_count": len(singles), "multi_photo_count": len(multis),
              "ignored_image_ids": sorted(ignored), "groups": []}
    for (model, variant), grouped in sorted(groups.items()):
        per_photo = []
        confusions = Counter()
        for row in singles:
            decision = _aggregate(grouped.get(row["image_id"], []))
            label = row["labels"][0]
            in_catalogue = label in catalogue
            correct = (decision["status"] == "match" and decision["product"] == label or
                       decision["status"] == "not_in_catalogue" and not in_catalogue)
            per_photo.append({**decision, "image_id": row["image_id"], "source_label": label,
                              "in_catalogue": in_catalogue, "correct": correct,
                              "result_present": row["image_id"] in grouped})
            confusions[(label, decision["product"] or decision["status"])] += 1
        n = len(singles)
        accepted = [x for x in per_photo if x["status"] == "match"]
        resolved = [x for x in per_photo if x["status"] != "not_sure"]
        wrong_accepted = [x for x in accepted if not x["correct"]]
        wrong = [x for x in resolved if not x["correct"]]
        correct_catalogue = sum(x["correct"] and x["in_catalogue"] for x in per_photo)
        correct_outside = sum(x["correct"] and not x["in_catalogue"] for x in per_photo)
        metrics = {"single_photo_count": n, "correct_total": correct_catalogue + correct_outside,
                   "correct_catalogue_matches": correct_catalogue,
                   "correct_non_catalogue_rejections": correct_outside,
                   "catalogue_photo_count": sum(x["in_catalogue"] for x in per_photo),
                   "non_catalogue_photo_count": sum(not x["in_catalogue"] for x in per_photo),
                   "accepted_count": len(accepted), "wrong_accepted_count": len(wrong_accepted),
                   "confidently_wrong_count": sum(x["confidence"] >= 90 for x in wrong),
                   "confidently_wrong_accepted_count": sum(x["confidence"] >= 90 for x in wrong_accepted),
                   "confidently_wrong_rejection_count": sum(x["confidence"] >= 90 and x["status"] == "not_in_catalogue" for x in wrong),
                   "false_catalogue_rejection_count": sum(x["in_catalogue"] and x["status"] == "not_in_catalogue" for x in per_photo),
                   "not_in_catalogue_count": sum(x["status"] == "not_in_catalogue" for x in per_photo),
                   "not_sure_count": n - len(resolved), "resolved_count": len(resolved),
                   "accuracy": _rate(correct_catalogue + correct_outside, n),
                   "accepted_precision": _rate(correct_catalogue, len(accepted)),
                   "acceptance_coverage": _rate(len(accepted), n), "resolved_coverage": _rate(len(resolved), n),
                   "label_confusion": [{"source_label": label, "prediction": prediction, "count": count}
                                       for (label, prediction), count in sorted(confusions.items())]}
        multi_results = []
        for row in multis:
            instances = grouped.get(row["image_id"], [])
            decisions = [_decision(item["decision"]) for item in instances]
            predicted = sorted({item["product"] for item in decisions if item["status"] == "match"})
            expected = sorted(set(row["labels"]) & catalogue)
            unresolved = not instances or any(_is_miss(x) or x["decision"]["status"] == "not_sure" for x in instances)
            outside = sum(x["status"] == "not_in_catalogue" for x in decisions)
            multi_results.append({"image_id": row["image_id"], "expected_identity_set": expected,
                                  "predicted_identity_set": predicted,
                                  "identity_set_exact": predicted == expected,
                                  "correct_resolved_identity_set": predicted == expected and not unresolved and not outside,
                                  "unresolved": unresolved, "outside_instance_count": outside,
                                  "identity_to_box_accuracy": None,
                                  "scope": "Photo identity set only; the source does not assign model identity to a box."})
        retrieval_rows = []
        for row in rows:
            expected = set(row["labels"]) & catalogue
            if not expected:
                continue
            candidates = {product for item in grouped.get(row["image_id"], []) if not _is_miss(item) for product in item.get("candidates", [])}
            top_one = {item["candidates"][0] for item in grouped.get(row["image_id"], []) if not _is_miss(item) and item.get("candidates")}
            retrieval_rows.append({"image_id": row["image_id"], "expected": sorted(expected),
                                   "retrieved": sorted(candidates), "retrieved_expected_count": len(expected & candidates),
                                   "all_expected_retrieved": expected <= candidates,
                                   "all_expected_in_top_one_union": expected <= top_one,
                                   "evaluation_role": row["evaluation_role"]})
        retrieval_singles = [x for x in retrieval_rows if x["evaluation_role"] == "labelled_single"]
        detection_rows = []
        for row in rows:
            instances = grouped.get(row["image_id"], [])
            count = sum(not _is_miss(item) for item in instances)
            expected_count = len(row["labels"])
            detection_rows.append({"image_id": row["image_id"], "source_identity_count": expected_count,
                                   "detected_instance_count": count, "result_missing": not instances,
                                   "explicit_detection_miss": any(_is_miss(item) for item in instances),
                                   "instance_count_deficit": max(0, expected_count - count)})
        saved_count = len(grouped)
        missing_ids = [row["image_id"] for row in rows if row["image_id"] not in grouped]
        observed_singles = [x for x in per_photo if x["result_present"]]
        output["groups"].append({"model": model, "variant": variant, "metrics": metrics,
                                  "saved_photo_count": saved_count, "missing_result_photo_count": len(missing_ids),
                                  "missing_result_image_ids": missing_ids,
                                  "subset_warning": None if saved_count == len(rows) else "Incomplete model/variant coverage. Missing photos remain not sure in full-set metrics; observed-subset accuracy is not a full-set comparison.",
                                  "observed_single_photo_count": len(observed_singles),
                                  "observed_subset_accuracy": _rate(sum(x["correct"] for x in observed_singles), len(observed_singles)),
                                  "per_photo": per_photo, "wrong_answers": wrong, "multi_photo_results": multi_results,
                                  "retrieval": {"catalogue_single_photo_count": len(retrieval_singles),
                                                "recalled_catalogue_single_photos": sum(x["all_expected_retrieved"] for x in retrieval_singles),
                                                "catalogue_single_recall": _rate(sum(x["all_expected_retrieved"] for x in retrieval_singles), len(retrieval_singles)),
                                                "catalogue_single_top_one_recall": _rate(sum(x["all_expected_in_top_one_union"] for x in retrieval_singles), len(retrieval_singles)),
                                                "per_photo": retrieval_rows,
                                                "scope": "Photo-level union of retrieved candidates. Multi-photo identity-to-box retrieval is unscored."},
                                  "detection": {"explicit_detection_miss_photo_count": sum(x["explicit_detection_miss"] for x in detection_rows),
                                                "missing_result_photo_count": len(missing_ids),
                                                "instance_count_deficit": sum(x["instance_count_deficit"] for x in detection_rows),
                                                "per_photo": detection_rows,
                                                "scope": "Count deficit against source identities, including missing results. Correct localisation and duplicate detections require separate box review."},
                                  "verification": _verification(rows, grouped)})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=ROOT / "out/pipeline/results.json")
    parser.add_argument("--manifest", type=Path, default=ROOT / "data/test/test_manifest.json")
    parser.add_argument("--output", type=Path, default=ROOT / "out/pipeline/summary.json")
    args = parser.parse_args()
    catalogue = list(json.loads((ROOT / "data/catalog_sources.json").read_text()))
    summary = evaluate(json.loads(args.manifest.read_text()), json.loads(args.results.read_text()), catalogue)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "groups": len(summary["groups"]),
                      "labelled_photos": summary["labelled_photo_count"]}))


if __name__ == "__main__":
    main()
