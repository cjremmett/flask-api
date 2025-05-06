from flask import jsonify
from time import sleep
from flask_socketio import send, emit
from utils import append_to_log
import uuid
import datetime
from datetime import timezone
from pymongo import MongoClient
from typing import List
import json
MONGO_CONNECTION_STRING = 'mongodb://admin:admin@192.168.0.121'

# Need this to support socketio decorators
# Docs say we need to import from __main__, but with gunicorn __name__ == 'main'
from main import socketio


def generate_new_ai_user_id():
    """Generate a new user ID using UUID4."""
    new_uuid = 'cjr-userid-' + str(uuid.uuid4())
    return new_uuid


def generate_new_ai_chat_id():
    """Generate a new chat room ID using UUID4."""
    new_uuid = 'cjr-chatid-' + str(uuid.uuid4())
    return new_uuid


def generate_new_ai_message_id():
    """Generate a new chhat message ID using UUID4."""
    new_uuid = 'cjr-messageid-' + str(uuid.uuid4())
    return new_uuid


def store_message(userid: str, messageid: str, message_contents: dict) -> bool:
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["ai"]
        collection = db["messages"]

        # Insert the message
        record = {
            "message_contents": message_contents,
            "userid": userid,
            "messageid": messageid,
            "timestamp": datetime.datetime.now(timezone.utc)
        }

        # Insert the record
        result = collection.insert_one(record)

        # Return True if the operation was successful
        return result.acknowledged

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error inserting MongoDB record: {repr(e)}")
        return False

    finally:
        # Close the MongoDB connection
        client.close()


def get_messages_by_user(userid: str) -> List[dict]:
    """
    Retrieves all records from MongoDB where the userid field matches the given userid.
    Orders the results by timestamp in ascending order.

    :param userid: The user ID to filter messages by.
    :return: A list of messages as dictionaries, or an empty list if no records are found.
    """
    try:
        # Connect to MongoDB
        client = MongoClient(MONGO_CONNECTION_STRING)
        db = client["ai"]
        collection = db["messages"]

        # Query the database and sort by timestamp in ascending order
        query = {"userid": userid}
        messages = list(collection.find(query).sort("timestamp", 1))

        return messages

    except Exception as e:
        # Log the error
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error retrieving messages from MongoDB: {repr(e)}")
        return []

    finally:
        # Close the MongoDB connection
        client.close()


def handle_user_message(userid: str, message_contents: dict):
    try:
        append_to_log('flask_logs', 'AI', 'TRACE', 'Processing message: ' + str(message_contents))

        # Store message in MongoDB. If successful, send back to user to display.
        if store_message(userid, generate_new_ai_message_id(), message_contents):
            message_dict = {
                "message": message_contents['message'],
                "isSystemMessage": message_contents['isSystemMessage']
            }
            emit('server_message', str(message_dict))
        else:
            return
        
        # Generate AI response
        dummy_ai_reponse = {"message": 'Hello world! This is a dummy AI response!', "isSystemMessage": True}

        # Store AI response. If successful, send to user to display.
        if store_message(userid, generate_new_ai_message_id(), dummy_ai_reponse):
            emit('server_message', str(dummy_ai_reponse))
        else:
            return
        

    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error handling user message: {repr(e)}")


@socketio.on('user_message')
def handle_message(data):
    try:
        append_to_log('flask_logs', 'AI', 'DEBUG', str(data))
        json_data = json.loads(data)
        handle_user_message(json_data['userid'], {'message': json_data['message'], 'isSystemMessage': False})
    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error handling user message socketio decorator fucntion: {repr(e)}")
    

def get_new_ai_userid():
    try:
        new_userid = generate_new_ai_user_id()
        append_to_log('flask_logs', 'AI', 'INFO', 'New user created with ID ' + new_userid + '.')
        return ({"userid": new_userid}, 200)
    except Exception as e:
        append_to_log('flask_logs', 'AI', 'ERROR', f"Error creating new user ID: {repr(e)}")
        return('', 500)
