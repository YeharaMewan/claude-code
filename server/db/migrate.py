"""
Database migration utilities for HR Agent
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Get database connection from environment variables"""
    database_url = os.getenv('DATABASE_URL', 'postgresql://hruser:hrpass@localhost:5432/hrdb')
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

def run_migrations():
    """Run database migrations"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Read and execute schema file
        schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
        
        logger.info("Running database migrations...")
        cur.execute(schema_sql)
        conn.commit()
        logger.info("Database migrations completed successfully")
        
        # Insert sample data if tables are empty
        cur.execute("SELECT COUNT(*) FROM employees")
        if cur.fetchone()[0] == 0:
            logger.info("Inserting sample data...")
            insert_sample_data(cur)
            conn.commit()
            logger.info("Sample data inserted")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        raise

def insert_sample_data(cur):
    """Insert sample data for development"""
    
    # Sample employees
    employees_data = [
        ('EMP001', 'John Doe', 'john.doe@company.com', 'hr', 'Human Resources', '2022-01-15'),
        ('EMP002', 'Jane Smith', 'jane.smith@company.com', 'leader', 'Engineering', '2022-03-20'),
        ('EMP003', 'Bob Johnson', 'bob.johnson@company.com', 'employee', 'Engineering', '2022-06-10'),
        ('EMP004', 'Alice Brown', 'alice.brown@company.com', 'employee', 'Marketing', '2022-08-05'),
        ('EMP005', 'Charlie Wilson', 'charlie.wilson@company.com', 'leader', 'Sales', '2022-02-12'),
    ]
    
    for emp_id, name, email, role, dept, hire_date in employees_data:
        cur.execute("""
            INSERT INTO employees (employee_id, name, email, role, department, hire_date)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (employee_id) DO NOTHING
        """, (emp_id, name, email, role, dept, hire_date))
    
    # Sample attendance records
    cur.execute("""
        INSERT INTO attendance (employee_id, date, check_in, check_out, status)
        VALUES 
            ('EMP001', CURRENT_DATE - INTERVAL '1 day', CURRENT_DATE - INTERVAL '1 day' + TIME '09:00:00', CURRENT_DATE - INTERVAL '1 day' + TIME '17:30:00', 'present'),
            ('EMP002', CURRENT_DATE - INTERVAL '1 day', CURRENT_DATE - INTERVAL '1 day' + TIME '09:15:00', CURRENT_DATE - INTERVAL '1 day' + TIME '18:00:00', 'present'),
            ('EMP003', CURRENT_DATE - INTERVAL '1 day', CURRENT_DATE - INTERVAL '1 day' + TIME '09:30:00', CURRENT_DATE - INTERVAL '1 day' + TIME '17:45:00', 'present'),
            ('EMP001', CURRENT_DATE, CURRENT_DATE + TIME '09:05:00', NULL, 'present'),
            ('EMP002', CURRENT_DATE, CURRENT_DATE + TIME '09:10:00', NULL, 'present')
        ON CONFLICT (employee_id, date) DO NOTHING
    """)
    
    # Sample tasks
    tasks_data = [
        ('EMP002', 'Complete project review', 'Review all pending projects and provide feedback', 'in_progress', 'high', 'EMP001'),
        ('EMP003', 'Update documentation', 'Update technical documentation for the new features', 'pending', 'medium', 'EMP002'),
        ('EMP004', 'Prepare marketing campaign', 'Create materials for Q4 marketing campaign', 'completed', 'high', 'EMP005'),
    ]
    
    for emp_id, title, desc, status, priority, assigned_by in tasks_data:
        cur.execute("""
            INSERT INTO tasks (employee_id, title, description, status, priority, assigned_by, due_date)
            VALUES (%s, %s, %s, %s, %s, %s, CURRENT_DATE + INTERVAL '7 days')
        """, (emp_id, title, desc, status, priority, assigned_by))

def check_connection(silent=False):
    """Test database connection"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        if not silent:
            logger.info(f"Database connected: {version}")
        cur.close()
        conn.close()
        return True
    except Exception as e:
        if not silent:
            logger.error(f"Database connection failed: {e}")
        return False

if __name__ == "__main__":
    if check_connection():
        run_migrations()
    else:
        logger.error("Cannot connect to database. Please check your configuration.")