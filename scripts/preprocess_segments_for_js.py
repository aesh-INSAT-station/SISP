"""Convert segments.csv to segments.json for the JS simulation."""
import csv
import json
from collections import defaultdict

CSV_PATH = "data/raw/segments.csv"
JSON_PATH = "simulation/public/segments.json"

rows_by_channel = defaultdict(list)

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ch = row["channel"]
        try:
            v = float(row["value"])
        except ValueError:
            continue
        rows_by_channel[ch].append({
            "value": v,
            "anomaly": int(row.get("anomaly", "0")),
            "train": int(row.get("train", "0")),
            "segment": int(row.get("segment", "0")),
        })

# Build per-channel time series
channels = {}
for ch, vals in rows_by_channel.items():
    channels[ch] = {
        "values": [v["value"] for v in vals],
        "anomaly": [v["anomaly"] for v in vals],
        "train": [v["train"] for v in vals],
        "segment": [v["segment"] for v in vals],
    }

output = {
    "channels": channels,
    "meta": {
        "totalRows": sum(len(c["values"]) for c in channels.values()),
        "channelNames": list(channels.keys()),
    }
}

with open(JSON_PATH, "w") as f:
    json.dump(output, f, separators=(",", ":"))

print(f"Wrote {JSON_PATH}")
print(f"  Channels: {list(channels.keys())}")
for ch, data in channels.items():
    n = len(data["values"])
    n_anom = sum(data["anomaly"])
    n_train = sum(data["train"])
    print(f"    {ch}: {n} samples, {n_anom} anomalous, {n_train} training")
