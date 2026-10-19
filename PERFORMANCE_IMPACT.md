# Performance changes and scientific compatibility

Baseline: **`7946d38905a36a765ae3f3df9d3f2069906effb9`**, the reviewed dashboard
version published before these optimizations. Measurements were made on the
local Windows workstation on 19 October 2026. Reproduction commands are in
[`tests/README.md`](tests/README.md).

## What changed

| Change | Impact on the current version | Compatibility controls |
|---|---|---|
| Delivery-sized branding | Header uses a 96px PNG; favicon uses a 32px PNG. Their combined size is 19,146 bytes versus the former 1,822,594-byte source. | Original generated image and transparency are retained. CSS dimensions and visual design are unchanged. |
| Shared dashboard reads | Concurrent consumers share a promise for each JSON/CSV URL. Trend inputs load with at most three simultaneous reads. Two fixed 500ms map waits are replaced with map readiness. | Cache holds at most 32 URLs. Failed reads are evicted. Scheduled refresh clears it; manual date changes revalidate metadata and the selected aggregate. Existing generation guards reject obsolete UI work. |
| Local read caches | Flask reuses metadata and assembled snapshots, avoiding repeated JSON parsing and assembly. Ordinary CSV/image requests no longer discover all station results. | Every relevant request checks file revisions, including additions/deletions, size, nanosecond modification/creation times, station selection and metadata. Metadata: two entries/1 MiB serialized payload budget; snapshots: eight entries/8 MiB. Copies isolate callers. No persistent cache or cache dependency was added. |
| Cached spectral setup | Reuses DPSS tapers, eigenvalues and frequency setup keyed by sample count, time-bandwidth parameter and sample rate. | Eight-entry LRU, read-only setup arrays. Returned frequency arrays remain independently owned. FFT, weighting, normalization, band integration and numerical precision are unchanged. |
| Lower-memory IAGA parsing | Scans only through the header, parses required columns in 16,384-row chunks, and retains component values for the required UTC night. Daily frames concatenate once. | Timestamp ordering and duplicate-winner behavior follow the original whole-file sort. Missing values, fill-value screening and the exact per-second grid remain. The original two-argument parser API still reads the full file. Raw inputs are preserved. |
| Incremental dashboard refresh | Unchanged snapshots retain map, markers and chart objects. Changed snapshots update existing charts and replace observation layers while retaining the map and its zoom. | Refresh revalidates station, history, event and trend dependencies before deciding that content is unchanged. Loading is labeled; export/selection are disabled during refresh. Failures clear stale observations. Chart labels, values and classifications are tested. |

Local cache byte limits count serialized payloads; Python object overhead and
revision metadata add memory. These caches live only inside the Flask process.
The browser cache is bounded by URL count. File revision checks assume normal
filesystem timestamp updates; deliberately rewriting a file while preserving
all its revision fields requires clearing the local cache or restarting Flask.

## Measured impact

| Measurement | Before | After | Interpretation |
|---|---:|---:|---|
| Local dashboard ready | 2.440 s | 1.105 s | About 55% faster |
| Date switch | 1.850 s | 0.210 s | About 89% faster |
| Refresh | 1.799 s | 0.235 s | About 87% faster |
| Startup data requests | 13 | 10 | Duplicate reads removed |
| Date-switch data requests | 11 | 4 | Historical/history reuse |
| Refresh data requests | 11 | 9 | Fresh dependencies, shared reads |
| Metadata lookup, warm | 47.68 ms | 27.58 ms | About 42% faster |
| Aggregate route, warm | 80.75 ms | 46.21 ms | About 43% faster |
| PSD, 3,600 samples, warm setup | 12.74 ms | 0.61 ms | About 20× faster for this component |
| Parser peak tracked allocations, two-day fixture | 51.89 MB | 13.11 MB | About 75% lower |
| Parser elapsed time, same fixture | 574 ms | 587 ms | About 2% slower; accepted memory tradeoff |

Browser numbers are medians of three fresh Chromium contexts per version,
without network throttling. The baseline HTML/JS came from the named Git
revision and used its existing local backend; the optimized version used a
fresh Flask process. Readiness includes charts and markers, while map tiles and
external fonts/CDNs can finish separately. Network variation affects timing.

