import sqlite3

# Connect to database (creates file if not exists)
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Create Students Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    roll_no TEXT,
    department TEXT,
    face_encoding TEXT
)
''')

# Create Attendance Table
cursor.execute('''
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    date TEXT,
    time TEXT,
    status TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
)
''')

# Save and close
conn.commit()
conn.close()

print("Database and tables created successfully!")