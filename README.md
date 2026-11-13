# mySocialWatcher

This repository contains a scaleable and containerised version of pySocialWatcher ([Araujo et al. 2017](https://doi.org/10.1145/3091478.3091513)). pySocialWatcher is a Python package that makes it easier to query the Meta Marketing API to get counts of active users on Meta's social media platforms (e.g. Facebook, Instagram). This repository containerises pySocialWatcher so that many instances can be run simultaneously. It also includes a containerised PostgreSQL database and REST API where all the data can be stored centrally to be easily queried later from the database or API. 

## Components

**Collectors:** Each mySocialWatcher collector is a docker container that runs an instance of pySocialWatcher to query Meta's marketing API and save the responses in .csv format. Many collectors can be orchestrated in a single `docker-compose.yml` file and these can be scheduled to launch at defined intervals using a compute scheduler such as cron. 

The pySocialWatcher version used here has been modified from the original (Araujo et al. 2017) to include error handling and minor updates to maintain compatibility with new versions of Meta's marketing API. The specifications for individual collections (e.g. geographies, demographics, and other targeting characteristics) are defined as JSON files using the pySocialWatcher format. 

**Datahub database:** The centralised database runs as as dockerised PostgreSQL database that stores data collected by the entire constellation of collectors. The database maintains the pySocialWatcher data format for compatibility with other pySocialWatcher collections. It stores the original unmodified JSON responses from Meta's marketing API and extrapolates additional data columns for easy filtering. The database can be directly queried to filter data by geography, demographics, and behaviours of Meta audiences. 

**Datahub API:** The API is a dockerised Flask API that serves two primary functions: writing data into the database and querying data from the database. The API can easily be replicated to increase capacity, service multiple clusters of collectors, or to write into more than one database instance.

The `write` endpoint conducts checks of data integrity before writing it into the database. The `query` endpoint provides arguments allowing historical data collections to be easily queried for a range of dates or other data characteristics. Additional endpoints are provided that provide queried data in cleaner formats and to provide basic monitoring of ongoing collections.

**Crawler:** The crawler is a dockerised Python process that simply reads the csv files from one or more collectors, processes each row of data, and writes it into the database through the API while keeping logs of any errors that arise for individual rows of data. The crawler can be launched with numerous replicas defined in its `docker-compose.yml` to increase crawl capacity. 

# Repo Organisation

**./config/**  The config folder contains files need to configure data collection specifications and API access credentials. 

**./config/collections/** The collections folder contains scripts that generate all of the files needed to configure a mySocialWatcher collector. 

**./config/specs/** The specs folder contains examples of collection specs that have been used to configure collectors for various projects to provide templates for future work. 

**./config/private/** This folder is excluded from GitHub for privacy reasons. It contains access tokens for Meta's API, datahub credentials, and datahub API tokens needed for write-access to the database. It may also include email configurations for email-based notifications of collector warnings and errors. The folder `./config/_example_private/` provides an example of the files that may be included here. 

**./data/** This folder is excluded from GitHub for data protection purposes. Data created by collectors and crawlers are saved here. 

**./docker/** The docker folder contains all of the docker files to build collecters, crawlers, datahub databases, and datahub APIs for specific projects. 

**./mySocialWatcher/** Source code for all mySocialWatcher components.

**./pySocialWatcher/** Source code for all pySocialWatcher components, built on top of the original source code from Aruajo et al. (2017).

**./scratch/** Scratch workspace for code used in testing or other purposes. 

**./utils/** Bash scripts used to help monitor servers running mySocialWatcher components.

# Usage

### Collectors

One or more collectors can be configured using the following steps (see existing collectors for specific examples):
1. Create a folder for your new collector in `./docker/collectors/`. 
2. Create a `docker-compose.yml` to define one or more containers that will each run a collector. 
3. Create a sub-folder for each collector using the same path that you defined for the collector in the `docker-compose.yml`. 
4. Add one or more collection specs in JSON format into the collector sub-folders. See `./config/specs/` for examples. 
5. Add a file named `credentials.csv` to each collector sub-folder. This should contain the Meta API token and app ID--separated by a comma--that you want to use for this collection. 
6. If you specified the build arg `email_notification=TRUE` in your docker-compose, then you must include a `yagmail.csv` in the collector sub-folder to provide credentials for sending email notifications. See `./config/_example_private/yagmail.csv` for an example. 
7. (optional) Create a bash script `deploy.sh` in your primary collector folder to document steps used to configure the collectors on a remote server.
8. (optional) Create a `collector_crontab` file to document the cron scheduling used for the collector. 
9. (optional) Collection specs (JSON) and scripts used to generate all of the required collector configuration files can be saved into `./config/` for future use.  

Once all of the collector configuration files are in place, you can launch the containers as background instances using `docker compose up -d` from within the collector directory.

### Datahub (database + API)
The datahub requires an environment file to exist in `./docker/datahub/.env` that defines database and API credentials. See `./docker/datahub/env_example` for an example. 

The database and API can be launched as background processes by executing `docker compose up -d` from within `./docker/datahub/`. 

Once running the API can be accessed from `https://localhost/api/v1` and the database connection is available on localhost port 5432.

For the routine logical-backup workflow used with Borg, see
[Datahub logical backups](docs/datahub-backups.md).

### Crawlers
The crawlers require an environment file to exist in `./docker/crawler/.env` to define a data directory and datahub API credentials.

Production uses API v2 and the file registry. The API token must have write access because both batch ingestion and registry claims are authenticated writes. The essential settings are:

```dotenv
DATA_DIR=data
CRAWLER_REPLICAS=4
API_URL=http://serenity/socialwatcher/v2/write-batch
API_BATCH_SIZE=500
REGISTRY_URL=http://serenity/socialwatcher/v2
REGISTRY_LEASE_SECONDS=900
CRAWLER_INSTANCE=daily-crawler
```

Interactive API v2 documentation is available internally at
`http://serenity/socialwatcher/v2/docs`. Public routing will be enabled after
the remaining v2 endpoints are complete in issue #10.

A single crawler can be launched as a background process by executing `docker compose up -d` from `./docker/crawler/`.

Many crawlers can be launched simultaneously using `docker compose up -d` from `./docker/crawler/`. Set `CRAWLER_REPLICAS` in `./docker/crawler/.env` to choose the number of crawlers; it defaults to four and can be set to one when desired.

The registry is always the crawler's completion authority. The crawler considers every eligible source file by modification time, newest first, skips content already completed in the registry, and writes reports beneath `data/crawler/registry/` without changing legacy completion logs. This allows the routine midnight restart to process newly synced files first and then continue backward through uncrawled history. Registry claims also coordinate replicas and recover expired work after interruption, so runs do not create `temp.txt` markers.

Before hashing candidates, the crawler performs registry preflight checks in batches of up to 1,000 using relative path, compressed size, and modification time. An unchanged path completed after that modification time is skipped without reading the file. New, moved, or modified files still use the decompressed SHA-256 identity, so path preflight is only an optimization and does not replace content verification.

Unreadable gzip archives do not stop the crawl. The crawler writes a `*_corrupt.json` diagnostic beneath `data/crawler/registry/`, skips that archive while its size and modification time remain unchanged, and retries it automatically after replacement or modification.

Optionally limit any crawl with `CRAWL_DATE_FROM`, `CRAWL_DATE_TO`, and/or `CRAWL_PATH_PREFIX` relative to `DATA_DIR`. Date bounds are inclusive and use the `YYYYMMDD` crawl date at the end of each source filename. Omitting all filters selects every eligible source file. For example:

```dotenv
CRAWL_DATE_FROM=2026-11-01
CRAWL_DATE_TO=2026-11-11
# CRAWL_PATH_PREFIX=serenity/migration_asia_pacific/
```

Use a stable `CRAWLER_INSTANCE` for operational reporting. The registry identifies file content by its decompressed SHA-256 hash; moving or recompressing identical content does not cause it to be ingested again.

### Crawler operations and recovery

The database registry is production's authoritative completion state. CSV reports under `data/crawler/registry/` are durable diagnostics and should be retained, but deleting or moving one does not make completed content eligible again. Older reports elsewhere under `data/crawler/` are legacy diagnostics. The recovery utilities below predate registry enforcement and remain useful for inspecting or extracting rows from those logs; they do not change registry completion state. Run commands from the repository root.

#### Starting crawlers and cleaning temporary markers

`daily_crawl.sh` synchronises collection data, stops the crawlers, removes stale `*temp.txt` claim files, and starts the configured replicas:

```bash
bash utils/daily_crawl.sh "$PWD"
```

Use `daily_crawl_nosync.sh` when the source data are already current and no `rsync` is needed:

```bash
bash utils/daily_crawl_nosync.sh "$PWD"
```

Both scripts require the repository path as their argument. The synchronisation script excludes directories named `logs` at any depth. `logs_cleanup.sh` only manages collector `*.log` and `*.log.gz` files beneath those `logs` directories; it does not remove crawler completion logs such as `*_log.csv.gz`.

The production cron job runs `daily_crawl.sh` at midnight. Its stop-and-start cycle prioritizes newly synchronized files, then resumes older registry work. To start a controlled date-limited crawl after editing `.env`, use `daily_crawl_nosync.sh` when no source synchronization is needed. Restarting the same range is safe: completed content is skipped and interrupted claims become retryable after their lease expires.

#### Reporting historical failures

`report_crawler_failures.py` scans crawler logs without changing them. It summarizes status codes and common failure categories, including invalid JSON, missing MAU values, missing database partitions, authentication failures, and database connection failures.

Run it across all available crawler logs:

```bash
python3 utils/report_crawler_failures.py data/crawler
```

Use UTC modification-time boundaries to inspect a calendar period. The lower boundary is inclusive and the upper boundary is exclusive:

```bash
python3 utils/report_crawler_failures.py data/crawler \
  --modified-after 2026-01-01 \
  --modified-before 2026-04-01 \
  --output crawler-recovery/reports/crawler-failures-2026-Q1.csv
```

The CSV groups failures by log modification year, collection path, status, and error category. It includes affected row and file counts plus one sample message. `--top N` controls how many categories are printed in the terminal. A nonzero exit status indicates that corrupt or unreadable logs were encountered; those logs can be handled with the quarantine utility below.

#### Quarantining complete failed logs

`quarantine_crawler_logs.py` finds legacy completion logs containing non-2xx responses other than the expected `409 Conflict`. Moving a log no longer triggers production reprocessing when its content is complete in the registry. Use date/path filters for a controlled registry crawl; registry state must be handled explicitly if completed content truly needs to be replayed.

Preview recent candidates first:

```bash
python3 utils/quarantine_crawler_logs.py data/crawler \
  --ignore-status 400 401 \
  --max-age-days 30 \
  --limit 100
```

Stop the crawlers before moving logs, then repeat with `--move`:

```bash
python3 utils/quarantine_crawler_logs.py data/crawler \
  --ignore-status 400 401 \
  --max-age-days 30 \
  --limit 100 \
  --move
```

Moved logs retain their relative paths under a timestamped directory in `crawler-recovery/log-quarantine/`. Source CSV files are not moved. Corrupt logs qualify regardless of ignored statuses because their row results cannot be trusted.

#### Extracting only failed rows

`extract_failed_crawler_rows.py` creates a small retry dataset containing selected source rows. It leaves the original source files and completion logs unchanged, so the normal crawler does not reprocess the full files. Original source files must remain unchanged because crawler-log indices refer to parsed row positions.

The default is a preview. This example selects recent JSON-related `400` errors while excluding other deliberate validation failures:

```bash
python3 utils/extract_failed_crawler_rows.py data \
  --status 400 \
  --message-contains "is not a valid json" \
  --max-age-days 14
```

Add `--write` after reviewing the preview:

```bash
python3 utils/extract_failed_crawler_rows.py data \
  --status 400 \
  --message-contains "is not a valid json" \
  --max-age-days 14 \
  --write
```

The command prints a `Retry data root` beneath `crawler-recovery/retry-data/`. Each batch mirrors the source directory layout and includes `manifest.jsonl`, which maps retry rows to their original source paths and row positions. Other useful filters are:

- `--status 500 502 503 504` to include only listed statuses.
- `--ignore-status 400 401` to exclude listed statuses.
- `--message-contains TEXT` to match an API error message; repeat the option to accept alternative messages.
- `--limit N` to stop after selecting N source files, newest first.
- `--max-age-days N` to filter by crawler-log modification time, not the collection date in a filename.
- `--modified-after DATETIME` to include logs at or after a UTC boundary.
- `--modified-before DATETIME` to include logs before a UTC boundary.

Date boundaries accept `YYYY-MM-DD` or ISO 8601 timestamps. They can be used to create non-overlapping monthly or quarterly historical recovery batches. If age and date filters are combined, a log must satisfy all of them.

#### Crawling an isolated retry batch

Keep the normal crawlers stopped while running a controlled recovery. Set the batch path printed by the extraction utility and obtain the existing crawler image:

```bash
RETRY_DIR=/absolute/path/to/crawler-recovery/retry-data/<batch-name>
CRAWLER_IMAGE=$(docker compose \
  -f docker/crawler/docker-compose.yml \
  images -q crawler)
```

Run one retry crawler:

```bash
docker run --rm \
  --network host \
  --user "$(id -u):$(id -g)" \
  -v "$RETRY_DIR:/app/data" \
  -v "$PWD/docker/crawler/.env:/app/.env:ro" \
  "$CRAWLER_IMAGE"
```

For a large recovery batch, start four detached containers using the same retry directory. Production registry claims ensure that only one crawler processes each file:

```bash
for replica in 1 2 3 4; do
  docker run -d --rm \
    --network host \
    --user "$(id -u):$(id -g)" \
    -v "$RETRY_DIR:/app/data" \
    -v "$PWD/docker/crawler/.env:/app/.env:ro" \
    "$CRAWLER_IMAGE"
done
```

Retry completion logs are written beneath `$RETRY_DIR/crawler/registry`. Check them with:

```bash
python3 utils/quarantine_crawler_logs.py "$RETRY_DIR/crawler"
```

If the utility selects nothing, every retry row returned a successful 2xx response or the expected `409` duplicate response.

#### Updating the recovery ledger

Original completion logs remain unchanged after row-level recovery. `update_crawler_recovery_ledger.py` maps successful retry results back to their original source rows so later extraction runs do not select them again:

```bash
python3 utils/update_crawler_recovery_ledger.py crawler-recovery/retry-data
```

The command creates or updates `crawler-recovery/retry-data/recovery-ledger.jsonl`. Only retry results with a 2xx or `409` status are recorded; failed and incomplete retries remain eligible for extraction. The operation is idempotent, and `extract_failed_crawler_rows.py` consults this ledger automatically. Keep completed retry batches as the detailed audit trail. Run the ledger update after every retry batch before performing another extraction.

#### Archiving successful source and log pairs

`archive_successful_crawler_files.py` identifies source files whose crawler logs are complete and contain only:

- `200` successful writes;
- `409` rows already present in the database;
- the intentional `400` rejection for rows missing all MAU values; or
- other failures whose original source rows are recorded as successfully recovered in the recovery ledger.

The utility validates that the source and log have the same number of rows. Its default is a read-only preview, ordered from the oldest log to the newest:

```bash
python3 utils/archive_successful_crawler_files.py \
  data /mnt/cold-storage/mySocialWatcher \
  --min-age-days 90 \
  --limit 100
```

Stop the crawlers, mount the external drive, verify the preview, and add `--move`:

```bash
python3 utils/archive_successful_crawler_files.py \
  data /mnt/cold-storage/mySocialWatcher \
  --min-age-days 90 \
  --limit 100 \
  --move
```

The cold-storage root must already exist when using `--move`; this prevents an unmounted drive path from being created on local storage. Each source and log is copied and SHA-256 verified before either hot copy is removed. Existing files are never overwritten. The archive retains the original layout beneath `COLD_STORAGE/data/` and writes checksums and row counts to `COLD_STORAGE/transfer-manifest.jsonl`.

Use `--modified-after` and `--modified-before` for bounded archive periods. Additional acceptable `400` messages can be specified deliberately with repeated `--accept-400-message TEXT` options. The recovery ledger defaults to `crawler-recovery/retry-data/recovery-ledger.jsonl`; use `--ledger PATH` if it is stored elsewhere.

# Contributing

Contributions are welcome! Thanks to everyone who has contributed already, particularly [@caseybreen](https://github.com/caseybreen), [@edarin](https://github.com/edarin), [@vallerrr](https://github.com/vallerrr), and [@mfatehkia](https://github.com/mfatehkia)!

Please feel free to fork the repo, open issues, and submit pull requests to help resolve issues. 

# License
You are free to use, modify, and share the code in this repository under the terms of a [GNU General Public License v3](https://www.gnu.org/licenses/quick-guide-gplv3.html) (see `./LICENSE` file for full terms of license).

Database schema history is maintained in `docker/datahub/migrations/`. Clean
initialization and existing-database upgrades use the same migration runner; see
[the API v2 database foundation notes](docs/api-v2.md#file-registry-database-foundation-issue-5)
for explicit legacy adoption and isolated rebuild testing. Production crawler
completion and replica coordination are registry-based. The unchanged pre-registry
crawler is archived in Git tag `legacy-crawler-pre-registry`.
