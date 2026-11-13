import os
import requests
import json
import math
import numpy
import datetime
import warnings
from uuid import uuid4
import re
from pathlib import Path
from time import sleep
import pandas as pd
from ast import literal_eval

from mysocialwatcher.crawler.batch import mark_better_estimates, submit_dataframe_v2
from mysocialwatcher.crawler.registry import CorruptArchiveError, RegistryError, RegistryObserver


CRAWL_DATE_PATTERN = re.compile(r"_(\d{8})(?:_betterestimate)?\.csv\.gz$")


def crawl_date_from_filename(path):
    match = CRAWL_DATE_PATTERN.search(os.path.basename(path))
    if not match:
        return None
    try:
        return datetime.datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def parse_crawl_date_bound(value, name):
    if value is None or isinstance(value, datetime.date):
        return value
    try:
        return datetime.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD") from exc


def normalize_path_prefix(value):
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError("CRAWL_PATH_PREFIX must be relative to DATA_DIR")
    return path.as_posix().strip('/') + '/'


def safe_http_error_message(exc, response=None):
    """Describe an HTTP failure without including request or response bodies."""
    exception = f"{type(exc).__name__}: {exc}"
    if isinstance(response, requests.models.Response):
        return f'EXCEPTION: "{exception}"; HTTP STATUS: {response.status_code}'
    return f'EXCEPTION: "{exception}"; HTTP STATUS: unavailable'


def corrupt_archive_marker_matches(marker_path, source_path):
    try:
        marker = json.loads(Path(marker_path).read_text(encoding='utf-8'))
        source = Path(source_path).stat()
        return (marker.get('archive_size'), marker.get('archive_mtime_ns')) == (
            source.st_size, source.st_mtime_ns)
    except (OSError, ValueError, TypeError):
        return False


def write_corrupt_archive_marker(marker_path, source_path, relative_path, error_type):
    source = Path(source_path).stat()
    marker = {
        'relative_path': relative_path,
        'archive_size': source.st_size,
        'archive_mtime_ns': source.st_mtime_ns,
        'detected_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'error_type': error_type,
    }
    marker_path = Path(marker_path)
    temporary = marker_path.with_name(f'{marker_path.name}.{uuid4().hex}.tmp')
    temporary.write_text(json.dumps(marker, sort_keys=True) + '\n', encoding='utf-8')
    temporary.replace(marker_path)


# def country_from_geo(geo):
#
#     country = []
#
#     if geo['name'] == 'countries':
#         country.append(geo['values'][0])
#
#     elif geo['name'] in ['regions', 'cities']:
#
#         if 'country_code' in geo.get('values')[0].keys():
#             country += [geo.get('values')[i].get('country_code') for i in range(len(geo.get('values')))]
#         elif 'PySocialWatcherReference' in geo.keys():
#             for i in range(len(geo.get('values'))):
#                 x = list(filter(lambda i: 'country:' in i, geo.get('pySocialWatcherReference').split('; ')))
#                 x = x[0].replace('country:', '')
#                 country.append(x)
#                 geo['values'][i]['country_code'] = x
#
#     return list(set(country))


