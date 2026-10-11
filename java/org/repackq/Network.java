package org.repackq;

import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.time.Duration;
import java.time.Instant;
import java.util.Random;

/*
 * Fully connected network with configurable hidden layers and backpropagation.
 * Source and licensing: README.md and java/LICENSE.
 */
public class Network
{
   private Random random = new Random();
   // Defaults keep older control files working.
   private String hiddenActivation = "sigmoid";
   private boolean shuffleTraining = false;
   private double weightDecay = 0.0;
   private double[] trainingWeights;

   // Set positive loss weights for the training cases.
   public void setTrainingWeights(double[] values)
   {
      if (values.length != numTestCases) throw new IllegalArgumentException("Training weight count differs");
      for (double value : values)
         if (!Double.isFinite(value) || value <= 0) throw new IllegalArgumentException("Invalid training weight");
      trainingWeights = values.clone();
   }
   // Set the seed before initializing weights so a run can be repeated.
   public void setRandomSeed(long seed)
   {
      random = new Random(seed);
   }

   /*
    * Run one scaled input without changing weights. Return a copy of the outputs.
    * Input order and scaling must match training; do not share this instance between threads.
    */
   public double[] predict(double[] input)
   {
      if (input == null || input.length != inputSize)
         throw new IllegalArgumentException("Prediction input width must be " + inputSize);
      for (double value : input)
         if (!Double.isFinite(value))
            throw new IllegalArgumentException("Prediction inputs must be finite");
      setActivations(input);
      run();
      return a[outputLayer].clone();
   }
   // Control-file settings
   private final static String DEFAULT_CONTROL_FILE = "control.txt";
   private String controlFileName;
   private int inputSize;
   private int[] hiddenSizes;    // 1-indexed by hidden layer number, with hiddenSizes[0] unused
   private int outputSize;
   private double randLowerBound;
   private double randUpperBound;
   private double learningRate;
   private int maxIterations;
   private double errorThreshold;
   private int keepAlive;
   private String loadFileName;
   private String saveFileName;
   private String trainingDataFileName;
   private String truthTableFileName;

   // Layer counts and indices
   private int numActivationLayers;
   private int numConnectivityLayers;
   private static final int INPUT_LAYER = 0;
   private static final int FIRST_HIDDEN_LAYER = 1;
   private int lastHiddenLayer;
   private int outputLayer;

   // Activations by layer: input at 0, output at outputLayer.
   private double[][] a;

   // Weights: w[layer][source neuron][destination neuron].
   private double[][][] w;

   // Weighted sums before the hidden-layer activation function.
   private double[][] theta;

   // Error terms passed back from the output layer.
   private double[][] psi;

   // Input cases and their expected outputs
   private int numTestCases;
   private double[][] trainingData;
   private double[][] truthTable;

   // Run options
   private boolean training;
   private String weightInputChoice;
   private boolean runningTestCases;
   private boolean saveWeights;
   private boolean printInputs;

   // Training exit state and timing
   private boolean hitErrorThreshold;
   private boolean hitMaxIterations;
   private int iterationsReached;
   private double averageErrorReached;
   private Duration timeTaken;

