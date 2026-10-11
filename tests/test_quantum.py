"""Check bit ordering, cost phases, size preservation, and live sampling."""
from importlib.util import find_spec
from itertools import product
import tempfile
from threading import Thread
import unittest
from unittest.mock import patch

from repackq.classical import exact_search
from repackq.classical.compare import compare, summarize
from repackq.classical.trials import synthetic_pool
from repackq.dashboard.service import DashboardService
from repackq.optimization import build_instance
from repackq.quantum.bitstrings import bits_to_qiskit_key, qiskit_key_to_bits, selected_indices
from repackq.quantum.circuits import build_circuit, cost_operator, objective_qubo, qubo_to_ising
from repackq.quantum.solver import PreparedRun, finish_qaoa, prepare_qaoa, run_qaoa, run_both


class CodecTest(unittest.TestCase):
    def test_all_small_states_round_trip(self):
        for n in range(1, 6):
            for bits in product((0, 1), repeat=n):
                self.assertEqual(qiskit_key_to_bits(bits_to_qiskit_key(bits), n), bits)
        self.assertEqual(selected_indices(qiskit_key_to_bits('0101', 4)), (0, 2))
        for key in ('2', 'x', '010'):
            with self.assertRaises(ValueError): qiskit_key_to_bits(key, 4)

    def test_classical_dashboard_works_without_qiskit(self):
        with tempfile.TemporaryDirectory() as root, patch('repackq.dashboard.quantum.capabilities',
                return_value={'available': False, 'status': 'not_installed', 'message': 'Install Qiskit'}):
            service = DashboardService(root)
            self.assertEqual(len(service.create_trial({})['results']), 4)
            with self.assertRaisesRegex(ValueError, 'Install Qiskit'):
                service.create_trial({'quantum': True})

    def test_failed_quantum_trials_remain_in_the_summary(self):
        report = compare(synthetic_pool()[0])
        report['quantum_runs'] = [{'algorithm': 'qaoa_penalty', 'status': 'no_feasible_sample'}]
        rows = summarize([{'comparisons': [report]}])
        row = next(r for r in rows if r['algorithm'] == 'qaoa_penalty')
        self.assertEqual(row['quantum_attempts'], 1)
        self.assertEqual(row['no_feasible_sample_trials'], 1)
        self.assertEqual(row['trials'], 0)
        self.assertIsNone(row['mean_objective_gap_abs'])


