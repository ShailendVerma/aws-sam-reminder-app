import json
import boto3
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key, Attr
from reminder_app.api_reminder_handler import validate_field
import reminder_app.DecimalEncoder as DecimalEncoder
from botocore.exceptions import ClientError

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
ssm = boto3.client('ssm', region_name="us-east-1")
param_path= '{app_name}/{stage}/'.format(app_name=os.environ['APP_NAME'],stage=os.environ['STAGE'])
#SNS Client for SMS
sns = boto3.client('sns')
#SES Client for Emails
ses = boto3.client('ses')
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
    data = json.loads(event['body'])
    validate_field(data,'reminder_id')
    timestamp = int(time.time() * 1000)
    #fetch the reminder
    try:
        response = table.get_item(
        Key={
            'reminder_id': data['reminder_id']
        }
    )
    except ClientError as e:
        logging.info(e.response['Error']['Message'])
    else:
        item = response['Item']
        logging.info("GetItem succeeded:")
        logging.info(item)

        #if state of reminder is not pending return to_execute as false
        if item['state'] != 'Pending':
            logging.info('Reminder:{reminderId} is not pending'.format(reminderId=data['reminder_id']))
            return {
                'to_execute':'false'
            }

        #else if retry_count > max_retry_count then mark state as Unacknowledged and return to_execute as false
        max_retry_count = int(ssm.get_parameters(Names=[param_path+"max_retry_count"])['Parameters'][0]['Value'])
        print(max_retry_count)
        if item['retry_count'] > max_retry_count:
            logging.info('Reminder:{reminderId} has exceeded max retry counts'.format(reminderId=data['reminder_id']))
            #mark state as Unacknowledged
            result = table.update_item(
            Key={
                'reminder_id': data['reminder_id']
            },
            UpdateExpression="SET state= :state, updated_at= :updated_at",
            ExpressionAttributeValues={
                    ':state' : 'Unacknowledged',
                    ':updated_at':timestamp
                }
            )

            # return to_execute as false
            return {
                'to_execute':'false'
            }

        #else if notify_date_time is in the future return with to_execute as true + reminder_id + notify_date_time
        date_ts = datetime.strptime(item['notify_date_time'], '%Y-%m-%dT%H:%M:%S.%f')
        if  date_ts > datetime.now():
            logging.info('Reminder:{reminderId} is scheduled for the future - skipping`  '.format(reminderId=data['reminder_id']))
            return {
                'to_execute':'true',
                'reminder_id':item['reminder_id'],
                'notify_date_time':item['notify_date_time']
            }

        #else send notification based on notify_by and return (dont update state)
        if item['notify_by']['type'] == 'SMS' :
            send_sms(item)
        else:
            send_email(item)
        
        #set a check notification status point 5 mins in the future for acknowledgment
        time_In_Future_By_10_mins = (datetime.now() + timedelta(minutes = 5)).strftime('%Y-%m-%dT%H:%M:%S.%f')

        return {
                'to_execute':'true',
                'reminder_id':item['reminder_id'],
                'notify_date_time':time_In_Future_By_10_mins
            }

def send_sms(item):
    #Send SMS
    response = sns.publish(PhoneNumber = item['notify_by']['phone_number'], Message=item['remind_msg'])
    logging.info(response)
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }


def send_email(item):
    #Send Email
    
    #Provide the contents of the email.
    response = ses.send_email(
        Destination={
            'ToAddresses': [
                item['notify_by']['to_address'],
            ],
        },
        Message={
            'Body': {
                'Text': {
                    'Charset': CHARSET,
                    'Data': item['remind_msg'],
                },
            },
            'Subject': {
                'Charset': CHARSET,
                'Data': item['remind_msg'],
            },
        },
        Source=item['notify_by']['from_address']
    )
    logging.info(response)
    return {
        'statusCode': 200,
        'body': json.dumps(response)
    }