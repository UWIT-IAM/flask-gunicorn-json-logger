# uw-it-flask-gunicorn-json-logger

This is a flask extension that configures
logging for applications running behind
gunicorn.

By default, when running behind gunicorn, all logging
goes to the `gunicorn.error`
log, which is misleading, and also can show up as
errors in other contexts.

This extension logs to a special child of the 
default: `gunicorn.error.app` and comes with the
logging configuration to emit 
the `.app` logstream as json so that it can be 
directly queried and examined without guesswork.

Each log statement handled by the `JsonFormatter`
will have additional information appended based on 
the request/session status at the time the statement
was issued.

The output json will filter out the `gunicorn.error`
string from the logger name, so that any children of
your app logger will also be 
free of the misleading "error" context, 
which allows you to scope and process logs easily.

## Installation

`pip install uw-it-flask-gunicorn-logger`

## Basic use

You can use this extension with minimal configuration for default use cases:

```python
from flask import Flask
from uw_it.flask_util.logger import FlaskJSONLogger
app = Flask(__name__)
FlaskJSONLogger(app)
app.logger.info("Info statement!")
```

This would generate a log that looked like:

```
{
  "severity": "INFO",
  "message": "Info statement!",
  "line": "example.py#__main__:5",
  "logger": "app",
  "thread": 123,
}
```

### Session & Request Info

If your log was created inside a request context, request information 
will be appended also: 

```python
from flask import Flask, request, session
from uw_it.flask_util.logger import FlaskJSONLogger

app = Flask(__name__)
app.config.setdefault('LOG_SESSION_USER_KEY', 'username')
FlaskJSONLogger(app)

@app.route('/')
def index():
    username = request.headers.get('X-Forwarded-User') or session.get('username')
    session['username'] = username
    if username:
        app.logger.info(f"User {username} is here!")
        return f'Hello, {username}', 200
    else:
        app.logger.warning("An unauthorized user attempted access!")
        return 'Unauthorized', 401
```

Now, the log output would look something like this for a signed in user:

```
{
  "severity": "INFO",
  "message": "User guest is here!",
  "line": "app.py#index:5",
  "logger": "app",
  "thread": 123,
  "request": {
    "method": "GET",
    "url": "http://localhost:5000",
    "remoteIp": "127.0.0.1",
    "id": 123456789,
    "username": "guest"
  }
}
```

### Adding extra annotations

You can also add any extra annotations that you like,
by using the `extra` argument on the log statement. 
This will allow you to access arbitrary contextual 
data from within your logs:

```
import flask
app = flask.Flask(__name__)


@app.route("/submit", methods=("POST",))
def submit_form():
    form_data = request.form
    app.logger.info("Processing form", extra={"formData": form_data})
```

The above snippet would append something like this to your output:

```
{
  "severity": "INFO",
  "message": "Processing form",
  "line": "app.py#index:5",
  "logger": "app",
  "thread": 123,
  "request": {
    "method": "POST",
    "url": "http://localhost:5000/submit",
    "remoteIp": "127.0.0.1",
    "id": 123456789,
  },
  "formData": {
      "name": "Lee Vit",
      "age": 42,
      "favoriteColor": "suprablue",
  }
}
```

### Adding timers

You can add timers to your request methods to get
the full snapshot of, for instance, request payload, user,
and the time a certain operation took. This can be
very helpful for finding bottlenecks!

In the [example app](#running-the-example-app) you can use the `/timeout/5` path
to simulate a long query that breaches a timing threshold and 
generates the appropriate logs.

Let's extend the above example and add a timer:

```python
from flask import Flask
from uw_it.flask_util.logger import FlaskJSONLogger, logged_timer

app = Flask(__name__)
FlaskJSONLogger(app)

@app.route('/submit', methods=('POST',))
@logged_timer(threshold=5, namespace='slow')
def submit_form():
    # ...
```

Now, whenever our users hit the `/submit` route, 
the request will be logged to the special timer
log any time it takes longer than 5 seconds to process
the request. 

Here is an example of what this might look like:

```
{
  "severity": "WARNING",
  "message": "Timer result: 20.34",
  "line": "logger.py#logged_timer#47",
  "logger": "app.timer.slow",
  "thread": 123,
  "request": {
    "method": "POST",
    "url": "http://localhost:5000/submit",
    "remoteIp": "127.0.0.1",
    "id": 123456789,
  },
  "formData": {
      "name": "Lee Vit",
      "age": 42,
      "favoriteColor": "suprablue",
  },
  "timer": {
    "startTime": 1655225002.643874,
    "endTime": 1655225022.981268,
    "elapsedTime": 20.33739399909973,
    "timedFunc": "submit_form",
  }
}
```

## App Config Settings

The following app config settings are available for you to use:

| Setting | Description | Default |
| --- | --- | --- |
| LOG_CONFIG_FILENAME | The filename to use to load log configuration, if not the default | `uw_it/flask_util/flask_gunicorn_log_config.yml` |
| LOG_CONFIG_FILE_TYPE | Valid values are `json` and `yaml` | `yaml` |
| LOG_CONFIG_APP_LEVEL | The default level to set for the app logger | `INFO` |
| LOG_CONFIG_TRACEBACK_LIMIT | How many lines of traceback you want to include in error logs | 20 |


## Customizing Configuration

If you aren't happy with or want to extend the 
default configuration supplied by the extension, you 
copy the default configuration into your project and 
update it as desired.


```bash
python -m uw_it.flask_util.logger create_config out.yaml
```

This will output a file, `out.yaml`, with the log configuration 
copied from the default. You can override and amend this as desired.
Then, set the `LOG_CONFIG_FILENAME` app config value to `out.yaml`.

**Note**: You can use either `.json` or `.yaml` files; if you choose to use json, 
you must also set `LOG_CONFIG_FILE_TYPE` to `json`. By default, all input and output 
is assumed to be yaml.


# Querying GKE Logs

Because of the structured and predictable format of the JSON logs, they can be 
easily queried.

Using the complete example from [above](#adding-timers) as a reference, here are some 
example queries you might try:

- Show me all breaching timer results

```
jsonPayload.logger = "app.timer"
severity >= "WARNING"
```

- Show me all messages for a single request

```
jsonPayload.request.id = 123456789
```

- Show me all requests to /submit that took longer than 20 seconds to process:

```
jsonPayload.timer.timedFunc = "submit_form"
jsonPayload.timer.elapsedTime > 20
```

# Development

## Making pull requests

Pull requests are welcome. There is no automation
for releasing and reviewing at this time.

Before making a pull request, please run: `poetry run black uw_it` to format your 
code according to the `black` specifications.

## Testing

There are currently no tests. Feel free to add some, along with additional examples 
to `examples/example_app.py`.

## Publishing a new release

This is currently not automated, and operates on best intentions. 

- Update `pyproject.toml` with the new release version number
- Run `poetry update`
- Run `poetry build`
- Run `poetry publish`

The login and password for PyPI are in the
UW-IT IAM Mosler Vault.

## Running the example app

```
FLASK_ENV=development FLASK_DEBUG=1 poetry run python -m examples.example_app 
```
