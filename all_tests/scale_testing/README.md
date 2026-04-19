# Protocol Scale Testing

This folder contains a repeatable scale runner for the whole protocol test surface.

## Runner
- Script: all_tests/scale_testing/run_protocol_scale.py
- Purpose: run protocol-level tests in tiers and collect repeat timing statistics.

## Tiers
- quick: core integration and end-to-end paths
- medium: quick + borrow flow
- heavy: medium + full correction/outlier benchmark

## Usage
From repository root:

```powershell
c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/scale_testing/run_protocol_scale.py --tier quick --repeats 3
c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/scale_testing/run_protocol_scale.py --tier medium --repeats 5
c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/scale_testing/run_protocol_scale.py --tier heavy --repeats 2
```

Optional:

```powershell
c:/Users/HP/aesh/SISP/.venv/Scripts/python.exe all_tests/scale_testing/run_protocol_scale.py --tier heavy --repeats 2 --fail-fast
```

## What this measures
- pass or fail per test module
- run duration per module
- mean and p95 duration across repeats

## Notes
- This runner scales by repeated workload and test breadth.
- To scale by constellation size directly, add CLI parameters to python_satellite_sim_v2.py and integrate those scenarios in this runner.
