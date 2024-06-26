from datetime import datetime, timezone
import time
import pandas as pd
import sqlalchemy
from typing import Iterable
import uuid
from redis_tools import get_secrets_dict
# Need to pip install psycopg2-binary or the postgres writes will throw.


def get_postgres_engine(database):
   try:
      # Postgres is not port forwarded so hardcoded login should be fine
      return sqlalchemy.create_engine("postgresql+psycopg2://admin:pass@localhost:5432/" + database)
   except Exception as e:
      print('Getting Postgres engine failed. Error:' + repr(e))
      raise Exception('Failed to get SQLAlchemy Postgres engine.')
   

def get_postgres_cursor_autocommit(database):
   return get_postgres_engine(database).connect().execution_options(isolation_level="AUTOCOMMIT")


def append_to_log(table, category, level, message):
   try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         log_line = pd.DataFrame({
            'timestamp': [get_postgres_timestamp_now()],
            'category': [category],
            'level': [level],
            'message': [message]
         })
         log_line.to_sql(name=table, con=cursor, if_exists='append', index=False)
   except Exception as e:
      print('Writing to log failed. Error:' + repr(e))


def log_resource_access(location, ip_address):
   try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         log_line = pd.DataFrame({
            'timestamp': [get_postgres_timestamp_now()],
            'location': [location],
            'ip_address': [ip_address]
         })
         log_line.to_sql(name='resource_access_logs', con=cursor, if_exists='append', index=False)
   except Exception as e:
      print('Writing to resource access log failed. Error:' + repr(e))
   

def get_epoch_time():
   return str(time.time())


def get_calendar_datetime_utc_string():
   return datetime.now(timezone.utc).strftime('%m/%d/%y %H:%M:%S')


def get_postgres_timestamp_now() -> str:
   # Use this function to get the timestamp string everywhere to ensure the format is consistent across functions and tables
   return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")

def get_postgres_date_now() -> str:
   # Use this function to get the date string everywhere to ensure the format is consistent across functions and tables
   # Use for date data type in Postgres
   # e.g. 2024-06-15
   return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def execute_postgres_query(query: str) -> None:
   try:
      with get_postgres_cursor_autocommit('cjremmett') as cursor:
         cursor.execute(get_sqlalchemy_query_text(query))
   except Exception as e:
      print('Exception thrown running the following SQL query:\n\n' + query + '\n\nError:' + repr(e))


def get_sql_formatted_list(items: Iterable[str]) -> str:
   try:
      if items == None or len(items) == 0:
         return "('')"
      
      sql = "("
      for item in items:
         sql += "'" + item + "',"
      sql = sql[:-1]
      sql += ")"
      return sql
   except Exception as e:
      append_to_log('flask_logs', 'UTILS', 'ERROR', repr(e))


def get_sqlalchemy_query_text(query: str) -> sqlalchemy.sql.elements.TextClause:
   try:
      return sqlalchemy.text(query)
   except Exception as e:
      append_to_log('flask_logs', 'UTILS', 'ERROR', repr(e))


def get_uuid() -> str:
   return str(uuid.uuid4())


def authorized_via_redis_token(request, module:str) -> bool:
    try:
        api_token = request.headers.get('token')
        secrets = get_secrets_dict()
        if api_token == secrets['secrets'][module]['api_token']:
            return True
        else:
            return False
    except Exception as e:
        append_to_log('flask_logs', 'UTILS', 'WARNING', 'Exception thrown in authorization check: ' + repr(e))
        return False


def get_heartbeat():
   return('', 200)