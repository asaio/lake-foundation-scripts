import boto3

class SSMAdapter(ParameterStoreInterface):
    def __init__(self):
        # Initialize the SSM client
        self.ssm_client = boto3.client('ssm')

    def get_parameter(self, name):
        response = self.ssm_client.get_parameter(Name=name, WithDecryption=True)
        return response['Parameter']['Value']
