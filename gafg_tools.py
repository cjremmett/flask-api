from flask import request, Response
from utils import append_to_log, get_postgres_cursor_autocommit, get_postgres_date_now, get_uuid, execute_postgres_query, get_sql_formatted_list, authorized_via_redis_token
from redis_tools import get_secrets_dict
from email_tools import queue_gmail_message
import requests
from typing import List, Optional
import re
import pandas as pd
from datetime import datetime
GAFG_CHECKIN_RECORDS_TABLE = 'gafg_checkin_records'
GAFG_CHECKIN_USERS_TABLE = 'gafg_checkin_users'

# The user cannot set Saturday or Sunday to true. That's only for debug purposes.
WEEKDAY_MAP = {0: 'monday', 1: 'tuesday', 2: 'wednesday', 3: 'thursday', 4: 'friday', 5: 'saturday', 6: 'sunday'}


# Be sure to check for SQL injection in user-provided email addresses because many of the functions in this module do not before constructing the SQL query
def ioffice_checkin():
    """
    POST endpoint.
    Pass the HTML source of the ioffice checkin email in JSON with the key html_source.
    Pass the from header of the email with the key sender. Expects GAFG email and name format.
    """
    try:
        if not authorized_via_redis_token(request, 'gafg_tools'):
            return('', 401)
        
        # Get the HTML source. This includes all the headers and other garbage in the email.
        json_body = request.json
        html_source = (json_body['html_source'])

        # Get the URL to make the API call to for the checkin.
        url = get_checkin_url(html_source)

        # Get the sender name and email address
        sender_email = get_sender_email(json_body['sender'])
        sender_name = get_sender_name(json_body['sender'])

        # Only allows GAFG email addresses to use this functionality.
        # If a bad email is received, it will be in the Gmail inbox for inspection.
        valid = check_if_request_valid(sender_email, sender_name)
        if not valid:
            append_to_log('flask_logs', 'GAFG_TOOLS', 'WARNING', 'Invalid email and/or sender name received. Aborting. Sender email: ' + sender_email + ' Sender name: ' + sender_name[0] + ' ' + sender_name[1])
            return('', 200)

        # Don't check anyone in unless they have exactly one account
        user_df = get_checkin_user_df(sender_email)
        if len(user_df) != 1:
            append_to_log('flask_logs', 'GAFG_TOOLS', 'WARNING', 'Did not check in ' + sender_email + ' because they do not have a GAFG checkin user account or they have multiple accounts.')
            return('', 200)
        
        # Don't check them in unless they're configured to auto check in today
        current_weekday = datetime.today().weekday()
        if user_df[WEEKDAY_MAP[current_weekday] + '_checkin'][0] != True:
            append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Did not check in ' + sender_email + ' because they disabled automatic checkin today.')
            return('', 200)

        # Don't try to check in multiple times in one day
        if(checkin_record_exists(sender_email)):
            append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Did not try to check in ' + sender_email + ' because they were already checked in today.')
            return('', 200)
        else:
            create_checkin_record(sender_email)

        # Use a GET request to trigger the checkin
        response = requests.get(url)
        append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Called ' + url + ' and got status code ' + str(response.status_code) + '.')

        if(response.status_code == 200):
            queue_gmail_message('GAFG_TOOLS', sender_email, 'Automatic iOffice Check-In Successful', 'Hello ' + sender_name[0] + ' ' + sender_name[1] + ',\n\nYou have been checked into your seat successfully.\n\nIf you no longer want to be checked in automatically, please visit cjremmett.com/ioffice to configure your account.\n\nThanks,\nAutomated Check-In Bot')
        else:
            queue_gmail_message('GAFG_TOOLS', sender_email, 'Failed Automatic Check-In', 'Hello ' + sender_name[0] + ' ' + sender_name[1] + ',\n\nAutomated seat check-in failed. Please manually check in. My apologies for any inconvenience.\n\nIf you no longer want to be checked in automatically, please visit cjremmett.com/ioffice to configure your account.\n\nThanks,\nAutomated Check-In Bot')

        return('', 201)

    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))
        return ('', 500)
    

