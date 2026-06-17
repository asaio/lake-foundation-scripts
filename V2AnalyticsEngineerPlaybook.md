# Devin AWS Athena Analysis Playbook (Cost-Optimized, Mandatory Capacity Cancellation)

## Step 1: Request AWS Access
- Ask the user for AWS account credentials (IAM role or access keys).
- Confirm permissions for:
  - Athena workgroups
  - Provisioned capacity
  - Query execution
  - Table creation and dataset management

---

## Step 2: Create a Dedicated Workgroup
- Create a new Athena workgroup named with prefix:  
  **consumer-Devin-<unique_suffix>**
- Provision **4 DPU capacity**.
- Associate provisioned capacity with the workgroup.
- Emphasize that provisioned capacity ensures predictable cost and performance.

---

## Step 3: Define Analysis Goals
- Ask the user:
  - What **data analysis** they want to perform.
  - What **question** they want answered.

---

## Step 4: Identify Relevant Tables
- Request **fully qualified table names** (`database.table`).
- Ask if Devin should:
  - **Limit queries to those tables** (reduces scan costs).
  - Or **browse all accessible tables** (broader scope, higher cost).

---

## Step 5: Optimize Query Strategy
- Inform the user that Devin will:
  - Apply **predicate pushdown** (filter early to reduce scanned data).
  - Use **column pruning** (select only necessary columns).
  - Leverage **partitioning** if available.
  - Use **compressed columnar formats** (e.g., Parquet/ORC) when creating tables.
- Explain how these techniques reduce Athena query costs.

---

## Step 6: Propose Analytical Techniques
- Suggest statistical methods tailored to user goals (e.g., descriptive stats, regression, hypothesis testing).
- Example: “To answer this, I’ll use **summary statistics** with **predicate filters** to minimize scanned data.”

---

## Step 7: User Validation
- Ask the user to:
  - **Accept** the proposed techniques.
  - Or **increment/modify** them (e.g., add clustering, advanced ML).

---

## Step 8: Execute Analysis
- Only after approval:
  - Run optimized queries in Athena using the workgroup.
  - Apply agreed techniques.
  - Return results in structured format.

---

## Step 9: Create Analysis Tables
- Prefix all new tables with:  
  **devin_analysis_<succinct_description>**
- Example: `devin_analysis_sales_summary`, `devin_analysis_customer_segments`.
- Ensure tables are optimized with partitioning and columnar formats.

---

## Step 10: Reporting & Visualization
- Ask if the user wants:
  - **HTML documents with graphs**.
  - **QuickSight datasets and analyses** from the new tables.
- If yes:
  - Require the user to provide the **Athena Data Source ID** for QuickSight.
  - Optimize QuickSight costs by:
    - Pointing datasets to the Athena data source.
    - Reading directly from the `devin_analysis_` tables.
    - Avoiding duplication of data in SPICE unless explicitly requested.
  - Prepare (but do not execute) **boto3 QuickSight API calls**.
  - Provide a `.py` file containing the prepared requests.
  - Never perform the API calls directly.

---

## Step 11: Cancel Provisioned Capacity (Mandatory)
- After analysis and optional reporting:
  - Devin must **always cancel the provisioned capacity** associated with the workgroup.
  - Prepare the boto3 call to release provisioned capacity.
  - Confirm cancellation to avoid ongoing costs.

---

## Workflow Summary
1. **[Request credentials](ca://s?q=Request_AWS_credentials)**
2. **[Create workgroup](ca://s?q=Create_consumer_Devin_Athena_workgroup_with_4_DPU)**
3. **[Ask analysis goals](ca://s?q=Ask_user_analysis_goals)**
4. **[Collect table names](ca://s?q=Collect_fully_qualified_table_names)**
5. **[Optimize queries](ca://s?q=Explain_predicate_pushdown_and_column_pruning)**
6. **[Propose techniques](ca://s?q=Propose_analysis_techniques)**
7. **[Validate techniques](ca://s?q=Validate_analysis_techniques_with_user)**
8. **[Run Athena queries](ca://s?q=Run_Athena_queries_with_user_approval)**
9. **[Create analysis tables](ca://s?q=Create_devin_analysis_tables)**
10. **[Prepare QuickSight API](ca://s?q=Prepare_QuickSight_API_requests_with_boto3_using_Athena_data_source_id)**
11. **[Cancel provisioned capacity](ca://s?q=Cancel_Athena_provisioned_capacity)**
