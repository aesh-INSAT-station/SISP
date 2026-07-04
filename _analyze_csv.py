import csv
from collections import defaultdict, Counter

with open('data/raw/segments.csv', newline='', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

seg_groups = defaultdict(list)
for r in rows:
    seg_groups[r['segment']].append(r)

print(f'Total rows: {len(rows)}')
print(f'Total segments: {len(seg_groups)}')

s1 = seg_groups['1']
print(f'Seg 1: {len(s1)} rows, ch={s1[0]["channel"]}, label={s1[0]["label"]}, anomaly={s1[0]["anomaly"]}, train={s1[0]["train"]}')

for sid, grp in seg_groups.items():
    if grp[0]['label'] == 'nominal':
        print(f'Nominal seg {sid}: {len(grp)} rows, ch={grp[0]["channel"]}')
        break

labels = Counter(r['label'] for r in rows)
anomaly = Counter(r['anomaly'] for r in rows)
train = Counter(r['train'] for r in rows)
print(f'Labels: {dict(labels)}')
print(f'Anomaly: {dict(anomaly)}')
print(f'Train: {dict(train)}')

# Check each channel
from collections import defaultdict
ch_segs = defaultdict(set)
for r in rows:
    ch_segs[r['channel']].add(r['segment'])
for ch, segs in sorted(ch_segs.items()):
    print(f'  {ch}: {len(segs)} segments')