def get_checkin_url(html_source: str) -> str:
    splits = html_source.split('https://gafg.iofficeconnect.com')
    splits = splits[1].split('" ')
    url = 'https://gafg.iofficeconnect.com' + splits[0].replace('amp;', '')
    return url


def get_sender_email(sender: str) -> str:
    # Input format: "Remmett, Christopher" <christopher.remmett@gafg.com>
    splits = sender.split('<')
    return splits[1][:-1]


def get_sender_name(sender: str) -> List[str]:
    # Input format: "Remmett, Christopher" <christopher.remmett@gafg.com>
    splits = sender.split(',')
    last_name = splits[0][1:]

    splits = splits[1].split('"')
    first_name = splits[0][1:]

    return [first_name, last_name]


def check_if_request_valid(sender_email: str, sender_name: List[str]) -> bool:
    # Check for invalid characters to prevent SQL injection and/or garbage getting inserted into the table
    # GAFG email accounts only contain alphanumeric, periods and @
    if not check_if_email_valid(sender_email) or not check_if_sender_name_valid(sender_name):
        return False
    else:
        return True


def check_if_email_valid(sender_email: str) -> bool:
    if sender_email == None or len(sender_email) < 12 or not re.match('^[a-zA-Z0-9.@]+$', sender_email) or sender_email[-9:] != '@gafg.com':
        return False
    else:
        return True
    

def check_if_sender_name_valid(sender_name: str) -> bool:
    if not re.match('^[a-zA-Z]+$', sender_name[0]) or not re.match('^[a-zA-Z]+$', sender_name[1]):
        return False
    else:
        return True
    

def create_checkin_record(email_address: str, record_date: Optional[str] = None) -> bool:
    try:
        if record_date == None:
            record_date = get_postgres_date_now()
        with get_postgres_cursor_autocommit('cjremmett') as cursor:
            record = pd.DataFrame({
                'email_address': [email_address],
                'record_date': [record_date]
            })
            record.to_sql(name=GAFG_CHECKIN_RECORDS_TABLE, con=cursor, if_exists='append', index=False)
        return True
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))
        return False


def checkin_record_exists(email_address: str, record_date: Optional[str] = None) -> bool:
    try:
        if record_date == None:
            record_date = get_postgres_date_now()
        with get_postgres_cursor_autocommit('cjremmett') as cursor:
            query = 'select count(*) from ' + GAFG_CHECKIN_RECORDS_TABLE + " records where records.record_date = '" + record_date + "' and records.email_address = '" + email_address + "'"
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG checkin exists query: ' + query)
            df = pd.read_sql_query(query, con=cursor)
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG checkin results df: ' + str(df))
            count = int(df['count'][0])
            return True if count > 0 else False
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))
        return True
    

def create_checkin_user(email_address: str) -> bool:
    try:
        existing_user_df = get_checkin_user_df(email_address)
        if len(existing_user_df) > 0:
            append_to_log('flask_logs', 'GAFG_TOOLS', 'WARNING', 'User with email address ' + email_address + ' already exists. Aborting.')
            return False
        uuid = get_uuid()
        with get_postgres_cursor_autocommit('cjremmett') as cursor:
            user = pd.DataFrame({
                'email_address': [email_address],
                'secret_key': [uuid],
                'monday_checkin': [True],
                'tuesday_checkin': [True],
                'wednesday_checkin': [True],
                'thursday_checkin': [True],
                'friday_checkin': [False],
                'saturday_checkin': [False],
                'sunday_checkin': [False]
            })
            user.to_sql(name=GAFG_CHECKIN_USERS_TABLE, con=cursor, if_exists='append', index=False)
        queue_gmail_message('GAFG_TOOLS', email_address, 'Automatic iOffice Check-In Account Created', 'Hello,\n\nYour automatic iOffice check-in acount has been created! To use this tool, please create an outlook rule to forward your iOffice check-in emails to cjriofficecheckinbot@gmail.com.\n\nPlease visit cjremmett.com/ioffice to configure which days you want to be checked in automatically. Your secret key is ' + uuid + ". Remember, don't share or lose this key! If you do, you'll have to come crawling to Joe and beg for a new one.\n\nThanks,\nAutomated Check-In Bot")
        append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Created new GAFG checkin user with email address ' + email_address + '.')
        return True
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))
        return False
    

