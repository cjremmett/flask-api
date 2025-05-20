import requests
from flask import request
import re
from utils import append_to_log, authorized_via_redis_token, get_api_key
from redis_tools import get_secrets_dict
from pymongo import MongoClient
MONGO_CONNECTION_STRING = 'mongodb://admin:admin@192.168.0.121'


def get_fx_rate_to_usd():
    """
    Query parameters:
    currency -- letter code, e.g. JPY
    """
    try:
        if not authorized_via_redis_token(request, 'finance_tools'):
            return ('', 401)
        
        # Get ticker from arguments and validate it 
        currency = request.args.get('currency')
        # Match a-zA-Z to prevent user from passing bad ticker.
        if currency == None or len(currency) < 1 or len(currency) > 4 or not re.match("^[a-zA-Z]+$", currency):
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Bad ticker submitted. Ticker: ' + str(currency))
            return ('', 400)
        
        # Get the FX conversion rate using Alpha Vantage API
        fx_rate = get_fx_conversion_rate_from_alpha_vantage(currency)

        # Return the result.
        # VBA has trouble with JSON so just send straight text back since the use case for this is displaying data in Excel.
        if fx_rate != None:
            append_to_log('flask_logs', 'FINANCE', 'TRACE', 'Got forex conversion rate successfully for currency ' + currency + '.\n\nForex conversion rate: ' + fx_rate)
            return(fx_rate, 200)
        else:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get forex conversion successfully for currency ' + currency + '.\n\nForex conversion rate: ' + str(fx_rate))
            return('', 500)

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', repr(e))
        return ('', 500)

def get_stock_price_and_market_cap_gurufocus():
    """
    Query parameters:
    ticker -- insert in Gurufocus URL.
    """
    try:
        if not authorized_via_redis_token(request, 'finance_tools'):
            return ('', 401)
        
        # Get ticker from arguments and validate it        
        ticker = request.args.get('ticker')
        # Match A-Z, a-z, 1-9 or colon to prevent user from passing bad ticker.
        if ticker == None or len(ticker) < 1 or len(ticker) > 12 or not re.match("^[a-zA-Z0-9:]+$", ticker):
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Bad ticker submitted. Ticker: ' + str(ticker))
            return ('', 400)
        ticker = ticker.upper()
        
        # Get HTML source from GuruFocus
        source = get_gurufocus_html_source(ticker)
        if source == None or len(source) < 100 or len(source) > 10000000:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get HTML source correctly from GuruFocus for ticker ' + ticker + '.')
            return ('', 500)
        
        # Get the stock price and market cap using HTML source from GuruFocus
        stock_price = get_stock_price_from_gurufocus_html_native_currency(source, ticker)
        market_cap = get_market_cap_from_gurufocus_html_native_currency(source, ticker)

        # Return the result.
        # VBA has trouble with JSON so just send straight text back since the use case for this is displaying data in Excel.
        if stock_price != None and market_cap != None:
            append_to_log('flask_logs', 'FINANCE', 'TRACE', 'Got native currency price and market cap successfully from GuruFocus for ticker ' + ticker + '.\n\nStock price: ' + stock_price + '\nMarket Cap: ' + market_cap)
            return(stock_price + ',' + market_cap, 200)
        # Handle ETFs where they have a price but no market cap
        elif stock_price != None and market_cap == None:
            append_to_log('flask_logs', 'FINANCE', 'TRACE', 'Got native currency price successfully from GuruFocus for ticker ' + ticker + '.\n\nStock price: ' + stock_price)
            return(stock_price + ',' + 'N/A', 200)
        else:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get stock price and market cap successfully for ' + ticker + '.\n\nStock price: ' + str(stock_price) + '\nMarket Cap: ' + str(market_cap))
            return('', 500)

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', repr(e))
        return ('', 500)
    

def get_gurufocus_html_source(ticker: str) -> str:
    # As of 3/1/24, GuruFocus has minimal anti-scraping measures.
    # Merely changing the user agent is enough to bypass them.
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
        response = requests.get('https://www.gurufocus.com/stock/' + ticker + '/summary', headers=headers)
        return str(response.content)
    
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', repr(e))
        return None

def get_google_fx_html_source(currency: str) -> str:
    # Google apparently does not try to stop scraping either.
    # Working 4/23/24.
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
        response = requests.get('https://www.google.com/search?q=usd+' + currency, headers=headers)
        return str(response.content)
    
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', repr(e))
        return None
    
