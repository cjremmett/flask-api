from flask import Response, request
from mailjet_rest import Client
from redis_tools import get_secrets_dict
from utils import append_to_log, get_postgres_cursor_autocommit, get_postgres_timestamp_now, execute_postgres_query, get_sql_formatted_list, get_uuid, authorized_via_redis_token
import pandas as pd
from typing import Optional, Iterable
GMAIL_OUTGOING_EMAIL_TABLE = 'outgoing_emails'
            

def send_mailjet_message(from_email, from_name, to_email, to_name, subject, text_part, html_part):
   try:
      secrets_dict = get_secrets_dict()
      mailjet = Client(auth=(secrets_dict['secrets']['mailjet']['api_key'], secrets_dict['secrets']['mailjet']['api_secret']), version='v3.1')
      data = {
      'Messages': [
                  {
                        "From": {
                              "Email": from_email,
                              "Name": from_name
                        },
                        "To": [
                              {
                                    "Email": to_email,
                                    "Name": to_name
                              }
                        ],
                        "Subject": subject,
                        "TextPart": text_part,
                        "HTMLPart": html_part
                  }
            ]
      }
      result = mailjet.send.create(data=data)
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'TRACE', 'Mailjet status code: ' + str(result.status_code) + ' Mailjet JSON: ' + str(result.json()))
   except Exception as e:
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'ERROR', repr(e))


def queue_gmail_message(module: str, recipient: str, subject: str, body: str) -> str:
   try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         message_id = get_uuid()
         email = pd.DataFrame({
            'created_timestamp': [get_postgres_timestamp_now()],
            'module': [module],
            'recipient_address': [recipient],
            'subject': [subject],
            'text_body': [body],
            'message_id': [message_id]
         })
         email.to_sql(name='outgoing_emails', con=cursor, if_exists='append', index=False)
         return message_id
   except Exception as e:
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'ERROR', repr(e))


def get_queued_gmail_messages(unsent_only: Optional[bool] = True) -> pd.DataFrame:
   try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         query = 'select * from ' + GMAIL_OUTGOING_EMAIL_TABLE + ' emails'
         if unsent_only:
            query += ' where emails.sent_timestamp is null'
         df = pd.read_sql_query(query, con=cursor)
         return df
   except Exception as e:
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'ERROR', repr(e))


def mark_gmail_emails_sent(message_ids: Iterable[str]) -> None:
   try:
      update_query = 'update ' + GMAIL_OUTGOING_EMAIL_TABLE + " set sent_timestamp = '" + get_postgres_timestamp_now() + "' WHERE message_id in " + get_sql_formatted_list(message_ids) + ';'
      execute_postgres_query(update_query)
   except Exception as e:
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'ERROR', repr(e))


def gscript_get_emails_to_send():
   # Get unsent messages and return them to Gmail for sending.
   # Could use some improvements, like getting confirmation from Gmail the message was sent before marking it sent.
   try:
      if not authorized_via_redis_token(request, 'email_tools'):
         return ('', 401)
      
      df = get_queued_gmail_messages(unsent_only=True)
      
      # Mark the messages sent
      if (len(df) > 0):
            message_ids = df['message_id'].tolist()
            mark_gmail_emails_sent(message_ids)

      return Response(df.to_json(orient="records"), status=200, content_type='application/json')

   except Exception as e:
      append_to_log('flask_logs', 'EMAIL_TOOLS', 'ERROR', repr(e))