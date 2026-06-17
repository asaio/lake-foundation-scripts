Playbook: Devin AWS Athena Analysis

## Overview
Create an AWS Athena analysis workflow using a dedicated workgroup and optimized query strategies, with optional reporting and visualization via QuickSight.

## What’s Needed From User
- AWS account credentials (IAM role or access keys with required permissions)
- Analysis goal or question to be answered
- Fully qualified table names (`database.table`) relevant to the analysis
- Confirmation whether to limit queries to those tables or allow browsing all accessible tables
- Athena Data Source ID for QuickSight (if reporting/visualization is requested)

## Procedure
1. Request AWS credentials from the user and validate permissions.
2. Create a new Athena workgroup named with prefix `consumer-Devin-<unique_suffix>` and provision **4 DPU capacity**.
3. Associate the provisioned capacity with the new workgroup.
4. Ask the user to specify the analysis goal or question.
5. Collect fully qualified table names from the user and confirm query scope (restricted vs. all tables).
6. Propose optimized query strategies:
   - Predicate pushdown (filter early to reduce scanned data)
   - Column pruning (select only necessary columns)
   - Partition awareness
   - Use compressed columnar formats (Parquet/ORC)
7. Suggest statistical and analytical techniques based on the user’s goal.
8. Prompt the user to accept or modify the proposed techniques.
9. Execute the analysis in Athena using the optimized queries and agreed techniques.
10. Create new tables for analysis results, prefixed with `devin_analysis_<succinct_description>`.
11. Ask if the user wants reporting/visualization:
   - If yes, require Athena Data Source ID.
   - Prepare QuickSight datasets pointing to the `devin_analysis_` tables via Athena data source.
   - Prepare (but do not execute) boto3 QuickSight API calls in a `.py` file.
   - Optionally generate HTML documents with graphs.
12. Cancel the provisioned capacity associated with the workgroup (mandatory).

## Specifications
1. Workgroup names must start with `consumer-Devin-`.
2. Analysis tables must start with `devin_analysis_` followed by a succinct descriptive name.
3. QuickSight datasets must point to Athena data source tables created for the analysis.
4. Provisioned capacity must always be cancelled at the end of the workflow.

## Advice and Pointers
1. Always apply predicate pushdown and column pruning to minimize Athena costs.
2. Use partitioned and columnar formats when creating new tables.
3. Avoid duplicating data in QuickSight SPICE unless explicitly requested by the user.
4. Ensure the Athena Data Source ID is provided before preparing QuickSight API calls.

## Forbidden Actions
1. Do not execute QuickSight API calls directly — only prepare the `.py` file.
2. Do not leave provisioned capacity active after workflow completion.
3. Do not create tables without the `devin_analysis_` prefix.
