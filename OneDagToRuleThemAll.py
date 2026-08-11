from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
import boto3
import casing
import json
import os

def format_parameters_for_shape(shape, params):
    """Filter only valid keys from params and adjust casing to match the shape."""
    formatted = {}
    if hasattr(shape, "members"):
        for expected_key in shape.members.keys():
            for user_key, value in params.items():
                variants = [
                    casing.pascalcase(user_key),
                    casing.camelcase(user_key),
                    casing.snakecase(user_key),
                    casing.kebabcase(user_key),
                ]
                if expected_key in variants or expected_key.lower() == user_key.lower():
                    formatted[expected_key] = value
    return formatted


def execute_payload_iterative(payload):
    """Iteratively execute payloads, handling multiple nested AssumeRole hops."""
    current_payload = payload
    client = None
    results = []

    while current_payload:
        service = current_payload["service"]
        operations = current_payload["operations"]
        parameters = current_payload["parameters"]

        if client is None:
            client = boto3.client(service)

        service_model = client.meta.service_model

        for op, params in zip(operations, parameters):
            if op not in service_model.operation_names:
                raise ValueError(f"Operation {op} not valid for {service}")

            op_model = service_model.operation_model(op)
            input_shape = op_model.input_shape
            formatted_params = format_parameters_for_shape(input_shape, params)

            response = client._make_api_call(op, formatted_params)
            results.append({op: response})

            if service == "sts" and op == "AssumeRole" and "nested" in current_payload:
                creds = response["Credentials"]
                nested = current_payload["nested"]

                client = boto3.client(
                    nested["service"],
                    aws_access_key_id=creds["AccessKeyId"],
                    aws_secret_access_key=creds["SecretAccessKey"],
                    aws_session_token=creds["SessionToken"],
                )
                current_payload = nested
                break
        else:
            current_payload = None

    return results


def aws_low_level_runner(file_name: str, **context):
    """
    Load JSON payload from MWAA input directory and execute.
    """
    # MWAA typically mounts S3 paths into /usr/local/airflow/dags or a configured input dir
    input_dir = os.environ.get("MWAA_INPUT_DIR", "/usr/local/airflow/dags/input")
    file_path = os.path.join(input_dir, file_name)

    with open(file_path, "r") as f:
        payload = json.load(f)

    return execute_payload_iterative(payload)


with DAG(
    dag_id="aws_low_level_file_input_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,
    catchup=False,
) as dag:

    run_aws_ops = PythonOperator(
        task_id="run_aws_ops",
        python_callable=aws_low_level_runner,
        op_kwargs={
            # Pass the filename of the JSON you’ve uploaded to MWAA’s input directory
            "file_name": "payload.json"
        },
    )

    run_aws_ops
