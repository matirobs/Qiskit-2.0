package org.repackq;

import java.io.BufferedOutputStream;
import java.io.BufferedReader;
import java.io.DataOutputStream;
import java.io.FileOutputStream;
import java.io.FileReader;
import java.io.IOException;
import java.util.HashMap;

/*
 * Read key=value control files and write binary matrices.
 * Source and licensing: README.md and java/LICENSE.
 */
public class Parser
{
   // Use the fallback when an optional setting is missing.
   public <T> T findValOrDefault(String key, Class<T> type, T fallback)
   {
      return configVariables.containsKey(key) ? findVal(key, type) : fallback;
   }
   // Control-file values before type conversion
   private HashMap<String, String> configVariables;

   /*
    * Read key=value entries, skipping blank lines and # comments.
    * Use spaces or commas for hiddenSizes; its first array slot is unused.
    */
   public void parseControlFile(String controlFileName)
   {
      configVariables = new HashMap<>();
      try (BufferedReader reader = new BufferedReader(new FileReader(controlFileName)))
      {
         String line;

         while ((line = reader.readLine()) != null)
         {
            line = line.trim();

            if (line.isEmpty() || line.startsWith("#"))
            {
               continue;
            }

            int equalsIndex = line.indexOf('=');
            if (equalsIndex < 0)
            {
               throw new IllegalArgumentException("Invalid control file line (missing '='): " + line);
            }

            String key = line.substring(0, equalsIndex).trim();
            String value = line.substring(equalsIndex + 1).trim();

            configVariables.put(key, value);
        }
      }
      catch (IOException e)
      {
         throw new RuntimeException(
            "Failed to read control file: " + controlFileName, e);
      }
   }

   /*
    * Convert a required setting to Integer, Double, Boolean, String, or int[].
    * Hidden sizes start at index 1 to match the network layers.
    */
   public <T> T findVal(String key, Class<T> type)
   {
      String value = configVariables.get(key);

      if (value == null)
      {
         throw new RuntimeException("Key not found: " + key);
      }

      Object result;
      if (type == Integer.class)
      {
         result = Integer.parseInt(value);
      }
      else if (type == Double.class)
      {
         result = Double.parseDouble(value);
      }
      else if (type == Boolean.class)
      {
         result = Boolean.parseBoolean(value);
      }
      else if (type == int[].class)
      {
         String[] parts = value.trim().split("[,\\s]+");
         int[] array = new int[parts.length + 1];
         for (int i = 0; i < parts.length; i++)
         {
            array[i + 1] = Integer.parseInt(parts[i].trim());
         }
         result = array;
      }
      else if (type == String.class)
      {
         result = value;
      }
      else
      {
         throw new RuntimeException("Unsupported type: " + type);
      }

      return type.cast(result);
   }

   /*
    * Write row count, column count, then row-major doubles in big-endian order.
    * The caller must supply a nonempty rectangular matrix.
    */
   public void writeBinary(String filename, double[][] data)
   {
      try (DataOutputStream out = new DataOutputStream(new BufferedOutputStream(new FileOutputStream(filename))))
      {
         int numTestCases = data.length;
         int size = data[0].length;

         out.writeInt(numTestCases);
         out.writeInt(size);

         for (int t = 0; t < numTestCases; t++)
         {
            for (int k = 0; k < size; k++)
            {
               out.writeDouble(data[t][k]);
            }
         }
      }
      catch (IOException e)
      {
         throw new RuntimeException("Failed to save binary data to file: " + filename, e);
      }
   }
}
