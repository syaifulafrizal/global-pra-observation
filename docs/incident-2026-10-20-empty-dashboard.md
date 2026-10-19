# Empty dashboard after daily deployment — 20 October 2026

## Observed failure

The `GEMPRA` Windows task started at 00:00:01 GMT+8 on 20 October and reported
exit code 0. The deployment completed at approximately 00:44 GMT+8. Source
commit `649d6331f` and Pages commit `015a2ee16637a72201eac47a1b1b6cc35a2d97ee`
were published by the existing workflow.

The page's metadata selected 20 October as its newest date and also offered
19 October, but neither corresponding aggregate nor station result files
existed. The browser requested the missing aggregate followed by 51 missing
station files, then displayed “No Data Available.” JavaScript loaded and ran;
this was a data/publication mismatch.

The aggregate labeled 18 October contained previous-night fallback results,
while the latest usable source observations were actually dated 17 October.
New raw downloads existed, but no newer processed station-night results were
present. Acquisition and successful deployment do not establish that a new
classified observation was produced.

## Root cause and test gap

`upload_results.get_available_dates()` generated seven calendar dates from the
current clock. It did not discover which dates had usable results. Aggregate
generation omitted dates without observations while metadata continued to
advertise those dates. The deployment's old checks validated station count and
the presence of a date list, rather than the files behind that list.

Earlier live-browser tests and manual releases used the Flask snapshot export,
which discovered actual dates. Workflow rehearsals used inert processing and
deployment stages. Those checks did not exercise the real daily exporter plus
publication validation, and therefore missed this integration defect.

## Fix

- Discover the latest seven actual usable source-result dates. Check that each
  result's stored date matches its filename; ignore missing, invalid and malformed results.
- Use the oldest retained observation date for export retention, preserving the
  latest available observations during upstream delays.
- Refuse export without usable observations before modifying existing output.
- Run `validate_pages_output.py` from the daily deployment script before any Git
  commit, initialization, branch switch or push. Every advertised date must have
  a readable aggregate with usable observations belonging to that night; a
  fallback-only aggregate cannot qualify a newer date as available.
- Publish and browser-test an isolated copy of the real daily export rather than
  relying solely on the separate Flask-preview path.

## Verification

Added regression cases cover phantom dates, fallback-only dates, an empty input
set preserving the previous output, and the real PowerShell deployment stopping
before Git on invalid output. The daily exporter was also run against an
isolated copy of the current canonical JSON, CSV, metadata, images and histories.
It correctly selected 17 October and advertised only 13–17 October.

This repair changes date discovery, export retention and publication validation.
It does not change signal processing, thresholds, anomaly flags, SYM-H screening,
earthquake matching, source observations or the registered task's settings.
The task's successful run on 20 October supersedes the earlier refused-run
status documented during the 19 October performance review; the failed page
was caused by export metadata, rather than the task failing to start.

Incident evidence and before/after screenshots are under ignored
`output/dogfood/incident-2026-10-20/`.
