import time

from flask import Flask, current_app
from uw_it.flask_util.logger import FlaskJSONLogger, logged_timer

app = Flask(__name__)
app.config.setdefault(
    'LOG_CONFIG_PRETTY_JSON', '1'
)

FlaskJSONLogger(app)


@app.route('/timeout/<sleep_timer>')
@logged_timer(threshold=5)
def timer_example(sleep_timer):
    current_app.logger.info(f"Sleeping for {sleep_timer} seconds")
    time.sleep(int(sleep_timer))
    return f'<html><body>You slept for {sleep_timer} seconds</body></html>', 200


if __name__ == "__main__":
    app.run()
