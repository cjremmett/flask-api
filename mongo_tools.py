from pymongo import MongoClient


def get_mongo_cursor():
    return MongoClient("mongodb://admin:admin@localhost")