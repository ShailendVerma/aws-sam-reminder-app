import json
import boto3
import logging
import os
import time
import uuid
from datetime import datetime
from boto3.dynamodb.conditions import Key, Attr
from reminder_app.api_reminder_handler import validate_field
import reminder_app.DecimalEncoder as DecimalEncoder
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
ssm = boto3.client('ssm', region_name="us-east-1")
param_path= '{app_name}/{stage}/'.format(app_name=os.environ['APP_NAME'],stage=os.environ['STAGE'])
sns = boto3.client('sns')
CHARSET = "UTF-8"

table = dynamodb.Table('RemindersTable')

# Gets triggered by step function
# Check if reminder is still in pending state and the execution date is in the past
# Check mode email or sms and send out email and call appropriate method
# retryCount +=1
# Create event to check if reminder is in acknowledged in 15 mins else mark as pending self again
# if retryCount >= {MAX_RETRIES} mark the reminder as unacknowledged in dynamoDB
# NOT USING CLOUD WATCH EVENTS AS 
def execute_reminder(event, context):
    #fetch the reminder
    data = json.loads(event['body'])
    validate_field(data,'reminder_id')

    try:
        response = table.get_item(
        Key={
            'reminder_id': data['reminder_id']
        }
    )
    except ClientError as e:
        logging(e.response['Error']['Message'])
    else:
        item = response['Item']
        logging("GetItem succeeded:")
        logging(json.dumps(item, indent=4, cls=DecimalEncoder))

        #if state of reminder is not pending return to_execute as false
        if item['state'] != 'Pending':
            logging('Reminder:{reminderId} is not pending'.format(reminderId=data['reminder_id']))
            return {
                'to_execute':'false'
            }

        #else if retry_count > max_retry_count then mark state as Unacknowledged and return to_execute as false
        max_retry_count = ssm.get_parameters(Names=[param_path+"max_retry_count"])
        if item['retry_count'] > max_retry_count:
            logging('Reminder:{reminderId} has exceeded max retry counts'.format(reminderId=data['reminder_id']))
            item['state'] = 'Unacknowledged'
            return {
                'to_execute':'false'
            }

        #else if notify_date_time is in the future return with to_execute as true + reminder_id + notify_date_time
        if item['notify_date_time'] > max_retry_count:
            logging('Reminder:{reminderId} has exceeded max retry counts'.format(reminderId=data['reminder_id']))
            item['state'] = 'Unacknowledged'
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
                'to_execute':'true',
                'reminder_id':item['reminder_id'],
                'notify_date_time':item['notify_date_time']
            }


        #else send notification based on notify_by and return (dont update state)
        

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }

def send_sms(event, context):
    # TODO implement
    #Send SMS
    
    response = sns.publish(PhoneNumber = '+14165618562', Message='Welcome from Lambda' )

    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }


def send_email(event, context):
    #Send Email
    ses = boto3.client('ses')
    #Provide the contents of the email.
    response = ses.send_email(
        Destination={
            'ToAddresses': [
                'shailend2k@gmail.com',
            ],
        },
        Message={
            'Body': {
                'Text': {
                    'Charset': CHARSET,
                    'Data': 'Hi from Lambda Function',
                },
            },
            'Subject': {
                'Charset': CHARSET,
                'Data': 'Hi from Lambda',
            },
        },
        Source='shailend2k@gmail.com'
    )
    
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }