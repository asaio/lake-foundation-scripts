import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import time
from datetime import datetime

def start_codepipeline(session, pipeline_name):
    codepipeline_client = session.client('codepipeline')
    try:
        response = codepipeline_client.start_pipeline_execution(name=pipeline_name)
        return response
    except Exception as e:
        return str(e)

def list_pipeline_executions(session, pipeline_name):
    codepipeline_client = session.client('codepipeline')
    try:
        response = codepipeline_client.list_pipeline_executions(pipelineName=pipeline_name, maxResults=1)
        if response['pipelineExecutionSummaries']:
            return response['pipelineExecutionSummaries'][0]
        else:
            return "No executions found"
    except Exception as e:
        return str(e)

def write_results_to_file(results, file_prefix):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    filename = f"{timestamp}_{file_prefix}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"Results written to {filename}")

def run_pipeline_operations():
    # List of AWS account IDs
    account_ids = [
        "123456789012",
        "234567890123",
        "345678901234",
        # Add more account IDs as needed
    ]
    
    pipeline_name = "YourCodePipelineName"
    
    start_results = {}
    execution_results = {}
    
    # Start pipeline executions
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_account = {
            executor.submit(
                start_codepipeline, 
                boto3.session.Session(),
                pipeline_name
            ): account_id for account_id in account_ids
        }
        
        for future in as_completed(future_to_account):
            account_id = future_to_account[future]
            try:
                result = future.result()
                start_results[account_id] = result
            except Exception as exc:
                start_results[account_id] = str(exc)
    
    write_results_to_file(start_results, "start_pipeline")
    
    # Wait for 180 seconds
    print("Waiting for 180 seconds...")
    time.sleep(180)
    
    # List pipeline executions
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_account = {
            executor.submit(
                list_pipeline_executions, 
                boto3.session.Session(),
                pipeline_name
            ): account_id for account_id in account_ids
        }
        
        for future in as_completed(future_to_account):
            account_id = future_to_account[future]
            try:
                result = future.result()
                execution_results[account_id] = result
            except Exception as exc:
                execution_results[account_id] = str(exc)
    
    write_results_to_file(execution_results, "list_executions")

    # List comprehension for non-Succeeded executions
    non_succeeded_executions = [
        account_id for account_id, execution in execution_results.items()
        if isinstance(execution, dict) and execution.get('status') != 'Succeeded'
    ]

    print("\nAccounts with non-Succeeded pipeline executions:")
    print(json.dumps(non_succeeded_executions, indent=2))

    return non_succeeded_executions

def main():
    while True:
        non_succeeded_executions = run_pipeline_operations()
        
        if non_succeeded_executions:
            retry = input("There are non-succeeded executions. Do you want to retry? (yes/no): ").lower()
            if retry != 'yes':
                break
        else:
            print("All pipeline executions succeeded.")
            break

if __name__ == "__main__":
    main()
