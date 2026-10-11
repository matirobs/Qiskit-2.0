package org.repackq;

import java.io.BufferedInputStream;
import java.io.DataInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

/*
 * Train and run the network from Python. Python prepares features and cell splits;
 * Java updates weights and selects validation checkpoints.
 * Matrices use two big-endian 32-bit dimensions followed by row-major 64-bit doubles.
 */
public final class BatteryModelCli {
    private BatteryModelCli() { }

    // Read a matrix and reject invalid dimensions, incomplete files, or non-finite values.
    private static double[][] readMatrix(String filename) throws Exception {
        long bytes = Files.size(Path.of(filename));
        try (DataInputStream input = new DataInputStream(
                new BufferedInputStream(Files.newInputStream(Path.of(filename))))) {
            int rows = input.readInt();
            int columns = input.readInt();
            if (rows < 1 || columns < 1 || rows > 1_000_000 || columns > 100_000
                    || bytes != 8L + 8L * rows * columns)
                throw new IllegalArgumentException("Invalid matrix dimensions/length: " + filename);
            double[][] values = new double[rows][columns];
            for (double[] row : values)
                for (int column = 0; column < columns; column++) {
                    row[column] = input.readDouble();
                    if (!Double.isFinite(row[column]))
                        throw new IllegalArgumentException("Non-finite matrix value");
                }
            return values;
        }
    }
    // Measure mean squared error without updating weights.
    private static double validationError(Network network, double[][] x, double[][] y) {
        if (x.length != y.length)
            throw new IllegalArgumentException("Validation row counts differ");
        double sum = 0;
        int count = 0;
        for (int row = 0; row < x.length; row++) {
            double[] predictions = network.predict(x[row]);
            if (predictions.length != y[row].length)
                throw new IllegalArgumentException("Validation output width differs");
            for (int column = 0; column < predictions.length; column++) {
                double difference = predictions[column] - y[row][column];
                sum += difference * difference;
                count++;
            }
        }
        return sum / count;
    }

    /*
     * Count predictions within 5% and 10% of actual validation capacity.
     * Reference columns are actual capacity, current capacity, and output baseline.
     */
    private static double[] successScore(Network network, double[][] x, double[][] references,
                                         double scale, double offset) {
        if (references.length != x.length) throw new IllegalArgumentException("Reference row count differs");
        double within5 = 0, within10 = 0, relativeSum = 0;
        for (int row = 0; row < x.length; row++) {
            if (references[row].length != 3 || references[row][0] <= 0 || references[row][1] <= 0)
                throw new IllegalArgumentException("Expected positive actual/current capacities and baseline");
            double capacity = references[row][2] + scale * (network.predict(x[row])[0] - offset);
            capacity = Math.max(0, Math.min(references[row][1], capacity));
            double relative = Math.abs(capacity - references[row][0]) / references[row][0];
            if (relative <= .05) within5++;
            if (relative <= .10) within10++;
            relativeSum += relative;
        }
        return new double[]{within5 / x.length, within10 / x.length, -relativeSum / x.length};
    }

    // Compare within-5%, then within-10%, then average relative error.
    private static boolean scoreImproved(double[] candidate, double[] best) {
        if (best == null) return true;
        for (int index = 0; index < candidate.length; index++) {
            if (candidate[index] > best[index] + 1e-12) return true;
            if (candidate[index] < best[index] - 1e-12) return false;
        }
        return false;
    }