def get_checkin_user_df(email_address: str) -> bool:
    try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         query = 'select gciu.* from ' + GAFG_CHECKIN_USERS_TABLE + " gciu where gciu.email_address = '" + email_address + "'"
         df = pd.read_sql_query(query, con=cursor)
         return df
    except Exception as e:
      append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))


def update_gafg_checkin_user_weekday_settings(email_address: str, monday_checkin: Optional[bool] = None, tuesday_checkin: Optional[bool] = None, wednesday_checkin: Optional[bool] = None, thursday_checkin: Optional[bool] = None, friday_checkin: Optional[bool] = None) -> bool:
    # Don't call this until the email address has been checked for SQL injections, the user account exists and secret key auth passed
    try:
        user_df = get_checkin_user_df(email_address)
        update_query = 'update ' + GAFG_CHECKIN_USERS_TABLE + " set monday_checkin = '" + str(monday_checkin if monday_checkin != None else user_df['monday_checkin']) + "', tuesday_checkin = '" + str(tuesday_checkin if tuesday_checkin != None else user_df['tuesday_checkin']) + "', wednesday_checkin = '" + str(wednesday_checkin if wednesday_checkin != None else user_df['wednesday_checkin']) + "', thursday_checkin = '" + str(thursday_checkin if thursday_checkin != None else user_df['thursday_checkin']) + "', friday_checkin = '" + str(friday_checkin if friday_checkin != None else user_df['friday_checkin']) + "' where email_address = '" + email_address + "';"
        append_to_log('flask_logs', 'EMAIL_TOOLS', 'TRACE', update_query)
        execute_postgres_query(update_query)
        return True
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', repr(e))
        return False


def update_gafg_checkin_user_account():
    """Get the new settings from the JSON body. Make sure the account exists and the secret key matches.

    JSON keys:
        email_address
        secret_key
        monday_checkin
        tuesday_checkin
        wednesday_checkin
        thursday_checkin
        friday_checkin
    """
    try:
        json_body = request.json

        # Make sure we won't get keyerror exception
        if 'email_address' not in json_body or 'secret_key' not in json_body or 'monday_checkin' not in json_body or 'tuesday_checkin' not in json_body or 'wednesday_checkin' not in json_body or 'thursday_checkin' not in json_body or 'friday_checkin' not in json_body:
            return("One or more required JSON keys are missing. Please use the web UI to make this API call.", 400)
        
        # Verify the email with a regex to prevent SQL injection
        if not check_if_email_valid(json_body['email_address']):
            return('Only valid GAFG email addresses are accepted.', 400)
        
        # Make sure the inputs are either True or False, then set the Python boolean data type
        for key in WEEKDAY_MAP:
            if key in json_body:
                json_value = json_body[WEEKDAY_MAP[key] + '_checkin']
                if json_value != 'True' and json_value != 'False':
                    return("Please enter either 'True' or 'False' for the weekday checkin JSON keys.", 400)
                else:
                    json_body[WEEKDAY_MAP[key] + '_checkin'] = True if json_value == 'True' else False
        
        # Check if the account exists and if the secret key matches
        user_df = get_checkin_user_df(json_body['email_address'])
        if len(user_df) != 1 or json_body['secret_key'] != user_df['secret_key'][0]:
            return('Authentication failed. Either no account with that email address exists or you entered the wrong secret key.', 400)
        
        update_gafg_checkin_user_weekday_settings(email_address=str(json_body['email_address']), monday_checkin=json_body['monday_checkin'], tuesday_checkin=json_body['tuesday_checkin'], wednesday_checkin=json_body['wednesday_checkin'], thursday_checkin=json_body['thursday_checkin'], friday_checkin=json_body['friday_checkin'])
        return ('', 200)
    except Exception as e:
      append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', 'Exception thrown in update_gafg_checkin_user_account: ' + repr(e))
      return('', 500)


