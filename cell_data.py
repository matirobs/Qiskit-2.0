
#this file is what loads the battery data

import pandas as pd

# loads fresh cells data into a table 
fresh = pd.read_csv("Experimental_data_fresh_cell.csv")

#this prints the table size
print(fresh.shape)

print(fresh.head())