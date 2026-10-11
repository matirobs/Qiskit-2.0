"""Locked project defaults and explicit mission assumptions."""

from __future__ import annotations

from repackq.models import MissionProfile


PV_TOU_MISSION = MissionProfile(
    id="pv_tou",
    label="Residential PV + time-of-use storage",
    horizon_cycles=200,
    pack_size_k=4,
    minimum_soh=0.50,
    current_capacity_weight=0.30,
    resistance_weight=0.20,
    future_capacity_weight=0.35,
    health_reward_weight=0.10,
    uncertainty_weight=0.05,
    temperature_weight=0.00,
    description=(
        "MVP stationary-storage assumption. The 200-cycle horizon and objective "
        "weights are explicit modeling choices, not universal physical constants. "
        "No household load trace or electrochemical response is simulated."
    ),
)

# This is a visible placeholder only. It reuses the MVP estimator and weights;
# no frequency-response-specific degradation model has been parameterized.
FREQUENCY_RESPONSE_MISSION = MissionProfile(
    id="frequency_response",
    label="Frequency response (experimental placeholder)",
    horizon_cycles=200,
    pack_size_k=4,
    minimum_soh=0.50,
    current_capacity_weight=0.30,
    resistance_weight=0.20,
    future_capacity_weight=0.35,
    health_reward_weight=0.10,
    uncertainty_weight=0.05,
    temperature_weight=0.00,
    description=(
        "Experimental placeholder. This profile currently uses the same simple "
        "trajectory estimator and weights as pv_tou; no frequency-response "
        "duty-specific degradation model is implemented."
    ),
    experimental=True,
)

MISSION_PROFILES: dict[str, MissionProfile] = {
    PV_TOU_MISSION.id: PV_TOU_MISSION,
    FREQUENCY_RESPONSE_MISSION.id: FREQUENCY_RESPONSE_MISSION,
}
DEFAULT_MISSION_ID = PV_TOU_MISSION.id


def get_mission_profile(mission_id: str = DEFAULT_MISSION_ID) -> MissionProfile:
    """Get a named, immutable mission profile or raise a descriptive error."""

    try:
        return MISSION_PROFILES[mission_id]
    except KeyError as error:
        choices = ", ".join(sorted(MISSION_PROFILES))
        raise ValueError(f"unknown mission {mission_id!r}; choose one of: {choices}") from error