def trigger_manual_checkin_reminder():
    """Call this endpoint to send a manual checkin reminder email to all users who were not automatically checked in today."""
    try:
        if not authorized_via_redis_token(request, 'gafg_tools'):
            return('', 401)
        
        current_weekday_integer = datetime.today().weekday()
        current_weekday_column = WEEKDAY_MAP[current_weekday_integer] + '_checkin'
        with get_postgres_cursor_autocommit('cjremmett') as cursor:
            # Get email addresses that were already checked in today
            record_date = get_postgres_date_now()
            query = 'select records.email_address from ' + GAFG_CHECKIN_RECORDS_TABLE + " records where records.record_date = '" + record_date + "'"
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG manual notification records query: ' + query)
            records_df = pd.read_sql_query(query, con=cursor)
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG manual notification records df: ' + str(records_df))

            # Get users who are in not list of users already checked in today
            query = 'select users.email_address from ' + GAFG_CHECKIN_USERS_TABLE + " users where users." + current_weekday_column + " = True and users.email_address not in " + get_sql_formatted_list(records_df['email_address'].tolist())
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG manual notification query: ' + query)
            user_df = pd.read_sql_query(query, con=cursor)
            append_to_log('flask_logs', 'GAFG_TOOLS', 'DEBUG', 'GAFG manual notification results df: ' + str(user_df))

        for i in range(0, len(user_df)):
            queue_gmail_message('GAFG_TOOLS', user_df['email_address'][i], 'Automatic iOffice Check-In Not Completed', "Hello,\n\nPlease be advised that you were not automatically checked in to a seat this morning. Be sure to check in manually if you reserved a seat. If you're unsure why automatic check in failed, please contact Joe for more information.\n\nIf you want to change which days you are automatically checked in, please visit cjremmett.com/ioffice to configure your account.\n\nThanks,\nAutomated Check-In Bot")
        return ('', 201)
    except Exception as e:
      append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', 'Exception thrown in trigger_manual_checkin_reminder: ' + repr(e))
      return('', 500)
    

def get_resource_access_logs():
    try:
        return ('Disabled, contact Joe to enable this.', 401)
        with get_postgres_cursor_autocommit('cjremmett') as cursor:
            query = 'select * from resource_access_logs order by timestamp desc limit 20'
            records_df = pd.read_sql_query(query, con=cursor)
            return Response(records_df.to_json(orient="records"), mimetype='application/json')
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', 'Exception thrown in get_resource_access_logs: ' + repr(e))
        return('', 500)
    

def get_sample_data():
    # Example output:
    #     {
    #     "stocks": [
    #         {
    #             "price": 100,
    #             "ticker": "AAPL"
    #         },
    #         {
    #             "price": 200,
    #             "ticker": "MSFT"
    #         },
    #         {
    #             "price": 300,
    #             "ticker": "AMZN"
    #         }
    #     ]
    # }
    try:
        return {'stocks': [{'ticker': 'AAPL', 'price': 100}, {'ticker': 'MSFT', 'price': 200}, {'ticker': 'AMZN', 'price': 300}]}
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', 'Exception thrown in get_sample_data: ' + repr(e))
        return('', 500)
    

def submit_sample_stock():
    # Example JSON: {"Ticker": "AAPL","Price": 1234}
    try:
        json_body = request.json
        if 'Ticker' in json_body and 'Price' in json_body:
            if  (json_body['Ticker'] == 'AAPL' or json_body['Ticker'] == 'MSFT' or json_body['Ticker'] == 'AMZN'):
                append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Successfully received API call with ticker ' + json_body['Ticker'] + '.')
                return('Processed OK!', 201)
        elif 'ticker' in json_body and 'price' in json_body:
            if (json_body['ticker'] == 'AAPL' or json_body['ticker'] == 'MSFT' or json_body['ticker'] == 'AMZN'):
                append_to_log('flask_logs', 'GAFG_TOOLS', 'TRACE', 'Successfully received API call with ticker ' + json_body['ticker'] + '.')
                return('Processed OK!', 201)
        else:
            append_to_log('flask_logs', 'GAFG_TOOLS', 'WARNING', 'Failed to find required fields in submit_sample_stock. Received: ' + str(json_body))
            return('Failed to find required fields in submitted JSON. You sent: ' + str(json_body), 400)
    except Exception as e:
        append_to_log('flask_logs', 'GAFG_TOOLS', 'ERROR', 'Exception thrown in submit_sample_stock: ' + repr(e))
        return('', 500)