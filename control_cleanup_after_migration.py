import boto3
import json

def lambda_handler(event, context):
    # Initialize boto3 clients
    lakeformation = boto3.client('lakeformation')
    glue = boto3.client('glue')
    
    # Dictionary of account IDs (principals) and their corresponding database names
    account_db_dict = {
        "123456789012": ["account1_database1", "account1_database2", "account1_database3"],
        "234567890123": ["account2_database1", "account2_database2", "account2_database3"],
        "345678901234": ["account3_database1", "account3_database2", "account3_database3"]
    }
    
    # List of permissions to revoke
    permissions_to_revoke = [
        "ALTER",
        "CREATE_TABLE",
        "DROP",
        "DESCRIBE"
    ]
    
    # Results dictionary to store API responses
    results = {}
    
    for account_id, database_names in account_db_dict.items():
        results[account_id] = {
            'revoke': {},
            'delete_db': {}
        }
        
        for database_name in database_names:
            # 1. Revoke Lake Formation permissions
            try:
                revoke_response = lakeformation.batch_revoke_permissions(
                    Entries=[
                        {
                            'Id': f'revoke-{account_id}-{perm}-{database_name}',
                            'Principal': {
                                'DataLakePrincipalIdentifier': account_id
                            },
                            'Resource': {
                                'Database': {
                                    'Name': database_name
                                }
                            },
                            'Permissions': [perm],
                            'PermissionsWithGrantOption': [perm]
                        } for perm in permissions_to_revoke
                    ]
                )
                results[account_id]['revoke'][database_name] = revoke_response
                print(f"Successfully revoked permissions for account {account_id} on database {database_name}")
            except Exception as e:
                results[account_id]['revoke'][database_name] = str(e)
                print(f"Error revoking permissions for account {account_id} on database {database_name}: {str(e)}")
            
            # 2. Delete the Glue database
            try:
                delete_response = glue.delete_database(Name=database_name)
                results[account_id]['delete_db'][database_name] = delete_response
                print(f"Successfully deleted database {database_name}")
            except Exception as e:
                results[account_id]['delete_db'][database_name] = str(e)
                print(f"Error deleting database {database_name}: {str(e)}")
    
    return {
        'statusCode': 200,
        'body': json.dumps(results, default=str)
    }
