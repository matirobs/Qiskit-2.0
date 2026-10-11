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



1. Data Setup & Cost Calculation (mismatch)The Goal: Choose the best 4 cells out of 8 to build a battery pack that stays balanced and healthy over time.Capacity Analysis: Compares current capacities (capacity_now) and future projections (capacity_future after 200 cycles).The Penalty Formula: Computes an $8 \times 8$ mismatch table combining present differences (40% weight) and future degradation differences (60% weight) so that cells staying matched in the future are heavily favored.2. Quantum Initialization (StatePreparation)Smart Superposition: Instead of guessing randomly, you use StatePreparation to create a starting quantum state containing only the valid combinations (all 8-bit patterns where exactly four bits are 1).Constraint Enforcement: This ensures the quantum computer never wastes time evaluating invalid pack sizes (like picking 3 or 5 cells).3. The QAOA Layers (Cost & Mixers)Cost Layer (cost_layer): Uses controlled phase gates (cp) to penalize mismatched cell pairs. If two paired cells have a high degradation gap, they receive a heavier phase penalty.Swap Mixer (swap_mixer): Uses specialized XXPlusYYGate swap gates across all qubit pairs. This lets the quantum state explore different combinations while strictly keeping the rule that exactly 4 cells remain selected.4. Classical Optimization (COBYLA)Parameter Tuning: The quantum circuit relies on variational angles called gammas and betas.Finding the Sweet Spot: You first do a rough grid search, then hand the starting point over to SciPy's COBYLA optimizer to iteratively fine-tune the angles until the circuit yields the lowest possible average pack score.5. Measurement and Final ResultsSampling the Results: The optimized circuit is run for 1,024 shots using StatevectorSampler.Decoding: The script reverses the measurement bitstrings (reversed(key)) to map qubit positions back to cell names (e.g., C0, C1, C2, C3).The Winner: It filters out the top-measured packs, confirms the quantum computer matched the classical brute-force best answer, and prints out the final usable capacity and future spread of your winning battery pack!

SWAP algo: 
2. Compare capacities with future projections --> makes a mismatching table that'll compare the present differences of 40% weight with the future degradation diff 
3. Cells that stay matched in the future will be favored
4. Quantum Part: Instead of starting with all of the cells, we narrow them down finding ones where 4 bits are 1 
5. Quantum algorithm: using CNOT to find mismatched cells to penalize them 














Edits: In combination with the machine learning preprocessing and framework, we were able to further our algorithms to be able to find groups of 4, 8, or even 12 out of a provided set and predict which ones would still be efficiently running after up to 200 cycles of charging and discharging 

FINDINGS: 
- Runtimes for quantum #1: latest run 355 ms
- Cell swap: 3771 ms
- Classical with neural network preprocessing: .02 ms, .27ms, .93ms  for each version

- The swap algorithm was our least efficient. The QAOA penalization algorithm remains the most efficient. 

In the end: Classical seems to run significantly faster than our quantum algorithms, but each of the classical algorithms seemed to have more error as they generally outputted that 94% of the cells were within 10% of one another, which is incorrect. The quantum algorithms are consistent with one another and provide a more efficient overall. 
