import os
import time
from flask import request, current_app, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from mysocialwatcher.api import app, endpoints
from dotenv import load_dotenv

load_dotenv()
limiter_host = os.environ.get("LIMITER_HOST")

if not limiter_host:
    limiter_host = "datahub_limiter"

# define rate limiting
limiter = Limiter(
    app,
    key_func=get_remote_address,
    # application_limits=['60/minute', '1000/hour', '10000/day'],
    default_limits=["120/minute"],  # ['60/minute', '1000/hour', '10000/day'],
    strategy="fixed-window-elastic-expiry",
    storage_uri="memcached://" + limiter_host + ":11211",
    storage_options={},
)


@app.errorhandler(404)
def page_not_found(e):
    return f"<h1>404 Error</h1><p>The resource could not be found. {e}</p>", 404


api_name = "/socialwatcher"
api_version = "/v1"

api_root = api_name + api_version


@app.route(api_root)
def home():
    return current_app.send_static_file("docs.html")


@app.route(api_root + "/query", methods=["GET", "POST"])
def query_route():
    """API endpoint to select data from the 'social_media_audience' database."""
    args = dict(request.args)
    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.query(args)
        return jsonify(result), result.get("status")


@app.route(api_root + "/query_clean", methods=["GET", "POST"])
def query_clean_route():
    """API endpoint to select data from the 'social_media_audience' database."""
    args = dict(request.args)
    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.query_clean(args)
        return jsonify(result), result.get("status")


@app.route(api_root + "/write", methods=["GET", "POST"])
@limiter.exempt()
def write_route():
    """API endpoint to insert data into the 'social_media_audience' database."""
    # start = time.time()
    if request.method == "GET":
        args = dict(request.args)
    elif request.method == "POST":
        args = request.get_json()

    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.write(args)
        # elapsed = time.time() - start
        # current_app.logger.info(
        #     f"[{request.remote_addr}] {request.method} /write handled in {elapsed:.3f}s"
        # )
        return jsonify(result), result.get("status")


@app.route(api_root + "/list_collections", methods=["GET", "POST"])
def collections_route():
    """API endpoint to query a complete list of collection names."""
    args = dict(request.args)
    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.collections(args)
        return jsonify(result), result.get("status")


@app.route(api_root + "/monitor_collections", methods=["GET", "POST"])
def monitor_collections_route():
    """API endpoint to monitor collections."""
    args = dict(request.args)
    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.monitor(args)
        return jsonify(result), result.get("status")


@app.route(api_root + "/data_overview", methods=["GET", "POST"])
def data_overview_route():
    """API endpoint to monitor collections."""
    args = dict(request.args)
    if len(args) == 0:
        return (
            "<h1>400 Error</h1><p>Bad Request: This API endpoint requires arguments. "
            f"See <a href='{api_root}'>API documentation</a> for more information.</p>",
            400,
        )
    else:
        result = endpoints.data_overview(args)
        return jsonify(result), result.get("status")