   // Read the control file before allocating arrays. Hidden sizes use indices starting at 1.
   public void setConfigParams(String[] controlFile)
   {
      if (controlFile == null || controlFile.length == 0)
      {
         controlFile = new String[]{DEFAULT_CONTROL_FILE};
      }
      else if (controlFile.length > 1)
      {
         throw new IllegalArgumentException(
            "Expected zero or one command-line argument for the control file name, received " + controlFile.length + ".");
      }
      this.controlFileName = controlFile[0];
      Parser parser = new Parser();
      parser.parseControlFile(controlFileName);

      this.inputSize = parser.findVal("inputSize", Integer.class);
      this.hiddenSizes = parser.findVal("hiddenSizes", int[].class);
      this.outputSize = parser.findVal("outputSize", Integer.class);
      this.randLowerBound = parser.findVal("randLowerBound", Double.class);
      this.randUpperBound = parser.findVal("randUpperBound", Double.class);
      this.learningRate = parser.findVal("learningRate", Double.class);
      this.hiddenActivation = parser.findValOrDefault("hiddenActivation", String.class, "sigmoid");
      this.shuffleTraining = parser.findValOrDefault("shuffleTraining", Boolean.class, false);
      this.weightDecay = parser.findValOrDefault("weightDecay", Double.class, 0.0);
      if (!Double.isFinite(weightDecay) || weightDecay < 0)
         throw new IllegalArgumentException("Invalid weight decay");
      if (!hiddenActivation.equals("sigmoid") && !hiddenActivation.equals("tanh"))
         throw new IllegalArgumentException("Unknown hidden activation: " + hiddenActivation);
      this.maxIterations = parser.findVal("maxIterations", Integer.class);
      this.errorThreshold = parser.findVal("errorThreshold", Double.class);
      this.loadFileName = parser.findVal("loadFileName", String.class);
      this.saveFileName = parser.findVal("saveFileName", String.class);
      this.trainingDataFileName = parser.findVal("trainingDataFileName", String.class);

      this.numActivationLayers = parser.findVal("numActivationLayers", Integer.class);
      this.numConnectivityLayers = numActivationLayers - 1;
      this.lastHiddenLayer = numActivationLayers - 2;
      this.outputLayer = numActivationLayers - 1;

      if (hiddenSizes.length - 1 != numActivationLayers - 2)
      {
         throw new IllegalArgumentException("Number of hidden sizes provided does not match expected number of hidden layers. " +
            "Expected: " + (numActivationLayers - 2) + ", Provided: " + (hiddenSizes.length - 1));
      }

      this.training = parser.findVal("training", Boolean.class);
      this.weightInputChoice = parser.findVal("weightInputChoice", String.class);
      this.runningTestCases = parser.findVal("runningTestCases", Boolean.class);
      this.saveWeights = parser.findVal("saveWeights", Boolean.class);
      this.printInputs = parser.findVal("printInputs", Boolean.class);
      this.keepAlive = 0;

      if (training)
      {
         this.keepAlive = parser.findVal("keepAlive", Integer.class);
      }

      this.numTestCases = parser.findVal("numTestCases", Integer.class);

      if (training)
      {
         this.truthTableFileName = parser.findVal("truthTableFileName", String.class);
      }
   }

   // Print the layer sizes and options for this run.
   public void echoConfigParams()
   {
      System.out.println("\nReading configuration parameters from: " + controlFileName);
      System.out.println("\n=====Network Configuration Parameters=====");
      System.out.print("Network configuration: " + inputSize + "-");
      for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
      {
         System.out.print(hiddenSizes[n] + "-");
      }
      System.out.println(outputSize);

      if (training)
      {
         System.out.println("randLowerBound: " + randLowerBound);
         System.out.println("randUpperBound: " + randUpperBound);
         System.out.println("learningRate: " + learningRate);
         System.out.println("maxIterations: " + maxIterations);
         System.out.println("errorThreshold: " + errorThreshold);
         System.out.println("keepAlive: " + keepAlive);
         System.out.println("Reading training data from: " + trainingDataFileName);
         System.out.println("Reading truth table from: " + truthTableFileName);
      }

      System.out.println("printInputs: " + printInputs);

      if (weightInputChoice.equalsIgnoreCase("load"))
      {
         System.out.println("Reading weights from: " + loadFileName);
      }
   }

   // Allocate the layer arrays after reading the configuration.
   public void allocateMemory()
   {
      a = new double[numActivationLayers][];    //
      a[INPUT_LAYER] = new double[inputSize];
      for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
      {
         a[n] = new double[hiddenSizes[n]];
      }
      a[outputLayer] = new double[outputSize];

      w = new double[numConnectivityLayers][][];
      for (int n = 0; n < numConnectivityLayers; n++)
      {
         w[n] = new double[a[n].length][a[n + 1].length];
      }

      if (training || runningTestCases)
      {
         trainingData = new double[numTestCases][inputSize];
      }

      if (training)
      {
         theta = new double[numActivationLayers - 1][];
         for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
         {
            theta[n] = new double[hiddenSizes[n]];
         }

         psi = new double[numActivationLayers][];
         for (int n = outputLayer; n > FIRST_HIDDEN_LAYER; n--)
         {
            psi[n] = new double[a[n].length];
         }

         truthTable = new double[numTestCases][outputSize];
      }
   }

