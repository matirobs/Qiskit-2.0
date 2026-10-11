"""One canonical codec between Qiskit count keys and candidate bit vectors."""

from __future__ import annotations

from typing import Sequence


def qiskit_key_to_bits(key: str, n: int) -> tuple[int, ...]:
    """Decode Qiskit's displayed key into ``bits[i] == qubit/candidate i``.

    Qiskit renders the highest-index classical bit on the left. Whitespace is
    removed so keys containing register separators are also accepted.
    """

    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError("n must be a nonnegative integer")
    compact = "".join(str(key).split())
    if len(compact) != n:
        raise ValueError(f"Expected a {n}-bit Qiskit key, got {key!r}.")
    if any(bit not in "01" for bit in compact):
        raise ValueError(f"Expected a binary Qiskit key, got {key!r}.")
    return tuple(int(bit) for bit in reversed(compact))


def bits_to_qiskit_key(bits: Sequence[int]) -> str:
    """Encode candidate-index-order bits as a Qiskit display-order key."""

    normalized: list[int] = []
    for bit in bits:
        if isinstance(bit, bool):
            bit = int(bit)
        if not isinstance(bit, int) or bit not in (0, 1):
            raise ValueError("bit vector entries must be binary integers")
        normalized.append(bit)
    return "".join(str(bit) for bit in reversed(normalized))


def selected_indices(bits: Sequence[int]) -> list[int]:
    """Return selected candidate indices from a canonical bit vector."""

    selected: list[int] = []
    for index, bit in enumerate(bits):
        if isinstance(bit, bool):
            bit = int(bit)
        if not isinstance(bit, int) or bit not in (0, 1):
            raise ValueError("bit vector entries must be binary integers")
        if bit:
            selected.append(index)
    return selected
