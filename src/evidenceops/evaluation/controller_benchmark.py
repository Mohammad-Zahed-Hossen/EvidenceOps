from pydantic import BaseModel, ConfigDict

from evidenceops.domain.enums import Action


class ControllerDiagnosticReport(BaseModel):
    """Diagnostic comparison of a controller against oracle supervision."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    controller_name: str
    total_decisions: int
    accuracy: float
    macro_f1: float
    action_metrics: dict[str, dict[str, float]]
    confusion_matrix: dict[str, dict[str, int]]


def compute_controller_diagnostics(
    predicted: list[Action],
    ground_truth: list[Action],
    controller_name: str,
) -> ControllerDiagnosticReport:
    """Compute multi-class classification metrics comparing predicted actions to ground truth."""
    if len(predicted) != len(ground_truth):
        raise ValueError(
            f"Length mismatch: {len(predicted)} predicted vs {len(ground_truth)} ground truth"
        )

    total = len(predicted)
    if total == 0:
        return ControllerDiagnosticReport(
            controller_name=controller_name,
            total_decisions=0,
            accuracy=0.0,
            macro_f1=0.0,
            action_metrics={},
            confusion_matrix={},
        )

    correct_count = sum(1 for p, g in zip(predicted, ground_truth, strict=True) if p == g)
    accuracy = correct_count / total

    # Unique classes present in either ground truth or predictions
    all_classes = sorted({a.value for a in ground_truth} | {a.value for a in predicted})

    # Confusion matrix: row = ground truth, column = predicted
    matrix: dict[str, dict[str, int]] = {c1: {c2: 0 for c2 in all_classes} for c1 in all_classes}
    for p, g in zip(predicted, ground_truth, strict=True):
        matrix[g.value][p.value] += 1

    action_metrics: dict[str, dict[str, float]] = {}
    f1_list: list[float] = []

    for c in all_classes:
        tp = matrix[c][c]
        fp = sum(matrix[other][c] for other in all_classes if other != c)
        fn = sum(matrix[c][other] for other in all_classes if other != c)
        support = sum(matrix[c].values())

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        action_metrics[c] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": float(support),
        }
        f1_list.append(f1)

    macro_f1 = sum(f1_list) / len(f1_list) if f1_list else 0.0

    return ControllerDiagnosticReport(
        controller_name=controller_name,
        total_decisions=total,
        accuracy=accuracy,
        macro_f1=macro_f1,
        action_metrics=action_metrics,
        confusion_matrix=matrix,
    )