   // Load the data and initialize weights after allocating arrays.
   public void populateArrays()
   {
      if (training || runningTestCases) // Populate input data for both training and test cases
      {                                 // since they use the same input vectors
         setTrainingData();
      }

      if (training)
      {
         setTruthTable();
      }

      setWeights();
   }

   // Choose random, layer-scaled, manual, or saved weights. Unknown choices use random weights.
   private void setWeights()
   {
      if (weightInputChoice.equalsIgnoreCase("xavier"))
      {
         // Layer-scaled uniform initialization for the deeper tanh model.
         for (int layer = 0; layer < w.length; layer++)
         {
            double bound = Math.sqrt(6.0 / (w[layer].length + w[layer][0].length));
            for (double[] row : w[layer])
               for (int column = 0; column < row.length; column++)
                  row[column] = randomize(-bound, bound);
         }
      }
      else if (weightInputChoice.equalsIgnoreCase("random"))
      {
         setRandomWeights();
      }
      else if (weightInputChoice.equalsIgnoreCase("manual"))
      {
         setManualWeights();
      }
      else if (weightInputChoice.equalsIgnoreCase("load"))
      {
         loadWeights();
      }
      else
      {
         System.out.println("Invalid weightInputChoice: " + weightInputChoice);
         System.out.println("Defaulting to random weight initialization.");
         setRandomWeights();
      }
   }

   // Fill each weight matrix using the configured random bounds.
   private void setRandomWeights()
   {
      for (int n = 0; n < numConnectivityLayers; n++)
      {
         for (int j = 0; j < a[n].length; j++)
         {
            for (int k = 0; k < a[n + 1].length; k++)
            {
               w[n][j][k] = randomize(randLowerBound, randUpperBound);
            }
         }
      }
   }

   // Choose a uniform value between the given bounds.
   private double randomize(double low, double high)
   {
      return (random.nextDouble() * (high - low) + low);
   }

   // Fixed weights for a small test network; layer sizes must match these indices.
   private void setManualWeights()
   {
      w[0][0][0] = 0.3;
      w[0][1][0] = 0.45;
      w[1][0][0] = 0.05;
      w[1][1][0] = 0.6;

      w[2][0][0] = 0.29851;
      w[2][1][0] = 0.55;
   }

   // Read layer sizes, then weight matrices. Reject a file with different layer sizes.
   private void loadWeights()
   {
      try (DataInputStream in = new DataInputStream(new BufferedInputStream(new FileInputStream(loadFileName))))
      {
         int fileInputSize = in.readInt();
         int[] fileHiddenSizes = new int[hiddenSizes.length];
         for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
         {
            fileHiddenSizes[n] = in.readInt();
         }
         int fileOutputSize = in.readInt();

         if (!weightsMatch(fileInputSize, fileHiddenSizes, fileOutputSize))
         {
            String fileConfig = fileInputSize + "-";
            String currentConfig = inputSize + "-";

            for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
            {
               fileConfig += (fileHiddenSizes[n]) + "-";
               currentConfig += (hiddenSizes[n]) + "-";
            }

            fileConfig += fileOutputSize;
            currentConfig += outputSize;

            throw new IllegalStateException(
               "Weights file network configuration does not match current configuration. " +
               "File: " + fileConfig +
               ", Current: " + currentConfig
            );
         }

         for (int n = 0; n < numConnectivityLayers; n++)
         {
            for (int j = 0; j < w[n].length; j++)
            {
               for (int k = 0; k < w[n][j].length; k++)
               {
                  w[n][j][k] = in.readDouble();
               }
            }
         }

         if (in.available() != 0)
         {
            throw new IllegalStateException("Weights file contains extra data after all expected weights were loaded.");
         }
      }
      catch (IOException e)
      {
         throw new RuntimeException("Failed to load weights from file: " + loadFileName, e);
      }
   }

   // Check the saved layer sizes against this network.
   private boolean weightsMatch(int fileInputSize, int[] fileHiddenSizes, int fileOutputSize)
   {
      if (fileInputSize != inputSize || fileOutputSize != outputSize
         || fileHiddenSizes.length != hiddenSizes.length)
      {
         return false;
      }

      for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
      {
         if (fileHiddenSizes[n] != hiddenSizes[n])
         {
            return false;
         }
      }

      return true;
   }

