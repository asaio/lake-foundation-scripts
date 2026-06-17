# Devin AWS Athena Analysis Playbook (Extended)

## Step 1: Request AWS Access
- Prompt the user to provide **AWS account credentials** (IAM role or access keys).
- Confirm that the credentials have sufficient permissions for:
  - Creating Athena workgroups
  - Managing provisioned capacity
  - Running queries
  - Creating tables and datasets

---

## Step 2: Create a Dedicated Workgroup
- Provision a new Athena workgroup with **4 DPU capacity**.
- Associate the provisioned capacity with the new workgroup.
- Confirm successful creation and association.

---

## Step 3: Define User’s Analysis Goals
- Ask the user:
  - **What data analysis do you want to perform?**
  - **What question do you want answered?**

---

## Step 4: Identify Relevant Tables
- Request **fully qualified table names** in `database.table` notation.
- Ask:
  - Should the agent **limit itself to those tables**?
  - Or can it **browse all accessible tables**?

---

## Step 5: Propose Analytical Techniques
- Based on the user’s question and tables:
  - Suggest **analysis methods** (e.g., descriptive statistics, regression, clustering).
  - Outline **statistical techniques** (e.g., hypothesis testing, correlation, time-series analysis).
- Example:
  - “To answer your question, I will use **summary statistics** and a **linear regression model**.”

---

## Step 6: User Validation
- Prompt the user to:
  - **Accept** the proposed techniques
  - Or **increment/modify** them (e.g., add advanced ML methods)

---

## Step 7: Execute Analysis
- Only after user approval:
  - Run the queries in **AWS Athena** using the defined workgroup.
  - Apply the agreed-upon techniques.
  - Return results in a clear, structured format.

---

## Step 8: Deliver Results
- Present findings with:
  - **Query outputs**
  - **Statistical interpretations**
  - **Visual summaries** (charts, tables, dashboards if supported)

---

## Step 9: Optional Table Creation
- Ask the user:
  - **Do you want to create new tables with the analysis results?**
- If yes:
  - Prepare SQL statements to create and populate those tables in Athena.
  - Confirm table names and schema with the user before execution.

---

## Step 10: Optional Reporting & Visualization
- Ask the user:
  - **Do you want to generate HTML documents with graphs?**
  - **Do you want to prepare QuickSight datasets and analyses from those tables?**
- If yes:
  - Devin should prepare (but not execute) **boto3 QuickSight API calls**.
  - Provide the user with a `.py` file containing the prepared API requests.
  - Under no circumstances should Devin actually make the API calls.

---

## Workflow Summary
1. **[Request AWS credentials](ca://s?q=Request_AWS_credentials)**
2. **[Create Athena workgroup](ca://s?q=Create_Athena_workgroup_with_4_DPU)**
3. **[Ask analysis goals](ca://s?q=Ask_user_analysis_goals)**
4. **[Collect table names](ca://s?q=Collect_fully_qualified_table_names)**
5. **[Propose techniques](ca://s?q=Propose_analysis_techniques)**
6. **[Validate techniques](ca://s?q=Validate_analysis_techniques_with_user)**
7. **[Run Athena queries](ca://s?q=Run_Athena_queries_with_user_approval)**
8. **[Deliver results](ca://s?q=Deliver_analysis_results_to_user)**
9. **[Create tables](ca://s?q=Create_tables_with_analysis_results)**
10. **[Prepare QuickSight API](ca://s?q=Prepare_QuickSight_API_requests_with_boto3)**