def psw_to_sql(df, collection_name, token,
               valid=False,
               url='http://127.0.0.1/api/v1/write'):
    """Submit pysocialwatcher csv to /api/v1/fb/write"""

    response_timestamp = {}
    response_status = {}
    response_message = {}
    
    s = requests.Session()

    for row in df.itertuples(index=True):
        # index = 0

        index = row.Index

        # ---- platform ---- #
        platform = literal_eval(row.publisher_platforms)

        if len(platform) > 1:
            warnings.warn(f'More than one platform detected at index {index}.')
            continue
        else:
            platform = platform[0]

        # ---- all_fields ---- #
        all_fields = {k: v for k, v in literal_eval(row.all_fields)}

        # ---- targeting ---- #
        targeting = literal_eval(row.targeting)

        # ---- response ----#
        response = row.response
        if response[0] == "{":
            response = json.loads(row.response)
        elif response[0] == '[':
            response = literal_eval(row.response)
        elif response[:2] == "b\'":
            response = json.loads(literal_eval(row.response).decode('utf-8'))
        elif response[:2] == "b'":
            response = json.loads(literal_eval(row.response).decode('utf-8'))

        # ---- prepare: geo_locations ----#
        geo = all_fields['geo_locations']  # literal_eval(row.geo_locations)

        # # ---- country ----#
        # country = countries_from_geo_locations(geo)
        #
        # if len(country) == 1:
        #     country = country[0]
        # else:
        #     df.loc[index, 'timestamp_api'] = str(datetime.datetime.now())
        #     df.loc[index, 'status_api'] = 400
        #     df.loc[index, 'message_api'] = 'Bad Request: Could not identify a single country.'
        #     next

        # ---- age ---- #
        ages_ranges = literal_eval(row.ages_ranges)
        if isinstance(ages_ranges, dict):
            age_min = ages_ranges.get('min')
            age_max = ages_ranges.get('max')
        elif isinstance(ages_ranges, list):
            age_min = ages_ranges[0]
            age_max = ages_ranges[1]

        # ---- prepare API arguments ---- #
        args = {'valid': valid,
                'collection': collection_name,
                'token': token,
                'platform': platform,
                # 'country': country,
                'timestamp': row.timestamp,
                'gender': row.genders,
                'age_min': age_min,
                'age_max': age_max,
                'dau': row.dau_audience,
                'mau': row.mau_audience,
                'mau_upper': getattr(row, 'mau_audience_upper_bound', None),
                'mau_lower': getattr(row, 'mau_audience_lower_bound', None),
                'geo_locations': json.dumps(geo),
                'all_fields': json.dumps(all_fields),
                'targeting': json.dumps(targeting),
                'response': json.dumps(response)
                }

        # drop arguments with no data
        drop = []
        for i in args.keys():
            if args.get(i) is None:
                drop.append(i)
            elif isinstance(args.get(i), float) and math.isnan(args.get(i)):
                drop.append(i)
        for i in drop:
            del args[i]

        # convert numpy.int64 to int
        for arg in args.keys():
            if isinstance(args.get(arg), numpy.int64):
                args[arg] = int(args.get(arg))

        # submit api request
        http_response = ''
        try:
            # http_response = requests.get(url=url, params=args)
            # http_response = requests.post(url=url, data=args)

            request = requests.Request('POST', url, json=args)
            request_prep = request.prepare()
            http_response = s.send(request_prep)

            http_response_dict = json.loads(json.dumps(http_response.json()))

            response_timestamp[index] = http_response_dict.get('timestamp')
            response_status[index] = int(http_response_dict.get('status'))
            response_message[index] = http_response_dict.get('message')

        except Exception as e:
            message = safe_http_error_message(e, http_response)
            warnings.warn(message)

            response_timestamp[index] = str(datetime.datetime.now())
            response_status[index] = 500
            response_message[index] = message
    
    df['timestamp_api'] = df.index.map(response_timestamp)
    df['status_api'] = df.index.map(response_status)
    df['message_api'] = df.index.map(response_message)

    # return result
    return df[['timestamp_api', 'status_api', 'message_api']]
    # return df


def governor(func, hours=1):
    def wrapper(*args, **kwargs):
        start_time = datetime.datetime.now()

        func(*args, **kwargs)

        # sleep if crawl was less than an hour
        time_diff = datetime.datetime.now() - start_time
        sleep_time = datetime.timedelta(hours=hours) - time_diff
        if sleep_time.seconds > 0:
            print('[' + str(datetime.datetime.now()) + '] Sleeping for ' + str(sleep_time))
            sleep(sleep_time.seconds)

    return wrapper


