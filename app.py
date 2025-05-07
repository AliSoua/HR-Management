import os
import re
import google.generativeai as genai
from flask import Flask, request, jsonify, render_template # Added render_template
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error as MySQLError
import datetime
import decimal
import json

# Load environment variables from .env file
load_dotenv()

# Configure Flask app
app = Flask(__name__)

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment variables. Please set it in .env file.")
genai.configure(api_key=GEMINI_API_KEY)

generation_config = {
  "temperature": 0.2,
  "top_p": 1,
  "top_k": 1,
  "max_output_tokens": 1024,
}
safety_settings = [
  {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

TUNED_MODEL_NAME = os.getenv("TUNED_GEMINI_MODEL_NAME")
BASE_MODEL_NAME = "gemini-2.0-flash" # Fallback
model_to_use = TUNED_MODEL_NAME if TUNED_MODEL_NAME else BASE_MODEL_NAME
print(f"Using Gemini model: {model_to_use}")

model = genai.GenerativeModel(model_name=model_to_use,
                              generation_config=generation_config,
                              safety_settings=safety_settings)

# --- MySQL Database Configuration ---
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

ALLOWED_WRITE_OPERATIONS = ["UPDATE", "INSERT"]

def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        if conn.is_connected():
            return conn
    except MySQLError as e:
        print(f"Error connecting to MySQL database: {e}")
        return None

def get_database_schema_description():
    # In a real application, you might fetch this dynamically using INFORMATION_SCHEMA
    # For now, we hardcode a detailed description.
    # CRITICAL: Keep this accurate and detailed.
    schema = f"""
    You have access to a MySQL database with the following tables for an HR Management system:

    1. Table: employees
       Description: Stores information about employees.
       Columns:
         - id (INT, PRIMARY KEY, AUTO_INCREMENT) - Unique identifier for the employee.
         - first_name (VARCHAR(50), NOT NULL) - First name of the employee.
         - last_name (VARCHAR(50), NOT NULL) - Last name of the employee.
         - email (VARCHAR(100), UNIQUE) - Email address of the employee.
         - phone_number (VARCHAR(20)) - Employee's phone number.
         - hire_date (DATE) - Date when the employee was hired (YYYY-MM-DD).
         - job_id (VARCHAR(10)) - Identifier for the employee's job role (e.g., IT_PROG, SA_REP, AD_PRES).
         - salary (DECIMAL(10, 2)) - Current monthly or annual salary of the employee.
         - commission_pct (DECIMAL(4,2)) - Commission percentage for sales staff (e.g., 0.10 for 10%). NULL if not applicable.
         - manager_id (INT, FOREIGN KEY to employees.id) - ID of the employee's manager. NULL if no manager (e.g., for CEO).
         - department_id (INT, FOREIGN KEY to departments.department_id) - ID of the department the employee belongs to.
         - insertion_date (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP) - Timestamp when the employee record was created.
         - last_payment_date (DATE) - Date of the most recent payment made to the employee.

    2. Table: departments
       Description: Stores information about company departments.
       Columns:
         - department_id (INT, PRIMARY KEY) - Unique identifier for the department.
         - department_name (VARCHAR(100), NOT NULL, UNIQUE) - Name of the department (e.g., 'IT', 'Sales', 'Human Resources').
         - location (VARCHAR(100)) - Physical location of the department.
       Relationships:
         - employees.department_id references departments.department_id

    3. Table: payments
       Description: Tracks salary payments, bonuses, and commissions paid to employees.
       Columns:
         - payment_id (INT, AUTO_INCREMENT, PRIMARY KEY) - Unique identifier for the payment.
         - employee_id (INT, NOT NULL, FOREIGN KEY to employees.id) - ID of the employee receiving the payment.
         - payment_date (DATE, NOT NULL) - Date the payment was made.
         - amount (DECIMAL(10, 2), NOT NULL) - Amount of the payment.
         - payment_type (VARCHAR(50), DEFAULT 'Salary') - Type of payment (e.g., 'Salary', 'Bonus', 'Commission').
         - notes (TEXT) - Optional notes about the payment.
       Relationships:
         - payments.employee_id references employees.id

    4. Table: leave_requests
       Description: Tracks employee requests for leave (vacation, sick leave, etc.).
       Columns:
         - leave_id (INT, AUTO_INCREMENT, PRIMARY KEY) - Unique identifier for the leave request.
         - employee_id (INT, NOT NULL, FOREIGN KEY to employees.id) - ID of the employee requesting leave.
         - leave_type (VARCHAR(50), NOT NULL, DEFAULT 'Vacation') - Type of leave (e.g., 'Vacation', 'Sick', 'Personal').
         - start_date (DATE, NOT NULL) - Start date of the leave period.
         - end_date (DATE, NOT NULL) - End date of the leave period.
         - status (VARCHAR(20), NOT NULL, DEFAULT 'Pending') - Status of the request ('Pending', 'Approved', 'Rejected', 'Cancelled').
         - reason (TEXT) - Reason for the leave request (optional).
         - requested_date (TIMESTAMP, DEFAULT CURRENT_TIMESTAMP) - When the leave was requested.
         - approved_by (INT, FOREIGN KEY to employees.id) - ID of the manager who approved/rejected the leave. NULL if pending or self-approved.
       Relationships:
         - leave_requests.employee_id references employees.id
         - leave_requests.approved_by references employees.id

    General Querying Notes:
    - When asked for information that spans multiple tables, use appropriate JOIN clauses.
      For example, to get employee names and their department names, JOIN employees with departments on department_id.
    - 'insertion_date' in 'employees' is for when the record was created. 'hire_date' is the official start date.
    - 'last_payment_date' in 'employees' can be used for "who was paid last", but for detailed payment history or amounts, query the 'payments' table.
    - For leave status or history, query the 'leave_requests' table.

    IMPORTANT FOR ADDING EMPLOYEES:
    If the user expresses an intent to "add a new employee", "hire someone", or "insert a new employee record",
    your primary response should be "LOAD_ADD_EMPLOYEE_FORM".
    You can optionally try to extract any mentioned details (like name, department, salary) and provide them as pre_fill_data.
    Example: "Add a new Sales Rep named Alice Wonderland with salary 80000 in the Oxford Sales department."
    Response should be "LOAD_ADD_EMPLOYEE_FORM" with pre_fill_data:
    pre_fill_data: {{"first_name": "Alice", "last_name": "Wonderland", "department_id": 80, "job_id": "SA_REP", "salary": 80000}}

    IMPORTANT NOTE FOR UPDATES WITH LIMIT:
    If you need to update a limited number of rows from the 'employees' table (e.g., "update the first 3 employees"),
    MySQL/MariaDB does not support 'LIMIT' directly in a subquery within an 'IN' clause for an UPDATE on the same table.
    Instead, use a JOIN with a derived table.
    Example: To update the hire_date for the first 3 employees (ordered by id):
    UPDATE employees e
    JOIN (SELECT id FROM employees ORDER BY id ASC LIMIT 3) AS temp_ids ON e.id = temp_ids.id
    SET e.hire_date = 'YYYY-MM-DD';
    ALWAYS include an ORDER BY clause with LIMIT to ensure deterministic results for which rows are selected.
    Today's date is {datetime.date.today().isoformat()}.
    """
    return schema.strip()

def generate_sql_with_gemini(user_message: str, schema_description: str, allow_writes: bool = False) -> tuple[str | None, str | None, dict | None]:
    allowed_operations_str = "SELECT"
    if allow_writes:
        allowed_operations_str += ", " + ", ".join(ALLOWED_WRITE_OPERATIONS)

    prompt = f"""
    Given the following database schema:
    {schema_description}

    And the user's question/command:
    "{user_message}"

    Analyze the user's intent.
    1. If the user wants to query data (e.g., "show me", "find", "list", "what is"), generate a MySQL SELECT query.
    2. If the user wants to modify existing data (e.g., "update salary", "change department"), generate a MySQL UPDATE query.
    3. If the user explicitly wants to "add a new employee", "hire someone", or "insert a new employee record":
       Respond with the exact text "LOAD_ADD_EMPLOYEE_FORM".
       Optionally, if you can extract details like name, department, salary, etc., from the user's message,
       provide them in a JSON string format after "LOAD_ADD_EMPLOYEE_FORM" on a new line, like this:
       LOAD_ADD_EMPLOYEE_FORM
       pre_fill_data: {{"first_name": "example", "salary": "50000"}}
       (Only include pre_fill_data if details are clearly mentioned for a new employee).
    4. If the question cannot be answered or the command cannot be fulfilled with the allowed SQL types or actions, respond with "CANNOT_ANSWER".
    5. If the question is a greeting, farewell, or general chit-chat not related to data, respond with "GENERAL_CHAT".

    Response (SQL Query, or "LOAD_ADD_EMPLOYEE_FORM" potentially with pre_fill_data, or "CANNOT_ANSWER", or "GENERAL_CHAT"):
    """
    print(f"\n--- Gemini Prompt for SQL/Action Generation ---\n{prompt}\n---------------------------------------\n")
    pre_fill_data = None
    try:
        response = model.generate_content(prompt)
        if response.parts:
            generated_text_full = response.text.strip()
            print(f"Gemini Raw Response: '{generated_text_full}'")

            lines = generated_text_full.split('\n')
            main_response_line = lines[0].strip()

            if main_response_line == "LOAD_ADD_EMPLOYEE_FORM":
                if len(lines) > 1 and lines[1].strip().startswith("pre_fill_data:"):
                    try:
                        json_str = lines[1].strip().replace("pre_fill_data:", "").strip()
                        pre_fill_data = json.loads(json_str)
                    except json.JSONDecodeError as e:
                        print(f"Warning: Could not parse pre_fill_data JSON: {e}. JSON string was: {json_str}")
                        pre_fill_data = {}
                    except Exception as e_gen:
                        print(f"Warning: General error processing pre_fill_data: {e_gen}")
                        pre_fill_data = {}
                return "LOAD_ADD_EMPLOYEE_FORM", "LOAD_ADD_EMPLOYEE_FORM", pre_fill_data

            if main_response_line == "CANNOT_ANSWER" or main_response_line == "GENERAL_CHAT":
                return main_response_line, main_response_line.upper(), None

             # Use generated_text_full for SQL extraction, not just the first line
            potential_sql = generated_text_full 
            
            # Remove markdown backticks and any "sql" language specifier
            cleaned_sql = re.sub(r"^```(?:sql)?\s*", "", potential_sql, flags=re.IGNORECASE | re.MULTILINE)
            cleaned_sql = re.sub(r"\s*```$", "", cleaned_sql, flags=re.MULTILINE)
            cleaned_sql = cleaned_sql.strip() # This should now be the pure SQL

            query_upper = cleaned_sql.upper() # Use the cleaned version for type checking
            query_type = None
            if query_upper.startswith("SELECT"):
                query_type = "SELECT"
            elif allow_writes:
                for op_type in ALLOWED_WRITE_OPERATIONS:
                    if query_upper.startswith(op_type):
                        query_type = op_type
                        break
            
            if query_type:
                return cleaned_sql, query_type, None # Return the fully cleaned SQL
            else:
                # This 'else' block is being hit because query_upper (from the cleaned full text)
                # doesn't start with a recognized command.
                print(f"Warning: Gemini returned an unsupported or disallowed query type after cleaning. Original Raw: '{generated_text_full}', Cleaned attempt: '{cleaned_sql}'")
                return "CANNOT_ANSWER", "CANNOT_ANSWER", None
        else:
            print("Warning: Gemini response has no parts. Content might be blocked.")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                 print(f"Block reason: {response.prompt_feedback.block_reason}")
            return "CANNOT_ANSWER", "CANNOT_ANSWER", None
    except Exception as e:
        print(f"Error calling Gemini API for SQL generation: {e}")
        return None, None, None

def execute_query(sql_query: str, query_type: str, params: tuple = None) -> dict:
    """
    Executes the SQL query.
    For SELECT, returns data.
    For INSERT/UPDATE/DELETE, returns affected_rows and success message.
    `params` is a tuple of values for parameterized queries.
    """
    conn = get_db_connection()
    if not conn:
        return {"error": "Database connection failed."}

    cursor = None
    try:
        # Use dictionary=True only for SELECT to get column names in results
        cursor = conn.cursor(dictionary=(query_type == "SELECT"))
        
        print(f"Executing {query_type} SQL: {sql_query}")
        if params:
            print(f"With parameters: {params}")
            cursor.execute(sql_query, params)
        else:
            cursor.execute(sql_query)

        if query_type == "SELECT":
            results = cursor.fetchall()
            print(f"Query executed successfully. Fetched {len(results)} rows.")
            for row in results: # Ensure results are dictionary for SELECT before processing
                if isinstance(row, dict): # Should be true if dictionary=True was set
                    for key, value in row.items():
                        if isinstance(value, (datetime.date, datetime.datetime)):
                            row[key] = value.isoformat()
                        elif isinstance(value, decimal.Decimal):
                            row[key] = float(value)
            return {"data": results, "rows_affected": len(results)}
        elif query_type in ALLOWED_WRITE_OPERATIONS:
            conn.commit()
            affected_rows = cursor.rowcount
            last_row_id = cursor.lastrowid if query_type == "INSERT" else None
            print(f"{query_type} executed successfully. {affected_rows} rows affected. Last ID: {last_row_id}")
            response = {"message": f"{query_type} successful. {affected_rows} row(s) affected.", "rows_affected": affected_rows}
            if last_row_id is not None:
                response["new_employee_id"] = last_row_id
            return response
        else:
            # This case should ideally not be reached if query_type is validated before calling
            return {"error": "Unsupported query type for execution."}

    except MySQLError as e:
        print(f"Error executing {query_type} query '{sql_query}': {e}")
        if conn:
            try:
                conn.rollback()
            except MySQLError as rb_err:
                print(f"Error during rollback: {rb_err}")
        return {"error": str(e), "query_attempted": sql_query}
    except ValueError as ve:
         return {"error": str(ve), "query_attempted": sql_query}
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat_handler():
    data = request.get_json()
    user_message = data.get("message")
    is_confirmed_execution = data.get("confirmed_execution", False)
    form_data_for_add = data.get("add_employee_form_data")

    if form_data_for_add:
        try:
            required_fields = ["first_name", "last_name", "email", "hire_date", "salary"]
            for field in required_fields:
                if not form_data_for_add.get(field): # Check if field exists and is not empty
                    return jsonify({"response_text": f"Missing required field: {field}", "type": "FORM_ERROR"}), 400

            columns = []
            values_placeholders = []
            values_data = []
            field_to_column = {
                "first_name": "first_name", "last_name": "last_name", "email": "email",
                "phone_number": "phone_number", "hire_date": "hire_date", "job_id": "job_id",
                "salary": "salary", "commission_pct": "commission_pct",
                "manager_id": "manager_id", "department_id": "department_id"
            }

            for field, db_col in field_to_column.items():
                value = form_data_for_add.get(field)
                if value is not None and value != '': # Process if value exists and is not an empty string
                    columns.append(db_col)
                    values_placeholders.append("%s")
                    
                    if db_col in ["salary", "commission_pct"]:
                        values_data.append(decimal.Decimal(value))
                    elif db_col in ["manager_id", "department_id"]:
                        values_data.append(int(value))
                    else:
                        values_data.append(value)
            
            if not columns:
                 return jsonify({"response_text": "No valid data provided for new employee.", "type": "FORM_ERROR"}), 400

            sql_query_insert = f"INSERT INTO employees ({', '.join(columns)}) VALUES ({', '.join(values_placeholders)})"
            execution_result = execute_query(sql_query_insert, "INSERT", tuple(values_data))

            if "error" in execution_result:
                 return jsonify({
                    "response_text": f"Database error on insert: {execution_result['error']}",
                    "type": "EXECUTION_ERROR",
                    "query_attempted": sql_query_insert # Be cautious showing full query with data
                }), 500
            
            return jsonify({
                "response_text": execution_result.get("message", "New employee added."),
                "type": "ACTION_SUCCESS",
                "rows_affected": execution_result.get("rows_affected"),
                "new_employee_id": execution_result.get("new_employee_id"),
                "query_executed": "INSERT statement from form data"
            })

        except ValueError as ve:
            return jsonify({"response_text": f"Invalid data format: {ve}", "type": "FORM_ERROR"}), 400
        except Exception as ex_form:
             print(f"Error processing add employee form data: {ex_form}")
             return jsonify({"response_text": "Error processing new employee data.", "type": "FORM_ERROR"}), 500

    if not user_message or not isinstance(user_message, str) or not user_message.strip():
        return jsonify({"error": "Message must be a non-empty string"}), 400

    print(f"\nReceived message: {user_message}, Confirmed: {is_confirmed_execution}")
    schema_desc = get_database_schema_description()
    allow_writes_for_this_request = True

    generated_command, command_type, pre_fill_data = generate_sql_with_gemini(user_message, schema_desc, allow_writes=allow_writes_for_this_request)

    if generated_command is None or command_type is None:
        return jsonify({"response_text": "Sorry, I encountered an error trying to understand that.", "type": "ERROR"}), 500

    if command_type == "LOAD_ADD_EMPLOYEE_FORM":
        return jsonify({
            "response_text": "Okay, let's add a new employee. Please fill out the form.",
            "type": "LOAD_COMPONENT",
            "component_name": "add_employee_form",
            "pre_fill_data": pre_fill_data if pre_fill_data else {}
        })

    if command_type == "CANNOT_ANSWER":
        return jsonify({"response_text": "I'm sorry, I can't answer that or it's too ambiguous. Can you rephrase?", "type": "CLARIFICATION"})
    if command_type == "GENERAL_CHAT":
        if "hello" in user_message.lower() or "hi" in user_message.lower():
             return jsonify({"response_text": "Hello! How can I help you with HR data today?", "type": "CHAT"})
        elif "bye" in user_message.lower() or "thanks" in user_message.lower():
             return jsonify({"response_text": "You're welcome! Goodbye.", "type": "CHAT"})
        return jsonify({"response_text": "I can help with questions about employee data. What would you like to know?", "type": "CHAT"})

    sql_query = generated_command
    if command_type in ALLOWED_WRITE_OPERATIONS and not is_confirmed_execution:
        confirmation_message = f"I understand you want to perform a {command_type.lower()} operation. The generated query is: `{sql_query}`. Are you sure you want to proceed?"
        return jsonify({
            "response_text": confirmation_message,
            "type": "CONFIRMATION_REQUIRED",
            "query_to_confirm": sql_query,
            "query_type_to_confirm": command_type
        })

    if command_type == "SELECT" or (command_type in ALLOWED_WRITE_OPERATIONS and is_confirmed_execution):
        sql_to_execute = data.get("confirmed_sql_query", sql_query)
        query_type_to_execute = data.get("confirmed_query_type", command_type)

        if not sql_to_execute or not query_type_to_execute:
            return jsonify({"error": "Missing confirmed query for execution."}), 400
        
        print(f"Proceeding with {query_type_to_execute} execution: {sql_to_execute}")
        execution_result = execute_query(sql_to_execute, query_type_to_execute) # No params for LLM generated DML for now

        if "error" in execution_result:
            return jsonify({
                "response_text": f"Database error: {execution_result['error']}",
                "type": "EXECUTION_ERROR",
                "query_attempted": execution_result.get("query_attempted", sql_to_execute)
            }), 500
        else:
            if query_type_to_execute == "SELECT":
                 return jsonify({
                    "response_text": "Here's the data I found:",
                    "type": "DATA_RESULT",
                    "data": execution_result.get("data"),
                    "query_executed": sql_to_execute
                })
            else: # INSERT, UPDATE
                return jsonify({
                    "response_text": execution_result.get("message", "Operation completed."),
                    "type": "ACTION_SUCCESS",
                    "rows_affected": execution_result.get("rows_affected"),
                    "new_employee_id": execution_result.get("new_employee_id"), # If applicable
                    "query_executed": sql_to_execute
                })
    else:
        return jsonify({"response_text": "An unexpected state occurred.", "type": "ERROR"}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)