    /*
     * Dispatch predict, fixed-budget fit, or validation-selected train.
     * Command arguments and control-file options are in docs/guides/training.md.
     */
    public static void main(String[] args) throws Exception {
        if (args.length != 3 && args.length != 4 && args.length != 7)
            throw new IllegalArgumentException("Expected predict (3 args), fit (4 args), or train (7 args)");
        Network network = new Network();
        network.setConfigParams(new String[]{args[1]});
        if (args[0].equals("fit") && args.length == 4) {
            // Use the pass count chosen by cross-validation; no early stopping here.
            network.setRandomSeed(Long.parseLong(args[2]));
            network.allocateMemory();
            network.populateArrays();
            Parser settings = new Parser(); settings.parseControlFile(args[1]);
            String weightFile = settings.findValOrDefault("caseWeightsFile", String.class, "unused");
            if (!weightFile.equals("unused")) {
                double[][] values = readMatrix(weightFile);
                double[] lossWeights = new double[values.length];
                for (int row=0; row<values.length; row++) {
                    if (values[row].length != 1) throw new IllegalArgumentException("Loss weights need one column");
                    lossWeights[row] = values[row][0];
                }
                network.setTrainingWeights(lossWeights);
            }
            int blocks = Integer.parseInt(args[3]);
            if (blocks < 1) throw new IllegalArgumentException("Positive fit budget required");
            long started = System.nanoTime();
            for (int block=1; block<=blocks; block++) {
                network.train();
                System.out.printf(java.util.Locale.ROOT,"fit_block=%d elapsed_seconds=%.3f%n",
                    block,(System.nanoTime()-started)/1e9);
            }
            network.saveWeights();
        } else if (args[0].equals("train") && args.length == 7) {
            network.setRandomSeed(Long.parseLong(args[2]));
            network.allocateMemory();
            network.populateArrays();
            double[][] x = readMatrix(args[3]);
            double[][] y = readMatrix(args[4]);
            Parser settings = new Parser();
            settings.parseControlFile(args[1]);
            String trainingWeightFile = settings.findValOrDefault("caseWeightsFile", String.class, "unused");
            if (!trainingWeightFile.equals("unused")) {
                double[][] values = readMatrix(trainingWeightFile);
                double[] lossWeights = new double[values.length];
                for (int row = 0; row < values.length; row++) {
                    if (values[row].length != 1) throw new IllegalArgumentException("Loss weights need one column");
                    lossWeights[row] = values[row][0];
                }
                network.setTrainingWeights(lossWeights);
            }
            String metric = settings.findValOrDefault("selectionMetric", String.class, "mse");
            if (!metric.equals("mse") && !metric.equals("success5"))
                throw new IllegalArgumentException("Unknown selection metric");
            double[][] references = metric.equals("success5")
                ? readMatrix(settings.findVal("validationReferenceFile", String.class)) : null;
            double scale = settings.findValOrDefault("outputScaleAh", Double.class, 3.0);
            double offset = settings.findValOrDefault("outputOffset", Double.class, 0.0);
            int blocks = Integer.parseInt(args[5]);
            int patience = Integer.parseInt(args[6]);
            if (blocks < 1 || patience < 1)
                throw new IllegalArgumentException("Blocks and patience must be positive");
            double best = Double.POSITIVE_INFINITY;
            double[] bestScore = null;
            int stale = 0;
            long started = System.nanoTime();
            for (int block = 1; block <= blocks; block++) {
                long blockStarted = System.nanoTime();
                network.train();
                double error = validationError(network, x, y);
                if (!Double.isFinite(error))
                    throw new IllegalStateException("Training produced non-finite validation error");
                double[] score = references == null ? new double[]{-error}
                    : successScore(network, x, references, scale, offset);
                boolean improved = references == null ? error < best - 1e-10 : scoreImproved(score, bestScore);
                if (improved) {
                    best = error;
                    bestScore = score;
                    stale = 0;
                    network.saveWeights();
                } else stale++;
                System.out.printf(java.util.Locale.ROOT,
                    "block=%d validation_mse=%.12g best_mse=%.12g block_seconds=%.3f elapsed_seconds=%.3f%n",
                    block, error, best, (System.nanoTime() - blockStarted) / 1e9,
                    (System.nanoTime() - started) / 1e9);
                if (references != null)
                    System.out.printf(java.util.Locale.ROOT,
                        "validation_within5=%.9f within10=%.9f mean_relative_error=%.9f selected=%s%n",
                        score[0], score[1], -score[2], improved);
                if (stale >= patience) break;
            }
        } else if (args[0].equals("predict") && args.length == 3) {
            network.allocateMemory();
            network.populateArrays();
            new Parser().writeBinary(args[2], network.runTestCases());
        } else throw new IllegalArgumentException("Invalid mode/argument combination");
    }
}