def crawler(data_dir, token,
            url='http://127.0.0.1:8001/socialwatcher/v2/write-batch',
            batch_size=500, registry_url=None,
            crawler_instance='crawler', registry_lease_seconds=900,
            crawl_date_from=None, crawl_date_to=None, crawl_path_prefix=None):
    # crawl_dir = 'data/_test'

    print('-----------------------------')
    print('[' + str(datetime.datetime.now()) + '] Starting crawler...')

    data_dir = os.path.abspath(data_dir.rstrip('/'))
    crawl_dir = os.path.join(data_dir, 'crawler')
    os.makedirs(crawl_dir, exist_ok=True)
    if not registry_url:
        raise ValueError("REGISTRY_URL is required")
    if not 1 <= registry_lease_seconds <= 86400:
        raise ValueError("REGISTRY_LEASE_SECONDS must be between 1 and 86400")
    date_from = parse_crawl_date_bound(crawl_date_from, 'CRAWL_DATE_FROM')
    date_to = parse_crawl_date_bound(crawl_date_to, 'CRAWL_DATE_TO')
    if date_from and date_to and date_from > date_to:
        raise ValueError("CRAWL_DATE_FROM must not be after CRAWL_DATE_TO")
    path_prefix = normalize_path_prefix(crawl_path_prefix)
    registry = RegistryObserver(registry_url, token, crawler_instance)

    # file list
    file_list = []
    exclude_dirs = ['crawler', 'db-data']
    for (root, dirs, file) in os.walk(data_dir, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in file:
            full_path = os.path.join(root, f)
            if "finished/dataframe_collected_finished_" in full_path:
                relative = Path(full_path).relative_to(data_dir).as_posix()
                if path_prefix and not relative.startswith(path_prefix):
                    continue
                crawl_date = crawl_date_from_filename(full_path)
                if date_from and (crawl_date is None or crawl_date < date_from):
                    continue
                if date_to and (crawl_date is None or crawl_date > date_to):
                    continue
                file_list.append(full_path)
    
    # Sort by modification time, most recent first
    file_list.sort(key=os.path.getmtime, reverse=True)

    try:
        completed_files = registry.preflight(Path(data_dir), [Path(file) for file in file_list])
    except (OSError, RegistryError) as registry_error:
        raise RegistryError(str(registry_error)) from registry_error

    # ---- finished ---- #
    for file in file_list:
        # file = file_list[0]
        # file = 'C:/Users/edithd/Documents/mySocialWatcher/data/saffron/ukraine_admin2_tessellation/finished/dataframe_collected_finished_1_facebook_all_admin2_20240328.csv'

        # The registry is the completion authority. Keep its reports separate so
        # legacy completion logs remain unchanged.
        log_root = os.path.join(crawl_dir, 'registry')
        out_path = file.replace(data_dir, log_root).replace('.csv.gz', '_log.csv.gz')
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        temp_path = out_path.replace('log.csv.gz', 'temp.txt')
        error_path = out_path.replace('log.csv.gz', 'error.txt')
        checkpoint_path = out_path.replace('_log.csv.gz', '_partial_log.csv.gz')
        corrupt_path = out_path.replace('_log.csv.gz', '_corrupt.json')

        completed_fingerprint = completed_files.get(Path(file))
        if completed_fingerprint is not None:
            current = Path(file).stat()
            if completed_fingerprint == (current.st_size, current.st_mtime_ns):
                continue

        if os.path.exists(corrupt_path):
            if corrupt_archive_marker_matches(corrupt_path, file):
                continue
            Path(corrupt_path).unlink(missing_ok=True)

        print('[' + str(datetime.datetime.now()) + '] ' + file)

        attempt = None
        collection_name = file.split('/')[-3].lstrip('_')
        try:
            attempt = registry.claim(Path(data_dir), Path(file), collection_name,
                                     registry_lease_seconds)
        except CorruptArchiveError as corrupt_error:
            write_corrupt_archive_marker(
                corrupt_path, file, Path(file).relative_to(data_dir).as_posix(),
                str(corrupt_error))
            warnings.warn(f'Corrupt archive skipped: {Path(file).relative_to(data_dir)}')
            continue
        except RegistryError as registry_error:
            warnings.warn(str(registry_error))
            continue
        if attempt['decision'] in {'already_completed', 'in_progress'}:
            continue
        if os.path.exists(temp_path):
            # A successful database claim supersedes a stale legacy marker.
            os.remove(temp_path)

        try:
            # load data
            df = pd.read_csv(file)

            if "_betterestimate.csv" in os.path.basename(file):
                df = mark_better_estimates(df)

            registry.renew(attempt, registry_lease_seconds)

            # write collection to SQL via API
            response = submit_dataframe_v2(
                dataframe=df,
                collection=collection_name,
                url=url,
                token=token,
                batch_size=batch_size,
                checkpoint_path=Path(checkpoint_path),
                batch_complete=lambda: registry.renew(attempt, registry_lease_seconds))

            if attempt:
                status_counts = response['status_api'].value_counts().astype(int).to_dict()
                action_counts = response['action_api'].value_counts().astype(int).to_dict()
                complete = (len(response) == len(df)
                            and sum(action_counts.values()) == len(df)
                            and set(action_counts).issubset(
                                {'inserted', 'promoted', 'unchanged', 'rejected'}))
                outcome = ('completed_with_rejections'
                           if complete and action_counts.get('rejected', 0)
                           else 'completed' if complete else 'failed')
                try:
                    registry.finish(attempt, outcome, len(df), status_counts,
                                    action_counts,
                                    None if complete else 'non-terminal row outcomes')
                except RegistryError:
                    raise

            # Publish the durable CSV log only after an enforced attempt is finished.
            response.to_csv(out_path)
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)

        except RegistryError as e:
            warnings.warn(str(e))
            if attempt:
                try:
                    registry.finish(attempt, 'failed', None, {}, {}, type(e).__name__)
                except RegistryError as registry_error:
                    warnings.warn(str(registry_error))
        except requests.RequestException as e:
            if attempt:
                try:
                    registry.finish(attempt, 'failed', None, {}, {}, type(e).__name__)
                except RegistryError as registry_error:
                    warnings.warn(str(registry_error))
            warnings.warn(safe_http_error_message(e))
        except Exception as e:
            if attempt:
                try:
                    registry.finish(attempt, 'failed', None, {}, {}, type(e).__name__)
                except RegistryError as registry_error:
                    warnings.warn(str(registry_error))
            with open(error_path, "w") as f:
                f.write('[' + str(datetime.datetime.now()) + ']  Exception: \n' + str(e) + '\n')

print('[' + str(datetime.datetime.now()) + '] Crawler finished.')
