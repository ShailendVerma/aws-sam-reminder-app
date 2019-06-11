import json
import boto3
import logging
import os
import time
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
ssm = boto3.client('ssm', region_name="us-east-1")
param_path= '{app_name}/{stage}/'.format(app_name=os.environ['APP_NAME'],stage=os.environ['STAGE'])

table = dynamodb.Table('RemindersTable')

def validate_field(data,fieldName):
    if fieldName not in data:
        logging.error("Validation Failed")
        raise Exception("Couldn't create the reminder item - {fieldName} missing".format(fieldName = fieldName))

def validate_notify_date_time(data):
    date_ts = datetime.strptime(data['notify_date_time'], '%Y-%m-%dT%H::%M::%S.%f')
    current_ts = datetime.now
    diff = (date_ts - current_ts).min

    min_delay_param = ssm.get_parameters(Names=[param_path+"min_delay_param"])
    max_delay_param = ssm.get_parameters(Names=[param_path+"max_delay_param"])

    if max_delay_param > diff  or diff < max_delay_param:
        logging.error("Validation Failed")
        raise Exception("Reminder should be at least {min_delay_param} mins in the future and less than {max_delay_param} mins in the future".format(min_delay_param=min_delay_param,max_delay_param=max_delay_param))




# Create a reminder and store in dynamoDB
# Create a scheduled event
# validate not less than {MIN_DELAY_PARAM} mins left
# validate not more than {MAX_DELAY_PARAM}
def create_reminder(event, context):
    data = json.loads(event['body'])

    validate_field(data,'user_id')
    validate_field(data,'notify_date_time')
    validate_field(data,'remind_msg')
    validate_field(data,'notify_by')

    validate_notify_date_time(data)

    timestamp = int(time.time() * 1000)

    reminder = {
                'reminder_id': str(uuid.uuid1()), #Partition key
                'user_id': data['user_id'], #Sort key
                'notify_date_time': data['notify_date_time'],
                'remind_msg': data['remind_msg'],
                'state' : 'Pending',
                'to_exeute': 'true',
                'retryCount': 0,
                'updated_at': timestamp
            }

    result = table.put_item(Item=reminder)

    return {
        "statusCode": 200,
        "body": json.dumps(reminder),
    }


# Update a reminder in DynamoDB - ideally date change
# Validate not less than {MIN_DELAY_PARAM} mins left 
def update_reminder(event, context):
    data = json.loads(event['body'])

    validate_field(data,'notify_date_time')
    validate_field(data,'remind_msg')
    validate_notify_date_time(data)

    timestamp = int(time.time() * 1000)

    result = table.update_item(
        Key={
            'reminder_id': event['pathParameters']['reminder_id']
        },
        AttributeUpdates={
            'notify_date_time': data['notify_date_time'],
            'remind_msg': data['remind_msg'],
            'updated_at': timestamp
        },
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result['Attributes']),
    }

# Mark reminder as deleted in DynamoDB
def delete_reminder(event, context):
    result = table.delete_item(
        Key={
            'reminder_id': event['pathParameters']['reminder_id']
        }
    )
    return {
        "statusCode": 200
    }

# Mark reminder as acknowledged in DynamoDB
def ack_reminder(event, context):
    timestamp = int(time.time() * 1000)

    result = table.update_item(
        Key={
            'reminder_id': event['pathParameters']['reminder_id']
        },
        AttributeUpdates={
            'state': 'Acknowledged',
            'updated_at': timestamp
        },
    )

    return {
        "statusCode": 200
    }

# Mark reminder as acknowledged in DynamoDB
def list_reminders(event, context):
    data = json.loads(event['body'])

    validate_field(data,'user_id')

    result = table.scan(
        FilterExpression=Attr('user_id').eq(data['user_id'])
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result['Items']),
    }