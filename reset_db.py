import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Delete all records
cursor.execute("DELETE FROM attendance")
cursor.execute("DELETE FROM students")

# Reset auto-increment IDs
cursor.execute("DELETE FROM sqlite_sequence WHERE name='students'")
cursor.execute("DELETE FROM sqlite_sequence WHERE name='attendance'")

conn.commit()
conn.close()

print("Database reset successfully!")