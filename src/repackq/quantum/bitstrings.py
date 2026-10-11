"""Translate Qiskit's rightmost qubit into our candidate order."""


def qiskit_key_to_bits(key, n):
    key = key.replace(" ", "")
    if len(key) != n or any(bit not in "01" for bit in key):
        raise ValueError("Measurement must contain one binary digit per candidate")
    return tuple(int(bit) for bit in reversed(key))


def bits_to_qiskit_key(bits):
    bits = tuple(bits)
    if any(bit not in (0, 1) for bit in bits):
        raise ValueError("Bits must be zero or one")
    return "".join(str(int(bit)) for bit in reversed(bits))


def selected_indices(bits):
    return tuple(i for i, bit in enumerate(bits) if bit)
