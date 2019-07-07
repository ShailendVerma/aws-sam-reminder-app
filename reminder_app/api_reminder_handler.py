import json
import boto3
import logging
import os
import time
import uuid
from datetime import datetime,timedelta
from boto3.dynamodb.conditions import Key, Attr
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

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
ssm = boto3.client('ssm', region_name="us-east-1")
sfn = boto3.client('stepfunctions')
param_path= '/{app_name}/{stage}'.format(app_name=os.environ['APP_NAME'],stage=os.environ['STAGE'])

table = dynamodb.Table('{stack_name}-RemindersTable'.format(stack_name=os.environ['STACK_NAME']))

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




# Create a reminder and store in dynamoDB
# Create a scheduled event
# validate not less than {MIN_DELAY_PARAM} mins left
# validate not more than {MAX_DELAY_PARAM}
def create_reminder(event, context):
    data = json.loads(event['body'],strict=False)

    validate_field(data,'user_id')
    validate_field(data,'notify_date_time')
    validate_field(data,'remind_msg')
    validate_field(data,'notify_by')

    validate_notify_date_time(data)

    timestamp = int(time.time() * 1000)
    reminder_id = str(uuid.uuid1())
    reminder = {
                'reminder_id': reminder_id, #Partition key
                'user_id': data['user_id'], #Sort key
                'notify_date_time': data['notify_date_time'],
                'remind_msg': data['remind_msg'],
                'state' : 'Pending',
                'to_execute': 'true',
                'retry_count': 0,
                'updated_at': timestamp,
                'notify_by': data['notify_by']
            }


    result = table.put_item(Item=reminder)
 
    reminder_step_input = {
        "reminder_id": reminder_id,
        "to_execute" : "true",
        "notify_date_time" : data['notify_date_time']
    }

    #Invoke the step function to execute
    response = sfn.start_execution(
        stateMachineArn=os.environ['STEP_FUNCTION_ARN'],
        name=reminder_id+"_reminder_fn",
        input=json.dumps(reminder_step_input)
    )

    return {
        "statusCode": 200,
        "body": json.dumps(reminder),
    }


# Update a reminder in DynamoDB - ideally date change
# Validate not less than {MIN_DELAY_PARAM} mins left 
def update_reminder(event, context):
    #check if reminder exists
    reminder = getReminder(event['pathParameters']['reminder_id'])
    if reminder == None:
        return {
            "statusCode": 404,
            "body": "Reminder not found" 
        }
    else:
        print(reminder)
    data = json.loads(event['body'],strict=False)

    validate_field(data,'notify_date_time')
    validate_field(data,'remind_msg')
    validate_notify_date_time(data)

    timestamp = int(time.time() * 1000)

    result = table.update_item(
        Key={
            'reminder_id': reminder['reminder_id'],
            'user_id': reminder['user_id']
        },
        UpdateExpression="SET notify_date_time= :notify_date_time, updated_at= :updated_at, remind_msg= :remind_msg",
        ExpressionAttributeValues={
                    ':notify_date_time':data['notify_date_time'],
                    ':remind_msg' : data['remind_msg'],
                    ':updated_at':timestamp
        }
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result),
    }

# Mark reminder as deleted in DynamoDB
def delete_reminder(event, context):
    #check if reminder exists
    reminder = getReminder(event['pathParameters']['reminder_id'])
    if reminder == None:
        return {
            "statusCode": 404,
            "body": "Reminder not found" 
        }
    else:
        print(reminder)
    result = table.delete_item(
        Key={
            'reminder_id': reminder['reminder_id'],
            'user_id': reminder['user_id']
        }
    )
    return {
        "statusCode": 200,
        "body": json.dumps(result) 

    }

# Mark reminder as acknowledged in DynamoDB
def ack_reminder(event, context):
    timestamp = int(time.time() * 1000)
    #check if reminder exists
    reminder = getReminder(event['pathParameters']['reminder_id'])
    if reminder == None:
        return {
            "statusCode": 404,
            "body": "Reminder not found" 
        }
    else:
        print(reminder)
    result = table.update_item(
        Key={
            'reminder_id': reminder['reminder_id'],
            'user_id': reminder['user_id']
        },
        UpdateExpression="SET #st= :state, updated_at= :updated_at, to_execute= :to_execute",
        ExpressionAttributeValues={
                    ':state':'Acknowledged',
                    ':updated_at':timestamp,
                    ':to_execute':'false'
        },
        ExpressionAttributeNames={
            "#st": "state"
        }
    )

    return {
        "statusCode": 200,
        "body": json.dumps(result) 
    }

# Mark reminder as acknowledged in DynamoDB
def list_reminders(event, context):
    user_id = event['pathParameters']['user_id']

    response = table.query(
        IndexName='UserIdIndex',
        KeyConditionExpression=Key('user_id').eq(user_id))

    return {
        "statusCode": 200,
        "body": json.dumps(response['Items']),
    }

def getReminder(reminder_id):
    #fetch the reminder
    try:
        response = table.query(
        KeyConditionExpression=Key('reminder_id').eq(reminder_id)
    )
    except ClientError as e:
        print(e.response['Error']['Message'])
        logging.info(e.response['Error']['Message'])
        return None
    else:
        item = None if len(response['Items']) == 0 else response['Items'][0]
        logging.info("GetItem succeeded:")
        print("GetItem succeeded:")
        logging.info(item)
        return item