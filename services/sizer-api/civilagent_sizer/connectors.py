"""Catalogue-driven Simpson Strong-Tie connector selection."""

from civilagent_sizer.catalogue.loader import load_yaml
from civilagent_sizer.trace.models import ConnectionTrace

CONNECTOR_NOT_FOUND = (
    "no catalogued connector adequate for this load - engineering connection design required"
)
CONNECTOR_VERIFICATION_WARNING = (
    "Connector allowable loads require verification against current Simpson Strong-Tie "
    "catalogue before stamped use."
)


def connector_warning(utilisation: float) -> str | None:
    """Return the same utilization warning language used for member checks."""

    if utilisation > 0.95:
        return "Near-capacity - strongly consider upsizing."
    if utilisation > 0.80:
        return "High utilisation - verify adequacy of safety margin."
    return None


def select_joist_hanger(
    *,
    joist_nominal: str,
    demand_lb: float,
    interface: str,
    category: str = "face_mount_joist_hanger",
) -> ConnectionTrace:
    """Select a joist hanger from Simpson catalogue values supplied in YAML."""

    candidates = [
        item
        for item in load_yaml("connectors/simpson_strong_tie.yaml")["connectors"]
        if item["category"] == category
        and joist_nominal in item.get("applicable_nominal_depths", [])
    ]
    return _select_by_allowable(candidates, demand_lb, interface, "allowable_download_lb")


def select_post_base(
    *,
    post_nominal: str,
    demand_lb: float,
    interface: str,
) -> ConnectionTrace:
    """Select a post base for axial gravity load from Simpson catalogue YAML."""

    candidates = [
        item
        for item in load_yaml("connectors/simpson_strong_tie.yaml")["connectors"]
        if item["category"] == "post_base" and post_nominal in item.get("applicable_post_sizes", [])
    ]
    return _select_by_allowable(candidates, demand_lb, interface, "allowable_download_lb")


def _select_by_allowable(
    candidates: list[dict],
    demand_lb: float,
    interface: str,
    allowable_key: str,
) -> ConnectionTrace:
    ordered = sorted(candidates, key=lambda item: _allowable_value(item, allowable_key))
    for candidate in ordered:
        allowable = _allowable_value(candidate, allowable_key)
        if demand_lb <= allowable:
            utilisation = demand_lb / allowable
            utilisation_warning = connector_warning(utilisation)
            warning = None
            if candidate.get("confidence") != "very_high":
                warning = CONNECTOR_VERIFICATION_WARNING
            if utilisation_warning:
                warning = (
                    f"{utilisation_warning} {warning}"
                    if warning
                    else utilisation_warning
                )
            download_basis = candidate.get("allowable_download_basis", allowable_key)
            return ConnectionTrace(
                interface=interface,
                demand_lb=demand_lb,
                product=candidate.get("model", candidate.get("product", "")),
                allowable_load_lb=allowable,
                utilisation=utilisation,
                source=candidate["source"],
                note=(
                    f"Catalogue download basis: {download_basis}; "
                    f"confidence={candidate['confidence']}. {candidate['notes']}"
                ),
                warning=warning,
            )
    raise ValueError(CONNECTOR_NOT_FOUND)


def _allowable_value(candidate: dict, preferred_key: str) -> float:
    if preferred_key in candidate:
        return float(candidate[preferred_key])
    if preferred_key == "allowable_download_lb":
        return float(candidate.get("allowable_down_load_lb", candidate.get("allowable_load_lb")))
    return float(candidate[preferred_key])