def get_fx_conversion_rate_from_google_html_source(source: str, currency: str) -> str:
    # Does not work anymore as of 1/21/25
    # Return FX conversion rate to USD as a string, rounded to two decimal places
    # Snippet of source we're using:
    # <span class="DFlfde SwHCTb" data-precision="2" data-value="154.818">154.82</span> <span class="MWvIVe nGP2Tb" data-mid="/m/088n7"
    try:      
        split = source.split('data-value="')
        if len(split) < 2:
            return None
        
        split = split[1][0:50].split('">')
        if len(split) < 2:
            return None

        fx_rate = float(split[0])
        fx_rate = round(fx_rate, 2)
        return str(fx_rate)

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get forex conversion rate correctly from Google HTML source for currency ' + currency + '.')
        return None
    
def get_fx_conversion_rate_from_alpha_vantage(currency: str) -> str:
    # JSON looks like this:
    # {'Realtime Currency Exchange Rate': {'1. From_Currency Code': 'USD', '2. From_Currency Name': 'United States Dollar', 
    # '3. To_Currency Code': 'JPY', '4. To_Currency Name': 'Japanese Yen', '5. Exchange Rate': '155.53900000', 
    # '6. Last Refreshed': '2025-01-21 15:20:01', '7. Time Zone': 'UTC', '8. Bid Price': '155.53250000', '9. Ask Price': '155.54310000'}}
    try:
        api_key = get_api_key('alpha_vantage')
        response = requests.get('https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency=USD&to_currency=' + currency + '&apikey=' + api_key)
        resp_json = response.json()
        fx_rate = float(resp_json['Realtime Currency Exchange Rate']['5. Exchange Rate'])
        fx_rate = round(fx_rate, 2)
        return str(fx_rate)
    
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get forex conversion rate from Alpha Vantage for currency ' + currency + '. ' + repr(e))
        return None

def get_stock_price_from_gurufocus_html_native_currency(source: str, ticker: str):
    # Return the stock price in the native currency
    # Snippet of source we're using:
    # What is Las Vegas Sands Corp(LVS)\'s  stock price today?\n      </span> <div class="t-caption t-label m-t-sm m-b-md" data-v-00a2281e>\n        The current price of LVS is $51.65.
    # The current price of MIC:SBER is \xe2\x82\xbd292.19.
    try:      
        split = source.split('The current price of ')
        if len(split) < 2:
            # Handle ETF case - the page has different formatting
            # Snippet looks like: 
            # ;aA.pretax_margain=a;aA.price=100.3201;aA.price52whigh=100.67;
            split = source.split('.price=')
            if len(split) < 2:
                return None
            else:
                price = split[1].split(';')[0]
                return str(round(float(price), 2))
        
        split = split[1][0:50].split(' ')
        if len(split) < 3:
            return None

        stock_price = split[2][0:-1]
        for i in reversed(range(0, len(stock_price))):
            if ord(stock_price[i]) != 46 and (ord(stock_price[i]) < 48 or ord(stock_price[i]) > 57):
                return stock_price[i+1:]

        return None

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get stock price correctly from GuruFocus HTML source for ticker ' + ticker + '. Error:\n' + repr(e))
        return None


def get_market_cap_from_gurufocus_html_native_currency(source: str, ticker: str):
    # Return the market cap in billions in the native currency

    try:
        splits = source.split('Market Cap:')
        if len(splits) < 2:
            return None
        
        splits = splits[1].split('<span ')
        if len(splits) < 2:
            return None
        
        splits = splits[1].split('</span>')
        if len(splits) < 2:
            return None
        
        stock_market_cap_letter = splits[0][-1].upper()

        # Looks like data-v-4e6e2268>HK$ 3.56
        market_cap_str = splits[0][:-1]

        for i in reversed(range(0, len(market_cap_str))):
            if ord(market_cap_str[i]) != 46 and (ord(market_cap_str[i]) < 48 or ord(market_cap_str[i]) > 57):
                market_cap_float = market_cap_str[i+1:]
                break
        stock_market_cap_float = float(market_cap_float)
        
        if stock_market_cap_letter == 'B':
            return str(stock_market_cap_float)
        elif stock_market_cap_letter == 'M':
            return str(round(stock_market_cap_float / 1000, 2))
        elif stock_market_cap_letter == 'T':
            return str(round(stock_market_cap_float * 1000, 2))
        else:
            raise Exception('Unkown letter following market cap.')
        
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get market cap correctly from GuruFocus HTML source for ticker ' + ticker + '. Error:\n' + repr(e))
        return None
    

def get_api_ninjas_api_key() -> str:
    try:
        secrets_dict = get_secrets_dict()
        return secrets_dict['secrets']['api-ninjas']['api_key']
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Exception thrown in get_api_ninjas_api_key: ' + repr(e))
        return ''


