import pandas as pd 
import numpy as np 

data  = pd.read_csv(r"data\kepler_raw.csv", comment="#")

print (data.isnull().sum())

print(data.describe())

print(data.info())

print(data.shape)

print(data["koi_disposition"].value_counts())