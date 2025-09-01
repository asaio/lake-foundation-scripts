import boto3
import uuid

lakeformation = boto3.client("lakeformation")

MAX_EXPRESSION_LENGTH = 2000

def chunked_exclusion_expressions(column_values, column_name, column_type, notation_type="dot"):
    """
    Returns a list of PartiQL exclusion expressions, each ≤ 2000 characters.
    """
    expressions = []
    current_values = []

    def format_column(col):
        return f"{notation_type}.{col}" if notation_type == "dot" else f"{notation_type}['{col}']"

    def build_expression(values):
        formatted_values = [f"'{v}'" if column_type == "string" else str(v) for v in values]
        return f"{format_column(column_name)} NOT IN ({', '.join(formatted_values)})"

    for value in column_values:
        current_values.append(value)
        test_expr = build_expression(current_values)
        if len(test_expr) > MAX_EXPRESSION_LENGTH:
            expressions.append(build_expression(current_values[:-1]))
            current_values = [value]

    if current_values:
        expressions.append(build_expression(current_values))

    return expressions

def create_data_filters(databases_tables, column_values, column_name, column_type, notation_type="dot"):
    """
    Creates Lake Formation data filters for each database/table pair.
    """
    for db_name, table_name in databases_tables:
        expressions = chunked_exclusion_expressions(column_values, column_name, column_type, notation_type)
        for i, expr in enumerate(expressions):
            filter_name = f"{table_name}_filter_{i}_{uuid.uuid4().hex[:6]}"
            print(f"Creating filter: {filter_name} on {db_name}.{table_name}")
            lakeformation.create_data_cells_filter(
                TableData={
                    "TableCatalogId": boto3.client("sts").get_caller_identity()["Account"],
                    "DatabaseName": db_name,
                    "TableName": table_name,
                    "Name": filter_name,
                    "RowFilter": {
                        "FilterExpression": expr
                    },
                    "ColumnNames": [column_name]
                }
            )

# 🧪 Example usage
if __name__ == "__main__":
    databases_tables = [
        ("sales_db", "orders"),
        ("marketing_db", "leads")
    ]
    values_to_exclude = [f"user{i}" for i in range(1, 1000)]  # Example values
    create_data_filters(
        databases_tables,
        column_values=values_to_exclude,
        column_name="user_id",
        column_type="string",
        notation_type="dot"
    )
