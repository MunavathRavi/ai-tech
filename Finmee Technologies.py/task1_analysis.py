import pandas as pd                           # TASK 1: Predictive Maintenance - Data Pipeline & Analysis
import matplotlib.pyplot as plt
print("=" * 50)                          #Load Dataset
print("Loading Dataset")
print("=" * 50)

df = pd.read_csv("data/machine_logs.csv")

print(df.head())
print("\n" + "=" * 50)                  #3. Dataset Information
print("Dataset Information")
print("=" * 50)

print(df.info())

print("\nMissing Values")
print(df.isnull().sum())

print("\nDuplicate Rows:", df.duplicated().sum())
print("\n" + "=" * 50)                    # 4. Data Cleaning
print("Data Cleaning")
print("=" * 50)
df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")  # Convert timestamp to datetime format

df = df.drop_duplicates()           # Remove duplicate records

if "sensor_temp_c" in df.columns:
    df["sensor_temp_c"] = df["sensor_temp_c"].fillna(   # Fill missing numerical values with median
        df["sensor_temp_c"].median()
    )

if "vibration_mm_s" in df.columns:
    df["vibration_mm_s"] = df["vibration_mm_s"].fillna(
        df["vibration_mm_s"].median()
    )
if "status_code" in df.columns:
    df["status_code"] = df["status_code"].fillna("UNKNOWN")  # Fill missing status values

df = df.dropna(subset=["timestamp"])

print("Cleaning Completed Successfully")           # Remove invalid timestamps            
print("\n" + "=" * 50)                  # Remove invalid timestamps
print("Cleaned Dataset")
print("=" * 50)

print(df.head())
print("\n" + "=" * 50)                       # Remove invalid timestamps
print("Summary Statistics")
print("=" * 50)

print(df.describe())

print("\nAverage Temperature :", df["sensor_temp_c"].mean())
print("Maximum Temperature :", df["sensor_temp_c"].max())

print("\nAverage Vibration :", df["vibration_mm_s"].mean())
print("Maximum Vibration :", df["vibration_mm_s"].max())

plt.figure(figsize=(12,5))
plt.plot(
    df["timestamp"],
    df["sensor_temp_c"],            
    marker="o"
)

plt.title("Machine Temperature Over Time")
plt.xlabel("Timestamp")
plt.ylabel("Temperature (°C)")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
plt.figure(figsize=(12,5))           # 8. Vibration Visualization

plt.plot(
    df["timestamp"],
    df["vibration_mm_s"],
    marker="o"
)

plt.title("Machine Vibration Over Time")
plt.xlabel("Timestamp")
plt.ylabel("Vibration (mm/s)")
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()


df.to_csv("cleaned_machine_logs.csv", index=False)       # 9. Save Cleaned Dataset

print("\nCleaned dataset saved as:")
print("cleaned_machine_logs.csv")
print("\nTask Completed Successfully")       