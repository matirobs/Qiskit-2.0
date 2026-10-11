from __future__ import annotations

import itertools
import math
import unittest
from dataclasses import replace

from qiskit.providers.basic_provider import BasicSimulator
from qiskit.quantum_info import Statevector

from repackq.config import PV_TOU_MISSION
from repackq.models import CandidatePool, CellSnapshot
from repackq.optimization.objective import (
    IsingModel,
    build_optimization_instance,
    build_qubo,
    qubo_to_ising,
)
from repackq.optimization.solvers import exact_enumeration
from repackq.quantum.bitstrings import (
    bits_to_qiskit_key,
    qiskit_key_to_bits,
)
from repackq.quantum.engine import (
    _energy_for_params,
    optimize_qaoa_parameters,
    run_qaoa,
    QAOAParams,
)
from repackq.quantum.qiskit_compat import (
    build_cost_operator,
    build_qaoa_ansatz,
    run_bit_order_sanity,
)


def make_pool(n: int = 4, k: int = 2) -> CandidatePool:
    mission = replace(PV_TOU_MISSION, pack_size_k=k)
    snapshots = tuple(
        CellSnapshot(
            cell_id=f"TOY-{index}",
            protocol_id="toy",
            cycle_index=20,
            capacity_ah=1.20 + index * 0.04,
            nominal_capacity_ah=2.4,
            soh=(1.20 + index * 0.04) / 2.4,
            internal_resistance_ohm=0.07 + index * 0.005,
            temperature_c=None,
            recent_capacity_slope_ah_per_cycle=-0.0001 * (index + 1),
            predicted_capacity_ah=1.18 + index * 0.03,
            prediction_uncertainty_ah=0.002 + index * 0.0004,
            horizon_cycles=mission.horizon_cycles,
            source_dataset="synthetic_qaoa_test",
        )
        for index in range(n)
    )
    return CandidatePool(
        pool_id=f"toy-{n}-{k}",
        decision_cycle=20,
        horizon_cycles=mission.horizon_cycles,
        candidate_ids=tuple(item.cell_id for item in snapshots),
        snapshots=snapshots,
        future_truth=None,
        seed=7,
    )


class BitstringCodecTests(unittest.TestCase):
    def test_all_keys_round_trip_through_five_bits(self) -> None:
        for n in range(1, 6):
            for bits in itertools.product((0, 1), repeat=n):
                key = bits_to_qiskit_key(bits)
                self.assertEqual(qiskit_key_to_bits(key, n), bits)
                self.assertEqual(bits_to_qiskit_key(qiskit_key_to_bits(key, n)), key)

    def test_known_qiskit_state_decodes_q0_and_q2(self) -> None:
        report = run_bit_order_sanity(backend=BasicSimulator(), shots=16)
        self.assertTrue(report["ok"])
        self.assertEqual(report["counts"], {"0101": 16})
        self.assertEqual(report["decoded_qubit_bits"], [1, 0, 1, 0])
        self.assertEqual(report["selected_indices"], [0, 2])


