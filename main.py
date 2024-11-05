from flask import Flask, request
import email_tools
import finance_tools
import gafg_tools
import utils
import werkzeug
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

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

# Finance
app.add_url_rule('/flask/finance/get-stock-price-and-market-cap-gurufocus', view_func=finance_tools.get_stock_price_and_market_cap_gurufocus, methods=['GET'])
app.add_url_rule('/flask/finance/get-forex-conversion-google', view_func=finance_tools.get_fx_rate_to_usd, methods=['GET'])

# GAFG Tools
app.add_url_rule('/flask/gafg-tools/ioffice-checkin', view_func=gafg_tools.ioffice_checkin, methods=['POST'])
app.add_url_rule('/flask/gafg-tools/ioffice-checkin-user-update-settings', view_func=gafg_tools.update_gafg_checkin_user_account, methods=['PUT'])
app.add_url_rule('/flask/gafg-tools/trigger-manual-checkin-reminder', view_func=gafg_tools.trigger_manual_checkin_reminder, methods=['POST'])
app.add_url_rule('/flask/gafg-tools/get-resource-access-logs', view_func=gafg_tools.get_resource_access_logs, methods=['GET'])
app.add_url_rule('/flask/gafg-tools/sample-data', view_func=gafg_tools.get_resource_access_logs, methods=['GET'])

# Email Tools
app.add_url_rule('/flask/email-tools/get-outgoing-gscript-emails', view_func=email_tools.gscript_get_emails_to_send, methods=['GET'])