def get_earnings_call_transcript_from_db(ticker: str, year: int, quarter: int) -> str:
    """
    Queries MongoDB to check if a record exists with matching ticker, year, and quarter.
    Returns the contents of the transcript field if the record exists, otherwise returns an empty string.

    :param ticker: The stock ticker symbol (e.g., 'GOOGL').
    :param year: The year of the earnings call (e.g., 2027).
    :param quarter: The quarter of the earnings call (e.g., 4).
    :return: The transcript as a string if found, otherwise an empty string.
    """
    try:
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["finance"]
        collection = db["earnings_call_transcripts"]

        # Query the database
        query = {"ticker": ticker, "year": year, "quarter": quarter}
        record = collection.find_one(query)

        # Return the transcript if the record exists
        if record and "transcript" in record:
            return record["transcript"]
        else:
            return ""

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Error querying MongoDB: {repr(e)}")
        raise Exception(f"Error querying MongoDB: {repr(e)}")

    finally:
        client.close()


def upsert_earnings_call_transcript(ticker: str, year: int, quarter: int, transcript: str) -> bool:
    """
    Upserts an earnings call transcript record into MongoDB.
    If a record with the same ticker, year, and quarter exists, it updates the transcript field.
    Otherwise, it inserts a new record.

    :param ticker: The stock ticker symbol (e.g., 'GOOGL').
    :param year: The year of the earnings call (e.g., 2027).
    :param quarter: The quarter of the earnings call (e.g., 4).
    :param transcript: The transcript content to store.
    :return: True if the operation is successful, False otherwise.
    """
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["finance"]
        collection = db["earnings_call_transcripts"]

        # Upsert the record
        query = {"ticker": ticker, "year": year, "quarter": quarter}
        update = {"$set": {"transcript": transcript}}
        result = collection.update_one(query, update, upsert=True)

        # Return True if the operation was successful
        return result.acknowledged

    except Exception as e:
        # Log the error
        append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Error upserting MongoDB record: {repr(e)}")
        return False

    finally:
        # Close the MongoDB connection
        client.close()


def get_earnings_call_transcript_from_api_ninjas(ticker: str, year: int, quarter: int) -> str:
    """
    Fetches the earnings call transcript from the API Ninjas service.
    Returns the transcript as a string.

    :param ticker: The stock ticker symbol (e.g., 'GOOGL').
    :param year: The year of the earnings call (e.g., 2027).
    :param quarter: The quarter of the earnings call (e.g., 4).
    :return: The transcript as a string.
    """
    try:
        api_key = get_api_ninjas_api_key()
        api_url = f'https://api.api-ninjas.com/v1/earningstranscript?ticker={ticker}&year={year}&quarter={quarter}'
        headers = {'X-Api-Key': api_key}
        response = requests.get(api_url, headers=headers)

        if response.status_code == requests.codes.ok:
            data = response.json()
            return data['transcript'] if 'transcript' in data else ""
        else:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Error fetching transcript for {ticker} {year} {quarter} from API Ninjas: {response.status_code}")
            return ""

    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Exception fetching transcript for {ticker} {year} {quarter} from API Ninjas: {repr(e)}")
        return ""
    

def get_earnings_call_transcript(ticker: str, year: int, quarter: int) -> str:
    """
    Fetches the earnings call transcript for a given ticker, year, and quarter.
    First checks the database for an existing record. If not found, fetches from API Ninjas and stores it in the database.

    :param ticker: The stock ticker symbol (e.g., 'GOOGL').
    :param year: The year of the earnings call (e.g., 2027).
    :param quarter: The quarter of the earnings call (e.g., 4).
    :return: The transcript as a string.
    """
    try:
        ticker = ticker.strip().upper()

        # Check if the transcript exists in the database
        transcript = get_earnings_call_transcript_from_db(ticker, year, quarter)
        
        if not transcript or transcript == "":
            # If not found, fetch from API Ninjas
            transcript = get_earnings_call_transcript_from_api_ninjas(ticker, year, quarter)
            
            # Store the fetched transcript in the database
            upsert_earnings_call_transcript(ticker, year, quarter, transcript)

        return transcript
    
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Exception in get_earnings_call_transcript: {repr(e)}")
        return ""
    

def get_earnings_call_transcript_endpoint():
    try:
        if not authorized_via_redis_token(request, 'finance_tools'):
            return ('', 401)
        
        ticker = request.args.get('ticker')
        quarter = request.args.get('quarter')
        year = request.args.get('year')
        transcript = get_earnings_call_transcript(ticker, quarter, year)
        return ({{"transcript": transcript}}, 200)
    
    except Exception as e:
        append_to_log('flask_logs', 'FINANCE', 'ERROR', f"Exception in get_earnings_call_transcript_endpoint: {repr(e)}")
        return ('', 500)
    