class QAOAEngineTests(unittest.TestCase):
    def test_cost_operator_diagonal_matches_ising_evaluator_for_every_state(self) -> None:
        instance = build_optimization_instance(make_pool(5, 2), mission=replace(PV_TOU_MISSION, pack_size_k=2))
        qubo = build_qubo(instance)
        ising = qubo_to_ising(qubo)
        operator = build_cost_operator(ising)
        for bits in itertools.product((0, 1), repeat=instance.n):
            state = Statevector.from_label(bits_to_qiskit_key(bits))
            actual = complex(state.expectation_value(operator))
            self.assertAlmostEqual(actual.real, ising.energy(bits), places=9)
            self.assertAlmostEqual(actual.imag, 0.0, places=9)

    def test_parameterized_p1_ansatz_binds_gamma_and_beta_by_name(self) -> None:
        operator = build_cost_operator(IsingModel(h=(0.7, -0.2), couplings={(0, 1): 0.35}, offset=0.1))
        ansatz = build_qaoa_ansatz(operator, reps=1)
        baseline = _energy_for_params(ansatz, operator, QAOAParams((0.4,), (0.2,)))
        gamma_changed = _energy_for_params(ansatz, operator, QAOAParams((0.8,), (0.2,)))
        beta_changed = _energy_for_params(ansatz, operator, QAOAParams((0.4,), (0.6,)))
        self.assertNotAlmostEqual(baseline, gamma_changed, places=7)
        self.assertNotAlmostEqual(baseline, beta_changed, places=7)

    def test_parameterized_ansatz_exposes_each_layer_for_p2(self) -> None:
        operator = build_cost_operator(IsingModel(h=(0.7, -0.2), couplings={(0, 1): 0.35}, offset=0.1))
        ansatz = build_qaoa_ansatz(operator, reps=2)
        state = _energy_for_params(
            ansatz,
            operator,
            QAOAParams((0.3, 0.8), (0.2, 0.5)),
        )
        self.assertTrue(math.isfinite(state))
        self.assertEqual(ansatz.num_parameters, 4)

    def test_portable_grid_optimizer_runs_with_explicit_fallback(self) -> None:
        operator = build_cost_operator(IsingModel(h=(0.7, -0.2), couplings={(0, 1): 0.35}, offset=0.1))
        ansatz = build_qaoa_ansatz(operator, reps=1)
        report = optimize_qaoa_parameters(
            ansatz,
            operator,
            reps=1,
            optimizer_mode="grid",
            max_evaluations=121,
        )
        self.assertEqual(report.method, "coarse_to_fine_grid")
        self.assertGreaterEqual(report.evaluations, 96)
        self.assertLessEqual(report.evaluations, 121)
        self.assertLessEqual(report.expected_energy, report.initial_expected_energy + 1e-10)

    def test_tiny_toy_qubo_runs_end_to_end_and_reports_exact_optimum(self) -> None:
        pool = make_pool(2, 1)
        mission = replace(PV_TOU_MISSION, pack_size_k=1)
        instance = build_optimization_instance(pool, mission=mission)
        exact = exact_enumeration(instance)
        exact_bits = [
            tuple(1 if index in indices else 0 for index in range(instance.n))
            for indices in exact.metadata["tied_optima"]
        ]
        result = run_qaoa(
            instance,
            shots=2048,
            simulator_seed=9,
            optimizer_mode="grid",
            max_evaluations=121,
            exact_optimal_bitstrings=exact_bits,
        )
        self.assertTrue(result.feasible, result.status_message)
        self.assertEqual(result.backend_jobs_submitted, 1)
        self.assertEqual(result.shots_observed, 2048)
        self.assertIsNotNone(result.recommended_result)
        self.assertIsNotNone(result.optimum_probability_mass)
        self.assertGreater(result.feasible_probability_mass, 0.0)
        self.assertLessEqual(result.best_feasible_optimality_gap or 0.0, 1e-9)

    def test_no_feasible_sample_is_explicit_and_backend_is_called_once(self) -> None:
        class FixedJob:
            def result(self):
                return self

            def get_counts(self, circuit=None):
                return {"0000": 128}

        class InfeasibleBackend(BasicSimulator):
            def __init__(self):
                super().__init__()
                self.submissions = 0

            def run(self, run_input, **run_options):
                self.submissions += 1
                return FixedJob()

        pool = make_pool(4, 2)
        instance = build_optimization_instance(pool, mission=replace(PV_TOU_MISSION, pack_size_k=2))
        backend = InfeasibleBackend()
        result = run_qaoa(
            instance,
            backend,
            shots=128,
            optimizer_mode="grid",
            max_evaluations=121,
        )
        self.assertFalse(result.feasible)
        self.assertEqual(result.status_message, "No feasible K-cell sample observed.")
        self.assertIsNone(result.best_feasible_sample)
        self.assertIsNone(result.recommended_result)
        self.assertEqual(result.cardinality_violation_sample.cardinality, 0)
        self.assertEqual(backend.submissions, 1)
        self.assertEqual(result.backend_jobs_submitted, 1)


if __name__ == "__main__":
    unittest.main()
