import unittest

from repackq.quantum.qiskit_compat import (
    decode_qiskit_bitstring,
    get_capabilities,
    run_smoke_test,
)


class QiskitCompatibilityTests(unittest.TestCase):
    def test_import_and_capabilities(self):
        capabilities = get_capabilities()
        self.assertTrue(capabilities["qiskit_available"])
        self.assertTrue(capabilities["numpy_available"])
        self.assertEqual(capabilities["local_backend"], "qiskit.providers.basic_provider.BasicSimulator")

    def test_deterministic_local_smoke(self):
        report = run_smoke_test(shots=16)
        self.assertTrue(report["ok"])
        self.assertEqual(report["counts"], {"01": 16})
        self.assertEqual(report["decoded_qubit_bits"], [1, 0])

    def test_backend_can_be_injected(self):
        from qiskit.providers.basic_provider import BasicSimulator

        report = run_smoke_test(backend=BasicSimulator(), shots=8)
        self.assertEqual(report["backend"], "basic_simulator")
        self.assertEqual(report["counts"], {"01": 8})

    def test_count_decoder_uses_qiskit_display_order(self):
        self.assertEqual(decode_qiskit_bitstring("01", 2), [1, 0])
        self.assertEqual(decode_qiskit_bitstring("0 101", 4), [1, 0, 1, 0])
        with self.assertRaises(ValueError):
            decode_qiskit_bitstring("0x1", 2)


if __name__ == "__main__":
    unittest.main()
