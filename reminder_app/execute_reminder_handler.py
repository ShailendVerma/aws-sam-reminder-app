import json
import boto3
import logging
import os
import time
import uuid
from datetime import datetime, timedelta
from boto3.dynamodb.conditions import Key, Attr
#from reminder_app.api_reminder_handler import validate_field
#import reminder_app.DecimalEncoder as DecimalEncoder
from botocore.exceptions import ClientError
#from reminder_app.date_utils import isostr_to_datetime, datetime_to_isostr

#TODO PUT COMMON CODE IN LAYERS
def isostr_to_datetime(date_string):
    print("From Datestr:",date_string)
    dtval = datetime.strptime(date_string, '%Y-%m-%dT%H:%M:%S.%f%z').replace(tzinfo=None)
    print ("To Datetime:",dtval)
    return dtval

def datetime_to_isostr(date):
    print("From Datetime:",date)
    #FIXME - handle propertly
    dt = date.strftime('%Y-%m-%dT%H:%M:%S.%f%Z')+'Z'
    print("To Datestr:",dt)
    return dt

def validate_field(data,fieldName):
    if fieldName not in data:
        logging.error("Validation Failed")
        raise Exception("Couldn't create the reminder item - {fieldName} missing".format(fieldName = fieldName))

def validate_notify_date_time(data):
    current_ts = datetime.utcnow()
    logging.info("Current ts:",current_ts)
    print("Current ts:",current_ts)
    date_ts = isostr_to_datetime(data['notify_date_time'])
    logging.info("Reminder ts:",date_ts)
    print("Reminder ts:",date_ts)
    if current_ts > date_ts:
        logging.error("Validation Failed: Reminder in the past")
        raise Exception("Reminder {date_ts} in the past".format(date_ts=date_ts))

    diff = (date_ts - current_ts)
    print("diff ts:",diff.seconds)

    delay_params_list = ssm.get_parameters_by_path(Path=param_path,Recursive=False)['Parameters']

    logging.debug(delay_params_list)

    delay_params_dict = {param['Name'] : param for param in delay_params_list}
    
    min_delay_param = int(delay_params_dict[param_path+"/min_delay_param"]['Value'])
    max_delay_param = int(delay_params_dict[param_path+"/max_delay_param"]['Value'])

    delay_seconds = int(diff.seconds)
    if (min_delay_param >  delay_seconds)  or (delay_seconds > max_delay_param):
        logging.error("Validation Failed")
        raise Exception("Reminder should be at least {min_delay_param} mins in the future and less than {max_delay_param} mins in the future".format(min_delay_param=min_delay_param,max_delay_param=max_delay_param))




dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
ssm = boto3.client('ssm', region_name="us-east-1")
param_path= '/{app_name}/{stage}'.format(app_name=os.environ['APP_NAME'],stage=os.environ['STAGE'])
#SNS Client for SMS
sns = boto3.client('sns')
#SES Client for Emails
ses = boto3.client('ses')
CHARSET = "UTF-8"

table = dynamodb.Table('{stack_name}-RemindersTable'.format(stack_name=os.environ['STACK_NAME']))

# Gets triggered by step function
# Check if reminder is still in pending state and the execution date is in the past
# Check mode email or sms and send out email and call appropriate method
# retry_count +=1
# Create event to check if reminder is in acknowledged in 15 mins else mark as pending self again
# if retry_count >= {MAX_RETRIES} mark the reminder as unacknowledged in dynamoDB
# NOT USING CLOUD WATCH EVENTS AS 
def execute_reminder(event, context):
    #data = json.loads(event['body'],strict=False)
    data = event
    logging.info("Event: "+str(event))
    print("Event:>> "+str(event))
    validate_field(data,'reminder_id')
    timestamp = int(time.time() * 1000)
    #fetch the reminder
    try:
        response = table.query(
        KeyConditionExpression=Key('reminder_id').eq(data['reminder_id'])
    )
    except ClientError as e:
        print(e.response['Error']['Message'])
        logging.info(e.response['Error']['Message'])
    else:
        item = response['Items'][0]
        logging.info("GetItem succeeded:")
        print("GetItem succeeded:")
        logging.info(item)

        #if state of reminder is not pending return to_execute as false
        if item['state'] != 'Pending':
            logging.info('Reminder:{reminderId} is not pending'.format(reminderId=data['reminder_id']))
            print('Reminder:{reminderId} is not pending'.format(reminderId=data['reminder_id']))
            return {
                'to_execute':'false'
            }

        #else if retry_count > max_retry_count then mark state as Unacknowledged and return to_execute as false
        app_params_list = ssm.get_parameters_by_path(Path=param_path,Recursive=False)['Parameters']
        logging.debug(app_params_list)
        delay_params_dict = {param['Name'] : param for param in app_params_list}
    
        max_retry_count = int(delay_params_dict[param_path+"/max_retry_count"]['Value'])
        print(max_retry_count)
        if item['retry_count'] > max_retry_count:
            logging.info('Reminder:{reminderId} has exceeded max retry counts'.format(reminderId=data['reminder_id']))
            print('Reminder:{reminderId} has exceeded max retry counts'.format(reminderId=data['reminder_id']))
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
        date_ts = isostr_to_datetime(item['notify_date_time'])
        if  date_ts > datetime.utcnow():
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
        #FIXME remove hard coding
        time_In_Future_By_5_mins = datetime_to_isostr(datetime.utcnow() + timedelta(minutes = 5))

        return {
                'to_execute':'true',
                'reminder_id':item['reminder_id'],
                'notify_date_time':time_In_Future_By_5_mins
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