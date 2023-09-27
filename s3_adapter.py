import boto3

class S3Adapter(ObjectStorageInterface):
    def __init__(self):
        # Initialize the S3 client
        self.s3_client = boto3.client('s3')

    def get_versioning_configuration(self, bucket_name):
        response = self.s3_client.get_bucket_versioning(Bucket=bucket_name)
        return response.get('Status')

    def update_versioning_configuration(self, bucket_name, status):
        self.s3_client.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={
                'Status': status
            }
        )
