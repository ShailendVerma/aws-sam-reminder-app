import json
import boto3

# Create a reminder and store in dynamoDB
# Create a scheduled event
# validate not less than {MIN_DELAY_PARAM} mins left
def create_reminder(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }

# Update a reminder in DynamoDB - ideally date change
# Validate not less than {MIN_DELAY_PARAM} mins left 
def update_reminder(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }

# Mark reminder as deleted in DynamoDB
def delete_reminder(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }

# Mark reminder as acknowledged in DynamoDB
def ack_reminder(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }