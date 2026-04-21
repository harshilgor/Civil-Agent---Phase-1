"""Phase 3 orchestrator — runs all engines in dependency order."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from .assumptions import AssumptionBuilder
from .confidence import compute_overall_confidence, confidence_level
from .engines.combos import compute_member_demands, evaluate_combinations
from .engines.dead_load import compute_dead_loads
from .engines.live_load import compute_live_loads
from .engines.seismic import compute_seismic_loads
from .engines.story_loads import compute_story_loads
from .engines.tributary import compute_tributary_areas
from .engines.wind import compute_wind_loads
from .models.enums import ConfidenceLevel
from .models.inputs import Phase3Input
from .models.outputs import AssumptionRegister, DesignLoadModel, Phase3Output, Phase3Warning
from .overrides import inject_overrides
from .warnings import make_warning


class Phase3Service:
    """High-level entry point that assembles a :class:`Phase3Output`.

    Execution order (strict):

        1.  Validate inputs (building code).
        2.  Dead loads.
        3.  Live loads (unreduced, one per occupancy).
        4.  Tributary areas (Voronoi + Shapely).
        5.  Story load aggregation.
        6.  Wind loads (simplified directional procedure).
        7.  Seismic loads (ELF).
        8.  Member demands + representative load combinations.
        9.  Apply overrides (by re-running with overrides injected).
        10. Confidence scoring.
        11. Assemble the :class:`Phase3Output`.
    """

    def run(self, phase3_input: Phase3Input) -> Phase3Output:
        """Execute Phase 3 for a single building."""

        start = time.perf_counter()
        warnings: list[Phase3Warning] = []

        # --- Step 1: Validate ----------------------------------------------------
        if phase3_input.building_code != "ASCE 7-22":
            warnings.append(
                make_warning(
                    "P3W008",
                    message_override=(
                        f"Building code '{phase3_input.building_code}' is not supported in V1."
                    ),
                )
            )
            empty_builder = AssumptionBuilder()
            register = empty_builder.build_register()
            score = compute_overall_confidence(
                phase3_input.building_graph,
                phase3_input.structural_design_graph,
                register,
                warnings,
            )
            return Phase3Output(
                status="failed",
                design_load_model=None,
                assumption_register=register,
                warnings=warnings,
                overall_confidence=score,
                overall_confidence_level=confidence_level(score),
                processing_time_seconds=time.perf_counter() - start,
                computed_at=datetime.now(timezone.utc),
            )

        builder = AssumptionBuilder()

        try:
            design_model, eng_warnings = self._run_engines(phase3_input, builder)
            warnings.extend(eng_warnings)
        except Exception as exc:  # fail loudly per spec
            register = builder.build_register()
            return Phase3Output(
                status="failed",
                design_load_model=None,
                assumption_register=register,
                warnings=warnings
                + [
                    make_warning(
                        "P3W008",
                        message_override=f"Phase 3 engine failure: {exc!s}",
                    )
                ],
                overall_confidence=0.10,
                overall_confidence_level=ConfidenceLevel.LOW,
                processing_time_seconds=time.perf_counter() - start,
                computed_at=datetime.now(timezone.utc),
            )

        # --- Step 9: Apply overrides --------------------------------------------
        if phase3_input.overrides:
            try:
                builder.apply_overrides(phase3_input.overrides)
            except ValueError as exc:
                warnings.append(
                    make_warning(
                        "P3W008",
                        message_override=f"Override application failed: {exc!s}",
                    )
                )

        register = builder.build_register()

        # --- Step 10: Confidence -----------------------------------------------
        score = compute_overall_confidence(
            phase3_input.building_graph,
            phase3_input.structural_design_graph,
            register,
            warnings,
        )
        level = confidence_level(score)

        design_model = design_model.model_copy(
            update={
                "overall_confidence": score,
                "overall_confidence_level": level,
            }
        )

        status = "success"
        if any(w.level.value == "error" for w in warnings):
            status = "partial"

        return Phase3Output(
            status=status,
            design_load_model=design_model,
            assumption_register=register,
            warnings=warnings,
            overall_confidence=score,
            overall_confidence_level=level,
            processing_time_seconds=time.perf_counter() - start,
            computed_at=datetime.now(timezone.utc),
        )

    def rerun_with_overrides(
        self, phase3_input: Phase3Input, overrides: list
    ) -> Phase3Output:
        """Re-execute Phase 3 with additional overrides merged in."""

        merged = inject_overrides(phase3_input, overrides)
        return self.run(merged)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _run_engines(
        self,
        phase3_input: Phase3Input,
        builder: AssumptionBuilder,
    ) -> tuple[DesignLoadModel, list[Phase3Warning]]:
        """Run engines 2–8 and assemble the :class:`DesignLoadModel`."""

        bg = phase3_input.building_graph
        sg = phase3_input.structural_design_graph
        warnings: list[Phase3Warning] = []

        # 2. Dead
        dead = compute_dead_loads(bg, phase3_input.material_family, builder)

        # 3. Live (unreduced)
        live_per_occ = compute_live_loads(bg, builder)

        # 4. Tributary
        tribs, trib_warnings = compute_tributary_areas(bg, sg, builder)
        warnings.extend(trib_warnings)

        # 5. Story loads
        story_loads = compute_story_loads(bg, dead, live_per_occ, builder)

        # 6. Wind
        wind, wind_warnings = compute_wind_loads(
            bg,
            basic_wind_speed_m_per_s=phase3_input.basic_wind_speed_m_per_s,
            exposure_category=phase3_input.exposure_category,
            risk_category=phase3_input.risk_category,
            assumption_builder=builder,
        )
        warnings.extend(wind_warnings)

        # 7. Seismic
        seismic, seis_warnings = compute_seismic_loads(
            bg,
            sg,
            story_loads,
            material_family=phase3_input.material_family,
            risk_category=phase3_input.risk_category,
            site_class=phase3_input.site_class,
            Ss=phase3_input.Ss,
            S1=phase3_input.S1,
            assumption_builder=builder,
        )
        warnings.extend(seis_warnings)

        # 8. Member demands + representative 7-combination set
        demands, combos = compute_member_demands(
            tributary_areas=tribs,
            story_loads=story_loads,
            dead_loads=dead,
            live_loads=live_per_occ,
            wind_loads=wind,
            seismic_loads=seismic,
            building_graph=bg,
            assumption_builder=builder,
        )

        if not combos:
            combos = evaluate_combinations(
                D=sum(sl.total_dead_kN for sl in story_loads),
                L=sum(sl.total_live_kN for sl in story_loads),
                Lr=0.0,
                W=wind.wind_base_shear_kN,
                E=seismic.V,
                assumption_ids=["load_combination_standard"],
            )

        register_snapshot: AssumptionRegister = builder.build_register()
        score = compute_overall_confidence(bg, sg, register_snapshot, warnings)

        design_model = DesignLoadModel(
            building_graph_id=str(bg.get("project", {}).get("name", "unknown")),
            structural_graph_id=str(sg.get("building_graph_id", "unknown")),
            dead_loads=dead,
            live_loads=live_per_occ,
            tributary_areas=tribs,
            story_loads=story_loads,
            wind_loads=wind,
            seismic_loads=seismic,
            load_combinations=combos,
            member_demands=demands,
            overall_confidence=score,
            overall_confidence_level=confidence_level(score),
        )

        return design_model, warnings
