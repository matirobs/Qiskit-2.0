# this file measures how much charge each battery hold

import pandas as pd   # needed to build a table at the end of the function

# gets the discharge data from cell data file 
from cell_data import fresh_discharge, aged_discharge 


# function: does all our steps for ONE cell, returns a table (one row per discharge)
def discharge_table(discharge):
    # time gap between each row and the row before it 
    gaps = discharge["Time"].diff()

    # a gap bigger than 10 seconds means a new discharge started
    new_discharge = gaps > 10

    # give the rows each a discharge numebr 1,2,3,...
    #cumsum is the running total, it goes up 1 every time a new discharge starts 
    discharge_number = new_discharge.cumsum()

    # count rows in each discharge (1 row = 1 second), then turn into minutes
    minutes = discharge.groupby(discharge_number).size() / 60

    #capacity of each discahrge              divide by 3600 because we need in amp-hours
    capacity = discharge.groupby(discharge_number)["Current"].sum() / 3600

    # put minutes and capacity together into one table
    return pd.DataFrame({"minutes": minutes, "capacity_Ah": capacity})


# run the function on both cells
fresh_table = discharge_table(fresh_discharge)
aged_table = discharge_table(aged_discharge)


# function: prints the same summary for any cell
def summary(name, table):
    minutes = table["minutes"]
    print("\n=====", name, "=====")
    print("number of discharges:", len(table))

    # shortest, longest, and typical length
    print("shortest discharge:", round(minutes.min(), 1), "minutes")
    print("longest discharge: ", round(minutes.max(), 1), "minutes")
    print("typical discharge: ", round(minutes.median(), 1), "minutes")

    # count how many discharges have each length (rounded to whole minutes)
    print("discharge length (min) -> how many:")
    print(minutes.round().value_counts().head(8))


summary("FRESH", fresh_table)
summary("AGED", aged_table)


# keep only full discharges: ones that last close to that cell's longest discharge (within 5%)
def full_capacity(table):
    full = table["minutes"] > 0.95 * table["minutes"].max()
    return table["capacity_Ah"][full]

fresh_full = full_capacity(fresh_table)
aged_full = full_capacity(aged_table)

print("\nfresh: ", len(fresh_full), "full discharges, average", round(fresh_full.mean(), 2), "Ah")
print("aged:  ", len(aged_full), "full discharges, average", round(aged_full.mean(), 2), "Ah")

# state of health = how much the aged cell holds compared to a new one
soh = aged_full.mean() / fresh_full.mean()
print("aged cell state of health:", round(soh * 100, 1), "%")