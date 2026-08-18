from srstudio.images.evaluation import (
    DecisionView,
    EvaluationLabel,
    evaluate_decisions,
    sample_for_manual_review,
)


def decision(sha, product, status, confidence, *, consensus=1.0, products=1, alternatives=()):
    return DecisionView(
        image_sha256=sha,
        product_name=product,
        status=status,
        confidence=confidence,
        consensus_ratio=consensus,
        distinct_source_count=2,
        distinct_product_count=products,
        alternatives=alternatives,
    )


def test_evaluation_measures_product_precision_coverage_and_decorative_accuracy():
    decisions = [
        decision("a", "MONSTER 473ML", "accepted", .96),
        decision("b", "TODDY 750G", "probable", .86),
        decision("c", "", "decorative", .40),
    ]
    labels = [
        EvaluationLabel("a", "MONSTER 473ML"),
        EvaluationLabel("b", "TODDY 370G"),
        EvaluationLabel("c", decorative=True),
        EvaluationLabel("d", "DETERGENTE YPE 500ML"),
    ]

    result = evaluate_decisions(decisions, labels)

    assert result.metrics.labeled_images == 4
    assert result.metrics.product_labels == 3
    assert result.metrics.product_predictions == 2
    assert result.metrics.correct_product_predictions == 1
    assert result.metrics.wrong_product_predictions == 1
    assert result.metrics.missing_product_predictions == 1
    assert result.metrics.association_precision == .5
    assert result.metrics.product_coverage == .666667
    assert result.metrics.decorative_accuracy == 1.0
    assert result.metrics.auto_accept_precision == 1.0


def test_wrong_high_confidence_auto_accept_is_explicit_failure():
    result = evaluate_decisions(
        [decision("x", "TODDY 750G", "accepted", .98)],
        [EvaluationLabel("x", "TODDY 370G")],
    )

    assert result.metrics.auto_accept_labeled == 1
    assert result.metrics.auto_accept_correct == 0
    assert result.metrics.auto_accept_wrong == 1
    assert result.metrics.auto_accept_precision == 0.0
    assert any(error["reason"] == "wrong-auto-accept" for error in result.errors)


def test_alias_equivalent_name_can_count_as_correct_but_measurement_change_cannot():
    equivalent = evaluate_decisions(
        [decision("a", "CAFÉ VASCONCELOS 500 G", "accepted", .96)],
        [EvaluationLabel("a", "CAFE VASCONCELOS 500G")],
    )
    different_measure = evaluate_decisions(
        [decision("b", "MONSTER 269ML", "accepted", .96)],
        [EvaluationLabel("b", "MONSTER 473ML")],
    )

    assert equivalent.metrics.auto_accept_precision == 1.0
    assert different_measure.metrics.auto_accept_precision == 0.0


def test_manual_sample_prioritizes_conflicts_then_adds_deterministic_random_rows():
    rows = [
        decision("hard-review", "A 500G", "review", .85, consensus=.50, products=3, alternatives=("B", "C")),
        decision("probable", "D 500G", "probable", .86, consensus=.75, products=2, alternatives=("E",)),
        decision("accepted-1", "F 500G", "accepted", .97),
        decision("accepted-2", "G 500G", "accepted", .97),
        decision("accepted-3", "H 500G", "accepted", .97),
    ]

    first = sample_for_manual_review(rows, hard_count=2, random_count=2, seed=123)
    second = sample_for_manual_review(rows, hard_count=2, random_count=2, seed=123)

    assert [row.image_sha256 for row in first[:2]] == ["hard-review", "probable"]
    assert [row.image_sha256 for row in first] == [row.image_sha256 for row in second]
    assert len(first) == 4
