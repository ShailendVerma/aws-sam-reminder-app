import json
import pytest
import boto3
from botocore.stub import Stubber, ANY
from pytest_mock import mocker
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timedelta 
from reminder_app.api_reminder_handler import create_reminder, dynamodb, sfn, ssm, update_reminder, delete_reminder, ack_reminder, list_reminders
from reminder_app.date_utils import isostr_to_datetime, datetime_to_isostr

@pytest.fixture(autouse=True)
def dynamodb_stub():
    with Stubber(dynamodb.meta.client) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()

def tests_create_reminder(dynamodb_stub):
    stubber1 = Stubber(ssm)
    stubber1.add_response('get_parameters_by_path',
        {"Parameters": 
        [{ "Name":"/test-app/test/min_delay_param","Value": "300"},{ "Name":"/test-app/test/max_delay_param","Value": "5000"}]},
        {'Path': '/test-app/test', 'Recursive': False})
    stubber1.activate()

    stubber_sfn = Stubber(sfn)
    stubber_sfn.add_response('start_execution',
        {'executionArn': 'SOME_ARN','startDate': datetime.utcnow()},
        {'stateMachineArn':'test-stepfunction-arn', 'name' : ANY, 'input': ANY})

    stubber_sfn.activate()

    time_In_Future_By_10_mins = datetime_to_isostr(datetime.utcnow() + timedelta(minutes = 10))

    print("Scheduling for ",time_In_Future_By_10_mins)

    reminder2create = """
    {
        "user_id":"1",
        "notify_date_time":"{0}",
        "remind_msg":"Pay your taxes",
        "notify_by":{
            "type":"Email",
            "to_address": "shail@gmail.com",
            "from_address":"shail@gmail.com"
        }
    }
    """

    expectedParams = {'Item': 
                        {
                            'notify_by': 
                            {'from_address': 'shail@gmail.com',
                            'to_address': 'shail@gmail.com',
                            'type': 'Email'},
                            'notify_date_time': ANY,
                    'remind_msg': 'Pay your taxes',
                     'reminder_id': ANY,
                     'retry_count': 0,
                     'state': 'Pending',
                     'to_execute': 'true',
                     'updated_at': ANY,
                     'user_id': '1'},
            'TableName': 'test-stack-RemindersTable'}
    
    dynamodb_stub.add_response('put_item', {U'Attributes':{u'string':{"S": "string"}}}, expectedParams)

    with stubber1, stubber_sfn:
        response = create_reminder({u'body': reminder2create.replace('{0}',time_In_Future_By_10_mins)}, 'context')  
    assert response == {'body': ANY, 'statusCode': 200}

def tests_update_reminder(dynamodb_stub):
    stubber2 = Stubber(ssm)
    stubber2.add_response('get_parameters_by_path',
        {"Parameters": 
        [{ "Name":"/test-app/test/min_delay_param","Value": "300"},{ "Name":"/test-app/test/max_delay_param","Value": "5000"}]},
        {'Path': '/test-app/test', 'Recursive': False})
    stubber2.activate()

    time_In_Future_By_10_mins = datetime_to_isostr(datetime.utcnow() + timedelta(minutes = 10))

    print("Scheduling for ",time_In_Future_By_10_mins)

    #Add query response
    dynamodb_stub.add_response('query', {U'Items':[{'reminder_id': {"S":"2"}, 'user_id': {"S":"1"}}]}, 
    {'KeyConditionExpression': Key('reminder_id').eq('2'),
    'TableName': 'test-stack-RemindersTable'})
    
    #Add update_item response
    reminder2update = """
    {
        "reminder_id":"2",
        "notify_date_time":"{0}",
        "remind_msg":"Pay your taxes in the morning"
    }
    """

    expectedParams = { 
        u'Key': {'reminder_id': '2', 'user_id': '1'},
        u'TableName': u'test-stack-RemindersTable',
        u'UpdateExpression': u'SET notify_date_time= :notify_date_time, updated_at= :updated_at, remind_msg= :remind_msg',
        u'ExpressionAttributeValues': {
            u':notify_date_time': ANY, 
            u':remind_msg': u'Pay your taxes in the morning',
            U':updated_at' : ANY
            }
        }
    
    stubbed_response = {U'Attributes' :{ u'string': {"S": "string"}}}
        
    dynamodb_stub.add_response('update_item', stubbed_response, expectedParams)

    reminderIdParam = {
        "reminder_id":"2",
    }

    with stubber2:
        response = update_reminder({u'pathParameters': reminderIdParam,u'body': reminder2update.replace('{0}',time_In_Future_By_10_mins)}, 'context')  
    assert response == {'body': '{"Attributes": {"string": "string"}}', 'statusCode': 200}

# pathParameters is a dictionary
def tests_delete_reminder(dynamodb_stub):
    #Add query response
    dynamodb_stub.add_response('query', {U'Items':[{'reminder_id': {"S":"3"}, 'user_id': {"S":"1"}}]}, 
    {'KeyConditionExpression': Key('reminder_id').eq('3'),
    'TableName': 'test-stack-RemindersTable'})

    #Add delete item response
    dynamodb_stub.add_response('delete_item', {}, 
    {'Key': {'reminder_id': '3', 'user_id': '1'}, 'TableName': 'test-stack-RemindersTable'})
    reminder2delete = {
        "reminder_id":"3",
    }
    response = delete_reminder({u'pathParameters': reminder2delete}, 'context')  
    assert response == {'statusCode': 200, 'body': '{}'}

def tests_ack_reminder(dynamodb_stub):
    #Add query response
    dynamodb_stub.add_response('query', {U'Items':[{'reminder_id': {"S":"3"}, 'user_id': {"S":"1"}}]}, 
    {'KeyConditionExpression': Key('reminder_id').eq('3'),
    'TableName': 'test-stack-RemindersTable'})

    #Add update item response
    reminder2ack = {
        "reminder_id":"3"
    }

    expectedParams = {
            'ExpressionAttributeNames': {'#st': 'state'},
            'ExpressionAttributeValues': {':state': 'Acknowledged', ':updated_at': ANY, ':to_execute': 'false'},
            'Key': {'reminder_id': '3', 'user_id': '1'},
            'TableName': 'test-stack-RemindersTable',
            'UpdateExpression': 'SET #st= :state, updated_at= :updated_at, to_execute= :to_execute'
           }
    
    dynamodb_stub.add_response('update_item', {}, expectedParams)

    response = ack_reminder({u'pathParameters': reminder2ack}, 'context')  
    assert response == {'body': '{}', 'statusCode': 200}

def tests_list_reminders(dynamodb_stub):
    user2list = {"pathParameters":{"user_id":"123"}}

    reminders2fetch = [
    {
        "user_id":{"S":"123"},
        "reminder_id":{"S":"1"}
    },
    {
        "user_id":{"S":"123"},
        "reminder_id":{"S":"2"}
    },
    ]
    
    expectedParams = {
        'IndexName': 'UserIdIndex',
        'KeyConditionExpression': Key('user_id').eq('123'), 'TableName': 'test-stack-RemindersTable'}
    
    dynamodb_stub.add_response('query', {U'Items':reminders2fetch}, expectedParams)

    response = list_reminders(user2list, 'context')  

    assert response == {'body': '[{"user_id": "123", "reminder_id": "1"}, {"user_id": "123", "reminder_id": "2"}]', 'statusCode': 200}