   // Write input, hidden, and output sizes, followed by the weight matrices.
   public void saveWeights()
   {
      try (DataOutputStream out = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(saveFileName))))
      {
         out.writeInt(inputSize);
         for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
         {
            out.writeInt(hiddenSizes[n]);
         }
         out.writeInt(outputSize);

         for (int n = 0; n < numConnectivityLayers; n++)
         {
            for (int j = 0; j < a[n].length; j++)
            {
               for (int k = 0; k < a[n + 1].length; k++)
               {
                  out.writeDouble(w[n][j][k]);
               }
            }
         }

         System.out.println("Saved weights to: " + saveFileName);
      }
      catch (IOException e)
      {
         throw new RuntimeException("Failed to save weights to file: " + saveFileName, e);
      }
   }

   // Read the row count, input width, and row-major doubles. Dimensions must match the control file.
   private void setTrainingData()
   {
      try (DataInputStream in = new DataInputStream(new BufferedInputStream(new FileInputStream(trainingDataFileName))))
      {
         int fileNumTestCases = in.readInt();
         int fileInputSize = in.readInt();

         if (fileNumTestCases != numTestCases || fileInputSize != inputSize)
         {
            throw new IllegalStateException(
               "Training data file configuration does not match current configuration. " +
               "File: numTestCases=" + fileNumTestCases + ", inputSize=" + fileInputSize +
               ", Current: numTestCases=" + numTestCases + ", inputSize=" + inputSize
            );
         }

         for (int t = 0; t < numTestCases; t++)
         {
            for (int k = 0; k < inputSize; k++)
            {
               trainingData[t][k] = in.readDouble();
            }
         }
      }
      catch (IOException e)
      {
         throw new RuntimeException("Failed to load training data from file: " + trainingDataFileName, e);
      }
   }

   // Read the expected outputs in the same binary format as the inputs.
   private void setTruthTable()
   {
      try (DataInputStream in = new DataInputStream(new BufferedInputStream(new FileInputStream(truthTableFileName))))
      {
         int fileNumTestCases = in.readInt();
         int fileOutputSize = in.readInt();

         if (fileNumTestCases != numTestCases || fileOutputSize != outputSize)
         {
            throw new IllegalStateException(
               "Truth table file configuration does not match current configuration. " +
               "File: numTestCases=" + fileNumTestCases + ", outputSize=" + fileOutputSize +
               ", Current: numTestCases=" + numTestCases + ", outputSize=" + outputSize
            );
         }

         for (int t = 0; t < numTestCases; t++)
         {
            for (int i = 0; i < outputSize; i++)
            {
               truthTable[t][i] = in.readDouble();
            }
         }
      }
      catch (IOException e)
      {
         throw new RuntimeException("Failed to load truth table from file: " + truthTableFileName, e);
      }
   }


   // Apply the selected hidden-layer activation. The output layer uses sigmoid separately.
   private double activationFunction(double x)
   {
      return hiddenActivation.equals("tanh") ? Math.tanh(x) : sigmoid(x);
   }

   // Get the hidden activation derivative from its weighted input.
   private double activationDerivative(double x)
   {
      if (hiddenActivation.equals("tanh")) {
         double value = Math.tanh(x);
         return 1.0 - value * value;
      }
      return sigmoidDerivative(x);
   }

   // Sigmoid: 1 / (1 + exp(-x)).
   private double sigmoid(double x)
   {
      return 1.0 / (1.0 + Math.exp(-x));
   }

   // Sigmoid: 1 / (1 + exp(-x)).
   // Sigmoid derivative: sigmoid(x) * (1 - sigmoid(x)).
   private double sigmoidDerivative(double x)
   {
      double s = sigmoid(x);
      return s * (1.0 - s);
   }

   // Compute tanh using the sign of x to avoid a large positive exponential.
   private double tanh(double x)
   {
      double epsilon = (x < 0.0) ? 1.0 : -1.0;
      double exponential = Math.exp(epsilon * 2.0 * x);
      return epsilon * (exponential - 1.0) / (exponential + 1.0);
   }

   // Compute tanh using the sign of x to avoid a large positive exponential.
   // Tanh derivative: 1 - tanh(x)^2.
   private double tanhDerivative(double x)
   {
      double t = tanh(x);
      return 1.0 - t * t;
   }

   /*
    * Update weights after each case. Stop at the error threshold or maxIterations.
    * One iteration is one pass through all training cases.
    */
   public void train()
   {
      hitErrorThreshold = false;
      hitMaxIterations = false;
      iterationsReached = 0;
      averageErrorReached = Double.POSITIVE_INFINITY;
      int[] order = new int[numTestCases];
      for (int index = 0; index < numTestCases; index++) order[index] = index;

      while (iterationsReached < maxIterations && averageErrorReached > errorThreshold)
      {
         double totalTwiceError = 0.0;
         if (shuffleTraining)
            for (int index = order.length - 1; index > 0; index--)
            {
               int other = random.nextInt(index + 1);
               int temporary = order[index]; order[index] = order[other]; order[other] = temporary;
            }
         for (int t = 0; t < numTestCases; t++) // Update once per training case
         {
            int example = order[t];
            setActivations(trainingData[example]);
            totalTwiceError += runForTraining(example);
            updateWeights();
         }
         averageErrorReached = totalTwiceError / ((double) numTestCases * 2.0);

         iterationsReached++;

         if (keepAlive != 0 && iterationsReached % keepAlive == 0)
         {
            if (iterationsReached == keepAlive)
            {
               System.out.println();
            }
            System.out.printf("Iteration %d, Error = %f\n", iterationsReached, averageErrorReached);
         }
      }

      if (averageErrorReached <= errorThreshold)
      {
         hitErrorThreshold = true;
      }

      if (iterationsReached >= maxIterations)
      {
         hitMaxIterations = true;
      }
   }

   /*
    * Run one case and calculate output error terms for backpropagation.
    * The return value is twice the weighted squared-error loss.
    */
   public double runForTraining(int testCase)
   {
      for (int n = FIRST_HIDDEN_LAYER; n <= lastHiddenLayer; n++)
      {
         for (int k = 0; k < a[n].length; k++)
         {
            theta[n][k] = 0.0;
            for (int j = 0; j < a[n - 1].length; j++)
            {
               theta[n][k] += a[n - 1][j] * w[n - 1][j][k];
            }
            a[n][k] = activationFunction(theta[n][k]);
         }
      }

      double twiceError = 0.0;
      for (int k = 0; k < outputSize; k++) // Compute output layer activations
      {
         double outputTheta = 0.0;
         for (int j = 0; j < a[lastHiddenLayer].length; j++)
         {
            outputTheta += a[lastHiddenLayer][j] * w[lastHiddenLayer][j][k];
         }
         a[outputLayer][k] = sigmoid(outputTheta);

         double omega_k = truthTable[testCase][k] - a[outputLayer][k];
         double lossWeight = trainingWeights == null ? 1.0 : trainingWeights[testCase];
         twiceError += lossWeight * omega_k * omega_k;
         psi[outputLayer][k] = lossWeight * omega_k * sigmoidDerivative(outputTheta);
      }
      return twiceError;
   }

   /*
    * Work backwards through the layers using the last training forward pass.
    * Use each old weight for the error calculation before updating it.
    */
   private void updateWeights()
   {
      for (int n = lastHiddenLayer; n > FIRST_HIDDEN_LAYER; n--)
      {
         for (int j = 0; j < a[n].length; j++)
         {
            double omega_j = 0.0;
            for (int k = 0; k < a[n + 1].length; k++)
            {
               omega_j += psi[n + 1][k] * w[n][j][k];
               w[n][j][k] += learningRate * (a[n][j] * psi[n + 1][k] - weightDecay * w[n][j][k]);
            }

            psi[n][j] = omega_j * activationDerivative(theta[n][j]);
         }
      }

      for (int j = 0; j < a[FIRST_HIDDEN_LAYER].length; j++)
      {
         double omega_j = 0.0;
         for (int k = 0; k < a[FIRST_HIDDEN_LAYER + 1].length; k++)
         {
            omega_j += psi[FIRST_HIDDEN_LAYER + 1][k] * w[FIRST_HIDDEN_LAYER][j][k];
            w[FIRST_HIDDEN_LAYER][j][k] += learningRate * (a[FIRST_HIDDEN_LAYER][j] * psi[FIRST_HIDDEN_LAYER + 1][k]
                - weightDecay * w[FIRST_HIDDEN_LAYER][j][k]);
         }

         double inputPsi = omega_j * activationDerivative(theta[FIRST_HIDDEN_LAYER][j]);
         for (int i = 0; i < inputSize; i++)
         {
            w[INPUT_LAYER][i][j] += learningRate * (a[INPUT_LAYER][i] * inputPsi - weightDecay * w[INPUT_LAYER][i][j]);
         }
      }
   }

   // Run forward from the current input activations without updating weights.
   public void run()
   {
      for (int n = FIRST_HIDDEN_LAYER; n <= outputLayer; n++)
      {
         for (int k = 0; k < a[n].length; k++)
         {
            double runTheta = 0.0;
            for (int j = 0; j < a[n - 1].length; j++)
            {
               runTheta += a[n - 1][j] * w[n - 1][j][k];
            }
            a[n][k] = n == outputLayer ? sigmoid(runTheta) : activationFunction(runTheta);
         }
      }
   }

   // Print the stop condition, final error, pass count, and elapsed time.
   public void reportTrainingResults()
   {
      if (!training) return;

      System.out.println("\n=====Training Exit Information=====");
      System.out.println("Reason for end of training:");
      System.out.println("Reached error threshold: " + hitErrorThreshold);
      System.out.println("Reached max iterations: " + hitMaxIterations);
      System.out.println("Iterations reached: " + iterationsReached);
      System.out.printf("Average Error reached: %.4f\n", averageErrorReached);
      System.out.println("Time taken: " + timeTaken.toMillis() + " ms");
   }

   // Copy the input values into the first layer.
   private void setActivations(double[] input)
   {
      for (int k = 0; k < inputSize; k++)
      {
         a[INPUT_LAYER][k] = input[k];
      }
   }

   // Run every stored input case and return its output values.
   public double[][] runTestCases()
   {
      double[][] outputs = new double[numTestCases][outputSize];

      for (int t = 0; t < numTestCases; t++) // Run each test case and store the output activations
      {
         setActivations(trainingData[t]);
         run();
         for (int i = 0; i < outputSize; i++)
         {
            outputs[t][i] = a[outputLayer][i];
         }
      }

      return outputs;
   }

   // Print outputs and, when requested, the corresponding inputs.
   public void reportRunResults(double[][] outputs)
   {
      if (printInputs)
      {
         System.out.println("\n=====Input Table=====");
         for (int t = 0; t < numTestCases; t++) // Print input vectors for each test case
         {
            System.out.print(t + ": ");
            for (int k = 0; k < inputSize; k++)
            {
               System.out.print(trainingData[t][k]);
               if (k < inputSize - 1) System.out.print(" ");
            }
            System.out.println();
         }
      }

      if (truthTable != null) // Print truth table values if available (i.e., if training was enabled)
      {
         System.out.println("\n=====Truth Table=====");
         for (int t = 0; t < numTestCases; t++)
         {
            System.out.print(t + ": ");
            for (int i = 0; i < outputSize; i++)
            {
               System.out.print(truthTable[t][i]);
               if (i < outputSize - 1) System.out.print(" ");
            }
            System.out.println();
         }
      }

      System.out.println("\n=====Actual Outputs=====");
      for (int t = 0; t < outputs.length; t++) // Print the actual output activations for each test case
      {
         System.out.print(t + ": ");
         for (int i = 0; i < outputSize; i++)
         {
            System.out.printf("%.4f", outputs[t][i]);
            if (i < outputSize - 1) System.out.print(" ");
         }
         System.out.println();
      }

      System.out.println("\n=====Time Taken=====");
      System.out.println(timeTaken.toMillis() + " ms");
   }

   // Read a control file, train if enabled, then run and report the configured cases.
   public static void main(String[] args)
   {
      Network net = new Network();
      net.setConfigParams(args);
      net.echoConfigParams();
      net.allocateMemory();
      net.populateArrays();

      if (net.training)
      {
         Instant startTime = Instant.now();
         net.train();
         Instant endTime = Instant.now();
         net.timeTaken = Duration.between(startTime, endTime);
         net.reportTrainingResults();
      }

      if (net.saveWeights)
      {
         net.saveWeights();
      }

      if (net.runningTestCases)
      {
         Instant startTime = Instant.now();
         double [][] outputs = net.runTestCases();
         Instant endTime = Instant.now();
         net.timeTaken = Duration.between(startTime, endTime);
         net.reportRunResults(outputs);
      }
   }
}
