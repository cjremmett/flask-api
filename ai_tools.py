from flask import request
from flask_socketio import emit
from utils import append_to_log
import uuid
from pymongo import MongoClient
from typing import List
import time
import json
from finance_tools import get_earnings_call_transcript
from gemini_integration import submit_messages_to_gemini
MONGO_CONNECTION_STRING = 'mongodb://admin:admin@192.168.0.121'

# Need this to support socketio decorators
# Docs say we need to import from __main__, but with gunicorn __name__ == 'main'
from main import socketio


def generate_new_ai_user_id():
    """Generate a new user ID using UUID4."""
    new_uuid = 'cjr-userid-' + str(uuid.uuid4())
    return new_uuid


def get_new_ai_userid():
    try:
        new_userid = generate_new_ai_user_id()
        append_to_log('flask_logs', 'AI', 'INFO', 'New user created with ID ' + new_userid + '.')
        return ({"userid": new_userid}, 200)
    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error creating new user ID: {repr(e)}")
        return('', 500)


def generate_new_ai_chat_id():
    """Generate a new chat room ID using UUID4."""
    new_uuid = 'cjr-chatid-' + str(uuid.uuid4())
    return new_uuid


def generate_new_ai_message_id():
    """Generate a new chhat message ID using UUID4."""
    new_uuid = 'cjr-messageid-' + str(uuid.uuid4())
    return new_uuid
    

@socketio.on('earnings_call_inquiry')
def handle_earnings_call_inquiry(data):
    """Expects data to contain JSON in the following format:
    {
        "userid": "cjr-userid-example",
        "chatid": "cjr-chatid-example",
        "message": {
            "ticker": "AAPL",
            "year": 2025,
            "quarter": 1,
            "content": "Some user question."
        }
    }
    """
    try:
        append_to_log('flask_logs', 'AI', 'DEBUG', 'Earnings call chat message submitted: ' + str(data))

        messages_history = retrieve_earnings_call_inquiry_message_thread_from_database(data['userid'], data['chatid'])

        # If this is the first message, load the relevant transcript and initialize the message list
        if messages_history == None:
            append_to_log('flask_logs', 'AI', 'DEBUG', 'Earnings call inquiry chat started about ticker ' + str(data['message']['ticker']) + ' for Q' + str(data['message']['quarter']) + ' ' + str(data['message']['year']) + '.')
            transcript = get_earnings_call_transcript(data['message']['ticker'], data['message']['year'], data['message']['quarter'])
            messages_history = [(
                "system",
                transcript
            ),
            (
                "system",
                "You are a helpful assistant. Carefully review the entire earnings call transcript in the previous message before answering any questions."
            )]
        
        # Append the user message to the list
        append_message_to_messages_list('user', data['message']['content'], messages_history)

        # Send message back to user to load into the view
        send_earnings_call_inquiry_message_to_user('earnings_call_inquiry', {"role": "user", "message": data['message']['content']})
        
        # Store updated message thread in database
        store_earnings_call_inquiry_message_thread_to_database(data['userid'], data['chatid'], int(time.time()), messages_history)

        # Call the AI to get a response to the user message
        ai_response = submit_messages_to_gemini(messages_history)
        append_to_log('flask_logs', 'AI', 'DEBUG', 'AI responded with: ' + ai_response[0])

        # Store updated message thread in database
        store_earnings_call_inquiry_message_thread_to_database(data['userid'], data['chatid'], int(time.time()), ai_response[1])

        # Send AI response to the user
        send_earnings_call_inquiry_message_to_user('earnings_call_inquiry', {"role": "assistant", "message": ai_response[0]})

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error processing handle_earnings_call_inquiry socketio decorator function: {repr(e)}")


def send_earnings_call_inquiry_message_to_user(namespace: str, message: dict) -> None:
    # Need to use json.dumps to send a string because the frontend cannot parse a dict
    emit(namespace, json.dumps(message))


def append_message_to_messages_list(role: str, message: str, messages: List) -> List:
    messages.append((role, message))
    return messages


def store_earnings_call_inquiry_message_thread_to_database(userid: str, chatid: str, timestamp: int, messages: List) -> bool:
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["ai"]
        collection = db["chats"]

        # Generate the JSON to store
        messages_json = json.dumps(messages)

        # Upsert the message
        query = {"userid": userid, "chatid": chatid}
        update = {"$set": {"messages": messages_json, "timestamp": timestamp}}
        result = collection.update_one(query, update, upsert=True)

        # Return True if the operation was successful
        return result.acknowledged

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error upserting MongoDB record: {repr(e)}")
        return False

    finally:
        client.close()


def retrieve_earnings_call_inquiry_message_thread_from_database(userid: str, chatid: str) -> List:
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["ai"]
        collection = db["chats"]

        query = {"userid": userid, "chatid": chatid}
        first_record = collection.find_one(query)

        return list(json.loads(first_record['messages'])) if first_record is not None else None

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error retrieving MongoDB record: {repr(e)}")
        return None

    finally:
        client.close()


def get_all_chats_for_user(userid: str) -> List[dict]:
    """
    Retrieves all chat records from MongoDB where the userid matches the given parameter.
    Orders the results by timestamp in descending order.

    :param userid: The user ID to filter chats by.
    :return: A list of chat records as dictionaries, or an empty list if no records are found.
    """
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["ai"]
        collection = db["chats"]

        # Query the database and sort by timestamp in descending order
        query = {"userid": userid}
        projection = {"message": 0}
        chats = list(collection.find(query, projection).sort("timestamp", -1))
        append_to_log('flask_logs', 'AI', 'DEBUG', f"Chats: {str(chats)}")

        return chats

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error retrieving chats from MongoDB: {repr(e)}")
        return []

    finally:
        client.close()


def get_earnings_call_chat_history():
    """
    Query parameters:
    userid, chatid
    """
    try:
        userid = request.args.get('userid')
        chatid = request.args.get('chatid')
        history = retrieve_earnings_call_inquiry_message_thread_from_database(userid, chatid)
        return (history, 200)

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error retrieving chat history: {repr(e)}")
        return ('', 500)
    

def get_earnings_call_chats():
    """
    Query parameters:
    userid
    """
    try:
        userid = request.args.get('userid')
        chats = get_all_chats_for_user(userid)
        return (chats, 200)

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error retrieving chat history: {repr(e)}")
        return ('', 500)