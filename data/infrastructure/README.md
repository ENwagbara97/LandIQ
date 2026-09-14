# Nigerian Utility & Infrastructure Corridors Dataset

## Overview
This directory houses spatial alignment data for high-voltage electricity transmission lines and major hydrocarbon pipelines across the Federal Republic of Nigeria.

### Datasets:
1. `ng_transmission_lines.geojson`:
   - 330kV and 132kV national grid transmission alignments.
   - Source: Transmission Company of Nigeria (TCN) / Nigerian Electricity Regulatory Commission (NERC) statutory corridors and OpenStreetMap infrastructure layers.
   - Statutory Right-of-Way (RoW): 15–25 meters on either side of the transmission centerline.

2. `ng_pipelines.geojson`:
   - Major gas, crude oil, and refined petroleum trunklines (e.g., Escravos-Lagos Pipeline System ELPS, Ajaokuta-Kaduna-Kano AKK, NNPC System 2B network).
   - Source: Nigerian National Petroleum Company Limited (NNPCL) / Nigerian Gas Marketing Company (NGMC) public route records.
   - Statutory Right-of-Way (RoW): 15 meters from pipeline center.

### Classification Logic:
- `WITHIN_ROW` (Red): Parcel boundary / centroid is within <= 15 meters of an active transmission line or high-pressure pipeline right-of-way. Development is statutorily prohibited under Nigerian building regulations.
- `PROXIMATE` (Amber): Parcel is within 16 to 100 meters. Setback and clearance verification required by municipal town planners.
- `NONE` (Green): Parcel is > 100 meters from any major utility corridor.
