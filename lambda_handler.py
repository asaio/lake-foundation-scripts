import boto3
import os
from update_versioning_use_case import UpdateVersioningUseCase  # Updated import

# Initialize AWS clients
ssm_client = boto3.client('ssm')

def lambda_handler(event, context):
    # Extract the parameter name from the CloudWatch Event
    parameter_name = event['detail']['requestParameters']['name']

    # Check if the event matches the expected parameter name
    expected_parameter_name = "/tag/name"

    if parameter_name == expected_parameter_name:
        # Create an instance of UpdateVersioningUseCase
        use_case = UpdateVersioningUseCase()  # Updated class name
        
        # Retrieve the parameter value from AWS SSM Parameter Store
        try:
            parameter_value = use_case.get_ssm_parameter(parameter_name)

            # Update storage versioning based on the parameter value
            use_case.update_storage_versioning(parameter_value)
            
            return {
                'statusCode': 200,
                'body': 'Versioning updated successfully'
            }
        except Exception as e:
            return {
                'statusCode': 500,
                'body': f'Error: {str(e)}'
            }
    else:
        # Event does not match the expected parameter name, no action needed
        return {
            'statusCode': 200,
            'body': 'Event does not match expected parameter name'
        }

# Example usage:
if __name__ == '__main__':
    event = {
        'detail': {
            'requestParameters': {
                'name': '/tag/name'  # Replace with your parameter name
            }
        }
    }
    context = None
    lambda_handler(event, context)
  
