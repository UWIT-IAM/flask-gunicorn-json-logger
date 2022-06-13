import json
import logging
import logging.config
import os
import threading
import traceback
from typing import Any, Dict, Literal, Optional
import yaml

import flask
from flask import Flask, Request, request
from flask.sessions import SessionMixin

ROOT_LOGGER = "gunicorn.error"

# Provides a default configuration for drop-in functionality;
DEFAULT_LOG_CONFIG = os.path.join(
    os.path.abspath(os.path.dirname(__file__)),
    'flask_gunicorn_log_config.yml'
)

# Enable pretty logging if the env is development _or_
# if the FLASK_PRETTY_JSON_LOGS environment variable is set.
PRETTY_JSON = os.environ.get(
    "FLASK_ENV", "production"
) == "development" or os.environ.get('FLASK_PRETTY_JSON_LOGS')


class JsonFormatter(logging.Formatter):
    """
    A formatter adhering to the structure advised in
    https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry.
    """

    # All of our logs must be children of the gunicorn.error log as long
    # as we continue to use gunicorn.
    root_logger: str = ROOT_LOGGER

    def __init__(self, *args, session_user_key: str = 'uwnetid', **kwargs):
        super().__init__(*args, **kwargs)
        self.session_user_key = session_user_key

    @property
    def request(self) -> Optional[Request]:
        if flask.has_request_context():
            return flask.request
        return None

    @property
    def session(self) -> Optional[SessionMixin]:
        if flask.has_request_context():
            return flask.session
        return None

    def sanitize_logger_name(self, name: str):
        """
        Removes the scary looking 'gunicorn.error' string from the logs
        so as not to confuse anyone and also have nicer looking logs.
        """
        if name.startswith(self.root_logger):
            name = name.replace(self.root_logger, "")
            if not name:
                # All gunicorn logs go to the gunicorn.error log,
                # we rename it in our json payload to make it
                # more approachable
                name = "gunicorn_worker"
            if name.startswith("."):
                name = name[1:]
        return name

    def _append_request_log(self, data: Dict[str, Any]):
        if self.request:
            request_log = {
                "method": self.request.method,
                "url": self.request.url,
                "remoteIp": self.request.headers.get("X-Forwarded-For", request.remote_addr),
                "id": id(self.request),
            }
            if self.session:
                session_user = self.session.get(self.session_user_key)
                if session_user:
                    request_log[self.session_user_key] = session_user
            if self.session and self.session.get("uwnetid"):
                request_log["uwnetid"] = self.session["uwnetid"]
            data["request"] = request_log

    @staticmethod
    def _append_custom_attrs(record: logging.LogRecord, data: Dict[str, Any]):
        if hasattr(record, "extra_keys"):
            extras = {key: getattr(record, key, None) for key in record.extra_keys}
            data.update(extras)

    @staticmethod
    def _append_exception_info(record: logging.LogRecord, data: Dict[str, Any]):
        if record.exc_info:
            exc_type, exc_message, tb = record.exc_info
            data["exception"] = {
                "message": f"{exc_type.__name__}: {exc_message}",
                "traceback": traceback.format_tb(tb, limit=20),
            }

    def format(self, record):
        data = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "line": f"{record.filename}#{record.funcName}:{record.lineno}",
            "logger": self.sanitize_logger_name(record.name),
            "thread": threading.currentThread().ident,
        }
        self._append_request_log(data)
        self._append_custom_attrs(record, data)
        self._append_exception_info(record, data)

        kwargs = {}
        if PRETTY_JSON:
            kwargs["indent"] = 4
        return json.dumps(data, default=str, **kwargs)


def configure_logger(
        log_configuration: Optional[Dict] = None,
        log_config_filename: Optional[str] = DEFAULT_LOG_CONFIG,
        log_config_file_format: Literal['json', 'yaml'] = 'yaml',
):
    if not log_configuration:
        with open(log_config_filename) as f:
            if log_config_file_format == 'json':
                log_configuration = json.load(f)
            elif log_config_file_format == 'yaml':
                log_configuration = yaml.load(f, Loader=yaml.SafeLoader)
    logging.config.dictConfig(log_configuration)


class FlaskJSONLogger:
    def __init__(self, app: Optional[Flask] = None, configuration: Optional[Dict] = None):
        self.app = app
        if app:
            self.init_app(app)
        self.config = configuration
        self.config_filename = app.config.get('LOG_CONFIG_FILENAME', DEFAULT_LOG_CONFIG)
        self.config_format = app.config.get('LOG_CONFIG_FORMAT', 'yaml')

    def init_app(self, app: Flask):
        configure_logger(
            self.config,
            self.config_filename,
            self.config_format,
        )
        app.logger = logging.getLogger('gunicorn.error').getChild('app')
