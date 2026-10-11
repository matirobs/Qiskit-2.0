Goal: Given a data set containing general characteristics of cells (temperature, voltage, current, time, etc.) compare two quantum algorithms, a modified neural network, and a classical algorithm to see which is the most efficient and accurate to find the optimal combination of four cells based on their initial use and second use (recycling). 

Quantum Algorithm #1: QAOA Penalization Algorithm 
- Using the inputs of voltage, current, time, and temperature, the values were used to create linear weights to make a "score" for each of the cell cycles
- The first project our team submitted utilized SOH (State of Health), Capacity, and Resistance, so we used more general values which could viably be used to analyze any form of cell (not just our data set) to see if the algorithms could be efficiently expanded. Capacity was calculated by integrating the current over a given time cycle (and then the linear weight was found by comparing the original capacity from the new cells and the capacity from the second round of cells), and then resistance was found with ohm's law and comparing the values from the new and old cycles. We used the percent difference (fade) for those, and then found the standard deviation of temperature in the cycle to find any outliers in the temperature data (cells that were breaking down)
- These values were pushed through a linear weight for an "energy" rating to be imposed upon each cell
- Quadratic penalization: We find the combinations with the closest energy values --> it can return combinations of 2, 3, 5, etc.. so we penalize it for any combination that is not of four cells 
- We started off with a simplified algorithm. We took a different route from the other project our team submitted (though from the same algorithm, it was just approached differently given two different team members tackled it)-> finding a pair of cells out of four, and then expanded it to iterate for a greater group
- Used Rz, CNOT, then Rz --> entangles qubits, then only imposes shift if both qubits are selected (both 1), then unentangles

- Hamiltonian: We used the linear weights to impose a phase shift on the qubits.
- We then run interference to remove any cells with unfavorable amplitude
- Find output with least "energy" 

- qiskit indexes backwards, so we decoded by reversing the outputted bits



SWAP algo: 
2. Compare capacities with future projections --> makes a mismatching table that'll compare the present differences of 40% weight with the future degradation diff 
3. Cells that stay matched in the future will be favored
4. Quantum Part: Instead of starting with all of the cells, we narrow them down finding ones where 4 bits are 1 
5. Quantum algorithm: using CNOT to find mismatched cells to penalize them 
6. Use a XXPlusYY Gate to swap gates across qubit pairs --> gates let us keep the 4 cells 
7. Uses a hamiltonian angle shift like the previous algorithm until we find the combination with the lowest possible energy state through 1,024 shots 
8. Filters out the most common and top measured packs, while also sending out the predicted capacity. 


Neural Network: 
- We adapted a neural network that our teammate had priorly made in java (used for the sake of speed) and altered it to be used in python for the sake of expanding our SWAP and Quantum algorithms to be used for any combination of cells out of a sample of any size



CLASSICAL #1 
Setup & Cooling Schedule:initializes a random seed, sets up temperatures, and picks random starting cell packs across multiple restarts.

The Neighborhood Swap: swaps one cell currently in the pack with one outside it, keeping the group size (like the SWAP algo)

The Acceptance Rule (Metropolis): Always accepts better energy scores, but conditionally accepts worse scores based on a declining temperature probability to escape  traps.

Tracking & Output: Continuously updates and saves the global best pack found during the search, retrning full performance statistics at end


Classical #2
Multi-Start: Loops through each cell in the dataset as starting pt to for search multiple independent attempts.

Incremental Greedy Addition: it evaluates all remaining unchosen cells and appends the one with the lowest incremental cost relative to the current group.

Group Completion: Continues adding cells until each group reaches the target pack size (pack_size).

Best Group Selection: Ranks all generated groups, picks the one with the lowest global score, and returns performance stats.


Classical #3
Baseline Metrics Calculation: Computes core performance indicators like usable pack capacity, internal resistance spread, and statistical divergence (coefficient of variation).

Future Truth Integration: Optionally incorporates real-world observed outcomes so evaluates how accurately the pack performed after actual cycling.

Optimality & Regret Analysis: Compares the selection's score against a known optimum to calculate absolute performance gaps, percentage error, and normalized regret.


Classical 4: 

Result Builder (result): Validates the chosen indices, calculates the final objective energy score from the basic parameters found, measures the exact execution time in milliseconds, and bundles it with any extra solver metadata.

Deterministic Ranking (ranking): Evaluates the primary objective energy score first, then falls back on sorted cell identifiers to ensure reliable, reproducible tie-breaking across different runs.












Edits: In combination with the machine learning preprocessing and framework, we were able to further our algorithms to be able to find groups of 4, 8, or even 12 out of a provided set and predict which ones would still be efficiently running after up to 200 cycles of charging and discharging 

FINDINGS: 
- Runtimes for quantum #1: latest run 355 ms
- Cell swap: 3771 ms
- Classical with neural network preprocessing: .02 ms, .27ms, .93ms  for each version

- The swap algorithm was our least efficient. The QAOA penalization algorithm remains the most efficient. 

In the end: Classical seems to run significantly faster than our quantum algorithms, but each of the classical algorithms seemed to have more error as they generally outputted that 94% of the cells were within 10% of one another, which is incorrect. The quantum algorithms are consistent with one another and provide a more efficient overall. 
