
#this file is what loads the battery data

import pandas as pd

# loads fresh cells data into a table 
fresh = pd.read_csv("Experimental_data_fresh_cell.csv")

# this loads the aged cells data 
aged = pd.read_csv("Experimental_data_aged_cell.csv")


# this is a fucntion to split each data set into charging and dishcahring 
def split_cell(table):
    discharge_rows = []
    charge_rows = []

    # this looks at every row and decides which list it goes in
    for row in table.itertuples(index = False):
        if row.Current > 0:
            discharge_rows.append(row) # postive and discharging
        elif row.Current < 0:
            charge_rows.append(row) # negative and dishcarhign
    # skipping current is equal to 0 bc we need to simplfy it a bit 

    # now we turn each list back into a table 
    discharge = pd.DataFrame(discharge_rows)
    charge = pd.DataFrame(charge_rows)

    return (discharge, charge)

# this makes the 4 data sets 
fresh_discharge, fresh_charge = split_cell(fresh)
aged_discharge, aged_charge = split_cell(aged)


# checks
if __name__ == "__main__":
    print("fresh total:    ", len(fresh), "rows")
    print("fresh discharge:", len(fresh_discharge), "rows")
    print("fresh charge:   ", len(fresh_charge), "rows")
    print()
    print("aged total:     ", len(aged), "rows")
    print("aged discharge: ", len(aged_discharge), "rows")
    print("aged charge:    ", len(aged_charge), "rows")
    print()
    print("first 3 rows of fresh discharge:")
    print(fresh_discharge.head(3))
