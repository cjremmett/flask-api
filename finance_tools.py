import requests
from flask import request
import re
from utils import append_to_log, authorized_via_redis_token


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
        
        # Get HTML source from Google
        source = get_google_fx_html_source(currency)
        if source == None or len(source) < 100 or len(source) > 10000000:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get HTML source correctly from Google for currency ' + currency + '.')
            return ('', 500)
        
        # Get the FX conversion rate using the HTML source from Google
        fx_rate = get_fx_conversion_rate_from_google_html_source(source, currency)

        # Return the result.
        # VBA has trouble with JSON so just send straight text back since the use case for this is displaying data in Excel.
        if fx_rate != None:
            append_to_log('flask_logs', 'FINANCE', 'TRACE', 'Got forex conversion rate successfully from Google for currency ' + currency + '.\n\nForex conversion rate: ' + fx_rate)
            return(fx_rate, 200)
        else:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get forex conversion successfully for currency ' + currency + '.\n\nForex conversion rate: ' + str(fx_rate) + '\n\nHTML source: ' + source)
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
        else:
            append_to_log('flask_logs', 'FINANCE', 'ERROR', 'Failed to get stock price and/or market cap successfully for ' + ticker + '.\n\nStock price: ' + str(stock_price) + '\nMarket Cap: ' + str(market_cap) + '\n\nHTML source: ' + source)
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

def get_stock_price_from_gurufocus_html_native_currency(source: str, ticker: str):
    # Return the stock price in the native currency
    # Snippet of source we're using:
    # What is Las Vegas Sands Corp(LVS)\'s  stock price today?\n      </span> <div class="t-caption t-label m-t-sm m-b-md" data-v-00a2281e>\n        The current price of LVS is $51.65.
    # The current price of MIC:SBER is \xe2\x82\xbd292.19.
    try:      
        split = source.split('The current price of ')
        if len(split) < 2:
            return None
        
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
    
# if __name__ == '__main__':
#     import requests
#     import finance_tools
#     ticker = 'HKSE:00700'
#     headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/111.0.0.0 Safari/537.36'}
#     response = requests.get('https://www.gurufocus.com/stock/' + ticker + '/summary', headers=headers)
#     source = str(response.content)
#     val = finance_tools.get_stock_price_from_gurufocus_html_native_currency(source, ticker)
#     val = finance_tools.get_market_cap_from_gurufocus_html_native_currency(source, ticker)
#     print(str(val))