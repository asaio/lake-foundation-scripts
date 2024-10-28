import boto3
import time

def assume_role(account_id, role_name):
    """
    Assume an IAM role in a different AWS account
    
    Args:
        account_id (str): AWS account ID to assume role in
        role_name (str): Name of the role to assume
        
    Returns:
        boto3.Session: Session with assumed role credentials
    """
    sts_client = boto3.client('sts')
    
    role_arn = f'arn:aws:iam::{account_id}:role/{role_name}'
    
    try:
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f'GlueCleanup-{int(time.time())}',
            DurationSeconds=3600
        )
        
        credentials = response['Credentials']
        
        session = boto3.Session(
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )
        
        return session
    
    except Exception as e:
        print(f"Error assuming role in account {account_id}: {str(e)}")
        return None

def delete_glue_database(glue_client, database_name):
    """
    Delete a Glue database
    
    Args:
        glue_client: Boto3 Glue client
        database_name (str): Name of the database to delete
    """
    try:
        # First, get all tables in the database
        paginator = glue_client.get_paginator('get_tables')
        tables = []
        
        for page in paginator.paginate(DatabaseName=database_name):
            tables.extend(page['TableList'])
        
        # Delete all tables first
        for table in tables:
            try:
                glue_client.delete_table(
                    DatabaseName=database_name,
                    Name=table['Name']
                )
                print(f"Deleted table {table['Name']} from database {database_name}")
            except Exception as e:
                print(f"Error deleting table {table['Name']}: {str(e)}")
        
        # Then delete the database
        glue_client.delete_database(Name=database_name)
        print(f"Successfully deleted database {database_name}")
        
    except Exception as e:
        print(f"Error deleting database {database_name}: {str(e)}")

def main():
    # Role name to assume in target accounts
    ROLE_NAME = 'YourCrossAccountRole'
    
    # Dictionary of account IDs and their databases to delete
    account_databases = {
        '123456789012': ['database1', 'database2', 'database3'],
        '987654321098': ['database4', 'database5']
    }
    
    # Process each account
    for account_id, databases in account_databases.items():
        print(f"\nProcessing account: {account_id}")
        
        # Assume role in the target account
        session = assume_role(account_id, ROLE_NAME)
        
        if session:
            # Create Glue client with assumed role
            glue_client = session.client('glue')
            
            # Process each database in the account
            for database in databases:
                print(f"\nDeleting database: {database}")
                delete_glue_database(glue_client, database)
        else:
            print(f"Skipping account {account_id} due to role assumption failure")

if __name__ == "__main__":
    main()
