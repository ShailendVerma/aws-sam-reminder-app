import json
import boto3

# Gets triggered by cloud wath event
# Check if reminder is still in pending state and the execution date is in the past
# Check mode email or sms and send out email
# Update state to triggered and retryCount +=1
# Create event to check if reminder is in acknowledged in 15 mins else mark as pending self again
# if retryCount >= {MAX_RETRIES} mark the reminder as unacknowledged in dynamoDB
def execute_reminder(event, context):
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "hello world",
            # "location": ip.text.replace("\n", "")
        }),
    }
