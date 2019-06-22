import json
import pytest
import boto3
from botocore.stub import Stubber, ANY
from pytest_mock import mocker
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta 
from reminder_app.execute_reminder_handler import execute_reminder, ses, sns, ssm, dynamodb

@pytest.fixture(autouse=True)
def dynamodb_stub():
    with Stubber(dynamodb.meta.client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()

def tests_execute_reminder_send_email(dynamodb_stub):
    stubber_ssm = Stubber(ssm)
    stubber_ssm.add_response('get_parameters',
        {"Parameters": 
        [{ "Name":"test-app/test/max_retry_count","Value": "3"}]},
        {'Names': ['test-app/test/max_retry_count']})
    stubber_ssm.activate()

    stubber_ses = Stubber(ses)

    expectedParams = {'Destination': {
                            'ToAddresses': ['shail@example.com']},
                            'Message': {
                                'Body': {'Text': {'Charset': 'UTF-8', 'Data': 'Pay your taxes'}},
                            'Subject': {'Charset': 'UTF-8', 
                                        'Data': 'Pay your taxes'}},
                            'Source': 'shail@example.com'}

    stubber_ses.add_response('send_email',{"MessageId": "SomeID"},expectedParams)
    stubber_ses.activate()

    time_In_Past_By_10_mins = (datetime.now() - timedelta(minutes = 10)).strftime('%Y-%m-%dT%H:%M:%S.%f')

    print("Scheduling for ",time_In_Past_By_10_mins)

    reminder2send = { 
        "user_id":{"S": "1"},
        "reminder_id":{"S" :"1"},
        "notify_date_time": {"S" : str(time_In_Past_By_10_mins)},
        "remind_msg":{"S":"Pay your taxes"},
        "state":{"S":"Pending"},
        "retry_count":{"N":"0"},
        "notify_by":{"M":{
            "type":{"S":"Email"},
            "to_address": {"S":"shail@example.com"},
            "from_address":{"S":"shail@example.com"}
        }}
    }

    expectedParams = {'Key': {'reminder_id': '3'}, 'TableName': 'RemindersTable'}
    
    dynamodb_stub.add_response('get_item', {U'Item':reminder2send}, expectedParams)

    reminder_id2send = """{
        "reminder_id":"3"
    }"""

    expectedResponse = {'Destination': {
                            'ToAddresses': ['shail@example.com']},
                            'Message': {
                                'Body': {'Text': {'Charset': 'UTF-8', 'Data': 'Pay your taxes'}},
                            'Subject': {'Charset': 'UTF-8', 
                                    'Data': 'Pay your taxes'}},
                                        'Source': 'shail@example.com'}

    with stubber_ssm:
        with stubber_ses:
            response = execute_reminder({u'body': reminder_id2send}, 'context')  
            assert response == {'body': ANY, 'statusCode': 200}

def tests_execute_reminder_send_sms(dynamodb_stub):
    stubber_ssm = Stubber(ssm)
    stubber_ssm.add_response('get_parameters',
        {"Parameters": 
        [{ "Name":"test-app/test/max_retry_count","Value": "3"}]},
        {'Names': ['test-app/test/max_retry_count']})
    stubber_ssm.activate()

    stubber_sns = Stubber(sns)

    expectedParams = {'Message': 'Pay your taxes', 'PhoneNumber': "+1-123-456-7890"}

    stubber_sns.add_response('publish',{"MessageId": "SomeID"},expectedParams)
    stubber_sns.activate()

    time_In_Past_By_10_mins = (datetime.now() - timedelta(minutes = 10)).strftime('%Y-%m-%dT%H:%M:%S.%f')

    print("Scheduling for ",time_In_Past_By_10_mins)

    reminder2send = { 
        "user_id":{"S": "1"},
        "reminder_id":{"S" :"1"},
        "notify_date_time": {"S" : str(time_In_Past_By_10_mins)},
        "remind_msg":{"S":"Pay your taxes"},
        "state":{"S":"Pending"},
        "retry_count":{"N":"0"},
        "notify_by":{"M":{
            "type":{"S":"SMS"},
            "phone_number": {"S":"+1-123-456-7890"}
        }}
    }

    expectedParams = {'Key': {'reminder_id': '3'}, 'TableName': 'RemindersTable'}
    
    dynamodb_stub.add_response('get_item', {U'Item':reminder2send}, expectedParams)

    reminder_id2send = """{
        "reminder_id":"3"
    }"""

    with stubber_ssm:
        with stubber_sns:
            response = execute_reminder({u'body': reminder_id2send}, 'context')  
            assert response == {'body': ANY, 'statusCode': 200}

def tests_execute_reminder_not_pending(dynamodb_stub):
    time_In_Past_By_10_mins = (datetime.now() - timedelta(minutes = 10)).strftime('%Y-%m-%dT%H:%M:%S.%f')

    print("Scheduling for ",time_In_Past_By_10_mins)

    reminder2send = { 
        "user_id":{"S": "1"},
        "reminder_id":{"S" :"1"},
        "notify_date_time": {"S" : str(time_In_Past_By_10_mins)},
        "remind_msg":{"S":"Pay your taxes"},
        "state":{"S":"Acknowledged"},
        "retry_count":{"N":"0"},
        "notify_by":{"M":{
            "type":{"S":"SMS"},
            "phone_number": {"S":"+1-123-456-7890"}
        }}
    }

    expectedParams = {'Key': {'reminder_id': '3'}, 'TableName': 'RemindersTable'}
    
    dynamodb_stub.add_response('get_item', {U'Item':reminder2send}, expectedParams)

    reminder_id2send = """{
        "reminder_id":"3"
    }"""


    response = execute_reminder({u'body': reminder_id2send}, 'context')  
    assert response == {'to_execute': 'false'}

def tests_execute_reminder_exceeded_max_retry_counts(dynamodb_stub):
    stubber_ssm = Stubber(ssm)
    stubber_ssm.add_response('get_parameters',
        {"Parameters": 
        [{ "Name":"test-app/test/max_retry_count","Value": "3"}]},
        {'Names': ['test-app/test/max_retry_count']})
    stubber_ssm.activate()

    time_In_Past_By_10_mins = (datetime.now() - timedelta(minutes = 10)).strftime('%Y-%m-%dT%H:%M:%S.%f')

    print("Scheduling for ",time_In_Past_By_10_mins)

    reminder2send = { 
        "user_id":{"S": "1"},
        "reminder_id":{"S" :"1"},
        "notify_date_time": {"S" : str(time_In_Past_By_10_mins)},
        "remind_msg":{"S":"Pay your taxes"},
        "state":{"S":"Pending"},
        "retry_count":{"N":"4"},
        "notify_by":{"M":{
            "type":{"S":"SMS"},
            "phone_number": {"S":"+1-123-456-7890"}
        }}
    }

    expectedParams = {'Key': {'reminder_id': '3'}, 'TableName': 'RemindersTable'}
    
    dynamodb_stub.add_response('get_item', {U'Item':reminder2send}, expectedParams)

    reminder_id2send = """{
        "reminder_id":"3"
    }"""

    expectedUpdateParams = { 
        u'Key': {u'reminder_id': u'3'},
        u'TableName': u'RemindersTable',
        u'UpdateExpression': u'SET state= :state, updated_at= :updated_at',
        u'ExpressionAttributeValues': {
            u':state': 'Unacknowledged', 
            U':updated_at' : ANY
            }
        }
    
    stubbed_response = {U'Attributes' :{ u'string': {"S": "string"}}}
        
    dynamodb_stub.add_response('update_item', stubbed_response, expectedUpdateParams)


    with stubber_ssm:
        response = execute_reminder({u'body': reminder_id2send}, 'context')  
        assert response == {'to_execute': 'false'}

def tests_execute_reminder_rescheduled(dynamodb_stub):
    stubber_ssm = Stubber(ssm)
    stubber_ssm.add_response('get_parameters',
        {"Parameters": 
        [{ "Name":"test-app/test/max_retry_count","Value": "3"}]},
        {'Names': ['test-app/test/max_retry_count']})
    stubber_ssm.activate()

    time_In_Future_By_10_mins = (datetime.now() + timedelta(minutes = 10)).strftime('%Y-%m-%dT%H:%M:%S.%f')

    print("Scheduling for ",time_In_Future_By_10_mins)

    reminder2send = { 
        "user_id":{"S": "1"},
        "reminder_id":{"S" :"3"},
        "notify_date_time": {"S" : str(time_In_Future_By_10_mins)},
        "remind_msg":{"S":"Pay your taxes"},
        "state":{"S":"Pending"},
        "retry_count":{"N":"1"},
        "notify_by":{"M":{
            "type":{"S":"SMS"},
            "phone_number": {"S":"+1-123-456-7890"}
        }}
    }

    expectedParams = {'Key': {'reminder_id': '3'}, 'TableName': 'RemindersTable'}
    
    dynamodb_stub.add_response('get_item', {U'Item':reminder2send}, expectedParams)

    reminder_id2send = """{
        "reminder_id":"3"
    }"""

    with stubber_ssm:
        response = execute_reminder({u'body': reminder_id2send}, 'context')  
        assert response == {'to_execute': 'true','notify_date_time': ANY, 'reminder_id': '3'}


