import boto3
from boto3.dynamodb.conditions import Attr

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("assets")

response = table.scan(
    FilterExpression=Attr("typeMesh").eq("CONSUMER")
    & (Attr("isRetired").not_exists() | Attr("isRetired").eq(""))
)

items = response["Items"]
print(items)