Python timings use medians of 3–25 calls, depending on the operation. Parser
memory is the peak tracked by `tracemalloc`, rather than total process RSS.
The parser fixture contains 172,800 original rows plus a duplicate with different
component values; 28,800 rows are retained for the selected night. Additional
timestamp bookkeeping preserves duplicate handling and accounts for part of
the remaining allocation. Spectral speedup applies to warm setup reuse, rather
than a whole daily run dominated by acquisition, parsing and plotting.

## Scientific method and output checks

`verify_optimization.py` compares the optimized module directly with the
baseline Git revision, using temporary offline fixtures:

- All analysis options are identical.
- PSD and frequency arrays are bit-identical for three sample/taper/rate configurations.
- Full `analyze_row` outputs match exactly for anomalous, normal, missing-sample,
  disturbed-SYM-H and unavailable-SYM-H cases. This includes the threshold,
  anomalous-hour count, individual anomaly flags, series, anomaly table and
  threshold/baseline provenance. Both positive and negative detections are exercised.
- Full `process_station` runs produce identical saved JSON, time-series CSV and
  coverage CSV, and both generate the expected figure.
- Full-file parsing and the filtered eight-hour window retain identical values,
  timestamps, NaNs and duplicate winners compared with the original parser.
- All five published aggregate payloads match, excluding the assembly timestamp.
- `earthquake_integration.py` and `integrate_earthquakes.py` are unchanged, preserving
  earthquake eligibility, exact geodesic distances, forward matching and failure status.
- All 2,936 previously protected raw data, result and figure files remain checksum-identical.

The 0.095–0.110 Hz band, one-hour windows, nighttime gate, multitaper NW 3.5,
EVT/k-sigma thresholds, historical baseline selection, nZ guard, SYM-H screening,
persistence setting, and M≥5/200 km/14-day matching rules are unchanged.
Existing regression tests also execute a synthetic eight-hour night through
`process_station`, including the result, figure and coverage output in a
temporary directory. These checks establish compatibility with the baseline;
they do not supply new scientific validation of the anomaly model.

## Scheduler compatibility and existing operational issue

The registered **`GEMPRA`** task points to `deploy_all.bat`. Its XML is unchanged
before/after these changes, as are `deploy_all.bat`, `deploy_all.ps1`,
`run_daily_analysis.bat` and `run_daily_analysis.ps1`. Python entry points,
environment variables, result filenames and pipeline stage order are preserved.
The static-output preparer already copies the complete assets directory, so
the new header/favicon derivatives are included in future daily deployments.

`verify_scheduler.py` copied the actual workflow wrappers into temporary folders
and ran them with inert Python/deployment fixtures. Both wrappers exited with
code 0 and invoked the expected stages in order. No registered task was started,
no live download was requested, and no production dataset was regenerated.

**Pre-existing issue requiring attention:** at inspection, `GEMPRA` was enabled
and Ready, scheduled daily at **00:00 GMT+8**, with its next run listed as
20 October 2026. Its last result was **`0x800710E0`**: “The operator or
administrator has refused the request.” It uses an interactive logon, blocks
starts on battery and lacks catch-up/wake settings. The wrappers also contain
interactive pauses. The inspected Task Scheduler operational log did not provide
an event explaining this refusal. Script compatibility is verified; successful
future unattended execution depends on resolving/confirming these existing
Windows task conditions. The current registration has been preserved.

## Verification and evidence

- 28 Python and 12 JavaScript regression tests passed.
- 42 local browser scenarios passed, including all 255 station/date combinations,
  89 figure links, time zones, failures, delayed responses, export, touch layouts,
  and repeated/changed refreshes.
- Twelve consecutive unchanged refreshes retained map, marker and chart identity,
  preserved zoom, kept six canvases and kept the request cache bounded.
- A changed-response fixture updated anomaly counts/classifications while retaining
  map and chart instances.

Detailed diagnostic JSON, scheduler snapshots and browser screenshots are kept
under ignored `output/dogfood/optimization/`. Verification scripts and tests are
versioned. Reverting this optimization commit restores the baseline behavior;
the original image and protected datasets remain available throughout.