@unittest.skipUnless(find_spec('qiskit'), 'Install the quantum extra to test live circuits')
class QuantumTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problem = build_instance(synthetic_pool()[0][:4], 2)

    def test_qubo_ising_and_qiskit_energies_for_every_state(self):
        import numpy as np
        from qiskit.quantum_info import Statevector
        for algorithm in ('qaoa_penalty', 'qaoa_swap'):
            qubo = objective_qubo(self.problem, algorithm)
            z, zz, offset = qubo_to_ising(qubo)
            operator = cost_operator(qubo)
            for mask in range(16):
                bits = [(mask >> i) & 1 for i in range(4)]
                indices = selected_indices(bits)
                expected = self.problem.energy(indices) + qubo['cardinality_penalty'] * (len(indices) - 2) ** 2
                spins = [1 - 2 * b for b in bits]
                ising = offset + sum(v * spins[i] for i, v in enumerate(z)) + sum(v * spins[i] * spins[j] for i, j, v in zz)
                self.assertAlmostEqual(ising, expected)
                state = Statevector.from_int(mask, 16)
                self.assertAlmostEqual(float(state.expectation_value(operator).real), expected)
            self.assertTrue(np.isfinite(operator.coeffs).all())

    def test_cost_phase_and_named_angles(self):
        import numpy as np
        from qiskit.quantum_info import Statevector
        for algorithm in ('qaoa_penalty', 'qaoa_swap'):
            circuit, g, b, operator, qubo, scale = build_circuit(self.problem, algorithm, 1)
            initial = Statevector.from_instruction(circuit.assign_parameters({g[0]: 0, b[0]: 0})).data
            phased = Statevector.from_instruction(circuit.assign_parameters({g[0]: .7, b[0]: 0})).data
            energies = [self.problem.energy(tuple(i for i in range(4) if mask & (1 << i))) +
                        qubo['cardinality_penalty'] * (mask.bit_count() - 2) ** 2 for mask in range(16)]
            ideal = initial * np.exp(-.7j * np.array(energies) / scale)
            pivot = int(np.argmax(abs(initial)))
            np.testing.assert_allclose(phased, ideal * (phased[pivot] / ideal[pivot]), atol=1e-9)
            mixed = Statevector.from_instruction(circuit.assign_parameters({g[0]: .7, b[0]: .3}))
            base = Statevector(initial).expectation_value(operator).real
            self.assertGreater(abs(mixed.expectation_value(operator).real - base), 1e-7)

    def test_swap_preserves_count_at_multiple_depths_and_sizes(self):
        from qiskit.quantum_info import Statevector
        for k in (1, 2, 3, 4):
            problem = build_instance(self.problem.cells, k)
            circuit, g, b, *_ = build_circuit(problem, 'qaoa_swap', 2)
            parameters = {**{p: .73 for p in g}, **{p: -.41 for p in b}}
            probabilities = Statevector.from_instruction(circuit.assign_parameters(parameters)).probabilities()
            invalid = sum(p for mask, p in enumerate(probabilities) if mask.bit_count() != k)
            self.assertLess(invalid, 1e-12)

    def test_live_both_methods_grid_fallback_and_sample_recommendation(self):
        optimum = exact_search(self.problem)
        for algorithm in ('qaoa_penalty', 'qaoa_swap'):
            run = run_qaoa(self.problem, algorithm=algorithm, optimizer='grid', max_evaluations=112, seed=7)
            self.assertEqual(run['status'], 'computed')
            metadata = run['diagnostics']
            self.assertEqual(sum(metadata['counts'].values()), 1024)
            self.assertEqual(metadata['optimizer_evaluations'], 112)
            self.assertEqual(metadata['backend_jobs'], 1)
            self.assertAlmostEqual(run['selection'].objective_value, optimum.objective_value)
            if algorithm == 'qaoa_swap': self.assertEqual(metadata['feasible_fraction'], 1)
            repeat = run_qaoa(self.problem, algorithm=algorithm, optimizer='grid', max_evaluations=112, seed=7)
            self.assertEqual(metadata['counts'], repeat['diagnostics']['counts'])

    def test_no_feasible_sample_is_not_repaired(self):
        prepared = PreparedRun(self.problem, 'qaoa_penalty', None, {}, 0)
        run = finish_qaoa(prepared, {'0000': 100}, backend='test', shots=100)
        self.assertEqual(run['status'], 'no_feasible_sample')
        self.assertIsNone(run['selection'])
        self.assertEqual(run['diagnostics']['feasible_fraction'], 0)
        with self.assertRaisesRegex(ValueError, 'shot count'):
            finish_qaoa(prepared, {'0011': 99}, backend='test', shots=100)

    def test_tight_budget_and_invalid_quantum_settings(self):
        prepared = prepare_qaoa(self.problem, algorithm='qaoa_swap', max_evaluations=97)
        self.assertEqual(prepared.metadata['optimizer_evaluations'], 97)
        for settings in ({'shots': 0}, {'algorithm': 'fake'}, {'seed': -1},
                         {'max_evaluations': 95}, {'reps': 0}, {'optimizer': 'fake'}):
            with self.assertRaises(ValueError): run_qaoa(self.problem, **settings)

    def test_injected_backend_gets_one_sampling_job_and_correct_bit_order(self):
        from qiskit import QuantumCircuit
        class Backend:
            name = 'injected test simulator'
            calls = 0
            def run(self, circuit, shots):
                self.calls += 1
                class Job:
                    def result(self): return self
                    def get_counts(self): return {'0101': shots}
                return Job()
        backend = Backend()
        with patch('qiskit.transpile', side_effect=lambda circuit, *a, **kw: circuit):
            run = run_qaoa(self.problem, backend=backend, optimizer='grid', max_evaluations=96)
        self.assertEqual(backend.calls, 1)
        self.assertEqual(run['selection'].selected_indices, (0, 2))
        circuit = QuantumCircuit(4)
        circuit.x([0, 2]); circuit.measure_all()
        from qiskit.primitives import StatevectorSampler
        counts = StatevectorSampler(seed=2).run([circuit], shots=32).result()[0].data.meas.get_counts()
        self.assertEqual(counts, {'0101': 32})

    def test_comparison_serializes_quantum_diagnostics(self):
        import json
        report = compare(self.problem.cells, pack_size=2, quantum=True,
                         optimizer='grid', quantum_evaluations=96)
        self.assertEqual(len(report['results']), 6)
        self.assertEqual(len(report['quantum_runs']), 2)
        json.dumps(report, allow_nan=False)
        summary = summarize([{'comparisons': [report]}])
        self.assertEqual(len(summary), 6)

    def test_dashboard_future_boundary_and_live_results(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            service = DashboardService(root)
            trial = service.create_trial({'quantum': True})
            self.assertEqual(len(trial['results']), 6)
            self.assertEqual(trial['quantum']['executed_runs'], 2)
            self.assertNotIn('actual_capacity_ah', json.dumps(trial))
            self.assertEqual(service.export_problem(trial['trial_id'])['quantum_status'], 'computed')

    def test_repeated_dashboard_runs_from_different_request_threads(self):
        # request threads are short lived; native Qiskit work stays on one worker
        with tempfile.TemporaryDirectory() as root:
            service = DashboardService(root)
            outputs, errors = [], []
            def request():
                try: outputs.append(service.create_trial({'quantum': True}))
                except Exception as error: errors.append(error)
            def shorter_run(instance, **settings):
                return run_both(instance, max_evaluations=96, **settings)
            with patch('repackq.dashboard.quantum.run_both', side_effect=shorter_run):
                for _ in range(2):
                    thread = Thread(target=request)
                    thread.start(); thread.join(timeout=60)
                    self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(len(outputs), 2)
            for output in outputs:
                self.assertEqual(output['quantum']['executed_runs'], 2)
                self.assertEqual(len(output['results']), 6)


if __name__ == '__main__':
    unittest.main()
