from flask import Flask, request
import email_tools
import gafg_tools
import utils
import photography_tools
import werkzeug
import dynamic_dns
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_socketio import SocketIO
from flask_cors import CORS

app = Flask(__name__)
socketio = SocketIO(app, path='/flask/socket.io', cors_allowed_origins='*')
CORS(app)

# Boilerplate code to trust the proxy remote IP
# https://flask.palletsprojects.com/en/2.3.x/deploying/proxy_fix/
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

@app.before_request
def before_request():
    try:
        utils.log_resource_access(request.url, request.remote_addr)
    except:
        print('Failed to log URL and IP address for incoming request. Request stopped.')
        return ('', 500)

# Utils
app.add_url_rule('/flask', view_func=utils.get_heartbeat, methods=['GET'])

# GAFG Tools
app.add_url_rule('/flask/gafg-tools/ioffice-checkin', view_func=gafg_tools.ioffice_checkin, methods=['POST'])
app.add_url_rule('/flask/gafg-tools/ioffice-checkin-user-update-settings', view_func=gafg_tools.update_gafg_checkin_user_account, methods=['PUT'])
app.add_url_rule('/flask/gafg-tools/trigger-manual-checkin-reminder', view_func=gafg_tools.trigger_manual_checkin_reminder, methods=['POST'])
app.add_url_rule('/flask/gafg-tools/get-resource-access-logs', view_func=gafg_tools.get_resource_access_logs, methods=['GET'])
app.add_url_rule('/flask/gafg-tools/sample-data', view_func=gafg_tools.get_sample_data, methods=['GET'])
app.add_url_rule('/flask/gafg-tools/submit-sample-stock', view_func=gafg_tools.submit_sample_stock, methods=['POST'])
app.add_url_rule('/flask/gafg-tools/get-sample-portfolio', view_func=gafg_tools.get_sample_portfolio, methods=['GET'])

# Email Tools
app.add_url_rule('/flask/email-tools/get-outgoing-gscript-emails', view_func=email_tools.gscript_get_emails_to_send, methods=['GET'])

# [Unit]
# Description=Gunicorn Flask Server

# [Service]
# Type=simple
# WorkingDirectory=/home/cjr/flask
# Environment="PATH=/home/cjr/flask/bin"
# ExecStart=/home/cjr/flask/bin/gunicorn --chdir /home/cjr/flask/api/ wsgi:app --bind 0.0.0.0:5000 --worker-class eventlet -w 1

# [Install]
# WantedBy=multi-user.targets